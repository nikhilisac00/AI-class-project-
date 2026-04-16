"""
Memo Generation Agent — Dedicated IC Memo Writer
=================================================
This is the ONLY agent that produces narrative prose. All upstream agents
(fund_analysis, risk_flagging, news_research) produce structured JSON only.
This agent receives all structured outputs and synthesizes them into a single,
coherent IC-ready due diligence memo.

Inputs (all structured JSON):
  - analysis     : fund_analysis output (firm overview, fees, personnel, 13F, funds)
  - risk_report  : risk_flagging output (flags, tiers, gaps, clean items)
  - raw_data     : data_ingestion output (ADV summary, FRED macro, fund discovery)
  - news_report  : news_research output (news flags, findings, coverage gaps)

Output: a single markdown string — the complete IC memo
"""

import json
from datetime import date
from tools.llm_client import LLMClient


SYSTEM_PROMPT = """You are a senior research associate at an institutional LP (endowment / pension / family office).
You are writing a formal Investment Committee due diligence memo based on structured data provided to you.

YOUR ROLE IN THE PIPELINE:
You are the ONLY agent that writes narrative text. All upstream agents have already extracted and
structured the data. Your job is synthesis and professional writing — NOT further analysis.

CRITICAL RULES — NO EXCEPTIONS:
1. Every fact, number, name, or date must come directly from the provided structured data.
2. If a field is null or absent in the data, write "Not Disclosed" — never estimate or infer.
3. Do not add qualitative judgments beyond what the risk_report already concluded.
4. Do not repeat the same information across multiple sections.
5. Write for a senior investment professional audience: direct, precise, no fluff.
6. Cite source URLs for news findings inline (e.g. [Reuters, 2024-11-03]).
7. Tables must be properly formatted markdown. Use | col | col | format."""


def _build_context(
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    news_report: dict,
    today: str,
) -> str:
    """Assemble all structured inputs into a single context block for the writer."""

    adv = raw_data.get("adv_summary", {})
    fd  = raw_data.get("fund_discovery", {})

    # Keep fund discovery slim — just what the writer needs
    fd_slim = {
        "total_found":      fd.get("total_found", 0),
        "sources_used":     fd.get("sources_used", []),
        "errors":           fd.get("errors", []),
        "relying_advisors": fd.get("relying_advisors", []),
        "funds": [
            {
                "name":               f.get("name"),
                "offering_amount":    f.get("offering_amount"),
                "date_of_first_sale": f.get("date_of_first_sale"),
                "entity_type":        f.get("entity_type"),
                "exemptions":         f.get("exemptions", []),
                "is_private_fund":    f.get("is_private_fund"),
                "jurisdiction":       f.get("jurisdiction"),
                "edgar_url":          f.get("edgar_url"),
                "source":             f.get("source"),
                "news": [
                    {"title": n.get("title"), "url": n.get("url"), "date": n.get("date")}
                    for n in (f.get("news") or [])[:3]
                ],
            }
            for f in fd.get("funds", [])[:20]
        ],
    }

    # Keep news report slim
    nr_slim = None
    if news_report and (news_report.get("news_flags") or news_report.get("news_summary")):
        nr_slim = {
            "overall_news_risk": news_report.get("overall_news_risk"),
            "news_summary":      news_report.get("news_summary"),
            "research_rounds":   news_report.get("research_rounds"),
            "total_sources":     news_report.get("total_sources"),
            "news_flags":        news_report.get("news_flags", []),
            "coverage_gaps":     news_report.get("coverage_gaps", []),
        }

    blocks = [
        f"TODAY'S DATE: {today}",
        "",
        "=== FIRM REGISTRATION (IAPD ADV Summary) ===",
        json.dumps(adv, indent=2, default=str),
        "",
        "=== STRUCTURED ANALYSIS (fund_analysis agent) ===",
        json.dumps(analysis, indent=2, default=str),
        "",
        "=== RISK REPORT (risk_flagging agent) ===",
        json.dumps(risk_report, indent=2, default=str),
        "",
        "=== FUND DISCOVERY (Form D + IAPD + web) ===",
        json.dumps(fd_slim, indent=2, default=str),
        "",
        "=== MACRO CONTEXT (FRED) ===",
        json.dumps(raw_data.get("market_context", {}), indent=2, default=str),
        "",
        "=== INGESTION ERRORS (data gaps) ===",
        json.dumps(raw_data.get("errors", []), indent=2),
    ]

    if nr_slim:
        blocks += [
            "",
            "=== NEWS RESEARCH (news_research agent) ===",
            json.dumps(nr_slim, indent=2, default=str),
        ]

    return "\n".join(blocks)


