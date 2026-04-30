"""
SEC EDGAR & IAPD Client
Pulls real data from:
  - IAPD (Investment Adviser Public Disclosure): adviser search + ADV filing detail
  - SEC EDGAR full-text search: 13F filings, company filings
  - SEC EDGAR company API: filing history
  - ADV PDF (Part 1A): Schedule D Section 7.B private fund data

All URLs are public. No auth required.
Field names are verified against live API responses.
"""

import io
import json
import re
import time
import requests

IAPD_SEARCH   = "https://api.adviserinfo.sec.gov/search/firm"
IAPD_DETAIL   = "https://api.adviserinfo.sec.gov/search/firm/{crd}"
ADV_PDF_URL   = "https://reports.adviserinfo.sec.gov/reports/ADV/{crd}/PDF/{crd}.pdf"
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


# ─── ADV PDF: Section 7.B private fund data ──────────────────────────────────

# Max PDF size to download (bytes). ADV PDFs for large firms can be 30-50 MB.
_ADV_PDF_MAX_SIZE = 60 * 1024 * 1024  # 60 MB


def fetch_adv_pdf_text(crd: str) -> str | None:
    """
    Download the ADV Part 1A PDF and extract full text via pypdf.
    Returns extracted text or None if download/parse fails.
    """
    url = ADV_PDF_URL.format(crd=crd)
    print(f"[EDGAR] Downloading ADV PDF for CRD {crd}...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=90, stream=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        print(f"[EDGAR] ADV PDF download failed: {exc}")
        return None

    content_type = resp.headers.get("content-type", "")
    if "pdf" not in content_type and "octet" not in content_type:
        print(f"[EDGAR] ADV PDF unexpected content-type: {content_type}")
        return None

    # Stream into memory with size guard
    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=256 * 1024):
        total += len(chunk)
        if total > _ADV_PDF_MAX_SIZE:
            print(f"[EDGAR] ADV PDF exceeds {_ADV_PDF_MAX_SIZE // (1024*1024)} MB limit — aborting")
            return None
        chunks.append(chunk)

    pdf_bytes = b"".join(chunks)
    print(f"[EDGAR] ADV PDF downloaded ({total / (1024*1024):.1f} MB)")

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        full_text = "\n".join(pages_text)
        print(f"[EDGAR] ADV PDF parsed — {len(reader.pages)} pages, {len(full_text)} chars")
        return full_text
    except ImportError:
        print("[EDGAR] pypdf not installed — cannot parse ADV PDF")
        return None
    except Exception as exc:
        print(f"[EDGAR] ADV PDF parse error: {exc}")
        return None


# Known field label phrases in Section 7.B — used by the normalizer to rejoin
# labels that pypdf splits across lines due to column/wrapping layouts.
_SECTION_7B_LABELS = [
    "Name of the private fund",
    "Type of private fund",
    "Gross asset value",
    "Number of beneficial owners",
    "Is the private fund a feeder fund",
    "Regulatory assets under management",
]


def _normalize_pdf_text(text: str) -> str:
    """
    Pre-process PDF-extracted text to fix common pypdf layout artifacts
    before Section 7.B regex parsing.

    Three passes:
    1. Remove standalone page-number lines (only digits on a line).
    2. Rejoin known field label phrases that pypdf split across a line break
       e.g. "Name of the private\nfund:" → "Name of the private fund:"
    3. Collapse "label:\n  value" patterns into "label: value" so the value
       lands on the same line as the label colon.
    """
    # Pass 1: remove bare page numbers
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)

    # Pass 2: rejoin wrapped label phrases
    for phrase in _SECTION_7B_LABELS:
        words = phrase.split()
        pat = r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b"
        text = re.sub(pat, phrase, text, flags=re.IGNORECASE)

    # Pass 3: collapse ":\n<whitespace>value" → ": value"
    text = re.sub(r":\s*\n[ \t]+", ": ", text)

    return text


