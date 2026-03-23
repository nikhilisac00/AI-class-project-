"""
SEC EDGAR & IAPD Client
Pulls real data from:
  - IAPD (Investment Adviser Public Disclosure): adviser search + ADV filing detail
  - SEC EDGAR full-text search: 13F filings
  - SEC EDGAR submissions API: filing history

All URLs are public, no auth required.
"""

import time
import requests

IAPD_SEARCH   = "https://api.adviserinfo.sec.gov/search/firm"
IAPD_DETAIL   = "https://api.adviserinfo.sec.gov/search/firm/{crd}"
EDGAR_SEARCH  = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMIT  = "https://data.sec.gov/submissions/{cik}.json"
EDGAR_FILING  = "https://www.sec.gov/Archives/edgar/full-index/"

HEADERS = {
    "User-Agent": "AI-Alternatives-Research nikhilisac00@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}


def _get(url: str, params: dict = None, retries: int = 3) -> dict | None:
    """GET with polite retry. Returns parsed JSON or None on failure."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                time.sleep(2 ** attempt)
            else:
                print(f"[EDGAR] HTTP {r.status_code} on {url}: {e}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"[EDGAR] Request error on {url}: {e}")
            time.sleep(1)
    return None


def _get_text(url: str, retries: int = 3) -> str | None:
    """GET raw text (for filing documents)."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.exceptions.RequestException as e:
            print(f"[EDGAR] Text fetch error on {url}: {e}")
            time.sleep(1)
    return None


# ─── IAPD: Investment Adviser search ──────────────────────────────────────────

def search_adviser_by_name(name: str, max_results: int = 5) -> list[dict]:
    """
    Search IAPD for RIAs by firm name.
    Returns list of {crd, firm_name, sec_number, ...}.
    """
    params = {
        "query": name,
        "hl": "true",
        "nrows": max_results,
        "start": 0,
        "r": max_results,
        "sort": "score+desc",
        "wt": "json",
    }
    data = _get(IAPD_SEARCH, params=params)
    if not data:
        return []
    hits = data.get("hits", {}).get("hits", [])
    results = []
    for h in hits:
        src = h.get("_source", {})
        results.append({
            "crd": src.get("org_pk"),
            "firm_name": src.get("org_nm"),
            "sec_number": src.get("sec_number"),
            "city": src.get("st_cd"),
            "state": src.get("state_cd"),
            "registration_status": src.get("registration_status"),
        })
    return results


def get_adviser_detail(crd: str) -> dict | None:
    """
    Pull full IAPD detail for a CRD number.
    Returns raw JSON from the IAPD API (includes ADV sections).
    """
    url = IAPD_DETAIL.format(crd=crd)
    data = _get(url)
    return data


def extract_adv_summary(iapd_detail: dict) -> dict:
    """
    Parse IAPD detail JSON into a clean ADV summary dict.
    Only uses fields actually present in the API response — no inference.
    """
    if not iapd_detail:
        return {}

    hits = iapd_detail.get("hits", {}).get("hits", [])
    if not hits:
        return {}

    src = hits[0].get("_source", {})

    # Core firm info
    summary = {
        "firm_name": src.get("org_nm"),
        "crd_number": src.get("org_pk"),
        "sec_number": src.get("sec_number"),
        "registration_status": src.get("registration_status"),
        "registration_date": src.get("registration_date"),
        "city": src.get("st_cd"),
        "state": src.get("state_cd"),
        "website": src.get("website_addresses", [None])[0] if src.get("website_addresses") else None,
    }

    # AUM & client counts from latest ADV
    latest_filing = src.get("latest_filing", {})
    adv_data = latest_filing.get("form_adv", {})

    part1 = adv_data.get("part1", {})
    summary["aum_regulatory"] = part1.get("assets_under_management")
    summary["num_clients"] = part1.get("number_of_clients")
    summary["num_accounts"] = part1.get("number_of_accounts")
    summary["num_employees"] = part1.get("number_of_employees")
    summary["num_investment_advisers"] = part1.get("number_of_investment_advisers")

    # Fee structures
    part2 = adv_data.get("part2", {})
    summary["fee_types"] = part2.get("advisory_fee_types", [])
    summary["min_account_size"] = part2.get("minimum_account_size")

    # Key personnel (Item 1 / Schedule A)
    summary["key_personnel"] = []
    for person in src.get("ind_details", []):
        summary["key_personnel"].append({
            "name": person.get("ind_nm"),
            "crd": person.get("ind_pk"),
            "title": person.get("titles", []),
            "ownership_pct": person.get("ownership_pct"),
        })

    # Disciplinary history flags (Item 11)
    disc = src.get("disclosure_info", {})
    summary["has_disclosures"] = bool(disc)
    summary["disclosure_count"] = disc.get("total_disclosures", 0) if disc else 0
    summary["disclosure_types"] = list(disc.keys()) if disc else []

    # Regulatory / registration details
    summary["registrations"] = src.get("registrations", [])

    return summary


# ─── EDGAR: 13F filings ───────────────────────────────────────────────────────

def search_13f_filings(firm_name: str, max_results: int = 5) -> list[dict]:
    """
    Search EDGAR full-text for 13F-HR filings by firm name.
    Returns list of {accession_number, filing_date, entity_name, ...}.
    """
    params = {
        "q": f'"{firm_name}"',
        "forms": "13F-HR",
        "dateRange": "custom",
        "startdt": "2024-01-01",
        "_source": "period_of_report,file_date,entity_name,file_num",
        "hits.hits._source": "period_of_report,file_date,entity_name",
        "hits.hits.total.value": max_results,
    }
    data = _get(EDGAR_SEARCH, params=params)
    if not data:
        return []
    hits = data.get("hits", {}).get("hits", [])
    results = []
    for h in hits:
        src = h.get("_source", {})
        results.append({
            "entity_name": src.get("entity_name"),
            "accession_number": h.get("_id"),
            "filing_date": src.get("file_date"),
            "period_of_report": src.get("period_of_report"),
        })
    return results


def get_submissions_by_cik(cik: str) -> dict | None:
    """
    Pull filing history for an entity by SEC CIK number.
    CIK must be zero-padded to 10 digits, e.g. '0001234567'.
    """
    cik_padded = cik.zfill(10)
    url = EDGAR_SUBMIT.format(cik=f"CIK{cik_padded}")
    return _get(url)
