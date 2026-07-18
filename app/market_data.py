from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List

import requests

from .config import settings
from .models import ChainSnapshot, OptionQuote


class NSEPublicDataProvider:
    BASE_URL = "https://www.nseindia.com"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.headers = {
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "accept-language": "en-US,en;q=0.9",
            "accept": "application/json,text/plain,*/*",
            "referer": f"{self.BASE_URL}/option-chain",
        }
        self._bootstrap()

    def _bootstrap(self) -> None:
        self.session.get(
            f"{self.BASE_URL}/option-chain",
            headers=self.headers,
            timeout=20,
        )

    def _get_json(self, path: str) -> Dict:
        response = self.session.get(
            f"{self.BASE_URL}{path}",
            headers=self.headers,
            timeout=20,
        )
        if response.status_code >= 400:
            self._bootstrap()
            response = self.session.get(
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                timeout=20,
            )
        response.raise_for_status()
        payload = response.json()
        if payload == {}:
            self._bootstrap()
            response = self.session.get(
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        return payload

    def fetch_indices(self) -> Dict[str, float]:
        payload = self._get_json("/api/allIndices")
        spot = None
        vix = None
        for row in payload.get("data", []):
            index_name = str(row.get("index", "")).upper()
            symbol = str(row.get("indexSymbol", "")).upper()
            if symbol == "NIFTY 50" or index_name == "NIFTY 50":
                spot = float(row.get("last", 0.0))
            if symbol == "INDIA VIX" or index_name == "INDIA VIX":
                vix = float(row.get("last", 0.0))
        if spot is None:
            raise RuntimeError("Unable to fetch NIFTY spot from NSE indices endpoint.")
        return {"spot": spot, "vix": float(vix or 0.0)}

    def fetch_expiries(self, symbol: str = "NIFTY") -> List[str]:
        payload = self._get_json(f"/api/option-chain-contract-info?symbol={symbol}")
        return [str(item) for item in payload.get("expiryDates", [])]

    def nearest_expiry(self, today: date, symbol: str = "NIFTY") -> str:
        expiries = self.fetch_expiries(symbol)
        parsed = []
        for item in expiries:
            try:
                parsed.append((datetime.strptime(item, "%d-%b-%Y").date(), item))
            except ValueError:
                continue
        future = [entry for entry in parsed if entry[0] >= today]
        selected = future[0] if future else parsed[0]
        return selected[1]

    def fetch_chain(self, symbol: str = "NIFTY", expiry: str | None = None) -> ChainSnapshot:
        now = datetime.now(settings.timezone)
        expiry = expiry or self.nearest_expiry(now.date(), symbol)
        index_data = self.fetch_indices()
        payload = self._get_json(
            f"/api/option-chain-v3?type=Indices&symbol={symbol}&expiry={expiry}"
        )
        records = payload["records"]
        lot_size = 0
        quotes: Dict[str, Dict[int, OptionQuote]] = {"CE": {}, "PE": {}}

        for row in records.get("data", []):
            for option_type in ("CE", "PE"):
                leg = row.get(option_type)
                if not leg:
                    continue
                strike = int(leg.get("strikePrice", row.get("strikePrice")))
                lot_size = int(leg.get("marketLot", lot_size or 0))
                quotes[option_type][strike] = OptionQuote(
                    strike=strike,
                    option_type=option_type,
                    last_price=float(leg.get("lastPrice") or 0.0),
                    open_interest=int(leg.get("openInterest") or 0),
                    volume=int(leg.get("totalTradedVolume") or 0),
                )

        return ChainSnapshot(
            fetched_at=now,
            exchange_timestamp=str(records.get("timestamp", "")),
            spot=float(records.get("underlyingValue") or index_data["spot"]),
            vix=index_data["vix"],
            symbol=symbol,
            expiry=expiry,
            lot_size=lot_size or 65,
            quotes=quotes,
        )
