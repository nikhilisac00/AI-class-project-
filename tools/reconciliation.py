"""
Cross-source reconciliation checks.

Finance-domain data quality checks that compare values across SEC data sources.
Each check returns a dict with keys:
  check      — name of the check
  status     — "PASS" | "WARN" | "FAIL" | "SKIP" (SKIP = insufficient data)
  detail     — human-readable explanation
  sources    — list of sources compared
"""

from __future__ import annotations
import os
import re

# Bug #23: allow LP-specific tolerance to be configured via env var.
# Default remains 50% for backwards compatibility.
_DEFAULT_AUM_TOLERANCE = float(os.getenv("AUM_RECONCILIATION_TOLERANCE", "0.50"))


def _parse_usd(value: str | None) -> float | None:
    """Parse a USD string like '$1.2B', '$450M', '$2,300,000' into a float (USD)."""
    if not value or not isinstance(value, str):
        return None
    s = value.upper().replace(",", "").replace("$", "").strip()
    multiplier = 1.0
    if s.endswith("T"):
        multiplier = 1e12
        s = s[:-1]
    elif s.endswith("B"):
        multiplier = 1e9
        s = s[:-1]
    elif s.endswith("M"):
        multiplier = 1e6
        s = s[:-1]
    elif s.endswith("K"):
        multiplier = 1e3
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        # Try extracting first number from the string
        m = re.search(r"[\d.]+", s)
        if m:
            try:
                return float(m.group()) * multiplier
            except ValueError:
                pass
    return None


def check_aum_reconciliation(analysis: dict, raw_data: dict,
                              tolerance: float = _DEFAULT_AUM_TOLERANCE) -> dict:
    """
    Compare 13F portfolio value (proxy AUM) against ADV regulatory AUM.

    These will legitimately differ — 13F only covers US long equity positions
    while ADV AUM is regulatory AUM across all strategies. We flag when they
    diverge by more than `tolerance` (default 50%) as a data-quality signal
    worth noting in the memo, not necessarily a red flag.
    """
    adv_aum_str = (analysis.get("firm_overview") or {}).get("aum_regulatory")
    tf_val_str  = (analysis.get("13f_filings")   or {}).get("portfolio_value")

    adv_aum = _parse_usd(adv_aum_str)
    tf_val  = _parse_usd(tf_val_str)

    if adv_aum is None and tf_val is None:
        return {
            "check": "AUM Reconciliation (13F vs ADV)",
            "status": "SKIP",
            "detail": "Neither ADV regulatory AUM nor 13F portfolio value is available.",
            "sources": ["ADV (IAPD)", "SEC EDGAR 13F"],
        }

    if adv_aum is None:
        return {
            "check": "AUM Reconciliation (13F vs ADV)",
            "status": "SKIP",
            "detail": f"ADV regulatory AUM not available; 13F portfolio value is {tf_val_str}.",
            "sources": ["ADV (IAPD)", "SEC EDGAR 13F"],
        }

    if tf_val is None:
        return {
            "check": "AUM Reconciliation (13F vs ADV)",
            "status": "SKIP",
            "detail": f"13F portfolio value not available; ADV regulatory AUM is {adv_aum_str}.",
            "sources": ["ADV (IAPD)", "SEC EDGAR 13F"],
        }

    # 13F AUM should be <= ADV AUM (13F is a subset of total AUM)
    ratio = tf_val / adv_aum if adv_aum > 0 else None

    if ratio is None:
        status = "SKIP"
        detail = "Cannot compute ratio — ADV AUM is zero."
    elif ratio > (1.0 + tolerance):
        status = "WARN"
        detail = (
            f"13F portfolio value ({tf_val_str}) is {ratio:.1%} of ADV regulatory AUM "
            f"({adv_aum_str}), exceeding the {tolerance:.0%} tolerance. "
            "13F covers US long equity only; a ratio >100% warrants verification "
            "(possible ADV AUM understatement or 13F includes short positions)."
        )
    elif ratio < 0.01:
        status = "WARN"
        detail = (
            f"13F portfolio value ({tf_val_str}) is only {ratio:.2%} of ADV regulatory AUM "
            f"({adv_aum_str}). Manager may be primarily non-equity or non-US."
        )
    else:
        status = "PASS"
        detail = (
            f"13F portfolio value ({tf_val_str}) is {ratio:.1%} of ADV regulatory AUM "
            f"({adv_aum_str}). Within expected range for a partially equity-focused manager."
        )

    return {
        "check": "AUM Reconciliation (13F vs ADV)",
        "status": status,
        "detail": detail,
        "sources": ["ADV (IAPD)", "SEC EDGAR 13F"],
        "adv_aum": adv_aum_str,
        "thirteenf_value": tf_val_str,
        "ratio": round(ratio, 4) if ratio is not None else None,
    }


