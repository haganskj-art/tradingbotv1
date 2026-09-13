
from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from datetime import datetime

import numpy as np
import websocket


class MarketEngine:
    """
    V1 real-time BTCUSDT detector.

    Data:
      - Binance spot trade stream
      - Binance spot partial depth20 stream at 100ms

    Detection:
      - microprice from top-of-book sizes
      - EMA fair-value estimate
      - rolling deviation z-score
      - order-flow imbalance
      - volume burst
      - composite anomaly score

    This module is detection-only. It never sends orders.
    """

    WS_URL = (
        "wss://stream.binance.com:9443/stream?"
        "streams=btcusdt@trade/btcusdt@depth20@100ms"
    )

    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol.upper()
        self._lock = threading.RLock()
        self._started = False
        self._thread = None
        self._ws = None

        self.price = 0.0
        self.fair_value = 0.0
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.bid_qty = 0.0
        self.ask_qty = 0.0

        self.prices = deque(maxlen=2400)
        self.deviations = deque(maxlen=1200)
        self.trade_flow = deque(maxlen=300)
        self.history = deque(maxlen=600)
        self.volume_series = deque(maxlen=90)
        self.logs = deque(maxlen=30)

        self.buy_window = deque(maxlen=5000)
        self.sell_window = deque(maxlen=5000)
        self.volume_window = deque(maxlen=120)

        self.last_event_ns = time.perf_counter_ns()
        self.trade_count = 0
        self.last_book_update = 0
        self.status = "CONNECTING"
        self.reconnects = 0
        self._last_log_second = 0

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread = threading.Thread(
                target=self._run_forever,
                name="binance-market-feed",
                daemon=True,
            )
            self._thread.start()

    def _run_forever(self):
        while self._started:
            try:
                self.status = "CONNECTING"
                self._ws = websocket.WebSocketApp(
                    self.WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(
                    ping_interval=60,
                    ping_timeout=20,
                    ping_payload="v1",
                )
            except Exception as exc:
                self._log("SYSTEM", f"feed exception: {type(exc).__name__}: {exc}")
            self.reconnects += 1
            self.status = "RECONNECTING"
            time.sleep(min(10, 1 + self.reconnects * 0.5))

    def _on_open(self, ws):
        self.status = "LIVE"
        self.reconnects = 0
        self._log("SYSTEM", "Binance market stream connected")

    def _on_close(self, ws, close_status_code, close_msg):
        self.status = "DISCONNECTED"
        self._log("SYSTEM", f"WebSocket closed: {close_status_code or '-'}")

    def _on_error(self, ws, error):
        self.status = "ERROR"
        self._log("SYSTEM", f"WebSocket error: {error}")

    def _on_message(self, ws, raw):
        received_ns = time.perf_counter_ns()
        try:
            outer = json.loads(raw)
            data = outer.get("data", outer)
            event = data.get("e")
            if event == "trade":
                self._handle_trade(data, received_ns)
            elif event == "depthUpdate":
                self._handle_depth(data, received_ns)
        except Exception as exc:
            self._log("SYSTEM", f"message parse error: {exc}")

    def _handle_trade(self, d, received_ns):
        price = float(d["p"])
        qty = float(d["q"])
        # Binance "m": true means the buyer is the maker, so the aggressor was a seller.
        aggressive_sell = bool(d.get("m", False))
        now = time.time()

        with self._lock:
            self.price = price
            self.prices.append(price)
            self.trade_count += 1
            self.last_event_ns = received_ns

            if aggressive_sell:
                self.sell_window.append((now, qty))
            else:
                self.buy_window.append((now, qty))

            self._trim_flow(now)
            self._update_fair_value()
            self._update_detection(now)

    def _handle_depth(self, d, received_ns):
        bids = [(float(p), float(q)) for p, q in d.get("b", []) if float(q) > 0]
        asks = [(float(p), float(q)) for p, q in d.get("a", []) if float(q) > 0]
        if not bids or not asks:
            return

        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        with self._lock:
            self.best_bid, self.bid_qty = bids[0]
            self.best_ask, self.ask_qty = asks[0]
            self.last_book_update = int(d.get("u", 0))
            self.last_event_ns = received_ns
            self._book_bids = bids[:10]
            self._book_asks = asks[:10]

            self._update_fair_value()

    def _update_fair_value(self):
        if self.best_bid > 0 and self.best_ask > self.best_bid:
            denom = self.bid_qty + self.ask_qty
            micro = (
                (self.best_ask * self.bid_qty + self.best_bid * self.ask_qty) / denom
                if denom > 0
                else (self.best_bid + self.best_ask) / 2
            )
        elif self.price > 0:
            micro = self.price
        else:
            return

        if self.fair_value <= 0:
            self.fair_value = micro
        else:
            # Fast adaptive fair-value EMA.
            self.fair_value = 0.12 * micro + 0.88 * self.fair_value

    def _update_detection(self, now):
        if self.price <= 0 or self.fair_value <= 0:
            return

        deviation = self.price - self.fair_value
        self.deviations.append(deviation)

        if len(self.deviations) >= 50:
            arr = np.asarray(self.deviations, dtype=float)
            mean = float(np.mean(arr))
            std = float(np.std(arr))
            z = (deviation - mean) / std if std > 1e-9 else 0.0
        else:
            z = 0.0

        buy = sum(q for t, q in self.buy_window if now - t <= 10)
        sell = sum(q for t, q in self.sell_window if now - t <= 10)
        total_flow = buy + sell
        imbalance = ((buy - sell) / total_flow * 100) if total_flow else 0.0

        # Composite score is a monitoring heuristic, not a probability of profit.
        z_component = min(abs(z) / 4.0, 1.0) * 55
        flow_component = min(abs(imbalance) / 60.0, 1.0) * 25

        recent_vol = sum(q for t, q in self.buy_window if now - t <= 2) + \
                     sum(q for t, q in self.sell_window if now - t <= 2)
        baseline_vol = np.mean(list(self.volume_window)[-30:]) if self.volume_window else recent_vol
        burst = (recent_vol / baseline_vol) if baseline_vol and baseline_vol > 0 else 1.0
        burst_component = min(max(burst - 1.0, 0) / 3.0, 1.0) * 20

        score = min(100.0, z_component + flow_component + burst_component)

        direction = "NEUTRAL"
        if score >= 70:
            if z < -1.5 and imbalance > 10:
                direction = "BUY DISLOCATION"
            elif z > 1.5 and imbalance < -10:
                direction = "SELL DISLOCATION"
            else:
                direction = "ANOMALY"
        elif imbalance > 25:
            direction = "BUY FLOW"
        elif imbalance < -25:
            direction = "SELL FLOW"

        # Store once per ~100 ms to keep UI data light.
        if not self.history or now - self.history[-1]["epoch"] >= 0.10:
            self.history.append({
                "epoch": now,
                "time": datetime.fromtimestamp(now).strftime("%H:%M:%S.%f")[:-3],
                "price": self.price,
                "fair": self.fair_value,
            })

        if not self.volume_series or now - self.volume_series[-1]["epoch"] >= 1.0:
            self.volume_series.append({
                "epoch": now,
                "time": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
                "buy": buy,
                "sell": sell,
            })
            self.volume_window.append(recent_vol)

        if score >= 70 and int(now) != self._last_log_second:
            self._last_log_second = int(now)
            self._log(
                "ANOMALY",
                f"{direction} | score {score:.0f} | z {z:+.2f} | dev {deviation:+.2f}"
            )
        elif abs(imbalance) >= 30 and int(now) % 2 == 0:
            self._log("FLOW", f"order flow imbalance {imbalance:+.1f}%")

        self._zscore = z
        self._score = score
        self._imbalance = imbalance
        self._buy_pct = (buy / total_flow * 100) if total_flow else 50.0
        self._signal = direction
        self._burst = burst

    def _trim_flow(self, now):
        cutoff = now - 10
        while self.buy_window and self.buy_window[0][0] < cutoff:
            self.buy_window.popleft()
        while self.sell_window and self.sell_window[0][0] < cutoff:
            self.sell_window.popleft()

    def _log(self, level, message):
        self.logs.appendleft({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        })

    def snapshot(self):
        with self._lock:
            if not hasattr(self, "_book_bids"):
                self._book_bids = []
                self._book_asks = []
            return {
                "price": self.price,
                "fair_value": self.fair_value,
                "best_bid": self.best_bid,
                "best_ask": self.best_ask,
                "bids": list(self._book_bids),
                "asks": list(self._book_asks),
                "zscore": getattr(self, "_zscore", 0.0),
                "anomaly_score": getattr(self, "_score", 0.0),
                "imbalance": getattr(self, "_imbalance", 0.0),
                "buy_pct": getattr(self, "_buy_pct", 50.0),
                "signal": getattr(self, "_signal", "WAITING"),
                "burst": getattr(self, "_burst", 1.0),
                "status": self.status,
                "trade_count": self.trade_count,
                "last_event_ms": (time.perf_counter_ns() - self.last_event_ns) / 1_000_000,
                "history": list(self.history),
                "volume_series": list(self.volume_series),
                "logs": list(self.logs),
            }
