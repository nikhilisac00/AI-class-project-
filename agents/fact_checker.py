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


def _check_risk_tier_in_memo(risk_report: dict, memo_text: str) -> dict:
    """
    Verify the overall risk tier from the risk report appears in the memo text.

    Fails if the tier string is not found (case-insensitive) in the memo.
    """
    tier: str | None = risk_report.get("overall_risk_tier")
    evidence = {"risk_tier": tier}

    if tier is None:
        return _check(
            "Risk Tier in Memo",
            "analysis_to_memo",
            "WARN",
            "Risk tier is null — cannot verify presence in memo.",
            evidence,
        )

    if tier.lower() in memo_text.lower():
        return _check(
            "Risk Tier in Memo",
            "analysis_to_memo",
            "PASS",
            f"Risk tier '{tier}' confirmed present in memo.",
            evidence,
        )

    return _check(
        "Risk Tier in Memo",
        "analysis_to_memo",
        "FAIL",
        f"Risk tier '{tier}' not found in memo text.",
        evidence,
    )


def _check_high_flags_in_memo(risk_report: dict, memo_text: str) -> dict:
    """
    Verify each HIGH-severity flag from the risk report is referenced in the memo.

    For each HIGH flag, checks if at least 2 key words (4+ chars) from the finding
    appear in the memo, OR the flag category appears in the memo.
    Passes immediately if no HIGH flags exist.
    """
    flags: list = risk_report.get("flags") or []
    high_flags = [flag for flag in flags if (flag.get("severity") or "").upper() == "HIGH"]

    if not high_flags:
        return _check(
            "HIGH Flags in Memo",
            "analysis_to_memo",
            "PASS",
            "No HIGH-severity flags — check not applicable.",
            {"high_flag_count": 0},
        )

    memo_lower = memo_text.lower()
    missing_flags: list[str] = []

    for flag in high_flags:
        finding: str = flag.get("finding") or ""
        category: str = flag.get("category") or ""

        # Check if category appears in memo
        if category and category.lower() in memo_lower:
            continue

        # Extract key words (4+ chars) from finding and check for 2+ matches
        key_words = [word for word in re.findall(r"\b\w{4,}\b", finding.lower()) if word]
        matches = sum(1 for word in key_words if word in memo_lower)
        if matches >= 2:
            continue

        missing_flags.append(f"{category}: {finding}")

    evidence = {"high_flag_count": len(high_flags), "missing_flags": missing_flags}

    if missing_flags:
        return _check(
            "HIGH Flags in Memo",
            "analysis_to_memo",
            "FAIL",
            f"{len(missing_flags)} HIGH flag(s) not referenced in memo: {missing_flags}.",
            evidence,
        )

    return _check(
        "HIGH Flags in Memo",
        "analysis_to_memo",
        "PASS",
        f"All {len(high_flags)} HIGH flag(s) confirmed referenced in memo.",
        evidence,
    )


def _check_portfolio_value_in_memo(analysis: dict, memo_text: str) -> dict:
    """
    Verify the 13F portfolio value from analysis appears in the memo text.

    Returns WARN (not FAIL) if not found — absence may be legitimate.
    Passes if no portfolio value is present in analysis.
    """
    portfolio_value: str | None = (analysis.get("13f_filings") or {}).get("portfolio_value")
    evidence = {"portfolio_value": portfolio_value}

    if portfolio_value is None:
        return _check(
            "Portfolio Value in Memo",
            "analysis_to_memo",
            "PASS",
            "No portfolio value in analysis — check not applicable.",
            evidence,
        )

    if portfolio_value.lower() in memo_text.lower():
        return _check(
            "Portfolio Value in Memo",
            "analysis_to_memo",
            "PASS",
            f"Portfolio value '{portfolio_value}' confirmed present in memo.",
            evidence,
        )

    return _check(
        "Portfolio Value in Memo",
        "analysis_to_memo",
        "WARN",
        f"Portfolio value '{portfolio_value}' not found in memo text.",
        evidence,
    )


def _check_registration_in_memo(analysis: dict, memo_text: str) -> dict:
    """
    Verify the registration status from analysis appears in the memo text.

    Returns WARN (not FAIL) if not found. Passes if no status in analysis.
    """
    reg_status: str | None = (analysis.get("firm_overview") or {}).get("registration_status")
    evidence = {"registration_status": reg_status}

    if reg_status is None:
        return _check(
            "Registration in Memo",
            "analysis_to_memo",
            "PASS",
            "No registration status in analysis — check not applicable.",
            evidence,
        )

    if reg_status.lower() in memo_text.lower():
        return _check(
            "Registration in Memo",
            "analysis_to_memo",
            "PASS",
            f"Registration status '{reg_status}' confirmed present in memo.",
            evidence,
        )

    return _check(
        "Registration in Memo",
        "analysis_to_memo",
        "WARN",
        f"Registration status '{reg_status}' not found in memo text.",
        evidence,
    )


