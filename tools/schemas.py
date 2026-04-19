"""
Agent I/O schemas — TypedDict definitions, coercion, and validation.

This is the single source of truth for what data flows between agents.
Every agent function signature is annotated with these types.

Design:
  TypedDicts   — static contracts; IDEs and type checkers use these
  coerce_*     — normalise raw LLM dicts so callers can safely access
                 any defined field without KeyError or type errors
  validate_*   — check LLM output before accepting it; agents call
                 these after parsing and retry once on failure
"""

from __future__ import annotations
from typing import Any, List, Literal, Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore


# ── Shared literal types ──────────────────────────────────────────────────────

Severity       = Literal["HIGH", "MEDIUM", "LOW"]
ExtSeverity    = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAN"]
RiskTier       = Literal["HIGH", "MEDIUM", "LOW"]
NewsRiskLevel  = Literal["HIGH", "MEDIUM", "LOW", "CLEAN", "UNKNOWN"]
FirmType       = Literal[
    "PE", "Hedge Fund", "VC", "Credit", "Multi-Strategy", "Long-Only", "Unknown"
]
FlagCategory   = Literal[
    "Regulatory", "Key Person", "Fund Structure", "Disclosure",
    "Operational", "News", "Data Gap", "Concentration",
]
NewsCategory   = Literal[
    "Regulatory", "Fundraising", "Personnel", "Litigation",
    "Performance", "ESG", "General",
]


# ════════════════════════════════════════════════════════════════════════════════
# fund_analysis output
# ════════════════════════════════════════════════════════════════════════════════

class PersonnelItem(TypedDict, total=False):
    name: str                      # always present
    crd: Optional[str]
    titles: List[str]
    ownership_pct: Optional[str]


class FirmOverview(TypedDict, total=False):
    name: Optional[str]
    crd: Optional[str]
    sec_number: Optional[str]
    registration_status: Optional[str]
    registration_date: Optional[str]
    headquarters: Optional[str]
    website: Optional[str]
    aum_regulatory: Optional[str]
    aum_note: Optional[str]
    firm_type: Optional[FirmType]
    firm_type_rationale: Optional[str]
    num_clients: Optional[int]
    num_employees: Optional[int]
    num_investment_advisers: Optional[int]


class FeeStructure(TypedDict, total=False):
    fee_types: List[str]
    min_account_size: Optional[str]
    notes: Optional[str]


class RegulatoryDisclosures(TypedDict, total=False):
    has_disclosures: Optional[bool]
    disclosure_count: Optional[int]
    disclosure_types: List[str]
    severity_assessment: Optional[ExtSeverity]
    assessment: Optional[str]


class ThirteenFFilings(TypedDict, total=False):
    available: bool                # always present
    most_recent: Optional[str]
    count_found: int
    portfolio_value: Optional[str]
    holdings_count: Optional[int]
    period_of_report: Optional[str]
    strategy_signal: Optional[str]
    note: Optional[str]


class MacroContextSnapshot(TypedDict, total=False):
    fed_funds_rate: Optional[str]
    hy_spread: Optional[str]
    ten_yr_yield: Optional[str]
    notes: Optional[str]


class AnalysisFundItem(TypedDict, total=False):
    name: str
    entity_type: Optional[str]
    offering_amount: Optional[str]
    date_of_first_sale: Optional[str]
    jurisdiction: Optional[str]
    exemptions: List[str]
    is_private_fund: bool
    exemption_interpretation: Optional[str]
    edgar_url: Optional[str]
    news_headlines: List[str]


class FundsAnalysis(TypedDict, total=False):
    total_funds_found: Optional[int]
    sources_used: List[str]
    funds: List[AnalysisFundItem]
    vintage_summary: Optional[str]
    fundraising_pattern: Optional[str]
    notes: Optional[str]


class AnalysisOutput(TypedDict, total=False):
    """Output of agents/fund_analysis.py — input to risk_flagging and memo."""
    firm_overview: FirmOverview
    fee_structure: FeeStructure
    key_personnel: List[PersonnelItem]
    regulatory_disclosures: RegulatoryDisclosures
    thirteenf_filings: ThirteenFFilings   # canonical key (13f_filings also accepted)
    macro_context_snapshot: MacroContextSnapshot
    funds_analysis: FundsAnalysis
    data_quality_flags: List[str]
    analyst_notes: Optional[str]


