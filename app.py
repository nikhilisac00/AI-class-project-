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

import agents.data_ingestion  as ingestion_agent  # noqa: E402
import agents.firm_resolver   as resolver_agent   # noqa: E402
import agents.fund_analysis   as analysis_agent   # noqa: E402
import agents.news_research   as news_agent       # noqa: E402
import agents.risk_flagging   as risk_agent       # noqa: E402
import agents.memo_generation as memo_agent       # noqa: E402
from tools.llm_client import make_client          # noqa: E402
from tools.pal_client  import is_available as pal_available, call_consensus  # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────────────

def _badge(label: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 10px;'
        f'border-radius:4px;font-size:0.78rem;font-weight:600">{label}</span>'
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
    ("confirmed_firm", None),     # dict with crd, firm_name, city, state
    ("user_website",   ""),
    ("candidates",     []),
    ("search_query",   ""),
    ("pipeline_done",  False),
    ("pipeline_result", {}),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Settings")

    api_key = st.text_input(
        "OpenAI API Key",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
        help="Required. Get one at platform.openai.com",
    )
    st.caption("Model: o3 (reasoning mode)")

    fred_key = st.text_input(
        "FRED API Key (optional — free)",
        value=os.getenv("FRED_API_KEY", ""),
        type="password",
        help="Free at fred.stlouisfed.org. Adds macro rates/spreads to memo.",
    )

    tavily_key = st.text_input(
        "Tavily API Key (optional — free tier)",
        value=os.getenv("TAVILY_API_KEY", ""),
        type="password",
        help="Free at tavily.com (1,000 searches/month). Falls back to DuckDuckGo if blank.",
    )

    run_news = st.toggle(
        "Deep News Research",
        value=True,
        help="Karpathy autoresearch loop: iterative web research on the manager.",
    )
    news_rounds = st.slider("Research rounds", min_value=1, max_value=5, value=3) if run_news else 3

    st.divider()

    use_pal    = False
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
    st.caption("Sources: IAPD · SEC EDGAR (13F XML, Form D) · FRED")
    st.caption("No hallucination — every fact traces to a real API call")


# ── Header ───────────────────────────────────────────────────────────────────

st.title("AI Alternative Investments Research Associate")
st.caption("Autonomous LP due diligence — from firm name to IC-ready memo")

with st.expander("How it works", expanded=False):
    st.markdown(
        """
**Pipeline:**
1. **Firm Resolver** — fuzzy search IAPD, confirm the right entity before spending tokens
2. **Data Ingestion** — IAPD ADV detail · EDGAR 13F XML · FRED macro · Form D fund discovery
3. **Fund Discovery** — Form D filings · IAPD relying advisors · web search → fund table
4. **OpenAI o3** (reasoning) — structured analysis → LP risk flags → IC memo
5. *(optional)* **PAL MCP** — Gemini-3-Pro consensus on risk flags

**No hallucination:** `null` for any missing field. All data gaps surfaced explicitly.
        """
    )

st.divider()


# ────────────────────────────────────────────────────────────────────────────
# STEP 1 — Firm Search & Confirmation
# ────────────────────────────────────────────────────────────────────────────

st.subheader("Step 1 — Find Firm")

col_q, col_find = st.columns([4, 1])
with col_q:
    query_input = st.text_input(
        "Firm",
        value=st.session_state.search_query,
        placeholder='Firm name or CRD — e.g. "Apollo Global Management" or "149729"',
        label_visibility="collapsed",
        key="firm_search_input",
    )
with col_find:
    find_btn = st.button("Find Firm", type="secondary", use_container_width=True)

# Trigger search
if find_btn:
    if not query_input.strip():
        st.error("Enter a firm name or CRD to search.")
    else:
        with st.spinner("Searching IAPD..."):
            candidates = resolver_agent.resolve(
                query_input.strip(),
                tavily_key=tavily_key or None,
                max_candidates=5,
            )
        st.session_state.candidates    = candidates
        st.session_state.search_query  = query_input.strip()
        st.session_state.confirmed_firm = None   # reset if re-searching
        st.session_state.pipeline_done  = False
        st.session_state.pipeline_result = {}

# Show candidates
if st.session_state.candidates and not st.session_state.confirmed_firm:
    st.markdown("**Select the correct firm:**")
    for i, c in enumerate(st.session_state.candidates):
        score = c.get("match_score", 0.0)
        sc    = _score_color(score)
        name  = c.get("firm_name", "Unknown")
        crd   = c.get("crd", "")
        city  = c.get("city", "")
        state = c.get("state", "")
        status = c.get("registration_status", "")
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
                meta = []
                if crd:    meta.append(f"CRD: **{crd}**")
                if city and state: meta.append(f"**{city}, {state}**")
                if status: meta.append(status)
                if meta:
                    st.caption("  ·  ".join(meta))
                if website:
                    st.caption(f"[{website}]({website})")
            with btn_col:
                if st.button("Use this firm", key=f"use_{i}", use_container_width=True):
                    st.session_state.confirmed_firm = c
                    st.session_state.pipeline_done  = False
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

st.divider()


# ────────────────────────────────────────────────────────────────────────────
# STEP 2 — Run Analysis (only shown after firm confirmation)
# ────────────────────────────────────────────────────────────────────────────

if st.session_state.confirmed_firm:
    st.subheader("Step 2 — Run Analysis")

    run_button = st.button(
        f"Run Due Diligence on {st.session_state.confirmed_firm.get('firm_name', '')}",
        type="primary",
        use_container_width=True,
        disabled=not api_key,
    )
    if not api_key:
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
    client      = make_client(api_key)

    progress_bar = st.progress(0, text="Starting...")
    status_box   = st.empty()

    raw_data = analysis = risk_report = memo = pal_review = news_report = None

    try:
        total_steps = 4 + (1 if run_news else 0) + (1 if use_pal and pal_status else 0)
        step = [0]
        def _pct(n): return int(n / total_steps * 100)

        status_box.info("Step 1 — Ingesting: IAPD · EDGAR 13F · FRED · Form D...")
        progress_bar.progress(5, text="Ingesting...")
        raw_data = ingestion_agent.run(
            firm_input,
            fred_api_key=fred_key or None,
            website=user_website,
            client=client,
            tavily_key=tavily_key or None,
        )
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text="Ingestion complete")

        fd_count = len((raw_data.get("fund_discovery") or {}).get("funds", []))
        if raw_data.get("errors"):
            st.warning("Ingestion notes: " + " | ".join(raw_data["errors"]))

        status_box.info(f"Step 2 — Fund analysis (o3 reasoning) · {fd_count} funds found...")
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

        status_box.info("Step — Risk flagging (o3 reasoning)...")
        risk_report = risk_agent.run(analysis, raw_data, client, news_report=news_report)
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

        status_box.info("Step — Generating DD memo (o3 reasoning)...")
        memo = memo_agent.run(analysis, risk_report, raw_data, client,
                              news_report=news_report)
        progress_bar.progress(100, text="Done")
        status_box.success("Analysis complete.")

        st.session_state.pipeline_result = dict(
            raw_data=raw_data, analysis=analysis, risk_report=risk_report,
            memo=memo, pal_review=pal_review, news_report=news_report,
            firm_name=firm_name_resolved,
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
    pal_review  = pr["pal_review"]
    news_report = pr["news_report"]
    firm_name   = pr["firm_name"]

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

    # ── Key Metric Cards ──────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(
        "13F Portfolio Value",
        tf.get("portfolio_value_fmt") or "N/A",
        help="Total US public equity holdings from most recent 13F-HR",
    )
    c2.metric(
        "Holdings",
        str(tf.get("holdings_count")) if tf.get("holdings_count") else "—",
    )
    c3.metric(
        "Funds Found",
        str(fd.get("total_found", 0)),
        help="Private funds discovered via Form D, IAPD, and web search",
    )
    c4.metric(
        "Clients",
        str(ov.get("num_clients")) if ov.get("num_clients") else "—",
    )
    c5.metric(
        "Employees",
        str(ov.get("num_employees")) if ov.get("num_employees") else "—",
    )
    c6.metric(
        "Risk Tier",
        tier,
        help="Overall LP due diligence risk tier",
    )

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

    # ── Results Tabs ──────────────────────────────────────────────────────
    st.markdown("---")
    tab_risk, tab_funds, tab_news, tab_memo, tab_pal, tab_raw = st.tabs([
        "Risk Dashboard", "Funds", "News Research", "DD Memo", "PAL Consensus", "Raw Data",
    ])

    # ─ Risk Dashboard ────────────────────────────────────────────────────
    with tab_risk:
        if risk_report:
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
                order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
                flags_sorted = sorted(flags, key=lambda f: order.get(f.get("severity", ""), 9))
                st.subheader(f"Risk Flags ({len(flags_sorted)})")
                for f in flags_sorted:
                    sev   = f.get("severity", "")
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
                    for g in gaps: st.markdown(f"- {g}")
            with col_clean:
                clean = risk_report.get("clean_items", [])
                if clean:
                    st.subheader("Clean Items")
                    for c in clean: st.markdown(f"- {c}")
        else:
            st.warning("Risk report not available.")

    # ─ Funds Tab ─────────────────────────────────────────────────────────
    with tab_funds:
        funds_list = fd.get("funds", [])
        ra_list    = fd.get("relying_advisors", [])
        sources    = fd.get("sources_used", [])
        fd_errors  = fd.get("errors", [])

        if funds_list or ra_list:
            # Summary
            src_str = ", ".join(sources) if sources else "none"
            st.caption(f"Sources: {src_str}  ·  Total funds discovered: {fd.get('total_found', 0)}")

            if fd_errors:
                with st.expander("Discovery notes"):
                    for e in fd_errors: st.caption(e)

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
                for e in fd_errors: st.caption(e)

    # ─ News Research ─────────────────────────────────────────────────────
    with tab_news:
        if news_report and (news_report.get("findings") or news_report.get("news_summary")):
            nr           = news_report
            overall_nr   = nr.get("overall_news_risk", "UNKNOWN")
            nr_color     = _tier_color(overall_nr)

            st.markdown(
                f'<div style="background:{nr_color};color:#fff;padding:10px 16px;'
                f'border-radius:6px;font-size:1.1rem;font-weight:700;margin-bottom:12px">'
                f'News Risk: {overall_nr}</div>',
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
                st.subheader(f"News Flags ({len(flags_sorted)})")
                for f in flags_sorted:
                    sev   = f.get("severity", "INFO")
                    sev_c = _sev_color(sev) if sev != "INFO" else "#7f8c8d"
                    label = (
                        f'<span style="background:{sev_c};color:#fff;padding:1px 7px;'
                        f'border-radius:3px;font-size:0.75rem;font-weight:600;margin-right:6px">'
                        f'{sev}</span>'
                        f'[{f.get("category","")}] {f.get("finding","")[:90]}'
                    )
                    with st.expander(label, expanded=(sev == "HIGH")):
                        st.markdown(f"**Finding:** {f.get('finding', '')}")
                        if f.get("source_url"):
                            st.markdown(f"**Source:** [{f['source_url']}]({f['source_url']})")
                        if f.get("date"):
                            st.markdown(f"**Date:** {f['date']}")
                        if f.get("lp_action"):
                            st.markdown(f"**LP Action:** {f['lp_action']}")
            else:
                st.success("No material news flags identified.")

            if nr.get("coverage_gaps"):
                with st.expander("Coverage Gaps"):
                    for g in nr["coverage_gaps"]: st.markdown(f"- {g}")

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
                    for q in nr["queries_used"]: st.markdown(f"- `{q}`")

            if nr.get("errors"):
                with st.expander("Errors / Warnings"):
                    for e in nr["errors"]: st.warning(e)

        elif not run_news:
            st.info("News research was skipped. Enable **Deep News Research** in the sidebar.")
        else:
            st.warning("News research produced no results.")

    # ─ DD Memo ───────────────────────────────────────────────────────────
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
            with st.expander("Structured Analysis (o3 output)"):
                st.json(analysis)
