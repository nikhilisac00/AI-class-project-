"""
Agent output schemas and validation.

Every agent boundary is typed here. validate_* functions return a list of
error strings — empty list means the output is valid. Agents call these after
parsing the LLM response and retry once with the error list appended if invalid.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Fund Analysis Models ─────────────────────────────────────────────────────

class FirmOverview(BaseModel):
    """Firm overview from fund analysis agent."""

    model_config = {"extra": "allow"}

    name: str | None = None
    crd: str | None = None
    sec_number: str | None = None
    registration_status: str | None = None
    registration_date: str | None = None
    headquarters: str | None = None
    website: str | None = None
    aum_regulatory: str | None = None
    aum_note: str | None = None
    firm_type: str | None = None
    firm_type_rationale: str | None = None
    num_clients: int | None = None
    num_employees: int | None = None
    num_investment_advisers: int | None = None


class FeeStructure(BaseModel):
    """Fee structure from fund analysis agent."""

    model_config = {"extra": "allow"}

    fee_types: list[str] = Field(default_factory=list)
    min_account_size: str | None = None
    notes: str | None = None


class KeyPerson(BaseModel):
    """A key person entry from fund analysis agent."""

    model_config = {"extra": "allow"}

    name: str | None = None
    crd: str | None = None
    titles: list[str] = Field(default_factory=list)
    ownership_pct: str | None = None


class RegulatoryDisclosures(BaseModel):
    """Regulatory disclosure summary from fund analysis agent."""

    model_config = {"extra": "allow"}

    has_disclosures: bool | None = None
    disclosure_count: int | None = None
    disclosure_types: list[str] = Field(default_factory=list)
    severity_assessment: str | None = None
    assessment: str | None = None


class ThirteenFFilings(BaseModel):
    """13F filing data from fund analysis agent."""

    model_config = {"extra": "allow"}

    available: bool = False
    most_recent: str | None = None
    count_found: int | None = None
    portfolio_value: str | None = None
    holdings_count: int | None = None
    period_of_report: str | None = None
    strategy_signal: str | None = None
    note: str | None = None


class MacroContextSnapshot(BaseModel):
    """Macro context from fund analysis agent."""

    model_config = {"extra": "allow"}

    fed_funds_rate: str | None = None
    hy_spread: str | None = None
    ten_yr_yield: str | None = None
    notes: str | None = None


class FundsAnalysis(BaseModel):
    """Fund discovery analysis from fund analysis agent."""

    model_config = {"extra": "allow"}

    total_funds_found: int | None = None
    sources_used: list[str] = Field(default_factory=list)
    funds: list[dict] = Field(default_factory=list)
    vintage_summary: str | None = None
    fundraising_pattern: str | None = None
    notes: str | None = None


class FundAnalysisOutput(BaseModel):
    """Complete output from the fund analysis agent."""

    model_config = {"extra": "allow", "populate_by_name": True}

    firm_overview: FirmOverview = Field(default_factory=FirmOverview)
    fee_structure: FeeStructure | dict = Field(default_factory=dict)
    key_personnel: list[KeyPerson | dict] = Field(default_factory=list)
    regulatory_disclosures: RegulatoryDisclosures | dict = Field(default_factory=dict)
    thirteenf_filings: ThirteenFFilings | dict = Field(default_factory=dict, alias="13f_filings")
    macro_context_snapshot: MacroContextSnapshot | dict = Field(default_factory=dict)
    funds_analysis: FundsAnalysis | dict = Field(default_factory=dict)
    data_quality_flags: list[str] = Field(default_factory=list)
    analyst_notes: str | None = None


# ── Risk Flagging Models ─────────────────────────────────────────────────────

class RiskFlag(BaseModel):
    """A single risk flag from the risk flagging agent."""

    model_config = {"extra": "allow"}

    category: str
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    finding: str
    evidence: str
    context: str | None = None
    lp_action: str


class RiskReportOutput(BaseModel):
    """Complete output from the risk flagging agent."""

    model_config = {"extra": "allow"}

    overall_risk_tier: Literal["HIGH", "MEDIUM", "LOW"]
    overall_commentary: str = Field(min_length=10)
    flags: list[RiskFlag]
    clean_items: list[str] = Field(default_factory=list)
    critical_data_gaps: list[str] = Field(default_factory=list)


# ── Validators ───────────────────────────────────────────────────────────────

def validate_analysis(data: Any) -> list[str]:
    """Validate fund_analysis agent output. Returns list of error strings."""
    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]
    try:
        FundAnalysisOutput.model_validate(data)
        return []
    except Exception as exc:
        return [str(e["msg"]) for e in exc.errors()] if hasattr(exc, "errors") else [str(exc)]


def validate_risk_report(data: Any) -> list[str]:
    """Validate risk_flagging agent output. Returns list of error strings."""
    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]
    try:
        RiskReportOutput.model_validate(data)
        return []
    except Exception as exc:
        return [str(e["msg"]) for e in exc.errors()] if hasattr(exc, "errors") else [str(exc)]


def format_validation_errors(errors: list[str]) -> str:
    """Format errors into a retry prompt suffix."""
    lines = ["", "SCHEMA VALIDATION FAILED — fix these issues before responding:"]
    for e in errors:
        lines.append(f"  • {e}")
    lines.append("")
    lines.append("Return the corrected JSON now, fixing every issue listed above.")
    return "\n".join(lines)
