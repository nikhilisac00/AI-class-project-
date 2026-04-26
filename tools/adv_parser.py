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


def _text_large(url: str) -> Optional[str]:
    """Fetch a URL with a longer timeout — for large XML files like 13F infotables."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=90)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


# ── 13F holdings helpers ───────────────────────────────────────────────────────

def _detect_asset_class(name: str, title: str) -> str:
    """Classify a holding by asset class from issuer name and title of class."""
    n = (name  or "").upper()
    t = (title or "").upper()
    if any(x in t for x in ("CALL", "PUT")):
        return "Options"
    if any(x in t for x in ("NOTE", "BOND", "DEBN", "SR NT", "SUB NT", "PREF")):
        return "Fixed Income / Pref"
    if any(x in t for x in ("WART", "WARR", "RTS", "RIGHTS")):
        return "Warrants / Rights"
    if any(x in n for x in ("ISHARES", "SPDR", "POWERSHARES", "PROSHARES",
                             "VANECK", "INVESCO QQQ", "DIREXION")):
        return "ETF / Fund"
    if " ETF" in n or n.endswith(" ETF"):
        return "ETF / Fund"
    return "Common Stock"


def _infotable_file_from_filing(cik: str, acc: str) -> Optional[str]:
    """
    Find the information table XML (individual holdings) from a 13F filing index.
    The index page lists both primary_doc.xml (cover/summary) and infotable.xml (holdings).
    """
    acc_clean = acc.replace("-", "")
    html = _text(
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{acc}-index.htm"
    )
    if not html:
        return None

    lower = html.lower()
    # Prefer the file described as "information table"
    idx = lower.find("information table")
    if idx != -1:
        snippet = html[max(0, idx - 30): idx + 400]
        # Handle both absolute paths (/Archives/.../file.xml) and relative (file.xml)
        hits = re.findall(r'href="(?:[^"]*?/)?([^/\"]+\.xml)"', snippet, re.I)
        if hits:
            return hits[0]

    # Fallback: any .xml that isn't the primary doc or an xsl stylesheet
    for name in re.findall(r'href="(?:[^"]*?/)?([^/\"]+\.xml)"', html, re.I):
        if name.lower() not in ("primary_doc.xml",) and "xsl" not in name.lower():
            return name
    return None


def _parse_13f_holdings(
    cik:             str,
    acc:             str,
    infotable_file:  str,
    use_dollars:     bool,
    total_value_usd: int,
    top_n:           int = 25,
) -> dict:
    """
    Parse 13F information table XML → top holdings + asset class breakdown.

    Key detail: the same CUSIP can appear multiple times with different
    investmentDiscretion types (SOLE / SHARED / OTR).  We aggregate by CUSIP
    so each issuer appears once in the output.

    Also detects possible confidential treatment: if the sum of all parsed
    positions is materially less than the declared tableValueTotal, some
    positions may have been omitted under a confidential treatment request.

    Returns dict with: top_holdings, asset_class_breakdown, concentration,
    possible_confidential_positions. Empty dict on failure.
    """
    acc_clean = acc.replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{infotable_file}"
    )
    print(f"[ADV Enrichment] Downloading 13F infotable ({infotable_file})...")
    xml_content = _text_large(url)
    if not xml_content:
        return {}

    # Strip XML namespaces so ElementTree can parse cleanly
    xml_clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_content)
    xml_clean = re.sub(r'\s+\w+:schemaLocation="[^"]*"', "", xml_clean)
    xml_clean = re.sub(r"<(\w+):(\w[\w.-]*)",  r"<\2",  xml_clean)
    xml_clean = re.sub(r"</(\w+):(\w[\w.-]*)", r"</\2", xml_clean)

    try:
        root = ET.fromstring(xml_clean)
    except ET.ParseError:
        return {}

    rows = root.findall(".//infoTable") or root.findall(".//InfoTable")
    if not rows:
        return {}

    # Aggregate by CUSIP (same position may appear under multiple discretion types)
    by_cusip: dict[str, dict] = {}
    for row in rows:
        name  = (row.findtext("nameOfIssuer") or "").strip()
        cusip = (row.findtext("cusip") or "").strip()
        title = (row.findtext("titleOfClass") or "").strip()
        val_el = row.find("value")
        if val_el is None or not (val_el.text or "").strip():
            continue
        try:
            raw = int(val_el.text.strip().replace(",", ""))
        except ValueError:
            continue
        value_usd = raw if use_dollars else raw * 1000
        if value_usd <= 0:
            continue

        shares_el = row.find(".//sshPrnamt")
        shares = 0
        if shares_el is not None and shares_el.text:
            try:
                shares = int(shares_el.text.strip().replace(",", ""))
            except ValueError:
                pass

        key = cusip or name
        if key not in by_cusip:
            by_cusip[key] = {
                "name":       name,
                "cusip":      cusip,
                "title":      title,
                "value_usd":  0,
                "shares":     0,
            }
        by_cusip[key]["value_usd"] += value_usd
        by_cusip[key]["shares"]    += shares

    if not by_cusip:
        return {}

    # Sort all positions descending by value
    sorted_positions = sorted(
        by_cusip.values(), key=lambda x: x["value_usd"], reverse=True
    )
    denom = total_value_usd or sum(p["value_usd"] for p in sorted_positions)

    def _fmt(v: int) -> str:
        if v >= 1_000_000_000:
            return f"${v / 1e9:.2f}B"
        if v >= 1_000_000:
            return f"${v / 1e6:.1f}M"
        return f"${v / 1_000:.0f}K"

    # Build top-N holdings list
    top_holdings = []
    for i, pos in enumerate(sorted_positions[:top_n], 1):
        pct = round(pos["value_usd"] / denom * 100, 2) if denom else None
        top_holdings.append({
            "rank":             i,
            "name":             pos["name"],
            "cusip":            pos["cusip"],
            "value_usd":        pos["value_usd"],
            "value_fmt":        _fmt(pos["value_usd"]),
            "pct_of_portfolio": pct,
            "shares":           pos["shares"] or None,
            "asset_class":      _detect_asset_class(pos["name"], pos["title"]),
        })

    # Asset class breakdown (over ALL positions, not just top-N)
    asset_totals: dict[str, dict] = {}
    for pos in sorted_positions:
        cls = _detect_asset_class(pos["name"], pos["title"])
        if cls not in asset_totals:
            asset_totals[cls] = {"value_usd": 0, "count": 0}
        asset_totals[cls]["value_usd"] += pos["value_usd"]
        asset_totals[cls]["count"]     += 1

    asset_breakdown = {
        cls: {
            "value_fmt": _fmt(data["value_usd"]),
            "pct":       round(data["value_usd"] / denom * 100, 1) if denom else 0,
            "count":     data["count"],
        }
        for cls, data in sorted(
            asset_totals.items(), key=lambda x: -x[1]["value_usd"]
        )
    }

    # Concentration metrics
    top10_val = sum(p["value_usd"] for p in sorted_positions[:10])
    top25_val = sum(p["value_usd"] for p in sorted_positions[:25])
    concentration = {
        "top_10_pct":      round(top10_val / denom * 100, 1) if denom else None,
        "top_25_pct":      round(top25_val / denom * 100, 1) if denom else None,
        "total_positions": len(sorted_positions),
    }

    # Confidential treatment check: if parsed total is materially less than declared
    # tableValueTotal, the firm likely received permission to omit certain positions.
    parsed_total = sum(p["value_usd"] for p in sorted_positions)
    possible_confidential = (
        bool(total_value_usd)
        and parsed_total < total_value_usd * 0.95
    )
    parsed_pct = (
        round(parsed_total / total_value_usd * 100, 1)
        if total_value_usd else None
    )

    print(
        f"[ADV Enrichment] Holdings parsed — "
        f"{len(sorted_positions)} unique positions, "
        f"top 10 = {concentration['top_10_pct']}% of portfolio"
        + (f", possible confidential treatment (parsed {parsed_pct}% of declared total)"
           if possible_confidential else "")
    )
    return {
        "top_holdings":               top_holdings,
        "asset_class_breakdown":      asset_breakdown,
        "concentration":              concentration,
        "possible_confidential_positions": possible_confidential,
        "parsed_pct_of_declared_total":    parsed_pct,
    }


# ── 13F portfolio value (proxy AUM for public equity managers) ─────────────────

import re as _re

_SUFFIX_RE = _re.compile(
    r"\b(LLC|LP|L\.P\.|LLP|L\.L\.C\.|Inc\.?|Corp\.?|Co\.?|Ltd\.?|"
    r"Limited|Associates|Group|Holdings|Partners)\b", _re.I
)
_GENERIC_WORDS = frozenset({
    "management", "capital", "advisors", "advisers", "asset", "investments",
    "investment", "financial", "services", "wealth", "global", "fund",
})


def _13f_name_variants(firm_name: str) -> list[str]:
    """
    Generate search query variants for a firm name to improve 13F CIK resolution.
    Ordered from most-specific (lowest false-match risk) to least-specific.
    """
    stripped = _SUFFIX_RE.sub("", firm_name).strip().strip(",").strip()
    words = [w for w in firm_name.split() if len(w) > 2]

    variants: list[str] = [firm_name]  # exact match always first

    if stripped and stripped.lower() != firm_name.lower():
        variants.append(stripped)

    # Two meaningful words (e.g. "Ares Management")
    if len(words) >= 2:
        two = " ".join(words[:2])
        if two not in variants:
            variants.append(two)

    # Single first word only if it's distinctive (not a generic like "Capital")
    if words and words[0].lower() not in _GENERIC_WORDS and words[0] not in variants:
        variants.append(words[0])

    return variants


def _entity_name_matches(edgar_name: str, firm_name: str) -> bool:
    """
    Cross-validate that the EDGAR entity name plausibly belongs to the searched firm.

    Strips only hard legal suffixes (LLC/LP/Inc/Corp/Ltd) but keeps words like
    "management" and "capital" — these DO distinguish firms.
    E.g. "Ares Management" ≠ "Ares Capital": overlap on "ares" alone = 1/2 = 0.5,
    which falls below the 0.6 threshold, so the false match is rejected.
    """
    if not edgar_name or not firm_name:
        return False

    _LEGAL_SUFFIXES = frozenset({
        "llc", "lp", "llp", "inc", "corp", "ltd", "limited", "plc", "co",
    })

    def _norm(s: str) -> set[str]:
        tokens = _re.sub(r"[^\w\s]", " ", s.lower()).split()
        # Keep meaningful words — only drop hard legal suffixes, NOT "management"/"capital"
        return {t for t in tokens if len(t) > 2 and t not in _LEGAL_SUFFIXES}

    query_words = _norm(firm_name)
    edgar_words = _norm(edgar_name)

    if not query_words:
        return True

    overlap = query_words & edgar_words
    # Threshold 0.6: requires majority overlap, not just a single shared first word
    return len(overlap) / len(query_words) >= 0.6


def _find_cik_for_13f(firm_name: str) -> Optional[str]:
    """
    Find EDGAR CIK for a firm by searching 13F-HR filings on EFTS.

    For each name variant (most → least specific), fetches the top EDGAR hit
    and cross-validates the entity name before accepting the CIK. This prevents
    a short variant like "Ares" from resolving to "Ares Capital Corporation"
    instead of "Ares Management LLC".
    """
    for variant in _13f_name_variants(firm_name):
        for query in [f'"{variant}"', variant]:
            data = _json(EFTS_URL, {"q": query, "forms": "13F-HR"})
            if not data:
                time.sleep(0.2)
                continue

            hits = data.get("hits", {}).get("hits", [])
            for hit in hits[:3]:  # check top 3 results, not just the first
                src = hit.get("_source", {})
                ciks = src.get("ciks", [])
                # display_names is the filer name on the 13F filing
                display_names = src.get("display_names", [])
                edgar_name = display_names[0] if display_names else ""

                if not ciks:
                    continue

                cik = str(int(ciks[0]))

                # Cross-validate: entity name must plausibly match the searched firm
                if _entity_name_matches(edgar_name, firm_name):
                    print(
                        f"[ADV Enrichment] 13F CIK resolved: '{edgar_name}' "
                        f"(CIK={cik}) matched via query='{variant}'"
                    )
                    return cik
                else:
                    print(
                        f"[ADV Enrichment] 13F hit rejected: '{edgar_name}' "
                        f"does not match '{firm_name}' (query='{variant}')"
                    )

            time.sleep(0.2)

    print(f"[ADV Enrichment] No validated 13F CIK found for '{firm_name}'")
    return None


def _latest_13f_from_submissions(cik: str) -> Optional[dict]:
    """
    Use EDGAR submissions API to find the most recent 13F-HR filing (or amendment).
    Prefers 13F-HR/A over 13F-HR for the same reporting period.
    Returns dict with accession, filing_date, period_of_report or None.
    """
    url = SUBMISSIONS.format(cik=cik.lstrip("0").zfill(10))
    data = _json(url)
    if not data:
        return None
    recent = data.get("filings", {}).get("recent", {})
    forms   = recent.get("form", [])
    dates   = recent.get("filingDate", [])
    accs    = recent.get("accessionNumber", [])
    periods = recent.get("reportDate", [])

    best = None
    for i, ft in enumerate(forms):
        if ft in ("13F-HR", "13F-HR/A"):
            entry = {
                "accession":        accs[i],
                "filing_date":      dates[i]   if i < len(dates)   else None,
                "period_of_report": periods[i] if i < len(periods) else None,
            }
            if best is None:
                best = entry
            elif ft.endswith("/A") and entry["period_of_report"] == best["period_of_report"]:
                # Prefer the amendment for the same reporting period
                best = entry
            else:
                # Submissions are newest-first; once past the latest period, stop
                break
    return best


def _xml_file_from_submissions(cik: str, acc: str) -> Optional[str]:
    """
    Use the EDGAR submissions API to find the primary document for a 13F filing.
    The submissions API includes primaryDocument for each filing, which is more
    reliable than scraping the HTML index page.
    """
    cik_padded = cik.lstrip("0").zfill(10)
    url = SUBMISSIONS.format(cik=cik_padded)
    data = _json(url)
    if not data:
        return None

    recent = data.get("filings", {}).get("recent", {})
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    for idx, filed_acc in enumerate(accessions):
        if filed_acc == acc and idx < len(primary_docs):
            doc = primary_docs[idx]
            if doc and doc.lower().endswith(".xml"):
                print(
                    f"[ADV Enrichment] XML file resolved via submissions API: {doc} "
                    f"(acc={acc})"
                )
                return doc
            break

    return None


def _xml_file_from_html_index(cik: str, acc: str) -> Optional[str]:
    """
    Scrape the EDGAR filing HTML index to find the primary 13F XML filename.
    Returns just the filename (not the full URL).
    This is the fallback when the submissions API doesn't return a usable
    primaryDocument.
    """
    acc_clean = acc.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
    html = _text(base + acc + "-index.htm")
    if not html:
        return None
    # Look for primary_doc.xml (has tableValueTotal) but NOT inside xslForm subdir
    for name in re.findall(r'href="(?:[^"]*?/)?([^/\"]+\.xml)"', html, re.I):
        if name.lower() == "primary_doc.xml":
            return name
    # Fallback to any .xml not in an xsl subdirectory
    for name in re.findall(r'href="(?:[^"]*?/)?([^/\"]+\.xml)"', html, re.I):
        if "xsl" not in name.lower() and name.lower() not in ("xsl.xml",):
            return name
    return None


def _xml_file_from_filing(cik: str, acc: str) -> Optional[str]:
    """
    Find the primary 13F XML filename for a given filing.

    Strategy:
      1. Try submissions API primaryDocument (most reliable, machine-readable)
      2. Fall back to HTML index scraping (handles older filings)
      3. Log a traceable warning if both fail
    """
    # Primary: submissions API
    xml_file = _xml_file_from_submissions(cik, acc)
    if xml_file:
        return xml_file

    # Fallback: HTML index scraping
    xml_file = _xml_file_from_html_index(cik, acc)
    if xml_file:
        print(
            f"[ADV Enrichment] XML file resolved via HTML index fallback: {xml_file} "
            f"(acc={acc})"
        )
        return xml_file

    # Both approaches failed — log a traceable warning
    print(
        f"[ADV Enrichment] WARNING: Could not locate XML document for "
        f"CIK={cik}, accession={acc}. Neither submissions API nor HTML index "
        f"returned an XML file. The 13F parse will be skipped for this filing."
    )
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


def _all_13f_from_submissions(cik: str, max_quarters: int = 8) -> list[dict]:
    """Return up to max_quarters most recent 13F-HR filings, preferring amendments over originals."""
    url  = SUBMISSIONS.format(cik=cik.lstrip("0").zfill(10))
    data = _json(url)
    if not data:
        return []
    recent  = data.get("filings", {}).get("recent", {})
    forms   = recent.get("form",          [])
    dates   = recent.get("filingDate",    [])
    accs    = recent.get("accessionNumber", [])
    periods = recent.get("reportDate",    [])

    # Deduplicate by reporting period — prefer 13F-HR/A over 13F-HR for same period
    seen_periods: dict[str, dict] = {}
    for i, ft in enumerate(forms):
        if ft in ("13F-HR", "13F-HR/A"):
            entry = {
                "accession":        accs[i],
                "filing_date":      dates[i]   if i < len(dates)   else None,
                "period_of_report": periods[i] if i < len(periods) else None,
            }
            period_key = entry["period_of_report"] or accs[i]
            if period_key not in seen_periods or ft.endswith("/A"):
                seen_periods[period_key] = entry
        if len(seen_periods) >= max_quarters:
            break
    return list(seen_periods.values())


def _fetch_13f_quarters(cik: str, n_quarters: int = 8) -> list[dict]:
    """
    Parse the last n_quarters of 13F-HR filings for a known CIK.
    Each item: {period, filing_date, accession, portfolio_value_usd,
                portfolio_value_fmt, holdings_count, qoq_change_pct}
    Returns list sorted ascending by period.
    Hard deadline: stop after 90 seconds total to prevent pipeline hangs.
    """
    import time as _time
    deadline = _time.monotonic() + 90  # 90s total budget for all quarters

    filings = _all_13f_from_submissions(cik, max_quarters=n_quarters)
    history = []
    for filing in filings:
        if _time.monotonic() > deadline:
            print(f"[13F history] Time budget exceeded — returning {len(history)} quarters fetched so far")
            break
        acc    = filing["accession"]
        period = filing["period_of_report"]
        xml_file = _xml_file_from_filing(cik, acc)
        if xml_file:
            parsed = _parse_13f_xml(cik, acc, xml_file, period)
            if parsed.get("portfolio_value_usd"):
                history.append({
                    "period":              period,
                    "filing_date":         filing["filing_date"],
                    "accession":           acc,
                    "portfolio_value_usd": parsed["portfolio_value_usd"],
                    "portfolio_value_fmt": parsed.get("portfolio_value_fmt"),
                    "holdings_count":      parsed.get("holdings_count"),
                    "qoq_change_pct":      None,
                })
        time.sleep(0.3)  # respect SEC rate limits

    history.sort(key=lambda x: x.get("period") or "")

    # Compute quarter-over-quarter portfolio value change
    for i in range(1, len(history)):
        prev = history[i - 1]["portfolio_value_usd"]
        curr = history[i]["portfolio_value_usd"]
        if prev:
            history[i]["qoq_change_pct"] = round((curr - prev) / prev * 100, 1)

    return history


def get_13f_portfolio_value(firm_name: str) -> dict:
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

    # Step 2: get most recent 13F-HR accession via submissions API (prefers /A amendments)
    filing = _latest_13f_from_submissions(cik)
    if not filing:
        result["note"] = f"CIK {cik} found but no 13F-HR in recent submissions"
        return result

    acc    = filing["accession"]
    result["accession"]        = acc
    result["filing_date"]      = filing["filing_date"]
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

    # Step 5: parse individual holdings from infotable XML
    period = filing["period_of_report"] or ""
    use_dollars = period >= "2024-12-31"
    infotable = _infotable_file_from_filing(cik, acc)
    if infotable and result.get("portfolio_value_usd"):
        holdings_data = _parse_13f_holdings(
            cik, acc, infotable,
            use_dollars=use_dollars,
            total_value_usd=result["portfolio_value_usd"],
        )
        result["holdings_breakdown"] = holdings_data
    else:
        result["holdings_breakdown"] = {}

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


# ── Brochure PDF download ────────────────────────────────────────────────────

BROCHURE_URL = (
    "https://adviserinfo.sec.gov/IAPD/Content/Common/"
    "crd_iapd_Brochure.aspx?BROCHUREPK={brochure_id}"
)


def fetch_brochure_text(brochure_version_id: str) -> Optional[str]:
    """
    Attempt to download an ADV Part 2A brochure PDF and extract text.

    The IAPD brochure endpoint serves an SPA HTML page for most firms (not a
    direct PDF download). This function detects that case and returns None
    rather than raising.

    Returns extracted text if the PDF is accessible, None otherwise.
    """
    if not brochure_version_id:
        return None

    url = BROCHURE_URL.format(brochure_id=brochure_version_id)
    print(f"[Brochure] Attempting download: brochure ID {brochure_version_id}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.exceptions.RequestException as exc:
        print(f"[Brochure] Download failed: {exc}")
        return None

    if resp.status_code == 403:
        print("[Brochure] Not publicly accessible (403) — skipping")
        return None

    if resp.status_code == 404:
        print("[Brochure] Not found (404) — skipping")
        return None

    if resp.status_code != 200:
        print(f"[Brochure] Unexpected status {resp.status_code} — skipping")
        return None

    content_type = resp.headers.get("content-type", "").lower()

    # Check if response is a PDF
    if "pdf" in content_type or "octet-stream" in content_type:
        return _extract_pdf_text(resp.content, brochure_version_id)

    # Check if response is HTML (SPA login/redirect page)
    if "html" in content_type or resp.content[:20].strip().startswith(b"<"):
        print("[Brochure] Not publicly accessible — received HTML page, not PDF. Skipping")
        return None

    # Unknown content type — try parsing as PDF anyway
    if len(resp.content) > 1000 and resp.content[:5] == b"%PDF-":
        return _extract_pdf_text(resp.content, brochure_version_id)

    print(f"[Brochure] Unrecognized response (content-type: {content_type}) — skipping")
    return None


def _extract_pdf_text(pdf_bytes: bytes, brochure_id: str) -> Optional[str]:
    """Extract text from PDF bytes using pypdf."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        full_text = "\n".join(pages_text)
        print(
            f"[Brochure] PDF extracted — {len(reader.pages)} pages, "
            f"{len(full_text)} chars"
        )
        return full_text if full_text.strip() else None
    except ImportError:
        print("[Brochure] pypdf not installed — cannot extract brochure text")
        return None
    except Exception as exc:
        print(f"[Brochure] PDF parse error for brochure {brochure_id}: {exc}")
        return None


