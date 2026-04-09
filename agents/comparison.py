"""
Comparison Agent
=================
Side-by-side comparison of two investment managers for LP due diligence.

Takes analysis, risk reports, and scorecards for two managers and produces
a structured dimension-by-dimension comparison with an overall winner
recommendation.
"""

import json
from tools.llm_client import LLMClient


SYSTEM_PROMPT = """You are a senior analyst at a large institutional LP (endowment or pension).
You specialize in comparative manager evaluation — helping the investment committee choose
between competing allocations.

Your job is to produce an objective, evidence-based side-by-side comparison of two
investment managers across all dimensions that matter for LP due diligence.

CRITICAL RULES:
1. Base every comparison point strictly on the data provided — no assumptions.
2. If data is missing for one manager but not the other, note the asymmetry explicitly.
   Do NOT penalize a manager for missing data unless the gap itself is a red flag.
3. Be specific: cite AUM figures, registration status, risk flags, scores — not vague
   statements like "Manager A is better."
4. The winner for each dimension must be defensible from the evidence.
5. If a dimension is too close to call or data is insufficient, say TIED or
   INSUFFICIENT DATA — don't force a winner.
6. The overall recommendation should reflect which manager is more suitable for
   an institutional LP, not just which has fewer flags."""


def run(
    firm_a_name: str,
    firm_b_name: str,
    analysis_a: dict,
    analysis_b: dict,
    risk_report_a: dict,
    risk_report_b: dict,
    raw_data_a: dict,
    raw_data_b: dict,
    scorecard_a: dict,
    scorecard_b: dict,
    client: LLMClient,
) -> dict:
    """Compare two managers side-by-side.

    Args:
        firm_a_name: Name of first manager.
        firm_b_name: Name of second manager.
        analysis_a/b: Fund analysis output for each manager.
        risk_report_a/b: Risk flagging output for each manager.
        raw_data_a/b: Raw ingestion data for each manager.
        scorecard_a/b: IC scorecard output for each manager.
        client: LLMClient instance.

    Returns:
        Structured comparison dict.
    """
    def _summary(name: str, analysis: dict, risk: dict, raw: dict,
                 scorecard: dict) -> str:
        adv = raw.get("adv_summary", {})
        tf = (raw.get("adv_xml_data", {}).get("thirteenf") or {})
        fd = raw.get("fund_discovery", {})
        return json.dumps({
            "name": name,
            "firm_overview": (analysis or {}).get("firm_overview", {}),
            "registration_status": adv.get("registration_status"),
            "13f_portfolio_value": tf.get("portfolio_value_fmt"),
            "fund_count": len((fd or {}).get("funds", [])),
            "risk_tier": (risk or {}).get("overall_risk_tier"),
            "risk_flag_count": len((risk or {}).get("flags", [])),
            "high_flags": sum(
                1 for f in (risk or {}).get("flags", [])
                if f.get("severity") == "HIGH"
            ),
            "scorecard_recommendation": (scorecard or {}).get("recommendation"),
            "scorecard_confidence": (scorecard or {}).get("confidence"),
            "overall_score": (scorecard or {}).get("overall_score"),
            "scorecard_scores": (scorecard or {}).get("scores", {}),
            "reasons_to_proceed": (scorecard or {}).get("reasons_to_proceed", []),
            "reasons_to_pause": (scorecard or {}).get("reasons_to_pause", []),
            "data_errors": raw.get("errors", []),
        }, indent=2, default=str)

    user_message = f"""
Compare these two investment managers for an institutional LP allocation decision.

<manager_a>
{_summary(firm_a_name, analysis_a, risk_report_a, raw_data_a, scorecard_a)}
</manager_a>

<manager_b>
{_summary(firm_b_name, analysis_b, risk_report_b, raw_data_b, scorecard_b)}
</manager_b>

Return ONLY a JSON object with this schema:

{{
  "manager_a": "{firm_a_name}",
  "manager_b": "{firm_b_name}",

  "dimensions": [
    {{
      "dimension": "Regulatory / Compliance",
      "manager_a_value": "brief factual summary for A",
      "manager_b_value": "brief factual summary for B",
      "winner": "A | B | TIED | INSUFFICIENT DATA",
      "rationale": "why this manager wins on this dimension"
    }},
    {{
      "dimension": "Risk Profile",
      "manager_a_value": "...",
      "manager_b_value": "...",
      "winner": "A | B | TIED | INSUFFICIENT DATA",
      "rationale": "..."
    }},
    {{
      "dimension": "Operational Maturity",
      "manager_a_value": "...",
      "manager_b_value": "...",
      "winner": "A | B | TIED | INSUFFICIENT DATA",
      "rationale": "..."
    }},
    {{
      "dimension": "Fund Structure / Terms",
      "manager_a_value": "...",
      "manager_b_value": "...",
      "winner": "A | B | TIED | INSUFFICIENT DATA",
      "rationale": "..."
    }},
    {{
      "dimension": "Data Transparency",
      "manager_a_value": "...",
      "manager_b_value": "...",
      "winner": "A | B | TIED | INSUFFICIENT DATA",
      "rationale": "..."
    }},
    {{
      "dimension": "IC Readiness",
      "manager_a_value": "...",
      "manager_b_value": "...",
      "winner": "A | B | TIED | INSUFFICIENT DATA",
      "rationale": "..."
    }}
  ],

  "overall_winner": "A | B | TIED",
  "overall_rationale": "2-3 sentences summarizing why one manager is preferable",

  "key_differentiators": [
    "3-5 bullet points on the most important differences"
  ],

  "recommendation": "PREFER A | PREFER B | NO CLEAR PREFERENCE",
  "recommendation_detail": "2-3 sentence recommendation for the IC"
}}
"""

    print(f"[Comparison] Comparing {firm_a_name} vs {firm_b_name}...")
    return client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=5000,
        thinking_tokens=4000,
    )
