# GRAVAI V8 — Topstep Assistant (Auto Signals + Simulated Execution)

GravAI V8 builds on V7 with **local simulated execution**. It automatically opens a simulated bracket trade when a qualifying LONG/SHORT signal appears, then manages the simulated stop-loss and take-profit without sending any broker or TopstepX orders.

## V8 features

- NQ and MNQ
- Authorized CME WebSocket feed option from V7
- Yahoo delayed fallback clearly labeled
- Precision, multi-factor LONG/SHORT confluence engine
- Automatic monitoring
- Visual and optional audible alerts
- Automatic **simulation-only** entries
- Automatic simulated stop-loss and take-profit
- ATR-based stop sizing and configurable R:R target
- Maximum simulated trades/day
- Simulated daily-loss lock
- Simulated slippage option
- Unrealized and realized P&L
- Simulated position dashboard and trade history
- Emergency simulated flatten
- Reset simulation button
- No ProjectX API
- No TopstepX credentials
- No broker order submission
- No browser automation or screen scraping

## Simulation pipeline

```text
CME real-time feed (when configured)
            ↓
     Precision signal engine
            ↓
        LONG / SHORT
            ↓
     Simulation risk checks
            ↓
    Local simulated market entry
            ↓
       ┌──────────────┐
       │ Stop Loss    │
       │ Take Profit  │
       └──────────────┘
            ↓
      Simulated P&L log
```

### Automatic bracket settings

When Auto-simulate is enabled:

- Entry = current modeled market price
- Stop distance = `ATR × Auto stop = ATR ×`
- Target distance = `stop distance × Auto target R:R`
- NQ dollar value = $20 per index point per contract
- MNQ dollar value = $2 per index point per contract

When a single OHLC bar shows both the stop and target being touched, the simulator uses **stop-first** by default because OHLC data alone cannot prove which level traded first. This is a conservative simulation assumption.

## Safety

V8 is **simulation-only**. It does not log into TopstepX, click buttons, submit orders, modify orders, cancel orders, or access a Topstep account. Do not treat the signal score as a probability or a profit guarantee.

For live-use research, validate the strategy with recorded market data / paper results first and verify current Topstep rules and risk limits before trading.

## CME connection

V7's CME WebSocket connector is retained. Configure the exact environment-specific URL, authentication headers, and subscription message supplied by CME through Streamlit Secrets. Never put private credentials or tokens in GitHub.