def _check_risk_tier_vs_flags(risk_report: dict) -> dict:
    """
    Cross-check overall risk tier against the count of HIGH-severity flags.

    Fails if tier is LOW but any HIGH flags exist.
    Warns if tier is MEDIUM but more than 2 HIGH flags exist.
    """
    tier: str | None = (risk_report.get("overall_risk_tier") or "").upper()
    flags: list = risk_report.get("flags") or []
    high_count = sum(1 for flag in flags if (flag.get("severity") or "").upper() == "HIGH")

    evidence = {"tier": tier, "high_flag_count": high_count}

    if tier == "LOW" and high_count > 0:
        return _check(
            "Risk Tier vs Flags",
            "cross_agent",
            "FAIL",
            (
                f"Tier is LOW but {high_count} HIGH flag(s) exist — "
                "tier may be under-reported."
            ),
            evidence,
        )

    if tier == "MEDIUM" and high_count > 2:
        return _check(
            "Risk Tier vs Flags",
            "cross_agent",
            "WARN",
            (
                f"Tier is MEDIUM but {high_count} HIGH flag(s) exist — "
                "consider whether tier should be HIGH."
            ),
            evidence,
        )

    return _check(
        "Risk Tier vs Flags",
        "cross_agent",
        "PASS",
        f"Risk tier '{tier}' is consistent with {high_count} HIGH flag(s).",
        evidence,
    )


def _check_scorecard_vs_risk(risk_report: dict, scorecard: dict) -> dict:
    """
    Cross-check IC scorecard recommendation against overall risk tier.

    Warns if recommendation contains PROCEED (but not CAUTION) and tier is HIGH.
    Warns if recommendation contains PASS and tier is LOW.
    """
    tier: str | None = (risk_report.get("overall_risk_tier") or "").upper()
    recommendation: str = (scorecard.get("recommendation") or "").upper()

    evidence = {"tier": tier, "recommendation": recommendation}

    proceed_without_caution = "PROCEED" in recommendation and "CAUTION" not in recommendation
    if proceed_without_caution and tier == "HIGH":
        return _check(
            "Scorecard vs Risk Tier",
            "cross_agent",
            "WARN",
            (
                f"Recommendation is '{scorecard.get('recommendation')}' but risk tier is HIGH — "
                "review IC recommendation."
            ),
            evidence,
        )

    if "PASS" in recommendation and tier == "LOW":
        return _check(
            "Scorecard vs Risk Tier",
            "cross_agent",
            "WARN",
            (
                f"Recommendation is '{scorecard.get('recommendation')}' but risk tier is LOW — "
                "passing on a low-risk fund may be overly conservative."
            ),
            evidence,
        )

    return _check(
        "Scorecard vs Risk Tier",
        "cross_agent",
        "PASS",
        f"Recommendation '{scorecard.get('recommendation')}' is consistent with tier '{tier}'.",
        evidence,
    )


def _check_holdings_count(analysis: dict, raw_data: dict) -> dict:
    """
    Compare holdings count between raw 13F XML data and LLM analysis output.

    Fails if both values are present and do not match exactly.
    Passes if either value is None.
    """
    raw_count = (
        (raw_data.get("adv_xml_data") or {})
        .get("thirteenf", {})
        .get("holdings_count")
    )
    analysis_count = (analysis.get("13f_filings") or {}).get("holdings_count")

    evidence = {"raw": raw_count, "analysis": analysis_count}

    if raw_count is None or analysis_count is None:
        return _check(
            "Holdings Count",
            "cross_agent",
            "PASS",
            (
                f"One or both holdings count values are null — "
                f"raw='{raw_count}', analysis='{analysis_count}'. Skipping comparison."
            ),
            evidence,
        )

    if int(raw_count) == int(analysis_count):
        return _check(
            "Holdings Count",
            "cross_agent",
            "PASS",
            f"Holdings count confirmed: {raw_count}.",
            evidence,
        )

    return _check(
        "Holdings Count",
        "cross_agent",
        "FAIL",
        f"Holdings count mismatch: raw={raw_count}, analysis={analysis_count}.",
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
        # Layer: raw_to_analysis (5 checks)
        _check_firm_name(analysis, raw_data),
        _check_crd(analysis, raw_data),
        _check_registration_status(analysis, raw_data),
        _check_portfolio_value(analysis, raw_data),
        _check_fund_count(analysis, raw_data),
        # Layer: analysis_to_memo (4 checks)
        _check_risk_tier_in_memo(risk_report, memo_text),
        _check_high_flags_in_memo(risk_report, memo_text),
        _check_portfolio_value_in_memo(analysis, memo_text),
        _check_registration_in_memo(analysis, memo_text),
        # Layer: cross_agent (3 checks)
        _check_risk_tier_vs_flags(risk_report),
        _check_scorecard_vs_risk(risk_report, scorecard),
        _check_holdings_count(analysis, raw_data),
    ]
