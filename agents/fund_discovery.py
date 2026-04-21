"""
Fund Discovery Agent — Tool-Use Agent
======================================
GPT-4o autonomously decides which EDGAR Form D searches and web queries to run,
tries name variants, and loops until it's confident it has found all discoverable funds.

This is a real agent: GPT-4o uses tool_use to call EDGAR and web search,
sees the results, decides what to try next, and stops when done.

Tools available to the agent:
  search_form_d(gp_name)      — EDGAR Form D search
  search_web(query)           — Tavily / DuckDuckGo web search
  get_relying_advisors(crd)   — IAPD relying advisor list

Output: same shape as before so downstream agents need no changes:
  {funds, relying_advisors, total_found, sources_used, errors}
"""

from tools.llm_client import LLMClient
from tools.formd_client import search_funds_for_gp
from tools import web_search_client


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_form_d",
        "description": (
            "Search SEC EDGAR Form D filings for private funds associated with a GP name. "
            "Returns a list of funds with offering amounts, exemptions (3C.1 / 3C.7), "
            "and filing dates. Try the full legal name AND shorter variants "
            "(e.g. first word only, two meaningful words). Many GPs file Form D under "
            "slightly different entity names than their adviser registration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "gp_name": {
                    "type": "string",
                    "description": "GP / adviser name to search on EDGAR Form D",
                }
            },
            "required": ["gp_name"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web for fund names, fundraising news, or information about "
            "the investment manager. Use this to find funds not registered on Form D "
            "(e.g. offshore funds, separately managed accounts, funds closed before "
            "Form D was required). Also useful for finding fund names to then look up "
            "on EDGAR."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Web search query",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_relying_advisors",
        "description": (
            "Get the list of relying advisor entities from IAPD for a given CRD number. "
            "These are affiliated advisers that may manage sub-funds under the umbrella registration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "crd": {
                    "type": "string",
                    "description": "SEC CRD number of the investment adviser",
                }
            },
            "required": ["crd"],
        },
    },
]


SYSTEM_PROMPT = """You are a fund discovery agent performing LP due diligence on an investment manager.

Your goal: find ALL private funds this manager has ever raised or managed, using SEC EDGAR Form D
filings and web search.

HOW TO DO THIS:
1. Start with search_form_d using the full legal firm name
2. If that returns 0 results, try shorter variants:
   - First meaningful word only (e.g. "Ares" from "Ares Management LLC")
   - Two meaningful words (e.g. "Ares Management")
   Strip common suffixes: LLC, LP, Inc, Corp, Management, Capital, Advisors, Partners
3. Search the web for fund names if Form D search is sparse:
   - "[firm name] private equity fund"
   - "[firm name] fund I II III IV V"
   - "[firm name] hedge fund strategy"
4. For any fund names found via web but not on Form D, search Form D for that specific fund name
5. If a CRD is provided, call get_relying_advisors to find affiliated entities

Stop when you've tried at least 2 name variants AND at least 1 web search.

FINAL OUTPUT:
After all tool calls, output ONLY a JSON object:
{
  "funds": [
    {
      "name": "fund entity name",
      "offering_amount": "$X.XB or null",
      "date_of_first_sale": "YYYY-MM-DD or null",
      "entity_type": "Limited Partnership or null",
      "exemptions": ["3C.1", "3C.7"],
      "is_private_fund": true,
      "jurisdiction": "state or null",
      "edgar_url": "url or null",
      "source": "EDGAR Form D | web search | web search + EDGAR Form D"
    }
  ],
  "relying_advisors": [],
  "sources_used": ["EDGAR Form D", "Web search"],
  "search_variants_tried": ["full name", "abbreviated"],
  "notes": "any caveats about coverage"
}

Rules:
- No hallucination. Only include funds you actually found via tool calls.
- If a fund appears in web search but not Form D, include it with source "web search".
- Deduplicate by fund name (case-insensitive).
"""


# ── Tool executor functions ───────────────────────────────────────────────────

