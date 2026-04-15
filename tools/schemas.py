"""
Agent output schemas and validation.

Every agent boundary is typed here. validate_* functions return a list of
error strings — empty list means the output is valid. Agents call these after
parsing the LLM response and retry once with the error list appended if invalid.
"""

from __future__ import annotations
from typing import Any


# ── Required top-level keys ──────────────────────────────────────────────────

ANALYSIS_REQUIRED_KEYS = {
    "firm_overview",
    "fee_structure",
    "key_personnel",
    "regulatory_disclosures",
    "13f_filings",
    "macro_context_snapshot",
    "funds_analysis",
    "data_quality_flags",
}

RISK_REQUIRED_KEYS = {
    "overall_risk_tier",
    "flags",
    "clean_items",
    "critical_data_gaps",
    "overall_commentary",
}

VALID_SEVERITIES  = {"HIGH", "MEDIUM", "LOW"}
VALID_RISK_TIERS  = {"HIGH", "MEDIUM", "LOW"}
VALID_FLAG_CATEGORIES = {
    "Regulatory", "Concentration", "Key Person", "Fee/Structure",
    "Disclosure", "Data Gap", "Operational", "Fund Structure",
}
REQUIRED_FLAG_KEYS = {"category", "severity", "finding", "evidence", "lp_action"}


# ── Validators ───────────────────────────────────────────────────────────────

def validate_analysis(data: Any) -> list[str]:
    """Validate fund_analysis agent output. Returns list of error strings."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    for key in ANALYSIS_REQUIRED_KEYS:
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    # firm_overview checks
    ov = data.get("firm_overview", {})
    if not isinstance(ov, dict):
        errors.append("firm_overview must be a dict")
    else:
        for field in ("name", "crd", "registration_status"):
            if field not in ov:
                errors.append(f"firm_overview missing field: '{field}'")

    # key_personnel must be a list
    kp = data.get("key_personnel")
    if kp is not None and not isinstance(kp, list):
        errors.append("key_personnel must be a list")

    # 13f_filings checks
    tf = data.get("13f_filings", {})
    if isinstance(tf, dict):
        if "available" not in tf:
            errors.append("13f_filings missing field: 'available'")

    # data_quality_flags must be a list
    dqf = data.get("data_quality_flags")
    if dqf is not None and not isinstance(dqf, list):
        errors.append("data_quality_flags must be a list")

    return errors


def validate_risk_report(data: Any) -> list[str]:
    """Validate risk_flagging agent output. Returns list of error strings."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    for key in RISK_REQUIRED_KEYS:
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    # overall_risk_tier
    tier = data.get("overall_risk_tier")
    if tier is not None and tier not in VALID_RISK_TIERS:
        errors.append(
            f"overall_risk_tier must be one of {VALID_RISK_TIERS}, got: '{tier}'"
        )

    # flags
    flags = data.get("flags")
    if flags is not None:
        if not isinstance(flags, list):
            errors.append("flags must be a list")
        else:
            for i, flag in enumerate(flags):
                if not isinstance(flag, dict):
                    errors.append(f"flags[{i}] must be a dict")
                    continue
                for fkey in REQUIRED_FLAG_KEYS:
                    if fkey not in flag:
                        errors.append(f"flags[{i}] missing key: '{fkey}'")
                sev = flag.get("severity")
                if sev is not None and sev not in VALID_SEVERITIES:
                    errors.append(
                        f"flags[{i}].severity must be one of {VALID_SEVERITIES}, got: '{sev}'"
                    )

    # overall_commentary must be a non-empty string
    commentary = data.get("overall_commentary")
    if commentary is not None and not isinstance(commentary, str):
        errors.append("overall_commentary must be a string")
    elif isinstance(commentary, str) and len(commentary.strip()) < 10:
        errors.append("overall_commentary is too short (min 10 chars)")

    return errors


def format_validation_errors(errors: list[str]) -> str:
    """Format errors into a retry prompt suffix."""
    lines = ["", "SCHEMA VALIDATION FAILED — fix these issues before responding:"]
    for e in errors:
        lines.append(f"  • {e}")
    lines.append("")
    lines.append("Return the corrected JSON now, fixing every issue listed above.")
    return "\n".join(lines)
