"""
SEC Enforcement Agent
=====================
Synthesizes enforcement history into a structured LP-grade report.

Sources (via enforcement_client):
  1. IAPD iacontent disclosure arrays (when available from public API)
  2. Web search (Tavily / DuckDuckGo) — primary when IAPD arrays absent,
     always run when has_disclosure_flag=True
  3. EDGAR EFTS — enforcement-adjacent filings (UPLOAD, CORRESP)
  4. EDGAR submissions — ADV-W withdrawal / unusual form type flags

Note on IAPD API: the public endpoint (api.adviserinfo.sec.gov/search/firm/{crd})
returns a lightweight iacontent that omits disclosure arrays. Web search fills this gap.

Output:
  enforcement_data  : raw fetch result from enforcement_client
  summary           : LLM narrative (LP-grade, 3-5 sentences)
  severity          : CLEAN / LOW / MEDIUM / HIGH / CRITICAL
  key_findings      : list of bullet strings
  red_flags         : list of most serious concerns
  sources           : data sources used
  errors            : list of errors
"""

import json
from tools.llm_client import LLMClient
from tools.enforcement_client import fetch_enforcement_data


_SYSTEM = """You are an LP compliance analyst reviewing SEC enforcement history for an investment adviser.

Your job: summarize the enforcement record clearly for an investment committee.

Rules:
1. Base every finding strictly on the provided data — no assumptions or hallucinations.
2. If there are zero structured actions but web results exist, use the web results.
3. Distinguish resolved (historical) vs open/pending actions.
4. Assess materiality: a $50K fine 15 years ago differs from a recent bar or fraud order.
5. Flag patterns of repeat violations — a significant red flag for LPs.
6. Criminal disclosures and industry bars are near-disqualifying for institutional LPs.
7. If the IAPD flag says disclosures exist but no structured data was found, note that
   manual review at adviserinfo.sec.gov is required."""


def run(
    firm_name:           str,
    crd:                 str = None,
    cik:                 str = None,
    iacontent:           dict = None,
    has_disclosure_flag: bool = False,
    tavily_key:          str = None,
    client:              LLMClient = None,
) -> dict:
    """
    Run SEC enforcement deep-dive for an investment adviser.

    Args:
        firm_name           : adviser name
        crd                 : IAPD CRD number
        cik                 : EDGAR CIK (for submissions scan)
        iacontent           : raw IAPD iacontent dict
        has_disclosure_flag : True if IAPD search returned firm_ia_disclosure_fl=Y
        tavily_key          : optional Tavily API key for web search
        client              : LLMClient for narrative synthesis (optional)

    Returns structured enforcement report dict.
    """
    print(f"[Enforcement] Checking regulatory record for '{firm_name}'...")

    report = {
        "enforcement_data": {},
        "summary":          None,
        "severity":         "CLEAN",
        "key_findings":     [],
        "red_flags":        [],
        "sources":          [],
        "errors":           [],
    }

    # ── Fetch raw enforcement data ─────────────────────────────────────────
    try:
        data = fetch_enforcement_data(
            firm_name=firm_name,
            crd=crd,
            cik=cik,
            iacontent=iacontent,
            has_disclosure_flag=has_disclosure_flag,
            tavily_key=tavily_key,
        )
        report["enforcement_data"] = data
        report["sources"]          = data.get("sources_used", [])
        report["errors"].extend(data.get("errors", []))
    except Exception as e:
        report["errors"].append(f"Enforcement data fetch failed: {e}")
        return report

    actions     = data.get("actions", [])
    web_results = data.get("web_results", [])
    high        = data.get("high_count", 0)
    med         = data.get("medium_count", 0)
    total       = data.get("total_actions", 0)
    open_n      = len(data.get("open_actions", []))

    # ── Rule-based severity (from IAPD structured actions) ────────────────
    has_web_hits = len(web_results) > 0

    if total == 0 and not has_disclosure_flag and not has_web_hits:
        report["severity"] = "CLEAN"
    elif high >= 2 or open_n >= 1:
        report["severity"] = "HIGH"
    elif high == 1:
        report["severity"] = "MEDIUM"
    elif med >= 2:
        report["severity"] = "MEDIUM"
    elif total >= 1 or (has_disclosure_flag and has_web_hits):
        report["severity"] = "LOW"
    else:
        report["severity"] = "CLEAN"

    # Upgrade to CRITICAL for criminal / industry bar
    for a in actions:
        combined = " ".join(
            [a.get("action_type", ""), a.get("description", "")]
            + (a.get("sanctions") or [])
        ).lower()
        if a.get("action_type") == "Criminal" or any(
            kw in combined
            for kw in ("criminal", "felony", "fraud", "permanent bar",
                       "industry bar", "barred from", "expulsion")
        ):
            report["severity"] = "CRITICAL"
            break

    # ── LLM narrative synthesis ────────────────────────────────────────────
    has_data = total > 0 or has_web_hits or has_disclosure_flag

    if client and has_data:
        try:
            web_snippets = [
                {"title": r["title"], "url": r["url"], "snippet": r["snippet"][:300]}
                for r in web_results[:6]
            ]
            payload = {
                "iapd_disclosure_flag": has_disclosure_flag,
                "total_iapd_actions":   total,
                "high_count":           high,
                "medium_count":         med,
                "open_actions":         open_n,
                "penalty_total":        data.get("penalty_total_fmt"),
                "iapd_actions":         actions,
                "web_search_results":   web_snippets,
                "edgar_hits":           data.get("edgar_hits", [])[:3],
                "edgar_flags":          data.get("edgar_flags", []),
            }
            user_msg = f"""Firm: {firm_name}   CRD: {crd or "unknown"}

Enforcement record:
{json.dumps(payload, indent=2, default=str)}

Write:
1. summary: concise LP-grade narrative (3-5 sentences). Use web search results
   when IAPD structured actions are absent.
2. key_findings: up to 5 bullet points summarising the record
3. red_flags: list the most serious items (empty list if clean)

Return ONLY JSON with keys: summary, key_findings, red_flags."""

            raw = client.complete(system=_SYSTEM, user=user_msg, max_tokens=1000)
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            parsed = json.loads(raw)
            report["summary"]      = parsed.get("summary")
            report["key_findings"] = parsed.get("key_findings", [])
            report["red_flags"]    = parsed.get("red_flags", [])
        except Exception as e:
            report["errors"].append(f"LLM synthesis failed: {e}")

    elif not has_data:
        report["summary"] = (
            f"No enforcement actions, disciplinary events, or regulatory proceedings "
            f"were found for {firm_name} across IAPD disclosures and web search. "
            "The firm appears to present a clean regulatory history based on available public data."
        )
        report["key_findings"] = ["No enforcement actions found — clean regulatory record"]

    print(
        f"[Enforcement] Severity: {report['severity']} · "
        f"{total} IAPD action(s), {len(web_results)} web hit(s) · "
        f"sources: {report['sources']}"
    )
    return report
