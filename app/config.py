from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    app_name: str = "my first strategy with claude"
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = _env_int("APP_PORT", 8000)
    timezone_name: str = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
    capital: float = _env_float("APP_CAPITAL", 1_000_000.0)
    paper_start_date: date = date.fromisoformat(
        os.getenv("APP_PAPER_START_DATE", "2026-03-26")
    )
    data_provider: str = os.getenv("APP_DATA_PROVIDER", "nse_public")
    db_path: Path = BASE_DIR / "paper_trading.db"
    polling_seconds: int = _env_int("APP_POLLING_SECONDS", 60)
    market_open: time = time(9, 15)
    range_end: time = time(9, 30)
    entry_start: time = time(9, 35)
    entry_cutoff: time = time(10, 15)
    exit_time: time = time(15, 15)
    max_risk_per_trade_pct: float = 0.0125
    max_daily_loss_pct: float = 0.025
    max_drawdown_pct: float = 0.08
    max_margin_usage_pct: float = 0.30
    target_capture_pct: float = 0.45
    stop_loss_multiple: float = 1.60
    breach_buffer_points: int = 20
    min_credit_points: float = 20.0
    wing_width_points: int = 100
    strike_step: int = 50
    max_opening_range_points: int = 180
    vix_reduce_threshold: float = 20.0
    vix_skip_threshold: float = 28.0
    preview_fallback_range_points: int = 75

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


settings = Settings()
