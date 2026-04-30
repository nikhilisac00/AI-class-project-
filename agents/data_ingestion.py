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

import threading
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait

from tools.edgar_client import (
    search_adviser_by_name,
    get_adviser_detail,
    extract_adv_summary,
    search_13f_filings,
    search_13f_by_cik,
    fetch_private_funds_section7b,
)
from tools.fred_client import get_market_context, latest_value
from tools.raw_data_cache import load_raw_data, save_raw_data


def run(firm_input: str, fred_api_key: str = None,
        website: str = None, client=None, tavily_key: str = None,
        force_refresh: bool = False) -> dict:
    """
    Pull all available data for a firm.

    Args:
        firm_input:     Either a firm name (str) or CRD number (str of digits).
        fred_api_key:   Optional FRED key; falls back to env var.
        force_refresh:  If True, bypass cache and re-fetch all data.

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
    # ── Cache check ────────────────────────────────────────────────────
    if not force_refresh:
        cached = load_raw_data(firm_input)
        if cached is not None:
            print(f"[Ingestion] Loaded from cache for '{firm_input}'")
            return cached

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

    # ── Step 1: Resolve CRD ────────────────────────────────────────
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

    # ── Step 2: Pull IAPD/ADV detail ─────────────────────────────────
    iacontent = None  # renamed from _iacontent (Bug #28)
    if crd:
        print(f"[Ingestion] Fetching IAPD detail for CRD {crd}")
        detail = get_adviser_detail(str(crd))
        if detail:
            iacontent = detail
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

    # ── Steps 3-7: Run in parallel ─────────────────────────────────────
    # All depend only on firm_name/CRD from steps 1-2, not on each other.
    # Bug #1: semaphore limits concurrent outbound API calls to avoid triggering
    # SEC/IAPD rate limits when multiple sessions run simultaneously.
    _api_semaphore = threading.Semaphore(3)

    def _with_semaphore(fn):
        """Wrap a task so it acquires the shared semaphore before running."""
        def wrapper():
            with _api_semaphore:
                return fn()
        wrapper.__name__ = fn.__name__
        return wrapper

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
            return "adv_xml_data", fetch_adv_data(firm_name, iacontent=iacontent), None
        except (ValueError, KeyError, TypeError, OSError) as e:
            # Bug #29: catch specific recoverable errors rather than bare Exception
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
                iacontent=iacontent,
                website=website,
                client=client,
                tavily_key=tavily_key,
            ), None
        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as e:
            return "fund_discovery", {}, f"Fund discovery failed: {e}"

    def _fetch_enforcement():
        if not firm_name:
            return "enforcement", {}, None
        print(f"[Ingestion] Running enforcement check for '{firm_name}'")
        try:
            from agents import enforcement as _enf
            # cik intentionally omitted here — avoid race condition with _fetch_adv
            # (both run in parallel). enforcement agent works without cik.
            return "enforcement", _enf.run(
                firm_name=firm_name,
                crd=raw_data.get("crd"),
                cik=None,
                iacontent=iacontent,
                has_disclosure_flag=bool(raw_data["adv_summary"].get("has_disclosures")),
                tavily_key=tavily_key,
                client=client,
            ), None
        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as e:
            return "enforcement", {}, f"Enforcement check failed: {e}"

    def _fetch_section7b():
        _crd = raw_data.get("crd")
        if not _crd:
            return "_section7b", [], None
        print(f"[Ingestion] Downloading ADV Part 1A PDF for Section 7.B (CRD {_crd})")
        try:
            funds = fetch_private_funds_section7b(str(_crd))
            note = f"Section 7.B: {len(funds)} private fund(s) parsed from ADV PDF"
            print(f"[Ingestion] {note}")
            return "_section7b", funds, None
        except Exception as e:
            return "_section7b", [], f"Section 7.B fetch failed: {e}"

    tasks = [_fetch_13f, _fetch_fred, _fetch_adv, _fetch_funds, _fetch_enforcement, _fetch_section7b]
    print(f"[Ingestion] Running {len(tasks)} data pulls in parallel...")

    # Bug #11: use futures_wait with timeout so a hung API call doesn't block forever.
    _PARALLEL_TIMEOUT = 120  # seconds
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(_with_semaphore(t)): t.__name__ for t in tasks}
        done, not_done = futures_wait(futures, timeout=_PARALLEL_TIMEOUT)

        # Handle tasks that finished (done)
        for future in done:
            task_name = futures[future]
            try:
                key, value, err = future.result()
                raw_data[key] = value
                if err:
                    raw_data["errors"].append(err)
            except Exception as e:
                raw_data["errors"].append(f"Task {task_name} failed: {e}")

        # Handle tasks that timed out (not_done) — Bug #11
        for future in not_done:
            task_name = futures[future]
            future.cancel()
            raw_data["errors"].append(
                f"Task {task_name} timed out after {_PARALLEL_TIMEOUT}s — data unavailable"
            )
            print(f"[Ingestion] WARNING: {task_name} timed out")

    # ── Merge Section 7.B results into adv_summary ───────────────────────────
    # _fetch_section7b writes to a temporary "_section7b" key so it doesn't
    # conflict with the existing raw_data schema. Merge it here then remove.
    section7b_funds = raw_data.pop("_section7b", [])
    if isinstance(raw_data.get("adv_summary"), dict):
        raw_data["adv_summary"]["private_funds_section7b"] = section7b_funds or []

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

    # Bug #5: distinguish critical data source failures from supplementary ones.
    # ADV enrichment is critical — without it, downstream agents produce unreliable output.
    _CRITICAL_TASKS = {"_fetch_adv", "_fetch_13f"}
    critical_failures = [
        e for e in raw_data["errors"]
        if any(tag in e for tag in ("ADV enrichment", "Task _fetch_adv", "Task _fetch_13f"))
    ]
    if critical_failures:
        raw_data["critical_data_failure"] = True
        raw_data["critical_failure_detail"] = critical_failures
        print(f"[Ingestion] CRITICAL: core data source(s) failed: {critical_failures}")
    else:
        raw_data["critical_data_failure"] = False

    print(f"[Ingestion] Done. Errors: {raw_data['errors'] or 'none'}")
    save_raw_data(firm_input, raw_data)
    return raw_data
