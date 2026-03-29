"""
SEC Enforcement Client
======================
Aggregates enforcement and disciplinary history for an investment adviser.

Data sources:
  1. IAPD iacontent disclosure arrays — only present for some firms/API responses.
     The public IAPD API (`api.adviserinfo.sec.gov/search/firm/{crd}`) returns a
     lightweight iacontent that often OMITS the disclosure arrays.  We attempt the
     parse and fall back gracefully.
  2. Web search (Tavily / DuckDuckGo) — primary enforcement discovery when IAPD
     arrays are absent.  Searches SEC.gov, FINRA, regulatory news for the firm.
  3. EDGAR EFTS full-text search — UPLOAD/CORRESP form types and enforcement-
     adjacent filings from the firm's EDGAR CIK.
  4. EDGAR submissions scan — ADV-W registration withdrawal, UPLOAD orders.

Key output fields per action:
  action_type  : Regulatory / Criminal / Civil / Arbitration / Web
  initiated_by : SEC / FINRA / State / CFTC / DOJ / Unknown
  date         : ISO date string
  description  : what the action alleged
  sanctions    : list of sanction strings (Bar, Suspension, Fine, Censure, …)
  penalty_usd  : numeric penalty if extractable
  resolution   : Settled / Dismissed / Final Order / Pending / …
  severity     : HIGH / MEDIUM / LOW  (rule-based)
  source       : IAPD / Web search / EDGAR EFTS / EDGAR Submissions
"""

import re
import time
import requests
from typing import Optional

EFTS_URL    = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
HEADERS = {
    "User-Agent": "AI-Alternatives-Research research@example.com",
    "Accept-Encoding": "gzip, deflate",
}

# Sanction keywords → severity
_HIGH_SANCTIONS = {
    "bar", "barred", "permanent bar", "industry bar", "expulsion",
    "revocation", "revoked", "cancellation", "suspension", "suspended",
    "injunction", "disgorgement", "fraud", "felony", "criminal",
}
_MEDIUM_SANCTIONS = {
    "censure", "cease-and-desist", "cease and desist", "reprimand",
    "fine", "penalty", "civil money penalty", "undertakings", "undertaking",
    "restitution",
}

# EDGAR form types that may signal enforcement / unusual activity
_ENFORCEMENT_FORMS = {"UPLOAD", "CORRESP", "ADV-W", "40-OIP", "40-APP", "40-APP/A"}

# Skip these common non-enforcement forms in EFTS results
_SKIP_FORMS = {
    "13F-HR", "13F-HR/A", "D", "D/A", "ADV", "ADV/A", "ADV-W",
    "SC 13G", "SC 13G/A", "SC 13D", "SC 13D/A",
    "4", "3", "5", "144", "NPORT-P", "NPORT-P/A",
}

# Regulator name normalisation
_INITIATOR_MAP = {
    "sec":                       "SEC",
    "securities and exchange":   "SEC",
    "finra":                     "FINRA",
    "nasd":                      "FINRA",
    "cftc":                      "CFTC",
    "state":                     "State",
    "doj":                       "DOJ",
    "department of justice":     "DOJ",
    "fbi":                       "FBI",
    "nyag":                      "NY AG",
    "osc":                       "OSC",
}


# ── HTTP helper ────────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None) -> Optional[dict]:
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError:
            if r.status_code == 429:
                time.sleep(2 ** attempt)
            else:
                return None
        except Exception:
            time.sleep(1)
    return None


# ── Utility helpers ────────────────────────────────────────────────────────────

def _classify_severity(sanctions: list, description: str) -> str:
    combined = " ".join(list(sanctions) + [description or ""]).lower()
    if any(s in combined for s in _HIGH_SANCTIONS):
        return "HIGH"
    if any(s in combined for s in _MEDIUM_SANCTIONS):
        return "MEDIUM"
    return "LOW"


def _parse_penalty(text: Optional[str]) -> Optional[int]:
    """Extract numeric value from strings like '$1,250,000' or '1,250,000'."""
    if not text:
        return None
    clean = re.sub(r"[$,]", "", str(text))
    m = re.search(r"\d+(?:\.\d+)?", clean)
    if m:
        try:
            return int(float(m.group()))
        except ValueError:
            pass
    return None


def _fmt_penalty(amt: Optional[int]) -> Optional[str]:
    if not amt:
        return None
    if amt >= 1_000_000:
        return f"${amt / 1e6:.2f}M"
    if amt >= 1_000:
        return f"${amt / 1e3:.0f}K"
    return f"${amt:,}"


