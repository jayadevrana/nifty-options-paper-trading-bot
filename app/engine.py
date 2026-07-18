from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .brokerage import calculate_option_roundtrip_charges
from .config import settings
from .db import Database
from .market_data import NSEPublicDataProvider
from .models import ChainSnapshot, StrategyPlan
from .strategy import MyFirstStrategy


class PaperTradingEngine:
    def __init__(self) -> None:
        self.db = Database(settings.db_path)
        self.provider = NSEPublicDataProvider()
        self.strategy = MyFirstStrategy()
        self.lock = asyncio.Lock()
        self.last_snapshot: Optional[ChainSnapshot] = None
        self.last_error: Optional[str] = None
        self.last_plan: Optional[StrategyPlan] = None
        self.background_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self.db.init()
        if not self.db.get_state("engine_control"):
            self.db.set_state("engine_control", {"enabled": True})
        self.background_task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as exc:  # pragma: no cover - defensive runtime path
                self.last_error = str(exc)
            await asyncio.sleep(settings.polling_seconds)

    async def tick(self) -> None:
        async with self.lock:
            control = self.db.get_state("engine_control", {"enabled": True})
            now = datetime.now(settings.timezone)
            trading_day = now.date().isoformat()
            day_state = self.db.get_state(
                "day_state",
                {
                    "trading_day": trading_day,
                    "opening_prices": [],
                    "trade_taken": False,
                    "last_note": "Waiting for market.",
                },
            )
            if day_state.get("trading_day") != trading_day:
                day_state = {
                    "trading_day": trading_day,
                    "opening_prices": [],
                    "trade_taken": False,
                    "last_note": "New trading day.",
                }

            snapshot = self.provider.fetch_chain("NIFTY")
            self.last_snapshot = snapshot
            self.last_error = None

            if (
                now.date() >= settings.paper_start_date
                and now.weekday() < 5
                and settings.market_open <= now.time() <= settings.range_end
            ):
                day_state["opening_prices"].append(round(snapshot.spot, 2))

            open_trade = self.db.get_open_trade()
            if open_trade:
                await self._manage_open_trade(snapshot, now, open_trade)

            opening_range_points = self._opening_range_points(day_state["opening_prices"])
            realized_today = self.db.realized_pnl_for_day(trading_day)
            current_drawdown_pct = self._current_drawdown_pct()
            self.last_plan = self.strategy.build_plan(
                snapshot=snapshot,
                opening_range_points=opening_range_points or settings.preview_fallback_range_points,
                capital=settings.capital,
                realized_today=realized_today,
                current_drawdown_pct=current_drawdown_pct,
            )

            if (
                control.get("enabled", True)
                and not self.db.get_open_trade()
                and now.date() >= settings.paper_start_date
                and now.weekday() < 5
                and settings.entry_start <= now.time() <= settings.entry_cutoff
                and not day_state.get("trade_taken")
            ):
                if self.last_plan.valid:
                    self._open_trade(self.last_plan, snapshot, now)
                    day_state["trade_taken"] = True
                    day_state["last_note"] = "Paper trade opened."
                else:
                    day_state["last_note"] = self.last_plan.reason

            self._record_equity(snapshot, trading_day)
            self.db.set_state("day_state", day_state)

    async def _manage_open_trade(
        self,
        snapshot: ChainSnapshot,
        now: datetime,
        open_trade: Dict[str, Any],
    ) -> None:
        mark = self.strategy.mark_to_market(snapshot, open_trade)
        exit_reason = mark.exit_signal
        if now.time() >= settings.exit_time:
            exit_reason = exit_reason or "Timed exit"
        if exit_reason:
            self._close_trade(open_trade, snapshot, now, mark.current_debit_points, exit_reason)

    def _open_trade(self, plan: StrategyPlan, snapshot: ChainSnapshot, now: datetime) -> None:
        payload = {
            "strategy_name": settings.app_name,
            "trade_date": now.date().isoformat(),
            "opened_at": now.isoformat(),
            "closed_at": None,
            "expiry": plan.expiry,
            "status": "OPEN",
            "lots": plan.lots,
            "lot_size": plan.lot_size,
            "short_call_strike": plan.short_call_strike,
            "long_call_strike": plan.long_call_strike,
            "short_put_strike": plan.short_put_strike,
            "long_put_strike": plan.long_put_strike,
            "entry_credit": plan.credit_points,
            "exit_debit": None,
            "gross_pnl": None,
            "charges": None,
            "net_pnl": None,
            "max_risk": plan.total_max_loss,
            "estimated_margin": plan.total_estimated_margin,
            "entry_spot": snapshot.spot,
            "exit_spot": None,
            "entry_vix": snapshot.vix,
            "exit_reason": None,
            "entry_reason": plan.reason,
            "notes_json": json.dumps(
                {
                    "reference_naked_margin_per_lot": plan.reference_naked_margin_per_lot,
                    "opening_range_points": plan.opening_range_points,
                    "credit_points_per_spread": plan.credit_points,
                }
            ),
        }
        self.db.insert_trade(payload)

    def _close_trade(
        self,
        open_trade: Dict[str, Any],
        snapshot: ChainSnapshot,
        now: datetime,
        exit_debit_points: float,
        exit_reason: str,
    ) -> None:
        quantity = int(open_trade["lot_size"]) * int(open_trade["lots"])
        gross_pnl = round(
            (float(open_trade["entry_credit"]) - exit_debit_points) * quantity,
            2,
        )
        charges = calculate_option_roundtrip_charges(
            entry_credit_points=float(open_trade["entry_credit"]),
            exit_debit_points=exit_debit_points,
            quantity=quantity,
        )
        net_pnl = round(gross_pnl - charges["total"], 2)
        self.db.update_trade(
            int(open_trade["id"]),
            {
                "status": "CLOSED",
                "closed_at": now.isoformat(),
                "exit_debit": round(exit_debit_points, 2),
                "gross_pnl": gross_pnl,
                "charges": charges["total"],
                "net_pnl": net_pnl,
                "exit_spot": round(snapshot.spot, 2),
                "exit_reason": exit_reason,
                "notes_json": json.dumps(
                    {
                        **json.loads(open_trade.get("notes_json") or "{}"),
                        "charges_breakdown": charges,
                    }
                ),
            },
        )

    def _record_equity(self, snapshot: ChainSnapshot, trading_day: str) -> None:
        open_trade = self.db.get_open_trade()
        unrealized = 0.0
        if open_trade:
            unrealized = self.strategy.mark_to_market(snapshot, open_trade).gross_pnl
        realized = self.db.realized_pnl_total()
        equity = round(settings.capital + realized + unrealized, 2)
        history = self.db.list_equity_points(limit=1)
        last_peak = float(history[-1]["peak_equity"]) if history else settings.capital
        peak_equity = max(last_peak, equity)
        drawdown = round(peak_equity - equity, 2)
        self.db.upsert_equity_point(
            {
                "timestamp": datetime.now(settings.timezone).isoformat(),
                "trading_day": trading_day,
                "equity": equity,
                "realized_pnl": round(realized, 2),
                "unrealized_pnl": round(unrealized, 2),
                "peak_equity": round(peak_equity, 2),
                "drawdown": drawdown,
            }
        )

    def _opening_range_points(self, prices: List[float]) -> float:
        if len(prices) < 2:
            return 0.0
        return round(max(prices) - min(prices), 2)

    def _current_drawdown_pct(self) -> float:
        history = self.db.list_equity_points(limit=1)
        if not history:
            return 0.0
        latest = history[-1]
        peak = float(latest["peak_equity"]) or settings.capital
        drawdown = float(latest["drawdown"])
        return drawdown / peak if peak else 0.0

    async def set_enabled(self, enabled: bool) -> Dict[str, Any]:
        async with self.lock:
            self.db.set_state("engine_control", {"enabled": enabled})
            return {"enabled": enabled}

    async def preview(self) -> Dict[str, Any]:
        async with self.lock:
            snapshot = self.provider.fetch_chain("NIFTY")
            self.last_snapshot = snapshot
            plan = self.strategy.build_plan(
                snapshot=snapshot,
                opening_range_points=settings.preview_fallback_range_points,
                capital=settings.capital,
                realized_today=self.db.realized_pnl_for_day(
                    datetime.now(settings.timezone).date().isoformat()
                ),
                current_drawdown_pct=self._current_drawdown_pct(),
            )
            self.last_plan = plan
            return plan.to_dict()

    async def state(self) -> Dict[str, Any]:
        async with self.lock:
            control = self.db.get_state("engine_control", {"enabled": True})
            day_state = self.db.get_state("day_state", {})
            open_trade = self.db.get_open_trade()
            trades = self.db.list_trades(limit=50)
            equity_points = self.db.list_equity_points(limit=300)
            latest_equity = equity_points[-1] if equity_points else None

            drawdown_map: List[Dict[str, Any]] = []
            by_day: Dict[str, float] = {}
            for row in equity_points:
                day = row["trading_day"]
                by_day[day] = max(by_day.get(day, 0.0), float(row["drawdown"]))
            for trading_day, worst in sorted(by_day.items()):
                drawdown_map.append({"trading_day": trading_day, "worst_drawdown": round(worst, 2)})

            if open_trade and self.last_snapshot:
                open_trade = {
                    **open_trade,
                    "mark_to_market": self.strategy.mark_to_market(self.last_snapshot, open_trade).to_dict(),
                }

            return {
                "app_name": settings.app_name,
                "capital": settings.capital,
                "paper_start_date": settings.paper_start_date.isoformat(),
                "timezone": settings.timezone_name,
                "provider": settings.data_provider,
                "engine_enabled": bool(control.get("enabled", True)),
                "last_error": self.last_error,
                "last_snapshot": {
                    "spot": round(self.last_snapshot.spot, 2),
                    "vix": round(self.last_snapshot.vix, 2),
                    "expiry": self.last_snapshot.expiry,
                    "exchange_timestamp": self.last_snapshot.exchange_timestamp,
                    "fetched_at": self.last_snapshot.fetched_at.isoformat(),
                    "lot_size": self.last_snapshot.lot_size,
                }
                if self.last_snapshot
                else None,
                "day_state": day_state,
                "preview_plan": self.last_plan.to_dict() if self.last_plan else None,
                "open_trade": open_trade,
                "trades": trades,
                "equity_points": equity_points,
                "latest_equity": latest_equity,
                "drawdown_map": drawdown_map,
            }
