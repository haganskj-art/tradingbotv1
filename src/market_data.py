from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import time
import requests
import pandas as pd


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
    candles: Optional[pd.DataFrame] = None

    @property
    def age_seconds(self) -> float | None:
        if self.timestamp is None:
            return None
        return max(0.0, time.time() - self.timestamp.timestamp())


class YahooDelayedFeed:
    """Polling feed using Yahoo Finance's public chart endpoint.

    Yahoo labels CME futures quotes as delayed. The feed now also returns recent
    1-minute OHLCV candles so the signal engine can use trend, momentum,
    volatility, VWAP, volume and multi-timeframe confirmation instead of relying
    on a single last-price z-score.
    """

    SYMBOLS = {
        "NQ": "NQ=F",
        "MNQ": "MNQ=F",
    }

    def __init__(self, timeout: float = 8.0):
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
        result = response.json()["chart"]["result"][0]
        meta = result.get("meta", {})

        timestamps = result.get("timestamp", [])
        q = result.get("indicators", {}).get("quote", [{}])[0]
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": q.get("open", []),
            "high": q.get("high", []),
            "low": q.get("low", []),
            "close": q.get("close", []),
            "volume": q.get("volume", []),
        })
        if not df.empty:
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"]).drop_duplicates("timestamp").sort_values("timestamp")
            # Keep a compact working window. The engine only needs recent bars.
            df = df.tail(450).reset_index(drop=True)

        price = meta.get("regularMarketPrice")
        if price is None and not df.empty:
            price = float(df["close"].iloc[-1])
        if price is None:
            price = meta.get("chartPreviousClose")
        if price is None:
            raise RuntimeError("Yahoo returned no usable price data.")

        epoch = meta.get("regularMarketTime")
        if epoch is None and not df.empty:
            epoch = int(df["timestamp"].iloc[-1].timestamp())
        timestamp = datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None
        volume = meta.get("regularMarketVolume")
        if volume is None and not df.empty:
            volume = float(df["volume"].iloc[-1]) if pd.notna(df["volume"].iloc[-1]) else None

        # Yahoo's public chart response does not provide a dependable top-of-book.
        # Do not pretend bid/ask are live; use last price as a display placeholder.
        return Quote(
            symbol=symbol,
            price=float(price),
            bid=float(price),
            ask=float(price),
            timestamp=timestamp,
            source="Yahoo Finance",
            delayed=True,
            volume=float(volume) if volume is not None else None,
            candles=df,
        )
