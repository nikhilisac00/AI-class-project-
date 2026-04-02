"""
SEC Enforcement Agent — Tool-Use Agent
========================================
Claude autonomously investigates regulatory history using web search and EDGAR.
It decides what to search based on what it finds — if it sees a disclosure flag,
it searches for specifics; if it finds a firm name variant, it searches that too.

Tools:
  search_enforcement_web(query)   — targeted SEC/regulatory web search
  search_edgar_filings(firm_name) — EDGAR EFTS enforcement-adjacent forms
  get_iapd_disclosures(crd)       — IAPD structured disclosure array

Output: severity, summary, key_findings, red_flags, sources
"""

import json
from tools.llm_client import LLMClient
from tools.enforcement_client import fetch_enforcement_data
from tools import web_search_client


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_enforcement_web",
        "description": (
            "Search the web for SEC/FINRA/DOJ enforcement actions, regulatory proceedings, "
            "fines, bars, suspensions, or litigation involving this investment adviser. "
            "Good queries: '[firm] SEC enforcement', '[firm] FINRA fine', '[firm] SEC order', "
            "'[person name] bar industry', '[firm] fraud litigation'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Enforcement-focused search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_edgar_enforcement",
        "description": (
            "Search SEC EDGAR full-text for enforcement-adjacent filings: UPLOAD orders, "
            "CORRESP letters, ADV-W withdrawals, and other unusual form types for this firm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "firm_name": {"type": "string", "description": "Firm name to search on EDGAR"},
            },
            "required": ["firm_name"],
        },
    },
    {
        "name": "get_iapd_disclosures",
        "description": (
            "Get structured IAPD disclosure records from the already-fetched adviser detail. "
            "Returns criminal, regulatory, civil, and arbitration disclosures if available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "crd": {"type": "string", "description": "CRD number (for reference)"}
            },
            "required": ["crd"],
        },
    },
]


SYSTEM_PROMPT = """You are an LP compliance analyst investigating the regulatory history of an
investment adviser. Your job is to build the most complete picture of their enforcement record
using all available public sources.

HOW TO INVESTIGATE:
1. Always start with get_iapd_disclosures — it reads the already-fetched IAPD data
2. Always run at least 2 web searches: one for the firm, one for key principals if known
3. If IAPD says disclosures exist but you find nothing structured, search harder
4. If you find an enforcement action, search specifically for it to get details
5. Search EDGAR for unusual form types

SEVERITY FRAMEWORK:
- CRITICAL: criminal conviction, fraud finding, permanent industry bar
- HIGH: open/pending enforcement, recent bar or suspension (< 5 years), large fine (> $1M)
- MEDIUM: resolved fine < $1M, cease-and-desist order (resolved), civil litigation settled
- LOW: old minor action (> 10 years, resolved), single small fine
- CLEAN: nothing found after thorough search

Stop after 4-6 total tool calls unless you found something that requires follow-up.

FINAL OUTPUT — output ONLY valid JSON:
{
  "severity": "CLEAN | LOW | MEDIUM | HIGH | CRITICAL",
  "summary": "3-5 sentence LP-grade narrative of what was found and what it means.",
  "key_findings": ["up to 5 specific bullet points"],
  "red_flags": ["most serious items — empty list if clean"],
  "sources_used": ["list of sources consulted"],
  "actions": [
    {
      "action_type": "Regulatory | Criminal | Civil | Arbitration",
      "initiated_by": "SEC | FINRA | DOJ | State | CFTC | Unknown",
      "date": "YYYY-MM-DD or year",
      "description": "what was alleged",
      "sanctions": ["list"],
      "resolution": "Settled | Dismissed | Pending | Final Order",
      "severity": "HIGH | MEDIUM | LOW",
      "source": "IAPD | Web | EDGAR"
    }
  ]
}
"""


# ── Tool executors ────────────────────────────────────────────────────────────

