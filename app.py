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
    initial_sidebar_state="expanded",
)

sys.path.insert(0, str(Path(__file__).parent))

import agents.data_ingestion  as ingestion_agent
import agents.fund_analysis   as analysis_agent
import agents.risk_flagging   as risk_agent
import agents.memo_generation as memo_agent
from tools.llm_client import make_client
from tools.pal_client  import is_available as pal_available, call_consensus


# ── Helpers ────────────────────────────────────────────────────────────────────

def _badge(label: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 10px;'
        f'border-radius:4px;font-size:0.78rem;font-weight:600">{label}</span>'
    )

def _sev_color(sev: str) -> str:
    return {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}.get(sev, "#7f8c8d")

def _tier_color(tier: str) -> str:
    return {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}.get(tier, "#95a5a6")


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Settings")

    api_key = st.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Required. Get one at console.anthropic.com",
    )
    st.caption("Model: claude-opus-4-6 + extended thinking")

    fred_key = st.text_input(
        "FRED API Key (optional — free)",
        value=os.getenv("FRED_API_KEY", ""),
        type="password",
        help="Free at fred.stlouisfed.org. Adds macro rates/spreads to memo.",
    )

    st.divider()

    use_pal   = False
    pal_status = pal_available()
    if pal_status:
        use_pal = st.toggle(
            "Multi-Model Consensus (PAL)",
            value=False,
            help="Uses PAL MCP to validate risk flags with Gemini-3-Pro.",
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
    st.caption("Sources: IAPD · SEC EDGAR (13F XML) · FRED")
    st.caption("No hallucination — every fact traces to a real API call")


# ── Header ─────────────────────────────────────────────────────────────────────

st.title("AI Alternative Investments Research Associate")
st.caption("Autonomous due diligence — from CRD number to IC-ready memo")

col_search, col_btn = st.columns([4, 1])
with col_search:
    firm_input = st.text_input(
        "Firm",
        placeholder='Firm name or CRD — e.g. "AQR Capital Management" or "149729"',
        label_visibility="collapsed",
    )
with col_btn:
    run_button = st.button("Run Analysis", type="primary", use_container_width=True)

with st.expander("How it works", expanded=False):
    st.markdown(
        """
**Pipeline (5 steps):**
1. **IAPD** — resolve firm name → CRD → ADV registration data
2. **SEC EDGAR** — fetch latest 13F-HR filing, parse portfolio value from XML
3. **FRED** — pull macro context (rates, spreads, VIX)
4. **Claude Opus 4.6** (extended thinking) — analyze, flag risks, generate memo
5. *(optional)* **PAL MCP** — Gemini-3-Pro consensus validation of risk flags

**No hallucination:** `null` is returned for any missing field. Data gaps are surfaced explicitly in the memo.
        """
    )

st.divider()


# ── Run pipeline ───────────────────────────────────────────────────────────────

if run_button:
    if not api_key:
        st.error("Anthropic API key required. Add it in the sidebar.")
        st.stop()
    if not firm_input.strip():
        st.error("Enter a fund name or CRD number.")
        st.stop()

    client = make_client(api_key)

    progress_bar = st.progress(0, text="Starting...")
    status_box   = st.empty()

    raw_data = analysis = risk_report = memo = pal_review = None

    try:
        status_box.info("Step 1/5 — Ingesting: IAPD · EDGAR 13F XML · FRED...")
        progress_bar.progress(5, text="Ingesting...")
        raw_data = ingestion_agent.run(firm_input.strip(), fred_api_key=fred_key or None)
        progress_bar.progress(30, text="Ingestion complete")

        if raw_data.get("errors"):
            st.warning("Ingestion notes: " + " | ".join(raw_data["errors"]))

        status_box.info("Step 2/5 — Fund analysis (Claude + extended thinking)...")
        progress_bar.progress(35, text="Analyzing...")
        analysis = analysis_agent.run(raw_data, client)
        progress_bar.progress(55, text="Analysis complete")

        status_box.info("Step 3/5 — Risk flagging (Claude + extended thinking)...")
        progress_bar.progress(58, text="Flagging risks...")
        risk_report = risk_agent.run(analysis, raw_data, client)
        progress_bar.progress(75, text="Risk flagging complete")

        if use_pal and pal_status:
            status_box.info("PAL — Multi-model consensus (Gemini-3-Pro)...")
            progress_bar.progress(77, text="PAL consensus...")
            pal_review = call_consensus(
                question=(
                    "Validate these LP due diligence risk flags. "
                    "Identify gaps, overstatements, or missing standard diligence items."
                ),
                content=json.dumps(risk_report, indent=2, default=str),
            )
            progress_bar.progress(85, text="PAL complete")

        status_box.info("Step 4/5 — Generating DD memo (Claude + extended thinking)...")
        progress_bar.progress(87, text="Generating memo...")
        memo = memo_agent.run(analysis, risk_report, raw_data, client)
        progress_bar.progress(100, text="Done")
        status_box.success("Analysis complete.")

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.exception(e)
        st.stop()

    # ── Save outputs ──────────────────────────────────────────────────────────
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
    for label, obj in [
        ("raw_data",    raw_data),
        ("analysis",    analysis),
        ("risk_report", risk_report),
    ]:
        if obj:
            (base.parent / f"{base.name}_{label}.json").write_text(
                json.dumps(obj, indent=2, default=str), encoding="utf-8"
            )

    # ── Extract display fields ────────────────────────────────────────────────
    adv     = (raw_data  or {}).get("adv_summary",  {})
    adv_xml = (raw_data  or {}).get("adv_xml_data", {})
    ov      = (analysis  or {}).get("firm_overview", {})
    tf      = adv_xml.get("thirteenf",  {})
    discl   = adv_xml.get("disclosures", [])
    broch   = adv_xml.get("brochure",   {})
    macro   = (raw_data  or {}).get("market_context", {})
    tier    = (risk_report or {}).get("overall_risk_tier", "UNKNOWN")

    # ── ① Firm Identity Header ────────────────────────────────────────────────
    st.subheader(firm_name)

    reg_status = adv.get("registration_status") or ov.get("registration_status")
    reg_color  = "#27ae60" if reg_status == "ACTIVE" else "#e74c3c"
    crd_str    = adv.get("crd_number") or ov.get("crd")
    sec_str    = adv.get("sec_number") or ov.get("sec_number")
    city       = adv.get("city")
    state_str  = adv.get("state")
    adv_date   = adv.get("adv_filing_date")

    identity_parts = []
    if reg_status:
        identity_parts.append(_badge(reg_status, reg_color))
    if adv.get("is_sec_registered"):
        identity_parts.append(_badge("SEC Registered", "#2980b9"))
    if adv.get("is_state_registered"):
        identity_parts.append(_badge("State Registered", "#8e44ad"))

    if identity_parts:
        st.markdown(" ".join(identity_parts), unsafe_allow_html=True)

    meta_parts = []
    if crd_str:  meta_parts.append(f"CRD: **{crd_str}**")
    if sec_str:  meta_parts.append(f"SEC: **{sec_str}**")
    if city and state_str: meta_parts.append(f"**{city}, {state_str}**")
    if adv_date: meta_parts.append(f"Latest ADV: **{adv_date}**")
    if meta_parts:
        st.caption("  ·  ".join(meta_parts))

    notice_states = adv.get("notice_filing_states", [])
    if notice_states:
        st.caption(f"Notice filings in: {', '.join(notice_states)}")

    # ── ② Key Metric Cards ────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "13F Portfolio Value",
        tf.get("portfolio_value_fmt") or "N/A",
        help="Total US public equity holdings from most recent 13F-HR (proxy AUM)",
    )
    c2.metric(
        "Holdings",
        str(tf.get("holdings_count")) if tf.get("holdings_count") else "—",
        help="Distinct equity positions in latest 13F",
    )
    c3.metric(
        "Clients",
        str(ov.get("num_clients")) if ov.get("num_clients") else "—",
    )
    c4.metric(
        "Employees",
        str(ov.get("num_employees")) if ov.get("num_employees") else "—",
    )
    c5.metric(
        "Risk Tier",
        tier,
        help="Overall LP due diligence risk tier from risk flagging agent",
    )

    # ── ③ Source & Brochure Captions ─────────────────────────────────────────
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
        st.caption(
            adv_xml.get("aum_note", "Regulatory AUM not available via free public API.")
        )

    if broch.get("brochure_name"):
        st.caption(
            f"ADV Part 2A: **{broch['brochure_name']}** "
            f"(filed {broch.get('brochure_date', '')}). "
            "PDF at adviserinfo.sec.gov"
        )

    # ── ④ Disclosure Banner ───────────────────────────────────────────────────
    if discl:
        import pandas as pd
        with st.expander(
            f"Disclosure Events ({len(discl)}) — from IAPD", expanded=False
        ):
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

    # ── ⑤ Macro Context Panel ────────────────────────────────────────────────
    if macro:
        st.markdown("---")
        st.caption("**Market Context** (FRED — latest readings)")
        m1, m2, m3, m4, m5 = st.columns(5)
        def _m(series): return macro.get(series, {}).get("latest") or "—"
        m1.metric("Fed Funds",  _m("fed_funds_rate") + "%"  if _m("fed_funds_rate") != "—" else "—")
        m2.metric("10Y Yield",  _m("ten_yr_yield")   + "%"  if _m("ten_yr_yield")   != "—" else "—")
        m3.metric("HY Spread",  _m("hy_spread")             if _m("hy_spread")      != "—" else "—")
        m4.metric("IG Spread",  _m("ig_spread")             if _m("ig_spread")      != "—" else "—")
        m5.metric("VIX",        _m("vix")                   if _m("vix")            != "—" else "—")

    # ── ⑥ Results Tabs ────────────────────────────────────────────────────────
    st.markdown("---")
    tab_risk, tab_memo, tab_pal, tab_raw = st.tabs([
        "Risk Dashboard", "DD Memo", "PAL Consensus", "Raw Data",
    ])

    # ─ Risk Dashboard ──────────────────────────────────────────────────────────
    with tab_risk:
        if risk_report:
            # Risk tier banner
            tier_c = _tier_color(tier)
            st.markdown(
                f'<div style="background:{tier_c};color:#fff;padding:10px 16px;'
                f'border-radius:6px;font-size:1.1rem;font-weight:700;margin-bottom:12px">'
                f'Overall Risk Tier: {tier}</div>',
                unsafe_allow_html=True,
            )

            commentary = risk_report.get("overall_commentary", "")
            if commentary:
                st.info(commentary)

            flags = risk_report.get("flags", [])
            if flags:
                # Sort: HIGH → MEDIUM → LOW
                order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
                flags_sorted = sorted(flags, key=lambda f: order.get(f.get("severity",""), 9))

                st.subheader(f"Risk Flags ({len(flags_sorted)})")
                for f in flags_sorted:
                    sev  = f.get("severity", "")
                    sev_c = _sev_color(sev)
                    label = (
                        f'<span style="background:{sev_c};color:#fff;padding:1px 7px;'
                        f'border-radius:3px;font-size:0.75rem;font-weight:600;margin-right:6px">'
                        f'{sev}</span>'
                        f'[{f.get("category","")}] {f.get("finding","")[:90]}'
                    )
                    with st.expander(label, expanded=(sev == "HIGH")):
                        st.markdown(f"**Finding:** {f.get('finding','')}")
                        st.markdown(f"**Evidence:** {f.get('evidence','')}")
                        st.markdown(f"**LP Action:** {f.get('lp_action','')}")
            else:
                st.success("No risk flags identified from available public data.")

            col_gaps, col_clean = st.columns(2)
            with col_gaps:
                gaps = risk_report.get("critical_data_gaps", [])
                if gaps:
                    st.subheader("Critical Data Gaps")
                    for g in gaps:
                        st.markdown(f"- {g}")
            with col_clean:
                clean = risk_report.get("clean_items", [])
                if clean:
                    st.subheader("Clean Items")
                    for c in clean:
                        st.markdown(f"- {c}")
        else:
            st.warning("Risk report not available.")

    # ─ DD Memo ─────────────────────────────────────────────────────────────────
    with tab_memo:
        if memo:
            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    "Download Memo (.md)",
                    data=memo,
                    file_name=f"{safe_name}_DD_MEMO.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with dl2:
                if raw_data and analysis and risk_report:
                    bundle = json.dumps(
                        {"raw_data": raw_data, "analysis": analysis, "risk_report": risk_report},
                        indent=2, default=str,
                    )
                    st.download_button(
                        "Download JSON Bundle",
                        data=bundle,
                        file_name=f"{safe_name}_bundle.json",
                        mime="application/json",
                        use_container_width=True,
                    )
            st.divider()
            st.markdown(memo)
        else:
            st.warning("Memo not generated.")

    # ─ PAL Consensus ───────────────────────────────────────────────────────────
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

    # ─ Raw Data ────────────────────────────────────────────────────────────────
    with tab_raw:
        if raw_data:
            with st.expander("13F XML Data (EDGAR)", expanded=True):
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
            with st.expander("Structured Analysis (Claude output)"):
                st.json(analysis)
