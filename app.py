from __future__ import annotations

import html
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from src.market_data import LiveMarketData
from src.topstep_assistant import TopstepAssistant
from src.simulated_trader import SimulatedTrader

st.set_page_config(page_title="GravAI V8 — Topstep Assistant", page_icon="⚡", layout="wide")
st.markdown("""<style>
body{background:#08090d}.block-container{padding-top:1rem}.card,.signal{background:#101118;border:1px solid #242532;border-radius:12px;padding:16px;margin-bottom:14px}.small,.muted{color:#858897}.metric{font-size:2rem;font-weight:700}.green{color:#55d98a}.red{color:#ff6878}.yellow{color:#ffd45a}.mono{font-family:monospace}.alertbox{border:2px solid #ffcf33;background:#261f08;border-radius:14px;padding:18px;margin-bottom:16px}.status{padding:7px 10px;border-radius:10px;display:inline-block;background:#1b1d26}.danger{background:#35131a}.ok{background:#11251a}
</style>""", unsafe_allow_html=True)

st.title("⚡ GRAVAI V8 — TOPSTEP ASSISTANT")
st.caption("Automatic NQ/MNQ monitoring + alerts | You remain in control of the final TopstepX order click")

market = st.sidebar.selectbox("MARKET", ["NQ", "MNQ"])
multiplier = 20.0 if market == "NQ" else 2.0
label = "E-mini Nasdaq-100" if market == "NQ" else "Micro E-mini Nasdaq-100"

if "assistants" not in st.session_state:
    st.session_state.assistants = {}
if market not in st.session_state.assistants:
    st.session_state.assistants[market] = TopstepAssistant(market, multiplier)
assistant = st.session_state.assistants[market]

if "sims" not in st.session_state:
    st.session_state.sims = {}
if market not in st.session_state.sims:
    st.session_state.sims[market] = SimulatedTrader(market, multiplier)
sim = st.session_state.sims[market]

if "feed" not in st.session_state:
    st.session_state.feed = LiveMarketData(st.secrets)
    st.session_state.feed.start()
if "last_alert_signal" not in st.session_state:
    st.session_state.last_alert_signal = {"NQ": "", "MNQ": ""}
if "alert_count" not in st.session_state:
    st.session_state.alert_count = 0
if "alert_log" not in st.session_state:
    st.session_state.alert_log = []
if "last_sim_signal_key" not in st.session_state:
    st.session_state.last_sim_signal_key = {"NQ": "", "MNQ": ""}
if "last_fetch_error" not in st.session_state:
    st.session_state.last_fetch_error = ""

st.sidebar.markdown(f"**{label}**")
st.sidebar.caption(f"$ {multiplier:.0f} per index point per contract")

st.sidebar.subheader("DATA SOURCE")
provider = st.sidebar.selectbox("Market data", ["CME Live", "Yahoo Delayed"], index=0 if st.session_state.feed.cme_configured else 1)
if provider == "CME Live":
    if st.session_state.feed.cme_configured:
        st.sidebar.success("CME WebSocket configured")
    else:
        st.sidebar.warning("CME WebSocket not configured — using Yahoo fallback")

st.sidebar.subheader("AUTO MONITOR")
auto = st.sidebar.toggle("Enable automatic monitoring", value=False)
interval = st.sidebar.slider("Refresh interval (seconds)", min_value=5, max_value=60, value=10, step=5)
sound_enabled = st.sidebar.checkbox("Arm browser sound", value=False)

st.sidebar.subheader("SIMULATION MODE")
auto_sim = st.sidebar.toggle("Auto-simulate qualifying signals", value=False)
sim_balance = st.sidebar.number_input("Simulation starting balance ($)", min_value=1000.0, value=50000.0, step=1000.0)
sim_contracts = st.sidebar.number_input("Auto-sim contracts", min_value=1, value=1, step=1)
sim_stop_atr = st.sidebar.number_input("Auto stop = ATR ×", min_value=0.25, value=1.0, step=0.25)
sim_rr = st.sidebar.number_input("Auto target R:R", min_value=0.5, value=2.0, step=0.25)
sim_daily_limit = st.sidebar.number_input("Simulation daily loss limit ($)", min_value=25.0, value=300.0, step=25.0)
sim_max_trades = st.sidebar.number_input("Simulation max trades/day", min_value=1, value=5, step=1)
sim.slippage_points = st.sidebar.number_input("Simulated slippage (points)", min_value=0.0, value=0.0, step=0.25)
sim.starting_balance = float(sim_balance)
sim.max_trades = int(sim_max_trades)
st.sidebar.caption("Simulation only: no broker/API orders are sent.")
st.sidebar.caption("Stops/targets are exchange-independent planning levels for the simulator.")
if st.sidebar.button("Reset this market simulation", use_container_width=True):
    st.session_state.sims[market] = SimulatedTrader(market, multiplier, starting_balance=float(sim_balance))
    st.session_state.last_sim_signal_key[market] = ""
    st.rerun()

