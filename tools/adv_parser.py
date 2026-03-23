"""
ADV XML Parser — fetches and parses Form ADV Part 1A from SEC EDGAR.

Fills the critical gaps left by the IAPD JSON API:
  • Regulatory AUM (Item 5A)           • Client count (Item 5D)
  • Employee count (Item 5B)           • Fee types (Item 5C)
  • Key personnel — Schedule A owners  • Disclosure details (Item 11)

All SEC EDGAR endpoints are public. No auth required.
"""

import re
import time
import requests
import xml.etree.ElementTree as ET
from typing import Optional

EFTS_URL    = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"

HEADERS = {
    "User-Agent": "AI-Alternatives-Research research@example.com",
    "Accept-Encoding": "gzip, deflate",
}


# ── HTTP helpers ────────────────────────────────────────────────────────────────────────────

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
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


# ── Locate ADV filing on EDGAR ──────────────────────────────────────────────────────────

def _find_cik_and_accession(firm_name: str) -> Optional[tuple]:
    """
    Search EDGAR EFTS for the most recent ADV filing.
    Returns (cik, accession_number) or None.
    Tries exact-quoted match first, then fuzzy.
    """
    for query in [f'"{firm_name}"', firm_name]:
        data = _json(EFTS_URL, {"q": query, "forms": "ADV"})
        if data:
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                src  = hits[0]["_source"]
                ciks = src.get("ciks", [])
                acc  = src.get("adsh")
                if ciks and acc:
                    print(f"[ADV] EFTS match: CIK={ciks[0]}, acc={acc}")
                    return (ciks[0], acc)
    return None


def _latest_adv_accession(cik: str) -> Optional[str]:
    """Pull most recent ADV accession from EDGAR submissions API."""
    data = _json(SUBMISSIONS.format(cik=cik.lstrip("0").zfill(10)))
    if not data:
        return None
    recent = data.get("filings", {}).get("recent", {})
    forms  = recent.get("form", [])
    accs   = recent.get("accessionNumber", [])
    for i, form in enumerate(forms):
        if form == "ADV" and i < len(accs):
            return accs[i]
    return None


# ── Fetch ADV XML document ───────────────────────────────────────────────────────────────

def _fetch_xml(cik: str, accession: str) -> Optional[str]:
    """
    Download the ADV XML document.
    Tries filing index JSON first, then known filename patterns.
    Strips EDGAR SGML wrapper if present.
    """
    acc_clean = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"

    xml_file = None

    # Try filing index JSON to discover the XML document name
    index = _json(f"{base}{accession}-index.json")
    if index:
        items = index.get("directory", {}).get("item", [])
        for doc in items:  # prefer files with 'adv' in name
            name = doc.get("name", "")
            if name.lower().endswith(".xml") and "adv" in name.lower():
                xml_file = name
                break
        if not xml_file:
            for doc in items:  # any XML file
                if doc.get("name", "").lower().endswith(".xml"):
                    xml_file = doc["name"]
                    break

    # Fallback: try common ADV XML filenames
    if not xml_file:
        for candidate in ["ia.xml", "primary_doc.xml", "form_adv.xml", "adv.xml"]:
            try:
                r = requests.head(base + candidate, headers=HEADERS, timeout=10)
                if r.status_code == 200:
                    xml_file = candidate
                    break
            except Exception:
                pass

    if not xml_file:
        return None

    content = _text(base + xml_file)
    if not content:
        return None

    # Strip EDGAR SGML wrapper (<TEXT>...</TEXT>) if present
    if "<DOCUMENT>" in content or content.strip().startswith("<SUBMISSION>"):
        m = re.search(r"<TEXT>(.*?)</TEXT>", content, re.DOTALL)
        if m:
            content = m.group(1).strip()

    return content


# ── Parse ADV XML ────────────────────────────────────────────────────────────────────────────

