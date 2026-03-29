"""
Risk Flagging Agent
Scans structured analysis for red flags an LP due diligence team would care about.
All flags are derived from data — no fabricated risk signals.
"""

import json
from tools.llm_client import LLMClient


SYSTEM_PROMPT = """You are a risk analyst at an institutional LP (endowment/pension/family office).
Your job is to identify red flags and areas requiring follow-up in an investment adviser's profile.

CRITICAL RULES:
1. Flags must cite specific evidence from the provided data. No generic risks.
2. If data is missing/null, flag that as a data gap — not as a risk itself.
3. Use severity levels: HIGH / MEDIUM / LOW based on LP fiduciary standards.
4. Do not invent risks. Do not speculate beyond what the data shows.
5. Keep it factual. IC teams act on these flags."""


def run(analysis: dict, raw_data: dict, client: LLMClient,
        news_report: dict = None) -> dict:
    news_block = ""
    if news_report and news_report.get("findings"):
        news_block = f"""
<news_findings>
{json.dumps({
    "news_summary":      news_report.get("news_summary"),
    "overall_news_risk": news_report.get("overall_news_risk"),
    "news_flags":        news_report.get("news_flags", []),
    "coverage_gaps":     news_report.get("coverage_gaps", []),
}, indent=2, default=str)}
</news_findings>"""

    fund_discovery = raw_data.get("fund_discovery", {})
    fund_block = ""
    if fund_discovery.get("funds"):
        fund_block = f"""
<fund_discovery>
{json.dumps({
    "funds": fund_discovery.get("funds", [])[:15],
    "relying_advisors": fund_discovery.get("relying_advisors", []),
    "errors": fund_discovery.get("errors", []),
}, indent=2, default=str)}
</fund_discovery>

Also flag fund-level risks: vintage concentration, single large fund dominating AUM,
funds with no Form D filing found, offshore domicile concerns, exemption type mismatches."""

    user_message = f"""
Review the following investment adviser analysis and identify risk flags for LP due diligence.

<analysis>
{json.dumps(analysis, indent=2, default=str)}
</analysis>

<raw_data_errors>
{json.dumps(raw_data.get("errors", []), indent=2)}
</raw_data_errors>{news_block}{fund_block}

Return ONLY a JSON object:
{{
  "overall_risk_tier": "HIGH / MEDIUM / LOW — based on flags found",
  "flags": [
    {{
      "category": "one of: Regulatory | Concentration | Key Person | Fee/Structure | Disclosure | Data Gap | Operational | Fund Structure",
      "severity": "HIGH / MEDIUM / LOW",
      "finding": "specific factual observation from the data",
      "evidence": "quote or reference the exact data field/value that supports this",
      "lp_action": "recommended next step for the diligence team"
    }}
  ],
  "clean_items": [
    "list of areas that appear clean based on available data"
  ],
  "critical_data_gaps": [
    "list of fields that are null/missing but would be material to LP decision"
  ],
  "overall_commentary": "2-3 sentence factual summary for IC memo. No fluff."
}}
"""

    print(f"[Risk Flagging] Calling {client.provider} ({client.model})...")
    return client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=6000,
        thinking_tokens=4000,
    )
