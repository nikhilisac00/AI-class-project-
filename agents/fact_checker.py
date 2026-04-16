"""
Fact Checker Agent — deterministic raw-to-analysis checks.

Compares raw API data against LLM-generated analysis output to detect
hallucinations, transcription errors, and data drift before a memo is
released to the IC.  Each check returns a structured result dict with
status PASS | WARN | FAIL.
"""

from __future__ import annotations

import re

# ── Constants ──────────────────────────────────────────────────────────────────

_FILLER_WORDS: frozenset[str] = frozenset(
    {"llc", "inc", "ltd", "the", "and", "of", "group", "lp", "co", "corp", "company"}
)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _parse_usd(value: str | None) -> float | None:
    """Parse a USD string like '$5.00B', '$450M', '$2.50T', '$1,000,000' to float."""
    if not value or not isinstance(value, str):
        return None
    sanitized = value.upper().replace(",", "").replace("$", "").strip()
    multiplier = 1.0
    if sanitized.endswith("T"):
        multiplier = 1e12
        sanitized = sanitized[:-1]
    elif sanitized.endswith("B"):
        multiplier = 1e9
        sanitized = sanitized[:-1]
    elif sanitized.endswith("M"):
        multiplier = 1e6
        sanitized = sanitized[:-1]
    elif sanitized.endswith("K"):
        multiplier = 1e3
        sanitized = sanitized[:-1]
    try:
        return float(sanitized) * multiplier
    except ValueError:
        match = re.search(r"[\d.]+", sanitized)
        if match:
            try:
                return float(match.group()) * multiplier
            except ValueError:
                pass
    return None


def _check(
    name: str,
    layer: str,
    status: str,
    detail: str,
    evidence: dict,
) -> dict:
    """Build a standardised check result dict."""
    return {
        "check": name,
        "layer": layer,
        "status": status,
        "detail": detail,
        "evidence": evidence,
    }


def _normalise_name(name: str) -> str:
    """Lowercase and strip punctuation from a firm name."""
    return re.sub(r"[^\w\s]", "", name.lower()).strip()


def _significant_words(name: str) -> set[str]:
    """Return meaningful words from a firm name, excluding filler words."""
    words = set(_normalise_name(name).split())
    return words - _FILLER_WORDS


# ── Individual checks ──────────────────────────────────────────────────────────

def _check_firm_name(analysis: dict, raw_data: dict) -> dict:
    """
    Fuzzy firm name match between raw ADV data and LLM analysis output.

    Passes if either name contains the other (case-insensitive) or if the
    significant words of one name are a subset of the other's significant words.
    """
    raw_name: str | None = (raw_data.get("adv_summary") or {}).get("firm_name")
    analysis_name: str | None = (analysis.get("firm_overview") or {}).get("name")

    evidence = {"raw": raw_name, "analysis": analysis_name}

    if raw_name is None or analysis_name is None:
        return _check(
            "Firm Name (Raw → Analysis)",
            "raw_to_analysis",
            "WARN",
            "One or both firm names are null — cannot compare.",
            evidence,
        )

    norm_raw = _normalise_name(raw_name)
    norm_analysis = _normalise_name(analysis_name)

    # Substring containment check (handles abbreviations)
    if norm_raw in norm_analysis or norm_analysis in norm_raw:
        return _check(
            "Firm Name (Raw → Analysis)",
            "raw_to_analysis",
            "PASS",
            f"Firm name match confirmed: '{raw_name}' ↔ '{analysis_name}'.",
            evidence,
        )

    # Significant word overlap check
    raw_words = _significant_words(raw_name)
    analysis_words = _significant_words(analysis_name)

    if raw_words and analysis_words:
        if raw_words.issubset(analysis_words) or analysis_words.issubset(raw_words):
            return _check(
                "Firm Name (Raw → Analysis)",
                "raw_to_analysis",
                "PASS",
                f"Firm name significant words match: '{raw_name}' ↔ '{analysis_name}'.",
                evidence,
            )

    return _check(
        "Firm Name (Raw → Analysis)",
        "raw_to_analysis",
        "FAIL",
        (
            f"Firm name mismatch: raw='{raw_name}', analysis='{analysis_name}'. "
            "Analysis may reference a different entity."
        ),
        evidence,
    )


def _check_crd(analysis: dict, raw_data: dict) -> dict:
    """Exact string match of CRD number between raw ADV data and LLM analysis."""
    raw_crd: str | None = (raw_data.get("adv_summary") or {}).get("crd_number")
    analysis_crd: str | None = (analysis.get("firm_overview") or {}).get("crd")

    evidence = {"raw": raw_crd, "analysis": analysis_crd}

    if raw_crd is None or analysis_crd is None:
        return _check(
            "CRD Number (Raw → Analysis)",
            "raw_to_analysis",
            "WARN",
            "One or both CRD values are null — cannot compare.",
            evidence,
        )

    if str(raw_crd).strip() == str(analysis_crd).strip():
        return _check(
            "CRD Number (Raw → Analysis)",
            "raw_to_analysis",
            "PASS",
            f"CRD number confirmed: {raw_crd}.",
            evidence,
        )

    return _check(
        "CRD Number (Raw → Analysis)",
        "raw_to_analysis",
        "FAIL",
        f"CRD mismatch: raw={raw_crd}, analysis={analysis_crd}.",
        evidence,
    )


