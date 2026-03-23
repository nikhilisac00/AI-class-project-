"""
ADV Data Enrichment — fetches supplementary data to fill gaps in the IAPD JSON.

Reality check on data sources:
  • ADV Part 1A (AUM, fees, key personnel) lives in the IARD system, NOT EDGAR.
    IARD XML/PDF reports at reports.adviserinfo.sec.gov return 403 for programmatic access.
  • The IAPD iacontent JSON (what we already have) contains registration info and
    disclosure FLAGS but not financial details.

What this module DOES fetch:
  • 13F portfolio value — total US public equity holdings from EDGAR (real dollar amount,
    good proxy AUM for equity-focused managers; firms with >$100M US equity must file).
  • Disclosure details — parses iaCriminalDisclosures / iaRegulatoryDisclosures etc.
    from the iacontent JSON that edgar_client.py already fetches.
  • Brochure metadata — ADV Part 2A name and date (the PDF itself is behind auth).

All endpoints are public. No auth required.
"""

import re
import time
import json
import requests
import xml.etree.ElementTree as ET
from typing import Optional

EFTS_URL    = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
HEADERS = {
    "User-Agent": "AI-Alternatives-Research research@example.com",
    "Accept-Encoding": "gzip, deflate",
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _json(url: str, params: dict = None) -> Optional[dict]:
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


def _text(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


# ── 13F portfolio value (proxy AUM for public equity managers) ─────────────────

def _find_cik_for_13f(firm_name: str) -> Optional[str]:
    """Find EDGAR CIK for a firm by searching 13F-HR filings on EFTS."""
    for query in [f'"{firm_name}"', firm_name]:
        data = _json(EFTS_URL, {"q": query, "forms": "13F-HR"})
        if data:
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                ciks = hits[0]["_source"].get("ciks", [])
                if ciks:
                    return str(int(ciks[0]))  # strip leading zeros
    return None


def _latest_13f_from_submissions(cik: str) -> Optional[dict]:
    """
    Use EDGAR submissions API to find the most recent 13F-HR filing.
    Returns dict with accession, filing_date, period_of_report or None.
    """
    url = SUBMISSIONS.format(cik=cik.zfill(10))
    data = _json(url)
    if not data:
        return None
    recent = data.get("filings", {}).get("recent", {})
    forms   = recent.get("form", [])
    dates   = recent.get("filingDate", [])
    accs    = recent.get("accessionNumber", [])
    periods = recent.get("reportDate", [])
    for i, ft in enumerate(forms):
        if ft == "13F-HR":
            return {
                "accession":       accs[i],
                "filing_date":     dates[i],
                "period_of_report": periods[i] if i < len(periods) else None,
            }
    return None


def _xml_file_from_filing(cik: str, acc: str) -> Optional[str]:
    """
    Scrape the EDGAR filing HTML index to find the primary 13F XML filename.
    Returns just the filename (not the full URL).
    """
    acc_clean = acc.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
    html = _text(base + acc + "-index.htm")
    if not html:
        return None
    # Look for primary_doc.xml (has tableValueTotal) but NOT inside xslForm subdir
    for name in re.findall(r'href="[^"]*?/([^/\"]+\.xml)"', html, re.I):
        if name.lower() == "primary_doc.xml":
            return name
    # Fallback to any .xml not in an xsl subdirectory
    for name in re.findall(r'href="(?!.*xslForm)[^"]*?/([^/\"]+\.xml)"', html, re.I):
        if name.lower() not in ("xsl.xml",):
            return name
    return None


def _parse_13f_xml(cik: str, acc: str, xml_file: str, period: Optional[str]) -> dict:
    """
    Download and parse a 13F-HR primary_doc.xml.
    SEC changed reporting units from thousands → dollars starting with filings
    covering periods ending on or after 2024-12-31 (schema version X0202).
    Returns dict with portfolio_value_usd, portfolio_value_fmt, holdings_count.
    """
    acc_clean = acc.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
    xml_content = _text(base + xml_file)
    if not xml_content:
        return {}

    # Strip namespaces so ElementTree can parse
    xml_clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_content)
    xml_clean = re.sub(r'\s+\w+:schemaLocation="[^"]*"', "", xml_clean)
    xml_clean = re.sub(r"<(\w+):(\w[\w.-]*)", r"<\2", xml_clean)
    xml_clean = re.sub(r"</(\w+):(\w[\w.-]*)", r"</\2", xml_clean)

    try:
        root = ET.fromstring(xml_clean)
    except ET.ParseError:
        return {}

    # Detect schema version to determine value units.
    # X0202 (effective 2025-01-01) reports values in dollars; earlier in thousands.
    schema_el = root.find(".//schemaVersion")
    schema_ver = schema_el.text.strip() if schema_el is not None and schema_el.text else ""
    use_dollars = schema_ver >= "X0202" or (period or "") >= "2024-12-31"

    val_raw = None
    for tag in ("tableValueTotal", "totalValue", "sumValue", "portfolioValue"):
        el = root.find(f".//{tag}")
        if el is not None and el.text and el.text.strip().replace(",", "").isdigit():
            val_raw = int(el.text.strip().replace(",", ""))
            break

    out = {}
    if val_raw is not None:
        val_usd = val_raw if use_dollars else val_raw * 1000
        out["portfolio_value_usd"] = val_usd
        if val_usd >= 1e12:
            out["portfolio_value_fmt"] = f"${val_usd/1e12:.2f}T"
        elif val_usd >= 1e9:
            out["portfolio_value_fmt"] = f"${val_usd/1e9:.2f}B"
        else:
            out["portfolio_value_fmt"] = f"${val_usd/1e6:.1f}M"

    # Holdings count — prefer tableEntryTotal from the summary doc
    entry_el = root.find(".//tableEntryTotal")
    if entry_el is not None and entry_el.text and entry_el.text.strip().isdigit():
        out["holdings_count"] = int(entry_el.text.strip())
    else:
        holdings = root.findall(".//infoTable") or root.findall(".//InfoTable")
        if holdings:
            out["holdings_count"] = len(holdings)

    return out


def _get_13f_portfolio_value(firm_name: str) -> dict:
    """
    Find the most recent 13F-HR filing and extract total portfolio value.
    Uses EFTS to resolve CIK, then EDGAR submissions API for the latest filing.
    Only applicable for managers with >$100M in US public equities.
    """
    result = {
        "portfolio_value_usd": None,
        "portfolio_value_fmt": None,
        "filing_date": None,
        "period_of_report": None,
        "holdings_count": None,
        "cik": None,
        "accession": None,
        "note": None,
    }

    # Step 1: find CIK via EFTS
    cik = _find_cik_for_13f(firm_name)
    if not cik:
        result["note"] = "No 13F-HR filings found — firm may not hold >$100M in US public equities"
        return result
    result["cik"] = cik

    # Step 2: get most recent 13F-HR accession via submissions API
    filing = _latest_13f_from_submissions(cik)
    if not filing:
        result["note"] = f"CIK {cik} found but no 13F-HR in recent submissions"
        return result

    acc    = filing["accession"]
    result["accession"]       = acc
    result["filing_date"]     = filing["filing_date"]
    result["period_of_report"] = filing["period_of_report"]

    # Step 3: find the XML file via HTML index
    xml_file = _xml_file_from_filing(cik, acc)
    if not xml_file:
        result["note"] = f"13F filing found (CIK={cik}) but XML document not located in index"
        return result

    # Step 4: parse XML for portfolio value and holdings count
    parsed = _parse_13f_xml(cik, acc, xml_file, filing["period_of_report"])
    result.update(parsed)

    if result.get("portfolio_value_fmt"):
        result["note"] = (
            "13F public equity portfolio (US equities only — not total regulatory AUM). "
            f"Period: {result['period_of_report'] or 'unknown'}"
        )
    else:
        result["note"] = "13F filing found but could not extract total portfolio value from XML"

    return result


# ── Disclosure details from IAPD iacontent ────────────────────────────────────

def parse_iapd_disclosures(iacontent: dict) -> list[dict]:
    """
    Extract detailed disclosure events from IAPD iacontent JSON.
    The iacontent dict is returned by edgar_client.get_adviser_detail().
    Returns a list of disclosure event dicts.
    """
    disclosures = []

    # Keys in iacontent that contain disclosure arrays
    disclosure_keys = [
        "iaCriminalDisclosures",
        "iaRegulatoryDisclosures",
        "iaCivilDisclosures",
        "iaArbitrationDisclosures",
        "iaEmploymentDisclosures",
        "iaOrgDisclosures",
        "disclosures",
    ]

    for key in disclosure_keys:
        items = iacontent.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            disc = {
                "type": key.replace("ia", "").replace("Disclosures", "").replace("Disclosure", "").strip(),
                "date": (
                    item.get("disclosureDate")
                    or item.get("date")
                    or item.get("eventDate")
                ),
                "description": (
                    item.get("disclosureType")
                    or item.get("description")
                    or item.get("type")
                ),
                "resolution": (
                    item.get("disclosureResolution")
                    or item.get("resolution")
                    or item.get("status")
                ),
                "details": [],
            }
            # Some disclosures have a details sub-array
            detail_items = item.get("disclosureDetails", []) or item.get("details", [])
            if isinstance(detail_items, list):
                for d in detail_items:
                    if isinstance(d, dict):
                        label = d.get("disclosureDetailType") or d.get("label") or d.get("key")
                        value = d.get("disclosureDetailValue") or d.get("value")
                        if label and value:
                            disc["details"].append({"label": label, "value": value})
            disclosures.append(disc)

    return disclosures


# ── Brochure metadata ─────────────────────────────────────────────────────────

def parse_brochure_metadata(iacontent: dict) -> dict:
    """
    Extract ADV Part 2A brochure metadata from iacontent.
    Returns name, date, and version ID (the PDF itself requires auth).
    """
    brochures_raw = iacontent.get("brochures", {})
    if isinstance(brochures_raw, dict):
        details = brochures_raw.get("brochuredetails", [])
    elif isinstance(brochures_raw, list):
        details = brochures_raw
    else:
        return {}

    if not details:
        return {}

    latest = sorted(
        details,
        key=lambda x: x.get("dateSubmitted", "") if isinstance(x, dict) else "",
        reverse=True,
    )
    b = latest[0] if isinstance(latest[0], dict) else {}
    return {
        "brochure_name":    b.get("brochureName"),
        "brochure_date":    b.get("dateSubmitted"),
        "brochure_version": b.get("brochureVersionID"),
        "part2_exempt":     brochures_raw.get("part2ExemptFlag") if isinstance(brochures_raw, dict) else None,
        "note": "ADV Part 2A PDF accessible at adviserinfo.sec.gov (requires browser — not available via API)",
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_adv_data(firm_name: str, iacontent: dict = None) -> dict:
    """
    Fetch supplementary data for a firm.

    Args:
        firm_name:  Used to search for 13F filings on EDGAR.
        iacontent:  The parsed iacontent dict from edgar_client.get_adviser_detail()
                    (used for disclosure details and brochure metadata).

    Returns dict with:
      - thirteenf:       13F portfolio value data (proxy AUM for equity managers)
      - disclosures:     Detailed disclosure events from IAPD iacontent
      - brochure:        ADV Part 2A brochure metadata
      - aum_note:        Explanation of AUM data availability
    """
    result = {
        "thirteenf":   {},
        "disclosures": [],
        "brochure":    {},
        "aum_note": (
            "Regulatory AUM is in ADV Part 1A Item 5 (IARD system). "
            "Not accessible via free public API — requires IAPD website, "
            "Preqin, Bloomberg, or direct GP engagement."
        ),
        "error": None,
    }

    # 13F portfolio value
    print(f"[ADV Enrichment] Fetching 13F data for '{firm_name}'")
    result["thirteenf"] = _get_13f_portfolio_value(firm_name)

    # Disclosures and brochure from iacontent (if provided)
    if iacontent:
        result["disclosures"] = parse_iapd_disclosures(iacontent)
        result["brochure"]    = parse_brochure_metadata(iacontent)

    pv = result["thirteenf"].get("portfolio_value_fmt")
    print(
        f"[ADV Enrichment] Done — 13F portfolio={pv or 'N/A'}, "
        f"disclosures={len(result['disclosures'])}"
    )
    return result
