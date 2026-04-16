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
import re


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
                              tolerance: float = 0.50) -> dict:
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

    adv_count = int(adv_fund_count_raw) if adv_fund_count_raw is not None else None

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


def run_all(analysis: dict, raw_data: dict) -> list[dict]:
    """Run all reconciliation checks and return results list."""
    return [
        check_aum_reconciliation(analysis, raw_data),
        check_fund_count_reconciliation(analysis, raw_data),
    ]