def _normalize_initiator(text: str) -> str:
    if not text:
        return "Unknown"
    t = text.lower()
    for key, label in _INITIATOR_MAP.items():
        if key in t:
            return label
    return text.strip()[:40]


# ── Source 1: IAPD deep parse ──────────────────────────────────────────────────

_KEY_TO_TYPE = {
    "iaCriminalDisclosures":    "Criminal",
    "iaRegulatoryDisclosures":  "Regulatory",
    "iaCivilDisclosures":       "Civil",
    "iaArbitrationDisclosures": "Arbitration",
    "iaEmploymentDisclosures":  "Employment",
    "iaOrgDisclosures":         "Organizational",
    "disclosures":              "Regulatory",
}


def parse_iapd_enforcement(iacontent: dict) -> list:
    """
    Deep parse of ALL IAPD disclosure arrays → structured enforcement records.

    Extracts:
    - Penalty amounts (numeric, summed across multiple detail lines)
    - Specific sanction types
    - Initiating regulator
    - Rule-based severity (HIGH / MEDIUM / LOW)
    """
    if not iacontent:
        return []

    records = []

    for key, action_type in _KEY_TO_TYPE.items():
        items = iacontent.get(key, [])
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            # Flatten disclosureDetails into a normalised key→value dict
            details_kv: dict = {}
            raw_details = item.get("disclosureDetails") or item.get("details") or []
            if isinstance(raw_details, list):
                for d in raw_details:
                    if not isinstance(d, dict):
                        continue
                    label = (
                        d.get("disclosureDetailType")
                        or d.get("label") or d.get("key") or ""
                    ).strip().lower()
                    value = d.get("disclosureDetailValue") or d.get("value") or ""
                    if label:
                        details_kv[label] = str(value).strip()

            # Description / allegations
            description = (
                item.get("disclosureType")
                or details_kv.get("allegations")
                or details_kv.get("description")
                or details_kv.get("action")
                or ""
            )

            # Resolution status
            resolution = (
                item.get("disclosureResolution")
                or details_kv.get("resolution")
                or details_kv.get("resolution status")
                or details_kv.get("current status")
                or ""
            )

            # Sanctions list
            sanctions: list = []
            for k in (
                "principal sanction", "additional sanction(s)", "sanctions",
                "sanction", "sanction details", "action taken",
            ):
                v = details_kv.get(k, "")
                if v and v.lower() not in ("n/a", "none", ""):
                    sanctions.append(v)
            if not sanctions and description:
                sanctions = [description]

            # Penalty — sum across multiple detail fields
            penalty_usd: Optional[int] = None
            for k in (
                "penalty amount", "fine", "disgorgement",
                "civil money penalty", "monetary penalty", "amount",
            ):
                parsed = _parse_penalty(details_kv.get(k))
                if parsed and parsed > 0:
                    penalty_usd = (penalty_usd or 0) + parsed
            # Also try top-level penaltyAmount (some IAPD versions)
            top_penalty = _parse_penalty(str(item.get("penaltyAmount") or ""))
            if top_penalty and top_penalty > (penalty_usd or 0):
                penalty_usd = top_penalty

            initiated_by = _normalize_initiator(
                details_kv.get("initiated by")
                or details_kv.get("regulator")
                or details_kv.get("regulatory authority")
                or str(item.get("regulatoryAuthority") or "")
            )

            severity = _classify_severity(sanctions, description)
            if action_type == "Criminal":
                severity = "HIGH"  # criminal is always high

            records.append({
                "action_type":  action_type,
                "initiated_by": initiated_by,
                "date": (
                    item.get("disclosureDate")
                    or item.get("eventDate")
                    or details_kv.get("date")
                    or details_kv.get("action date")
                    or details_kv.get("initiated")
                ),
                "description":  description,
                "sanctions":    sanctions,
                "penalty_usd":  penalty_usd,
                "penalty_fmt":  _fmt_penalty(penalty_usd),
                "resolution":   resolution,
                "severity":     severity,
                "raw_details":  details_kv,
                "source":       "IAPD",
            })

    # Sort: HIGH first, then by date desc
    _sev = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    records.sort(key=lambda x: (
        _sev.get(x["severity"], 9),
        -(int(str(x.get("date") or "0")[:4])
          if str(x.get("date") or "")[:4].isdigit() else 0),
    ))
    return records


# ── Source 2: Web search enforcement discovery ────────────────────────────────

_ENFORCEMENT_QUERIES = [
    '"{name}" SEC enforcement action settlement penalty',
    '"{name}" FINRA fine suspension bar regulatory action',
    '"{name}" SEC "cease-and-desist" OR "fraud" OR "investment adviser" violation',
]

