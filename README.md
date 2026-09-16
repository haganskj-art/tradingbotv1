# GRAVAI V6 — Topstep Assistant

GravAI V6 is the no-API, no-auto-execution version for monitoring NQ/MNQ alongside TopstepX.

## V6 features

- NQ — E-mini Nasdaq-100
- MNQ — Micro E-mini Nasdaq-100
- Automatic polling market monitor
- Large visual LONG/SHORT setup alerts
- Optional browser sound/notification attempt after the user arms sound
- Alert history
- Fair-value / rolling-mean dislocation analysis
- Entry, stop, target and R:R planner
- Dollar risk calculation based on contract size
- Personal daily-loss planning check
- Manual input mode remains available
- No Topstep API credentials
- No order automation
- No browser clicking or scraping of TopstepX

## Market-data limitation

The built-in automatic feed uses Yahoo Finance's public chart endpoint for NQ=F and MNQ=F. Yahoo currently labels CME futures quotes as **Delayed Quote**, so the automatic monitor is useful as a prototype/secondary alerting tool but should **not** be treated as a real-time execution-grade feed. Replace `src/market_data.py` with an authorized real-time futures feed before relying on alerts for live trading.

Topstep states that Level 1 top-of-book market data is covered at no additional cost for Trading Combine and Express Funded Account users, while Level 2 is a paid upgrade. That platform data remains separate from this V6 app because no Topstep/ProjectX API is being used here.

## Alert behavior

V6 alerts only when the signal transitions into `LONG SETUP` or `SHORT SETUP`, not on every refresh. A return to `WAIT` arms the next setup alert.

The default setup rule is deterministic:

- `LONG SETUP`: z-score <= -1.5 and price <= fair value
- `SHORT SETUP`: z-score >= +1.5 and price >= fair value
- Otherwise: `WAIT`

These are strategy parameters, not guarantees of profitability.

## Run

```text
streamlit run app.py
```

## Topstep workflow

1. Open TopstepX on the same computer.
2. Open GravAI V6 beside it.
3. Enable automatic monitoring.
4. When a setup alert appears, review the plan.
5. Place the order manually in TopstepX.
6. Use TopstepX's own order/risk controls for execution and position management.

## Contract values

- NQ: $20 per index point per contract.
- MNQ: $2 per index point per contract.

Always verify your active contract and current Topstep rules before trading.