def _check_registration_status(analysis: dict, raw_data: dict) -> dict:
    """
    Exact match of registration status between raw ADV data and LLM analysis.

    Returns WARN when one value is null (insufficient data to assert FAIL).
    """
    raw_status: str | None = (raw_data.get("adv_summary") or {}).get("registration_status")
    analysis_status: str | None = (analysis.get("firm_overview") or {}).get("registration_status")

    evidence = {"raw": raw_status, "analysis": analysis_status}

    if raw_status is None or analysis_status is None:
        return _check(
            "Registration Status (Raw → Analysis)",
            "raw_to_analysis",
            "WARN",
            (
                "One or both registration status values are null — "
                f"raw='{raw_status}', analysis='{analysis_status}'."
            ),
            evidence,
        )

    if raw_status.strip() == analysis_status.strip():
        return _check(
            "Registration Status (Raw → Analysis)",
            "raw_to_analysis",
            "PASS",
            f"Registration status confirmed: '{raw_status}'.",
            evidence,
        )

    return _check(
        "Registration Status (Raw → Analysis)",
        "raw_to_analysis",
        "FAIL",
        (
            f"Registration status mismatch: raw='{raw_status}', "
            f"analysis='{analysis_status}'."
        ),
        evidence,
    )


def _check_portfolio_value(analysis: dict, raw_data: dict, tolerance: float = 0.01) -> dict:
    """
    Compare 13F portfolio value between raw XML data and LLM analysis.

    Uses a 1% tolerance to allow for minor formatting differences.
    Returns WARN when one value is null.
    """
    raw_fmt: str | None = (
        (raw_data.get("adv_xml_data") or {})
        .get("thirteenf", {})
        .get("portfolio_value_fmt")
    )
    analysis_fmt: str | None = (analysis.get("13f_filings") or {}).get("portfolio_value")

    evidence = {"raw": raw_fmt, "analysis": analysis_fmt}

    raw_val = _parse_usd(raw_fmt)
    analysis_val = _parse_usd(analysis_fmt)

    if raw_val is None or analysis_val is None:
        return _check(
            "Portfolio Value (Raw → Analysis)",
            "raw_to_analysis",
            "WARN",
            (
                "One or both portfolio value fields are null or unparseable — "
                f"raw='{raw_fmt}', analysis='{analysis_fmt}'."
            ),
            evidence,
        )

    if raw_val == 0 and analysis_val == 0:
        return _check(
            "Portfolio Value (Raw → Analysis)",
            "raw_to_analysis",
            "PASS",
            "Both portfolio values are zero.",
            evidence,
        )

    denominator = max(abs(raw_val), abs(analysis_val))
    relative_diff = abs(raw_val - analysis_val) / denominator

    if relative_diff <= tolerance:
        return _check(
            "Portfolio Value (Raw → Analysis)",
            "raw_to_analysis",
            "PASS",
            (
                f"Portfolio value confirmed within {tolerance:.0%} tolerance: "
                f"raw='{raw_fmt}', analysis='{analysis_fmt}'."
            ),
            evidence,
        )

    return _check(
        "Portfolio Value (Raw → Analysis)",
        "raw_to_analysis",
        "FAIL",
        (
            f"Portfolio value divergence ({relative_diff:.1%} > {tolerance:.0%} tolerance): "
            f"raw='{raw_fmt}', analysis='{analysis_fmt}'."
        ),
        evidence,
    )


def _check_fund_count(analysis: dict, raw_data: dict, max_diff: int = 2) -> dict:
    """
    Compare fund count between raw fund_discovery data and LLM analysis.

    Returns WARN when the absolute difference exceeds `max_diff` (default 2).
    """
    funds_list: list = (raw_data.get("fund_discovery") or {}).get("funds") or []
    raw_count: int = len(funds_list)

    analysis_count_raw = (analysis.get("funds_analysis") or {}).get("total_funds_found")

    evidence = {"raw_count": raw_count, "analysis_count": analysis_count_raw}

    if analysis_count_raw is None:
        return _check(
            "Fund Count (Raw → Analysis)",
            "raw_to_analysis",
            "WARN",
            f"Analysis fund count is null; raw discovery found {raw_count} fund(s).",
            evidence,
        )

    analysis_count = int(analysis_count_raw)
    diff = abs(raw_count - analysis_count)

    if diff <= max_diff:
        return _check(
            "Fund Count (Raw → Analysis)",
            "raw_to_analysis",
            "PASS",
            (
                f"Fund count within acceptable range: "
                f"raw={raw_count}, analysis={analysis_count} (diff={diff})."
            ),
            evidence,
        )

    return _check(
        "Fund Count (Raw → Analysis)",
        "raw_to_analysis",
        "WARN",
        (
            f"Fund count divergence: raw={raw_count}, analysis={analysis_count} "
            f"(diff={diff} > max_diff={max_diff}). Verify fund enumeration."
        ),
        evidence,
    )


# ── Public entry point ─────────────────────────────────────────────────────────

def run_deterministic_checks(
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    scorecard: dict,
    memo_text: str,
) -> list[dict]:
    """
    Run all deterministic raw-to-analysis fact checks.

    Args:
        analysis:    Structured output from the fund analysis agent.
        risk_report: Structured output from the risk flagging agent.
        raw_data:    Raw data dict from the data ingestion agent.
        scorecard:   IC scorecard dict from the scorecard agent.
        memo_text:   Final rendered memo text.

    Returns:
        List of check result dicts (keys: check, layer, status, detail, evidence).
    """
    return [
        _check_firm_name(analysis, raw_data),
        _check_crd(analysis, raw_data),
        _check_registration_status(analysis, raw_data),
        _check_portfolio_value(analysis, raw_data),
        _check_fund_count(analysis, raw_data),
    ]