def _strip_ns(s: str) -> str:
    """Remove XML namespace prefixes for simpler ElementTree access."""
    s = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", s)
    s = re.sub(r"<(\w+):(\w[\w.-]*)", r"<\2", s)
    s = re.sub(r"</(\w+):(\w[\w.-]*)", r"</\2", s)
    return s


def _f(root: ET.Element, *tags) -> Optional[str]:
    """Return text of first matching tag name (tree-wide search)."""
    for tag in tags:
        el = root.find(f".//{tag}")
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return None


def _child(el: ET.Element, *tags) -> Optional[str]:
    """Return text of first matching direct/indirect child tag."""
    for tag in tags:
        c = el.find(tag)
        if c is not None and c.text and c.text.strip():
            return c.text.strip()
    return None


def _fmt_aum(raw: str) -> str:
    """Convert a raw AUM number string to human-readable format."""
    try:
        n = float(raw.replace(",", "").replace("$", "").strip())
        if n >= 1e9:
            return f"${n/1e9:.2f}B"
        if n >= 1e6:
            return f"${n/1e6:.1f}M"
        if n >= 1e3:
            return f"${n/1e3:.0f}K"
        return f"${n:,.0f}"
    except (ValueError, TypeError):
        return raw


def parse_adv_xml(xml_content: str) -> dict:
    """
    Parse Form ADV Part 1A XML into structured fields.
    Returns None / empty list for any field not found — never estimates.
    Handles schema variations across different filing years.
    """
    out = {
        "aum_regulatory":          None,
        "aum_discretionary":       None,
        "aum_non_discretionary":   None,
        "num_clients":             None,
        "num_employees":           None,
        "num_investment_advisers": None,
        "fee_types":               [],
        "key_personnel":           [],
        "disclosures_detail":      [],
        "parse_error":             None,
    }

    try:
        root = ET.fromstring(_strip_ns(xml_content))
    except ET.ParseError as e:
        out["parse_error"] = str(e)
        return out

    # ── AUM (Item 5A) ──────────────────────────────────────────────────────────────────────────
    for tags, field in [
        (
            ("TotalRegulatoryAssets", "TotalAssets", "RegulatoryAssets",
             "TotalAUM", "TotRegAUM", "TotAstUnderMgmt",
             "TotalAssetsUnderManagement", "TotalRegAUM"),
            "aum_regulatory",
        ),
        (
            ("DiscretionaryAssets", "TotalDiscretionaryAUM",
             "DiscretionaryAUM", "Item5ARow1DiscAUM"),
            "aum_discretionary",
        ),
        (
            ("NonDiscretionaryAssets", "TotalNonDiscretionaryAUM",
             "NonDiscretionaryAUM", "Item5ARow1NonDiscAUM"),
            "aum_non_discretionary",
        ),
    ]:
        raw = _f(root, *tags)
        if raw:
            out[field] = _fmt_aum(raw)

    # ── Counts (Item 5B / 5D) ─────────────────────────────────────────────────────────
    for tags, field in [
        (
            ("TotalNumberOfClients", "NumberOfClients", "TotalClients",
             "Item5D1", "ClientCount", "NumberClients"),
            "num_clients",
        ),
        (
            ("TotalEmployees", "NumberOfEmployees", "EmployeeCount",
             "Item5B1", "TotEmpl", "TotalEmployeeCount"),
            "num_employees",
        ),
        (
            ("NumberOfRegisteredAdvisers", "IAEmployees", "Item5B2",
             "NumIAEmployees", "RegisteredIACount"),
            "num_investment_advisers",
        ),
    ]:
        raw = _f(root, *tags)
        if raw and raw.replace(",", "").isdigit():
            out[field] = int(raw.replace(",", ""))

    # ── Fee types (Item 5C) ─────────────────────────────────────────────────────────────
    fee_flag_map = {
        "PercentageOfAUM":   "% of AUM",
        "AUMBasedFee":       "% of AUM",
        "HourlyCharges":     "Hourly",
        "HourlyFee":         "Hourly",
        "SubscriptionFees":  "Subscription",
        "FixedFees":         "Fixed fee",
        "CommissionBased":   "Commissions",
        "PerformanceBased":  "Performance-based",
        "PerformanceFees":   "Performance-based",
    }
    fees: set = set()
    for xml_tag, label in fee_flag_map.items():
        el = root.find(f".//{xml_tag}")
        if el is not None and el.text and el.text.strip().upper() in ("Y", "YES", "TRUE", "1", "X"):
            fees.add(label)
    for el in root.findall(".//FeeType"):
        if el.text and el.text.strip():
            fees.add(el.text.strip())
    out["fee_types"] = sorted(fees)

    # ── Key personnel — Schedule A / B ───────────────────────────────────────────────
    seen: set = set()
    for tag in ("DirectOwner", "IndirectOwner", "ExecutiveOfficer",
                "RelatedPerson", "Owner"):
        for el in root.findall(f".//{tag}"):
            name = _child(el, "FullLegalName", "FullName", "Name", "PersonName")
            if not name:
                first = _child(el, "FirstName") or ""
                last  = _child(el, "LastName")  or ""
                name  = f"{first} {last}".strip() or None
            if not name or name in seen:
                continue
            seen.add(name)
            out["key_personnel"].append({
                "name": name,
                "crd":  _child(el, "CRDNumber", "IndividualCRD"),
                "titles": [t for t in [
                    _child(el, "Title"),
                    _child(el, "Position"),
                    _child(el, "TitleOrStatus"),
                ] if t],
                "ownership_pct": _child(
                    el, "OwnershipCode", "OwnershipPercentage", "PercentageOwned"
                ),
            })

    # ── Disclosures (Item 11) ────────────────────────────────────────────────────────────
    for tag in ("CriminalDisclosure", "RegulatoryAction", "CivilAction",
                "ArbitrationDisclosure", "DisclosureEvent", "Disclosure"):
        for el in root.findall(f".//{tag}"):
            out["disclosures_detail"].append({
                "type":        tag,
                "date":        _child(el, "Date", "EventDate"),
                "description": _child(el, "Description", "Explanation", "Details"),
                "status":      _child(el, "Status", "Resolution"),
            })

    return out