# ════════════════════════════════════════════════════════════════════════════════
# risk_flagging output
# ════════════════════════════════════════════════════════════════════════════════

class RiskFlag(TypedDict, total=False):
    category: FlagCategory
    severity: Severity
    finding: str                   # always present
    evidence: str
    context: Optional[str]
    lp_action: str


class RiskReport(TypedDict, total=False):
    """Output of agents/risk_flagging.py — input to memo."""
    overall_risk_tier: RiskTier
    overall_commentary: str        # always present
    flags: List[RiskFlag]
    clean_items: List[str]
    critical_data_gaps: List[str]


# ════════════════════════════════════════════════════════════════════════════════
# news_research output
# ════════════════════════════════════════════════════════════════════════════════

class NewsFlag(TypedDict, total=False):
    category: NewsCategory
    severity: Literal["HIGH", "MEDIUM", "LOW", "INFO"]
    finding: str
    source_url: Optional[str]
    date: Optional[str]
    lp_action: Optional[str]


class NewsSource(TypedDict, total=False):
    title: str
    url: str
    published_date: Optional[str]


class NewsFinding(TypedDict, total=False):
    fact: str
    source_url: Optional[str]
    published_date: Optional[str]
    query: Optional[str]
    category: Optional[NewsCategory]


class NewsReport(TypedDict, total=False):
    """Output of agents/news_research.py — input to risk_flagging and memo."""
    firm_name: str
    research_rounds: int
    total_sources: int
    news_flags: List[NewsFlag]
    news_summary: Optional[str]
    overall_news_risk: NewsRiskLevel
    findings: List[NewsFinding]
    sources_consulted: List[NewsSource]
    queries_used: List[str]
    coverage_gaps: List[str]
    errors: List[str]


# ════════════════════════════════════════════════════════════════════════════════
# enforcement output
# ════════════════════════════════════════════════════════════════════════════════

class EnforcementAction(TypedDict, total=False):
    action_type: Literal["Regulatory", "Criminal", "Civil", "Arbitration"]
    initiated_by: str
    date: Optional[str]
    description: Optional[str]
    sanctions: List[str]
    resolution: Optional[str]
    severity: Severity
    source: Optional[str]


class EnforcementData(TypedDict, total=False):
    actions: List[EnforcementAction]
    total_actions: int
    high_count: int
    open_actions: List[EnforcementAction]
    penalty_total_fmt: Optional[str]


class EnforcementReport(TypedDict, total=False):
    """Output of agents/enforcement.py — merged into raw_data["enforcement"]."""
    enforcement_data: EnforcementData
    summary: Optional[str]
    severity: ExtSeverity
    key_findings: List[str]
    red_flags: List[str]
    sources: List[str]
    errors: List[str]


# ════════════════════════════════════════════════════════════════════════════════
# fund_discovery output
# ════════════════════════════════════════════════════════════════════════════════

class DiscoveredFundNews(TypedDict, total=False):
    title: Optional[str]
    url: Optional[str]
    date: Optional[str]
    snippet: Optional[str]


class DiscoveredFund(TypedDict, total=False):
    name: str
    offering_amount: Optional[str]
    date_of_first_sale: Optional[str]
    entity_type: Optional[str]
    exemptions: List[str]
    is_private_fund: bool
    jurisdiction: Optional[str]
    edgar_url: Optional[str]
    news: List[DiscoveredFundNews]
    source: Optional[str]


class FundDiscoveryReport(TypedDict, total=False):
    """Output of agents/fund_discovery.py — merged into raw_data["fund_discovery"]."""
    funds: List[DiscoveredFund]
    relying_advisors: List[Any]
    total_found: int
    sources_used: List[str]
    errors: List[str]


# ════════════════════════════════════════════════════════════════════════════════
# data_ingestion output  (raw_data)
# ════════════════════════════════════════════════════════════════════════════════

