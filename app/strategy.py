from __future__ import annotations

from math import floor
from typing import Optional

from .config import settings
from .models import ChainSnapshot, MarkToMarket, StrategyPlan


def _round_to_step(value: float, step: int) -> int:
    return int(round(value / step) * step)


def _ceil_to_step(value: float, step: int) -> int:
    multiple = int(value // step)
    if value % step == 0:
        return multiple * step
    return (multiple + 1) * step


def _floor_to_step(value: float, step: int) -> int:
    return int(value // step) * step


class MyFirstStrategy:
    def build_plan(
        self,
        snapshot: ChainSnapshot,
        opening_range_points: float,
        capital: float,
        realized_today: float,
        current_drawdown_pct: float,
    ) -> StrategyPlan:
        step = settings.strike_step
        atm = _round_to_step(snapshot.spot, step)
        atm_ce = snapshot.get_price(atm, "CE")
        atm_pe = snapshot.get_price(atm, "PE")
        if atm_ce is None or atm_pe is None:
            return self._invalid(snapshot, opening_range_points, "ATM quotes missing.")

        if current_drawdown_pct >= settings.max_drawdown_pct:
            return self._invalid(
                snapshot,
                opening_range_points,
                "Overall drawdown cutoff reached.",
            )

        if opening_range_points > settings.max_opening_range_points:
            return self._invalid(
                snapshot,
                opening_range_points,
                "Opening range too wide for safe premium selling.",
            )

        if snapshot.vix >= settings.vix_skip_threshold:
            return self._invalid(
                snapshot,
                opening_range_points,
                "India VIX too high for this strategy.",
            )

        atm_straddle = atm_ce + atm_pe
        distance = max(100, opening_range_points, atm_straddle * 0.35)
        distance = _ceil_to_step(distance, step)

        short_call = _ceil_to_step(snapshot.spot + distance, step)
        short_put = _floor_to_step(snapshot.spot - distance, step)
        long_call = short_call + settings.wing_width_points
        long_put = short_put - settings.wing_width_points

        short_call_price = snapshot.get_price(short_call, "CE")
        long_call_price = snapshot.get_price(long_call, "CE")
        short_put_price = snapshot.get_price(short_put, "PE")
        long_put_price = snapshot.get_price(long_put, "PE")
        if None in (short_call_price, long_call_price, short_put_price, long_put_price):
            return self._invalid(
                snapshot,
                opening_range_points,
                "Required hedge strikes are not available.",
            )

        credit_points = round(
            short_call_price + short_put_price - long_call_price - long_put_price,
            2,
        )
        if credit_points < settings.min_credit_points:
            return self._invalid(
                snapshot,
                opening_range_points,
                "Net credit too low after hedging.",
            )

        max_loss_per_lot = round(
            max(settings.wing_width_points - credit_points, 0.0) * snapshot.lot_size,
            2,
        )
        estimated_margin_per_lot = round(
            max(15000.0, max_loss_per_lot * 2.0),
            2,
        )
        reference_naked_margin_per_lot = round(snapshot.spot * snapshot.lot_size * 0.09, 2)

        daily_loss_budget_remaining = max(
            0.0,
            (capital * settings.max_daily_loss_pct) + min(realized_today, 0.0),
        )
        risk_budget = min(capital * settings.max_risk_per_trade_pct, daily_loss_budget_remaining)
        lots_by_risk = int(floor(risk_budget / max_loss_per_lot)) if max_loss_per_lot else 0
        lots_by_margin = int(
            floor((capital * settings.max_margin_usage_pct) / estimated_margin_per_lot)
        )
        lots = max(0, min(lots_by_risk, lots_by_margin, 5))

        if snapshot.vix >= settings.vix_reduce_threshold:
            lots = max(1, lots // 2) if lots else 0

        if lots < 1:
            return self._invalid(
                snapshot,
                opening_range_points,
                "Capital or risk budget does not allow even one lot today.",
            )

        total_max_loss = round(max_loss_per_lot * lots, 2)
        total_estimated_margin = round(estimated_margin_per_lot * lots, 2)

        return StrategyPlan(
            valid=True,
            reason="Entry conditions satisfied.",
            symbol=snapshot.symbol,
            expiry=snapshot.expiry,
            lot_size=snapshot.lot_size,
            spot=round(snapshot.spot, 2),
            vix=round(snapshot.vix, 2),
            opening_range_points=round(opening_range_points, 2),
            atm_strike=atm,
            short_call_strike=short_call,
            long_call_strike=long_call,
            short_put_strike=short_put,
            long_put_strike=long_put,
            credit_points=credit_points,
            max_loss_per_lot=max_loss_per_lot,
            estimated_margin_per_lot=estimated_margin_per_lot,
            reference_naked_margin_per_lot=reference_naked_margin_per_lot,
            lots=lots,
            total_max_loss=total_max_loss,
            total_estimated_margin=total_estimated_margin,
        )

    def mark_to_market(self, snapshot: ChainSnapshot, trade: dict) -> MarkToMarket:
        current_debit = self._current_debit(snapshot, trade)
        gross_pnl = round(
            (float(trade["entry_credit"]) - current_debit)
            * int(trade["lot_size"])
            * int(trade["lots"]),
            2,
        )
        exit_signal: Optional[str] = None
        target_price = float(trade["entry_credit"]) * (1 - settings.target_capture_pct)
        stop_price = float(trade["entry_credit"]) * settings.stop_loss_multiple

        if current_debit <= target_price:
            exit_signal = "Profit target hit"
        elif current_debit >= stop_price:
            exit_signal = "Stop-loss hit"
        elif snapshot.spot >= int(trade["short_call_strike"]) - settings.breach_buffer_points:
            exit_signal = "Call side breached"
        elif snapshot.spot <= int(trade["short_put_strike"]) + settings.breach_buffer_points:
            exit_signal = "Put side breached"

        return MarkToMarket(
            current_debit_points=round(current_debit, 2),
            gross_pnl=gross_pnl,
            exit_signal=exit_signal,
        )

    def _current_debit(self, snapshot: ChainSnapshot, trade: dict) -> float:
        short_call = snapshot.get_price(int(trade["short_call_strike"]), "CE") or 0.0
        short_put = snapshot.get_price(int(trade["short_put_strike"]), "PE") or 0.0
        long_call = snapshot.get_price(int(trade["long_call_strike"]), "CE") or 0.0
        long_put = snapshot.get_price(int(trade["long_put_strike"]), "PE") or 0.0
        return max(round(short_call + short_put - long_call - long_put, 2), 0.0)

    def _invalid(self, snapshot: ChainSnapshot, opening_range_points: float, reason: str) -> StrategyPlan:
        return StrategyPlan(
            valid=False,
            reason=reason,
            symbol=snapshot.symbol,
            expiry=snapshot.expiry,
            lot_size=snapshot.lot_size,
            spot=round(snapshot.spot, 2),
            vix=round(snapshot.vix, 2),
            opening_range_points=round(opening_range_points, 2),
            atm_strike=_round_to_step(snapshot.spot, settings.strike_step),
            short_call_strike=0,
            long_call_strike=0,
            short_put_strike=0,
            long_put_strike=0,
            credit_points=0.0,
            max_loss_per_lot=0.0,
            estimated_margin_per_lot=0.0,
            reference_naked_margin_per_lot=0.0,
            lots=0,
            total_max_loss=0.0,
            total_estimated_margin=0.0,
        )
