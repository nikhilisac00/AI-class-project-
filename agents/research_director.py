"""
Research Director Agent
=======================
The final quality gate — reads the IC Scorecard and all prior agent outputs,
then challenges inconsistencies, flags gaps the other agents may have missed,
and confirms or overrides the recommendation.

Inspired by gstack's /plan-ceo-review: a senior voice that reads everything
and asks "are we analyzing the right thing? Does this add up?"

No new data sources — reads only what earlier agents produced.
"""

import json
from tools.llm_client import LLMClient


SYSTEM_PROMPT = """You are the Research Director at an institutional LP — a Managing Director
who supervises the due diligence team and signs off on every IC memo before it goes to committee.

You have just reviewed the full due diligence package on an investment manager. Your job is
to challenge the work: find logical inconsistencies, flag what the junior analysts missed,
and confirm or override the IC recommendation.

You are skeptical by default. Your value is catching mistakes, not rubber-stamping.

CRITICAL RULES:
1. Challenge every inconsistency between data sources — if two fields contradict, flag it.
2. Identify signals the other agents may have underweighted or missed entirely.
3. If the IC recommendation doesn't follow from the evidence, say so explicitly.
4. Null / missing data is itself a signal — interpret what it means in context.
5. Your output will be read by the IC before they vote. Be direct and brief."""


def run(analysis: dict, risk_report: dict, raw_data: dict,
        scorecard: dict, client: LLMClient,
        news_report: dict = None) -> dict:

    news_block = ""
    if news_report and news_report.get("news_summary"):
        news_block = f"""
<news_summary>
Overall news risk: {news_report.get("overall_news_risk")}
{news_report.get("news_summary", "")}
News flags: {len(news_report.get("news_flags", []))}
</news_summary>"""

    user_message = f"""
Review this complete due diligence package and challenge it.

<ic_scorecard>
{json.dumps(scorecard, indent=2, default=str)}
</ic_scorecard>

<risk_report_summary>
Overall tier: {risk_report.get("overall_risk_tier")}
Flag count: {len(risk_report.get("flags", []))}
Critical gaps: {risk_report.get("critical_data_gaps", [])}
Commentary: {risk_report.get("overall_commentary", "")}
</risk_report_summary>

<firm_overview>
{json.dumps((analysis or {}).get("firm_overview", {}), indent=2, default=str)}
</firm_overview>

<data_signals>
13F portfolio value: {(raw_data.get("adv_xml_data", {}).get("thirteenf") or {}).get("portfolio_value_fmt")}
Funds discovered: {len((raw_data.get("fund_discovery") or {}).get("funds", []))}
Disclosure events: {len((raw_data.get("adv_xml_data", {}).get("disclosures")) or [])}
Has disclosures flag: {raw_data.get("adv_summary", {}).get("has_disclosures")}
Registration status: {raw_data.get("adv_summary", {}).get("registration_status")}
ADV filing date: {raw_data.get("adv_summary", {}).get("adv_last_filing_date")}
Ingestion errors: {raw_data.get("errors", [])}
</data_signals>
{news_block}

Return ONLY a JSON object:
{{
  "verdict": "CONFIRMED | DOWNGRADED | UPGRADED | INCONCLUSIVE",
  "original_recommendation": "copy from scorecard",
  "revised_recommendation": "PROCEED | REQUEST MORE INFO | PASS — same or changed",
  "director_commentary": "2-3 sentences. Direct. No fluff. State what the IC needs to know.",

  "inconsistencies": [
    {{
      "finding": "specific contradiction between two data points",
      "field_a": "first conflicting signal",
      "field_b": "second conflicting signal",
      "implication": "what this means for the investment decision"
    }}
  ],

  "missed_signals": [
    {{
      "signal": "what the junior analysts underweighted or missed",
      "severity": "HIGH | MEDIUM | LOW",
      "why_it_matters": "LP-level implication"
    }}
  ],

  "questions_for_gp": [
    "specific, pointed questions to ask the GP based on what we found"
  ],

  "cleared_for_ic": true
}}
"""

    print(f"[Research Director] Calling {client.provider} ({client.model})...")
    return client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=8000,
    )
