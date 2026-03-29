"""
Fund Discovery Agent
====================
Discovers the private funds managed by an investment adviser and enriches
each fund with Form D filing data, news, and website information.

Sources (in priority order):
  1. EDGAR Form D — definitive SEC filings for each fund entity
  2. IAPD relyingAdvisors — affiliated adviser entities (may manage sub-funds)
  3. Web search on firm website — fund names from marketing pages / ADV brochure

For each discovered fund:
  - Form D: fund name, offering amount, date of first sale, entity type, exemption
  - News: web search for recent news on that specific fund
  - EDGAR link: direct link to the Form D filing index

Output feeds directly into:
  - fund_analysis agent (adds "funds" section to structured analysis)
  - risk_flagging agent (fund-level concentration / vintage / regulatory risks)
  - memo_generation agent (Fund Analysis section of the memo)
"""

import json
from tools.llm_client import LLMClient
from tools.formd_client import search_funds_for_gp
from tools import web_search_client


def _get_relying_advisors(iacontent: dict) -> list[dict]:
    """Extract relying advisor entities from IAPD iacontent."""
    ra = iacontent.get("relyingAdvisors", []) if iacontent else []
    return [
        {"name": r.get("name"), "crd": r.get("firmId"), "status": r.get("status")}
        for r in ra if isinstance(r, dict) and r.get("name")
    ]


def _search_fund_news(fund_name: str, gp_name: str,
                      tavily_key: str = None) -> list[dict]:
    """Quick news search for a specific fund."""
    query = f'"{fund_name}" {gp_name} fund fundraising close news'
    try:
        results = web_search_client.search(query, api_key=tavily_key, max_results=3)
        return [{"title": r.get("title"), "url": r.get("url"),
                 "date": r.get("published_date"), "snippet": (r.get("content") or "")[:300]}
                for r in results]
    except Exception:
        return []


def _extract_funds_from_website(
    firm_name: str,
    website: str,
    client: LLMClient,
    tavily_key: str = None,
) -> list[str]:
    """
    Web search the firm's website/brochure pages for fund names.
    Returns a list of fund name strings.
    """
    queries = [
        f'site:{website} fund strategy' if website else f'"{firm_name}" funds site:sec.gov',
        f'"{firm_name}" private fund names portfolio',
    ]
    raw_results = []
    for q in queries:
        try:
            hits = web_search_client.search(q, api_key=tavily_key, max_results=4)
            raw_results.extend(hits)
        except Exception:
            pass

    if not raw_results:
        return []

    # Ask o3 to extract fund names from the search snippets
    content = "\n\n".join(
        f"[{r.get('title','')}] {(r.get('content') or '')[:400]}"
        for r in raw_results[:8]
    )

    system = """You are extracting private fund names from web search results about an investment manager.
Return ONLY a JSON array of fund name strings. No other text.
Rules: only include named funds (e.g. "Blackstone Capital Partners IX"), not strategy descriptions."""

    user = f"""Investment manager: {firm_name}

Search results:
{content}

Extract all specific private fund names mentioned. Return JSON array only."""

    try:
        raw = client.complete(system=system, user=user, max_tokens=500)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        import json as _json
        names = _json.loads(raw)
        if isinstance(names, list):
            return [str(n) for n in names if n]
    except Exception:
        pass
    return []


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
    Discover and enrich all private funds managed by this adviser.

    Returns:
        {
          "funds":              list of enriched fund dicts
          "relying_advisors":   list from IAPD
          "total_found":        int
          "sources_used":       list of strings
          "errors":             list of strings
        }
    """
    report = {
        "funds":            [],
        "relying_advisors": [],
        "total_found":      0,
        "sources_used":     [],
        "errors":           [],
    }

    # ── Source 1: EDGAR Form D ────────────────────────────────────────────────
    print(f"[Fund Discovery] Searching EDGAR Form D for '{firm_name}'...")
    try:
        formd_funds = search_funds_for_gp(firm_name, max_funds=max_funds)
        if formd_funds:
            report["sources_used"].append("EDGAR Form D")
            print(f"[Fund Discovery] Found {len(formd_funds)} Form D funds")
        else:
            report["errors"].append(
                f"No Form D filings found for '{firm_name}' — "
                "firm may not manage SEC-registered private offerings, "
                "or funds may be registered under a different entity name"
            )
    except Exception as e:
        formd_funds = []
        report["errors"].append(f"Form D search failed: {e}")

    # Build fund list from Form D results
    fund_map: dict[str, dict] = {}   # entity_name (upper) → fund dict
    for f in formd_funds:
        key = (f.get("entity_name") or "").upper()
        fund_map[key] = {
            "name":                 f.get("entity_name"),
            "entity_type":          f.get("entity_type"),
            "exemptions":           f.get("exemptions", []),
            "is_private_fund":      f.get("is_private_fund", False),
            "offering_amount":      f.get("offering_fmt"),
            "offering_amount_raw":  f.get("total_offering_amount"),
            "date_of_first_sale":   f.get("date_of_first_sale"),
            "jurisdiction":         f.get("jurisdiction"),
            "cik":                  f.get("cik"),
            "accession":            f.get("accession"),
            "filing_date":          f.get("file_date"),
            "edgar_url": (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={f['cik']}&type=D&dateb=&owner=include&count=10"
                if f.get("cik") else None
            ),
            "news":                 [],
            "source":               "EDGAR Form D",
        }

    # ── Source 2: IAPD relyingAdvisors ───────────────────────────────────────
    ra = _get_relying_advisors(iacontent or {})
    report["relying_advisors"] = ra
    if ra:
        report["sources_used"].append("IAPD Relying Advisors")

    # ── Source 3: Website / web search for additional fund names ─────────────
    if client:
        print(f"[Fund Discovery] Web search for fund names from website/brochures...")
        try:
            web_names = _extract_funds_from_website(
                firm_name, website or "", client, tavily_key=tavily_key
            )
            if web_names:
                report["sources_used"].append("Web search / firm website")
                for name in web_names:
                    key = name.upper()
                    if key not in fund_map:
                        fund_map[key] = {
                            "name":               name,
                            "source":             "web search",
                            "entity_type":        None,
                            "offering_amount":    None,
                            "date_of_first_sale": None,
                            "news":               [],
                        }
        except Exception as e:
            report["errors"].append(f"Web fund name extraction failed: {e}")

    # ── Enrich each fund with news ────────────────────────────────────────────
    funds = list(fund_map.values())
    print(f"[Fund Discovery] Enriching {len(funds)} funds with news...")
    for fund in funds[:10]:   # cap news lookups to top 10 funds
        name = fund.get("name", "")
        if name:
            try:
                fund["news"] = _search_fund_news(name, firm_name, tavily_key=tavily_key)
            except Exception:
                fund["news"] = []

    report["funds"]       = funds
    report["total_found"] = len(funds)

    print(f"[Fund Discovery] Done. {len(funds)} funds, "
          f"sources: {report['sources_used']}, errors: {report['errors'] or 'none'}")
    return report
