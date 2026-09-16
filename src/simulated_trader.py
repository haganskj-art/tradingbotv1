from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class SimPosition:
    market: str
    side: str
    contracts: int
    entry: float
    stop: float
    target: float
    opened_at: str
    signal_score: float = 0.0
    risk_dollars: float = 0.0
    unrealized_pnl: float = 0.0
    peak_price: float = 0.0
    trough_price: float = 0.0


@dataclass
class SimTrade:
    market: str
    side: str
    contracts: int
    entry: float
    exit: float
    stop: float
    target: float
    pnl: float
    exit_reason: str
    opened_at: str
    closed_at: str
    signal_score: float = 0.0


class SimulatedTrader:
    """Deterministic simulated bracket trader.

    This class never connects to a broker or sends an exchange order. It models
    a market entry plus fixed stop-loss / take-profit and tracks P&L locally.
    """

    def __init__(self, market: str, multiplier: float, starting_balance: float = 50000.0):
        self.market = market
        self.multiplier = float(multiplier)
        self.starting_balance = float(starting_balance)
        self.realized_pnl = 0.0
        self.position: Optional[SimPosition] = None
        self.trades: list[SimTrade] = []
        self.daily_start_pnl = 0.0
        self.locked = False
        self.last_entry_key: Optional[str] = None
        self.cooldown_until_bar: Optional[str] = None
        self.max_trades = 5
        self.trades_today = 0
        self.stop_first_if_both_hit = True
        self.slippage_points = 0.0

    @property
    def equity(self) -> float:
        return self.starting_balance + self.realized_pnl + self.unrealized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return self.position.unrealized_pnl if self.position else 0.0

    @property
    def daily_pnl(self) -> float:
        return self.realized_pnl - self.daily_start_pnl + self.unrealized_pnl

    @property
    def open_position(self) -> bool:
        return self.position is not None

    def reset_day(self) -> None:
        self.daily_start_pnl = self.realized_pnl
        self.trades_today = 0
        self.locked = False
        self.cooldown_until_bar = None

    def emergency_flatten(self, price: float, reason: str = "MANUAL FLATTEN") -> Optional[SimTrade]:
        if not self.position or price <= 0:
            return None
        return self.close(price, reason)

    def can_enter(self, signal_key: str, max_daily_loss: float) -> tuple[bool, str]:
        if self.locked:
            return False, "Simulation locked after daily-loss/trade limit."
        if self.position is not None:
            return False, "Position already open."
        if self.trades_today >= self.max_trades:
            return False, "Maximum simulated trades reached."
        if self.daily_pnl <= -abs(max_daily_loss):
            self.locked = True
            return False, "Daily loss limit reached."
        if self.last_entry_key == signal_key:
            return False, "Signal already simulated."
        if self.cooldown_until_bar and signal_key == self.cooldown_until_bar:
            return False, "Cooldown active."
        return True, "READY"

    def open(self, side: str, contracts: int, entry: float, stop: float, target: float,
             opened_at: str, signal_key: str, signal_score: float = 0.0,
             max_daily_loss: float = 300.0) -> tuple[bool, str]:
        side = side.upper()
        if side not in {"LONG", "SHORT"}:
            return False, "Invalid side."
        ok, reason = self.can_enter(signal_key, max_daily_loss)
        if not ok:
            return False, reason
        if contracts < 1 or entry <= 0 or stop <= 0 or target <= 0:
            return False, "Invalid trade plan."
        if side == "LONG" and not (stop < entry < target):
            return False, "LONG plan must have stop < entry < target."
        if side == "SHORT" and not (target < entry < stop):
            return False, "SHORT plan must have target < entry < stop."

        self.position = SimPosition(
            market=self.market,
            side=side,
            contracts=int(contracts),
            entry=float(entry),
            stop=float(stop),
            target=float(target),
            opened_at=opened_at,
            signal_score=float(signal_score),
            risk_dollars=abs(entry - stop) * self.multiplier * contracts,
            peak_price=float(entry),
            trough_price=float(entry),
        )
        self.trades_today += 1
        self.last_entry_key = signal_key
        return True, "SIMULATED ENTRY FILLED"

    def update(self, price: float, high: float | None = None, low: float | None = None,
               bar_key: str | None = None, max_daily_loss: float = 300.0) -> Optional[SimTrade]:
        if not self.position or price <= 0:
            return None
        p = self.position
        price = float(price)
        high = float(high if high is not None else price)
        low = float(low if low is not None else price)
        p.peak_price = max(p.peak_price, high)
        p.trough_price = min(p.trough_price, low)

        if p.side == "LONG":
            p.unrealized_pnl = (price - p.entry) * p.contracts * self.multiplier
            stop_hit = low <= p.stop
            target_hit = high >= p.target
            if stop_hit and target_hit:
                # Conservative assumption: stop first when OHLC cannot establish order.
                if self.stop_first_if_both_hit:
                    return self.close(p.stop - self.slippage_points, "STOP LOSS (BOTH HIT)")
                return self.close(p.target - self.slippage_points, "TAKE PROFIT (BOTH HIT)")
            if stop_hit:
                return self.close(p.stop - self.slippage_points, "STOP LOSS")
            if target_hit:
                return self.close(p.target - self.slippage_points, "TAKE PROFIT")
        else:
            p.unrealized_pnl = (p.entry - price) * p.contracts * self.multiplier
            stop_hit = high >= p.stop
            target_hit = low <= p.target
            if stop_hit and target_hit:
                if self.stop_first_if_both_hit:
                    return self.close(p.stop + self.slippage_points, "STOP LOSS (BOTH HIT)")
                return self.close(p.target + self.slippage_points, "TAKE PROFIT (BOTH HIT)")
            if stop_hit:
                return self.close(p.stop + self.slippage_points, "STOP LOSS")
            if target_hit:
                return self.close(p.target + self.slippage_points, "TAKE PROFIT")

        if self.daily_pnl <= -abs(max_daily_loss):
            self.locked = True
        return None

    def close(self, exit_price: float, reason: str) -> SimTrade:
        p = self.position
        if p is None:
            raise RuntimeError("No simulated position to close.")
        exit_price = float(exit_price)
        if p.side == "LONG":
            pnl = (exit_price - p.entry) * p.contracts * self.multiplier
        else:
            pnl = (p.entry - exit_price) * p.contracts * self.multiplier
        self.realized_pnl += pnl
        trade = SimTrade(
            market=self.market,
            side=p.side,
            contracts=p.contracts,
            entry=p.entry,
            exit=exit_price,
            stop=p.stop,
            target=p.target,
            pnl=pnl,
            exit_reason=reason,
            opened_at=p.opened_at,
            closed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            signal_score=p.signal_score,
        )
        self.trades.insert(0, trade)
        self.trades = self.trades[:100]
        self.position = None
        self.cooldown_until_bar = datetime.now().strftime("%Y-%m-%d %H:%M")
        return trade

    def flatten_at_price(self, price: float) -> Optional[SimTrade]:
        return self.emergency_flatten(price, "MANUAL FLATTEN")

    def snapshot(self) -> dict:
        return {
            "market": self.market,
            "starting_balance": self.starting_balance,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "daily_pnl": self.daily_pnl,
            "equity": self.equity,
            "locked": self.locked,
            "trades_today": self.trades_today,
            "position": asdict(self.position) if self.position else None,
            "trades": [asdict(t) for t in self.trades],
        }