def _exec_search_enforcement_web(inputs: dict, tavily_key: str = None) -> list[dict]:
    query = inputs.get("query", "").strip()
    if not query:
        return []
    try:
        results = web_search_client.search(query, api_key=tavily_key, max_results=5)
        return [
            {
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "date":    r.get("published_date"),
                "snippet": (r.get("content") or "")[:500],
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _exec_search_edgar_enforcement(inputs: dict) -> list[dict]:
    import requests, time
    firm_name = inputs.get("firm_name", "").strip()
    if not firm_name:
        return []
    EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
    HEADERS  = {"User-Agent": "AI-Alternatives-Research research@example.com"}
    ENFORCE_FORMS = {"UPLOAD", "CORRESP", "ADV-W", "40-OIP", "40-APP"}
    try:
        r = requests.get(
            EFTS_URL,
            params={"q": f'"{firm_name}"', "forms": ",".join(ENFORCE_FORMS)},
            headers=HEADERS, timeout=15,
        )
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        return [
            {
                "form":       h["_source"].get("form"),
                "file_date":  h["_source"].get("file_date"),
                "entity":     (h["_source"].get("display_names") or [""])[0],
                "accession":  h["_source"].get("adsh"),
            }
            for h in hits[:8]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _exec_get_iapd_disclosures(iacontent: dict, has_disclosure_flag: bool) -> dict:
    ic = iacontent or {}
    disclosures = []
    for key in [
        "iaCriminalDisclosures", "iaRegulatoryDisclosures",
        "iaCivilDisclosures", "iaArbitrationDisclosures",
        "iaEmploymentDisclosures",
    ]:
        for d in ic.get(key, []) or []:
            if isinstance(d, dict):
                disclosures.append({
                    "type":        key.replace("ia", "").replace("Disclosures", ""),
                    "date":        d.get("disclosureDate") or d.get("eventDate"),
                    "description": d.get("allegations") or d.get("description"),
                    "sanctions":   d.get("sanctions") or d.get("penaltiesAndSanctions"),
                    "resolution":  d.get("disposition") or d.get("resolution"),
                })
    return {
        "has_disclosure_flag":          has_disclosure_flag,
        "structured_disclosures_found": len(disclosures),
        "disclosures":                  disclosures,
        "note": (
            f"{len(disclosures)} structured disclosure(s) found in IAPD." if disclosures
            else (
                "IAPD flag set but no structured data — manual review at adviserinfo.sec.gov required."
                if has_disclosure_flag else "No disclosures in IAPD data."
            )
        ),
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    firm_name: str,
    crd: str = None,
    cik: str = None,
    iacontent: dict = None,
    has_disclosure_flag: bool = False,
    tavily_key: str = None,
    client: LLMClient = None,
) -> dict:

    report = {
        "enforcement_data": {},
        "summary":          None,
        "severity":         "CLEAN",
        "key_findings":     [],
        "red_flags":        [],
        "sources":          [],
        "errors":           [],
    }

    if client is None:
        # Fallback: non-agent fetch
        print(f"[Enforcement] No LLM client — basic check for '{firm_name}'")
        try:
            data = fetch_enforcement_data(
                firm_name=firm_name, crd=crd, cik=cik,
                iacontent=iacontent, has_disclosure_flag=has_disclosure_flag,
                tavily_key=tavily_key,
            )
            report["enforcement_data"] = data
            report["sources"]          = data.get("sources_used", [])
            report["severity"] = "CLEAN" if data.get("total_actions", 0) == 0 else "LOW"
        except Exception as e:
            report["errors"].append(f"Enforcement fetch failed: {e}")
        return report

    # ── Build tool executor ───────────────────────────────────────────────────
    tool_executor = {
        "search_enforcement_web": lambda inp: _exec_search_enforcement_web(
            inp, tavily_key=tavily_key
        ),
        "search_edgar_enforcement": _exec_search_edgar_enforcement,
        "get_iapd_disclosures": lambda inp: _exec_get_iapd_disclosures(
            iacontent, has_disclosure_flag
        ),
    }

    context_lines = [
        f"Firm: {firm_name}",
        f"CRD: {crd or 'unknown'}",
        f"CIK: {cik or 'unknown'}",
        f"IAPD has_disclosures flag: {has_disclosure_flag}",
    ]
    if has_disclosure_flag:
        context_lines.append(
            "IMPORTANT: IAPD says this firm has disclosures on record — find them."
        )

    initial_message = (
        "\n".join(context_lines)
        + "\n\nInvestigate this firm's regulatory and enforcement history thoroughly. "
        "Output your final JSON when done."
    )

    print(f"[Enforcement Agent] Starting agent loop for '{firm_name}'...")
    try:
        result = client.agent_loop_json(
            system=SYSTEM_PROMPT,
            initial_message=initial_message,
            tools=TOOLS,
            tool_executor=tool_executor,
            max_tokens=4096,
            max_iterations=12,
        )
    except Exception as e:
        report["errors"].append(f"Agent loop failed: {e}")
        return report

    if "parse_error" in result:
        report["errors"].append(f"Agent output parse error: {result['parse_error'][:200]}")
        return report

    actions = result.get("actions", [])
    high_actions = [a for a in actions if a.get("severity") == "HIGH"]
    open_actions = [
        a for a in actions
        if (a.get("resolution") or "").lower() in ("pending", "open", "")
    ]

    report["severity"]     = result.get("severity", "CLEAN")
    report["summary"]      = result.get("summary")
    report["key_findings"] = result.get("key_findings", [])
    report["red_flags"]    = result.get("red_flags", [])
    report["sources"]      = result.get("sources_used", [])
    report["enforcement_data"] = {
        "actions":          actions,
        "total_actions":    len(actions),
        "high_count":       len(high_actions),
        "open_actions":     open_actions,
        "penalty_total_fmt": "—",   # penalties described in actions[].sanctions
        "web_results":      [],     # consumed internally by agent
        "edgar_hits":       [],     # consumed internally by agent
        "edgar_flags":      [],     # consumed internally by agent
    }

    print(f"[Enforcement Agent] Done — severity: {report['severity']}, "
          f"{len(actions)} action(s)")
    return report
