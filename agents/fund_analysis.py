"""
Fund Analysis Agent
Takes raw_data from the ingestion agent and produces structured analysis.
Uses Claude with extended thinking to reason over real data.
Never invents numbers — all outputs are grounded in raw_data fields.
"""

import json
import anthropic


SYSTEM_PROMPT = """You are a senior alternatives research analyst at a large institutional LP.
You have been given structured data extracted directly from SEC EDGAR and IAPD filings.

Your job is to produce factual, structured analysis of this investment adviser.

CRITICAL RULES — NO EXCEPTIONS:
1. Only use numbers and facts that appear explicitly in the <data> provided.
2. If a field is null, missing, or not in the data, say "Not disclosed" — never estimate.
3. Do not hallucinate AUM, returns, fees, or personnel details.
4. Flag clearly when data is absent or incomplete.
5. Your analysis informs real investment decisions. Accuracy > completeness.

Output must be valid JSON matching the schema in the user message."""


def run(raw_data: dict, client: anthropic.Anthropic) -> dict:
    """
    Produce structured fund analysis from ingested raw data.

    Args:
        raw_data: Output from data_ingestion.run()
        client:   Anthropic client instance

    Returns:
        analysis dict with structured findings
    """
    adv = raw_data.get("adv_summary", {})
    filings = raw_data.get("filings_13f", [])
    macro = raw_data.get("market_context", {})
    errors = raw_data.get("errors", [])

    user_message = f"""
Analyze the following investment adviser data and return a JSON object.

<data>
{json.dumps(raw_data, indent=2, default=str)}
</data>

Return ONLY a JSON object with this exact schema (use null for any missing field — never invent values):

{{
  "firm_overview": {{
    "name": "string or null",
    "crd": "string or null",
    "sec_number": "string or null",
    "registration_status": "string or null",
    "registration_date": "string or null",
    "headquarters": "string or null",
    "website": "string or null",
    "aum_regulatory": "string or null",
    "num_clients": "number or null",
    "num_employees": "number or null",
    "num_investment_advisers": "number or null"
  }},
  "fee_structure": {{
    "fee_types": ["list of strings from filing or empty list"],
    "min_account_size": "string or null",
    "notes": "string — only reference what is in the data"
  }},
  "key_personnel": [
    {{
      "name": "string",
      "crd": "string or null",
      "titles": ["list"],
      "ownership_pct": "string or null"
    }}
  ],
  "regulatory_disclosures": {{
    "has_disclosures": "boolean or null",
    "disclosure_count": "number or null",
    "disclosure_types": ["list or empty"],
    "assessment": "string — factual summary only"
  }},
  "13f_filings": {{
    "available": "boolean",
    "most_recent": "string or null",
    "count_found": "number",
    "portfolio_value": "string or null — from adv_xml_data.thirteenf.portfolio_value_fmt if present",
    "holdings_count": "number or null — from adv_xml_data.thirteenf.holdings_count if present",
    "period_of_report": "string or null",
    "note": "string — copy adv_xml_data.thirteenf.note verbatim if present"
  }},
  "macro_context_snapshot": {{
    "fed_funds_rate": "string or null",
    "hy_spread": "string or null",
    "ten_yr_yield": "string or null",
    "notes": "1-2 sentences on relevance to alternatives fundraising environment"
  }},
  "data_quality_flags": [
    "list of strings noting any missing, null, or inconsistent fields observed"
  ]
}}
"""

    print("[Fund Analysis] Calling Claude (extended thinking)...")
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={
            "type": "enabled",
            "budget_tokens": 5000,
        },
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract text block (skip thinking blocks)
    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text = block.text.strip()
            break

    # Strip markdown fences if present
    if result_text.startswith("```"):
        lines = result_text.split("\n")
        result_text = "\n".join(lines[1:-1])

    try:
        analysis = json.loads(result_text)
    except json.JSONDecodeError as e:
        print(f"[Fund Analysis] JSON parse error: {e}")
        analysis = {"raw_response": result_text, "parse_error": str(e)}

    return analysis