def split_brochure_into_chunks(text: str) -> list[dict]:
    """
    Split ADV Part 2A brochure text into labeled chunks by section headers.

    Standard ADV Part 2A sections are Item 1 through Item 18. We split on
    these boundaries so each chunk corresponds to one disclosure topic.
    """
    if not text:
        return []

    # Split on "Item N" headers (e.g., "Item 4", "Item 5 – Fees")
    parts = re.split(r"(?i)(?=\bItem\s+\d{1,2}\b)", text)

    chunks: list[dict] = []
    for part in parts:
        part = part.strip()
        if len(part) < 50:
            continue

        # Extract item number for labeling
        header_match = re.match(r"(?i)(Item\s+\d{1,2})\b(.{0,80})", part)
        if header_match:
            item_num = header_match.group(1).strip()
            item_rest = header_match.group(2).strip().strip("–—:-. ")
            label = f"ADV Part 2A {item_num}: {item_rest}" if item_rest else f"ADV Part 2A {item_num}"
        else:
            label = "ADV Part 2A (preamble)"

        chunks.append({
            "source": f"brochure:{label[:40]}",
            "label": label[:80],
            "content": part[:3000],  # cap chunk size for RAG context window
        })

    return chunks


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
      - thirteenf_history: QoQ history (up to 8 quarters, with qoq_change_pct)
      - disclosures:     Detailed disclosure events from IAPD iacontent
      - brochure:        ADV Part 2A brochure metadata
      - aum_note:        Explanation of AUM data availability
    """
    result = {
        "thirteenf":         {},
        "thirteenf_history": [],
        "disclosures":       [],
        "brochure":          {},
        "aum_note": (
            "Regulatory AUM is in ADV Part 1A Item 5 (IARD system). "
            "Not accessible via free public API — requires IAPD website, "
            "Preqin, Bloomberg, or direct GP engagement."
        ),
        "error": None,
    }

    # 13F portfolio value (latest)
    print(f"[ADV Enrichment] Fetching 13F data for '{firm_name}'")
    result["thirteenf"] = get_13f_portfolio_value(firm_name)

    # 13F history — reuse the CIK already resolved above (no second EFTS search)
    cik = result["thirteenf"].get("cik")
    if cik:
        print(f"[ADV Enrichment] Fetching 13F history for CIK {cik} (up to 8 quarters)")
        result["thirteenf_history"] = _fetch_13f_quarters(cik, n_quarters=8)

    # Disclosures and brochure from iacontent (if provided)
    if iacontent:
        result["disclosures"] = parse_iapd_disclosures(iacontent)
        result["brochure"]    = parse_brochure_metadata(iacontent)

        # Attempt brochure PDF download and text extraction
        brochure_meta = result["brochure"]
        bv_id = brochure_meta.get("brochure_version") if brochure_meta else None
        if bv_id:
            brochure_text = fetch_brochure_text(str(bv_id))
            if brochure_text:
                result["brochure"]["text_extracted"] = True
                result["brochure_chunks"] = split_brochure_into_chunks(brochure_text)
                result["brochure"]["note"] = (
                    f"Brochure PDF downloaded and parsed — "
                    f"{len(result['brochure_chunks'])} section(s) extracted"
                )
            else:
                result["brochure"]["text_extracted"] = False
                result["brochure_chunks"] = []

    pv = result["thirteenf"].get("portfolio_value_fmt")
    print(
        f"[ADV Enrichment] Done — 13F portfolio={pv or 'N/A'}, "
        f"disclosures={len(result['disclosures'])}"
    )
    return result