st.sidebar.caption("CME Live uses an authorized CME WebSocket subscription. Yahoo is retained only as a delayed fallback.")

if auto:
    st_autorefresh(interval=interval * 1000, key="grav_ai_v6_refresh")

manual_mode = st.sidebar.toggle("Manual input mode", value=False)

if manual_mode:
    st.sidebar.subheader("MANUAL MARKET INPUT")
    mprice = st.sidebar.number_input("Current / last price", min_value=0.0, value=0.0, step=0.25, format="%.2f")
    mbid = st.sidebar.number_input("Bid", min_value=0.0, value=0.0, step=0.25, format="%.2f")
    mask = st.sidebar.number_input("Ask", min_value=0.0, value=0.0, step=0.25, format="%.2f")
    mfair = st.sidebar.number_input("Fair value (optional)", min_value=0.0, value=0.0, step=0.25, format="%.2f")
    if st.sidebar.button("UPDATE MANUAL ANALYSIS", use_container_width=True):
        st.session_state.last_state = assistant.update(mprice, mbid, mask, mfair if mfair > 0 else None)
        st.session_state.feed_status = "MANUAL"
else:
    if auto:
        try:
            quote = st.session_state.feed.fetch(market, provider=provider)
            st.session_state.last_state = assistant.analyze_candles(quote.candles, quote.price, quote.bid, quote.ask, None)
            st.session_state.last_quote = quote
            st.session_state.last_fetch_error = ""
        except Exception as exc:
            st.session_state.last_fetch_error = str(exc)
    elif "last_quote" not in st.session_state:
        # Fetch once so the dashboard is not blank even before the user enables auto mode.
        try:
            quote = st.session_state.feed.fetch(market, provider=provider)
            st.session_state.last_state = assistant.analyze_candles(quote.candles, quote.price, quote.bid, quote.ask, None)
            st.session_state.last_quote = quote
            st.session_state.last_fetch_error = ""
        except Exception as exc:
            st.session_state.last_fetch_error = str(exc)

state = st.session_state.get("last_state", assistant.snapshot())
quote = st.session_state.get("last_quote")

# Update the simulated position on every refresh using the latest bar/quote.
if quote is not None and state.get("price", 0) > 0:
    sim_high = sim_low = float(state.get("price", 0))
    candles = quote.candles if quote is not None else None
    if candles is not None and not candles.empty:
        last_bar = candles.iloc[-1]
        sim_high = float(last_bar.get("high", state.get("price", 0)))
        sim_low = float(last_bar.get("low", state.get("price", 0)))
    closed = sim.update(float(state.get("price", 0)), sim_high, sim_low,
                        max_daily_loss=float(sim_daily_limit))
    if closed is not None:
        st.session_state.alert_log.insert(0, {
            "time": closed.closed_at, "market": market, "signal": closed.exit_reason,
            "price": closed.exit, "pnl": closed.pnl,
        })
        st.session_state.alert_log = st.session_state.alert_log[:20]

# Auto-enter once per unique confirmed signal. This is a local simulation only.
sig = state.get("signal", "WAITING")
diag = state.get("diagnostics", {}) or {}
atr = float(diag.get("atr", 0) or 0)
price_now = float(state.get("price", 0) or 0)
bar_key = str(candles.iloc[-1]["timestamp"]) if quote is not None and candles is not None and not candles.empty else str(state.get("updated", ""))
if auto_sim and sig in ("LONG SETUP", "SHORT SETUP") and price_now > 0 and atr > 0:
    stop_points_auto = max(0.25, atr * float(sim_stop_atr))
    target_points_auto = stop_points_auto * float(sim_rr)
    auto_side = "LONG" if sig.startswith("LONG") else "SHORT"
    entry = price_now
    stop = assistant.stop_price(entry, stop_points_auto, auto_side)
    target = assistant.target_price(entry, target_points_auto, auto_side)
    signal_key = f"{market}|{sig}|{bar_key}"
    # Only auto-enter once when a fresh setup bar appears; do not re-enter on every refresh.
    # A new setup direction/bar can create a new key after a position is closed.
    if st.session_state.last_sim_signal_key.get(market) != signal_key:
        opened, reason = sim.open(auto_side, int(sim_contracts), entry, stop, target,
                                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                  signal_key, float(state.get("score", 0)),
                                  float(sim_daily_limit))
        st.session_state.last_sim_signal_key[market] = signal_key
        if opened:
            st.session_state.alert_log.insert(0, {
                "time": datetime.now().strftime("%H:%M:%S"), "market": market,
                "signal": f"SIM ENTRY {auto_side}", "price": entry,
                "score": float(state.get("score", 0)), "stop": stop, "target": target,
            })
            st.session_state.alert_log = st.session_state.alert_log[:20]

