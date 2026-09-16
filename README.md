# GRAVAI V5 — Topstep Assistant

GravAI V5 is the no-API, no-auto-execution version for trading NQ/MNQ alongside a TopstepX account.

## What it does

- NQ — E-mini Nasdaq-100
- MNQ — Micro E-mini Nasdaq-100
- Manual current price / bid / ask input
- Fair-value and price-dislocation analysis
- LONG SETUP / SHORT SETUP / WAIT signal display
- Entry, stop, target and R:R planner
- Dollar risk calculation based on contract size
- Personal daily-loss planning check
- Trade-plan dashboard and journal-ready layout

## What it does NOT do

- It does not connect to TopstepX.
- It does not require ProjectX API access.
- It does not submit, modify, or cancel Topstep orders.
- It does not scrape or click TopstepX.
- It does not guarantee profitable trades.

You place the order manually in TopstepX after reviewing GravAI.

## Contract values

- NQ: $20 per index point per contract.
- MNQ: $2 per index point per contract.

Always verify the active contract and current Topstep rules before trading.

## Run

The app is designed for Streamlit. No Topstep or broker credentials are required for V5.

```text
streamlit run app.py
```

If deploying to Streamlit Cloud, no secrets are required for the Topstep Assistant mode.

## Important limitation

Without an official market-data API connection, V5 uses manual market input. It is intended to sit beside TopstepX while you trade. Do not assume the values are live unless you entered them from your live platform.
