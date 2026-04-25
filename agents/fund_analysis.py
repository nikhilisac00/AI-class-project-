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
from datetime import date
from tools.llm_client import LLMClient
from tools.schemas import validate_analysis, format_validation_errors

_TODAY = date.today().isoformat()

SYSTEM_PROMPT = f"""You are a senior alternatives research analyst at a large institutional LP
TODAY'S DATE: {_TODAY} — use this for all date recency assessments.
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
    d.pop("market_context", None)  # FRED rates don't affect fund analysis output

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

    # Trim fund news to title + date (drop snippet text); cap at 12 funds
    fund_disc = raw_data.get("fund_discovery") or {}
    funds = fund_disc.get("funds")
    if isinstance(funds, list):
        slimmed_funds = [
            {
                **{k: v for k, v in fund.items() if k != "news"},
                "news": [
                    {"title": n.get("title"), "date": n.get("date")}
                    for n in (fund.get("news") or [])[:2]
                ],
            }
            for fund in funds[:12]
        ]
        d["fund_discovery"] = {**fund_disc, "funds": slimmed_funds[:5]}

    # Trim enforcement to summary fields only (drop verbose order/action text)
    enforcement = raw_data.get("enforcement") or {}
    if enforcement:
        actions = enforcement.get("actions") or []
        d["enforcement"] = {
            **{k: v for k, v in enforcement.items() if k != "actions"},
            "actions": [
                {k: v for k, v in a.items()
                 if k in ("date", "type", "summary", "source")}
                for a in actions[:5]
            ],
        }

    return d


def _data_preamble(slimmed: dict) -> str:
    return (
        "Analyze this investment adviser data. Think carefully before responding.\n\n"
        f"<data>\n{json.dumps(slimmed, indent=2, default=str)}\n</data>\n\n"
        "Context questions:\n"
        "1. Firm type? (PE/hedge fund/VC/credit/multi-strat/long-only) — reason from 13F, Form D, name.\n"
        "2. What does 13F tell us about strategy and scale? Gap vs likely AUM?\n"
        "3. What do Form D funds tell us? Exemption types, fundraising cadence?\n"
        "4. IAPD disclosures — what do they mean for an LP?\n"
        "5. Any internal inconsistencies worth flagging?\n\n"
        "Return ONLY valid JSON. null for any missing field. Keep all narrative fields to 1-2 sentences.\n\n"
    )


def run(raw_data: dict, client: LLMClient) -> dict:
    """Two-pass analysis: each pass targets ≤8000 output tokens to avoid truncation."""
    slimmed = _slim_raw_data(raw_data)
    preamble = _data_preamble(slimmed)

    # ── Pass 1: firm identity, personnel, regulatory, 13F, macro ──────────────
    pass1_schema = """\
{
  "firm_overview": {
    "name": "string or null",
    "crd": "string or null",
    "sec_number": "string or null",
    "registration_status": "string or null",
    "registration_date": "string or null",
    "headquarters": "string or null",
    "website": "string or null",
    "aum_regulatory": "string or null",
    "aum_note": "1 sentence: AUM picture from 13F + Form D",
    "firm_type": "PE | Hedge Fund | VC | Credit | Multi-Strategy | Long-Only | Unknown",
    "firm_type_rationale": "1 sentence",
    "num_clients": null,
    "num_employees": null,
    "num_investment_advisers": null
  },
  "fee_structure": {
    "fee_types": ["list"],
    "min_account_size": "string or null",
    "notes": "1 sentence or null"
  },
  "key_personnel": [
    {"name": "string", "crd": "string or null", "titles": ["list"], "ownership_pct": "string or null"}
  ],
  "regulatory_disclosures": {
    "has_disclosures": true,
    "disclosure_count": 0,
    "disclosure_types": ["list"],
    "severity_assessment": "CLEAN | LOW | MEDIUM | HIGH | CRITICAL",
    "assessment": "1 sentence"
  },
  "13f_filings": {
    "available": true,
    "most_recent": "string or null",
    "count_found": 0,
    "portfolio_value": "string or null",
    "holdings_count": null,
    "period_of_report": "string or null",
    "strategy_signal": "1 sentence",
    "note": "string or null"
  },
  "macro_context_snapshot": {
    "fed_funds_rate": "string or null",
    "hy_spread": "string or null",
    "ten_yr_yield": "string or null",
    "notes": "1 sentence"
  }
}"""

    print(f"[Fund Analysis] Pass 1 — firm profile ({client.model})...")
    pass1 = client.complete_json(
        system=SYSTEM_PROMPT,
        user=preamble + "OUTPUT SCHEMA — respond with ONLY this JSON:\n" + pass1_schema,
        max_tokens=8000,
    )

    # ── Pass 2: fund structure and analyst synthesis ───────────────────────────
    # Keep funds entries minimal (factual fields only) to stay within 8000 tokens
    # even for firms with many registered funds (Point72, Citadel, etc.)
    pass2_schema = """\
{
  "funds_analysis": {
    "total_funds_found": 0,
    "sources_used": ["list"],
    "funds": [
      {
        "name": "string",
        "offering_amount": "string or null",
        "date_of_first_sale": "string or null",
        "exemptions": ["3C.1 / 3C.7 etc."],
        "is_private_fund": true
      }
    ],
    "vintage_summary": "1 sentence",
    "fundraising_pattern": "1 sentence",
    "notes": "1 sentence or null"
  },
  "data_quality_flags": ["specific gap or inconsistency"],
  "analyst_notes": "2 sentences max — highest-signal observations for IC"
}
IMPORTANT: funds array must contain AT MOST 5 entries (most significant only)."""

    print(f"[Fund Analysis] Pass 2 — funds + synthesis ({client.model})...")
    pass2 = client.complete_json(
        system=SYSTEM_PROMPT,
        user=preamble + "OUTPUT SCHEMA — respond with ONLY this JSON:\n" + pass2_schema,
        max_tokens=8000,
    )

    result = {**pass1, **pass2}

    errors = validate_analysis(result)
    if errors:
        print(f"[Fund Analysis] Schema errors ({len(errors)}) — retrying both passes...")
        err_note = format_validation_errors(errors)
        pass1 = client.complete_json(
            system=SYSTEM_PROMPT,
            user=preamble + "OUTPUT SCHEMA — respond with ONLY this JSON:\n"
                 + pass1_schema + err_note,
            max_tokens=8000,
        )
        pass2 = client.complete_json(
            system=SYSTEM_PROMPT,
            user=preamble + "OUTPUT SCHEMA — respond with ONLY this JSON:\n"
                 + pass2_schema + err_note,
            max_tokens=8000,
        )
        result = {**pass1, **pass2}
        remaining = validate_analysis(result)
        if remaining:
            print(f"[Fund Analysis] Retry still has {len(remaining)} errors: {remaining}")

    return result
