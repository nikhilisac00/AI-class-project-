"""
Risk Flagging Agent — Reasoning Agent
======================================
Uses GPT-4o to reason about risk — not just matching keywords to categories.

An LP risk analyst needs to understand:
- What's a real red flag vs standard industry practice
- Context: a fine from 15 years ago vs an open enforcement action are very different
- Pattern recognition: multiple minor issues = bigger concern than any single one
- What's missing and why that matters
"""

import json
from tools.llm_client import LLMClient
from tools.schemas import validate_risk_report, format_validation_errors


SYSTEM_PROMPT = """You are a risk analyst at a $15B institutional LP (pension fund).
You have reviewed hundreds of alternative investment managers and know what distinguishes
routine issues from genuine red flags.

LP RISK FRAMEWORK — apply this when flagging:

**REGULATORY (severity guide):**
- Criminal disclosure = near-disqualifying for most institutional LPs. Flag HIGH.
- Permanent industry bar = disqualifying. Flag HIGH.
- Recent enforcement action (< 3 years, unresolved) = HIGH regardless of size
- Resolved fine > $1M = MEDIUM (materiality threshold)
- Resolved fine < $1M, > 5 years ago = LOW (note but don't escalate)
- Discrepancy (IAPD says disclosures exist but none found in data) = MEDIUM (needs manual review)
- Multiple small actions = MEDIUM by pattern, even if each is LOW individually

**KEY PERSON / CONCENTRATION:**
- Single principal owns > 50% AND is sole investment decision-maker = HIGH
- Founder approaching retirement age with no documented succession = MEDIUM
- Team < 3 investment professionals for fund > $500M = HIGH
- Key person recently departed (found in news) = HIGH
- All executives joined < 2 years ago = MEDIUM (team instability)

**FUND STRUCTURE:**
- Missing Form D for a firm that clearly raises private capital = MEDIUM
  (could be offshore, could be compliance gap)
- 3C.1 exemption for a fund >$250M = flag (suggests cap table management issues)
- All funds in offshore jurisdictions (Cayman, BVI) with no US registration = MEDIUM
- Fund vintage gap > 5 years = MEDIUM (fundraising hiatus — why?)
- Single fund representing >80% of apparent AUM = concentration risk

**DATA GAPS — know what's normal vs suspicious:**
- Missing AUM = NORMAL (IARD not public) — not a flag
- Missing fee details = NORMAL (ADV Part 2 PDF) — not a flag
- Missing 13F (no public equity) = NORMAL for PE/credit — not a flag
- Missing Form D for a self-described PE firm = suspicious — flag it
- Old ADV filing date (> 12 months) = possible compliance issue — LOW flag
- No brochure found = LOW flag (required for RIA)

**NEWS / REPUTATION:**
- Active litigation with LPs (gate disputes, fraud claims) = HIGH
- SEC subpoena or investigation reported = HIGH
- Key person departure after reported conflict = MEDIUM
- Negative press with factual backing (not opinion) = MEDIUM
- Positive fundraising news = INFO (not a flag, but context)

**WHAT NOT TO FLAG:**
- Null fields where null is expected (AUM, fees from public data)
- Industry-standard practices (management fees, carried interest)
- Small firms being small (not a risk unless size creates operational issues)
- Historical news without material LP implications

CRITICAL RULES:
1. Evidence-based only — cite the exact data field or finding
2. Context matters: resolve date, amount, recency all affect severity
3. One accurate HIGH flag is worth more than five speculative MEDIUM flags
4. If something smells wrong but you can't cite evidence, put it in critical_data_gaps
"""


