from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from src.topstep_assistant import TopstepAssistant

st.set_page_config(page_title="GravAI V5 — Topstep Assistant", page_icon="⚡", layout="wide")
st.markdown("""<style>
body{background:#08090d}.block-container{padding-top:1rem}.card,.signal{background:#101118;border:1px solid #242532;border-radius:12px;padding:16px;margin-bottom:14px}.small,.muted{color:#858897}.metric{font-size:2rem;font-weight:700}.green{color:#55d98a}.red{color:#ff6878}.magenta{color:#ff4bb2}.mono{font-family:monospace}
</style>""", unsafe_allow_html=True)

st.title("⚡ GRAVAI V5 — TOPSTEP ASSISTANT")
st.caption("NQ • MNQ | Analysis + risk planning only | YOU place the TopstepX order")

market = st.sidebar.selectbox("MARKET", ["NQ", "MNQ"])
multiplier = 20.0 if market == "NQ" else 2.0
label = "E-mini Nasdaq-100" if market == "NQ" else "Micro E-mini Nasdaq-100"

if "assistants" not in st.session_state:
    st.session_state.assistants = {}
key = market
if key not in st.session_state.assistants:
    st.session_state.assistants[key] = TopstepAssistant(market, multiplier)
assistant = st.session_state.assistants[key]

st.sidebar.markdown(f"**{label}**")
st.sidebar.caption(f"$ {multiplier:.0f} per index point per contract")

st.sidebar.subheader("MARKET INPUT")
price = st.sidebar.number_input("Current / last price", min_value=0.0, value=0.0, step=0.25, format="%.2f")
bid = st.sidebar.number_input("Bid", min_value=0.0, value=0.0, step=0.25, format="%.2f")
ask = st.sidebar.number_input("Ask", min_value=0.0, value=0.0, step=0.25, format="%.2f")
fair = st.sidebar.number_input("Fair value (optional)", min_value=0.0, value=0.0, step=0.25, format="%.2f")

if st.sidebar.button("UPDATE ANALYSIS", use_container_width=True):
    st.session_state.last_state = assistant.update(price, bid, ask, fair if fair > 0 else None)

state = st.session_state.get("last_state", assistant.snapshot())

st.sidebar.subheader("TRADE PLANNER")
contracts = st.sidebar.number_input("Contracts", min_value=1, value=1, step=1)
side = st.sidebar.selectbox("Side", ["LONG", "SHORT"])
entry = st.sidebar.number_input("Planned entry", min_value=0.0, value=float(state.get("price", 0.0)), step=0.25, format="%.2f")
stop_points = st.sidebar.number_input("Stop distance (points)", min_value=0.25, value=10.0, step=0.25)
target_points = st.sidebar.number_input("Target distance (points)", min_value=0.25, value=20.0, step=0.25)
daily_limit = st.sidebar.number_input("Personal daily loss limit ($)", min_value=1.0, value=300.0, step=25.0)

risk = assistant.risk_for_stop(entry, entry - stop_points if side == "LONG" else entry + stop_points, contracts) if entry > 0 else 0.0
target = assistant.target_price(entry, target_points, side) if entry > 0 else 0.0
stop = assistant.stop_price(entry, stop_points, side) if entry > 0 else 0.0
rr = target_points / stop_points if stop_points > 0 else 0.0

c1,c2,c3 = st.columns([1,2,1])
with c1:
    st.markdown('<div class="signal"><div class="small">GRAVAI SETUP</div>', unsafe_allow_html=True)
    sig = state.get("signal", "WAITING")
    cls = "green" if "LONG" in sig else ("red" if "SHORT" in sig else "")
    st.markdown(f'<div class="metric {cls}">{sig}</div><div class="mono">Z-SCORE {state.get("zscore",0):+.2f}</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="card"><div class="small">MARKET INPUT</div>', unsafe_allow_html=True)
    st.write(f"**Bid:** {state.get('bid',0):,.2f}")
    st.write(f"**Ask:** {state.get('ask',0):,.2f}")
    st.write(f"**Fair:** {state.get('fair',0):,.2f}")
    st.write(f"**Deviation:** {state.get('deviation',0):+.2f}")
    st.write("**Feed:** MANUAL / TOPSTEPX SIDE-BY-SIDE")
    st.markdown('</div>', unsafe_allow_html=True)

st.subheader("Trade Plan")
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

st.subheader("How to use while trading")
st.markdown("""
1. Keep **TopstepX** open beside GravAI.
2. Enter the current NQ/MNQ price, bid, and ask in the sidebar.
3. Click **UPDATE ANALYSIS**.
4. Review the setup, entry, stop, target, and dollar risk.
5. If you decide to trade, place the order **manually in TopstepX**.
6. GravAI does **not** send, modify, or cancel Topstep orders.
""")

with st.expander("Safety"):
    st.write("This V5 build intentionally has no Topstep API credentials and no automatic order execution. It does not bypass or automate TopstepX. NQ uses $20/point/contract; MNQ uses $2/point/contract. Verify the current contract and your account rules before trading.")

st.caption(f"GravAI V5 • {market} • Topstep Assistant • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
