"""
Fund Analysis Agent — Reasoning Agent
======================================
Uses GPT-4o to reason through what the data means before producing
structured output — not just pattern-matching fields to schema.

The reasoning step works through:
- What type of firm this is (PE, hedge, VC, multi-strat, credit) and what that implies
- What the 13F holdings tell us about the actual investment strategy
- What Form D exemptions (3C.1 vs 3C.7) mean for LP suitability
- What IAPD disclosure flags actually indicate
- Whether the data picture is internally consistent
"""

import json
from tools.llm_client import LLMClient
from tools.schemas import validate_analysis, format_validation_errors


SYSTEM_PROMPT = """You are a senior alternatives research analyst at a large institutional LP
(university endowment, $10B+ AUM). You have 15+ years of experience evaluating hedge funds,
private equity, and credit managers for institutional investment.

You have been given raw data extracted from public SEC filings (IAPD, EDGAR 13F, Form D, FRED).
Your job is to analyze this data and produce structured, insightful output — not just reformat it.

WHAT YOU SHOULD UNDERSTAND AND APPLY:

**Firm type identification:**
- 13F filers with >$100M US equity = public markets manager (hedge fund, long-only, quant)
- No 13F + Form D with 3C.1/3C.7 = private fund manager (PE, VC, credit)
- Both = multi-strategy or large alternative asset manager
- State-registered only = likely smaller / less sophisticated operation

**Form D exemptions:**
- 3C.1 = max 100 beneficial owners, typically retail-eligible accredited investors
- 3C.7 = qualified purchasers only ($5M+ investable assets), institutional-grade
- 3C.7 funds signal institutional quality; 3C.1 may indicate smaller/retail fundraising
- 06B = Regulation D Rule 506(b) — accredited investors, no general solicitation

**13F holdings interpretation:**
- High holdings count (>200) = diversified / quantitative / index-like
- Low holdings count (<20) = concentrated, high-conviction
- Compare portfolio_value_fmt to regulatory AUM: large gap = significant private AUM
- Quarter-over-quarter changes signal strategy drift or redemptions

**IAPD disclosures — what they mean:**
- Criminal disclosures = near-disqualifying for most institutional LPs
- Regulatory disclosures = FINRA/SEC actions, fines, sanctions — assess severity + recency
- Civil disclosures = lawsuits, arbitration awards — assess size and pattern
- Employment disclosures = terminations for cause — key person red flag

**Registration signals:**
- SEC-registered = manages >$100M or qualifies for federal exemption
- State-only = likely smaller operation
- ACTIVE vs INACTIVE or PENDING are very different

**Data gaps to interpret:**
- Null AUM doesn't mean small — ADV Part 1A is behind IARD auth wall
- No Form D funds doesn't mean no private activity — could use offshore vehicles
- Old ADV filing date (>6 months) = potential compliance issue

**CRITICAL — Date fields:**
- adv_last_filing_date = date the firm last updated its ADV filing (e.g. annual amendment). This is NOT the firm's original registration date.
- firm_registration_date = when the firm first registered (may be null if not in public data).
- Use null for registration_date in your output UNLESS firm_registration_date is explicitly present in the data. NEVER substitute adv_last_filing_date as registration_date.

CRITICAL RULES:
1. Use null for any missing field — never invent or estimate
2. Your analysis informs real investment decisions
3. Be specific: cite the exact data that supports each conclusion
4. Interpret, don't just reformat — explain what the data means, not just what it says
"""


def _slim_raw_data(raw_data: dict) -> dict:
    """
    Trim raw_data before sending to the LLM to stay within token limits.

    Bug #25: replaced copy.deepcopy(raw_data) with a targeted shallow copy
    that only deep-copies the specific nested structures we mutate. This avoids
    allocating a full duplicate of potentially large SEC filing data.

    Removes high-volume fields that add tokens without adding analytical value:
    - search_results (IAPD search hits — not needed by the analyst)
    - Top holdings truncated to 10 (from 25)
    - 13F history trimmed to period/value/qoq only
    - Fund news trimmed to title + date (no snippets)
    - Disclosure details arrays dropped (type/date/description kept)
    """
    # Shallow copy of top-level dict to avoid mutating caller's raw_data
    d = dict(raw_data)

    # Not useful for synthesis
    d.pop("search_results", None)

    # Only deep-copy the sub-dicts we will mutate
    adv_xml = raw_data.get("adv_xml_data") or {}

    # Trim 13F holdings to top 10
    thirteenf = adv_xml.get("thirteenf") or {}
    hb = thirteenf.get("holdings_breakdown") or {}
    if hb.get("top_holdings"):
        thirteenf = dict(thirteenf)
        hb = dict(hb)
        hb["top_holdings"] = hb["top_holdings"][:10]
        thirteenf["holdings_breakdown"] = hb

    # Trim 13F history to essential fields only
    history = adv_xml.get("thirteenf_history")
    slimmed_history = None
    if isinstance(history, list):
        slimmed_history = [
            {
                "period":              q.get("period"),
                "portfolio_value_fmt": q.get("portfolio_value_fmt"),
                "holdings_count":      q.get("holdings_count"),
                "qoq_change_pct":      q.get("qoq_change_pct"),
            }
            for q in history
        ]

    # Drop verbose details arrays from disclosures (keep type/date/description)
    disclosures = adv_xml.get("disclosures")
    slimmed_disclosures = None
    if isinstance(disclosures, list):
        slimmed_disclosures = [
            {k: v for k, v in disc.items() if k != "details"}
            for disc in disclosures
        ]

    # Reassemble adv_xml_data without mutating the original
    slim_adv = dict(adv_xml)
    slim_adv["thirteenf"] = thirteenf
    if slimmed_history is not None:
        slim_adv["thirteenf_history"] = slimmed_history
    if slimmed_disclosures is not None:
        slim_adv["disclosures"] = slimmed_disclosures
    d["adv_xml_data"] = slim_adv

    # Trim fund news to title + date (drop snippet text)
    fund_disc = raw_data.get("fund_discovery") or {}
    funds = fund_disc.get("funds")
    if isinstance(funds, list):
        slimmed_funds = [
            {
                **{k: v for k, v in fund.items() if k != "news"},
                "news": [
                    {"title": n.get("title"), "date": n.get("date")}
                    for n in (fund.get("news") or [])
                ],
            }
            for fund in funds
        ]
        d["fund_discovery"] = {**fund_disc, "funds": slimmed_funds}

    return d


