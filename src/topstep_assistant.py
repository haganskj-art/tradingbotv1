from __future__ import annotations

from collections import deque
from datetime import datetime
import math


class TopstepAssistant:
    """Signal and risk-planning engine. It never sends Topstep orders."""

    def __init__(self, market="NQ", multiplier=20.0):
        self.market = market
        self.multiplier = float(multiplier)
        self.history = deque(maxlen=300)
        self.prices = deque(maxlen=120)
        self.last_signal = "WAITING"
        self.last_update = None

    def update(self, price: float, bid: float, ask: float, fair: float | None = None):
        price = float(price)
        bid = float(bid)
        ask = float(ask)
        if price <= 0:
            return self.snapshot()
        if fair is None or fair <= 0:
            if bid > 0 and ask > bid:
                fair = (bid + ask) / 2.0
            else:
                fair = price
        self.prices.append(price)
        mean = sum(self.prices) / len(self.prices)
        if len(self.prices) > 1:
            var = sum((p - mean) ** 2 for p in self.prices) / max(1, len(self.prices) - 1)
            std = math.sqrt(var)
        else:
            std = 0.0
        z = (price - mean) / std if std > 1e-9 else 0.0
        deviation = price - fair
        if z <= -1.5 and price <= fair:
            signal = "LONG SETUP"
        elif z >= 1.5 and price >= fair:
            signal = "SHORT SETUP"
        else:
            signal = "WAIT"
        self.last_signal = signal
        self.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.history.append({"time": self.last_update, "price": price, "fair": fair})
        return self.snapshot(price, bid, ask, fair, z, deviation)

    def snapshot(self, price=0.0, bid=0.0, ask=0.0, fair=0.0, z=0.0, deviation=0.0):
        if abs(z) >= 2.5:
            strength = "HIGH"
        elif abs(z) >= 1.5:
            strength = "SETUP"
        else:
            strength = "NONE"
        return {
            "market": self.market,
            "price": float(price),
            "bid": float(bid),
            "ask": float(ask),
            "fair": float(fair),
            "zscore": float(z),
            "deviation": float(deviation),
            "signal": self.last_signal,
            "strength": strength,
            "history": list(self.history),
            "updated": self.last_update,
        }

    def dollar_value_per_point(self, contracts: int) -> float:
        return float(contracts) * self.multiplier

    def risk_for_stop(self, entry: float, stop: float, contracts: int) -> float:
        return abs(float(entry) - float(stop)) * self.dollar_value_per_point(contracts)

    def target_price(self, entry: float, points: float, side: str) -> float:
        return float(entry) + (float(points) if side.upper() == "LONG" else -float(points))

    def stop_price(self, entry: float, points: float, side: str) -> float:
        return float(entry) - (float(points) if side.upper() == "LONG" else -float(points))