def parse_section_7b(text: str, deadline: float | None = None) -> list[dict]:
    """
    Extract private fund data from ADV Part 1A Section 7.B PDF text.

    Each fund entry in Section 7.B typically contains:
      - Fund name
      - Fund type (hedge fund, PE, VC, liquidity fund, etc.)
      - Gross asset value
      - Number of beneficial owners
      - Whether the fund is a feeder fund
      - Regulatory AUM attributable to the fund

    If *deadline* (``time.monotonic()`` timestamp) is provided, parsing
    stops early and returns whatever funds were successfully parsed so far.

    Returns a list of dicts, one per fund. Fields are None when not found.
    """
    if not text:
        return []

    # Normalize before any regex work so patterns are robust to pypdf artifacts
    text = _normalize_pdf_text(text)

    funds: list[dict] = []

    # Section 7.B in ADV PDFs uses "SECTION 7.B" or "Schedule D, Section 7.B"
    # Each private fund block starts with a fund name and has structured fields.
    # The PDF text layout varies, but funds are delimited by repeated headers
    # like "Private Fund Name:" or by the pattern "SECTION 7.B.(1)" numbering.

    # Strategy: find the Section 7.B region, then split into per-fund blocks
    section_start = _find_section_7b_start(text)
    if section_start < 0:
        print("[EDGAR] Section 7.B not found in ADV PDF text")
        return []

    # Find where Section 7.B ends (next major section like Section 8, 9, etc.)
    section_end = _find_section_7b_end(text, section_start)
    section_text = text[section_start:section_end]

    # Split into individual fund blocks
    # Funds are separated by headers like "Name of the private fund:"
    fund_blocks = re.split(
        r"(?i)(?=Name\s+of\s+the\s+private\s+fund\s*:)",
        section_text,
    )

    for block in fund_blocks:
        if deadline and time.monotonic() > deadline:
            print(f"[EDGAR] Section 7.B deadline reached — returning {len(funds)} fund(s) parsed so far")
            break
        if len(block.strip()) < 30:
            continue
        fund = _parse_fund_block(block)
        if fund and fund.get("fund_name"):
            funds.append(fund)

    print(f"[EDGAR] Section 7.B parsed — {len(funds)} private fund(s) found")
    return funds


