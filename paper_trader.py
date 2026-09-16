from __future__ import annotations

import threading
import time
from datetime import date, datetime


class PaperTrader:
    """Paper-only execution simulator. It never submits exchange orders."""

    def __init__(self, position_usd=5000.0, take_profit_usd=25.0, stop_loss_usd=10.0,
                 trailing_start_usd=15.0, trailing_distance_usd=8.0,
                 max_daily_loss_usd=50.0, cooldown_seconds=15, min_signal_score=70.0):
        self.lock = threading.RLock()
        self.position_usd = float(position_usd)
        self.take_profit_usd = float(take_profit_usd)
        self.stop_loss_usd = float(stop_loss_usd)
        self.trailing_start_usd = float(trailing_start_usd)
        self.trailing_distance_usd = float(trailing_distance_usd)
        self.max_daily_loss_usd = float(max_daily_loss_usd)
        self.cooldown_seconds = int(cooldown_seconds)
        self.min_signal_score = float(min_signal_score)
        self.enabled = False
        self.position = None
        self.realized_pnl = 0.0
        self.trades = []
        self.last_exit_time = 0.0
        self.day = date.today()
        self.daily_start_pnl = 0.0
        self.last_reason = "IDLE"

    def _roll_day(self):
        today = date.today()
        if today != self.day:
            self.day = today
            self.daily_start_pnl = self.realized_pnl
            self.last_reason = "NEW DAY"

    def daily_pnl(self):
        return self.realized_pnl - self.daily_start_pnl

    def set_enabled(self, enabled):
        with self.lock:
            self.enabled = bool(enabled)
            self.last_reason = "PAPER BOT ARMED" if enabled else "PAPER BOT DISARMED"

    def _signal(self, state):
        if float(state["anomaly_score"]) < self.min_signal_score:
            return None
        if state["signal"] == "BUY DISLOCATION":
            return "LONG"
        if state["signal"] == "SELL DISLOCATION":
            return "SHORT"
        return None

    def _pnl(self, price):
        if not self.position:
            return 0.0
        move = price - self.position["entry"]
        if self.position["side"] == "SHORT":
            move = -move
        return move * self.position["qty"]

    def _open(self, side, price, state):
        self.position = {
            "side": side,
            "entry": price,
            "qty": self.position_usd / price,
            "opened_at": time.time(),
            "entry_score": float(state["anomaly_score"]),
            "best_pnl": 0.0,
        }
        self.last_reason = f"OPEN {side}"

    def _close(self, price, reason):
        pnl = self._pnl(price)
        pos = self.position
        self.realized_pnl += pnl
        self.trades.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "side": pos["side"],
            "entry": round(pos["entry"], 2),
            "exit": round(price, 2),
            "pnl": round(pnl, 2),
            "reason": reason,
            "score": round(pos["entry_score"], 1),
        })
        self.trades = self.trades[:100]
        self.position = None
        self.last_exit_time = time.time()
        self.last_reason = f"EXIT {reason}"

    def update(self, state):
        with self.lock:
            self._roll_day()
            price = float(state["price"])
            if price <= 0:
                return

            if self.daily_pnl() <= -self.max_daily_loss_usd:
                if self.position:
                    self._close(price, "DAILY LOSS LIMIT")
                self.enabled = False
                self.last_reason = "DAILY LOSS LIMIT — DISARMED"
                return

            now = time.time()
            if self.position is None and self.enabled and now - self.last_exit_time >= self.cooldown_seconds:
                side = self._signal(state)
                if side:
                    self._open(side, price, state)
                    return

            if not self.position:
                return

            pnl = self._pnl(price)
            self.position["best_pnl"] = max(self.position["best_pnl"], pnl)

            if pnl >= self.take_profit_usd:
                self._close(price, "TAKE PROFIT")
            elif pnl <= -self.stop_loss_usd:
                self._close(price, "STOP LOSS")
            elif (self.position["best_pnl"] >= self.trailing_start_usd and
                  pnl <= self.position["best_pnl"] - self.trailing_distance_usd):
                self._close(price, "TRAILING STOP")

    def emergency_flatten(self, price):
        with self.lock:
            if self.position and price > 0:
                self._close(float(price), "MANUAL FLATTEN")
            self.enabled = False

    def snapshot(self, price=0.0):
        with self.lock:
            return {
                "enabled": self.enabled,
                "position": dict(self.position) if self.position else None,
                "unrealized_pnl": self._pnl(price),
                "realized_pnl": self.realized_pnl,
                "daily_pnl": self.daily_pnl(),
                "last_reason": self.last_reason,
                "trades": list(self.trades),
            }
