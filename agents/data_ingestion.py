"""
Data Ingestion Agent
Orchestrates all data pulls for a given fund/adviser.
Input:  firm name or CRD number
Output: structured raw_data dict ready for downstream agents
"""

from tools.edgar_client import (
    search_adviser_by_name,
    get_adviser_detail,
    extract_adv_summary,
    search_13f_filings,
)
from tools.fred_client import get_market_context, latest_value


def run(firm_input: str, fred_api_key: str = None) -> dict:
    """
    Pull all available data for a firm.

    Args:
        firm_input: Either a firm name (str) or CRD number (str of digits).
        fred_api_key: Optional FRED key; falls back to env var.

    Returns:
        raw_data dict with keys:
          - search_results   : IAPD search hits
          - crd              : resolved CRD
          - adv_summary      : parsed ADV fields (only real data, no defaults)
          - filings_13f      : list of 13F-HR filing metadata
          - market_context   : FRED macro series (latest readings)
          - errors           : list of any non-fatal errors encountered
    """
    raw_data = {
        "input": firm_input,
        "search_results": [],
        "crd": None,
        "adv_summary": {},
        "filings_13f": [],
        "market_context": {},
        "errors": [],
    }

    # ── Step 1: Resolve CRD ───────────────────────────────────────────────────
    if firm_input.isdigit():
        crd = firm_input
        raw_data["crd"] = crd
        print(f"[Ingestion] Using CRD directly: {crd}")
    else:
        print(f"[Ingestion] Searching IAPD for: '{firm_input}'")
        results = search_adviser_by_name(firm_input, max_results=5)
        raw_data["search_results"] = results

        if not results:
            msg = f"No IAPD results found for '{firm_input}'"
            raw_data["errors"].append(msg)
            print(f"[Ingestion] WARNING: {msg}")
            # Still try 13F search below with the name
            crd = None
        else:
            # Take the top hit — downstream memo will show search_results so
            # user can verify we matched the right entity
            crd = results[0]["crd"]
            raw_data["crd"] = crd
            print(f"[Ingestion] Resolved to CRD {crd}: {results[0]['firm_name']}")

    # ── Step 2: Pull IAPD/ADV detail ─────────────────────────────────────────
    if crd:
        print(f"[Ingestion] Fetching IAPD detail for CRD {crd}")
        detail = get_adviser_detail(str(crd))
        if detail:
            raw_data["adv_summary"] = extract_adv_summary(detail)
        else:
            raw_data["errors"].append(f"IAPD detail fetch failed for CRD {crd}")

    # ── Step 3: Search 13F filings on EDGAR ──────────────────────────────────
    search_name = firm_input if not firm_input.isdigit() else raw_data["adv_summary"].get("firm_name", "")
    if search_name:
        print(f"[Ingestion] Searching EDGAR for 13F filings: '{search_name}'")
        filings = search_13f_filings(search_name, max_results=5)
        raw_data["filings_13f"] = filings
        if not filings:
            raw_data["errors"].append(f"No 13F filings found for '{search_name}'")

    # ── Step 4: Pull macro context from FRED ─────────────────────────────────
    print("[Ingestion] Fetching macro context from FRED")
    macro = get_market_context(api_key=fred_api_key)
    if macro:
        # Summarise to latest reading per series for memo brevity
        raw_data["market_context"] = {
            name: {"latest": latest_value(obs), "recent": obs[:3]}
            for name, obs in macro.items()
        }
    else:
        raw_data["errors"].append("FRED macro data unavailable (check API key)")

    print(f"[Ingestion] Done. Errors: {raw_data['errors'] or 'none'}")
    return raw_data