def _exec_search_form_d(inputs: dict, max_funds: int = 20) -> list[dict]:
    gp_name = inputs.get("gp_name", "").strip()
    if not gp_name:
        return []
    try:
        funds = search_funds_for_gp(gp_name, max_funds=max_funds)
        # Return slim dicts to keep context manageable
        return [
            {
                "name":               f.get("entity_name"),
                "offering_amount":    f.get("offering_fmt"),
                "date_of_first_sale": f.get("date_of_first_sale"),
                "entity_type":        f.get("entity_type"),
                "exemptions":         f.get("exemptions", []),
                "is_private_fund":    f.get("is_private_fund", False),
                "jurisdiction":       f.get("jurisdiction"),
                "cik":                f.get("cik"),
                "accession":          f.get("accession"),
                "edgar_url": (
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                    f"&CIK={f['cik']}&type=D&dateb=&owner=include&count=10"
                    if f.get("cik") else None
                ),
                "source": "EDGAR Form D",
            }
            for f in funds
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _exec_search_web(inputs: dict, tavily_key: str = None) -> list[dict]:
    query = inputs.get("query", "").strip()
    if not query:
        return []
    try:
        results = web_search_client.search(query, api_key=tavily_key, max_results=5)
        if results and results[0].get("_search_error"):
            return [{"error": f"Web search unavailable: {results[0].get('error')}"}]
        return [
            {
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "date":    r.get("published_date"),
                "snippet": (r.get("content") or "")[:400],
            }
            for r in results
            if not r.get("_search_error")
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _exec_get_relying_advisors(inputs: dict, iacontent: dict = None) -> list[dict]:
    ra = (iacontent or {}).get("relyingAdvisors", [])
    return [
        {"name": r.get("name"), "crd": r.get("firmId"), "status": r.get("status")}
        for r in ra if isinstance(r, dict) and r.get("name")
    ]


# ── News enrichment (post-agent, not part of the loop) ───────────────────────

def _fetch_fund_news(fund_name: str, firm_name: str, tavily_key: str = None) -> list[dict]:
    query = f'"{fund_name}" {firm_name} fund fundraising close news'
    try:
        results = web_search_client.search(query, api_key=tavily_key, max_results=3)
        return [
            {
                "title":   r.get("title"),
                "url":     r.get("url"),
                "date":    r.get("published_date"),
                "snippet": (r.get("content") or "")[:300],
            }
            for r in results
            if not r.get("_search_error")
        ]
    except Exception:
        return []


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    firm_name: str,
    crd: str = None,
    iacontent: dict = None,
    website: str = None,
    client: LLMClient = None,
    tavily_key: str = None,
    max_funds: int = 15,
) -> dict:
    """
    Run the fund discovery agent.

    If no LLMClient is provided, falls back to a direct Form D search (no agent loop).
    """
    report = {
        "funds":            [],
        "relying_advisors": [],
        "total_found":      0,
        "sources_used":     [],
        "errors":           [],
    }

    if client is None:
        # Fallback: direct Form D search without agent
        print(f"[Fund Discovery] No LLM client — running direct Form D search for '{firm_name}'")
        try:
            funds = search_funds_for_gp(firm_name, max_funds=max_funds)
            report["funds"] = [
                {
                    "name":               f.get("entity_name"),
                    "offering_amount":    f.get("offering_fmt"),
                    "date_of_first_sale": f.get("date_of_first_sale"),
                    "entity_type":        f.get("entity_type"),
                    "exemptions":         f.get("exemptions", []),
                    "is_private_fund":    f.get("is_private_fund", False),
                    "jurisdiction":       f.get("jurisdiction"),
                    "edgar_url": (
                        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                        f"&CIK={f['cik']}&type=D&dateb=&owner=include&count=10"
                        if f.get("cik") else None
                    ),
                    "news":   [],
                    "source": "EDGAR Form D",
                }
                for f in funds
            ]
            if funds:
                report["sources_used"].append("EDGAR Form D")
            report["total_found"] = len(report["funds"])
        except Exception as e:
            report["errors"].append(f"Form D search failed: {e}")
        return report

    # ── Build tool executor ───────────────────────────────────────────────────
    tool_executor = {
        "search_form_d": lambda inp: _exec_search_form_d(inp, max_funds=max_funds),
        "search_web":    lambda inp: _exec_search_web(inp, tavily_key=tavily_key),
        "get_relying_advisors": lambda inp: _exec_get_relying_advisors(inp, iacontent=iacontent),
    }

    # Build initial context for the agent
    crd_line = f"CRD: {crd}" if crd else "CRD: unknown"
    website_line = f"Website: {website}" if website else ""
    initial_message = (
        f"Find all private funds managed by this investment adviser:\n\n"
        f"Firm name: {firm_name}\n"
        f"{crd_line}\n"
        f"{website_line}\n\n"
        f"Use the available tools. Try multiple name variants on Form D. "
        f"Also search the web. Output your final JSON when done."
    )

    print(f"[Fund Discovery Agent] Starting agent loop for '{firm_name}'...")
    try:
        result = client.agent_loop_json(
            system=SYSTEM_PROMPT,
            initial_message=initial_message,
            tools=TOOLS,
            tool_executor=tool_executor,
            max_tokens=4096,
            max_iterations=15,
        )
    except Exception as e:
        report["errors"].append(f"Agent loop failed: {e}")
        return report

    if "parse_error" in result:
        report["errors"].append(f"Agent output parse error: {result['parse_error'][:200]}")
        return report

    # ── Enrich with news ──────────────────────────────────────────────────────
    raw_funds = result.get("funds", [])
    print(f"[Fund Discovery Agent] Found {len(raw_funds)} funds. Enriching with news...")
    enriched = []
    for f in raw_funds[:max_funds]:
        name = f.get("name") or ""
        if name:
            f["news"] = _fetch_fund_news(name, firm_name, tavily_key=tavily_key)
        else:
            f["news"] = []
        enriched.append(f)

    report["funds"]            = enriched
    report["relying_advisors"] = result.get("relying_advisors", [])
    report["total_found"]      = len(enriched)
    report["sources_used"]     = result.get("sources_used", [])

    if result.get("notes"):
        report["errors"].append(result["notes"])

    print(
        f"[Fund Discovery Agent] Done — {len(enriched)} funds, "
        f"sources: {report['sources_used']}"
    )
    return report