# ── Main entry point ────────────────────────────────────────────────────────────────────────────

def fetch_adv_data(firm_name: str) -> dict:
    """
    Full pipeline: search EDGAR → fetch XML → parse.
    Always returns a dict. 'error' key is None on success.
    """
    result: dict = {
        "error":       None,
        "cik":         None,
        "accession":   None,
        "filing_url":  None,
    }

    print(f"[ADV Parser] Searching EDGAR for '{firm_name}'")
    found = _find_cik_and_accession(firm_name)
    if not found:
        result["error"] = f"No ADV filings found on EDGAR for '{firm_name}'"
        print(f"[ADV Parser] {result['error']}")
        return result

    cik, accession = found

    # Prefer the most current filing from the submissions API
    newer = _latest_adv_accession(cik)
    if newer:
        accession = newer

    acc_clean = accession.replace("-", "")
    result.update({
        "cik":        cik,
        "accession":  accession,
        "filing_url": (
            f"https://www.sec.gov/Archives/edgar/data/{cik}"
            f"/{acc_clean}/{accession}-index.htm"
        ),
    })

    print(f"[ADV Parser] Fetching XML — CIK={cik}, accession={accession}")
    xml_content = _fetch_xml(cik, accession)
    if not xml_content:
        result["error"] = f"ADV XML document not accessible (CIK={cik})"
        print(f"[ADV Parser] {result['error']}")
        return result

    parsed = parse_adv_xml(xml_content)
    result.update(parsed)

    print(
        f"[ADV Parser] Done — AUM={result.get('aum_regulatory')}, "
        f"clients={result.get('num_clients')}, "
        f"employees={result.get('num_employees')}, "
        f"personnel={len(result.get('key_personnel', []))}"
    )
    return result
