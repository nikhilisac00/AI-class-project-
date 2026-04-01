"""
Fund Analysis Agent
Takes raw_data from the ingestion agent and produces structured analysis.
Uses LLMClient (Anthropic Claude) — never invents numbers.
"""

import json
from tools.llm_client import LLMClient


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


def run(raw_data: dict, client: LLMClient) -> dict:
    user_message = f"""
Analyze the following investment adviser data and return a JSON object.
Note: raw_data.fund_discovery already contains all fund discovery results.

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
  "funds_analysis": {{
    "total_funds_found": "number or null",
    "sources_used": ["list of source strings"],
    "funds": [
      {{
        "name": "fund name",
        "entity_type": "string or null",
        "offering_amount": "formatted string e.g. $2.5B or null",
        "date_of_first_sale": "string or null",
        "jurisdiction": "string or null",
        "exemptions": ["3C.1 / 3C.7 etc."],
        "is_private_fund": "boolean",
        "edgar_url": "string or null",
        "news_headlines": ["up to 3 headline strings from fund news — only if in data"]
      }}
    ],
    "vintage_summary": "1-2 sentences on fund vintage years and fundraising cadence — only if data supports it",
    "notes": "any data gaps or limitations"
  }},
  "data_quality_flags": [
    "list of strings noting any missing, null, or inconsistent fields observed"
  ]
}}
"""

    print(f"[Fund Analysis] Calling {client.provider} ({client.model})...")
    return client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=8000,
        thinking_tokens=5000,
    )
