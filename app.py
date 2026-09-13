
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from src.market_engine import MarketEngine

st.set_page_config(
    page_title="GravAI • BTC Market Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Theme ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: "Space Grotesk", sans-serif;
}
.stApp {
    background:
        radial-gradient(circle at 80% 0%, rgba(214, 0, 120, .10), transparent 30%),
        radial-gradient(circle at 10% 25%, rgba(50, 20, 100, .10), transparent 28%),
        #07070b;
    color: #e8e8ef;
}
.block-container { padding: 1.0rem 1.3rem 2rem; max-width: 1700px; }
[data-testid="stHeader"] { background: transparent; }

.topbar {
    border: 1px solid #29202d;
    background: linear-gradient(90deg, rgba(20,12,24,.94), rgba(10,10,15,.94));
    padding: 12px 16px;
    border-radius: 14px;
    margin-bottom: 12px;
    box-shadow: 0 0 35px rgba(190,0,120,.06);
}
.brand { font-family:"JetBrains Mono"; font-weight:700; letter-spacing:.08em; }
.live { color:#ff3e9d; font-family:"JetBrains Mono"; font-size:.78rem; }
.small { color:#7e7b88; font-size:.72rem; font-family:"JetBrains Mono"; letter-spacing:.08em; text-transform:uppercase; }
.card {
    background: rgba(13,13,19,.92);
    border: 1px solid #26232d;
    border-radius: 14px;
    padding: 15px;
    min-height: 100%;
    box-shadow: inset 0 1px rgba(255,255,255,.015);
}
.metric {
    font-family:"JetBrains Mono";
    font-size:1.8rem;
    font-weight:700;
    margin-top:5px;
}
.muted { color:#85818d; }
.magenta { color:#ff38a1; }
.green { color:#48e6a1; }
.red { color:#ff587c; }
.yellow { color:#ffd166; }
.mono { font-family:"JetBrains Mono"; }
.signal {
    border:1px solid #4b193e;
    background:linear-gradient(145deg, rgba(55,10,43,.55), rgba(15,12,20,.75));
    border-radius:14px;
    padding:18px;
}
.signal-title { font-family:"JetBrains Mono"; font-size:.75rem; letter-spacing:.14em; color:#ff38a1; }
.signal-main { font-size:2.4rem; font-weight:700; margin:4px 0; }
.bar {
    height:7px; background:#1d1921; border-radius:99px; overflow:hidden; margin-top:8px;
}
.bar > div { height:100%; background:linear-gradient(90deg,#6f1458,#ff38a1); }
hr { border-color:#24212a; }
div[data-testid="stMetric"] {
    background:#0d0d13; border:1px solid #26232d; padding:10px; border-radius:12px;
}
button[kind="secondary"] {
    background:#15111a; border-color:#38263a; color:#eee;
}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_engine():
    return MarketEngine(symbol="BTCUSDT")

engine = get_engine()
engine.start()

state = engine.snapshot()
price = state["price"]
fair = state["fair_value"]
score = state["anomaly_score"]
z = state["zscore"]
imbalance = state["imbalance"]
buy_pct = state["buy_pct"]
status = state["status"]
signal = state["signal"]

st.markdown(f"""
<div class="topbar">
  <span class="brand">⚡ GRAVIAI</span>
  <span class="muted"> &nbsp; BTC MARKET INTELLIGENCE &nbsp; / &nbsp; V1</span>
  <span style="float:right" class="live">● {status.upper()} &nbsp; {datetime.now().strftime("%H:%M:%S")}</span>
</div>
""", unsafe_allow_html=True)

# Row 1
c1, c2, c3 = st.columns([1.0, 2.25, 1.0])

with c1:
    st.markdown('<div class="signal">', unsafe_allow_html=True)
    st.markdown('<div class="signal-title">AI ANOMALY DETECTOR</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="signal-main">{signal}</div>', unsafe_allow_html=True)
    st.markdown(f'<span class="mono muted">SCORE</span> <span class="mono">{score:.0f}/100</span>', unsafe_allow_html=True)
    st.markdown(f'<div class="bar"><div style="width:{score:.0f}%"></div></div>', unsafe_allow_html=True)
    st.markdown(f'<br><span class="small">Z-SCORE</span><br><span class="metric">{z:+.2f}</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="small">LIVE PRICE / 100ms MARKET FEED</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric">${price:,.2f}</div>', unsafe_allow_html=True)

    hist = state["history"]
    fig = go.Figure()
    if hist:
        df = pd.DataFrame(hist)
        fig.add_trace(go.Scatter(
            x=df["time"], y=df["price"], mode="lines",
            line=dict(color="#ff38a1", width=2),
            name="BTC"
        ))
        if "fair" in df:
            fig.add_trace(go.Scatter(
                x=df["time"], y=df["fair"], mode="lines",
                line=dict(color="#8c7aa5", width=1, dash="dot"),
                name="Fair value"
            ))
    fig.update_layout(
        height=290, margin=dict(l=0,r=0,t=10,b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8d8995", family="JetBrains Mono"),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#17151c", zeroline=False),
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=10)),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="small">PRICE INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown(f'<span class="small">ACTUAL</span><br><span class="mono">${price:,.2f}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="small">EST. FAIR VALUE</span><br><span class="mono">${fair:,.2f}</span>', unsafe_allow_html=True)
    delta = price - fair
    delta_cls = "red" if delta < 0 else "green"
    st.markdown(f'<span class="small">DEVIATION</span><br><span class="mono {delta_cls}">{delta:+,.2f}</span>', unsafe_allow_html=True)
    st.markdown(f'<hr><span class="small">ORDER FLOW</span><br><span class="mono">BUY {buy_pct:.0f}% &nbsp; / &nbsp; SELL {100-buy_pct:.0f}%</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="small">IMBALANCE</span><br><span class="mono">{imbalance:+.1f}%</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# Row 2: order book + volume
b1, b2 = st.columns([1.25, 1.0])

with b1:
    st.markdown('<div class="card"><div class="small">ORDER BOOK / TOP 10 LEVELS</div>', unsafe_allow_html=True)
    bids, asks = state["bids"], state["asks"]
    book_df = pd.DataFrame(
        [{"SIDE":"ASK","PRICE":p,"SIZE":q} for p,q in asks] +
        [{"SIDE":"BID","PRICE":p,"SIZE":q} for p,q in bids]
    )
    if not book_df.empty:
        # Render compact table with a depth bar.
        maxq = max(float(book_df["SIZE"].max()), 1e-9)
        rows = []
        for _, r in book_df.iterrows():
            side = r["SIDE"]
            cls = "red" if side == "ASK" else "green"
            pct = min(100, float(r["SIZE"]) / maxq * 100)
            rows.append(
                f'<div style="display:grid;grid-template-columns:50px 1fr 90px;gap:10px;align-items:center;margin:3px 0">'
                f'<span class="mono {cls}">{side}</span>'
                f'<span class="mono">${r["PRICE"]:,.2f}</span>'
                f'<span class="mono" style="text-align:right">{r["SIZE"]:.4f}</span>'
                f'</div>'
                f'<div class="bar"><div style="width:{pct:.1f}%"></div></div>'
            )
        st.markdown("".join(rows), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with b2:
    st.markdown('<div class="card"><div class="small">BUY / SELL AGGRESSION</div>', unsafe_allow_html=True)
    vol = state["volume_series"]
    vf = pd.DataFrame(vol)
    fig2 = go.Figure()
    if not vf.empty:
        fig2.add_trace(go.Bar(x=vf["time"], y=vf["buy"], name="Buy"))
        fig2.add_trace(go.Bar(x=vf["time"], y=[-x for x in vf["sell"]], name="Sell"))
    fig2.update_layout(
        barmode="relative", height=300, margin=dict(l=0,r=0,t=15,b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8d8995", family="JetBrains Mono"),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=True, gridcolor="#17151c", zeroline=True, zerolinecolor="#302b35"),
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=10)),
    )
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

# Row 3
l1, l2 = st.columns([1.4, 1.0])
with l1:
    st.markdown('<div class="card"><div class="small">DETECTION LOG / LIVE</div>', unsafe_allow_html=True)
    logs = state["logs"]
    for item in logs[:12]:
        cls = "magenta" if item["level"] == "ANOMALY" else ("green" if item["level"] == "FLOW" else "muted")
        st.markdown(
            f'<div class="mono" style="font-size:.74rem;margin:7px 0">'
            f'<span class="muted">{item["time"]}</span>&nbsp;&nbsp;'
            f'<span class="{cls}">{item["level"]}</span>&nbsp;&nbsp;'
            f'{item["message"]}</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

with l2:
    st.markdown('<div class="card"><div class="small">SYSTEM</div>', unsafe_allow_html=True)
    st.markdown(f'<span class="small">WEBSOCKET</span><br><span class="mono green">{status}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="small">LAST EVENT</span><br><span class="mono">{state["last_event_ms"]:.0f} ms</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="small">TRADES BUFFERED</span><br><span class="mono">{state["trade_count"]:,}</span>', unsafe_allow_html=True)
    st.markdown('<hr><span class="muted">V1 is detection-only. No exchange API keys and no order execution are used.</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Refresh without an extra package. Streamlit reruns when the page is refreshed.
st.caption("Refresh the browser to update the dashboard. The background collector continues while the Streamlit process is running.")
