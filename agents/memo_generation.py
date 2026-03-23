"""
Memo Generation Agent
Synthesizes analysis + risk flags into a formatted LP due diligence memo.
Output: structured text memo ready for IC review.
"""

import json
import anthropic
from datetime import date


SYSTEM_PROMPT = """You are a senior research associate drafting an investment due diligence memo
for an institutional LP's investment committee.

CRITICAL RULES:
1. This memo will be reviewed by senior investment professionals. Accuracy is paramount.
2. Only include facts that appear in the provided analysis and risk data.
3. Mark every field as "Not Disclosed" or "Data Unavailable" if the source data is null.
4. Never round up, estimate, or paraphrase numerical data — quote exact figures.
5. The memo must be honest about data limitations. Incomplete data is not a reason to fabricate.
6. Write in a professional, direct tone. No marketing language. No hedging filler phrases."""


MEMO_TEMPLATE_INSTRUCTIONS = """
Draft a structured investment due diligence memo with these exact sections:

1. HEADER
   - Fund/Manager Name
   - CRD / SEC Number
   - Date of Analysis
   - Analyst: AI Research Associate (Automated)
   - Data Sources: IAPD / SEC EDGAR / FRED (automated pull)
   - Status: DRAFT — For IC Review

2. EXECUTIVE SUMMARY (3-4 sentences max)
   - Core facts only. Risk tier. Key flags. Recommend proceed/pass/more info.

3. FIRM OVERVIEW
   - AUM, registration status, headquarters, years registered, client count, team size
   - All fields: quote exact values from data or "Not Disclosed"

4. INVESTMENT TEAM
   - Key personnel with titles and ownership percentages
   - Note any key person concentration risks flagged

5. FEE STRUCTURE
   - Fee types from ADV
   - Minimum account size
   - Any anomalies flagged by risk agent

6. REGULATORY & COMPLIANCE
   - Disclosure history (exact count and types from data)
   - Registration status and history
   - Any flags from risk agent

7. RISK FLAGS SUMMARY
   - Table format: Category | Severity | Finding | Recommended Action
   - List all flags from risk report, verbatim where possible

8. MACRO CONTEXT
   - Current rates / spreads as of data pull date
   - Brief note on fundraising environment relevance

9. DATA GAPS & LIMITATIONS
   - Explicit list of material fields not available in public data
   - Note: private fund performance data requires direct GP engagement

10. NEXT STEPS
    - Specific diligence items for follow-up (reference flagged items)
    - Standard LP asks: audited financials, LPA, reference calls, etc.

11. APPENDIX: DATA QUALITY LOG
    - List all ingestion errors and missing fields from raw data
"""


def run(analysis: dict, risk_report: dict, raw_data: dict,
        client: anthropic.Anthropic) -> str:
    """
    Generate the final DD memo as formatted text.

    Args:
        analysis:    Output from fund_analysis.run()
        risk_report: Output from risk_flagging.run()
        raw_data:    Original ingested data
        client:      Anthropic client

    Returns:
        Formatted memo as a string
    """
    today = date.today().strftime("%B %d, %Y")

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

{MEMO_TEMPLATE_INSTRUCTIONS}

Write the complete memo now. Use markdown formatting (headers with ##, tables with |---|).
Every numerical claim must trace back to the analysis data above.
"""

    print("[Memo Generation] Calling Claude (extended thinking)...")
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=10000,
        thinking={
            "type": "enabled",
            "budget_tokens": 6000,
        },
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    memo_text = ""
    for block in response.content:
        if block.type == "text":
            memo_text = block.text.strip()
            break

    return memo_text
