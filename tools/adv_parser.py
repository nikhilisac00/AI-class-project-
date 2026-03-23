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

def _get_13f_portfolio_value(firm_name: str) -> dict:
    """
    Find the most recent 13F-HR filing and extract total portfolio value.
    Returns dict with portfolio_value_usd, filing_date, cik, and holdings_count.
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

    # Find 13F filing via EFTS
    for query in [f'"{firm_name}"', firm_name]:
        data = _json(EFTS_URL, {"q": query, "forms": "13F-HR"})
        if data:
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                src = hits[0]["_source"]
                ciks = src.get("ciks", [])
                acc  = src.get("adsh")
                if ciks and acc:
                    result["cik"]       = ciks[0]
                    result["accession"] = acc
                    result["filing_date"] = src.get("file_date")
                    result["period_of_report"] = src.get("period_ending")
                    break

    if not result["cik"]:
        result["note"] = "No 13F-HR filings found — firm may not hold >$100M in US public equities"
        return result

    # Fetch the 13F XML to get total portfolio value
    cik = result["cik"]
    acc = result["accession"]
    acc_clean = acc.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"

    # Get filing index
    index = _json(f"{base}{acc}-index.json")
    xml_file = None
    if index:
        for doc in index.get("directory", {}).get("item", []):
            name = doc.get("name", "")
            # 13F primary XML is typically infotable.xml or primary_doc.xml
            if name.lower().endswith(".xml") and name.lower() not in ("xsl.xml",):
                xml_file = name
                break

    if not xml_file:
        result["note"] = f"13F filing found (CIK={cik}) but XML document not accessible"
        return result

    xml_content = _text(base + xml_file)
    if not xml_content:
        result["note"] = f"Could not download 13F XML from {base + xml_file}"
        return result

    # Parse 13F XML for total value and holdings count
    try:
        xml_clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_content)
        xml_clean = re.sub(r"<(\w+):(\w[\w.-]*)", r"<\2", xml_clean)
        xml_clean = re.sub(r"</(\w+):(\w[\w.-]*)", r"</\2", xml_clean)
        root = ET.fromstring(xml_clean)

        # Total portfolio value (in thousands)
        for tag in ("tableValueTotal", "totalValue", "sumValue", "portfolioValue"):
            el = root.find(f".//{tag}")
            if el is not None and el.text and el.text.strip().replace(",", "").isdigit():
                val_thousands = int(el.text.strip().replace(",", ""))
                val_usd = val_thousands * 1000
                result["portfolio_value_usd"] = val_usd
                if val_usd >= 1e12:
                    result["portfolio_value_fmt"] = f"${val_usd/1e12:.2f}T"
                elif val_usd >= 1e9:
                    result["portfolio_value_fmt"] = f"${val_usd/1e9:.2f}B"
                else:
                    result["portfolio_value_fmt"] = f"${val_usd/1e6:.1f}M"
                break

        # Holdings count
        holdings = root.findall(".//infoTable") or root.findall(".//InfoTable")
        if holdings:
            result["holdings_count"] = len(holdings)

    except ET.ParseError as e:
        result["note"] = f"13F XML parse error: {e}"

    if result["portfolio_value_fmt"]:
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
