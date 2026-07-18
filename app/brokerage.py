from __future__ import annotations

from typing import Dict


ZERODHA_OPTION_BROKERAGE_RATE = 0.0003
ZERODHA_OPTION_BROKERAGE_CAP = 20.0
NFO_TRANSACTION_CHARGE_RATE = 0.0003503
SEBI_CHARGE_RATE = 0.000001
GST_RATE = 0.18
STAMP_DUTY_BUY_RATE = 0.00003
STT_OPTION_SELL_RATE = 0.0015


def _brokerage(order_value: float) -> float:
    return min(ZERODHA_OPTION_BROKERAGE_CAP, order_value * ZERODHA_OPTION_BROKERAGE_RATE)


def calculate_option_roundtrip_charges(
    entry_credit_points: float,
    exit_debit_points: float,
    quantity: int,
) -> Dict[str, float]:
    sell_value = max(entry_credit_points, 0.0) * quantity
    buy_value = max(exit_debit_points, 0.0) * quantity
    turnover = sell_value + buy_value

    sell_brokerage = _brokerage(sell_value)
    buy_brokerage = _brokerage(buy_value)
    brokerage = sell_brokerage + buy_brokerage
    transaction_charges = turnover * NFO_TRANSACTION_CHARGE_RATE
    sebi_charges = turnover * SEBI_CHARGE_RATE
    gst = GST_RATE * (brokerage + transaction_charges + sebi_charges)
    stamp_duty = buy_value * STAMP_DUTY_BUY_RATE
    stt = sell_value * STT_OPTION_SELL_RATE
    total = brokerage + transaction_charges + sebi_charges + gst + stamp_duty + stt

    return {
        "sell_value": round(sell_value, 2),
        "buy_value": round(buy_value, 2),
        "brokerage": round(brokerage, 2),
        "transaction_charges": round(transaction_charges, 2),
        "sebi_charges": round(sebi_charges, 2),
        "gst": round(gst, 2),
        "stamp_duty": round(stamp_duty, 2),
        "stt": round(stt, 2),
        "total": round(total, 2),
    }
