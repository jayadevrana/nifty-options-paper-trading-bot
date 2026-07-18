from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class OptionQuote:
    strike: int
    option_type: str
    last_price: float
    open_interest: int
    volume: int


@dataclass
class ChainSnapshot:
    fetched_at: datetime
    exchange_timestamp: str
    spot: float
    vix: float
    symbol: str
    expiry: str
    lot_size: int
    quotes: Dict[str, Dict[int, OptionQuote]]

    def get_price(self, strike: int, option_type: str) -> Optional[float]:
        quote = self.quotes.get(option_type.upper(), {}).get(int(strike))
        return quote.last_price if quote else None


@dataclass
class StrategyPlan:
    valid: bool
    reason: str
    symbol: str
    expiry: str
    lot_size: int
    spot: float
    vix: float
    opening_range_points: float
    atm_strike: int
    short_call_strike: int
    long_call_strike: int
    short_put_strike: int
    long_put_strike: int
    credit_points: float
    max_loss_per_lot: float
    estimated_margin_per_lot: float
    reference_naked_margin_per_lot: float
    lots: int
    total_max_loss: float
    total_estimated_margin: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarkToMarket:
    current_debit_points: float
    gross_pnl: float
    exit_signal: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