def check_fund_count_reconciliation(analysis: dict, raw_data: dict) -> dict:
    """
    Compare Form D fund count against ADV private fund count.

    ADV Part 1A Schedule D lists private funds; Form D filings on EDGAR are
    the registration events. We expect Form D count >= ADV fund count since
    Form D captures fundraising events (multiple per fund over its life).
    """
    funds_analysis = analysis.get("funds_analysis") or {}
    adv_fund_count_raw = funds_analysis.get("total_funds_found")

    fund_discovery = raw_data.get("fund_discovery") or {}
    form_d_funds   = fund_discovery.get("funds") or []
    form_d_count   = len([f for f in form_d_funds
                          if "Form D" in str(f.get("source", ""))])

    if adv_fund_count_raw is None and form_d_count == 0:
        return {
            "check": "Fund Count Reconciliation (Form D vs ADV)",
            "status": "SKIP",
            "detail": "No fund count data available from either ADV or Form D.",
            "sources": ["ADV (IAPD)", "SEC EDGAR Form D"],
        }

    try:
        adv_count = int(adv_fund_count_raw) if adv_fund_count_raw is not None else None
    except (TypeError, ValueError):
        adv_count = None

    if adv_count is None:
        return {
            "check": "Fund Count Reconciliation (Form D vs ADV)",
            "status": "SKIP",
            "detail": f"ADV fund count not available. Form D shows {form_d_count} filing(s).",
            "sources": ["ADV (IAPD)", "SEC EDGAR Form D"],
        }

    if form_d_count == 0:
        status = "WARN"
        detail = (
            f"ADV analysis references {adv_count} fund(s) but no Form D filings were found. "
            "Private funds typically must file Form D. Possible causes: funds are below "
            "reporting threshold, filings are under a different name, or data pull incomplete."
        )
    elif form_d_count >= adv_count:
        status = "PASS"
        detail = (
            f"Form D shows {form_d_count} filing(s); ADV analysis references {adv_count} fund(s). "
            "Consistent — Form D count ≥ ADV fund count is expected (multiple filings per fund)."
        )
    else:
        status = "WARN"
        detail = (
            f"Form D shows only {form_d_count} filing(s) but ADV analysis references "
            f"{adv_count} fund(s). {adv_count - form_d_count} fund(s) may be missing Form D "
            "filings. Recommend verifying on EDGAR."
        )

    return {
        "check": "Fund Count Reconciliation (Form D vs ADV)",
        "status": status,
        "detail": detail,
        "sources": ["ADV (IAPD)", "SEC EDGAR Form D"],
        "adv_fund_count": adv_count,
        "form_d_count": form_d_count,
    }


def check_personnel_reconciliation(analysis: dict, raw_data: dict) -> dict:
    """
    Compare key personnel count against employee headcount from analysis and ADV.

    Flags data inconsistencies between the number of identified key personnel
    and the total reported employee base. A firm with many employees but zero
    identified key personnel warrants scrutiny; more key personnel than total
    employees indicates a data extraction error.
    """
    firm_overview = analysis.get("firm_overview") or {}
    num_employees_analysis = firm_overview.get("num_employees")
    key_personnel_count = len(analysis.get("key_personnel") or [])
    adv_summary = raw_data.get("adv_summary") or {}
    num_employees_adv = adv_summary.get("num_employees")

    # Coerce employee counts to int where possible
    def _to_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    employees_analysis = _to_int(num_employees_analysis)
    employees_adv = _to_int(num_employees_adv)

    # Prefer analysis-derived count; fall back to ADV raw field
    num_employees = employees_analysis if employees_analysis is not None else employees_adv

    if num_employees is None and key_personnel_count == 0:
        return {
            "check": "Personnel Reconciliation",
            "status": "SKIP",
            "detail": "No employee count or key personnel data available.",
            "sources": ["ADV (IAPD)", "Analysis"],
        }

    if key_personnel_count == 0 and num_employees is not None and num_employees > 10:
        return {
            "check": "Personnel Reconciliation",
            "status": "WARN",
            "detail": (
                f"No key personnel identified despite sizable employee base "
                f"({num_employees} employees). Key person extraction may have failed "
                "or ADV Part 2 brochure was unavailable."
            ),
            "sources": ["ADV (IAPD)", "Analysis"],
        }

    if (
        num_employees is not None
        and key_personnel_count > 0
        and key_personnel_count > num_employees
    ):
        return {
            "check": "Personnel Reconciliation",
            "status": "WARN",
            "detail": (
                f"More key personnel identified ({key_personnel_count}) than total reported "
                f"employees ({num_employees}) — data inconsistency. Possible duplicate "
                "extraction or stale employee count in ADV."
            ),
            "sources": ["ADV (IAPD)", "Analysis"],
        }

    return {
        "check": "Personnel Reconciliation",
        "status": "PASS",
        "detail": (
            f"Key personnel count ({key_personnel_count}) is consistent with reported "
            f"employee base ({num_employees if num_employees is not None else 'unknown'})."
        ),
        "sources": ["ADV (IAPD)", "Analysis"],
    }


