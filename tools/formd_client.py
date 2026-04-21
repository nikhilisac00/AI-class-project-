"""
SEC EDGAR Form D Client
=======================
Form D is filed by private fund issuers (hedge funds, PE funds, VC funds)
for exempt securities offerings under Reg D.

Key data available per filing:
  - entityName     : fund name
  - totalOfferingAmount / amountSold : capital raised
  - dateOfFirstSale : fund inception / fundraise date
  - entityType     : Limited Partnership / LLC etc.
  - exemptions     : 3C.1 (≤100 investors), 3C.7 (QIBs) — indicates fund type
  - stateOfInc, jurisdiction

Approach:
  1. EDGAR EFTS search: find all Form D/D/A filings matching the GP firm name
  2. For each unique fund (deduplicate by entity name), fetch the XML for financials
  3. Return structured fund list
"""

import re
import time
import requests
import xml.etree.ElementTree as ET
from typing import Optional

EFTS_URL      = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS   = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
PRIMARY_DOC   = EDGAR_ARCHIVE + "primary_doc.xml"

HEADERS = {
    "User-Agent": "AI-Alternatives-Research research@example.com",
    "Accept-Encoding": "gzip, deflate",
}

# Exemption codes that indicate private fund structures
FUND_EXEMPTIONS = {"3C.1", "3C.7", "06B"}

_SUFFIX_RE = re.compile(
    r"\b(LLC|LP|L\.P\.|LLP|L\.L\.C\.|Inc\.?|Corp\.?|Co\.?|Ltd\.?|"
    r"Limited|Associates|Group|Holdings|Partners)\b",
    re.I,
)
_GENERIC_WORDS = frozenset({
    "management", "capital", "advisors", "advisers", "asset", "investments",
    "investment", "financial", "services", "wealth", "global", "fund",
})


def _formd_name_variants(gp_name: str) -> list[str]:
    """
    Generate Form D EFTS search query variants for a GP name.
    Ordered most-specific → least-specific to minimise false matches.

    Form D full-text search looks inside the XML, so the GP's name may
    appear as "Ares Management" even when the filing was made by a fund
    sub-entity like "ACOF Operating Manager IV, LLC".
    """
    stripped = _SUFFIX_RE.sub("", gp_name).strip().strip(",").strip()
    words = [w for w in gp_name.split() if len(w) > 2]

    variants: list[str] = [gp_name]  # exact name always first

    if stripped and stripped.lower() != gp_name.lower():
        variants.append(stripped)

    # Two meaningful words: "Ares Management", "KKR Capital"
    if len(words) >= 2:
        two = " ".join(words[:2])
        if two not in variants:
            variants.append(two)

    # Single brand word (only if distinctive, not a generic like "Capital")
    if words and words[0].lower() not in _GENERIC_WORDS and words[0] not in variants:
        variants.append(words[0])

    return variants


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


def _text(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _parse_formd_xml(xml_text: str) -> dict:
    """
    Parse Form D primary_doc.xml for key financial fields.
    Returns dict with: entity_name, total_offering_amount, amount_sold,
    date_of_first_sale, entity_type, exemptions, jurisdiction.
    """
    if not xml_text:
        return {}

    # Strip namespaces
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_text)
    clean = re.sub(r"<(\w+):(\w[\w.-]*)", r"<\2", clean)
    clean = re.sub(r"</(\w+):(\w[\w.-]*)", r"</\2", clean)

    try:
        root = ET.fromstring(clean)
    except ET.ParseError:
        return {}

    def _txt(tag: str) -> Optional[str]:
        el = root.find(f".//{tag}")
        return el.text.strip() if el is not None and el.text else None

    # Offering amounts
    total_str = _txt("totalOfferingAmount") or _txt("offeringData/totalOfferingAmount")
    sold_str  = _txt("amountSold")

    def _parse_amount(s: Optional[str]) -> Optional[int]:
        if not s:
            return None
        clean_s = s.replace(",", "").replace("$", "").strip()
        try:
            return int(float(clean_s))
        except ValueError:
            return None

    total = _parse_amount(total_str)
    sold  = _parse_amount(sold_str)

    # Exemption types (3C.1, 3C.7 etc.)
    # "3C" alone is not a valid exemption code — it is a section reference that
    # appears in the Form D XML alongside the specific sub-section (3C.1, 3C.7).
    # Filter it out to avoid displaying meaningless codes in the memo.
    _BARE_CODES = {"3C", "SECTION 3(C)"}
    exemptions = []
    for el in root.findall(".//exemptionsRelied") or root.findall(".//item"):
        v = (el.text or "").strip().upper()  # normalise to upper so "06b"→"06B"
        if v and v not in _BARE_CODES:
            exemptions.append(v)
    # Also check items[] field
    for el in root.findall(".//item"):
        v = (el.text or "").strip().upper()
        if v and v not in exemptions and v not in _BARE_CODES:
            exemptions.append(v)

    return {
        "entity_name":           _txt("entityName"),
        "total_offering_amount": total,
        "amount_sold":           sold,
        "date_of_first_sale":    _txt("dateOfFirstSale"),
        "entity_type":           _txt("entityType"),
        "jurisdiction":          _txt("stateOrCountryDescription") or _txt("jurisdictionOfInc"),
        "exemptions":            exemptions,
        "is_private_fund":       bool(set(exemptions) & FUND_EXEMPTIONS),
    }