def run(raw_data: dict, client: LLMClient) -> dict:
    slimmed = _slim_raw_data(raw_data)

    user_message = f"""
Analyze this investment adviser data. Think carefully about what it means before responding.

<data>
{json.dumps(slimmed, indent=2, default=str)}
</data>

Work through the following in your analysis:

1. What TYPE of firm is this? (PE, hedge fund, VC, credit, multi-strat, long-only public equity?)
   Reason from: 13F presence, Form D exemptions, firm name, registration details.

2. What does the 13F data tell us about strategy and scale?
   Is there a gap between 13F portfolio value and likely AUM that suggests significant private AUM?

3. What do the Form D funds tell us? What exemption types? What fundraising cadence?
   Are the fund sizes consistent with the firm's apparent scale?

4. What do the IAPD disclosures (if any) actually mean in LP context?

5. Are there any internal inconsistencies in the data that warrant flagging?

Return ONLY a JSON object with this exact schema (null for any missing field):

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
    "aum_note": "your interpretation of AUM picture given 13F + Form D data",
    "firm_type": "your assessment: PE | Hedge Fund | VC | Credit | Multi-Strategy | Long-Only | Unknown",
    "firm_type_rationale": "1-2 sentences explaining what signals led to this classification",
    "num_clients": "number or null",
    "num_employees": "number or null",
    "num_investment_advisers": "number or null"
  }},
  "fee_structure": {{
    "fee_types": ["list from filing"],
    "min_account_size": "string or null",
    "notes": "string"
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
    "disclosure_types": ["list"],
    "severity_assessment": "CLEAN | LOW | MEDIUM | HIGH | CRITICAL",
    "assessment": "your interpretation of what these disclosures mean for an LP"
  }},
  "13f_filings": {{
    "available": "boolean",
    "most_recent": "string or null",
    "count_found": "number",
    "portfolio_value": "string or null",
    "holdings_count": "number or null",
    "period_of_report": "string or null",
    "strategy_signal": "what the holdings count and concentration tell us about strategy",
    "note": "string or null"
  }},
  "macro_context_snapshot": {{
    "fed_funds_rate": "string or null",
    "hy_spread": "string or null",
    "ten_yr_yield": "string or null",
    "notes": "what this rate environment means specifically for this firm type"
  }},
  "funds_analysis": {{
    "total_funds_found": "number or null",
    "sources_used": ["list"],
    "funds": [
      {{
        "name": "string",
        "entity_type": "string or null",
        "offering_amount": "string or null",
        "date_of_first_sale": "string or null",
        "jurisdiction": "string or null",
        "exemptions": ["3C.1 / 3C.7 etc."],
        "is_private_fund": "boolean",
        "exemption_interpretation": "what 3C.1 vs 3C.7 means for this specific fund",
        "edgar_url": "string or null",
        "news_headlines": ["up to 3 headlines"]
      }}
    ],
    "vintage_summary": "what the fund launch dates tell us about fundraising cadence",
    "fundraising_pattern": "your read on the fundraising trajectory",
    "notes": "data gaps or limitations"
  }},
  "data_quality_flags": [
    "specific inconsistencies or gaps that need follow-up"
  ],
  "analyst_notes": "2-3 sentences of your highest-signal observations that the IC should know first"
}}
"""

    print(f"[Fund Analysis] Calling {client.provider} ({client.model})...")
    result = client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=8000,
    )

    errors = validate_analysis(result)
    if errors:
        print(f"[Fund Analysis] Schema validation failed ({len(errors)} errors) — retrying...")
        retry_message = user_message + format_validation_errors(errors)
        result = client.complete_json(
            system=SYSTEM_PROMPT,
            user=retry_message,
            max_tokens=8000,
        )
        remaining = validate_analysis(result)
        if remaining:
            print(f"[Fund Analysis] Retry still has {len(remaining)} schema errors: {remaining}")

    return result