_WEB_ENFORCEMENT_KEYWORDS = {
    "enforcement", "settlement", "penalty", "fine", "bar", "suspension",
    "cease-and-desist", "cease and desist", "fraud", "violation", "sanction",
    "disgorgement", "injunction", "criminal", "indictment", "action taken",
    "regulatory action", "disciplinary", "ordered to pay",
}


def web_search_enforcement(firm_name: str, tavily_key: str = None) -> list:
    """
    Search web (Tavily → ddgs) for SEC/FINRA enforcement actions.
    Returns up to 8 relevant search hits as dicts with title/url/snippet/date.
    """
    results = []
    seen_urls: set = set()

    # ── Try Tavily first (better quality, needs API key) ──────────────────
    if tavily_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)
            for template in _ENFORCEMENT_QUERIES[:2]:
                query = template.format(name=firm_name)
                resp = client.search(query, search_depth="advanced", max_results=5,
                                     include_answer=False)
                for r in resp.get("results", []):
                    url     = r.get("url", "")
                    content = (r.get("content") or "").lower()
                    if url not in seen_urls and any(
                        kw in content for kw in _WEB_ENFORCEMENT_KEYWORDS
                    ):
                        seen_urls.add(url)
                        results.append({
                            "title":   r.get("title", ""),
                            "url":     url,
                            "snippet": (r.get("content") or "")[:500],
                            "date":    r.get("published_date"),
                            "source":  "tavily",
                        })
                        if len(results) >= 8:
                            return results
        except Exception:
            pass

    if results:
        return results

    # ── Fallback: ddgs (new package name for duckduckgo-search) ──────────
    for package in ("ddgs", "duckduckgo_search"):
        try:
            mod = __import__(package, fromlist=["DDGS"])
            DDGS = mod.DDGS
            for template in _ENFORCEMENT_QUERIES[:2]:
                query = template.format(name=firm_name)
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        with DDGS() as ddgs:
                            hits = list(ddgs.text(query, max_results=5))
                    for h in hits:
                        url     = h.get("href", "")
                        content = (h.get("body") or "").lower()
                        if url not in seen_urls and any(
                            kw in content for kw in _WEB_ENFORCEMENT_KEYWORDS
                        ):
                            seen_urls.add(url)
                            snippet = (h.get("body") or "")[:500]
                            results.append({
                                "title":   h.get("title", ""),
                                "url":     url,
                                "snippet": snippet,
                                "date":    None,
                                "source":  "ddgs",
                            })
                            if len(results) >= 8:
                                return results
                except Exception:
                    pass
            if results:
                return results   # first working package is enough
        except ImportError:
            continue

    return results


# ── Source 3: EDGAR EFTS enforcement search ────────────────────────────────────

def search_edgar_enforcement(firm_name: str, cik: str = None) -> list:
    """
    Full-text EDGAR search for enforcement-adjacent filings (UPLOAD, CORRESP, etc.)
    mentioning this firm.  Returns up to 10 hits.
    """
    params = {
        "q":         f'"{firm_name}"',
        "dateRange": "custom",
        "startdt":   "2000-01-01",
    }
    data = _get(EFTS_URL, params=params)
    if not data:
        return []

    hits   = data.get("hits", {}).get("hits", [])
    seen   = set()
    results = []

    for h in hits:
        src       = h.get("_source", {})
        acc       = src.get("adsh", "")
        form_type = src.get("form", "").upper()

        if acc in seen or form_type in _SKIP_FORMS:
            continue

        # Accept UPLOAD/CORRESP (SEC staff enforcement uploads) or flag via keyword
        is_enforcement_form = form_type in _ENFORCEMENT_FORMS
        display = " ".join([
            str(src.get("display_names", "")),
            form_type,
        ]).lower()
        has_enforcement_hint = any(
            kw in display for kw in
            ("cease", "order", "sanction", "penalty", "violation",
             "enforcement", "proceeding", "bar", "suspension")
        )

        if is_enforcement_form or has_enforcement_hint:
            ciks     = src.get("ciks", [])
            filing_cik = str(int(ciks[0])) if ciks else cik
            seen.add(acc)
            results.append({
                "form_type":  form_type,
                "file_date":  src.get("file_date"),
                "accession":  acc,
                "cik":        filing_cik,
                "edgar_url":  (
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                    f"&CIK={filing_cik}&type={form_type}&dateb=&owner=include&count=5"
                    if filing_cik else None
                ),
                "source": "EDGAR EFTS",
            })
            if len(results) >= 10:
                break

    time.sleep(0.2)
    return results


# ── Source 3: EDGAR submissions scan ──────────────────────────────────────────

