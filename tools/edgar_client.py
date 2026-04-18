"""
SEC EDGAR & IAPD Client
Pulls real data from:
  - IAPD (Investment Adviser Public Disclosure): adviser search + ADV filing detail
  - SEC EDGAR full-text search: 13F filings, company filings
  - SEC EDGAR company API: filing history

All URLs are public. No auth required.
Field names are verified against live API responses.
"""

import json
import time
import requests

IAPD_SEARCH   = "https://api.adviserinfo.sec.gov/search/firm"
IAPD_DETAIL   = "https://api.adviserinfo.sec.gov/search/firm/{crd}"
EDGAR_EFTS    = "https://efts.sec.gov/LATEST/search-index"
EDGAR_COMPANY = "https://www.sec.gov/cgi-bin/browse-edgar"
EDGAR_SUBMIT  = "https://data.sec.gov/submissions/CIK{cik}.json"

HEADERS = {
    "User-Agent": "AI-Alternatives-Research contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}


def _get(url: str, params: dict = None, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError:
            if r.status_code == 429:
                wait = 2 ** attempt
                print(f"[EDGAR] Rate limited (429) — retrying in {wait}s")
                time.sleep(wait)
            else:
                print(f"[EDGAR] HTTP {r.status_code} → {url}")
                return None
        except requests.exceptions.Timeout:
            # Bug #9: explicit Timeout handling with retry backoff
            wait = 2 ** attempt
            print(f"[EDGAR] Request timed out (attempt {attempt + 1}/{retries}) — retrying in {wait}s")
            time.sleep(wait)
        except requests.exceptions.RequestException as e:
            print(f"[EDGAR] Request error: {e}")
            time.sleep(1)
    return None


# ─── IAPD: search ─────────────────────────────────────────────────────────────

def search_adviser_by_name(name: str, max_results: int = 5) -> list[dict]:
    """
    Search IAPD for RIAs by firm name.
    Field names verified against live API response.
    """
    params = {
        "query": name,
        "hl": "true",
        "nrows": max_results,
        "start": 0,
        "r": max_results,
        "wt": "json",
    }
    data = _get(IAPD_SEARCH, params=params)
    if not data:
        return []

    hits = data.get("hits", {}).get("hits", [])
    results = []
    for h in hits:
        src = h.get("_source", {})
        # Parse address from embedded JSON string
        addr = {}
        addr_raw = src.get("firm_ia_address_details", "")
        if addr_raw:
            try:
                addr = json.loads(addr_raw).get("officeAddress", {})
            except (json.JSONDecodeError, AttributeError):
                pass

        results.append({
            "crd": src.get("firm_source_id"),
            "firm_name": src.get("firm_name"),
            "sec_number": src.get("firm_ia_full_sec_number"),
            "registration_status": src.get("firm_ia_scope") if isinstance(src.get("firm_ia_scope"), str) else str(src.get("firm_ia_scope", "")),
            "has_disclosures": src.get("firm_ia_disclosure_fl") == "Y",
            "city": addr.get("city"),
            "state": addr.get("state"),
        })
    return results


def get_adviser_detail(crd: str) -> dict | None:
    """
    Pull full IAPD detail for a CRD number.
    Returns the parsed iacontent dict (contains basicInformation, registrationStatus, etc.)
    """
    url = IAPD_DETAIL.format(crd=crd)
    data = _get(url)
    if not data:
        return None

    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return None

    src = hits[0].get("_source", {})
    iacontent_raw = src.get("iacontent", "")
    if not iacontent_raw:
        return None

    try:
        return json.loads(iacontent_raw)
    except json.JSONDecodeError:
        return None


def extract_adv_summary(iacontent: dict, search_hit: dict = None) -> dict:
    """
    Parse IAPD iacontent dict into a clean ADV summary.
    Only uses fields actually present in the real API response.
    search_hit: the matching search result dict (for extra fields)
    """
    if not iacontent:
        return {}

    basic = iacontent.get("basicInformation", {})
    scope_flags = iacontent.get("orgScopeStatusFlags", {})
    address_details = iacontent.get("iaFirmAddressDetails", {})
    brochures = iacontent.get("brochures", [])
    notice_filings = iacontent.get("noticeFilings", [])

    # Address parsing
    addr = {}
    if isinstance(address_details, list) and address_details:
        addr = address_details[0].get("officeAddress", {})
    elif isinstance(address_details, dict):
        addr = address_details.get("officeAddress", {})

    # Brochure URLs (Part 2A/2B)
    brochure_urls = []
    if isinstance(brochures, list):
        for b in brochures:
            if isinstance(b, dict) and b.get("fileId"):
                brochure_urls.append(b.get("fileId"))

    summary = {
        "firm_name": basic.get("firmName"),
        "crd_number": basic.get("firmId"),
        "sec_number": f"{basic.get('iaSECNumberType','')}-{basic.get('iaSECNumber','')}".strip("-"),
        "registration_status": basic.get("iaScope"),
        "adv_filing_date": basic.get("advFilingDate"),
        "has_pdf": basic.get("hasPdf") == "Y",

        # Registration flags
        "is_sec_registered": scope_flags.get("isSECRegistered") == "Y",
        "is_state_registered": scope_flags.get("isStateRegistered") == "Y",
        "is_era_registered": scope_flags.get("isERARegistered") == "Y",

        # Address
        "city": addr.get("city"),
        "state": addr.get("state"),
        "country": addr.get("country"),
        "postal_code": addr.get("postalCode"),

        # Notice filings (state registrations)
        "notice_filing_states": [
            nf.get("stateCode") for nf in notice_filings
            if isinstance(nf, dict) and nf.get("stateCode")
        ],

        # Brochures
        "brochure_file_ids": brochure_urls,

        # From search results (if provided)
        "has_disclosures": search_hit.get("has_disclosures") if search_hit else None,

        # Fields not available in this API — must be obtained from ADV Part 1 PDF/XML
        "aum_regulatory": None,     # Not in IAPD API — in ADV Part 1 Item 5
        "num_clients": None,        # Not in IAPD API — in ADV Part 1 Item 5
        "num_employees": None,      # Not in IAPD API — in ADV Part 1 Item 5
        "fee_types": [],            # Not in IAPD API — in ADV Part 2
        "min_account_size": None,   # Not in IAPD API — in ADV Part 2
        "key_personnel": [],        # Not in IAPD API — in Schedule A/B
    }

    return summary


# ─── EDGAR: 13F filings ───────────────────────────────────────────────────────

def search_13f_filings(firm_name: str, max_results: int = 5) -> list[dict]:
    """
    Search EDGAR full-text for 13F-HR filings by firm name.
    Uses EFTS API with correct field names from live API inspection.
    """
    params = {
        "q": f'"{firm_name}"',
        "forms": "13F-HR",
    }
    data = _get(EDGAR_EFTS, params=params)
    if not data:
        return []

    hits = data.get("hits", {}).get("hits", [])[:max_results]
    results = []
    for h in hits:
        src = h.get("_source", {})
        results.append({
            "entity_name": src.get("display_names", [None])[0] if src.get("display_names") else None,
            "cik": src.get("ciks", [None])[0] if src.get("ciks") else None,
            "accession_number": src.get("adsh"),
            "filing_date": src.get("file_date"),
            "period_ending": src.get("period_ending"),
            "form": src.get("form"),
            "description": src.get("file_description"),
        })
    return results


def search_13f_by_cik(cik: str, max_results: int = 5) -> list[dict]:
    """
    Pull 13F-HR filings for a known CIK directly from EDGAR submissions API.
    More accurate than name-based search when CIK is known.
    """
    cik_padded = cik.lstrip("0").zfill(10)
    submissions = get_submissions_by_cik(cik_padded)
    if not submissions:
        return []

    filings = submissions.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    descriptions = filings.get("primaryDocument", [])

    results = []
    for i, form in enumerate(forms):
        if form in ("13F-HR", "13F-HR/A") and len(results) < max_results:
            results.append({
                "entity_name": submissions.get("name"),
                "cik": cik,
                "accession_number": accessions[i] if i < len(accessions) else None,
                "filing_date": dates[i] if i < len(dates) else None,
                "period_ending": None,  # not in submissions API directly
                "form": form,
                "description": descriptions[i] if i < len(descriptions) else None,
            })
    return results


def get_submissions_by_cik(cik: str) -> dict | None:
    """
    Pull filing history for an entity by SEC CIK (zero-padded to 10 digits).
    E.g. cik='1234567' → fetches CIK0001234567.json
    """
    cik_padded = cik.zfill(10)
    url = EDGAR_SUBMIT.format(cik=cik_padded)
    return _get(url)
