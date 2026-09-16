from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import websocket


@dataclass
class LiveQuote:
    symbol: str
    price: float
    bid: float
    ask: float
    timestamp: Optional[datetime]
    source: str = "CME WebSocket"
    delayed: bool = False
    volume: float | None = None
    candles: Optional[pd.DataFrame] = None
    connected: bool = False
    message_count: int = 0
    last_error: str = ""

    @property
    def age_seconds(self) -> float | None:
        if self.timestamp is None:
            return None
        return max(0.0, time.time() - self.timestamp.timestamp())


class CMERealtimeFeed:
    """Generic CME real-time WebSocket adapter.

    CME's portal supplies the environment-specific WebSocket URL, authentication
    method/headers, and subscription message. This adapter deliberately does not
    invent those values. Put the exact values supplied by CME into Streamlit
    secrets, then the adapter maintains a local 1-minute OHLCV buffer for GravAI.
    """

    def __init__(self, config: dict[str, Any]):
        self.url = str(config.get("CME_WS_URL", "")).strip()
        self.headers = self._json_object(config.get("CME_WS_HEADERS_JSON", "{}"))
        self.subscribe_message = self._json_value(config.get("CME_SUBSCRIBE_JSON", ""))
        self.symbol = str(config.get("CME_SYMBOL", "NQ")).strip() or "NQ"
        self.max_candles = int(config.get("CME_MAX_CANDLES", 500))
        self.timeout = float(config.get("CME_CONNECT_TIMEOUT", 10))
        self._ws = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._price = 0.0
        self._bid = 0.0
        self._ask = 0.0
        self._volume = 0.0
        self._timestamp: datetime | None = None
        self._bars = deque(maxlen=self.max_candles)
        self._connected = False
        self._message_count = 0
        self._last_error = ""
        self._last_bar_minute: pd.Timestamp | None = None
        self._bar = None

    @staticmethod
    def _json_object(value: Any) -> dict[str, str]:
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        if not value:
            return {}
        obj = json.loads(str(value))
        return {str(k): str(v) for k, v in obj.items()}

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, (dict, list)):
            return value
        return json.loads(str(value))

    def configured(self) -> bool:
        return bool(self.url and self.subscribe_message is not None)

    def start(self) -> None:
        if not self.configured():
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="grav-ai-cme-ws", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    self.url,
                    header=[f"{k}: {v}" for k, v in self.headers.items()],
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
                backoff = min(backoff * 1.5, 30.0)
            except Exception as exc:
                with self._lock:
                    self._last_error = f"CME connection error: {exc}"
                    self._connected = False
            if not self._stop.is_set():
                time.sleep(backoff)

    def _on_open(self, ws) -> None:
        with self._lock:
            self._connected = True
            self._last_error = ""
        try:
            ws.send(json.dumps(self.subscribe_message))
        except Exception as exc:
            with self._lock:
                self._last_error = f"Subscription send failed: {exc}"

    def _on_error(self, ws, error) -> None:
        with self._lock:
            self._connected = False
            self._last_error = str(error)

    def _on_close(self, ws, code, msg) -> None:
        with self._lock:
            self._connected = False
            if msg:
                self._last_error = str(msg)

    @staticmethod
    def _walk(obj: Any):
        if isinstance(obj, dict):
            for key, value in obj.items():
                yield str(key).lower(), value
                yield from CMERealtimeFeed._walk(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from CMERealtimeFeed._walk(value)

    @classmethod
    def _first_number(cls, obj: Any, aliases: tuple[str, ...]) -> float | None:
        aliases = tuple(a.lower() for a in aliases)
        for key, value in cls._walk(obj):
            if key in aliases:
                try:
                    n = float(value)
                    if n == n:
                        return n
                except (TypeError, ValueError):
                    continue
        return None

    @classmethod
    def _first_timestamp(cls, obj: Any) -> datetime:
        for key, value in cls._walk(obj):
            if key in ("timestamp", "time", "eventtime", "event_time", "transacttime", "update_time"):
                try:
                    n = float(value)
                    if n > 10_000_000_000:
                        n /= 1000.0
                    return datetime.fromtimestamp(n, tz=timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    pass
        return datetime.now(timezone.utc)

    def _on_message(self, ws, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Generic aliases intentionally support the common CME sample payload shapes.
        last = self._first_number(payload, ("lastprice", "last_price", "last", "tradeprice", "trade_price", "price"))
        bid = self._first_number(payload, ("bidprice", "bid_price", "bid"))
        ask = self._first_number(payload, ("askprice", "ask_price", "ask"))
        size = self._first_number(payload, ("quantity", "qty", "size", "volume", "tradevolume"))
        ts = self._first_timestamp(payload)

        if last is None and bid is not None and ask is not None:
            last = (bid + ask) / 2.0
        if last is None and bid is None and ask is None:
            return

        with self._lock:
            if bid is not None and bid > 0:
                self._bid = bid
            if ask is not None and ask > 0:
                self._ask = ask
            if last is not None and last > 0:
                self._price = last
            if size is not None and size >= 0:
                self._volume += size
            self._timestamp = ts
            self._message_count += 1
            self._append_tick(ts)

    def _append_tick(self, ts: datetime) -> None:
        minute = pd.Timestamp(ts).floor("min")
        price = self._price
        if price <= 0:
            return
        if self._last_bar_minute != minute:
            if self._bar is not None:
                self._bars.append(self._bar)
            self._last_bar_minute = minute
            self._bar = {
                "timestamp": minute.tz_convert("UTC"),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.0,
            }
        else:
            self._bar["high"] = max(self._bar["high"], price)
            self._bar["low"] = min(self._bar["low"], price)
            self._bar["close"] = price
        if self._bar is not None:
            self._bar["volume"] = self._volume

    def snapshot(self) -> LiveQuote:
        with self._lock:
            rows = list(self._bars)
            if self._bar is not None:
                rows = rows + [dict(self._bar)]
            df = pd.DataFrame(rows)
            if not df.empty:
                df = df.drop_duplicates("timestamp").sort_values("timestamp").tail(self.max_candles).reset_index(drop=True)
            return LiveQuote(
                symbol=self.symbol,
                price=float(self._price),
                bid=float(self._bid),
                ask=float(self._ask),
                timestamp=self._timestamp,
                volume=float(self._volume),
                candles=df,
                connected=self._connected,
                message_count=self._message_count,
                last_error=self._last_error,
            )