def scan_submissions_for_enforcement(cik: str) -> list:
    """
    Scan the firm's EDGAR submissions JSON for unusual form types
    (ADV-W withdrawal, UPLOAD enforcement orders, etc.).
    """
    if not cik:
        return []

    data = _get(SUBMISSIONS.format(cik=str(cik).zfill(10)))
    if not data:
        return []

    recent   = data.get("filings", {}).get("recent", {})
    forms     = recent.get("form", [])
    dates     = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])

    results = []
    for form, date, acc in zip(forms, dates, accessions):
        if form.upper() in _ENFORCEMENT_FORMS:
            results.append({
                "form_type": form,
                "file_date": date,
                "accession": acc,
                "source":    "EDGAR Submissions",
            })
    return results


# ── Aggregate ──────────────────────────────────────────────────────────────────

def fetch_enforcement_data(
    firm_name:           str,
    crd:                 str = None,
    cik:                 str = None,
    iacontent:           dict = None,
    has_disclosure_flag: bool = False,
    tavily_key:          str = None,
) -> dict:
    """
    Full enforcement data aggregation for an investment adviser.

    Args:
        has_disclosure_flag : True if IAPD search result had firm_ia_disclosure_fl=Y.
                              Ensures we still run web search even when iacontent
                              arrays are absent (as is common with the public API).
        tavily_key          : optional Tavily key for better web search results.

    Returns:
        actions            : list of IAPD enforcement action dicts
        web_results        : list of web-search-derived enforcement hits
        edgar_hits         : EDGAR EFTS enforcement-adjacent filings
        edgar_flags        : unusual form types in EDGAR submissions
        iapd_flag          : bool — IAPD indicated disclosures on record
        total_actions      : int
        high_count         : int
        medium_count       : int
        penalty_total_usd  : total numeric penalties or None
        penalty_total_fmt  : formatted string or None
        open_actions       : subset of actions without clear resolution
        sources_used       : list of source labels
        errors             : list of error strings
    """
    report: dict = {
        "actions":           [],
        "web_results":       [],
        "edgar_hits":        [],
        "edgar_flags":       [],
        "iapd_flag":         has_disclosure_flag,
        "total_actions":     0,
        "high_count":        0,
        "medium_count":      0,
        "penalty_total_usd": None,
        "penalty_total_fmt": None,
        "open_actions":      [],
        "sources_used":      [],
        "errors":            [],
    }

    # Source 1: IAPD disclosure arrays (when available)
    if iacontent:
        try:
            actions = parse_iapd_enforcement(iacontent)
            report["actions"] = actions
            if actions:
                report["sources_used"].append("IAPD disclosures")
        except Exception as e:
            report["errors"].append(f"IAPD parse error: {e}")

    # Source 2: Web search — primary when IAPD arrays absent or flag is set
    if has_disclosure_flag or not report["actions"]:
        try:
            web_hits = web_search_enforcement(firm_name, tavily_key=tavily_key)
            report["web_results"] = web_hits
            if web_hits:
                report["sources_used"].append("Web search (SEC / FINRA news)")
        except Exception as e:
            report["errors"].append(f"Web search error: {e}")

    # Source 3: EDGAR EFTS
    try:
        edgar_hits = search_edgar_enforcement(firm_name, cik=cik)
        report["edgar_hits"] = edgar_hits
        if edgar_hits:
            report["sources_used"].append("EDGAR EFTS")
    except Exception as e:
        report["errors"].append(f"EDGAR EFTS search error: {e}")

    # Source 3: EDGAR submissions
    if cik:
        try:
            flags = scan_submissions_for_enforcement(cik)
            report["edgar_flags"] = flags
            if flags:
                report["sources_used"].append("EDGAR Submissions")
        except Exception as e:
            report["errors"].append(f"EDGAR submissions scan error: {e}")

    # Aggregate statistics
    actions = report["actions"]
    report["total_actions"] = len(actions)
    report["high_count"]    = sum(1 for a in actions if a["severity"] == "HIGH")
    report["medium_count"]  = sum(1 for a in actions if a["severity"] == "MEDIUM")

    total_penalty = sum(a["penalty_usd"] for a in actions if a.get("penalty_usd"))
    if total_penalty:
        report["penalty_total_usd"] = total_penalty
        report["penalty_total_fmt"] = _fmt_penalty(total_penalty)

    # Open / unresolved
    _open_kw = {"pending", "open", "in progress", "unresolved", "not resolved"}
    report["open_actions"] = [
        a for a in actions
        if not a.get("resolution")
        or any(kw in (a.get("resolution") or "").lower() for kw in _open_kw)
    ]

    return report
