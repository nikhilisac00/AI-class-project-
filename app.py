"""
AI Alternative Investments Research Associate — Streamlit UI
============================================================
Run:  streamlit run app.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="AI Alternatives Research Associate",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* ── Hide Streamlit chrome ────────────────────────────────────── */
#MainMenu, footer, header { display: none !important; height: 0 !important; }
.stDeployButton { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

/* ── Typography ───────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] {
    font-family: "Inter", "Segoe UI", ui-sans-serif, sans-serif !important;
}

/* ── Global dark background ──────────────────────────────────── */
.stApp, [data-testid="stAppViewContainer"], .main .block-container {
    background-color: #0b1120 !important;
}
.main { background-color: #0b1120 !important; }

/* ── Main area ────────────────────────────────────────────────── */
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 1.5rem !important;
    max-width: 960px;
}

/* ── Sidebar ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #080e1a !important;
    border-right: 1px solid #141e30 !important;
}
[data-testid="stSidebar"] * {
    color: #94a3b8 !important;
}
[data-testid="stSidebar"] hr {
    border-color: #1a2540 !important;
}
[data-testid="stSidebar"] label {
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b !important;
}

/* ── Metric cards ─────────────────────────────────────────────── */
.metric-card {
    background: #111827;
    border: 1px solid #1e293b;
    border-top: 2px solid #3b82f6;
    border-radius: 8px;
    padding: 12px 14px;
    text-align: center;
}
.metric-card .metric-label {
    font-size: 0.62rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-bottom: 4px;
}
.metric-card .metric-value {
    font-size: 1.2rem;
    font-weight: 700;
    color: #f1f5f9;
    line-height: 1.2;
}
.metric-card .metric-sub {
    font-size: 0.62rem;
    color: #64748b;
    margin-top: 2px;
}
.metric-card.risk-card {
    border-top: 2px solid #ef4444;
}

/* ── Firm result header ───────────────────────────────────────── */
.firm-header {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 14px 20px;
    margin-bottom: 12px;
}
.firm-header h2 {
    margin: 0 0 4px 0;
    font-size: 1.15rem;
    font-weight: 700;
    color: #f1f5f9;
}
.firm-header .firm-meta {
    font-size: 0.72rem;
    color: #64748b;
    margin-top: 4px;
}

/* ── Step labels ──────────────────────────────────────────────── */
.step-label {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
}
.step-label .step-num {
    background: #1e40af;
    color: #fff;
    border-radius: 50%;
    width: 20px; height: 20px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.68rem; font-weight: 700; flex-shrink: 0;
}
.step-label .step-title {
    font-size: 0.88rem;
    font-weight: 700;
    color: #e2e8f0;
}

/* ── Risk tier banner ─────────────────────────────────────────── */
.risk-tier-banner {
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 0.85rem;
    font-weight: 700;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Section label ────────────────────────────────────────────── */
.section-label {
    font-size: 0.62rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-bottom: 4px;
}

/* ── Sidebar config title ─────────────────────────────────────── */
.sb-title {
    font-size: 0.72rem;
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 10px 0 6px 0;
    border-bottom: 1px solid #1a2540;
    margin-bottom: 8px;
}

/* ── Badges ───────────────────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    line-height: 1.6;
}

/* ── Primary button ───────────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
    border: none !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    padding: 0.4rem 1.5rem !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.3) !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1d4ed8 0%, #3b82f6 100%) !important;
    box-shadow: 0 2px 8px rgba(37, 99, 235, 0.4) !important;
    transform: translateY(-1px) !important;
}

/* ── Tabs ─────────────────────────────────────────────────────── */
[data-testid="stTabs"] button[role="tab"] {
    font-size: 0.74rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    padding: 6px 14px !important;
    color: #94a3b8 !important;
}

/* ── Expanders ────────────────────────────────────────────────── */
[data-testid="stExpander"] summary {
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    color: #cbd5e1 !important;
}
[data-testid="stExpander"] {
    border-color: #1e293b !important;
}

/* ── Dividers ─────────────────────────────────────────────────── */
hr { border-color: #1e293b !important; }

/* ── Captions ─────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {
    font-size: 0.7rem !important;
    color: #64748b !important;
}

/* ── Hero card ────────────────────────────────────────────────────────────── */
.hero-card {
    background: linear-gradient(145deg, #0f172a 0%, #131d33 50%, #111827 100%);
    border-radius: 10px;
    padding: 14px 22px 12px 22px;
    margin-bottom: 12px;
    border: 1px solid #1e293b;
}
.hero-row {
    display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
}
.hero-icon {
    background: linear-gradient(135deg, #d4a537 0%, #b8942f 100%);
    border-radius: 6px;
    width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem; flex-shrink: 0;
}
.hero-title {
    font-size: 1.05rem; font-weight: 700; color: #f1f5f9;
    letter-spacing: -0.01em;
}
.hero-sub {
    font-size: 0.65rem; color: #475569; margin-top: 1px;
    letter-spacing: 0.02em;
}

/* ── Horizontal step flow ────────────────────────────────────────────────── */
.step-flow {
    display: flex; align-items: center;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; padding: 8px 14px;
}
.sf-step { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.sf-circle {
    width: 22px; height: 22px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.65rem; font-weight: 700; flex-shrink: 0;
    transition: all 0.2s ease;
}
.sf-text { min-width: 0; }
.sf-name { font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
.sf-hint { font-size: 0.6rem; opacity: 0.5; white-space: nowrap; }
.sf-arrow { color: rgba(255,255,255,0.12); font-size: 0.85rem; padding: 0 6px; flex-shrink: 0; }
.sf-step.s1 .sf-circle { background: rgba(59,130,246,0.15); color: #60a5fa; }
.sf-step.s1 .sf-name   { color: #60a5fa; }
.sf-step.s1 .sf-hint   { color: #334155; }
.sf-step.s2 .sf-circle { background: rgba(52,211,153,0.12); color: #34d399; }
.sf-step.s2 .sf-name   { color: #34d399; }
.sf-step.s2 .sf-hint   { color: #334155; }
.sf-step.s3 .sf-circle { background: rgba(251,191,36,0.12); color: #fbbf24; }
.sf-step.s3 .sf-name   { color: #fbbf24; }
.sf-step.s3 .sf-hint   { color: #334155; }
.sf-step.s4 .sf-circle { background: rgba(167,139,250,0.12); color: #a78bfa; }
.sf-step.s4 .sf-name   { color: #a78bfa; }
.sf-step.s4 .sf-hint   { color: #334155; }

/* ── Search section card ─────────────────────────────────────────────────── */
.search-section {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 14px 18px 12px 18px;
    margin-bottom: 12px;
}
.search-section-title {
    font-size: 0.62rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em;
    color: #64748b; margin-bottom: 8px;
}
[data-testid="stTextInput"] input {
    font-size: 0.88rem !important;
    border-radius: 6px !important;
    border: 1px solid #1e293b !important;
    padding: 8px 14px !important;
    background: #0f172a !important;
    color: #e2e8f0 !important;
    transition: all 0.2s ease !important;
}
[data-testid="stTextInput"] input::placeholder {
    color: #475569 !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #2563eb !important;
    background: #0c1425 !important;
    box-shadow: 0 0 0 2px rgba(37,99,235,0.15) !important;
}

/* ── Example chips ───────────────────────────────────────────────────────── */
.chip-section-label {
    font-size: 0.6rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em;
    color: #475569; margin: 6px 0 4px 0;
}
div[data-testid="column"] .stButton > button {
    background: transparent !important;
    border: 1px solid #1e293b !important;
    border-radius: 16px !important;
    color: #94a3b8 !important;
    font-size: 0.65rem !important;
    font-weight: 500 !important;
    padding: 2px 0 !important;
    transition: all 0.2s ease !important;
    line-height: 1.4 !important;
}
div[data-testid="column"] .stButton > button:hover {
    background: rgba(37,99,235,0.1) !important;
    color: #60a5fa !important;
    border-color: #2563eb !important;
}

/* ── Criteria strip ──────────────────────────────────────────────────────── */
.criteria-strip {
    background: rgba(180,140,50,0.06);
    border: 1px solid rgba(180,140,50,0.15);
    border-radius: 8px; padding: 10px 14px; margin-top: 8px;
}
.criteria-strip-title {
    font-size: 0.6rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em;
    color: #b8942f; margin-bottom: 6px;
}
.criteria-row {
    display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2px 14px;
}
.crit-item {
    display: flex; align-items: baseline; gap: 5px;
    font-size: 0.68rem; color: #94a3b8; line-height: 1.5;
}
.crit-dot { color: #b8942f; font-size: 0.6rem; flex-shrink: 0; }

/* ── Dark theme overrides for Streamlit containers ───────────────────────── */
[data-testid="stContainer"], [data-testid="stVerticalBlock"] {
    color: #e2e8f0;
}
.stAlert { border-radius: 6px !important; }
.stMarkdown p { color: #cbd5e1; }
.stMarkdown strong { color: #f1f5f9; }
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { color: #f1f5f9; }

</style>
""", unsafe_allow_html=True)

sys.path.insert(0, str(Path(__file__).parent))

import agents.data_ingestion  as ingestion_agent  # noqa: E402
import agents.firm_resolver   as resolver_agent   # noqa: E402
import agents.fund_analysis   as analysis_agent   # noqa: E402
import agents.news_research   as news_agent       # noqa: E402
import agents.risk_flagging   as risk_agent       # noqa: E402
import agents.memo_generation as memo_agent       # noqa: E402
import agents.ic_scorecard      as scorecard_agent    # noqa: E402
import agents.research_director as director_agent    # noqa: E402
import agents.comparables       as comparables_agent # noqa: E402
import agents.fact_checker      as fact_checker_agent  # noqa: E402
import agents.comparison        as comparison_agent    # noqa: E402
import agents.portfolio_fit     as portfolio_fit_agent # noqa: E402
from tools.llm_client import make_client              # noqa: E402
from tools.pal_client  import is_available as pal_available, call_consensus  # noqa: E402
from tools.memo_export import to_docx, to_pdf        # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────────────

def _badge(label: str, color: str) -> str:
    return (
        f'<span class="badge" style="background:{color};color:#fff">{label}</span>'
    )

def _sev_color(sev: str) -> str:
    return {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}.get(sev, "#7f8c8d")

def _tier_color(tier: str) -> str:
    return {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}.get(tier, "#95a5a6")

def _score_color(score: float) -> str:
    if score >= 0.80:
        return "#27ae60"
    if score >= 0.55:
        return "#e67e22"
    return "#c0392b"


# ── Session state init ───────────────────────────────────────────────────────

