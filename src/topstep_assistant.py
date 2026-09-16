from __future__ import annotations

from collections import deque
from datetime import datetime
import math
from typing import Any

import numpy as np
import pandas as pd


class TopstepAssistant:
    """Precision-first signal and risk planner.

    This engine is deliberately selective: it only produces a trade alert when
    several independent conditions agree. It does not place Topstep orders.
    """

    def __init__(self, market="NQ", multiplier=20.0):
        self.market = market
        self.multiplier = float(multiplier)
        self.history = deque(maxlen=300)
        self.signal_history = deque(maxlen=100)
        self.prices = deque(maxlen=300)
        self.last_signal = "WAITING"
        self.last_update = None
        self.last_candle_ts = None
        self.bars_since_signal = 999
        self.last_direction = None
        self.cooldown_bars = 3
        self.min_score = 78

    @staticmethod
    def _ema(s: pd.Series, n: int) -> pd.Series:
        return s.ewm(span=n, adjust=False).mean()

    @staticmethod
    def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
        delta = s.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
        prev_close = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()

    @staticmethod
    def _session_vwap(df: pd.DataFrame) -> pd.Series:
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        volume = df["volume"].fillna(0.0)
        # A reset at each calendar UTC day is a reasonable approximation for the
        # public feed's session. This is an indicator, not an exchange execution price.
        day = df["timestamp"].dt.floor("D")
        pv = typical * volume
        return pv.groupby(day).cumsum() / volume.groupby(day).cumsum().replace(0, np.nan)

    @staticmethod
    def _zscore(s: pd.Series, n: int = 60) -> pd.Series:
        mean = s.rolling(n, min_periods=max(20, n // 3)).mean()
        std = s.rolling(n, min_periods=max(20, n // 3)).std(ddof=1)
        return (s - mean) / std.replace(0, np.nan)

    @staticmethod
    def _resample_close(df: pd.DataFrame, rule: str) -> pd.Series:
        x = df.set_index("timestamp")["close"].resample(rule).last().dropna()
        return x

    def analyze_candles(self, df: pd.DataFrame, current_price: float | None = None,
                        bid: float | None = None, ask: float | None = None,
                        fair: float | None = None) -> dict[str, Any]:
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if df is None or df.empty or not required.issubset(df.columns):
            return self.snapshot(current_price or 0, bid or 0, ask or 0, fair or 0, 0, 0)

        d = df.copy().dropna(subset=["close"]).sort_values("timestamp").drop_duplicates("timestamp")
        if len(d) < 60:
            return self.snapshot(float(d["close"].iloc[-1]), float(bid or d["close"].iloc[-1]),
                                 float(ask or d["close"].iloc[-1]), float(fair or d["close"].iloc[-1]), 0, 0,
                                 diagnostics={"ready": False, "reason": "Waiting for 60+ one-minute bars"})

        c = d["close"]
        d["ema9"] = self._ema(c, 9)
        d["ema21"] = self._ema(c, 21)
        d["ema50"] = self._ema(c, 50)
        d["rsi"] = self._rsi(c, 14)
        d["atr"] = self._atr(d, 14)
        d["vwap"] = self._session_vwap(d)
        d["z"] = self._zscore(c, 60)
        d["ret5"] = c.pct_change(5) * 10000
        d["ret15"] = c.pct_change(15) * 10000
        d["vol_ma20"] = d["volume"].rolling(20, min_periods=10).mean()

        x = d.iloc[-1]
        close = float(x["close"])
        fv = float(fair) if fair and fair > 0 else (float(x["vwap"]) if pd.notna(x["vwap"]) else close)
        z = float(x["z"]) if pd.notna(x["z"]) else 0.0
        atr = float(x["atr"]) if pd.notna(x["atr"]) else 0.0
        rsi = float(x["rsi"]) if pd.notna(x["rsi"]) else 50.0
        ema9, ema21, ema50 = float(x["ema9"]), float(x["ema21"]), float(x["ema50"])
        vwap = float(x["vwap"]) if pd.notna(x["vwap"]) else close
        volume = float(x["volume"]) if pd.notna(x["volume"]) else 0.0
        vol_ma = float(x["vol_ma20"]) if pd.notna(x["vol_ma20"]) else 0.0
        vol_ratio = volume / vol_ma if vol_ma > 0 else 1.0

        # Higher-timeframe confirmation from the same 1-minute source.
        c5 = self._resample_close(d, "5min")
        c15 = self._resample_close(d, "15min")
        htf5_up = len(c5) >= 30 and self._ema(c5, 9).iloc[-1] > self._ema(c5, 21).iloc[-1]
        htf5_dn = len(c5) >= 30 and self._ema(c5, 9).iloc[-1] < self._ema(c5, 21).iloc[-1]
        htf15_up = len(c15) >= 25 and self._ema(c15, 8).iloc[-1] > self._ema(c15, 21).iloc[-1]
        htf15_dn = len(c15) >= 25 and self._ema(c15, 8).iloc[-1] < self._ema(c15, 21).iloc[-1]

        # Precision-first confluence. Each component is binary and independently
        # interpretable; the score is a filter, not a probability.
        # Additional precision filters: prefer a controlled pullback/reclaim rather
        # than chasing an already-extended candle. These reduce alert frequency.
        recent = d.tail(4)
        pullback_long = bool(((recent["low"] <= (recent["ema21"] + 0.20 * recent["atr"])) & (recent["low"] >= (recent["ema21"] - 1.00 * recent["atr"]))).any())
        pullback_short = bool(((recent["high"] >= (recent["ema21"] - 0.20 * recent["atr"])) & (recent["high"] <= (recent["ema21"] + 1.00 * recent["atr"]))).any())
        body = abs(float(x["close"]) - float(x["open"]))
        rng = max(1e-9, float(x["high"]) - float(x["low"]))
        close_location = (close - float(x["low"])) / rng
        candle_long = float(x["close"]) > float(x["open"]) and close_location >= 0.65 and body / rng >= 0.45
        candle_short = float(x["close"]) < float(x["open"]) and close_location <= 0.35 and body / rng >= 0.45
        not_overextended_long = atr <= 0 or abs(close - vwap) <= 1.80 * atr
        not_overextended_short = atr <= 0 or abs(close - vwap) <= 1.80 * atr
        z_long = 0.5 <= z <= 2.20
        z_short = -2.20 <= z <= -0.5

        long_checks = {
            "trend": ema9 > ema21 > ema50,
            "htf_5m": htf5_up,
            "htf_15m": htf15_up,
            "above_vwap": close >= vwap,
            "momentum": 52 <= rsi <= 68 and float(x["ret5"]) > 0,
            "pullback_reclaim": pullback_long and close > ema9,
            "price_action": candle_long,
            "volume": vol_ratio >= 1.10,
            "not_overextended": not_overextended_long and z_long,
        }
        short_checks = {
            "trend": ema9 < ema21 < ema50,
            "htf_5m": htf5_dn,
            "htf_15m": htf15_dn,
            "below_vwap": close <= vwap,
            "momentum": 32 <= rsi <= 48 and float(x["ret5"]) < 0,
            "pullback_reclaim": pullback_short and close < ema9,
            "price_action": candle_short,
            "volume": vol_ratio >= 1.10,
            "not_overextended": not_overextended_short and z_short,
        }

        long_score = sum(long_checks.values()) / len(long_checks) * 100
        short_score = sum(short_checks.values()) / len(short_checks) * 100

        # Require two consecutive qualifying bars plus a short cooldown after a signal.
        candle_ts = d["timestamp"].iloc[-1]
        new_bar = self.last_candle_ts is None or candle_ts != self.last_candle_ts
        if new_bar:
            self.last_candle_ts = candle_ts
            self.bars_since_signal += 1

        candidate = None
        score = max(long_score, short_score)
        if long_score >= self.min_score and long_score > short_score:
            candidate = "LONG SETUP"
        elif short_score >= self.min_score and short_score > long_score:
            candidate = "SHORT SETUP"

        # Confirmation: current bar and prior completed bar must agree on direction.
        prior = d.iloc[-2]
        prior_long = float(prior["ema9"]) > float(prior["ema21"]) > float(prior["ema50"]) and float(prior["z"]) >= 0.5
        prior_short = float(prior["ema9"]) < float(prior["ema21"]) < float(prior["ema50"]) and float(prior["z"]) <= -0.5
        confirmed = (candidate == "LONG SETUP" and prior_long) or (candidate == "SHORT SETUP" and prior_short)

        signal = candidate if confirmed and self.bars_since_signal >= self.cooldown_bars else "WAIT"
        if signal != "WAIT":
            self.bars_since_signal = 0
            self.last_direction = signal

        self.last_signal = signal
        self.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.prices.extend([float(v) for v in d["close"].tail(10)])
        self.history.append({"time": self.last_update, "price": close, "fair": fv})
        self.signal_history.append({"time": self.last_update, "signal": signal, "score": score})

        diagnostics = {
            "ready": True,
            "long_score": round(long_score, 1),
            "short_score": round(short_score, 1),
            "rsi": round(rsi, 1),
            "atr": round(atr, 2),
            "vwap": round(vwap, 2),
            "zscore": round(z, 2),
            "volume_ratio": round(vol_ratio, 2),
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "ema50": round(ema50, 2),
            "long_checks": long_checks,
            "short_checks": short_checks,
            "confirmed": confirmed,
            "cooldown_bars": self.bars_since_signal,
            "signal_threshold": self.min_score,
            "long_passed": int(sum(long_checks.values())),
            "long_total": len(long_checks),
            "short_passed": int(sum(short_checks.values())),
            "short_total": len(short_checks),
        }
        deviation = close - fv
        return self.snapshot(close, float(bid or close), float(ask or close), fv, z, deviation, diagnostics)

    def update(self, price: float, bid: float, ask: float, fair: float | None = None):
        """Backward-compatible single-price update for manual mode."""
        price = float(price)
        bid = float(bid)
        ask = float(ask)
        if price <= 0:
            return self.snapshot()
        if fair is None or fair <= 0:
            fair = (bid + ask) / 2.0 if ask > bid > 0 else price
        self.prices.append(price)
        mean = sum(self.prices) / len(self.prices)
        std = (sum((p - mean) ** 2 for p in self.prices) / max(1, len(self.prices) - 1)) ** 0.5
        z = (price - mean) / std if std > 1e-9 else 0.0
        deviation = price - fair
        # Manual mode stays conservative: it cannot run the full multi-factor model.
        signal = "LONG SETUP" if z <= -2.0 and price <= fair else "SHORT SETUP" if z >= 2.0 and price >= fair else "WAIT"
        self.last_signal = signal
        self.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.history.append({"time": self.last_update, "price": price, "fair": fair})
        return self.snapshot(price, bid, ask, fair, z, deviation,
                             diagnostics={"ready": True, "manual_mode": True, "note": "Manual mode uses a stricter z-score-only fallback."})

    def snapshot(self, price=0.0, bid=0.0, ask=0.0, fair=0.0, z=0.0, deviation=0.0, diagnostics=None):
        strength = "HIGH" if abs(z) >= 2.5 else "SETUP" if abs(z) >= 1.5 else "NONE"
        diag = diagnostics or {}
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
            "score": float(max(diag.get("long_score", 0), diag.get("short_score", 0))),
            "diagnostics": diag,
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
