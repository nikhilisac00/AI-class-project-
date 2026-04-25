"""
Fund Analysis Agent — Agentic RAG
==================================
Uses GPT-4o with a retrieve() tool to pull only the data chunks needed
for each analysis question. This replaces the full-data-dump approach
that caused truncation for large firms (Point72, Bridgewater, Two Sigma).

The agent issues 6-10 targeted retrieve() calls per pass, then produces
structured JSON. Only the relevant chunks enter the context window.

Upgrade path: swap RawDataIndex.search() for embedding cosine similarity
once ADV brochure text is indexed — the tool interface is identical.

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
from tools.rag_index import RawDataIndex
from tools.schemas import validate_analysis, format_validation_errors

_TODAY = date.today().isoformat()

SYSTEM_PROMPT = f"""You are a senior alternatives research analyst at a large institutional LP
TODAY'S DATE: {_TODAY} — use this for all date recency assessments.
(university endowment, $10B+ AUM). You have 15+ years of experience evaluating hedge funds,
private equity, and credit managers for institutional investment.

You have access to a retrieve() tool that searches SEC filing data (IAPD, EDGAR 13F, Form D, FRED).
Issue targeted retrieve() calls to gather the data you need, then produce your structured JSON output.

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

_RETRIEVE_TOOL = {
    "name": "retrieve",
    "description": (
        "Retrieve relevant data chunks from the SEC filing index. "
        "Issue multiple targeted queries to gather all data you need before producing your final answer. "
        "Each call returns up to top_k chunks of raw data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural language search query, e.g. 'fee structure minimum account size', "
                    "'key personnel ownership percentages', '13F holdings count strategy', "
                    "'Form D funds exemptions', 'regulatory disclosures violations'"
                ),
            },
            "top_k": {
                "type": "integer",
                "description": "Number of chunks to return (default 4, max 6)",
                "default": 4,
            },
        },
        "required": ["query"],
    },
}

_PASS1_SCHEMA = """\
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

_PASS2_SCHEMA = """\
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


def _build_pass1_prompt(sources_hint: str, extra: str = "") -> str:
    return (
        f"Analyze this investment adviser for LP due diligence.\n"
        f"Available data sources: {sources_hint}\n\n"
        "Use retrieve() to gather the data you need. Suggested queries:\n"
        "  • \"firm registration AUM employees clients\"\n"
        "  • \"key personnel ownership percentages titles\"\n"
        "  • \"fee structure minimum account size compensation\"\n"
        "  • \"regulatory disclosures violations disciplinary\"\n"
        "  • \"13F portfolio holdings count strategy value\"\n"
        "  • \"macro context rates spreads\"\n\n"
        "After gathering data, respond with ONLY valid JSON matching this schema. "
        "Use null for any missing field. Keep narrative fields to 1-2 sentences.\n\n"
        f"OUTPUT SCHEMA:\n{_PASS1_SCHEMA}"
        + (f"\n\n{extra}" if extra else "")
    )


def _build_pass2_prompt(sources_hint: str, extra: str = "") -> str:
    return (
        f"Analyze this investment adviser's fund structure for LP due diligence.\n"
        f"Available data sources: {sources_hint}\n\n"
        "Use retrieve() to gather the data you need. Suggested queries:\n"
        "  • \"Form D funds exemptions 3C.1 3C.7\"\n"
        "  • \"fund offering amounts first sale dates\"\n"
        "  • \"fund discovery sources relying advisors\"\n"
        "  • \"enforcement actions penalties SEC FINRA\"\n"
        "  • \"data gaps inconsistencies AUM reconciliation\"\n\n"
        "After gathering data, respond with ONLY valid JSON matching this schema. "
        "Use null for any missing field. Keep narrative fields to 1-2 sentences.\n\n"
        f"OUTPUT SCHEMA:\n{_PASS2_SCHEMA}"
        + (f"\n\n{extra}" if extra else "")
    )


def run(raw_data: dict, client: LLMClient) -> dict:
    """Two-pass agentic RAG analysis: each pass issues retrieve() calls, then produces JSON."""
    index = RawDataIndex(raw_data)
    sources_hint = ", ".join(index.available_sources())

    tool_executor = {
        "retrieve": lambda args: index.search(
            args["query"], min(int(args.get("top_k", 4)), 6)
        )
    }

    # ── Pass 1: firm identity, personnel, regulatory, 13F, macro ──────────────
    print(f"[Fund Analysis] Pass 1 — firm profile ({client.model})...")
    pass1 = client.agent_loop_json(
        system=SYSTEM_PROMPT,
        initial_message=_build_pass1_prompt(sources_hint),
        tools=[_RETRIEVE_TOOL],
        tool_executor=tool_executor,
        max_tokens=6000,
        max_iterations=15,
    )

    # ── Pass 2: fund structure and analyst synthesis ───────────────────────────
    print(f"[Fund Analysis] Pass 2 — funds + synthesis ({client.model})...")
    pass2 = client.agent_loop_json(
        system=SYSTEM_PROMPT,
        initial_message=_build_pass2_prompt(sources_hint),
        tools=[_RETRIEVE_TOOL],
        tool_executor=tool_executor,
        max_tokens=6000,
        max_iterations=15,
    )

    result = {**pass1, **pass2}

    errors = validate_analysis(result)
    if errors:
        print(f"[Fund Analysis] Schema errors ({len(errors)}) — retrying both passes...")
        err_note = format_validation_errors(errors)
        pass1 = client.agent_loop_json(
            system=SYSTEM_PROMPT,
            initial_message=_build_pass1_prompt(sources_hint, extra=err_note),
            tools=[_RETRIEVE_TOOL],
            tool_executor=tool_executor,
            max_tokens=6000,
            max_iterations=15,
        )
        pass2 = client.agent_loop_json(
            system=SYSTEM_PROMPT,
            initial_message=_build_pass2_prompt(sources_hint, extra=err_note),
            tools=[_RETRIEVE_TOOL],
            tool_executor=tool_executor,
            max_tokens=6000,
            max_iterations=15,
        )
        result = {**pass1, **pass2}
        remaining = validate_analysis(result)
        if remaining:
            print(f"[Fund Analysis] Retry still has {len(remaining)} errors: {remaining}")

    return result