def check_section7b_vs_form_d(analysis: dict, raw_data: dict) -> dict:
    """
    Cross-reference ADV Section 7.B private funds against Form D fund discovery.

    Section 7.B is the authoritative list of private funds an adviser manages.
    Form D filings are the offering registrations. A fund in Section 7.B with
    no matching Form D filing may indicate a stale Form D, an exemption, or
    incomplete data pull.
    """
    adv_summary = raw_data.get("adv_summary") or {}
    section7b_funds = adv_summary.get("private_funds_section7b") or []
    fund_discovery = raw_data.get("fund_discovery") or {}
    form_d_funds = fund_discovery.get("funds") or []

    if not section7b_funds:
        return {
            "check": "Section 7.B vs Form D Reconciliation",
            "status": "SKIP",
            "detail": "No Section 7.B private fund data available from ADV PDF.",
            "sources": ["ADV Part 1A Section 7.B", "SEC EDGAR Form D"],
        }

    if not form_d_funds:
        return {
            "check": "Section 7.B vs Form D Reconciliation",
            "status": "WARN",
            "detail": (
                f"ADV Section 7.B lists {len(section7b_funds)} private fund(s) "
                "but no Form D filings were found. Recommend verifying on EDGAR."
            ),
            "sources": ["ADV Part 1A Section 7.B", "SEC EDGAR Form D"],
            "section7b_count": len(section7b_funds),
            "form_d_count": 0,
        }

    # Normalize names for fuzzy matching
    def _norm(name: str) -> set[str]:
        return set(re.sub(r"[^\w\s]", " ", name.lower()).split())

    form_d_names = []
    for fd in form_d_funds:
        name = fd.get("fund_name") or fd.get("name") or ""
        if name:
            form_d_names.append((name, _norm(name)))

    unmatched = []
    for fund in section7b_funds:
        s7b_name = fund.get("fund_name") or ""
        if not s7b_name:
            continue
        s7b_tokens = _norm(s7b_name)
        if not s7b_tokens:
            continue
        # Check for any Form D fund with >= 50% token overlap
        matched = False
        for fd_name, fd_tokens in form_d_names:
            if not fd_tokens:
                continue
            overlap = len(s7b_tokens & fd_tokens)
            if overlap / max(len(s7b_tokens), 1) >= 0.5:
                matched = True
                break
        if not matched:
            unmatched.append(s7b_name)

    if not unmatched:
        status = "PASS"
        detail = (
            f"All {len(section7b_funds)} Section 7.B fund(s) have matching Form D filings. "
            f"Form D shows {len(form_d_funds)} total filing(s)."
        )
    else:
        status = "WARN"
        detail = (
            f"{len(unmatched)} of {len(section7b_funds)} Section 7.B fund(s) "
            f"have no matching Form D filing: {', '.join(unmatched[:5])}"
            + (f" (and {len(unmatched) - 5} more)" if len(unmatched) > 5 else "")
            + ". Possible causes: fund is exempt, uses a different name in Form D, "
            "or Form D filing is missing."
        )

    return {
        "check": "Section 7.B vs Form D Reconciliation",
        "status": status,
        "detail": detail,
        "sources": ["ADV Part 1A Section 7.B", "SEC EDGAR Form D"],
        "section7b_count": len(section7b_funds),
        "form_d_count": len(form_d_funds),
        "unmatched_funds": unmatched[:10],
    }


def run_all(analysis: dict, raw_data: dict) -> list[dict]:
    """Run all reconciliation checks and return results list."""
    return [
        check_aum_reconciliation(analysis, raw_data),
        check_fund_count_reconciliation(analysis, raw_data),
        check_personnel_reconciliation(analysis, raw_data),
        check_section7b_vs_form_d(analysis, raw_data),
    ]