for _k, _v in [
    ("confirmed_firm",  None),
    ("user_website",    ""),
    ("candidates",      []),
    ("search_query",    ""),
    ("pipeline_done",   False),
    ("pipeline_result", {}),
    ("chat_messages",   []),
    ("_auto_search",       False),
    ("firm_b_result",      {}),
    ("comparison_result",  {}),
    ("portfolio_fit_result", {}),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Watch List helpers ───────────────────────────────────────────────────────

_WATCHLIST_PATH = Path("./output/watchlist.json")


def _load_watchlist() -> list:
    try:
        if _WATCHLIST_PATH.exists():
            return json.loads(_WATCHLIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_watchlist(items: list) -> None:
    try:
        _WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        _WATCHLIST_PATH.write_text(json.dumps(items, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="sb-title">⚙ Configuration</div>', unsafe_allow_html=True)

    def _secret(key: str) -> str:
        """Read from env vars first, then Streamlit secrets (for Cloud deployments)."""
        val = os.getenv(key, "")
        if not val:
            try:
                val = st.secrets.get(key, "")
            except Exception:
                pass
        return val or ""

    st.markdown('<div class="section-label">API Keys</div>', unsafe_allow_html=True)
    fred_key = st.text_input(
        "FRED API Key (optional)",
        value=_secret("FRED_API_KEY"),
        type="password",
        help="Free at fred.stlouisfed.org — adds macro rates/spreads.",
    )

    tavily_key = st.text_input(
        "Tavily API Key (optional)",
        value=_secret("TAVILY_API_KEY"),
        type="password",
        help="Free tier at tavily.com (1,000/mo). Falls back to DuckDuckGo.",
    )

    openai_key = st.text_input(
        "OpenAI API Key",
        value=_secret("OPENAI_API_KEY"),
        type="password",
        help="Required. Powers all analysis with GPT-4o. Get one at platform.openai.com",
    )
    st.caption("Model: gpt-4o")

    st.divider()
    st.markdown('<div class="section-label">Research Options</div>', unsafe_allow_html=True)
    run_news = st.toggle(
        "Deep News Research",
        value=True,
        help="Iterative web research loop on the manager.",
    )
    news_rounds = st.slider("Research rounds", min_value=1, max_value=5, value=3) if run_news else 3

    st.divider()
    st.markdown('<div class="section-label">Advanced</div>', unsafe_allow_html=True)
    use_pal    = False
    pal_status = pal_available()
    if pal_status:
        use_pal = st.toggle(
            "Multi-Model Consensus (PAL)",
            value=False,
            help="Validate risk flags with Gemini-3-Pro via PAL MCP.",
        )
        st.caption("PAL MCP: connected")
    else:
        st.caption("PAL MCP: not available")

    output_dir = st.text_input(
        "Output directory",
        value="./output/memos",
        help="Where to save memo and JSON files",
    )

    st.divider()
    st.markdown('<div class="section-label">Risk Scoring Weights</div>', unsafe_allow_html=True)
    st.caption("Adjust how each risk dimension is weighted (1 = low priority, 10 = critical)")
    w_regulatory = st.slider("Regulatory / Compliance", 1, 10, 8)
    w_key_person = st.slider("Key Person Risk", 1, 10, 7)
    w_structure  = st.slider("Fund Structure", 1, 10, 5)
    w_fees       = st.slider("Fee Structure", 1, 10, 4)
    scoring_weights = {
        "Regulatory": w_regulatory,
        "Key Person": w_key_person,
        "Fund Structure": w_structure,
        "Fees": w_fees,
    }

    st.divider()
    st.caption("Data: IAPD · SEC EDGAR 13F · Form D · FRED")
    st.caption("No hallucination — every fact cites a real API field")


# ── Hero card (always visible) ───────────────────────────────────────────────

_step_active = (
    4 if st.session_state.pipeline_done else
    3 if st.session_state.get("_pipeline_running") else
    2 if st.session_state.confirmed_firm else
    1
)

def _sf(n, label, hint, cls):
    active_ring = ' outline:2px solid currentColor;outline-offset:2px;' if n == _step_active else ''
    return f'''<div class="sf-step {cls}">
      <div class="sf-circle" style="{active_ring}">{n}</div>
      <div class="sf-text">
        <div class="sf-name">{label}</div>
        <div class="sf-hint">{hint}</div>
      </div>
    </div>'''

st.markdown(f"""
<div class="hero-card">
  <div class="hero-row">
    <div class="hero-icon">📋</div>
    <div>
      <div class="hero-title">LP Due Diligence Intelligence</div>
      <div class="hero-sub">SEC EDGAR 13F · IAPD / Form ADV · Form D · FRED Macro · GPT-4o · 8 AI Agents</div>
    </div>
  </div>
  <div class="step-flow">
    {_sf(1, "Search", "Firm or CRD", "s1")}
    <div class="sf-arrow">›</div>
    {_sf(2, "Confirm", "IAPD match", "s2")}
    <div class="sf-arrow">›</div>
    {_sf(3, "Analyze", "8 agents", "s3")}
    <div class="sf-arrow">›</div>
    {_sf(4, "Review", "IC memo", "s4")}
  </div>
</div>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# STEP 1 — Firm Search & Confirmation
# ────────────────────────────────────────────────────────────────────────────

_EXAMPLE_FIRMS = [
    ("AQR Capital Management",  "Quant · $120B+"),
    ("Bridgewater Associates",   "Macro · $150B+"),
    ("Two Sigma Investments",    "Quant · $60B+"),
    ("D.E. Shaw",                "Quant · $60B+"),
    ("Citadel Advisors",         "Multi-strategy"),
    ("Millennium Management",    "Multi-strategy"),
    ("Man Group",                "Quant / Alt"),
    ("Renaissance Technologies", "Quant · Medallion"),
]

if not st.session_state.confirmed_firm:
    st.markdown('<div class="search-section">', unsafe_allow_html=True)
    st.markdown('<div class="search-section-title">Search Investment Manager</div>', unsafe_allow_html=True)

    col_q, col_find = st.columns([6, 1])
    with col_q:
        query_input = st.text_input(
            "Firm",
            value=st.session_state.search_query,
            placeholder='Firm name or CRD number — e.g. "AQR Capital Management" or "149729"',
            label_visibility="collapsed",
            key="firm_search_input",
        )
    with col_find:
        find_btn = st.button("Search", type="primary", use_container_width=True)

    # Example chips
    st.markdown('<div class="chip-section-label">Quick examples</div>', unsafe_allow_html=True)
    # Two rows of 4 for cleaner layout
    _row1 = _EXAMPLE_FIRMS[:4]
    _row2 = _EXAMPLE_FIRMS[4:]
    chip_cols_1 = st.columns(4)
    for _ci, (_firm_name, _firm_sub) in enumerate(_row1):
        with chip_cols_1[_ci]:
            if st.button(_firm_name, key=f"chip_{_ci}", use_container_width=True, help=_firm_sub):
                st.session_state.search_query = _firm_name
                st.session_state._auto_search  = True
                st.rerun()
    chip_cols_2 = st.columns(4)
    for _ci, (_firm_name, _firm_sub) in enumerate(_row2):
        with chip_cols_2[_ci]:
            if st.button(_firm_name, key=f"chip_{_ci + 4}", use_container_width=True, help=_firm_sub):
                st.session_state.search_query = _firm_name
                st.session_state._auto_search  = True
                st.rerun()

    # Criteria below chips
    st.markdown("""
<div class="criteria-strip">
  <div class="criteria-strip-title">Which firms qualify?</div>
  <div class="criteria-row">
    <div class="crit-item"><span class="crit-dot">◆</span><span>SEC-registered adviser (CRD number)</span></div>
    <div class="crit-item"><span class="crit-dot">◆</span><span>Files Form ADV with IAPD</span></div>
    <div class="crit-item"><span class="crit-dot">◆</span><span>Hedge funds, PE, quant, family offices</span></div>
    <div class="crit-item"><span class="crit-dot">◆</span><span>Files 13F quarterly (&gt;$100M US equities)</span></div>
    <div class="crit-item"><span class="crit-dot">◆</span><span>US-based or US-registered operations</span></div>
    <div class="crit-item"><span class="crit-dot">◆</span><span>State-registered also supported (less data)</span></div>
  </div>
</div>
""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)  # close search-section
else:
    # Firm already confirmed — show minimal search bar for changing
    col_q, col_find = st.columns([5, 1])
    with col_q:
        query_input = st.text_input(
            "Firm",
            value=st.session_state.search_query,
            placeholder='Firm name or CRD number',
            label_visibility="collapsed",
            key="firm_search_input",
        )
    with col_find:
        find_btn = st.button("Search", type="primary", use_container_width=True)

# Trigger search (manual button OR chip auto-search)
_do_search = find_btn or st.session_state.get("_auto_search", False)
if _do_search:
    st.session_state._auto_search = False
    _q = query_input.strip() or st.session_state.search_query
    if not _q:
        st.error("Enter a firm name or CRD to search.")
    else:
        with st.spinner(f"Searching IAPD for '{_q}'..."):
            candidates = resolver_agent.resolve(
                _q,
                tavily_key=tavily_key or None,
                max_candidates=5,
            )
        st.session_state.candidates    = candidates
        st.session_state.search_query  = _q
        st.session_state.confirmed_firm = None   # reset if re-searching
        st.session_state.pipeline_done  = False
        st.session_state.pipeline_result = {}

# Auto-confirm if resolver is confident
if (st.session_state.candidates and not st.session_state.confirmed_firm
        and st.session_state.candidates[0].get("auto_confirm")):
    st.session_state.confirmed_firm  = st.session_state.candidates[0]
    st.session_state.pipeline_done   = False
    st.session_state.pipeline_result = {}
    st.rerun()

# Show candidates
if st.session_state.candidates and not st.session_state.confirmed_firm:
    st.markdown("**Select the correct firm:**")
    for i, c in enumerate(st.session_state.candidates):
        score   = c.get("match_score", 0.0)
        sc      = _score_color(score)
        name    = c.get("firm_name", "Unknown")
        crd     = c.get("crd", "")
        city    = c.get("city", "")
        state   = c.get("state", "")
        status  = c.get("registration_status", "")
        website = c.get("website") or ""

        with st.container(border=True):
            hdr_col, btn_col = st.columns([5, 1])
            with hdr_col:
                st.markdown(
                    f'**{name}** &nbsp;'
                    f'<span style="background:{sc};color:#fff;padding:1px 7px;'
                    f'border-radius:3px;font-size:0.75rem">'
                    f'Match {score:.0%}</span>',
                    unsafe_allow_html=True,
                )
                # Website is the primary identifier — show it prominently
                if website:
                    st.markdown(f'🌐 [{website}]({website})')
                meta = []
                if crd:
                    meta.append(f"CRD: **{crd}**")
                if city and state:
                    meta.append(f"{city}, {state}")
                if status:
                    meta.append(status)
                if meta:
                    st.caption("  ·  ".join(meta))
            with btn_col:
                if st.button("Use this firm", key=f"use_{i}", use_container_width=True):
                    st.session_state.confirmed_firm  = c
                    st.session_state.pipeline_done   = False
                    st.session_state.pipeline_result = {}
                    st.rerun()

elif st.session_state.candidates and st.session_state.confirmed_firm:
    # Show confirmed banner
    cf = st.session_state.confirmed_firm
    st.success(
        f"Confirmed: **{cf.get('firm_name')}** "
        f"(CRD {cf.get('crd')}, {cf.get('city', '')}, {cf.get('state', '')})"
    )
    if st.button("Change firm", type="secondary"):
        st.session_state.confirmed_firm = None
        st.session_state.pipeline_done  = False
        st.session_state.pipeline_result = {}
        st.rerun()

# ── Optional website override ────────────────────────────────────────────────
if st.session_state.confirmed_firm:
    detected = st.session_state.confirmed_firm.get("website") or ""
    website_input = st.text_input(
        "Firm website (optional — improves fund discovery)",
        value=st.session_state.user_website or detected,
        placeholder="https://www.example.com",
        help="Leave blank to use auto-detected website, or paste the correct URL.",
    )
    st.session_state.user_website = website_input.strip()


# ────────────────────────────────────────────────────────────────────────────
# STEP 2 — Run Analysis (only shown after firm confirmation)
# ────────────────────────────────────────────────────────────────────────────

if st.session_state.confirmed_firm:
    st.markdown("""
    <div class="step-label">
      <div class="step-num">2</div>
      <div class="step-title">Run Analysis</div>
    </div>
    """, unsafe_allow_html=True)

    run_button = st.button(
        f"Run Due Diligence on {st.session_state.confirmed_firm.get('firm_name', '')}",
        type="primary",
        use_container_width=True,
        disabled=not openai_key,
    )
    if not openai_key:
        st.caption("Add your OpenAI API key in the sidebar to run.")
else:
    run_button = False


# ────────────────────────────────────────────────────────────────────────────
# Pipeline execution
# ────────────────────────────────────────────────────────────────────────────

if run_button:
    cf          = st.session_state.confirmed_firm
    firm_input  = cf.get("crd") or cf.get("firm_name", "")
    user_website = st.session_state.user_website or None
    client      = make_client(openai_key)

    progress_bar = st.progress(0, text="Starting...")
    status_box   = st.empty()

    raw_data = analysis = risk_report = memo = pal_review = news_report = None

    try:
        total_steps = 7 + (1 if run_news else 0) + (1 if use_pal and pal_status else 0)
        step = [0]
        def _pct(n): return int(n / total_steps * 100)

        status_box.info("⏳ Step 1 — Fetching IAPD registration · EDGAR 13F filings · FRED macro rates · Form D fund records...")
        progress_bar.progress(5, text="Fetching data sources...")
        raw_data = ingestion_agent.run(
            firm_input,
            fred_api_key=fred_key or None,
            website=user_website,
            client=client,
            tavily_key=tavily_key or None,
        )
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Data ingestion complete")

        fd_count   = len((raw_data.get("fund_discovery") or {}).get("funds", []))
        aum_note   = (raw_data.get("adv_xml_data") or {}).get("thirteenf", {}).get("portfolio_value_fmt") or "no 13F"
        errs_count = len(raw_data.get("errors", []))
        _ingest_summary = f"{fd_count} funds found · 13F: {aum_note}"
        if errs_count:
            _ingest_summary += f" · {errs_count} notes"
        if raw_data.get("errors"):
            st.warning("Ingestion notes: " + " | ".join(raw_data["errors"]))

        status_box.info(f"⏳ Step 2 — Analyzing firm structure · {_ingest_summary} · Running GPT-4o reasoning...")
        analysis = analysis_agent.run(raw_data, client)
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Analysis complete")

        firm_name_resolved = (
            (analysis or {}).get("firm_overview", {}).get("name")
            or cf.get("firm_name", firm_input)
        )

        if run_news:
            search_backend = "Tavily" if tavily_key else "DuckDuckGo"
            status_box.info(
                f"Step 3 — Deep news research ({news_rounds} rounds · {search_backend})..."
            )
            news_report = news_agent.run(
                firm_name=firm_name_resolved,
                analysis=analysis,
                client=client,
                tavily_api_key=tavily_key or None,
                max_rounds=news_rounds,
            )
            step[0] += 1
            progress_bar.progress(_pct(step[0]), text=(
                f"News complete — {news_report['research_rounds']} rounds, "
                f"{news_report['total_sources']} sources"
            ))
            if news_report.get("errors"):
                st.warning("News notes: " + " | ".join(news_report["errors"]))

        status_box.info("⏳ Step 4 — Scanning for LP risk flags · regulatory disclosures · key-person concentration · data gaps...")
        risk_report = risk_agent.run(analysis, raw_data, client, news_report=news_report,
                                     scoring_weights=scoring_weights)
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Risk flagging complete")

        if use_pal and pal_status:
            status_box.info("PAL — Multi-model consensus (Gemini-3-Pro)...")
            pal_review = call_consensus(
                question=(
                    "Validate these LP due diligence risk flags. "
                    "Identify gaps, overstatements, or missing standard diligence items."
                ),
                content=json.dumps(risk_report, indent=2, default=str),
            )
            step[0] += 1
            progress_bar.progress(_pct(step[0]), text="PAL complete")

        status_box.info("⏳ Step 5 — Drafting IC-ready due diligence memo (11 sections)...")
        memo = memo_agent.run(analysis, risk_report, raw_data, client,
                              news_report=news_report)
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Memo complete")

        status_box.info("⏳ Step 5b — Fact Checker verifying memo claims against source data...")
        fact_check = fact_checker_agent.run(
            memo_text=memo,
            raw_data=raw_data,
            analysis=analysis,
            risk_report=risk_report,
            scorecard={},
            client=client,
        )
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Fact check complete")

        status_box.info("⏳ Step 6 — Scoring investment dimensions · building IC recommendation...")
        scorecard = scorecard_agent.run(analysis, risk_report, raw_data, client,
                                        news_report=news_report)
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Scorecard complete")

        status_box.info("⏳ Step 7 — Searching IAPD for comparable managers by strategy and size...")
        comparables = comparables_agent.run(
            firm_name=firm_name_resolved,
            adv_summary=raw_data.get("adv_summary", {}),
            raw_data=raw_data,
        )
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Comparables complete")

        status_box.info("⏳ Step 8 — Research Director cross-checking findings for inconsistencies...")
        director_review = director_agent.run(
            analysis, risk_report, raw_data, scorecard, client,
            news_report=news_report,
        )
        progress_bar.progress(100, text="Done")
        status_box.success("Analysis complete.")

        st.session_state.pipeline_result = dict(
            raw_data=raw_data, analysis=analysis, risk_report=risk_report,
            memo=memo, scorecard=scorecard, comparables=comparables,
            director_review=director_review, pal_review=pal_review,
            news_report=news_report, firm_name=firm_name_resolved,
            fact_check=fact_check,
        )
        st.session_state.pipeline_done = True

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.exception(e)
        st.stop()


# ────────────────────────────────────────────────────────────────────────────
# Results display
# ────────────────────────────────────────────────────────────────────────────

if st.session_state.pipeline_done and st.session_state.pipeline_result:
    pr          = st.session_state.pipeline_result
    raw_data    = pr["raw_data"]
    analysis    = pr["analysis"]
    risk_report = pr["risk_report"]
    memo        = pr["memo"]
    scorecard       = pr.get("scorecard", {})
    comparables     = pr.get("comparables", {})
    director_review = pr.get("director_review", {})
    pal_review      = pr["pal_review"]
    news_report = pr["news_report"]
    firm_name   = pr["firm_name"]
    fact_check  = pr.get("fact_check", {})

    # Save outputs
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in firm_name)[:40]
    out_dir   = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{ts}_{safe_name}"

    memo_path = base.parent / f"{base.name}_DD_MEMO.md"
    if memo:
        try:
            memo_path.write_text(memo, encoding="utf-8")
        except Exception:
            pass
    for label, obj in [("raw_data", raw_data), ("analysis", analysis), ("risk_report", risk_report)]:
        if obj:
            try:
                (base.parent / f"{base.name}_{label}.json").write_text(
                    json.dumps(obj, indent=2, default=str), encoding="utf-8"
                )
            except Exception:
                pass

    # Extract display fields
    adv      = (raw_data  or {}).get("adv_summary",   {})
    adv_xml  = (raw_data  or {}).get("adv_xml_data",  {})
    ov       = (analysis  or {}).get("firm_overview",  {})
    tf       = adv_xml.get("thirteenf",   {})
    discl    = adv_xml.get("disclosures", [])
    broch    = adv_xml.get("brochure",    {})
    macro    = (raw_data  or {}).get("market_context", {})
    tier     = (risk_report or {}).get("overall_risk_tier", "UNKNOWN")
    fd       = (raw_data  or {}).get("fund_discovery", {})

    # ── Firm Identity Header ──────────────────────────────────────────────
    reg_status = adv.get("registration_status") or ov.get("registration_status")
    reg_color  = "#1a7a4a" if reg_status == "ACTIVE" else "#b03030"
    crd_str    = adv.get("crd_number") or ov.get("crd")
    sec_str    = adv.get("sec_number") or ov.get("sec_number")
    city       = adv.get("city")
    state_str  = adv.get("state")
    adv_date   = adv.get("adv_filing_date")

    badges_html = ""
    if reg_status:
        badges_html += _badge(reg_status, reg_color) + " "
    if adv.get("is_sec_registered"):
        badges_html += _badge("SEC Registered", "#1a3d6e") + " "
    if adv.get("is_state_registered"):
        badges_html += _badge("State Registered", "#5b3a8e") + " "
    if adv.get("has_disclosures"):
        badges_html += _badge("Disclosures on Record", "#8b3a1a") + " "
    firm_type = ov.get("firm_type")
    if firm_type and firm_type != "Unknown":
        badges_html += _badge(firm_type, "#2c6e49") + " "

    meta_items = []
    if crd_str:
        meta_items.append(f"CRD {crd_str}")
    if sec_str:
        meta_items.append(f"SEC {sec_str}")
    if city and state_str:
        meta_items.append(f"{city}, {state_str}")
    if adv_date:
        meta_items.append(f"ADV filed {adv_date}")
    meta_html = "  ·  ".join(meta_items)

    notice_states = adv.get("notice_filing_states", [])
    notice_html = ""
    if notice_states:
        notice_html = (
            f'<div style="margin-top:6px;font-size:0.77rem;color:#8fa3bb">'
            f'Notice filings: {", ".join(notice_states)}</div>'
        )

    _hdr_col, _wl_col = st.columns([5, 1])
    with _hdr_col:
        st.markdown(f"""
        <div class="firm-header">
          <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
            <h2>{firm_name}</h2>
            <div>{badges_html}</div>
          </div>
          <div class="firm-meta">{meta_html}</div>
          {notice_html}
        </div>
        """, unsafe_allow_html=True)
    with _wl_col:
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        _wl = _load_watchlist()
        _already_watched = any(w.get("firm_name") == firm_name for w in _wl)
        if _already_watched:
            st.success("On Watch List", icon="👁")
        elif st.button("+ Watch List", use_container_width=True, help="Add to LP watch list"):
            _wl.append({
                "firm_name": firm_name,
                "crd": adv.get("crd_number") or "",
                "added_date": datetime.now().strftime("%Y-%m-%d"),
                "risk_tier": tier,
                "recommendation": (scorecard or {}).get("recommendation", ""),
            })
            _save_watchlist(_wl)
            st.rerun()

    # ── Key Metric Cards ──────────────────────────────────────────────────
    tier_color_map = {"HIGH": "#b03030", "MEDIUM": "#b06010", "LOW": "#1a7a4a"}
    tier_c_card = tier_color_map.get(tier, "#4a5568")

    def _metric_card(label: str, value: str, sublabel: str = "", risk: bool = False) -> str:
        sub = f'<div class="metric-sub">{sublabel}</div>' if sublabel else ""
        cls = "metric-card risk-card" if risk else "metric-card"
        return f"""
        <div class="{cls}">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
          {sub}
        </div>"""

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.markdown(_metric_card(
        "13F Portfolio",
        tf.get("portfolio_value_fmt") or "N/A",
        "US public equity"
    ), unsafe_allow_html=True)
    c2.markdown(_metric_card(
        "Holdings",
        str(tf.get("holdings_count")) if tf.get("holdings_count") else "—",
        "positions"
    ), unsafe_allow_html=True)
    c3.markdown(_metric_card(
        "Funds Found",
        str(fd.get("total_found", 0)),
        "Form D + IAPD"
    ), unsafe_allow_html=True)
    c4.markdown(_metric_card(
        "Clients",
        str(ov.get("num_clients")) if ov.get("num_clients") else "—",
    ), unsafe_allow_html=True)
    c5.markdown(_metric_card(
        "Employees",
        str(ov.get("num_employees")) if ov.get("num_employees") else "—",
    ), unsafe_allow_html=True)
    c6.markdown(_metric_card(
        "Risk Tier",
        f'<span style="color:{tier_c_card}">{tier}</span>',
        risk=True,
    ), unsafe_allow_html=True)

    # ── Analyst Notes (from fund_analysis extended thinking) ─────────────
    analyst_notes = (analysis or {}).get("analyst_notes")
    firm_type_rationale = ov.get("firm_type_rationale")
    if analyst_notes:
        st.info(f"**Analyst Read:** {analyst_notes}")
    elif firm_type_rationale:
        st.info(f"**Firm Type:** {firm_type_rationale}")

    # ── Source / brochure captions ────────────────────────────────────────
    if tf.get("accession") and tf.get("cik"):
        acc_clean  = tf["accession"].replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{tf['cik']}"
            f"/{acc_clean}/{tf['accession']}-index.htm"
        )
        st.caption(
            f"[EDGAR 13F-HR filing]({filing_url}) · {tf.get('filing_date', '')} · "
            f"{tf.get('note', '')}"
        )
    else:
        st.caption(adv_xml.get("aum_note", "Regulatory AUM not available via free public API."))

    if broch.get("brochure_name"):
        st.caption(
            f"ADV Part 2A: **{broch['brochure_name']}** "
            f"(filed {broch.get('brochure_date', '')}). "
            "PDF at adviserinfo.sec.gov"
        )

    # ── Disclosure Banner ─────────────────────────────────────────────────
    if discl:
        import pandas as pd
        with st.expander(f"Disclosure Events ({len(discl)}) — from IAPD", expanded=False):
            df_d = pd.DataFrame([{
                "Type":        d.get("type", ""),
                "Date":        d.get("date") or "—",
                "Description": d.get("description") or "—",
                "Resolution":  d.get("resolution") or "—",
            } for d in discl])
            st.dataframe(df_d, use_container_width=True, hide_index=True)
    elif adv.get("has_disclosures"):
        st.warning(
            "IAPD indicates disclosure events on record. "
            "Visit adviserinfo.sec.gov for full details."
        )

    # ── Macro Context Panel ───────────────────────────────────────────────
    if macro:
        st.markdown("---")
        st.caption("**Market Context** (FRED — latest readings)")
        m1, m2, m3, m4, m5 = st.columns(5)
        def _m(series): return macro.get(series, {}).get("latest") or "—"
        m1.metric("Fed Funds", _m("fed_funds_rate") + "%" if _m("fed_funds_rate") != "—" else "—")
        m2.metric("10Y Yield", _m("ten_yr_yield")   + "%" if _m("ten_yr_yield")   != "—" else "—")
        m3.metric("HY Spread", _m("hy_spread")             if _m("hy_spread")      != "—" else "—")
        m4.metric("IG Spread", _m("ig_spread")             if _m("ig_spread")      != "—" else "—")
        m5.metric("VIX",       _m("vix")                   if _m("vix")            != "—" else "—")

    # ── Historical 13F Portfolio Trend ───────────────────────────────────
    history = (raw_data or {}).get("adv_xml_data", {}).get("thirteenf_history", [])
    if history and len(history) >= 2:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        periods  = [h["period"] for h in history]
        vals_b   = [round(h["portfolio_value_usd"] / 1e9, 3) for h in history]
        holdings = [h.get("holdings_count") for h in history]

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Scatter(
                x=periods, y=vals_b,
                name="Portfolio ($B)",
                fill="tozeroy",
                fillcolor="rgba(41,128,185,0.15)",
                line=dict(color="#2980b9", width=2),
                marker=dict(size=5),
            ),
            secondary_y=False,
        )
        if any(h is not None for h in holdings):
            fig.add_trace(
                go.Scatter(
                    x=periods, y=holdings,
                    name="Holdings Count",
                    line=dict(color="#e67e22", width=2, dash="dot"),
                    marker=dict(size=5),
                ),
                secondary_y=True,
            )
        fig.update_layout(
            title_text="13F Portfolio Trend — Public US Equity Holdings",
            height=300,
            margin=dict(l=10, r=10, t=45, b=10),
            legend=dict(orientation="h", y=-0.2),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        fig.update_yaxes(title_text="Portfolio Value ($B)", secondary_y=False, gridcolor="#eee")
        fig.update_yaxes(title_text="Holdings Count",       secondary_y=True,  showgrid=False)

        st.markdown("---")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Source: SEC EDGAR 13F-HR · {len(history)} quarters · "
            "US public equity positions only — not total regulatory AUM"
        )

    # ── 13F Holdings Breakdown ────────────────────────────────────────────
    holdings_data = tf.get("holdings_breakdown", {})
    if holdings_data:
        import plotly.graph_objects as go  # noqa: F811

        top_h    = holdings_data.get("top_holdings", [])
        ac_break = holdings_data.get("asset_class_breakdown", {})
        conc     = holdings_data.get("concentration", {})

        st.markdown("---")
        st.subheader("13F Holdings Breakdown")

        # ── Concentration metric cards ────────────────────────────────────
        hc1, hc2, hc3 = st.columns(3)
        hc1.metric(
            "Total Positions",
            str(conc.get("total_positions", "—")),
            help="Unique issuers after aggregating all investment discretion types",
        )
        hc2.metric(
            "Top 10 Concentration",
            f"{conc['top_10_pct']}%" if conc.get("top_10_pct") is not None else "—",
            help="% of portfolio held in the 10 largest positions",
        )
        hc3.metric(
            "Top 25 Concentration",
            f"{conc['top_25_pct']}%" if conc.get("top_25_pct") is not None else "—",
            help="% of portfolio held in the 25 largest positions",
        )

        # ── Charts: bar + pie side by side ───────────────────────────────
        col_bar, col_pie = st.columns([3, 2])

        with col_bar:
            if top_h:
                top10 = top_h[:10]
                bar_names = [h["name"][:30] for h in reversed(top10)]
                bar_vals  = [round(h["value_usd"] / 1e6, 1) for h in reversed(top10)]
                bar_fig = go.Figure(go.Bar(
                    x=bar_vals,
                    y=bar_names,
                    orientation="h",
                    marker_color="#2980b9",
                    text=[f"${v:.0f}M" for v in bar_vals],
                    textposition="outside",
                ))
                bar_fig.update_layout(
                    title="Top 10 Positions by Value",
                    xaxis_title="Value (USD millions)",
                    height=360,
                    margin=dict(l=10, r=60, t=45, b=10),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                bar_fig.update_xaxes(gridcolor="#eee")
                st.plotly_chart(bar_fig, use_container_width=True)

        with col_pie:
            if ac_break:
                pie_labels = list(ac_break.keys())
                pie_vals   = [ac_break[k]["pct"] for k in pie_labels]
                pie_fig = go.Figure(go.Pie(
                    labels=pie_labels,
                    values=pie_vals,
                    hole=0.4,
                    textinfo="label+percent",
                    hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
                ))
                pie_fig.update_layout(
                    title="Asset Class Breakdown",
                    height=360,
                    margin=dict(l=10, r=10, t=45, b=10),
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(pie_fig, use_container_width=True)

        # ── Full top-25 holdings table ────────────────────────────────────
        if top_h:
            import pandas as pd
            with st.expander(f"Top {len(top_h)} Holdings Table"):
                df = pd.DataFrame([
                    {
                        "Rank":        h["rank"],
                        "Name":        h["name"],
                        "CUSIP":       h["cusip"],
                        "Value":       h["value_fmt"],
                        "% Portfolio": f"{h['pct_of_portfolio']:.2f}%"
                                       if h.get("pct_of_portfolio") is not None else "—",
                        "Shares":      f"{h['shares']:,}" if h.get("shares") else "—",
                        "Asset Class": h["asset_class"],
                    }
                    for h in top_h
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption(
            "Source: SEC EDGAR 13F Information Table · Latest quarter only · "
            "Aggregated by CUSIP across all investment discretion types"
        )

    # ── TL;DR Summary Banner ─────────────────────────────────────────────
    st.markdown("---")
    _tldr_rec     = (scorecard or {}).get("recommendation", "")
    _tldr_summary = (scorecard or {}).get("recommendation_summary", "")
    _tldr_verdict = (director_review or {}).get("verdict", "")
    _tldr_dir_rec = (director_review or {}).get("revised_recommendation", "")
    _tldr_tier    = (risk_report or {}).get("overall_risk_tier", "UNKNOWN")
    _tldr_comment = (risk_report or {}).get("overall_commentary", "")
    _tldr_news    = (news_report or {}).get("overall_news_risk", "") if news_report else ""
    _tldr_news_sum= (news_report or {}).get("news_summary", "") if news_report else ""

    _tldr_rec_color   = {"PROCEED": "#1a7a4a", "REQUEST MORE INFO": "#b06010", "PASS": "#b03030"}.get(_tldr_rec, "#4a5568")
    _tldr_tier_color  = {"HIGH": "#b03030", "MEDIUM": "#b06010", "LOW": "#1a7a4a"}.get(_tldr_tier, "#4a5568")
    _tldr_verdict_color = {"CONFIRMED": "#1a7a4a", "UPGRADED": "#1a3d6e", "DOWNGRADED": "#b03030", "INCONCLUSIVE": "#b06010"}.get(_tldr_verdict, "#4a5568")

    _tldr_parts = []
    if _tldr_rec:
        _tldr_parts.append(f'<span style="font-weight:700;color:{_tldr_rec_color}">{_tldr_rec}</span>')
    if _tldr_tier:
        _tldr_parts.append(f'Risk: <span style="font-weight:700;color:{_tldr_tier_color}">{_tldr_tier}</span>')
    if _tldr_verdict and _tldr_dir_rec:
        _tldr_parts.append(f'Director: <span style="font-weight:700;color:{_tldr_verdict_color}">{_tldr_verdict} → {_tldr_dir_rec}</span>')
    if _tldr_news:
        _nc = {"HIGH":"#b03030","MEDIUM":"#b06010","LOW":"#1a7a4a"}.get(_tldr_news,"#4a5568")
        _tldr_parts.append(f'News Risk: <span style="font-weight:700;color:{_nc}">{_tldr_news}</span>')

    _tldr_detail = _tldr_summary or _tldr_comment or ""

    st.markdown(f"""
    <div style="background:#ffffff;border:1px solid #e2e6ea;border-left:4px solid #1a3d6e;
                border-radius:6px;padding:14px 18px;margin-bottom:8px">
      <div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.08em;color:#8fa3bb;margin-bottom:6px">TL;DR — Analysis Summary</div>
      <div style="font-size:0.88rem;display:flex;flex-wrap:wrap;gap:16px;margin-bottom:{"8px" if _tldr_detail else "0"}">{" &nbsp;·&nbsp; ".join(_tldr_parts)}</div>
      {"<div style='font-size:0.80rem;color:#4a5568;line-height:1.5;border-top:1px solid #f0f2f5;padding-top:8px;margin-top:4px'>" + _tldr_detail[:280] + ("…" if len(_tldr_detail) > 280 else "") + "</div>" if _tldr_detail else ""}
    </div>
    """, unsafe_allow_html=True)

    # ── Results Tabs ──────────────────────────────────────────────────────
    enf_report  = (raw_data or {}).get("enforcement", {})
    enf_sev     = enf_report.get("severity", "CLEAN")
    _enf_icons  = {"CLEAN": "✅", "LOW": "🟡", "MEDIUM": "🟠", "HIGH": "🔴", "CRITICAL": "🚨"}
    enf_icon    = _enf_icons.get(enf_sev, "⚪")

    # ── Tab badge helpers ─────────────────────────────────────────────────
    _risk_flags   = (risk_report or {}).get("flags", [])
    _high_flags   = sum(1 for f in _risk_flags if f.get("severity") == "HIGH")
    _med_flags    = sum(1 for f in _risk_flags if f.get("severity") == "MEDIUM")
    _news_risk    = (news_report or {}).get("overall_news_risk", "")
    _news_flags   = len((news_report or {}).get("news_flags", []))
    _rec          = (scorecard or {}).get("recommendation", "")
    _rec_icons    = {"PROCEED": "✅", "REQUEST MORE INFO": "🔄", "PASS": "❌"}
    _risk_badge   = f" 🔴{_high_flags}" if _high_flags else (f" 🟡{_med_flags}" if _med_flags else " 🟢")
    _news_badge   = f" 🔴{_news_flags}" if _news_risk == "HIGH" and _news_flags else (f" 🟡{_news_flags}" if _news_flags else "")
    _rec_badge    = f" {_rec_icons.get(_rec,'')}" if _rec else ""
    _enf_badge    = f" {enf_icon}" if enf_sev != "CLEAN" else " ✅"

    _fc_verdict   = (fact_check or {}).get("verdict", "")
    _fc_badge     = " ✅" if _fc_verdict == "PASS" else (" ⚠️" if _fc_verdict == "PASS_WITH_FLAGS" else (" 🔴" if _fc_verdict == "FAIL" else ""))

    (
        tab_memo, tab_scorecard, tab_risk, tab_director,
        tab_enf, tab_comparables, tab_funds, tab_news,
        tab_fact_check, tab_pal, tab_raw, tab_chat,
        tab_portfolio_fit, tab_compare, tab_watchlist,
    ) = st.tabs([
        "DD Memo",
        f"IC Scorecard{_rec_badge}",
        f"Risk Dashboard{_risk_badge}",
        "Director Review",
        f"Enforcement{_enf_badge}",
        "Comparables",
        "Funds",
        f"News{_news_badge}",
        f"Fact Checker{_fc_badge}",
        "PAL Consensus",
        "Raw Data",
        "💬 AI Assistant",
        "Portfolio Fit",
        "Compare",
        "Watch List 👁",
    ])

    # ─ IC Scorecard ──────────────────────────────────────────────────────
    with tab_scorecard:
        if scorecard:
            rec       = scorecard.get("recommendation", "UNKNOWN")
            conf      = scorecard.get("confidence", "UNKNOWN")
            rec_color = {"PROCEED": "#1a7a4a", "REQUEST MORE INFO": "#b06010", "PASS": "#b03030"}.get(rec, "#4a5568")
            rec_icon  = {"PROCEED": "✅", "REQUEST MORE INFO": "🔄", "PASS": "❌"}.get(rec, "⚪")
            conf_color = {"HIGH": "#1a7a4a", "MEDIUM": "#b06010", "LOW": "#b03030"}.get(conf, "#4a5568")

            # ── Recommendation banner ─────────────────────────────────────
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0f1923 0%,#1a2f45 100%);
                        border-radius:4px;padding:12px 16px;margin-bottom:8px;border-left:3px solid {rec_color}">
              <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
                <div style="font-size:2.2rem">{rec_icon}</div>
                <div>
                  <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
                              letter-spacing:0.1em;color:#8fa3bb;margin-bottom:4px">
                    IC Recommendation
                  </div>
                  <div style="font-size:1.8rem;font-weight:800;color:{rec_color}">
                    {rec}
                  </div>
                </div>
                <div style="margin-left:auto;text-align:right">
                  <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
                              letter-spacing:0.1em;color:#8fa3bb;margin-bottom:4px">
                    Confidence
                  </div>
                  <div style="font-size:1.2rem;font-weight:700;color:{conf_color}">{conf}</div>
                </div>
              </div>
              <div style="font-size:0.88rem;color:#c8d6e5;line-height:1.6;border-top:1px solid #1e3a5a;padding-top:12px">
                {scorecard.get("recommendation_summary", "")}
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Overall score + dimension scores ──────────────────────────
            overall = scorecard.get("overall_score")
            scores  = scorecard.get("scores", {})

            score_labels = {
                "regulatory_compliance": "Regulatory & Compliance",
                "data_availability":     "Data Availability",
                "key_person_risk":       "Key Person Risk",
                "fund_structure":        "Fund Structure",
                "news_reputation":       "News & Reputation",
                "operational_maturity":  "Operational Maturity",
            }

            if scores:
                st.markdown("#### Score Breakdown")
                for key, label in score_labels.items():
                    dim = scores.get(key, {})
                    s   = dim.get("score")
                    rat = dim.get("rationale", "")
                    if s is None:
                        continue
                    s = int(s)
                    bar_color = "#1a7a4a" if s >= 7 else "#b06010" if s >= 5 else "#b03030"
                    bar_pct   = s * 10

                    st.markdown(f"""
                    <div style="margin-bottom:12px">
                      <div style="display:flex;justify-content:space-between;
                                  margin-bottom:4px;align-items:baseline">
                        <span style="font-size:0.82rem;font-weight:600;color:#0f1923">{label}</span>
                        <span style="font-size:1rem;font-weight:700;color:{bar_color}">{s}/10</span>
                      </div>
                      <div style="background:#e8ecf0;border-radius:4px;height:8px;overflow:hidden">
                        <div style="background:{bar_color};width:{bar_pct}%;height:100%;
                                    border-radius:4px;transition:width 0.3s"></div>
                      </div>
                      <div style="font-size:0.75rem;color:#6b7a8d;margin-top:3px">{rat}</div>
                    </div>
                    """, unsafe_allow_html=True)

                if overall is not None:
                    ov_color = "#1a7a4a" if float(overall) >= 7 else "#b06010" if float(overall) >= 5 else "#b03030"
                    st.markdown(f"""
                    <div style="background:#f7f9fc;border:1px solid #e8ecf0;border-radius:8px;
                                padding:14px 18px;margin-top:8px;display:flex;
                                justify-content:space-between;align-items:center">
                      <span style="font-size:0.85rem;font-weight:700;color:#0f1923;
                                   text-transform:uppercase;letter-spacing:0.05em">
                        Overall Score
                      </span>
                      <span style="font-size:1.6rem;font-weight:800;color:{ov_color}">
                        {overall}/10
                      </span>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")

            # ── Reasons to proceed / pause ────────────────────────────────
            col_pros, col_cons = st.columns(2)
            with col_pros:
                st.markdown("#### Reasons to Proceed")
                for r in scorecard.get("reasons_to_proceed", []):
                    st.markdown(
                        f'<div style="display:flex;gap:8px;margin-bottom:8px">'
                        f'<span style="color:#1a7a4a;font-size:1rem;flex-shrink:0">✓</span>'
                        f'<span style="font-size:0.85rem;color:#0f1923">{r}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            with col_cons:
                st.markdown("#### Reasons to Pause")
                for r in scorecard.get("reasons_to_pause", []):
                    st.markdown(
                        f'<div style="display:flex;gap:8px;margin-bottom:8px">'
                        f'<span style="color:#b03030;font-size:1rem;flex-shrink:0">⚠</span>'
                        f'<span style="font-size:0.85rem;color:#0f1923">{r}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── Minimum diligence checklist ───────────────────────────────
            diligence = scorecard.get("minimum_diligence_items", [])
            if diligence:
                st.markdown("#### Minimum Diligence Checklist")
                must  = [d for d in diligence if d.get("priority") == "MUST HAVE"]
                nice  = [d for d in diligence if d.get("priority") != "MUST HAVE"]
                for group, label, color in [(must, "Must Have", "#b03030"), (nice, "Nice to Have", "#b06010")]:
                    if group:
                        st.markdown(
                            f'<div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;'
                            f'letter-spacing:0.08em;color:{color};margin:10px 0 6px 0">{label}</div>',
                            unsafe_allow_html=True,
                        )
                        for d in group:
                            st.markdown(
                                f'<div style="background:#f7f9fc;border:1px solid #e8ecf0;'
                                f'border-left:3px solid {color};border-radius:6px;'
                                f'padding:10px 14px;margin-bottom:6px">'
                                f'<div style="font-size:0.85rem;font-weight:600;color:#0f1923">'
                                f'{d.get("item","")}</div>'
                                f'<div style="font-size:0.75rem;color:#6b7a8d;margin-top:3px">'
                                f'{d.get("why","")}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

            # ── Standard LP asks ──────────────────────────────────────────
            lp_asks = scorecard.get("standard_lp_asks", [])
            if lp_asks:
                with st.expander("Standard LP Asks (GP Request List)"):
                    for ask in lp_asks:
                        st.markdown(f"- {ask}")

            # ── Data coverage ─────────────────────────────────────────────
            cov = scorecard.get("data_coverage_assessment", "")
            cov_note = scorecard.get("data_coverage_note", "")
            if cov:
                cov_color = {"HIGH": "#1a7a4a", "MEDIUM": "#b06010", "LOW": "#b03030"}.get(cov, "#4a5568")
                st.caption(
                    f"Data coverage: **{cov}** — {cov_note}"
                )

            # ── Confidence rationale ──────────────────────────────────────
            if scorecard.get("confidence_rationale"):
                st.caption(f"Confidence note: {scorecard['confidence_rationale']}")

        else:
            st.warning("IC Scorecard not available.")

    # ─ Enforcement Tab ───────────────────────────────────────────────────
    with tab_enf:
        _sev_colors_enf = {
            "CLEAN":    "#1a7a4a",
            "LOW":      "#b5870a",
            "MEDIUM":   "#b06010",
            "HIGH":     "#c0392b",
            "CRITICAL": "#7b0000",
        }
        enf_sev_color = _sev_colors_enf.get(enf_sev, "#4a5568")

        # ── Severity banner ───────────────────────────────────────────────
        st.markdown(
            f'<div style="background:{enf_sev_color};color:#fff;padding:10px 16px;'
            f'border-radius:6px;font-size:1.1rem;font-weight:700;margin-bottom:16px">'
            f'{enf_icon} Enforcement Severity: {enf_sev}</div>',
            unsafe_allow_html=True,
        )

        if enf_report.get("summary"):
            if enf_sev == "CLEAN":
                st.success(enf_report["summary"])
            elif enf_sev in ("HIGH", "CRITICAL"):
                st.error(enf_report["summary"])
            else:
                st.warning(enf_report["summary"])

        # ── Key stats row ─────────────────────────────────────────────────
        enf_data   = enf_report.get("enforcement_data", {})
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Total Actions",    str(enf_data.get("total_actions", 0)))
        ec2.metric(
            "High Severity",
            str(enf_data.get("high_count", 0)),
            help="Bars, suspensions, fraud orders, criminal disclosures",
        )
        ec3.metric(
            "Open / Pending",
            str(len(enf_data.get("open_actions", []))),
            help="Actions without a clear resolved/dismissed status",
        )
        ec4.metric(
            "Total Penalties",
            enf_data.get("penalty_total_fmt") or "—",
            help="Sum of numeric penalty amounts extracted from IAPD disclosures",
        )

        # ── Red flags ─────────────────────────────────────────────────────
        red_flags = enf_report.get("red_flags", [])
        if red_flags:
            st.markdown("---")
            st.subheader("Red Flags")
            for flag in red_flags:
                st.markdown(
                    f'<div style="background:#fff0f0;border-left:4px solid #c0392b;'
                    f'padding:8px 12px;border-radius:4px;margin-bottom:6px">'
                    f'🚩 {flag}</div>',
                    unsafe_allow_html=True,
                )

        # ── Key findings ──────────────────────────────────────────────────
        key_findings = enf_report.get("key_findings", [])
        if key_findings:
            st.markdown("---")
            st.subheader("Key Findings")
            for finding in key_findings:
                st.markdown(f"- {finding}")

        # ── Individual action cards ───────────────────────────────────────
        actions = enf_data.get("actions", [])
        if actions:
            st.markdown("---")
            st.subheader(f"Enforcement Actions ({len(actions)})")
            import pandas as pd
            _sev_c = {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}
            for i, a in enumerate(actions):
                sev   = a.get("severity", "LOW")
                badge = (
                    f'<span style="background:{_sev_c.get(sev,"#95a5a6")};'
                    f'color:#fff;padding:1px 8px;border-radius:3px;'
                    f'font-size:0.75rem;font-weight:600">{sev}</span>'
                )
                label = (
                    f'{badge} &nbsp;'
                    f'[{a.get("action_type","")} · {a.get("initiated_by","")}] &nbsp;'
                    f'{(a.get("description") or "")[:70]}'
                )
                with st.expander(label, expanded=(sev == "HIGH" and i < 3)):
                    col_a, col_b = st.columns(2)
                    col_a.markdown(f"**Date:** {a.get('date') or '—'}")
                    col_a.markdown(f"**Type:** {a.get('action_type','—')}")
                    col_a.markdown(f"**Initiated by:** {a.get('initiated_by','—')}")
                    col_b.markdown(f"**Resolution:** {a.get('resolution') or '—'}")
                    col_b.markdown(
                        f"**Penalty:** {a.get('penalty_fmt') or '—'}"
                    )
                    if a.get("sanctions"):
                        st.markdown(
                            "**Sanctions:** " + " · ".join(a["sanctions"])
                        )
                    if a.get("description"):
                        st.markdown(f"**Description:** {a['description']}")
                    if a.get("raw_details"):
                        with st.expander("Full IAPD detail fields"):
                            df_d = pd.DataFrame(
                                [{"Field": k, "Value": v}
                                 for k, v in a["raw_details"].items()],
                            )
                            st.dataframe(df_d, use_container_width=True,
                                         hide_index=True)

        # ── Web search results ────────────────────────────────────────────
        web_results = enf_data.get("web_results", [])
        if web_results:
            st.markdown("---")
            with st.expander(
                f"Web Search — Enforcement News ({len(web_results)} results)"
            ):
                for r in web_results:
                    st.markdown(
                        f"**[{r.get('title','(no title)')}]({r.get('url','')})**"
                        + (f"  ·  {r.get('date','')}" if r.get("date") else "")
                    )
                    st.caption(r.get("snippet", "")[:300])
                    st.markdown("---")

        # ── EDGAR enforcement-adjacent filings ────────────────────────────
        edgar_hits = enf_data.get("edgar_hits", [])
        if edgar_hits:
            st.markdown("---")
            with st.expander(
                f"EDGAR Enforcement-Adjacent Filings ({len(edgar_hits)})"
            ):
                import pandas as pd
                df_e = pd.DataFrame([
                    {
                        "Form":       h.get("form_type"),
                        "Filed":      h.get("file_date"),
                        "Accession":  h.get("accession"),
                        "EDGAR Link": h.get("edgar_url") or "—",
                    }
                    for h in edgar_hits
                ])
                st.dataframe(df_e, use_container_width=True, hide_index=True)

        # ── EDGAR submission flags ────────────────────────────────────────
        edgar_flags = enf_data.get("edgar_flags", [])
        if edgar_flags:
            st.markdown("---")
            with st.expander(
                f"Unusual EDGAR Submission Forms ({len(edgar_flags)})"
            ):
                import pandas as pd
                df_f = pd.DataFrame([
                    {"Form": f.get("form_type"), "Filed": f.get("file_date"),
                     "Accession": f.get("accession")}
                    for f in edgar_flags
                ])
                st.dataframe(df_f, use_container_width=True, hide_index=True)
                st.caption(
                    "ADV-W = registration withdrawal · "
                    "UPLOAD = SEC staff-uploaded document"
                )

        if enf_report.get("errors"):
            with st.expander("Enforcement check notes"):
                for err in enf_report["errors"]:
                    st.caption(f"⚠ {err}")

        st.caption(
            "Sources: IAPD regulatory/criminal/civil disclosures · "
            "SEC EDGAR EFTS · EDGAR Submissions · "
            "adviserinfo.sec.gov"
        )

    # ─ Director Review ───────────────────────────────────────────────────
    with tab_director:
        if director_review:
            verdict     = director_review.get("verdict", "UNKNOWN")
            revised_rec = director_review.get("revised_recommendation", "")
            orig_rec    = director_review.get("original_recommendation", "")
            verdict_color = {
                "CONFIRMED":    "#1a7a4a",
                "UPGRADED":     "#1a3d6e",
                "DOWNGRADED":   "#b03030",
                "INCONCLUSIVE": "#b06010",
            }.get(verdict, "#4a5568")
            verdict_icon = {
                "CONFIRMED": "✅", "UPGRADED": "⬆️",
                "DOWNGRADED": "⬇️", "INCONCLUSIVE": "🔄",
            }.get(verdict, "⚪")

            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0f1923 0%,#1a2f45 100%);
                        border-radius:4px;padding:12px 16px;margin-bottom:8px;border-left:3px solid {rec_color}">
              <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;
                          letter-spacing:0.1em;color:#8fa3bb;margin-bottom:6px">
                Research Director Verdict
              </div>
              <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
                <span style="font-size:1.8rem">{verdict_icon}</span>
                <span style="font-size:1.6rem;font-weight:800;color:{verdict_color}">{verdict}</span>
                <span style="font-size:0.85rem;color:#8fa3bb;margin-left:8px">
                  {orig_rec} → <strong style="color:#ffffff">{revised_rec}</strong>
                </span>
              </div>
              <div style="font-size:0.88rem;color:#c8d6e5;line-height:1.6;
                          border-top:1px solid #1e3a5a;padding-top:12px">
                {director_review.get("director_commentary", "")}
              </div>
            </div>
            """, unsafe_allow_html=True)

            col_inc, col_miss = st.columns(2)
            with col_inc:
                inconsistencies = director_review.get("inconsistencies", [])
                if inconsistencies:
                    st.markdown("#### Inconsistencies Found")
                    for item in inconsistencies:
                        st.markdown(f"""
                        <div style="border:1px solid #e8ecf0;border-left:4px solid #b03030;
                                    border-radius:8px;padding:14px 16px;margin-bottom:8px;background:#fff">
                          <div style="font-size:0.85rem;font-weight:600;color:#0f1923;margin-bottom:6px">
                            {item.get("finding","")}
                          </div>
                          <div style="font-size:0.75rem;color:#6b7a8d;margin-bottom:4px">
                            <strong>A:</strong> {item.get("field_a","")}
                          </div>
                          <div style="font-size:0.75rem;color:#6b7a8d;margin-bottom:6px">
                            <strong>B:</strong> {item.get("field_b","")}
                          </div>
                          <div style="background:#fff5f5;border-radius:4px;padding:8px 10px;
                                      font-size:0.75rem;color:#b03030">
                            {item.get("implication","")}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("No inconsistencies found between data sources.")

            with col_miss:
                missed = director_review.get("missed_signals", [])
                if missed:
                    st.markdown("#### Missed Signals")
                    for item in missed:
                        sev = item.get("severity", "MEDIUM")
                        sev_c = _sev_color(sev)
                        st.markdown(f"""
                        <div style="border:1px solid #e8ecf0;border-left:4px solid {sev_c};
                                    border-radius:8px;padding:14px 16px;margin-bottom:8px;background:#fff">
                          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                            <span style="background:{sev_c};color:#fff;padding:2px 8px;
                                         border-radius:10px;font-size:0.70rem;font-weight:700">
                              {sev}
                            </span>
                          </div>
                          <div style="font-size:0.85rem;font-weight:600;color:#0f1923;margin-bottom:4px">
                            {item.get("signal","")}
                          </div>
                          <div style="font-size:0.75rem;color:#6b7a8d">{item.get("why_it_matters","")}</div>
                        </div>
                        """, unsafe_allow_html=True)

            questions = director_review.get("questions_for_gp", [])
            if questions:
                st.markdown("#### Questions for the GP")
                for i, q in enumerate(questions, 1):
                    st.markdown(f"""
                    <div style="display:flex;gap:10px;margin-bottom:8px;align-items:flex-start">
                      <span style="background:#1a3d6e;color:#fff;border-radius:50%;
                                   width:22px;height:22px;display:flex;align-items:center;
                                   justify-content:center;font-size:0.72rem;font-weight:700;
                                   flex-shrink:0;margin-top:1px">{i}</span>
                      <span style="font-size:0.85rem;color:#0f1923">{q}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.warning("Director Review not available.")

    # ─ Comparables ───────────────────────────────────────────────────────
    with tab_comparables:
        if comparables and comparables.get("table"):
            import pandas as pd
            table   = comparables["table"]
            note    = comparables.get("note", "")
            sr      = comparables.get("size_rank")
            target  = comparables.get("target", {})

            if sr:
                st.markdown(f"""
                <div style="background:#f7f9fc;border:1px solid #e8ecf0;border-radius:8px;
                            padding:14px 18px;margin-bottom:16px;display:flex;
                            align-items:center;gap:12px">
                  <div style="font-size:1.6rem;font-weight:800;color:#1a3d6e">#{sr}</div>
                  <div>
                    <div style="font-size:0.85rem;font-weight:600;color:#0f1923">
                      Size rank among {comparables.get("total_in_comparison",0)} managers
                    </div>
                    <div style="font-size:0.75rem;color:#8fa3bb">by 13F public equity portfolio</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            rows = []
            for r in table:
                rows.append({
                    "":              "▶ YOU" if r.get("is_target") else "",
                    "Firm":          r.get("firm_name", ""),
                    "CRD":           r.get("crd") or "—",
                    "Status":        r.get("registration_status") or "—",
                    "13F Portfolio": r.get("portfolio_value_fmt") or "—",
                    "Holdings":      str(r.get("holdings_count")) if r.get("holdings_count") else "—",
                    "Disclosures":   "Yes" if r.get("has_disclosures") else "No" if r.get("has_disclosures") is False else "—",
                    "Location":      f"{r.get('city','')}, {r.get('state','')}" if r.get("city") else r.get("state") or "—",
                    "ADV Filed":     r.get("adv_filing_date") or "—",
                })

            df = pd.DataFrame(rows)
            st.dataframe(
                df.style.apply(
                    lambda x: ["background-color:#e8f4fd;font-weight:600" if x[""] == "▶ YOU"
                               else "" for _ in x],
                    axis=1,
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(note)
        else:
            st.info("Comparables not available.")

    # ─ Risk Dashboard ────────────────────────────────────────────────────
    with tab_risk:
        if risk_report:
            tier_c = _tier_color(tier)
            tier_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(tier, "⚪")
            st.markdown(
                f'<div class="risk-tier-banner" style="background:{tier_c}20;'
                f'border-left:4px solid {tier_c};color:#0f1923">'
                f'<span style="font-size:1.3rem">{tier_icon}</span>'
                f'<span>Overall Risk Tier: <strong style="color:{tier_c}">{tier}</strong></span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            commentary = risk_report.get("overall_commentary", "")
            if commentary:
                st.info(commentary)

            flags = risk_report.get("flags", [])
            if flags:
                order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
                flags_sorted = sorted(flags, key=lambda f: order.get(f.get("severity", ""), 9))
                st.markdown(f"#### Risk Flags &nbsp; `{len(flags_sorted)}`")
                for f in flags_sorted:
                    sev   = f.get("severity", "")
                    sev_c = _sev_color(sev)
                    cat   = f.get("category", "")
                    finding  = f.get("finding", "")
                    evidence = f.get("evidence", "")
                    action   = f.get("lp_action", "")
                    context  = f.get("context", "")
                    context_row = (
                        f'<div style="background:#f0f7f0;border-radius:6px;padding:10px 12px;margin-top:10px">'
                        f'<div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;'
                        f'letter-spacing:0.07em;color:#1a7a4a;margin-bottom:4px">Context</div>'
                        f'<div style="font-size:0.80rem;color:#4a5568;line-height:1.5">{context}</div>'
                        f'</div>'
                    ) if context else ""
                    st.markdown(f"""
                    <div style="border:1px solid #e8ecf0;border-left:4px solid {sev_c};
                                border-radius:8px;padding:16px 18px;margin-bottom:10px;
                                background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.05)">
                      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                        <span style="background:{sev_c};color:#fff;padding:3px 10px;
                                     border-radius:12px;font-size:0.72rem;font-weight:700;
                                     letter-spacing:0.05em;text-transform:uppercase">{sev}</span>
                        <span style="background:#f0f4f8;color:#4a5568;padding:3px 10px;
                                     border-radius:12px;font-size:0.72rem;font-weight:600">{cat}</span>
                      </div>
                      <div style="font-size:0.92rem;font-weight:600;color:#0f1923;
                                  margin-bottom:10px;line-height:1.5">{finding}</div>
                      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                        <div style="background:#f7f9fc;border-radius:6px;padding:10px 12px">
                          <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;
                                      letter-spacing:0.07em;color:#8fa3bb;margin-bottom:4px">Evidence</div>
                          <div style="font-size:0.80rem;color:#4a5568;line-height:1.5">{evidence}</div>
                        </div>
                        <div style="background:#fff8f0;border-radius:6px;padding:10px 12px">
                          <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;
                                      letter-spacing:0.07em;color:#b06010;margin-bottom:4px">LP Action</div>
                          <div style="font-size:0.80rem;color:#4a5568;line-height:1.5">{action}</div>
                        </div>
                      </div>
                      {context_row}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("No risk flags identified from available public data.")

            st.markdown("---")
            col_gaps, col_clean = st.columns(2)
            with col_gaps:
                gaps = risk_report.get("critical_data_gaps", [])
                if gaps:
                    st.markdown("#### Critical Data Gaps")
                    for g in gaps:
                        st.markdown(f"""
                        <div style="display:flex;gap:8px;margin-bottom:6px;align-items:flex-start">
                          <span style="color:#b03030;font-size:0.85rem;flex-shrink:0;margin-top:2px">⚠</span>
                          <span style="font-size:0.83rem;color:#4a5568">{g}</span>
                        </div>""", unsafe_allow_html=True)
            with col_clean:
                clean = risk_report.get("clean_items", [])
                if clean:
                    st.markdown("#### Clean Items")
                    for c in clean:
                        st.markdown(f"""
                        <div style="display:flex;gap:8px;margin-bottom:6px;align-items:flex-start">
                          <span style="color:#1a7a4a;font-size:0.85rem;flex-shrink:0;margin-top:2px">✓</span>
                          <span style="font-size:0.83rem;color:#4a5568">{c}</span>
                        </div>""", unsafe_allow_html=True)
        else:
            st.warning("Risk report not available.")

    # ─ Funds Tab ─────────────────────────────────────────────────────────
    with tab_funds:
        funds_list = fd.get("funds", [])
        ra_list    = fd.get("relying_advisors", [])
        sources    = fd.get("sources_used", [])
        fd_errors  = fd.get("errors", [])

        # ── ADV Section 7.B (authoritative private fund list from ADV PDF) ──
        s7b_funds = (raw_data.get("adv_summary") or {}).get("private_funds_section7b") or []
        if s7b_funds:
            st.markdown("#### ADV Part 1A — Section 7.B Private Funds")
            st.caption(
                f"Source: SEC ADV Part 1A PDF · {len(s7b_funds)} fund(s) disclosed by adviser · "
                "Authoritative — GP-filed with SEC, not Form D offering registrations"
            )
            import pandas as pd
            s7b_rows = []
            for f in s7b_funds:
                gav = f.get("gross_asset_value")
                gav_fmt = (
                    f"${gav/1e9:.2f}B" if gav and gav >= 1e9
                    else f"${gav/1e6:.1f}M" if gav and gav >= 1e6
                    else f"${gav:,}" if gav else "—"
                )
                raum = f.get("regulatory_aum")
                raum_fmt = (
                    f"${raum/1e9:.2f}B" if raum and raum >= 1e9
                    else f"${raum/1e6:.1f}M" if raum and raum >= 1e6
                    else f"${raum:,}" if raum else "—"
                )
                s7b_rows.append({
                    "Fund Name":       f.get("fund_name") or "—",
                    "Type":            f.get("fund_type") or "—",
                    "Gross Assets":    gav_fmt,
                    "Reg. AUM":        raum_fmt,
                    "Beneficial Owners": f.get("number_of_beneficial_owners") or "—",
                    "Feeder Fund":     "Yes" if f.get("is_feeder_fund") is True else ("No" if f.get("is_feeder_fund") is False else "—"),
                })
            st.dataframe(pd.DataFrame(s7b_rows), use_container_width=True, hide_index=True)
            st.divider()
        elif raw_data.get("adv_summary") is not None:
            st.caption(
                "ADV Section 7.B: no private fund data extracted — "
                "PDF may not be publicly accessible or firm has no registered private funds."
            )

        if funds_list or ra_list:
            # Summary
            src_str = ", ".join(sources) if sources else "none"
            st.caption(f"Sources: {src_str}  ·  Total funds discovered: {fd.get('total_found', 0)}")

            if fd_errors:
                with st.expander("Discovery notes"):
                    for e in fd_errors:
                        st.caption(e)

            # Fund table
            if funds_list:
                import pandas as pd
                st.subheader(f"Private Funds ({len(funds_list)})")

                rows = []
                for f in funds_list:
                    news_titles = "; ".join(
                        n.get("title", "") for n in (f.get("news") or [])[:2] if n.get("title")
                    )
                    rows.append({
                        "Fund Name":     f.get("name", ""),
                        "Offering Size": f.get("offering_amount") or "—",
                        "First Sale":    f.get("date_of_first_sale") or "—",
                        "Exemptions":    ", ".join(f.get("exemptions", [])) or "—",
                        "Jurisdiction":  f.get("jurisdiction") or "—",
                        "Source":        f.get("source", ""),
                        "Recent News":   news_titles or "—",
                    })
                df_f = pd.DataFrame(rows)
                st.dataframe(df_f, use_container_width=True, hide_index=True)

                # Expandable cards with EDGAR links + news
                st.subheader("Fund Detail")
                for f in funds_list:
                    with st.expander(f.get("name", "Unknown"), expanded=False):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown(f"**Offering amount:** {f.get('offering_amount') or '—'}")
                            st.markdown(f"**Date of first sale:** {f.get('date_of_first_sale') or '—'}")
                            st.markdown(f"**Entity type:** {f.get('entity_type') or '—'}")
                            st.markdown(f"**Jurisdiction:** {f.get('jurisdiction') or '—'}")
                        with col_b:
                            st.markdown(f"**Exemptions:** {', '.join(f.get('exemptions', [])) or '—'}")
                            st.markdown(f"**Private fund:** {'Yes' if f.get('is_private_fund') else 'No / Unknown'}")
                            st.markdown(f"**Source:** {f.get('source', '')}")
                            if f.get("edgar_url"):
                                st.markdown(f"[View on EDGAR]({f['edgar_url']})")
                        news = f.get("news", [])
                        if news:
                            st.markdown("**Recent news:**")
                            for n in news:
                                title = n.get("title", "")
                                url   = n.get("url", "")
                                date  = n.get("date") or ""
                                date_str = f" _{date}_" if date else ""
                                if url:
                                    st.markdown(f"- [{title}]({url}){date_str}")
                                else:
                                    st.markdown(f"- {title}{date_str}")

            # Relying advisors
            if ra_list:
                st.subheader(f"IAPD Relying Advisors ({len(ra_list)})")
                import pandas as pd
                df_ra = pd.DataFrame([{
                    "Name":   r.get("name", ""),
                    "CRD":    r.get("crd", ""),
                    "Status": r.get("status", ""),
                } for r in ra_list])
                st.dataframe(df_ra, use_container_width=True, hide_index=True)

        else:
            st.info(
                "No private funds discovered. This is expected for advisers that:\n"
                "- Manage only public equities (no private offerings)\n"
                "- File under a different entity name\n"
                "- Have not registered offerings under SEC Rule 506"
            )
            if fd_errors:
                for e in fd_errors:
                    st.caption(e)

    # ─ News Research ─────────────────────────────────────────────────────
    with tab_news:
        if news_report and (news_report.get("findings") or news_report.get("news_summary")):
            nr           = news_report
            overall_nr   = nr.get("overall_news_risk", "UNKNOWN")
            nr_color     = _tier_color(overall_nr)

            nr_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(overall_nr, "⚪")
            st.markdown(
                f'<div class="risk-tier-banner" style="background:{nr_color}20;'
                f'border-left:4px solid {nr_color};color:#0f1923">'
                f'<span style="font-size:1.3rem">{nr_icon}</span>'
                f'<span>News Risk: <strong style="color:{nr_color}">{overall_nr}</strong></span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            meta_cols = st.columns(3)
            meta_cols[0].metric("Research Rounds", nr.get("research_rounds", 0))
            meta_cols[1].metric("Sources Consulted", nr.get("total_sources", 0))
            meta_cols[2].metric("News Flags", len(nr.get("news_flags", [])))

            if nr.get("news_summary"):
                st.info(nr["news_summary"])

            flags = nr.get("news_flags", [])
            if flags:
                order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
                flags_sorted = sorted(flags, key=lambda f: order.get(f.get("severity", ""), 9))
                st.markdown(f"#### News Flags &nbsp; `{len(flags_sorted)}`")
                for f in flags_sorted:
                    sev   = f.get("severity", "INFO")
                    sev_c = _sev_color(sev) if sev != "INFO" else "#7f8c8d"
                    cat   = f.get("category", "")
                    finding = f.get("finding", "")
                    source  = f.get("source_url", "")
                    date    = f.get("date", "")
                    action  = f.get("lp_action", "")
                    source_html = (
                        f'<a href="{source}" target="_blank" style="color:#1a3d6e;font-size:0.78rem">'
                        f'{source[:60]}{"…" if len(source) > 60 else ""}</a>'
                    ) if source else "—"
                    meta_html = " &nbsp;·&nbsp; ".join(filter(None, [
                        f'<span style="font-size:0.75rem;color:#8fa3bb">{date}</span>' if date else "",
                        source_html if source else "",
                    ]))
                    st.markdown(f"""
                    <div style="border:1px solid #e8ecf0;border-left:4px solid {sev_c};
                                border-radius:8px;padding:16px 18px;margin-bottom:10px;
                                background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.05)">
                      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                        <span style="background:{sev_c};color:#fff;padding:3px 10px;
                                     border-radius:12px;font-size:0.72rem;font-weight:700;
                                     letter-spacing:0.05em;text-transform:uppercase">{sev}</span>
                        <span style="background:#f0f4f8;color:#4a5568;padding:3px 10px;
                                     border-radius:12px;font-size:0.72rem;font-weight:600">{cat}</span>
                        <span style="margin-left:auto">{meta_html}</span>
                      </div>
                      <div style="font-size:0.92rem;font-weight:600;color:#0f1923;
                                  margin-bottom:8px;line-height:1.5">{finding}</div>
                      {f'<div style="background:#fff8f0;border-radius:6px;padding:10px 12px;margin-top:8px"><div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:#b06010;margin-bottom:4px">LP Action</div><div style="font-size:0.80rem;color:#4a5568;line-height:1.5">{action}</div></div>' if action else ''}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("No material news flags identified.")

            if nr.get("coverage_gaps"):
                with st.expander("Coverage Gaps"):
                    for g in nr["coverage_gaps"]:
                        st.markdown(f"- {g}")

            if nr.get("sources_consulted"):
                import pandas as pd
                with st.expander(f"Sources Consulted ({len(nr['sources_consulted'])})"):
                    df_s = pd.DataFrame([{
                        "Title": s.get("title", "")[:80],
                        "URL":   s.get("url", ""),
                        "Date":  s.get("published_date") or "—",
                    } for s in nr["sources_consulted"]])
                    st.dataframe(df_s, use_container_width=True, hide_index=True)

            if nr.get("queries_used"):
                with st.expander(f"Search Queries Used ({len(nr['queries_used'])})"):
                    for q in nr["queries_used"]:
                        st.markdown(f"- `{q}`")

            if nr.get("errors"):
                with st.expander("Errors / Warnings"):
                    for e in nr["errors"]:
                        st.warning(e)

        elif not run_news:
            st.info("News research was skipped. Enable **Deep News Research** in the sidebar.")
        else:
            st.warning("News research produced no results.")

    # ─ DD Memo ───────────────────────────────────────────────────────────
    with tab_memo:
        if memo:
            dl1, dl2, dl3 = st.columns(3)
            with dl1:
                try:
                    docx_bytes = to_docx(memo, "", firm_name)
                    st.download_button(
                        "⬇ Download Word (.docx)",
                        data=docx_bytes,
                        file_name=f"{safe_name}_DD_MEMO.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.download_button(
                        "⬇ Download Memo (.md)",
                        data=memo,
                        file_name=f"{safe_name}_DD_MEMO.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )
            with dl2:
                try:
                    pdf_bytes = to_pdf(memo, "", firm_name)
                    st.download_button(
                        "⬇ Download PDF",
                        data=pdf_bytes,
                        file_name=f"{safe_name}_DD_MEMO.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception:
                    st.empty()
            with dl3:
                if raw_data and analysis and risk_report:
                    bundle = json.dumps(
                        {"raw_data": raw_data, "analysis": analysis, "risk_report": risk_report},
                        indent=2, default=str,
                    )
                    st.download_button(
                        "⬇ Download JSON Bundle",
                        data=bundle,
                        file_name=f"{safe_name}_bundle.json",
                        mime="application/json",
                        use_container_width=True,
                    )
            st.divider()
            st.markdown(memo)
        else:
            st.warning("Memo not generated.")

    # ─ Fact Checker ──────────────────────────────────────────────────────
    with tab_fact_check:
        if fact_check and fact_check.get("verdict") != "SKIP":
            verdict    = fact_check.get("verdict", "—")
            confidence = fact_check.get("confidence", "—")
            hal_risk   = fact_check.get("hallucination_risk", "—")
            summary    = fact_check.get("summary", "")
            verified   = fact_check.get("verified_claims", [])
            flagged    = fact_check.get("flagged_claims", [])
            high_flags = [f for f in flagged if f.get("severity") == "HIGH"]

            verdict_color = {"PASS": "#28a745", "PASS_WITH_FLAGS": "#fd7e14", "FAIL": "#dc3545"}.get(verdict, "#6c757d")
            st.markdown(
                f'<div style="padding:12px;border-radius:6px;background:{verdict_color}20;'
                f'border-left:4px solid {verdict_color};margin-bottom:12px">'
                f'<b style="color:{verdict_color};font-size:1.1rem">{verdict}</b> &nbsp;·&nbsp; '
                f'Confidence: {confidence} &nbsp;·&nbsp; Hallucination Risk: {hal_risk}<br>'
                f'<span style="font-size:0.9rem">{summary}</span></div>',
                unsafe_allow_html=True,
            )

            m1, m2, m3 = st.columns(3)
            m1.metric("Verified Claims", len(verified))
            m2.metric("Flagged Claims", len(flagged))
            m3.metric("HIGH Severity", len(high_flags))

            if flagged:
                st.subheader("Flagged Claims")
                for f in flagged:
                    sev = f.get("severity", "LOW")
                    color = {"HIGH": "#dc3545", "MEDIUM": "#fd7e14", "LOW": "#6c757d"}.get(sev, "#6c757d")
                    st.markdown(
                        f'<div style="padding:8px;border-left:3px solid {color};margin-bottom:6px">'
                        f'<b style="color:{color}">{sev}</b> &nbsp;'
                        f'<i>"{f.get("claim","")}"</i><br>'
                        f'<span style="font-size:0.85rem">⚠ {f.get("issue","")}</span></div>',
                        unsafe_allow_html=True,
                    )

            if verified:
                with st.expander(f"Verified Claims ({len(verified)})", expanded=False):
                    for v in verified:
                        st.markdown(
                            f'✅ **"{v.get("claim","")}"** — '
                            f'Source: `{v.get("source","")}` = `{v.get("value","")}`'
                        )
        else:
            st.info("Fact check not available for this analysis.")

    # ─ PAL Consensus ─────────────────────────────────────────────────────
    with tab_pal:
        if pal_review:
            st.subheader("PAL Multi-Model Consensus Review")
            st.caption("Validated by Gemini-3-Pro via PAL MCP server")
            st.markdown(pal_review)
        elif use_pal:
            st.info("PAL MCP server not available in this environment.")
        else:
            st.info(
                "Enable **Multi-Model Consensus** in the sidebar to validate "
                "risk flags with Gemini-3-Pro via PAL MCP."
            )

    # ─ Raw Data ──────────────────────────────────────────────────────────
    with tab_raw:
        if raw_data:
            with st.expander("Enforcement Data"):
                st.json(enf_report)
            with st.expander("Fund Discovery", expanded=True):
                st.json(fd)
            with st.expander("13F XML Data (EDGAR)"):
                st.json(adv_xml)
            with st.expander("IAPD ADV Summary"):
                st.json(adv)
            with st.expander("13F Filing Search Results"):
                st.json(raw_data.get("filings_13f", []))
            with st.expander("FRED Macro Context"):
                st.json(macro)
            with st.expander("Ingestion Errors / Notes"):
                st.json(raw_data.get("errors", []))
        if analysis:
            with st.expander("Structured Analysis (GPT-4o output)"):
                st.json(analysis)

    # ─ AI Assistant ──────────────────────────────────────────────────────
    with tab_chat:
        st.markdown("""
        <div style="margin-bottom:16px">
          <div style="font-size:1.05rem;font-weight:700;color:#0f1923">AI Research Assistant</div>
          <div style="font-size:0.80rem;color:#8fa3bb;margin-top:2px">
            Powered by GPT-4o · Knows everything about the analyzed firm
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Build context-aware system prompt
        if st.session_state.pipeline_done and st.session_state.pipeline_result:
            pr      = st.session_state.pipeline_result
            _firm   = pr.get("firm_name", "the analyzed firm")
            _ov     = (pr.get("analysis") or {}).get("firm_overview", {})
            _tier   = (pr.get("risk_report") or {}).get("overall_risk_tier", "UNKNOWN")
            _rec    = (pr.get("scorecard") or {}).get("recommendation", "UNKNOWN")
            _flags  = (pr.get("risk_report") or {}).get("flags", [])
            _gaps   = (pr.get("risk_report") or {}).get("critical_data_gaps", [])
            _commentary = (pr.get("risk_report") or {}).get("overall_commentary", "")
            _director   = (pr.get("director_review") or {}).get("director_commentary", "")
            _news_risk  = (pr.get("news_report") or {}).get("overall_news_risk", "N/A")

            import json as _json
            system_prompt = f"""You are an expert LP due diligence analyst assistant.
You have just completed a full due diligence analysis on {_firm}.

Here is a summary of the findings:
- Risk Tier: {_tier}
- IC Recommendation: {_rec}
- News Risk: {_news_risk}
- Overall Commentary: {_commentary}
- Director Commentary: {_director}
- Risk Flags ({len(_flags)} total): {_json.dumps([f.get('finding','') for f in _flags[:5]], default=str)}
- Critical Data Gaps: {_json.dumps(_gaps[:5], default=str)}
- Firm Overview: {_json.dumps(_ov, default=str)}

Answer the user's questions about this firm, the due diligence findings, or general LP/alternatives investing topics.
Be direct, concise, and professional. Cite specific findings when relevant.
If asked about data not in the analysis, say so clearly — do not fabricate."""
            placeholder = f"Ask anything about {_firm} or the due diligence findings..."
        else:
            system_prompt = """You are an expert LP due diligence analyst assistant specializing in
alternative investments, hedge funds, private equity, and institutional investing.
Answer questions about due diligence, SEC filings, IAPD, investment manager evaluation,
LP/GP dynamics, fund structures, and related topics.
Be direct, concise, and professional. No firm has been analyzed yet in this session."""
            placeholder = "Ask anything about LP due diligence, fund managers, or investing..."

        # Render chat history
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Chat input
        if prompt := st.chat_input(placeholder, key="chat_input"):
            if not openai_key:
                st.error("Add your OpenAI API key in the sidebar to use the AI Assistant.")
            else:
                # Add user message
                st.session_state.chat_messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                # Build messages for API call
                messages = [{"role": "system", "content": system_prompt}]
                messages += st.session_state.chat_messages

                # Get response
                with st.chat_message("assistant"):
                    with st.spinner(""):
                        try:
                            client_chat = make_client(openai_key)
                            response = client_chat.chat(messages)
                        except Exception as e:
                            response = f"Sorry, I encountered an error: {e}"
                    st.markdown(response)

                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": response}
                )

        # Clear chat button
        if st.session_state.chat_messages:
            if st.button("Clear conversation", type="secondary", key="clear_chat"):
                st.session_state.chat_messages = []
                st.rerun()

    # ─ Portfolio Fit ─────────────────────────────────────────────────────
    with tab_portfolio_fit:
        st.markdown("### Portfolio Fit Scoring")
        st.caption(
            "Define your LP's current portfolio allocation. "
            "GPT-4o scores how well this manager fits — strategy overlap, "
            "geographic/vintage diversification, size fit, risk budget."
        )

        with st.form("portfolio_fit_form"):
            st.markdown("**Strategy Allocation (% of alternatives portfolio)**")
            pf_c1, pf_c2, pf_c3 = st.columns(3)
            pf_pe    = pf_c1.number_input("Private Equity %",   0, 100, 30)
            pf_pc    = pf_c2.number_input("Private Credit %",   0, 100, 15)
            pf_hf    = pf_c3.number_input("Hedge Fund %",       0, 100, 25)
            pf_re    = pf_c1.number_input("Real Estate %",      0, 100, 15)
            pf_infra = pf_c2.number_input("Infrastructure %",   0, 100, 10)
            pf_vc    = pf_c3.number_input("Venture Capital %",  0, 100, 5)

            st.markdown("**Geographic Allocation (%)**")
            geo_c1, geo_c2, geo_c3 = st.columns(3)
            pf_na     = geo_c1.number_input("North America %", 0, 100, 60)
            pf_eu     = geo_c2.number_input("Europe %",        0, 100, 25)
            pf_asia   = geo_c3.number_input("Asia %",          0, 100, 15)

            st.markdown("**Portfolio Parameters**")
            par_c1, par_c2, par_c3 = st.columns(3)
            pf_num_mgrs   = par_c1.number_input("Current # Managers",    1, 100, 18)
            pf_target_mgrs= par_c2.number_input("Target # Managers",     1, 100, 20)
            pf_check_mm   = par_c3.number_input("Typical Check Size ($M)", 1, 500, 25)
            pf_risk_budget= st.selectbox("Risk Budget Remaining", ["LOW", "MEDIUM", "HIGH"], index=1)

            st.markdown("**Vintage Exposure (% committed per year)**")
            vint_c1, vint_c2, vint_c3, vint_c4, vint_c5 = st.columns(5)
            v2020 = vint_c1.number_input("2020 %", 0, 100, 10)
            v2021 = vint_c2.number_input("2021 %", 0, 100, 30)
            v2022 = vint_c3.number_input("2022 %", 0, 100, 25)
            v2023 = vint_c4.number_input("2023 %", 0, 100, 20)
            v2024 = vint_c5.number_input("2024 %", 0, 100, 15)

            fit_submit = st.form_submit_button("Score Portfolio Fit", type="primary",
                                               use_container_width=True)

        if fit_submit:
            if not openai_key:
                st.error("OpenAI API key required.")
            else:
                lp_portfolio = {
                    "strategies": {
                        "Private Equity": pf_pe,
                        "Private Credit": pf_pc,
                        "Hedge Fund": pf_hf,
                        "Real Estate": pf_re,
                        "Infrastructure": pf_infra,
                        "Venture Capital": pf_vc,
                    },
                    "geographies": {
                        "North America": pf_na,
                        "Europe": pf_eu,
                        "Asia": pf_asia,
                    },
                    "num_managers": pf_num_mgrs,
                    "target_managers": pf_target_mgrs,
                    "typical_check_size_mm": pf_check_mm,
                    "vintage_exposure": {
                        "2020": v2020, "2021": v2021,
                        "2022": v2022, "2023": v2023, "2024": v2024,
                    },
                    "risk_budget_remaining": pf_risk_budget,
                }
                with st.spinner("Scoring portfolio fit..."):
                    _fit = portfolio_fit_agent.run(
                        firm_name=firm_name,
                        analysis=analysis,
                        risk_report=risk_report,
                        raw_data=raw_data,
                        lp_portfolio=lp_portfolio,
                        client=make_client(openai_key),
                    )
                st.session_state.portfolio_fit_result = _fit

        _fit_result = st.session_state.get("portfolio_fit_result", {})
        if _fit_result and _fit_result.get("fit_score") is not None:
            _fit_score = _fit_result.get("fit_score", 0)
            _fit_label = _fit_result.get("fit_label", "")
            _fit_color = (
                "#1a7a4a" if _fit_score >= 85 else
                "#2980b9" if _fit_score >= 65 else
                "#b06010" if _fit_score >= 45 else
                "#c0392b"
            )
            _fit_rec   = _fit_result.get("recommendation", "")
            _fit_rec_color = {"ADD": "#1a7a4a", "CONSIDER": "#2980b9", "SKIP": "#c0392b"}.get(_fit_rec, "#4a5568")

            st.markdown(f"""
            <div style="background:#ffffff;border:1px solid #e2e6ea;
                        border-left:6px solid {_fit_color};border-radius:8px;
                        padding:18px 22px;margin:12px 0">
              <div style="font-size:2.2rem;font-weight:800;color:{_fit_color};
                          line-height:1">{_fit_score}</div>
              <div style="font-size:1rem;font-weight:700;color:{_fit_color};
                          margin-top:4px">{_fit_label}</div>
              <div style="margin-top:10px">
                <span style="background:{_fit_rec_color};color:#fff;padding:3px 12px;
                             border-radius:4px;font-size:0.85rem;font-weight:700">
                  {_fit_rec}
                </span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            _fit_reco_detail = _fit_result.get("recommendation_detail", "")
            if _fit_reco_detail:
                st.markdown(f"**Recommendation:** {_fit_reco_detail}")

            # Dimension scores
            _dim_scores = _fit_result.get("dimension_scores", {})
            if _dim_scores:
                st.markdown("**Dimension Scores**")
                _dim_cols = st.columns(3)
                for _di, (_dim, _dv) in enumerate(_dim_scores.items()):
                    with _dim_cols[_di % 3]:
                        _ds = _dv.get("score", 0) if isinstance(_dv, dict) else 0
                        _dr = _dv.get("rationale", "") if isinstance(_dv, dict) else ""
                        _dc = "#1a7a4a" if _ds >= 70 else ("#b06010" if _ds >= 45 else "#c0392b")
                        st.markdown(
                            f'<div style="border:1px solid #e2e6ea;border-radius:6px;'
                            f'padding:10px 12px;margin-bottom:8px">'
                            f'<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
                            f'color:#8fa3bb;letter-spacing:0.07em">{_dim.replace("_"," ")}</div>'
                            f'<div style="font-size:1.4rem;font-weight:800;color:{_dc}">{_ds}</div>'
                            f'<div style="font-size:0.72rem;color:#4a5568;margin-top:3px">{_dr}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            _fit_gaps     = _fit_result.get("fit_gaps", [])
            _fit_concerns = _fit_result.get("fit_concerns", [])
            _g1, _g2 = st.columns(2)
            with _g1:
                if _fit_gaps:
                    st.markdown("**Gaps This Manager Fills**")
                    for g in _fit_gaps:
                        st.markdown(f"- {g}")
            with _g2:
                if _fit_concerns:
                    st.markdown("**Concerns / Overlaps**")
                    for c in _fit_concerns:
                        st.markdown(f"- {c}")

    # ─ Compare ───────────────────────────────────────────────────────────
    with tab_compare:
        st.markdown("### Side-by-Side Manager Comparison")
        st.caption(
            f"Compare **{firm_name}** against another manager. "
            "Enter a second firm, run its analysis, then generate a head-to-head comparison."
        )

        _b_name_input = st.text_input(
            "Second firm name or CRD",
            placeholder='e.g. "Two Sigma Investments" or "149729"',
            key="firm_b_input",
        )
        _run_b = st.button("Analyze Second Firm", type="primary",
                           disabled=not (openai_key and _b_name_input.strip()),
                           key="run_firm_b")

        if _run_b and _b_name_input.strip():
            with st.spinner(f"Running mini-pipeline for {_b_name_input.strip()}..."):
                try:
                    _client_b = make_client(openai_key)
                    _b_candidates = resolver_agent.resolve(
                        _b_name_input.strip(), tavily_key=tavily_key or None, max_candidates=1
                    )
                    _b_firm = _b_candidates[0] if _b_candidates else None
                    _b_crd  = (_b_firm or {}).get("crd", _b_name_input.strip())
                    _b_raw  = ingestion_agent.run(
                        _b_crd,
                        fred_api_key=fred_key or None,
                        website=None,
                        client=_client_b,
                        tavily_key=tavily_key or None,
                    )
                    _b_analysis = analysis_agent.run(_b_raw, _client_b)
                    _b_risk     = risk_agent.run(_b_analysis, _b_raw, _client_b,
                                                 scoring_weights=scoring_weights)
                    _b_scorecard = scorecard_agent.run(_b_analysis, _b_risk, _b_raw, _client_b)
                    _b_firm_name = (
                        (_b_analysis or {}).get("firm_overview", {}).get("name")
                        or (_b_firm or {}).get("firm_name", _b_name_input.strip())
                    )
                    st.session_state.firm_b_result = {
                        "firm_name": _b_firm_name,
                        "raw_data": _b_raw,
                        "analysis": _b_analysis,
                        "risk_report": _b_risk,
                        "scorecard": _b_scorecard,
                    }
                    st.session_state.comparison_result = {}
                except Exception as _e:
                    st.error(f"Firm B analysis failed: {_e}")

        _b_res = st.session_state.get("firm_b_result", {})
        if _b_res.get("firm_name"):
            st.success(f"Firm B analyzed: **{_b_res['firm_name']}**")
            _run_compare = st.button("Generate Comparison Report", type="primary",
                                     key="run_comparison")
            if _run_compare:
                with st.spinner("Generating comparison..."):
                    _comp = comparison_agent.run(
                        firm_a_name=firm_name,
                        firm_b_name=_b_res["firm_name"],
                        analysis_a=analysis,
                        analysis_b=_b_res["analysis"],
                        risk_report_a=risk_report,
                        risk_report_b=_b_res["risk_report"],
                        raw_data_a=raw_data,
                        raw_data_b=_b_res["raw_data"],
                        scorecard_a=scorecard,
                        scorecard_b=_b_res.get("scorecard"),
                        client=make_client(openai_key),
                    )
                    st.session_state.comparison_result = _comp

        _comp_res = st.session_state.get("comparison_result", {})
        if _comp_res and _comp_res.get("dimensions"):
            _ca = _comp_res.get("manager_a", firm_name)
            _cb = _comp_res.get("manager_b", "")
            _winner = _comp_res.get("overall_winner", "")
            _winner_name = _ca if _winner == "A" else (_cb if _winner == "B" else "Tied")
            _winner_color = "#1a7a4a" if _winner in ("A", "B") else "#4a5568"

            st.markdown(f"""
            <div style="background:#ffffff;border:1px solid #e2e6ea;
                        border-left:6px solid {_winner_color};border-radius:8px;
                        padding:14px 18px;margin:12px 0">
              <div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;
                          color:#8fa3bb;margin-bottom:4px">Overall Winner</div>
              <div style="font-size:1.1rem;font-weight:800;color:{_winner_color}">{_winner_name}</div>
              <div style="font-size:0.82rem;color:#4a5568;margin-top:6px">
                {_comp_res.get("overall_rationale", "")}
              </div>
            </div>
            """, unsafe_allow_html=True)

            _comp_rec = _comp_res.get("recommendation", "")
            _comp_detail = _comp_res.get("recommendation_detail", "")
            if _comp_rec:
                st.markdown(f"**Recommendation:** {_comp_rec}")
            if _comp_detail:
                st.markdown(_comp_detail)

            # Dimension table
            import pandas as pd
            _dims = _comp_res.get("dimensions", [])
            if _dims:
                st.markdown("**Dimension-by-Dimension Comparison**")
                _win_icon = {"A": f"✅ {_ca}", "B": f"✅ {_cb}", "TIED": "🟡 Tied",
                             "INSUFFICIENT DATA": "⚪ N/A"}
                _df_comp = pd.DataFrame([{
                    "Dimension":      d.get("dimension", ""),
                    _ca[:20]:         d.get("manager_a_value", ""),
                    _cb[:20]:         d.get("manager_b_value", ""),
                    "Winner":         _win_icon.get(d.get("winner", ""), d.get("winner", "")),
                    "Rationale":      d.get("rationale", ""),
                } for d in _dims])
                st.dataframe(_df_comp, use_container_width=True, hide_index=True)

            _diffs = _comp_res.get("key_differentiators", [])
            if _diffs:
                st.markdown("**Key Differentiators**")
                for _d in _diffs:
                    st.markdown(f"- {_d}")

    # ─ Watch List ────────────────────────────────────────────────────────
    with tab_watchlist:
        st.markdown("### LP Watch List")
        st.caption(
            "Firms added to your watch list. "
            "Use this to track managers you want to monitor over time."
        )

        _wl_items = _load_watchlist()
        if not _wl_items:
            st.info(
                f"No firms on watch list yet. "
                f"Click **+ Watch List** in the firm header to add **{firm_name}**."
            )
        else:
            for _wi, _witem in enumerate(_wl_items):
                _w_name  = _witem.get("firm_name", "")
                _w_crd   = _witem.get("crd", "")
                _w_date  = _witem.get("added_date", "")
                _w_tier  = _witem.get("risk_tier", "")
                _w_rec   = _witem.get("recommendation", "")
                _tc      = {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}.get(_w_tier, "#8fa3bb")
                with st.container(border=True):
                    _wc1, _wc2 = st.columns([5, 1])
                    with _wc1:
                        st.markdown(f"**{_w_name}**")
                        _wmeta = []
                        if _w_crd:
                            _wmeta.append(f"CRD: {_w_crd}")
                        if _w_date:
                            _wmeta.append(f"Added: {_w_date}")
                        if _w_tier:
                            _wmeta.append(
                                f'Risk: <span style="color:{_tc};font-weight:700">{_w_tier}</span>'
                            )
                        if _w_rec:
                            _wmeta.append(f"IC: **{_w_rec}**")
                        st.markdown("  ·  ".join(_wmeta), unsafe_allow_html=True)
                    with _wc2:
                        if st.button("Remove", key=f"wl_rm_{_wi}", use_container_width=True):
                            _wl_items.pop(_wi)
                            _save_watchlist(_wl_items)
                            st.rerun()

            if st.button("Clear All", type="secondary", key="wl_clear_all"):
                _save_watchlist([])
                st.rerun()
