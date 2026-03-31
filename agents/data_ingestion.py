"""
Data Ingestion Agent
Orchestrates all data pulls for a given fund/adviser.
Input:  firm name or CRD number
Output: structured raw_data dict ready for downstream agents

Steps 1-2 run sequentially (each needs the CRD from the previous step).
Steps 3-7 run in parallel via ThreadPoolExecutor — they all depend only on
the firm name / CRD resolved in step 2, not on each other.
Step 5b runs after the parallel block — upgrades the 13F filing list using
the CIK resolved by ADV enrichment (more accurate than name-based search).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from tools.edgar_client import (
    search_adviser_by_name,
    get_adviser_detail,
    extract_adv_summary,
    search_13f_filings,
    search_13f_by_cik,
)
from tools.fred_client import get_market_context, latest_value


def run(firm_input: str, fred_api_key: str = None,
        website: str = None, client=None, tavily_key: str = None) -> dict:
    """
    Pull all available data for a firm.

    Args:
        firm_input: Either a firm name (str) or CRD number (str of digits).
        fred_api_key: Optional FRED key; falls back to env var.

    Returns:
        raw_data dict with keys:
          - search_results   : IAPD search hits
          - crd              : resolved CRD
          - adv_summary      : parsed ADV fields from IAPD
          - adv_xml_data     : 13F portfolio value + IAPD disclosures
          - filings_13f      : list of 13F-HR filing metadata
          - market_context   : FRED macro series (latest readings)
          - fund_discovery   : Form D + IAPD relying advisors + web search
          - enforcement      : SEC enforcement deep-dive
          - errors           : list of any non-fatal errors encountered
    """
    raw_data = {
        "input":          firm_input,
        "search_results": [],
        "crd":            None,
        "adv_summary":    {},
        "adv_xml_data":   {},
        "filings_13f":    [],
        "market_context": {},
        "fund_discovery": {},
        "enforcement":    {},
        "errors":         [],
    }

    # ── Step 1: Resolve CRD ──────────────────────────────────────────────────
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
            crd = None
        else:
            crd = results[0]["crd"]
            raw_data["crd"] = crd
            print(f"[Ingestion] Resolved to CRD {crd}: {results[0]['firm_name']}")

    # ── Step 2: Pull IAPD/ADV detail ────────────────────────────────────────
    _iacontent = None
    if crd:
        print(f"[Ingestion] Fetching IAPD detail for CRD {crd}")
        detail = get_adviser_detail(str(crd))
        if detail:
            _iacontent = detail
            search_hit = raw_data["search_results"][0] if raw_data["search_results"] else None
            raw_data["adv_summary"] = extract_adv_summary(detail, search_hit=search_hit)
        else:
            raw_data["errors"].append(f"IAPD detail fetch failed for CRD {crd}")

    # Resolve firm name for downstream steps
    search_name = (
        firm_input if not firm_input.isdigit()
        else raw_data["adv_summary"].get("firm_name", "")
    )
    firm_name = raw_data["adv_summary"].get("firm_name") or search_name

    # ── Steps 3-7: Run in parallel ───────────────────────────────────────────
    # All depend only on firm_name/CRD from steps 1-2, not on each other.

    def _fetch_13f():
        if not search_name:
            return "filings_13f", [], None
        print(f"[Ingestion] Searching EDGAR for 13F filings: '{search_name}'")
        filings = search_13f_filings(search_name, max_results=5)
        err = None
        if not filings:
            err = (
                f"No 13F filings found for '{search_name}' — "
                "firm may not hold reportable US equity positions above $100M threshold"
            )
        return "filings_13f", filings, err

    def _fetch_fred():
        print("[Ingestion] Fetching macro context from FRED")
        macro = get_market_context(api_key=fred_api_key)
        if macro:
            result = {
                name: {"latest": latest_value(obs), "recent": obs[:3]}
                for name, obs in macro.items()
            }
            return "market_context", result, None
        return "market_context", {}, "FRED macro data unavailable (check API key)"

    def _fetch_adv():
        if not firm_name:
            return "adv_xml_data", {}, "ADV enrichment: could not determine firm name"
        print(f"[Ingestion] Running ADV enrichment for '{firm_name}'")
        try:
            from tools.adv_parser import fetch_adv_data
            return "adv_xml_data", fetch_adv_data(firm_name, iacontent=_iacontent), None
        except Exception as e:
            return "adv_xml_data", {}, f"ADV enrichment failed: {e}"

    def _fetch_funds():
        if not firm_name:
            return "fund_discovery", {}, "Fund discovery: could not determine firm name"
        print(f"[Ingestion] Running fund discovery for '{firm_name}'")
        try:
            from agents import fund_discovery as _fd
            return "fund_discovery", _fd.run(
                firm_name=firm_name,
                crd=raw_data.get("crd"),
                iacontent=_iacontent,
                website=website,
                client=client,
                tavily_key=tavily_key,
            ), None
        except Exception as e:
            return "fund_discovery", {}, f"Fund discovery failed: {e}"

    def _fetch_enforcement():
        if not firm_name:
            return "enforcement", {}, None
        print(f"[Ingestion] Running enforcement check for '{firm_name}'")
        try:
            from agents import enforcement as _enf
            cik = (raw_data.get("adv_xml_data", {}).get("thirteenf") or {}).get("cik")
            return "enforcement", _enf.run(
                firm_name=firm_name,
                crd=raw_data.get("crd"),
                cik=cik,
                iacontent=_iacontent,
                has_disclosure_flag=bool(raw_data["adv_summary"].get("has_disclosures")),
                tavily_key=tavily_key,
                client=client,
            ), None
        except Exception as e:
            return "enforcement", {}, f"Enforcement check failed: {e}"

    tasks = [_fetch_13f, _fetch_fred, _fetch_adv, _fetch_funds, _fetch_enforcement]
    print(f"[Ingestion] Running {len(tasks)} data pulls in parallel...")

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(t): t.__name__ for t in tasks}
        for future in as_completed(futures):
            try:
                key, value, err = future.result()
                raw_data[key] = value
                if err:
                    raw_data["errors"].append(err)
            except Exception as e:
                raw_data["errors"].append(f"Parallel task failed: {e}")

    # ── Step 5b: Upgrade 13F list using resolved CIK (post-parallel) ────────
    # ADV enrichment resolves the CIK via EFTS — more accurate than name search.
    cik_from_13f = (raw_data.get("adv_xml_data", {}).get("thirteenf") or {}).get("cik")
    if cik_from_13f:
        print(f"[Ingestion] Re-fetching 13F filing list by CIK {cik_from_13f}")
        filings_by_cik = search_13f_by_cik(cik_from_13f, max_results=5)
        if filings_by_cik:
            raw_data["filings_13f"] = filings_by_cik
            raw_data["errors"] = [
                e for e in raw_data["errors"]
                if "No 13F filings found" not in e
            ]

    print(f"[Ingestion] Done. Errors: {raw_data['errors'] or 'none'}")
    return raw_data
