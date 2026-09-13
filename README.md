# GravAI BTC Market Intelligence — V1

A detection-only real-time BTCUSDT dashboard inspired by the supplied dark trading-terminal screenshot.

## What V1 does

- Connects to Binance Spot public WebSocket market streams.
- Reads BTCUSDT trades and top-20 order-book depth.
- Updates the feed at sub-second speed (depth stream is 100ms).
- Calculates:
  - microprice
  - adaptive EMA fair value
  - price deviation
  - rolling z-score
  - buy/sell aggressive-flow imbalance
  - short-term volume burst
  - composite anomaly score
- Shows a dark neon dashboard with:
  - live price chart
  - actual vs fair value
  - anomaly score
  - order book
  - buy/sell aggression
  - live detection log
  - feed health

## Important

This is **not an execution bot**. V1 does not use API keys and cannot place trades.

The anomaly score is a heuristic monitoring score, not a probability of profit. A large deviation can be real market movement, feed noise, or a temporary dislocation.

## Install on Windows

1. Install Python 3.11+.
2. Open PowerShell in this folder.
3. Create a virtual environment:

```powershell
py -m venv .venv
```

4. Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

5. Install packages:

```powershell
python -m pip install -r requirements.txt
```

6. Start the dashboard:

```powershell
python -m streamlit run app.py
```

7. Open the local address Streamlit prints, usually `http://localhost:8501`.

## If Windows Firewall asks

Allow Python to communicate on private networks if you trust your local network. The app only consumes public Binance market data.

## Project structure

```text
btc_anomaly_dashboard_v1/
├── app.py
├── requirements.txt
├── README.md
└── src/
    └── market_engine.py
```

## Next upgrades

- Multi-exchange BTC comparison.
- Better order-book imbalance features.
- Persistent tick database.
- Replay/backtesting mode.
- Alert sound / Discord / Telegram.
- NQ adapter using a licensed real-time futures feed.
- Separate model training/evaluation pipeline.
- Paper-trading simulator.
