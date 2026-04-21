"""
IC Scorecard Agent
Synthesizes all prior agent outputs into a single investment committee verdict.
Outputs a structured scorecard: recommendation, confidence, dimension scores,
reasons to proceed/pause, and minimum diligence checklist.

No new data sources — reads only what earlier agents already produced.
"""

import json
from tools.llm_client import LLMClient


SYSTEM_PROMPT = """You are a managing director at a large institutional LP (endowment or pension).
You have reviewed hundreds of alternative investment managers and sat on many IC committees.

Your job is to synthesize a complete due diligence package into a single structured verdict
for the investment committee. This scorecard will be the first thing the IC reads.

CRITICAL RULES:
1. Base every score and finding strictly on the data provided — no assumptions.
2. If data is missing for a dimension, score it LOW and flag the gap explicitly.
3. The recommendation must be defensible from the evidence — no gut-feel calls.
4. Distinguish between "data gap" risk (solvable with more diligence) and "fundamental" risk
   (structural issue that would not change with more information).
5. Minimum diligence items must be specific and actionable, not generic boilerplate."""


def run(analysis: dict, risk_report: dict, raw_data: dict, client: LLMClient,
        news_report: dict = None) -> dict:

    news_block = ""
    if news_report and (news_report.get("findings") or news_report.get("news_summary")):
        news_block = f"""
<news_report>
{json.dumps({
    "news_summary":      news_report.get("news_summary"),
    "overall_news_risk": news_report.get("overall_news_risk"),
    "news_flags":        news_report.get("news_flags", []),
    "coverage_gaps":     news_report.get("coverage_gaps", []),
}, indent=2, default=str)}
</news_report>"""

    user_message = f"""
You have completed full LP due diligence on this investment manager.
Synthesize the package below into an IC scorecard.

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

Return ONLY a JSON object with this exact schema:

{{
  "recommendation": "PROCEED | REQUEST MORE INFO | PASS",
  "confidence": "HIGH | MEDIUM | LOW",
  "confidence_rationale": "1-2 sentences explaining confidence level",
  "recommendation_summary": "2-3 sentence IC-ready justification for the recommendation",

  "scores": {{
    "regulatory_compliance": {{
      "score": "integer 1-10",
      "rationale": "1 sentence citing specific evidence"
    }},
    "data_availability": {{
      "score": "integer 1-10",
      "rationale": "1 sentence — how complete is the public data picture"
    }},
    "key_person_risk": {{
      "score": "integer 1-10",
      "rationale": "1 sentence — concentration, disclosure history, tenure"
    }},
    "fund_structure": {{
      "score": "integer 1-10",
      "rationale": "1 sentence — fund terms, exemptions, LP protections"
    }},
    "news_reputation": {{
      "score": "integer 1-10",
      "rationale": "1 sentence — press coverage, litigation, public profile"
    }},
    "operational_maturity": {{
      "score": "integer 1-10",
      "rationale": "1 sentence — firm age, SEC registration, team stability"
    }}
  }},

  "overall_score": "number 1-10, weighted average of dimension scores",

  "reasons_to_proceed": [
    "3-5 specific, evidence-backed reasons an LP would want to proceed"
  ],
  "reasons_to_pause": [
    "3-5 specific, evidence-backed reasons an LP would hesitate"
  ],

  "minimum_diligence_items": [
    {{
      "item": "specific action required",
      "priority": "MUST HAVE | NICE TO HAVE",
      "why": "why this is needed before committing capital"
    }}
  ],

  "standard_lp_asks": [
    "list of standard documents/calls to request from the GP"
  ],

  "data_coverage_assessment": "HIGH | MEDIUM | LOW — overall quality of public data available",
  "data_coverage_note": "1 sentence on key missing data points"
}}
"""

    print(f"[IC Scorecard] Calling {client.provider} ({client.model})...")
    return client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=8000,
    )
