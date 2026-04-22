"""
Portfolio Fit Agent
====================
Scores how well a candidate manager fits an LP's existing portfolio.

Evaluates strategy overlap, geographic diversification, vintage exposure,
size fit, and risk budget alignment. Returns a structured fit score with
dimension-level breakdown and actionable recommendation.
"""

import json
from tools.llm_client import LLMClient


SYSTEM_PROMPT = """You are a portfolio construction specialist at a large institutional LP
(endowment or pension fund). You evaluate how well a new manager allocation would fit
within an existing alternatives portfolio.

Your job is to score fit across multiple dimensions — not just strategy match, but also
geographic diversification benefit, vintage year exposure, manager count targets, check
size appropriateness, and remaining risk budget.

CRITICAL RULES:
1. Base every score on the data provided — no assumptions about the manager or portfolio.
2. If data is missing for a dimension, score conservatively and flag the gap.
3. A high fit score means the manager genuinely improves the portfolio — not just that
   the manager is good on its own.
4. Consider both additive value (fills a gap) and overlap risk (redundant exposure).
5. Be specific about what makes the fit good or bad — cite numbers from the portfolio
   and manager data."""


def run(
    firm_name: str,
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    lp_portfolio: dict,
    client: LLMClient,
) -> dict:
    """Score how well this manager fits the LP's current portfolio.

    Args:
        firm_name: Name of the manager being evaluated.
        analysis: Output from fund_analysis agent.
        risk_report: Output from risk_flagging agent.
        raw_data: Raw ingestion data.
        lp_portfolio: LP's current portfolio allocation dict with keys:
            strategies, geographies, num_managers, target_managers,
            typical_check_size_mm, vintage_exposure, risk_budget_remaining.
        client: LLMClient instance.

    Returns:
        Structured fit assessment dict.
    """
    user_message = f"""
Evaluate how well adding **{firm_name}** would fit within this LP's existing
alternatives portfolio.

<manager_analysis>
{json.dumps(analysis, indent=2, default=str)}
</manager_analysis>

<manager_risk_report>
Overall risk tier: {(risk_report or {}).get("overall_risk_tier", "UNKNOWN")}
Flag count: {len((risk_report or {}).get("flags", []))}
Critical gaps: {(risk_report or {}).get("critical_data_gaps", [])}
</manager_risk_report>

<raw_data_summary>
Registration status: {raw_data.get("adv_summary", {}).get("registration_status")}
13F portfolio value: {(raw_data.get("adv_xml_data", {}).get("thirteenf") or {}).get("portfolio_value_fmt")}
Fund count: {len((raw_data.get("fund_discovery") or {}).get("funds", []))}
</raw_data_summary>

<lp_current_portfolio>
{json.dumps(lp_portfolio, indent=2, default=str)}
</lp_current_portfolio>

Score the fit across these dimensions and return ONLY a JSON object:

{{
  "fit_score": "integer 0-100 (overall portfolio fit)",
  "fit_label": "STRONG FIT | GOOD FIT | MODERATE FIT | POOR FIT",
  "recommendation": "ADD | CONSIDER | SKIP",
  "recommendation_detail": "2-3 sentences explaining the portfolio construction case",

  "dimension_scores": {{
    "strategy_fit": {{
      "score": "integer 0-100",
      "rationale": "Does this manager's strategy fill a gap or create overlap?"
    }},
    "geographic_diversification": {{
      "score": "integer 0-100",
      "rationale": "Does the manager improve geographic spread?"
    }},
    "vintage_exposure": {{
      "score": "integer 0-100",
      "rationale": "Does the timing help balance vintage year concentration?"
    }},
    "size_fit": {{
      "score": "integer 0-100",
      "rationale": "Is the fund size appropriate for the LP's check size and portfolio?"
    }},
    "risk_budget_alignment": {{
      "score": "integer 0-100",
      "rationale": "Does the manager's risk profile fit the remaining risk budget?"
    }},
    "manager_count": {{
      "score": "integer 0-100",
      "rationale": "Does adding this manager move toward or away from the target count?"
    }}
  }},

  "fit_gaps": [
    "specific portfolio gaps this manager would fill"
  ],
  "fit_concerns": [
    "specific overlap or concentration risks from adding this manager"
  ]
}}
"""

    print(f"[Portfolio Fit] Calling {client.provider} ({client.model})...")
    return client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=8000,
    )
