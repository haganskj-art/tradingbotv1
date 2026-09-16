from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import time
import requests


@dataclass
class Quote:
    symbol: str
    price: float
    bid: float
    ask: float
    timestamp: Optional[datetime]
    source: str
    delayed: bool
    volume: float | None = None

    @property
    def age_seconds(self) -> float | None:
        if self.timestamp is None:
            return None
        return max(0.0, time.time() - self.timestamp.timestamp())


class YahooDelayedFeed:
    """Polling feed using Yahoo Finance's public chart endpoint.

    Yahoo labels CME futures quotes as delayed. This is therefore a monitoring
    prototype, not a real-time execution-grade market-data feed.
    """

    SYMBOLS = {
        "NQ": "NQ=F",
        "MNQ": "MNQ=F",
    }

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
        })

    def fetch(self, market: str) -> Quote:
        market = market.upper()
        symbol = self.SYMBOLS[market]
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"range": "1d", "interval": "1m", "includePrePost": "true"}
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()["chart"]["result"][0]
        meta = payload.get("meta", {})

        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        if price is None:
            quotes = payload.get("indicators", {}).get("quote", [{}])[0]
            closes = [x for x in quotes.get("close", []) if x is not None]
            if not closes:
                raise RuntimeError("Yahoo returned no usable price data.")
            price = closes[-1]

        epoch = meta.get("regularMarketTime")
        timestamp = datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None
        volume = meta.get("regularMarketVolume")

        # Yahoo's public quote does not provide a dependable bid/ask in the
        # chart response. Use the last/market price for both so the app can
        # continue to display a complete quote panel without pretending it is
        # a real top-of-book feed.
        return Quote(
            symbol=symbol,
            price=float(price),
            bid=float(price),
            ask=float(price),
            timestamp=timestamp,
            source="Yahoo Finance",
            delayed=True,
            volume=float(volume) if volume is not None else None,
        )