def _find_section_7b_start(text: str) -> int:
    """Locate the start of Section 7.B in ADV PDF text."""
    patterns = [
        r"(?i)SECTION\s+7\.?\s*B",
        r"(?i)Schedule\s+D.*?Section\s+7\.?\s*B",
        r"(?i)Item\s+7\.?\s*B\b.*?Private\s+Fund",
        r"(?i)PRIVATE\s+FUND\s+REPORTING",
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            return match.start()
    return -1


def _find_section_7b_end(text: str, start: int) -> int:
    """Find where Section 7.B ends (start of next major section)."""
    # Look for Section 8, 9, 10, or Part 2 / Schedule markers after the start
    patterns = [
        r"(?i)SECTION\s+[89]\b",
        r"(?i)Item\s+[89]\b",
        r"(?i)PART\s+2[AB]?\b",
        r"(?i)Schedule\s+[A-C]\b",
        r"(?i)SECTION\s+1[0-9]",
    ]
    earliest = len(text)
    for pat in patterns:
        match = re.search(pat, text[start + 100:])
        if match:
            pos = start + 100 + match.start()
            if pos < earliest:
                earliest = pos
    return earliest


def _parse_fund_block(block: str) -> dict:
    """Parse a single private fund block from Section 7.B text."""
    fund: dict = {
        "fund_name": None,
        "fund_type": None,
        "gross_asset_value": None,
        "number_of_beneficial_owners": None,
        "is_feeder_fund": None,
        "regulatory_aum": None,
    }

    # Fund name — typically after "Name of the private fund:"
    name_match = re.search(
        r"(?i)Name\s+of\s+the\s+private\s+fund\s*:\s*(.+?)(?:\n|$)",
        block,
    )
    if name_match:
        fund["fund_name"] = name_match.group(1).strip()

    # Fund type — hedge fund, PE, VC, liquidity fund, real estate, securitized asset
    type_match = re.search(
        r"(?i)(?:Type\s+of\s+(?:private\s+)?fund|fund\s+type)\s*:\s*(.+?)(?:\n|$)",
        block,
    )
    if type_match:
        fund["fund_type"] = type_match.group(1).strip()
    else:
        # Infer from keywords in the block
        block_lower = block.lower()
        for ftype in ["hedge fund", "private equity fund", "venture capital fund",
                       "liquidity fund", "real estate fund", "securitized asset fund",
                       "other investment fund"]:
            if ftype in block_lower:
                fund["fund_type"] = ftype.title()
                break

    # Gross asset value
    # Use [ \t]* (not \s*) before the suffix so a newline doesn't cause [MB]
    # to greedily match the first letter of the next field (e.g. "b" in "beneficial").
    # Require \b after [MB] so it only matches a standalone letter, not mid-word.
    gav_match = re.search(
        r"(?i)(?:gross\s+asset\s+value|total\s+assets?)\s*[\$:]?\s*\$?\s*([\d,]+(?:\.\d+)?)[ \t]*(million|billion|[MB]\b)?",
        block,
    )
    if gav_match:
        val = gav_match.group(1).replace(",", "")
        suffix = (gav_match.group(2) or "").lower()
        try:
            num = float(val)
            if suffix.startswith("b"):
                num *= 1_000_000_000
            elif suffix.startswith("m"):
                num *= 1_000_000
            fund["gross_asset_value"] = int(num)
        except ValueError:
            pass

    # Number of beneficial owners
    owners_match = re.search(
        r"(?i)(?:number\s+of\s+)?beneficial\s+owners?\s*:\s*(\d+)",
        block,
    )
    if owners_match:
        fund["number_of_beneficial_owners"] = int(owners_match.group(1))

    # Feeder fund flag
    feeder_match = re.search(
        r"(?i)(?:Is\s+the\s+(?:private\s+)?fund\s+a\s+)?feeder\s+fund\s*[:\?]?\s*(yes|no)",
        block,
    )
    if feeder_match:
        fund["is_feeder_fund"] = feeder_match.group(1).strip().lower() == "yes"

    # Regulatory AUM — same [ \t]* + \b fix as gross asset value above
    aum_match = re.search(
        r"(?i)(?:regulatory\s+assets?\s+under\s+management|RAUM)\s*[\$:]?\s*\$?\s*([\d,]+(?:\.\d+)?)[ \t]*(million|billion|[MB]\b)?",
        block,
    )
    if aum_match:
        val = aum_match.group(1).replace(",", "")
        suffix = (aum_match.group(2) or "").lower()
        try:
            num = float(val)
            if suffix.startswith("b"):
                num *= 1_000_000_000
            elif suffix.startswith("m"):
                num *= 1_000_000
            fund["regulatory_aum"] = int(num)
        except ValueError:
            pass

    return fund


def fetch_private_funds_section7b(crd: str, deadline: float | None = None) -> list[dict]:
    """
    High-level function: download ADV PDF for a CRD and parse Section 7.B.
    Returns list of private fund dicts, or empty list on failure.

    If *deadline* (a ``time.monotonic()`` timestamp) is provided, parsing
    stops early and returns whatever funds were parsed so far.
    """
    text = fetch_adv_pdf_text(crd)
    if not text:
        return []
    return parse_section_7b(text, deadline=deadline)


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

    # Disclosures: count events across all disclosure categories
    _disc_raw = iacontent.get("disclosures") or {}
    _disc_count = sum(
        len(v) if isinstance(v, list) else (1 if v else 0)
        for v in _disc_raw.values()
        if v
    )
    # Fall back to search_hit flag when iacontent has no disclosure block
    if _disc_count == 0 and search_hit and search_hit.get("has_disclosures"):
        _disc_has = True
    else:
        _disc_has = _disc_count > 0

    summary = {
        "firm_name": basic.get("firmName"),
        "crd_number": basic.get("firmId"),
        "sec_number": f"{basic.get('iaSECNumberType','')}-{basic.get('iaSECNumber','')}".strip("-"),
        "registration_status": basic.get("iaScope"),
        # adv_last_filing_date = date of the most recent ADV amendment filed.
        # This is NOT the firm's original registration/incorporation date.
        "adv_last_filing_date": basic.get("advFilingDate"),
        "has_pdf": basic.get("hasPdf") == "Y",

        # Original registration date — try basicInformation fields first,
        # then fall back to registrationStatus[0].effectiveDate which is
        # reliably present in all IAPD responses (e.g. "1/31/2005" for Ares).
        "firm_registration_date": (
            basic.get("registrationDate")
            or basic.get("orgEstablishedDate")
            or basic.get("incorporationDate")
            or basic.get("firmRegistrationDate")
            or (iacontent.get("registrationStatus") or [{}])[0].get("effectiveDate")
        ),

        # Website — try several field names used across different IAPD response versions
        "website": (
            basic.get("firmWebsite")
            or basic.get("website")
            or basic.get("webAddress")
            or iacontent.get("website")
            or iacontent.get("webAddress")
        ),

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

        # Disclosures — read directly from iacontent (more reliable than search_hit flag)
        "has_disclosures": _disc_has,
        "num_disclosures": _disc_count,

        # Fields not available in this API — must be obtained from ADV Part 1 PDF/XML
        "aum_regulatory": None,     # Not in IAPD API — in ADV Part 1 Item 5
        "num_clients": None,        # Not in IAPD API — in ADV Part 1 Item 5
        "num_employees": None,      # Not in IAPD API — in ADV Part 1 Item 5
        "fee_types": [],            # Not in IAPD API — in ADV Part 2
        "min_account_size": None,   # Not in IAPD API — in ADV Part 2
        "key_personnel": [],        # Not in IAPD API — in Schedule A/B

        # Section 7.B private funds — populated by data_ingestion._fetch_section7b()
        # as a parallel task so the PDF download doesn't block extract_adv_summary.
        "private_funds_section7b": [],
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
