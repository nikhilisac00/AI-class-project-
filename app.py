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

# ── Page config (must be first Streamlit call) ─────────────────────────────────────────
st.set_page_config(
    page_title="AI Alternatives Research Associate",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

sys.path.insert(0, str(Path(__file__).parent))

import agents.data_ingestion as ingestion_agent
import agents.fund_analysis  as analysis_agent
import agents.risk_flagging  as risk_agent
import agents.memo_generation as memo_agent
from tools.pal_client import is_available as pal_available, call_thinkdeep, call_consensus


# ── Sidebar ──────────────────────────────────────────────────────────────────────────────
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
            help="Uses PAL MCP to validate risk flags with a second model. Slower but catches more edge cases.",
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
    st.caption("Data sources: IAPD · SEC EDGAR (ADV XML + 13F) · FRED")
    st.caption("Model: claude-opus-4-6 + extended thinking")
    st.caption("No hallucination — all facts trace to real API responses")


# ── Main ──────────────────────────────────────────────────────────────────────────────
st.title("AI Alternative Investments Research Associate")
st.caption("Autonomous due diligence — from CRD number to IC-ready memo")

st.markdown(
    """
    Enter a fund manager name or CRD number. The system will:
    1. Pull ADV filing data from IAPD / SEC EDGAR (including AUM, fees, and key personnel from ADV XML)
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


# ── Pipeline ────────────────────────────────────────────────────────────────────────────
if run_button:
    if not anthropic_key:
        st.error("Anthropic API key required. Add it in the sidebar.")
        st.stop()
    if not firm_input.strip():
        st.error("Enter a fund name or CRD number.")
        st.stop()

    import anthropic
    client = anthropic.Anthropic(api_key=anthropic_key)

    progress_bar = st.progress(0, text="Starting...")
    status_area  = st.empty()

    raw_data, analysis, risk_report, memo, pal_review = None, None, None, None, None

    try:
        # ── Step 1: Ingest ───────────────────────────────────────────────────────────────
        status_area.info("Step 1/5 — Ingesting data from EDGAR / IAPD / ADV XML / FRED...")
        progress_bar.progress(5, text="Ingesting data...")
        raw_data = ingestion_agent.run(firm_input.strip(), fred_api_key=fred_key or None)
        progress_bar.progress(30, text="Data ingestion complete")

        if raw_data.get("errors"):
            st.warning("Ingestion warnings: " + " | ".join(raw_data["errors"]))

        # ── Step 2: Analyze ──────────────────────────────────────────────────────────────
        status_area.info("Step 2/5 — Running fund analysis (Claude + extended thinking)...")
        progress_bar.progress(35, text="Analyzing...")
        analysis = analysis_agent.run(raw_data, client)
        progress_bar.progress(55, text="Fund analysis complete")

        # ── Step 3: Risk flags ──────────────────────────────────────────────────────────
        status_area.info("Step 3/5 — Flagging risks (Claude + extended thinking)...")
        progress_bar.progress(60, text="Flagging risks...")
        risk_report = risk_agent.run(analysis, raw_data, client)
        progress_bar.progress(75, text="Risk flagging complete")

        # ── PAL consensus (optional) ────────────────────────────────────────────────────
        if use_pal and pal_status:
            status_area.info("PAL — Running multi-model consensus validation...")
            progress_bar.progress(77, text="PAL consensus review...")
            pal_review = call_consensus(
                question="Validate these risk flags for an LP reviewing this investment manager. Are there gaps or overstatements?",
                content=json.dumps(risk_report, indent=2, default=str),
            )
            progress_bar.progress(85, text="PAL consensus complete")

        # ── Step 4: Memo ───────────────────────────────────────────────────────────────
        status_area.info("Step 4/5 — Generating DD memo (Claude + extended thinking)...")
        progress_bar.progress(87, text="Generating memo...")
        memo = memo_agent.run(analysis, risk_report, raw_data, client)
        progress_bar.progress(100, text="Done")
        status_area.success("Analysis complete.")

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.exception(e)
        st.stop()

    # ── Save outputs ────────────────────────────────────────────────────────────────────
    firm_name = (
        (analysis or {}).get("firm_overview", {}).get("name")
        or firm_input.strip()
    )
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in firm_name)[:40]
    out_dir   = Path(output_dir)
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

    # ──────────────────────────────────────────────────────────────────────────────
    # FUND SNAPSHOT — key metrics from real data sources + risk tier
    # ──────────────────────────────────────────────────────────────────────────────
    st.divider()
    st.subheader(firm_name)

    adv_xml  = (raw_data or {}).get("adv_xml_data", {})
    overview = (analysis  or {}).get("firm_overview", {})
    tf       = adv_xml.get("thirteenf", {})
    disclosures = adv_xml.get("disclosures", [])
    brochure    = adv_xml.get("brochure", {})

    # 13F portfolio value (real filed data — proxy AUM for equity managers)
    portfolio_val = tf.get("portfolio_value_fmt")
    portfolio_note = tf.get("note", "")

    # Fallback fields from Claude analysis
    clients   = overview.get("num_clients")
    employees = overview.get("num_employees")
    num_ia    = overview.get("num_investment_advisers")
    fee_types = (analysis or {}).get("fee_structure", {}).get("fee_types", [])
    personnel = []  # Not available from free APIs
    tier      = (risk_report or {}).get("overall_risk_tier", "UNKNOWN")
    tier_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(tier, "⚪")

    # ─ Key metric cards ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("13F Portfolio Value", portfolio_val or "N/A")
    c2.metric("Holdings Count",      str(tf.get("holdings_count")) if tf.get("holdings_count") else "—")
    c3.metric("Clients",             str(clients)  if clients   else "—")
    c4.metric("Employees",           str(employees) if employees else "—")
    c5.metric("Risk Tier",           f"{tier_icon} {tier}")

    # ─ Fee types ────────────────────────────────────────────────────────────────────────
    if fee_types:
        st.markdown(
            "**Fee Structure:** " + " ".join(f"`{f}`" for f in fee_types)
        )

    # ─ EDGAR source info ───────────────────────────────────────────────────────────
    # 13F source link
    if tf.get("accession") and tf.get("cik"):
        acc_clean = tf["accession"].replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{tf['cik']}"
            f"/{acc_clean}/{tf['accession']}-index.htm"
        )
        st.caption(
            f"Source: [EDGAR 13F-HR filing]({filing_url}) "
            f"({tf.get('filing_date', '')}). "
            f"{portfolio_note}"
        )
    else:
        st.caption((raw_data or {}).get("adv_xml_data", {}).get(
            "aum_note", "Regulatory AUM not available via free API."))

    if brochure.get("brochure_name"):
        st.caption(
            f"ADV Part 2A: **{brochure['brochure_name']}** "
            f"(filed {brochure.get('brochure_date', '')}). "
            "PDF available at adviserinfo.sec.gov"
        )

    if disclosures:
        import pandas as pd
        with st.expander(f"Disclosure Events ({len(disclosures)}) from IAPD", expanded=False):
            df_d = pd.DataFrame([{
                "Type":        d.get("type", ""),
                "Date":        d.get("date") or "—",
                "Description": d.get("description") or "—",
                "Resolution":  d.get("resolution") or "—",
            } for d in disclosures])
            st.dataframe(df_d, use_container_width=True, hide_index=True)
    elif (raw_data or {}).get("adv_summary", {}).get("has_disclosures"):
        st.warning("IAPD indicates this firm has disclosures. Check adviserinfo.sec.gov for details.")

    # ── Results tabs ────────────────────────────────────────────────────────────────────
    st.divider()
    tab_risk, tab_memo, tab_pal, tab_raw = st.tabs([
        "Risk Dashboard", "DD Memo", "PAL Consensus", "Raw Data",
    ])

    # ─ Risk Dashboard ─────────────────────────────────────────────────────────────────
    with tab_risk:
        if risk_report:
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

    # ─ DD Memo ─────────────────────────────────────────────────────────────────────────
    with tab_memo:
        if memo:
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button(
                    label="Download Memo (.md)",
                    data=memo,
                    file_name=f"{safe_name}_DD_MEMO.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with col_dl2:
                if raw_data and analysis and risk_report:
                    bundle = json.dumps(
                        {"raw_data": raw_data, "analysis": analysis, "risk_report": risk_report},
                        indent=2, default=str,
                    )
                    st.download_button(
                        label="Download JSON Bundle",
                        data=bundle,
                        file_name=f"{safe_name}_bundle.json",
                        mime="application/json",
                        use_container_width=True,
                    )
            st.divider()
            st.markdown(memo)
        else:
            st.warning("Memo not generated.")

    # ─ PAL Consensus ───────────────────────────────────────────────────────────────
    with tab_pal:
        if pal_review:
            st.subheader("PAL Multi-Model Consensus Review")
            st.markdown(pal_review)
        elif use_pal and not pal_status:
            st.info("PAL MCP server not available in this environment.")
        else:
            st.info("Enable 'Multi-Model Consensus' in the sidebar to run PAL validation.")

    # ─ Raw Data ─────────────────────────────────────────────────────────────────────
    with tab_raw:
        if raw_data:
            with st.expander("ADV XML Data (EDGAR)", expanded=True):
                st.json(raw_data.get("adv_xml_data", {}))
            with st.expander("IAPD ADV Summary"):
                st.json(raw_data.get("adv_summary", {}))
            with st.expander("13F Filings"):
                st.json(raw_data.get("filings_13f", []))
            with st.expander("FRED Macro Context"):
                st.json(raw_data.get("market_context", {}))

        if analysis:
            with st.expander("Structured Analysis (Claude)"):
                st.json(analysis)
