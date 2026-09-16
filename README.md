# GRAVIAI V2 — BTC Paper Trader

Upload the included files to the GitHub repo. Keep `app.py` at the repository root and `src/market_engine.py` under `src/`.

This version uses Binance public market data and adds a **paper-only** trading engine. It can simulate entries on the existing GRAVIAI BUY/SELL DISLOCATION signals and automatically simulate exits with take profit, stop loss, trailing stop, cooldown, and a maximum daily loss.

It does not connect to an exchange trading account and does not place real orders.

Streamlit Cloud main file: `app.py`


## V3 — Binance Spot Testnet execution adapter

V3 adds `src/binance_testnet.py`, an authenticated, **testnet-only** Binance Spot execution adapter.

It is intentionally separate from the V2 paper trader. The dashboard should remain in PAPER mode by default. Before enabling automatic Testnet execution, add an explicit TESTNET mode with one-entry-per-signal protection, exchange order reconciliation, symbol quantity-filter validation, and hard risk limits.

### Credentials

Put these in Streamlit Cloud Secrets, never in GitHub:

    BINANCE_TESTNET_API_KEY = "..."
    BINANCE_TESTNET_API_SECRET = "..."

The adapter uses `https://testnet.binance.vision` only.

This V3 package does not enable live-money trading and does not include the production Binance endpoint.
