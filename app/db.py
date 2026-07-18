from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    expiry TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lots INTEGER NOT NULL,
                    lot_size INTEGER NOT NULL,
                    short_call_strike INTEGER NOT NULL,
                    long_call_strike INTEGER NOT NULL,
                    short_put_strike INTEGER NOT NULL,
                    long_put_strike INTEGER NOT NULL,
                    entry_credit REAL NOT NULL,
                    exit_debit REAL,
                    gross_pnl REAL,
                    charges REAL,
                    net_pnl REAL,
                    max_risk REAL NOT NULL,
                    estimated_margin REAL NOT NULL,
                    entry_spot REAL NOT NULL,
                    exit_spot REAL,
                    entry_vix REAL NOT NULL,
                    exit_reason TEXT,
                    entry_reason TEXT,
                    notes_json TEXT
                );

                CREATE TABLE IF NOT EXISTS equity_points (
                    timestamp TEXT PRIMARY KEY,
                    trading_day TEXT NOT NULL,
                    equity REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    peak_equity REAL NOT NULL,
                    drawdown REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def set_state(self, key: str, value: Dict[str, Any]) -> None:
        payload = json.dumps(value)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO state(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, payload),
            )

    def get_state(self, key: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        if not row:
            return default or {}
        return json.loads(row["value"])

    def insert_trade(self, payload: Dict[str, Any]) -> int:
        columns = ", ".join(payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        values = tuple(payload.values())
        with self.connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO trades ({columns}) VALUES ({placeholders})",
                values,
            )
            return int(cursor.lastrowid)

    def update_trade(self, trade_id: int, payload: Dict[str, Any]) -> None:
        assignments = ", ".join(f"{key} = ?" for key in payload)
        values = tuple(payload.values()) + (trade_id,)
        with self.connect() as conn:
            conn.execute(f"UPDATE trades SET {assignments} WHERE id = ?", values)

    def get_open_trade(self) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY opened_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def list_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def realized_pnl_total(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(net_pnl), 0) AS total FROM trades WHERE status = 'CLOSED'"
            ).fetchone()
        return float(row["total"] if row else 0.0)

    def realized_pnl_for_day(self, trading_day: str) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(net_pnl), 0) AS total
                FROM trades
                WHERE status = 'CLOSED' AND trade_date = ?
                """,
                (trading_day,),
            ).fetchone()
        return float(row["total"] if row else 0.0)

    def upsert_equity_point(self, payload: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO equity_points(
                    timestamp, trading_day, equity, realized_pnl, unrealized_pnl, peak_equity, drawdown
                ) VALUES(
                    :timestamp, :trading_day, :equity, :realized_pnl, :unrealized_pnl, :peak_equity, :drawdown
                )
                ON CONFLICT(timestamp) DO UPDATE SET
                    trading_day=excluded.trading_day,
                    equity=excluded.equity,
                    realized_pnl=excluded.realized_pnl,
                    unrealized_pnl=excluded.unrealized_pnl,
                    peak_equity=excluded.peak_equity,
                    drawdown=excluded.drawdown
                """,
                payload,
            )

    def list_equity_points(self, limit: int = 500) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM equity_points
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = [dict(row) for row in rows]
        result.reverse()
        return result