# Alert only on a new setup direction, not every page refresh.
sig = state.get("signal", "WAITING")
previous = st.session_state.last_alert_signal.get(market, "")
if sig in ("LONG SETUP", "SHORT SETUP") and sig != previous:
    st.session_state.alert_count += 1
    st.session_state.alert_log.insert(0, {
        "time": datetime.now().strftime("%H:%M:%S"),
        "market": market,
        "signal": sig,
        "price": state.get("price", 0.0),
        "zscore": state.get("zscore", 0.0),
    })
    st.session_state.alert_log = st.session_state.alert_log[:20]
    st.session_state.last_alert_signal[market] = sig
elif sig == "WAIT":
    st.session_state.last_alert_signal[market] = ""

if sig in ("LONG SETUP", "SHORT SETUP"):
    color_class = "green" if "LONG" in sig else "red"
    st.markdown(f'<div class="alertbox"><div class="small">🚨 GRAVAI TRADE ALERT</div><div class="metric {color_class}">{html.escape(sig)}</div><div>Z-score {state.get("zscore",0):+.2f} • Signal strength: {state.get("strength","NONE")}</div><div style="margin-top:8px">Review the plan below, then place the order manually in TopstepX.</div></div>', unsafe_allow_html=True)

# Tiny browser sound/notification component. Browser policies may require one click to enable audio.
trigger_id = f"{market}-{st.session_state.alert_count}-{sig}"
components.html(f"""
<div style='font-family:Arial;color:#ddd;font-size:12px'>
<button id='enable' style='padding:6px 10px;border-radius:8px;border:1px solid #555;background:#171922;color:#ddd;cursor:pointer'>🔊 Enable sound</button>
<span id='status' style='margin-left:8px;color:#888'>{'armed' if sound_enabled else 'click to arm'}</span>
</div>
<script>
const key='gravAI_sound_armed';
const trig='{trigger_id}';
let armed = localStorage.getItem(key)==='1';
const status=document.getElementById('status');
const btn=document.getElementById('enable');
function beep() {{
  try {{
    const Ctx=window.AudioContext||window.webkitAudioContext;
    const ctx=new Ctx();
    const osc=ctx.createOscillator(); const gain=ctx.createGain();
    osc.frequency.value=880; gain.gain.value=0.08;
    osc.connect(gain); gain.connect(ctx.destination); osc.start();
    setTimeout(()=>{{osc.stop();ctx.close();}},180);
  }} catch(e) {{}}
}}
btn.onclick=()=>{{
  armed=true; localStorage.setItem(key,'1'); status.textContent='armed'; beep();
}};
if(armed) {{ status.textContent='armed'; }}
const prev=localStorage.getItem('gravAI_last_trigger');
if(armed && trig!==prev && ('{sig}'==='LONG SETUP' || '{sig}'==='SHORT SETUP')) {{
  localStorage.setItem('gravAI_last_trigger',trig); beep();
  try {{ if ('Notification' in window && Notification.permission==='granted') new Notification('GravAI '+ '{market}', {{body:'{sig} — review the trade plan'}}); }} catch(e) {{}}
}}
</script>
""", height=48)