class RawData(TypedDict, total=False):
    """Output of agents/data_ingestion.py — the top-level pipeline payload."""
    input: str
    search_results: List[Any]
    crd: Optional[str]
    adv_summary: dict
    adv_xml_data: dict
    filings_13f: List[Any]
    market_context: dict
    fund_discovery: FundDiscoveryReport
    enforcement: EnforcementReport
    reconciliation: List[dict]
    errors: List[str]


# ════════════════════════════════════════════════════════════════════════════════
# Coercion — fill defaults so callers can access any key without KeyError
# ════════════════════════════════════════════════════════════════════════════════

def coerce_analysis(data: Any) -> AnalysisOutput:
    """
    Normalise raw fund_analysis LLM output into AnalysisOutput.

    - Renames "13f_filings" key to "thirteenf_filings" (LLM uses the former
      because JSON keys starting with digits are ambiguous in Python)
    - Fills every missing top-level key with a safe empty default
    - Coerces list fields that arrived as None to []
    """
    if not isinstance(data, dict):
        data = {}

    # The LLM returns "13f_filings"; normalise to our canonical key
    if "13f_filings" in data and "thirteenf_filings" not in data:
        data["thirteenf_filings"] = data.pop("13f_filings")

    def _ensure_dict(val: Any) -> dict:
        return val if isinstance(val, dict) else {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("firm_overview",           _ensure_dict(data.get("firm_overview")))
    data.setdefault("fee_structure",           _ensure_dict(data.get("fee_structure")))
    data.setdefault("key_personnel",           _ensure_list(data.get("key_personnel")))
    data.setdefault("regulatory_disclosures",  _ensure_dict(data.get("regulatory_disclosures")))
    data.setdefault("thirteenf_filings",       _ensure_dict(data.get("thirteenf_filings")))
    data.setdefault("macro_context_snapshot",  _ensure_dict(data.get("macro_context_snapshot")))
    data.setdefault("funds_analysis",          _ensure_dict(data.get("funds_analysis")))
    data.setdefault("data_quality_flags",      _ensure_list(data.get("data_quality_flags")))
    data.setdefault("analyst_notes",           None)

    # Coerce nested list defaults
    fo: dict = data["firm_overview"]
    fo.setdefault("firm_type", "Unknown")

    rd: dict = data["regulatory_disclosures"]
    if not isinstance(rd.get("disclosure_types"), list):
        rd["disclosure_types"] = []

    tf: dict = data["thirteenf_filings"]
    if not isinstance(tf.get("available"), bool):
        tf["available"] = False
    tf.setdefault("count_found", 0)

    fa: dict = data["funds_analysis"]
    if not isinstance(fa.get("funds"), list):
        fa["funds"] = []
    if not isinstance(fa.get("sources_used"), list):
        fa["sources_used"] = []
    fa.setdefault("total_funds_found", 0)

    fs: dict = data["fee_structure"]
    if not isinstance(fs.get("fee_types"), list):
        fs["fee_types"] = []

    return data  # type: ignore[return-value]


def coerce_risk_report(data: Any) -> RiskReport:
    """Normalise raw risk_flagging LLM output into RiskReport."""
    if not isinstance(data, dict):
        data = {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("overall_risk_tier",   "LOW")
    data.setdefault("overall_commentary",  "")
    data.setdefault("flags",               _ensure_list(data.get("flags")))
    data.setdefault("clean_items",         _ensure_list(data.get("clean_items")))
    data.setdefault("critical_data_gaps",  _ensure_list(data.get("critical_data_gaps")))

    for flag in data["flags"]:
        if isinstance(flag, dict):
            flag.setdefault("category", "Data Gap")
            flag.setdefault("severity", "LOW")
            flag.setdefault("finding",  "")
            flag.setdefault("evidence", "")
            flag.setdefault("context",  None)
            flag.setdefault("lp_action", "")

    return data  # type: ignore[return-value]


def coerce_news_report(data: Any, firm_name: str = "") -> NewsReport:
    """Normalise raw news_research LLM output into NewsReport."""
    if not isinstance(data, dict):
        data = {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("firm_name",         firm_name)
    data.setdefault("research_rounds",   0)
    data.setdefault("total_sources",     0)
    data.setdefault("news_flags",        _ensure_list(data.get("news_flags")))
    data.setdefault("news_summary",      None)
    data.setdefault("overall_news_risk", "UNKNOWN")
    data.setdefault("findings",          _ensure_list(data.get("findings")))
    data.setdefault("sources_consulted", _ensure_list(data.get("sources_consulted")))
    data.setdefault("queries_used",      _ensure_list(data.get("queries_used")))
    data.setdefault("coverage_gaps",     _ensure_list(data.get("coverage_gaps")))
    data.setdefault("errors",            _ensure_list(data.get("errors")))
    return data  # type: ignore[return-value]


def coerce_enforcement_report(data: Any) -> EnforcementReport:
    """Normalise raw enforcement LLM output into EnforcementReport."""
    if not isinstance(data, dict):
        data = {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("enforcement_data", {})
    data.setdefault("summary",          None)
    data.setdefault("severity",         "CLEAN")
    data.setdefault("key_findings",     _ensure_list(data.get("key_findings")))
    data.setdefault("red_flags",        _ensure_list(data.get("red_flags")))
    data.setdefault("sources",          _ensure_list(data.get("sources")))
    data.setdefault("errors",           _ensure_list(data.get("errors")))

    ed: dict = data["enforcement_data"]
    if not isinstance(ed.get("actions"), list):
        ed["actions"] = []
    ed.setdefault("total_actions",    0)
    ed.setdefault("high_count",       0)
    ed.setdefault("open_actions",     [])
    ed.setdefault("penalty_total_fmt", "—")

    return data  # type: ignore[return-value]


def coerce_fund_discovery_report(data: Any) -> FundDiscoveryReport:
    """Normalise raw fund_discovery output into FundDiscoveryReport."""
    if not isinstance(data, dict):
        data = {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("funds",            _ensure_list(data.get("funds")))
    data.setdefault("relying_advisors", _ensure_list(data.get("relying_advisors")))
    data.setdefault("total_found",      len(data.get("funds") or []))
    data.setdefault("sources_used",     _ensure_list(data.get("sources_used")))
    data.setdefault("errors",           _ensure_list(data.get("errors")))

    for fund in data["funds"]:
        if isinstance(fund, dict):
            fund.setdefault("exemptions", [])
            fund.setdefault("is_private_fund", False)
            fund.setdefault("news", [])

    return data  # type: ignore[return-value]


# ════════════════════════════════════════════════════════════════════════════════
# Validation — called by agents after parsing LLM output; retry on failure
# ════════════════════════════════════════════════════════════════════════════════

_VALID_SEVERITIES  = {"HIGH", "MEDIUM", "LOW"}
_VALID_EXT_SEV     = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAN"}
_VALID_RISK_TIERS  = {"HIGH", "MEDIUM", "LOW"}
_VALID_FIRM_TYPES  = {"PE", "Hedge Fund", "VC", "Credit", "Multi-Strategy", "Long-Only", "Unknown"}
_VALID_FLAG_CATS   = {
    "Regulatory", "Key Person", "Fund Structure", "Disclosure",
    "Operational", "News", "Data Gap", "Concentration",
}
_REQUIRED_FLAG_KEYS = {"category", "severity", "finding", "evidence", "lp_action"}


def validate_analysis(data: Any) -> list[str]:
    """
    Validate fund_analysis agent output.
    Returns a list of error strings; empty = valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    # Top-level required keys
    for key in ("firm_overview", "fee_structure", "key_personnel",
                "regulatory_disclosures", "funds_analysis", "data_quality_flags"):
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    # Accept either key variant for 13F
    has_13f = ("thirteenf_filings" in data) or ("13f_filings" in data)
    if not has_13f:
        errors.append("Missing required key: 'thirteenf_filings' (or '13f_filings')")

    # firm_overview
    fo = data.get("firm_overview")
    if not isinstance(fo, dict):
        errors.append("firm_overview must be a dict")
    else:
        for field in ("name", "crd", "registration_status"):
            if field not in fo:
                errors.append(f"firm_overview missing field: '{field}'")
        ft = fo.get("firm_type")
        if ft is not None and ft not in _VALID_FIRM_TYPES:
            errors.append(
                f"firm_overview.firm_type must be one of {sorted(_VALID_FIRM_TYPES)}, got: '{ft}'"
            )

    # fee_structure
    fs = data.get("fee_structure")
    if fs is not None and not isinstance(fs, dict):
        errors.append("fee_structure must be a dict")
    elif isinstance(fs, dict) and not isinstance(fs.get("fee_types", []), list):
        errors.append("fee_structure.fee_types must be a list")

    # key_personnel
    kp = data.get("key_personnel")
    if kp is not None and not isinstance(kp, list):
        errors.append("key_personnel must be a list")
    elif isinstance(kp, list):
        for i, p in enumerate(kp):
            if not isinstance(p, dict):
                errors.append(f"key_personnel[{i}] must be a dict")
            elif "name" not in p:
                errors.append(f"key_personnel[{i}] missing 'name'")

    # regulatory_disclosures
    rd = data.get("regulatory_disclosures")
    if rd is not None and not isinstance(rd, dict):
        errors.append("regulatory_disclosures must be a dict")
    elif isinstance(rd, dict):
        sev = rd.get("severity_assessment")
        if sev is not None and sev not in _VALID_EXT_SEV:
            errors.append(
                f"regulatory_disclosures.severity_assessment must be one of "
                f"{sorted(_VALID_EXT_SEV)}, got: '{sev}'"
            )

    # 13f_filings
    tf = data.get("thirteenf_filings") or data.get("13f_filings")
    if isinstance(tf, dict) and "available" not in tf:
        errors.append("thirteenf_filings missing field: 'available'")

    # funds_analysis
    fa = data.get("funds_analysis")
    if fa is not None and not isinstance(fa, dict):
        errors.append("funds_analysis must be a dict")
    elif isinstance(fa, dict) and not isinstance(fa.get("funds", []), list):
        errors.append("funds_analysis.funds must be a list")

    # data_quality_flags
    dqf = data.get("data_quality_flags")
    if dqf is not None and not isinstance(dqf, list):
        errors.append("data_quality_flags must be a list")

    return errors


def validate_risk_report(data: Any) -> list[str]:
    """
    Validate risk_flagging agent output.
    Returns a list of error strings; empty = valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    for key in ("overall_risk_tier", "flags", "clean_items",
                "critical_data_gaps", "overall_commentary"):
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    tier = data.get("overall_risk_tier")
    if tier is not None and tier not in _VALID_RISK_TIERS:
        errors.append(
            f"overall_risk_tier must be one of {sorted(_VALID_RISK_TIERS)}, got: '{tier}'"
        )

    flags = data.get("flags")
    if flags is not None:
        if not isinstance(flags, list):
            errors.append("flags must be a list")
        else:
            for i, flag in enumerate(flags):
                if not isinstance(flag, dict):
                    errors.append(f"flags[{i}] must be a dict")
                    continue
                for fkey in _REQUIRED_FLAG_KEYS:
                    if fkey not in flag:
                        errors.append(f"flags[{i}] missing key: '{fkey}'")
                sev = flag.get("severity")
                if sev is not None and sev not in _VALID_SEVERITIES:
                    errors.append(
                        f"flags[{i}].severity must be one of "
                        f"{sorted(_VALID_SEVERITIES)}, got: '{sev}'"
                    )
                cat = flag.get("category")
                if cat is not None and cat not in _VALID_FLAG_CATS:
                    errors.append(
                        f"flags[{i}].category must be one of "
                        f"{sorted(_VALID_FLAG_CATS)}, got: '{cat}'"
                    )

    commentary = data.get("overall_commentary")
    if commentary is not None and not isinstance(commentary, str):
        errors.append("overall_commentary must be a string")
    elif isinstance(commentary, str) and len(commentary.strip()) < 10:
        errors.append("overall_commentary is too short (min 10 chars)")

    for key in ("clean_items", "critical_data_gaps"):
        val = data.get(key)
        if val is not None and not isinstance(val, list):
            errors.append(f"{key} must be a list")

    return errors


def format_validation_errors(errors: list[str]) -> str:
    """Format error list into a retry prompt suffix."""
    lines = ["", "SCHEMA VALIDATION FAILED — fix these issues before responding:"]
    for e in errors:
        lines.append(f"  • {e}")
    lines.append("")
    lines.append("Return the corrected JSON now, fixing every issue listed above.")
    return "\n".join(lines)