def run(analysis: dict, raw_data: dict, client: LLMClient,
        news_report: dict = None, scoring_weights: dict = None) -> dict:

    news_block = ""
    if news_report and (news_report.get("news_flags") or news_report.get("news_summary")):
        news_block = f"""
<news_research>
Overall news risk: {news_report.get("overall_news_risk")}
Summary: {news_report.get("news_summary")}

News flags:
{json.dumps(news_report.get("news_flags", []), indent=2, default=str)}

Coverage gaps: {news_report.get("coverage_gaps", [])}
</news_research>"""

    fund_discovery = raw_data.get("fund_discovery", {})
    fund_block = ""
    if fund_discovery.get("funds") or fund_discovery.get("errors"):
        fund_block = f"""
<fund_discovery>
{json.dumps({
    "total_found":      fund_discovery.get("total_found", 0),
    "funds":            fund_discovery.get("funds", [])[:15],
    "relying_advisors": fund_discovery.get("relying_advisors", []),
    "sources_used":     fund_discovery.get("sources_used", []),
    "errors":           fund_discovery.get("errors", []),
}, indent=2, default=str)}
</fund_discovery>"""

    enforcement_block = ""
    enforcement = raw_data.get("enforcement", {})
    if enforcement.get("severity") and enforcement["severity"] != "CLEAN":
        enforcement_block = f"""
<enforcement>
{json.dumps({
    "severity":     enforcement.get("severity"),
    "summary":      enforcement.get("summary"),
    "key_findings": enforcement.get("key_findings", []),
    "red_flags":    enforcement.get("red_flags", []),
}, indent=2, default=str)}
</enforcement>"""

    user_message = f"""
Review this investment adviser and identify LP-material risk flags.
Think carefully about context and severity before flagging anything.

<analysis>
{json.dumps(analysis, indent=2, default=str)}
</analysis>

<raw_data_summary>
Registration status: {raw_data.get("adv_summary", {}).get("registration_status")}
Has disclosures (IAPD flag): {raw_data.get("adv_summary", {}).get("has_disclosures")}
ADV filing date: {raw_data.get("adv_summary", {}).get("adv_filing_date")}
13F portfolio value: {(raw_data.get("adv_xml_data", {}).get("thirteenf") or {}).get("portfolio_value_fmt")}
Ingestion errors: {raw_data.get("errors", [])}
</raw_data_summary>
{fund_block}
{enforcement_block}
{news_block}
{f"""
<lp_scoring_weights>
The LP has specified custom importance weights (1=low, 10=high).
Reflect these in severity decisions:
{json.dumps(scoring_weights, indent=2)}
</lp_scoring_weights>""" if scoring_weights else ""}
Apply the LP risk framework. For each flag:
- What SPECIFICALLY in the data supports this?
- Is this a real flag or just a data gap?
- What severity does it deserve given recency and context?
- What should an LP analyst actually do about it?

Return ONLY a JSON object:
{{
  "overall_risk_tier": "HIGH | MEDIUM | LOW",
  "overall_commentary": "2-3 sentences an IC member needs to know — your highest-signal read",
  "flags": [
    {{
      "category": "Regulatory | Key Person | Fund Structure | Disclosure | Operational | News | Data Gap",
      "severity": "HIGH | MEDIUM | LOW",
      "finding": "specific, factual — cite the data",
      "evidence": "exact field or value from the data",
      "context": "why this is or isn't as bad as it sounds",
      "lp_action": "specific next step for the diligence team"
    }}
  ],
  "clean_items": [
    "areas that appear clean with brief rationale"
  ],
  "critical_data_gaps": [
    "fields that are null/missing AND would materially change the risk assessment if known"
  ]
}}
"""

    print(f"[Risk Flagging] Calling {client.provider} ({client.model})...")
    result = client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=8000,
    )

    errors = validate_risk_report(result)
    if errors:
        print(f"[Risk Flagging] Schema validation failed ({len(errors)} errors) — retrying...")
        retry_message = user_message + format_validation_errors(errors)
        result = client.complete_json(
            system=SYSTEM_PROMPT,
            user=retry_message,
            max_tokens=6000,
        )
        remaining = validate_risk_report(result)
        if remaining:
            print(f"[Risk Flagging] Retry still has {len(remaining)} schema errors: {remaining}")

    return result
