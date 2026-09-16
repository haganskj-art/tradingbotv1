# GRAVAI V7 — Topstep Assistant (Real-Time Market Data)

GravAI V7 keeps the final TopstepX order click under your control while adding an **authorized real-time CME futures data connector** for NQ/MNQ. It does not place Topstep orders and does not scrape or click TopstepX.

## What changed from V6

- CME Group real-time WebSocket feed option for NQ/MNQ
- Yahoo delayed feed retained only as an explicit fallback
- Live connection/status indicator
- Live quote age and message counter
- Existing precision LONG/SHORT confluence engine retained
- Existing visual/audio alerts retained
- No ProjectX API required for order execution because V7 never sends orders

## Important: real-time CME access is separate from TopstepX execution

CME offers a cloud-hosted real-time Futures & Options WebSocket API that can provide top-of-book and trade data. Access requires the appropriate CME data subscription/licensing. CME's portal provides the environment-specific WebSocket URL, authentication, and sample subscription message. V7 intentionally reads those values from Streamlit Secrets instead of guessing at CME-specific protocol details.

## Streamlit Secrets

Use the exact values supplied by CME for:

- `CME_WS_URL`
- `CME_WS_HEADERS_JSON` (JSON object; only when required)
- `CME_SUBSCRIBE_JSON` (exact JSON subscription request)
- `CME_SYMBOL`

Never commit real credentials, tokens, or private subscription values to GitHub.

## Data pipeline

```text
CME WebSocket (real-time)
        ↓
NQ / MNQ quote + trade messages
        ↓
Local 1-minute OHLCV buffer
        ↓
GravAI precision signal engine
        ↓
LONG / SHORT / WAIT
        ↓
Visual + optional sound alert
        ↓
YOU place the order in TopstepX
```

The V7 adapter also keeps the last quote, connection status, and a rolling bar buffer in memory. If CME Live is not configured, the dashboard clearly falls back to Yahoo delayed data.

## Topstep workflow

1. Open TopstepX on the same computer.
2. Run GravAI V7.
3. Select `CME Live` once your CME subscription is configured.
4. Enable automatic monitoring.
5. Confirm the dashboard says `REAL-TIME` and the quote age is current.
6. Wait for a LONG/SHORT alert.
7. Review entry, stop, target, R:R and risk.
8. Place the trade manually in TopstepX.

Do not treat an alert as a guarantee of profit or execution quality. Validate the signal engine in simulation first.
