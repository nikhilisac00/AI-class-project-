"""
Memo Generation Agent
Synthesizes analysis + risk flags into a formatted LP due diligence memo.
"""

import json
from datetime import date
from tools.llm_client import LLMClient


SYSTEM_PROMPT = """You are a senior research associate drafting an investment due diligence memo
for an institutional LP's investment committee.

CRITICAL RULES:
1. This memo will be reviewed by senior investment professionals. Accuracy is paramount.
2. Only include facts that appear in the provided analysis and risk data.
3. Mark every field as "Not Disclosed" or "Data Unavailable" if the source data is null.
4. Never round up, estimate, or paraphrase numerical data — quote exact figures.
5. The memo must be honest about data limitations. Incomplete data is not a reason to fabricate.
6. Write in a professional, direct tone. No marketing language."""


MEMO_TEMPLATE = """
Draft a structured investment due diligence memo with these exact sections:

1. HEADER — Fund/Manager Name, CRD / SEC Number, Date, Analyst: AI Research Associate (Automated),
   Data Sources: IAPD / SEC EDGAR / FRED, Status: DRAFT — For IC Review

2. EXECUTIVE SUMMARY (3-4 sentences) — Core facts only. Risk tier. Key flags. Proceed/pass/more info.

3. FIRM OVERVIEW — AUM, registration status, headquarters, years registered, client count, team size.
   All fields: quote exact values or "Not Disclosed".

4. INVESTMENT TEAM — Key personnel, titles, ownership percentages. Note key person concentration risks.

5. FEE STRUCTURE — Fee types from ADV, minimum account size, any anomalies.

6. REGULATORY & COMPLIANCE — Disclosure history (exact count and types), registration status.

7. RISK FLAGS SUMMARY — Table: Category | Severity | Finding | Recommended Action

8. MACRO CONTEXT — Current rates/spreads as of data pull date. Brief note on fundraising environment.

9. DATA GAPS & LIMITATIONS — Explicit list of material fields not in public data.

10. NEXT STEPS — Specific diligence items. Standard LP asks: audited financials, LPA, reference calls.

11. APPENDIX: DATA QUALITY LOG — Ingestion errors and missing fields.

Use markdown formatting (## headers, | tables |).
Every numerical claim must trace back to the analysis data above.
"""


def run(analysis: dict, risk_report: dict, raw_data: dict, client: LLMClient,
        news_report: dict = None) -> str:
    today = date.today().strftime("%B %d, %Y")

    news_block = ""
    if news_report and news_report.get("findings"):
        news_block = f"""
<news_report>
{json.dumps({
    "news_summary":      news_report.get("news_summary"),
    "overall_news_risk": news_report.get("overall_news_risk"),
    "news_flags":        news_report.get("news_flags", []),
    "sources_consulted": len(news_report.get("sources_consulted", [])),
    "research_rounds":   news_report.get("research_rounds"),
    "coverage_gaps":     news_report.get("coverage_gaps", []),
}, indent=2, default=str)}
</news_report>

Note: Section 2 (Executive Summary) and a new Section 8a (News & Press) should incorporate
news_report findings. Cite source URLs inline. If overall_news_risk is HIGH or MEDIUM,
surface news flags prominently in Section 7 (Risk Flags)."""

    user_message = f"""
Today's date: {today}

<analysis>
{json.dumps(analysis, indent=2, default=str)}
</analysis>

<risk_report>
{json.dumps(risk_report, indent=2, default=str)}
</risk_report>

<data_errors>
{json.dumps(raw_data.get("errors", []), indent=2)}
</data_errors>
{news_block}
{MEMO_TEMPLATE}
"""

    print(f"[Memo Generation] Calling {client.provider} ({client.model})...")
    return client.complete(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=10000,
        thinking_tokens=6000,
    )
