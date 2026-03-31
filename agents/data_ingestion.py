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
          - adv_summary      : parsed ADV fields from IAPD (registration, status, etc.)
          - adv_xml_data     : ADV Part 1A XML fields from EDGAR (AUM, fees, personnel)
          - filings_13f      : list of 13F-HR filing metadata
          - market_context   : FRED macro series (latest readings)
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
        "errors":         [],
    }

    # ── Step 1: Resolve CRD ───────────────────────────────────────────────────────────────
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

    # ── Step 2: Pull IAPD/ADV detail ─────────────────────────────────────────────────────
    _iacontent = None   # keep for Step 5
    if crd:
        print(f"[Ingestion] Fetching IAPD detail for CRD {crd}")
        detail = get_adviser_detail(str(crd))
        if detail:
            _iacontent = detail  # pass to ADV enrichment step
            search_hit = raw_data["search_results"][0] if raw_data["search_results"] else None
            raw_data["adv_summary"] = extract_adv_summary(detail, search_hit=search_hit)
        else:
            raw_data["errors"].append(f"IAPD detail fetch failed for CRD {crd}")

    # ── Step 3: 13F filing list — name-based fallback (will be upgraded in Step 5b) ───────
    search_name = firm_input if not firm_input.isdigit() else raw_data["adv_summary"].get("firm_name", "")
    if search_name:
        print(f"[Ingestion] Searching EDGAR for 13F filings (name): '{search_name}'")
        filings = search_13f_filings(search_name, max_results=5)
        raw_data["filings_13f"] = filings
        if not filings:
            raw_data["errors"].append(
                f"No 13F filings found for '{search_name}' — "
                "firm may not hold reportable US equity positions above $100M threshold"
            )

    # ── Step 4: Pull macro context from FRED ──────────────────────────────────────────
    print("[Ingestion] Fetching macro context from FRED")
    macro = get_market_context(api_key=fred_api_key)
    if macro:
        raw_data["market_context"] = {
            name: {"latest": latest_value(obs), "recent": obs[:3]}
            for name, obs in macro.items()
        }
    else:
        raw_data["errors"].append("FRED macro data unavailable (check API key)")

    # ── Step 5: ADV enrichment (13F portfolio value + IAPD disclosure details) ──────────
    adv_search_name = (
        raw_data["adv_summary"].get("firm_name")
        or (search_name if not firm_input.isdigit() else None)
    )
    if adv_search_name:
        print(f"[Ingestion] Running ADV enrichment for '{adv_search_name}'")
        try:
            from tools.adv_parser import fetch_adv_data
            adv_xml = fetch_adv_data(adv_search_name, iacontent=_iacontent)
            raw_data["adv_xml_data"] = adv_xml
        except Exception as e:
            raw_data["errors"].append(f"ADV enrichment failed: {e}")
    else:
        raw_data["errors"].append("ADV enrichment: could not determine firm name")

    # ── Step 5b: Upgrade 13F filing list using resolved CIK (more accurate than name search) ──
    cik_from_13f = (raw_data.get("adv_xml_data", {}).get("thirteenf") or {}).get("cik")
    if cik_from_13f:
        print(f"[Ingestion] Re-fetching 13F filing list by CIK {cik_from_13f}")
        filings_by_cik = search_13f_by_cik(cik_from_13f, max_results=5)
        if filings_by_cik:
            raw_data["filings_13f"] = filings_by_cik
            # Clear the name-mismatch error if we now have results
            raw_data["errors"] = [
                e for e in raw_data["errors"]
                if "No 13F filings found" not in e
            ]

    # ── Step 6: Fund discovery (Form D + IAPD relying advisors + web) ──────────
    fund_disc_name = (
        raw_data["adv_summary"].get("firm_name")
        or (firm_input if not firm_input.isdigit() else None)
    )
    if fund_disc_name:
        print(f"[Ingestion] Running fund discovery for '{fund_disc_name}'")
        try:
            from agents import fund_discovery as _fd
            raw_data["fund_discovery"] = _fd.run(
                firm_name=fund_disc_name,
                crd=raw_data.get("crd"),
                iacontent=_iacontent,
                website=website,
                client=client,
                tavily_key=tavily_key,
            )
        except Exception as e:
            raw_data["errors"].append(f"Fund discovery failed: {e}")
    else:
        raw_data["errors"].append("Fund discovery: could not determine firm name")

    # ── Step 7: SEC enforcement deep-dive ────────────────────────────────────
    enf_name = (
        raw_data["adv_summary"].get("firm_name")
        or (firm_input if not firm_input.isdigit() else None)
    )
    if enf_name:
        print(f"[Ingestion] Running enforcement check for '{enf_name}'")
        try:
            from agents import enforcement as _enf
            cik_for_enf = (
                (raw_data.get("adv_xml_data", {}).get("thirteenf") or {}).get("cik")
            )
            raw_data["enforcement"] = _enf.run(
                firm_name=enf_name,
                crd=raw_data.get("crd"),
                cik=cik_for_enf,
                iacontent=_iacontent,
                has_disclosure_flag=bool(
                    raw_data["adv_summary"].get("has_disclosures")
                ),
                tavily_key=tavily_key,
                client=client,
            )
        except Exception as e:
            raw_data["errors"].append(f"Enforcement check failed: {e}")
            raw_data["enforcement"] = {}
    else:
        raw_data["enforcement"] = {}

    print(f"[Ingestion] Done. Errors: {raw_data['errors'] or 'none'}")
    return raw_data
