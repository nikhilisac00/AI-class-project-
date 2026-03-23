"""
AI Alternative Investments Research Associate — Streamlit UI
============================================================
DRIVER Path A: Python + Streamlit

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

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="AI Alternatives Research Associate",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Add project root to path so agents/ and tools/ are importable
sys.path.insert(0, str(Path(__file__).parent))

import agents.data_ingestion as ingestion_agent
import agents.fund_analysis as analysis_agent
import agents.risk_flagging as risk_agent
import agents.memo_generation as memo_agent
from tools.pal_client import is_available as pal_available, call_thinkdeep, call_consensus


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Settings")

    anthropic_key = st.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Required. Get one at console.anthropic.com",
    )
    fred_key = st.text_input(
        "FRED API Key (optional)",
        value=os.getenv("FRED_API_KEY", ""),
        type="password",
        help="Free at fred.stlouisfed.org. Adds macro context to memo.",
    )

    st.divider()

    use_pal = False
    pal_status = pal_available()
    if pal_status:
        use_pal = st.toggle(
            "Multi-Model Consensus (PAL)",
            value=False,
            help="Uses PAL MCP to validate risk flags with Gemini-3-Pro. Slower but catches more edge cases.",
        )
        st.caption("PAL MCP: connected")
    else:
        st.caption("PAL MCP: not available (optional)")

    st.divider()

    output_dir = st.text_input(
        "Output directory",
        value="./output/memos",
        help="Where to save memo and JSON files",
    )

    st.divider()
    st.caption("Data sources: IAPD · SEC EDGAR · FRED")
    st.caption("Model: claude-opus-4-6 + extended thinking")
    st.caption("No hallucination — all facts trace to real API responses")


# ── Main ───────────────────────────────────────────────────────────────────────
st.title("AI Alternative Investments Research Associate")
st.caption("Autonomous due diligence — from CRD number to IC-ready memo")

st.markdown(
    """
    Enter a fund manager name or CRD number. The system will:
    1. Pull ADV filing data from IAPD / SEC EDGAR
    2. Analyze AUM, team, fees, and registration history
    3. Flag risks using LP due diligence standards
    4. Generate a structured memo ready for IC review
    """
)

col1, col2 = st.columns([3, 1])
with col1:
    firm_input = st.text_input(
        "Fund manager name or CRD number",
        placeholder='e.g. "AQR Capital Management" or "149729"',
        label_visibility="collapsed",
    )
with col2:
    run_button = st.button("Run Analysis", type="primary", use_container_width=True)


# ── Pipeline ───────────────────────────────────────────────────────────────────
if run_button:
    if not anthropic_key:
        st.error("Anthropic API key required. Add it in the sidebar.")
        st.stop()
    if not firm_input.strip():
        st.error("Enter a fund name or CRD number.")
        st.stop()

    import anthropic
    client = anthropic.Anthropic(api_key=anthropic_key)

    # Progress container
    progress_bar = st.progress(0, text="Starting...")
    status_area = st.empty()

    raw_data, analysis, risk_report, memo, pal_review = None, None, None, None, None

    try:
        # ── Step 1: Ingest ────────────────────────────────────────────────────
        status_area.info("Step 1/4 — Ingesting data from EDGAR / IAPD / FRED...")
        progress_bar.progress(10, text="Ingesting data...")
        raw_data = ingestion_agent.run(firm_input.strip(), fred_api_key=fred_key or None)
        progress_bar.progress(25, text="Data ingestion complete")

        if raw_data.get("errors"):
            st.warning(f"Ingestion warnings: {' | '.join(raw_data['errors'])}")

        # ── Step 2: Analyze ───────────────────────────────────────────────────
        status_area.info("Step 2/4 — Running fund analysis (Claude + extended thinking)...")
        progress_bar.progress(30, text="Analyzing...")
        analysis = analysis_agent.run(raw_data, client)
        progress_bar.progress(50, text="Fund analysis complete")

        # ── Step 3: Risk flags ────────────────────────────────────────────────
        status_area.info("Step 3/4 — Flagging risks (Claude + extended thinking)...")
        progress_bar.progress(55, text="Flagging risks...")
        risk_report = risk_agent.run(analysis, raw_data, client)
        progress_bar.progress(70, text="Risk flagging complete")

        # ── PAL consensus (optional) ──────────────────────────────────────────
        if use_pal and pal_status:
            status_area.info("PAL — Running multi-model consensus validation (Gemini-3-Pro)...")
            progress_bar.progress(72, text="PAL consensus review...")
            pal_review = call_consensus(
                question="Validate these risk flags for an LP reviewing this investment manager. Are there gaps or overstatements?",
                content=json.dumps(risk_report, indent=2, default=str),
            )
            progress_bar.progress(80, text="PAL consensus complete")

        # ── Step 4: Memo ──────────────────────────────────────────────────────
        status_area.info("Step 4/4 — Generating DD memo (Claude + extended thinking)...")
        progress_bar.progress(82, text="Generating memo...")
        memo = memo_agent.run(analysis, risk_report, raw_data, client)
        progress_bar.progress(100, text="Done")
        status_area.success("Analysis complete.")

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.exception(e)
        st.stop()

    # ── Save outputs ──────────────────────────────────────────────────────────
    firm_name = (
        (analysis or {}).get("firm_overview", {}).get("name")
        or firm_input.strip()
    )
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in firm_name)[:40]
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{ts}_{safe_name}"

    memo_path = base.parent / f"{base.name}_DD_MEMO.md"
    if memo:
        memo_path.write_text(memo, encoding="utf-8")
    if raw_data:
        (base.parent / f"{base.name}_raw_data.json").write_text(
            json.dumps(raw_data, indent=2, default=str), encoding="utf-8"
        )
    if analysis:
        (base.parent / f"{base.name}_analysis.json").write_text(
            json.dumps(analysis, indent=2, default=str), encoding="utf-8"
        )
    if risk_report:
        (base.parent / f"{base.name}_risk_report.json").write_text(
            json.dumps(risk_report, indent=2, default=str), encoding="utf-8"
        )

    # ── Results tabs ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f"Results: {firm_name}")

    tab_risk, tab_memo, tab_pal, tab_raw = st.tabs([
        "Risk Dashboard", "DD Memo", "PAL Consensus", "Raw Data"
    ])

    # Risk Dashboard
    with tab_risk:
        if risk_report:
            tier = risk_report.get("overall_risk_tier", "UNKNOWN")
            tier_colors = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
            color = tier_colors.get(tier, "gray")
            st.markdown(
                f"<h3 style='color:{color}'>Overall Risk Tier: {tier}</h3>",
                unsafe_allow_html=True,
            )

            commentary = risk_report.get("overall_commentary", "")
            if commentary:
                st.info(commentary)

            flags = risk_report.get("flags", [])
            if flags:
                st.subheader("Flags")
                for f in flags:
                    sev = f.get("severity", "")
                    sev_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev, "⚪")
                    with st.expander(
                        f"{sev_icon} [{f.get('category','')}] {f.get('finding','')[:80]}"
                    ):
                        st.markdown(f"**Severity:** {sev}")
                        st.markdown(f"**Finding:** {f.get('finding','')}")
                        st.markdown(f"**Evidence:** {f.get('evidence','')}")
                        st.markdown(f"**LP Action:** {f.get('lp_action','')}")
            else:
                st.success("No risk flags identified from available data.")

            gaps = risk_report.get("critical_data_gaps", [])
            if gaps:
                st.subheader("Critical Data Gaps")
                for g in gaps:
                    st.markdown(f"- {g}")

            clean = risk_report.get("clean_items", [])
            if clean:
                st.subheader("Clean Items")
                for c in clean:
                    st.markdown(f"- {c}")
        else:
            st.warning("Risk report not available.")

    # DD Memo
    with tab_memo:
        if memo:
            st.download_button(
                label="Download Memo (.md)",
                data=memo,
                file_name=f"{safe_name}_DD_MEMO.md",
                mime="text/markdown",
            )
            if raw_data and analysis and risk_report:
                bundle = json.dumps(
                    {"raw_data": raw_data, "analysis": analysis, "risk_report": risk_report},
                    indent=2, default=str
                )
                st.download_button(
                    label="Download JSON Bundle",
                    data=bundle,
                    file_name=f"{safe_name}_bundle.json",
                    mime="application/json",
                )
            st.divider()
            st.markdown(memo)
        else:
            st.warning("Memo not generated.")

    # PAL Consensus
    with tab_pal:
        if pal_review:
            st.subheader("PAL Multi-Model Consensus Review")
            st.caption("Validated by Gemini-3-Pro via PAL MCP server")
            st.markdown(pal_review)
        elif use_pal and not pal_status:
            st.info("PAL MCP server not available in this environment.")
        else:
            st.info("Enable 'Multi-Model Consensus' in the sidebar to run PAL validation.")

    # Raw Data
    with tab_raw:
        st.subheader("Raw Ingested Data")
        if raw_data:
            st.json(raw_data)
        else:
            st.warning("No raw data.")

        if analysis:
            st.subheader("Structured Analysis")
            st.json(analysis)