c1, c2, c3 = st.columns([1, 2, 1])
with c1:
    st.markdown('<div class="signal"><div class="small">GRAVAI SETUP</div>', unsafe_allow_html=True)
    cls = "green" if "LONG" in sig else ("red" if "SHORT" in sig else "")
    diag = state.get("diagnostics", {}) or {}
    quality = state.get("score", 0.0)
    st.markdown(f'<div class="metric {cls}">{html.escape(sig)}</div><div class="mono">QUALITY {quality:.0f}% • Z-SCORE {state.get("zscore",0):+.2f}</div><div class="muted">Strength: {state.get("strength","NONE")} • Multi-factor confirmation required</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="card"><div class="small">PRICE / FAIR VALUE</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric">{state.get("price",0):,.2f}</div>', unsafe_allow_html=True)
    hist = pd.DataFrame(state.get("history", []))
    fig = go.Figure()
    if not hist.empty:
        fig.add_trace(go.Scatter(x=hist["time"], y=hist["price"], mode="lines", name="Price"))
        fig.add_trace(go.Scatter(x=hist["time"], y=hist["fair"], mode="lines", name="Fair"))
    fig.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showticklabels=False), yaxis=dict(gridcolor="#22242e"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="card"><div class="small">MARKET DATA</div>', unsafe_allow_html=True)
    st.write(f"**Price:** {state.get('price',0):,.2f}")
    st.write(f"**Bid:** {state.get('bid',0):,.2f}")
    st.write(f"**Ask:** {state.get('ask',0):,.2f}")
    st.write(f"**Fair:** {state.get('fair',0):,.2f}")
    st.write(f"**Deviation:** {state.get('deviation',0):+.2f}")
    if quote is not None:
        age = quote.age_seconds
        age_text = f"{age:.0f}s ago" if age is not None else "unknown age"
        st.write(f"**Feed:** {quote.source} ({"DELAYED" if quote.delayed else "REAL-TIME"})")
        if not quote.delayed:
            st.write(f"**Connection:** {"CONNECTED" if quote.connected else "WAITING"}")
            st.write(f"**Messages:** {quote.message_count}")
        st.write(f"**Quote time:** {age_text}")
    else:
        st.write("**Feed:** Manual")
    if st.session_state.last_fetch_error:
        st.error("Automatic data fetch failed. Check the connection or use manual mode.")
    if quote is not None and quote.last_error:
        st.warning(quote.last_error)
    st.markdown('</div>', unsafe_allow_html=True)

with st.expander("Signal diagnostics — why GravAI is waiting or alerting", expanded=False):
    diag = state.get("diagnostics", {}) or {}
    if diag:
        a,b,c,d = st.columns(4)
        a.metric("LONG SCORE", f"{diag.get("long_score", 0):.0f}%")
        b.metric("SHORT SCORE", f"{diag.get("short_score", 0):.0f}%")
        c.metric("RSI", f"{diag.get("rsi", 0):.1f}")
        d.metric("VOL RATIO", f"{diag.get("volume_ratio", 0):.2f}x")
        st.write({
            "EMA9": diag.get("ema9"), "EMA21": diag.get("ema21"), "EMA50": diag.get("ema50"),
            "VWAP": diag.get("vwap"), "ATR": diag.get("atr"), "Z-score": diag.get("zscore")
        })
        if diag.get("long_checks") or diag.get("short_checks"):
            left, right = st.columns(2)
            with left:
                st.markdown("**LONG confluence**")
                for k,v in diag.get("long_checks", {}).items():
                    st.write(("✅ " if v else "⬜ ") + k.replace("_", " ").title())
            with right:
                st.markdown("**SHORT confluence**")
                for k,v in diag.get("short_checks", {}).items():
                    st.write(("✅ " if v else "⬜ ") + k.replace("_", " ").title())
        st.caption("The quality score is a rule-based confluence score, not a probability of profit. V6 requires multi-timeframe alignment, momentum, pullback/reclaim, candle quality and volume; alerts are intentionally less frequent.")
    else:
        st.info("Waiting for enough market bars to calculate the precision model.")

st.subheader("Simulated Execution")
sp = sim.snapshot()
if sp["position"]:
    pos = sp["position"]
    st.markdown(f'<div class="alertbox"><div class="small">SIMULATED POSITION</div><div class="metric {"green" if pos["side"]=="LONG" else "red"}">{pos["side"]} {pos["contracts"]} {market}</div><div>Entry {pos["entry"]:,.2f} • Stop {pos["stop"]:,.2f} • Target {pos["target"]:,.2f}</div><div>Risk ${pos["risk_dollars"]:,.2f} • Unrealized P&L ${sp["unrealized_pnl"]:,.2f}</div></div>', unsafe_allow_html=True)
    if st.button("EMERGENCY FLATTEN SIMULATION", type="secondary", use_container_width=True):
        sim.flatten_at_price(price_now)
        st.rerun()
else:
    st.info("No simulated position. Enable Auto-simulate to let qualifying GravAI signals open a local simulated bracket trade.")

sa,sb,sc,sd = st.columns(4)
sa.metric("SIM EQUITY", f'${sp["equity"]:,.2f}')
sb.metric("REALIZED P&L", f'${sp["realized_pnl"]:,.2f}')
sc.metric("DAILY P&L", f'${sp["daily_pnl"]:,.2f}')
sd.metric("TRADES TODAY", f'{sp["trades_today"]} / {sim.max_trades}')
if sp["locked"]:
    st.error("SIMULATION LOCKED — daily loss or trade limit reached.")

with st.expander("Simulated trade history"):
    if sp["trades"]:
        st.dataframe(pd.DataFrame(sp["trades"]), use_container_width=True, hide_index=True)
    else:
        st.caption("No simulated trades yet.")

st.subheader("Trade Plan")
col1, col2 = st.columns([1, 2])
with col1:
    contracts = st.number_input("Contracts", min_value=1, value=1, step=1)
    side = st.selectbox("Side", ["LONG", "SHORT"], index=0 if "LONG" in sig else 1 if "SHORT" in sig else 0)
    entry = st.number_input("Planned entry", min_value=0.0, value=float(state.get("price", 0.0)), step=0.25, format="%.2f")
    stop_points = st.number_input("Stop distance (points)", min_value=0.25, value=10.0, step=0.25)
    target_points = st.number_input("Target distance (points)", min_value=0.25, value=20.0, step=0.25)
    daily_limit = st.number_input("Personal daily loss limit ($)", min_value=1.0, value=300.0, step=25.0)

stop = assistant.stop_price(entry, stop_points, side) if entry > 0 else 0.0
target = assistant.target_price(entry, target_points, side) if entry > 0 else 0.0
risk = assistant.risk_for_stop(entry, stop, contracts) if entry > 0 else 0.0
rr = target_points / stop_points if stop_points > 0 else 0.0

with col2:
    a,b,c,d,e = st.columns(5)
    a.metric("CONTRACTS", contracts)
    b.metric("RISK", f"${risk:,.2f}")
    c.metric("STOP", f"{stop:,.2f}" if stop else "—")
    d.metric("TARGET", f"{target:,.2f}" if target else "—")
    e.metric("R:R", f"1:{rr:.2f}")
    if risk > daily_limit:
        st.error(f"Planned trade risk ${risk:,.2f} exceeds your personal daily limit ${daily_limit:,.2f}.")
    else:
        st.info("Risk check: planned single-trade stop risk is within your personal daily limit. This is a planning aid, not a guarantee of execution or profit.")

with st.expander("Alert history"):
    if st.session_state.alert_log:
        st.dataframe(pd.DataFrame(st.session_state.alert_log), use_container_width=True, hide_index=True)
    else:
        st.caption("No new setup alerts yet.")

st.subheader("How V8 works")
st.markdown("""
1. Turn on **Enable automatic monitoring**.
2. GravAI polls the configured market feed on the selected interval.
3. The precision model checks trend alignment, 5-minute and 15-minute confirmation, VWAP, RSI/momentum, pullback/reclaim behavior, candle quality, volume, and overextension.
4. A setup must also confirm on the prior completed bar and pass a cooldown.
5. When the signal changes into **LONG SETUP** or **SHORT SETUP**, V8 shows a visual/audio alert.
6. Turn on **Auto-simulate qualifying signals** to open a local simulated bracket trade automatically.
7. Every simulated trade gets a stop-loss and take-profit and is monitored on subsequent market updates.
8. Review simulated results before considering any live execution path.
""")

st.warning("Simulation safety: V8 never sends broker or TopstepX orders. Auto-simulation is local only. If CME Live is not configured, Yahoo data is delayed and should not be treated as execution-grade data.")

with st.expander("Safety"):
    st.write("V6 never logs into, scrapes, clicks, submits, modifies, or cancels TopstepX orders. It is an analysis/alerting tool. NQ uses $20 per index point per contract; MNQ uses $2 per point per contract. Verify your current Topstep rules, contract, and risk limits before trading.")

st.caption(f"GravAI V8 • {market} • Automatic monitoring: {'ON' if auto else 'OFF'} • Auto-simulation: {'ON' if auto_sim else 'OFF'} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
