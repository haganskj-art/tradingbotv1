from __future__ import annotations

import html
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from src.market_data import YahooDelayedFeed
from src.topstep_assistant import TopstepAssistant

st.set_page_config(page_title="GravAI V6 — Topstep Assistant", page_icon="⚡", layout="wide")
st.markdown("""<style>
body{background:#08090d}.block-container{padding-top:1rem}.card,.signal{background:#101118;border:1px solid #242532;border-radius:12px;padding:16px;margin-bottom:14px}.small,.muted{color:#858897}.metric{font-size:2rem;font-weight:700}.green{color:#55d98a}.red{color:#ff6878}.yellow{color:#ffd45a}.mono{font-family:monospace}.alertbox{border:2px solid #ffcf33;background:#261f08;border-radius:14px;padding:18px;margin-bottom:16px}.status{padding:7px 10px;border-radius:10px;display:inline-block;background:#1b1d26}.danger{background:#35131a}.ok{background:#11251a}
</style>""", unsafe_allow_html=True)

st.title("⚡ GRAVAI V6 — TOPSTEP ASSISTANT")
st.caption("Automatic NQ/MNQ monitoring + alerts | You remain in control of the final TopstepX order click")

market = st.sidebar.selectbox("MARKET", ["NQ", "MNQ"])
multiplier = 20.0 if market == "NQ" else 2.0
label = "E-mini Nasdaq-100" if market == "NQ" else "Micro E-mini Nasdaq-100"

if "assistants" not in st.session_state:
    st.session_state.assistants = {}
if market not in st.session_state.assistants:
    st.session_state.assistants[market] = TopstepAssistant(market, multiplier)
assistant = st.session_state.assistants[market]

if "feed" not in st.session_state:
    st.session_state.feed = YahooDelayedFeed()
if "last_alert_signal" not in st.session_state:
    st.session_state.last_alert_signal = {"NQ": "", "MNQ": ""}
if "alert_count" not in st.session_state:
    st.session_state.alert_count = 0
if "alert_log" not in st.session_state:
    st.session_state.alert_log = []
if "last_fetch_error" not in st.session_state:
    st.session_state.last_fetch_error = ""

st.sidebar.markdown(f"**{label}**")
st.sidebar.caption(f"$ {multiplier:.0f} per index point per contract")

st.sidebar.subheader("AUTO MONITOR")
auto = st.sidebar.toggle("Enable automatic monitoring", value=False)
interval = st.sidebar.slider("Refresh interval (seconds)", min_value=5, max_value=60, value=10, step=5)
sound_enabled = st.sidebar.checkbox("Arm browser sound", value=False)
st.sidebar.caption("Automatic feed: Yahoo Finance CME futures quote, which Yahoo labels delayed.")

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
            quote = st.session_state.feed.fetch(market)
            st.session_state.last_state = assistant.update(quote.price, quote.bid, quote.ask, None)
            st.session_state.last_quote = quote
            st.session_state.last_fetch_error = ""
        except Exception as exc:
            st.session_state.last_fetch_error = str(exc)
    elif "last_quote" not in st.session_state:
        # Fetch once so the dashboard is not blank even before the user enables auto mode.
        try:
            quote = st.session_state.feed.fetch(market)
            st.session_state.last_state = assistant.update(quote.price, quote.bid, quote.ask, None)
            st.session_state.last_quote = quote
            st.session_state.last_fetch_error = ""
        except Exception as exc:
            st.session_state.last_fetch_error = str(exc)

state = st.session_state.get("last_state", assistant.snapshot())
quote = st.session_state.get("last_quote")

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
    st.markdown(f'<div class="metric {cls}">{html.escape(sig)}</div><div class="mono">Z-SCORE {state.get("zscore",0):+.2f}</div><div class="muted">Strength: {state.get("strength","NONE")}</div>', unsafe_allow_html=True)
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
        st.write(f"**Feed:** {quote.source} (delayed)")
        st.write(f"**Quote time:** {age_text}")
    else:
        st.write("**Feed:** Manual")
    if st.session_state.last_fetch_error:
        st.error("Automatic data fetch failed. Check the connection or use manual mode.")
    st.markdown('</div>', unsafe_allow_html=True)

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

st.subheader("How V6 works")
st.markdown("""
1. Turn on **Enable automatic monitoring**.
2. GravAI polls the configured market feed on the selected interval.
3. A deterministic dislocation rule evaluates the recent price series.
4. When the signal changes into **LONG SETUP** or **SHORT SETUP**, V6 shows a large visual alert and, after browser sound is armed, attempts an audible beep/notification.
5. Review the entry/stop/target and risk panel.
6. **You place the order manually in TopstepX.**
""")

st.warning("Market-data limitation: the built-in Yahoo Finance feed is labeled delayed for CME futures. Do not treat these alerts as real-time execution signals. For live trading, use an authorized real-time market-data source; V6 is structured so the feed can be swapped later without adding order automation.")

with st.expander("Safety"):
    st.write("V6 never logs into, scrapes, clicks, submits, modifies, or cancels TopstepX orders. It is an analysis/alerting tool. NQ uses $20 per index point per contract; MNQ uses $2 per point per contract. Verify your current Topstep rules, contract, and risk limits before trading.")

st.caption(f"GravAI V6 • {market} • Automatic monitoring: {'ON' if auto else 'OFF'} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