MEMO_INSTRUCTIONS = """
Write a complete Investment Committee Due Diligence Memo using ONLY the structured data above.
Follow this exact structure:

---

# DUE DILIGENCE MEMO — [FIRM NAME]

**Prepared by:** AI Research Associate (Automated)
**Date:** [TODAY'S DATE]
**Data Sources:** IAPD · SEC EDGAR (13F-HR, Form D) · FRED
**Status:** DRAFT — For IC Review Only

---

## 1. EXECUTIVE SUMMARY

3-4 sentences covering: what the firm does, registration status, key risk tier, most material flag,
and recommendation (Proceed to full diligence / Request more information / Pass).
If news risk is HIGH or MEDIUM, mention it here.

---

## 2. FIRM OVERVIEW

| Field | Value |
|---|---|
| Legal Name | |
| CRD Number | |
| SEC Number | |
| Registration Status | |
| Registration Date | |
| Headquarters | |
| AUM (13F Public Equity) | |
| Number of Clients | |
| Number of Employees | |
| Website | |

*(Use "Not Disclosed" for any null fields — do not omit rows)*

---

## 3. INVESTMENT TEAM

List all key personnel from key_personnel array. For each:
- Name, titles, ownership %
- Note if ownership data unavailable

Flag key person concentration if a single individual holds >25% ownership or is sole principal.

---

## 4. FEE STRUCTURE

Summarize fee types from ADV filing. If fee_types is empty or null, state "Not Disclosed in public filings."
Include minimum account size if available.

---

## 5. REGULATORY & COMPLIANCE

- Registration status and jurisdiction
- Disclosure history: exact count by type (criminal / regulatory / civil / arbitration)
- If has_disclosures is true but disclosure_count is 0, note the discrepancy
- Note if no disclosures found

---

## 6. PRIVATE FUNDS DISCOVERED

If funds were found:

| Fund Name | Vintage | Offering Size | Type | Exemption | Jurisdiction | Source |
|---|---|---|---|---|---|---|

Include a brief vintage/cadence summary below the table.
For each fund with news, add a bullet: "**[Fund Name]:** [headline] ([source, date])"

If no funds found, state clearly: "No private fund filings discovered via [sources attempted]. [reason from errors]."

---

## 7. NEWS & PRESS COVERAGE

*(Only include if news_report is present)*

**Overall News Risk: [level]** — [N] flags across [N] rounds of research, [N] sources consulted.

[news_summary text verbatim]

For each news_flag with severity HIGH or MEDIUM:
- **[severity] — [category]:** [finding] ([source_url, date]) → *LP Action: [lp_action]*

Coverage gaps (topics not found in public press): [list]

If no news_report, write: "News research not run for this analysis."

---

## 8. RISK FLAGS SUMMARY

**Overall Risk Tier: [tier]**

[overall_commentary verbatim from risk_report]

| Category | Severity | Finding | Recommended Action |
|---|---|---|---|

*(Sort: HIGH first, then MEDIUM, then LOW)*

---

## 9. MACRO CONTEXT

| Indicator | Latest Value |
|---|---|
| Fed Funds Rate | |
| 10Y Treasury Yield | |
| HY Spread | |
| IG Spread | |
| VIX | |

1-2 sentences on what the current rate/spread environment means for alternatives fundraising.

---

## 10. DATA GAPS & LIMITATIONS

Explicit list of material fields not available via public data:
- ADV Part 1A regulatory AUM (not accessible via public API)
- ADV Part 1A private fund schedule (IARD access restricted)
- Fee details (ADV Part 2 PDF, not machine-readable)
- Audited fund financials (private)
- [any other null/missing fields from data_quality_flags or ingestion errors]

---

## 11. NEXT STEPS

Standard LP due diligence asks:
- [ ] Request audited financial statements for last 3 years
- [ ] Obtain Limited Partnership Agreement(s)
- [ ] Conduct reference calls with existing LPs
- [ ] Review ADV Part 2A brochure (adviserinfo.sec.gov)
- [ ] Verify key person arrangements and succession planning
- [add any firm-specific items suggested by risk flags]

---

## APPENDIX: DATA QUALITY LOG

List all ingestion errors and null fields verbatim from the data.
"""


def run(
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    client: LLMClient,
    news_report: dict = None,
) -> str:
    today = date.today().strftime("%B %d, %Y")

    context = _build_context(analysis, risk_report, raw_data, news_report, today)

    user_message = f"""
<structured_data>
{context}
</structured_data>

{MEMO_INSTRUCTIONS}
"""

    print(f"[Memo Writer] Calling {client.provider} ({client.model})...")
    return client.complete(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=12000,
    )