def search_funds_for_gp(
    gp_name: str,
    max_funds: int = 20,
    only_private_funds: bool = True,
) -> list[dict]:
    """
    Find all Form D fund filings associated with a GP / investment adviser.

    Strategy:
      1. EFTS text search for Form D filings matching gp_name
      2. Deduplicate by entity name (keep most recent filing per fund)
      3. For each unique fund, fetch XML for financial details

    Args:
        gp_name:            GP firm name to search
        max_funds:          Cap on number of unique funds to return
        only_private_funds: If True, filter to 3C.1/3C.7 exemptions only

    Returns:
        List of fund dicts sorted by date_of_first_sale desc.
    """
    # Step 1: EFTS search — try name variants from most- to least-specific.
    # Large GPs file Form D under subsidiary/operating manager names, so the
    # exact firm name often yields 0 hits while a shorter variant finds them.
    variants = _formd_name_variants(gp_name)
    all_hits: list[dict] = []
    tried: set[str] = set()

    for variant in variants:
        # Try quoted (exact phrase) first, then unquoted if empty
        for q in (f'"{variant}"', variant):
            if q in tried:
                continue
            tried.add(q)
            data = _get(EFTS_URL, params={"q": q, "forms": "D,D/A"})
            if data:
                batch = data.get("hits", {}).get("hits", [])
                if batch:
                    print(f"[FormD] '{q}' → {len(batch)} hits")
                    all_hits.extend(batch)
                    break  # found results with this variant; try next variant
            time.sleep(0.1)

        # Once we have enough raw hits to satisfy max_funds after dedup, stop early
        if len(all_hits) >= max_funds * 6:
            break

    if not all_hits:
        return []

    hits = all_hits

    # Step 2: Deduplicate — keep most recent filing per entity name
    seen: dict[str, dict] = {}   # entity_name → best hit
    for h in hits:
        src = h.get("_source", {})
        names = src.get("display_names", [])
        entity_name = names[0].split("(CIK")[0].strip() if names else None
        if not entity_name:
            continue
        key = entity_name.upper()
        existing = seen.get(key)
        if not existing or src.get("file_date", "") > existing.get("file_date", ""):
            ciks = src.get("ciks", [])
            seen[key] = {
                "entity_name":  entity_name,
                "cik":          str(int(ciks[0])) if ciks else None,
                "accession":    src.get("adsh"),
                "file_date":    src.get("file_date"),
                "form":         src.get("form"),
                "exemptions":   src.get("items", []),
                "jurisdiction": (src.get("inc_states") or [""])[0],
            }

    candidates = list(seen.values())

    # Sort by filing date desc.
    # NOTE: Do NOT pre-filter by exemptions here — the EFTS `items` field is
    # unreliably populated and often empty even for real private funds. We fetch
    # XML for all candidates first and apply the filter using the XML-derived
    # `is_private_fund` flag, which reads the actual exemption elements.
    candidates.sort(key=lambda x: x.get("file_date") or "", reverse=True)
    # Fetch up to 3x max_funds so we have enough after the post-XML filter
    candidates = candidates[:max(max_funds * 3, 60)]

    # Step 3: Fetch XML for each to get offering amounts + accurate exemptions
    funds = []
    for c in candidates:
        cik = c.get("cik")
        acc = c.get("accession")
        if cik and acc:
            acc_clean = acc.replace("-", "")
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/primary_doc.xml"
            xml_text = _text(xml_url)
            parsed = _parse_formd_xml(xml_text) if xml_text else {}
            # Merge — prefer XML values but fall back to EFTS
            fund = {**c, **{k: v for k, v in parsed.items() if v is not None}}
        else:
            fund = c

        # Apply private fund filter HERE using XML-derived is_private_fund flag
        # (EFTS items field is not reliable; XML exemptions are authoritative)
        if only_private_funds and not fund.get("is_private_fund", False):
            time.sleep(0.05)
            continue

        # Format offering amount for display
        amt = fund.get("total_offering_amount") or fund.get("amount_sold")
        if amt:
            if amt >= 1e9:
                fund["offering_fmt"] = f"${amt/1e9:.2f}B"
            elif amt >= 1e6:
                fund["offering_fmt"] = f"${amt/1e6:.1f}M"
            else:
                fund["offering_fmt"] = f"${amt:,}"
        else:
            fund["offering_fmt"] = None

        funds.append(fund)
        time.sleep(0.1)   # polite rate limiting

        if len(funds) >= max_funds:
            break

    return funds
