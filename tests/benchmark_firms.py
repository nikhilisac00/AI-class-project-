"""
Benchmark Firms — Memo Validation Harness
==========================================
Defines 5 benchmark firms with expected facts for validating memo accuracy.
Use score_memo() to check a generated memo against expected assertions.

This is the scaffold only — does not run the pipeline or make API calls.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class BenchmarkFirm:
    """A benchmark firm with expected facts for memo validation."""
    name: str
    crd: str
    category: str
    description: str
    expected_facts: dict = field(default_factory=dict)


# ── Benchmark Firms ──────────────────────────────────────────────────────────

BENCHMARK_FIRMS: list[BenchmarkFirm] = [
    BenchmarkFirm(
        name="GPB Capital Holdings",
        crd="148760",
        category="sec_enforcement",
        description="Firm with known SEC enforcement action and disclosure history.",
        expected_facts={
            "has_sec_disclosure": True,
            "risk_tier_in": ["HIGH", "MEDIUM"],
            "memo_must_contain": ["disclosure", "enforcement", "regulatory"],
            "memo_must_not_contain": ["clean regulatory record"],
        },
    ),
    BenchmarkFirm(
        name="ARK Investment Management",
        crd="160418",
        category="large_13f_change",
        description="Firm with significant quarter-over-quarter 13F holding changes.",
        expected_facts={
            "has_13f": True,
            "aum_range_usd": (1e9, 100e9),
            "memo_must_contain": ["13F", "portfolio value", "holdings"],
            "memo_must_not_contain": [],
        },
    ),
    BenchmarkFirm(
        name="Man Investments",
        crd="106017",
        category="offshore_domiciled",
        description="UK-based manager with offshore fund structures.",
        expected_facts={
            "is_foreign_private_adviser": True,
            "memo_must_contain": ["offshore", "jurisdiction"],
            "memo_must_not_contain": [],
            "registration_status_not": "Active",
        },
    ),
    BenchmarkFirm(
        name="Blackstone Alternative Asset Management",
        crd="149051",
        category="recent_form_d",
        description="Large alternative manager with active Form D filing history.",
        expected_facts={
            "has_form_d_funds": True,
            "min_fund_count": 1,
            "aum_range_usd": (10e9, 1e12),
            "memo_must_contain": ["fund", "Form D"],
            "memo_must_not_contain": [],
        },
    ),
    BenchmarkFirm(
        name="AQR Capital Management",
        crd="149729",
        category="clean_control",
        description="Clean baseline control firm — well-known, well-documented.",
        expected_facts={
            "has_sec_disclosure": False,
            "risk_tier_in": ["LOW", "MEDIUM"],
            "has_13f": True,
            "memo_must_contain": ["Active", "SEC-registered"],
            "memo_must_not_contain": ["criminal", "fraud", "bar"],
        },
    ),
]


# ── Scoring Function ─────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result of a single assertion check."""
    assertion: str
    passed: bool
    detail: str


@dataclass
class MemoScoreReport:
    """Full scoring report for a memo against expected facts."""
    firm_name: str
    total_checks: int
    passed: int
    failed: int
    results: list[CheckResult] = field(default_factory=list)

    @property
    def score_pct(self) -> float:
        """Pass rate as a percentage."""
        return (self.passed / self.total_checks * 100) if self.total_checks else 0.0


def score_memo(
    memo_text: str,
    expected_facts: dict,
    firm_name: str = "",
    analysis: dict | None = None,
    risk_report: dict | None = None,
    raw_data: dict | None = None,
) -> MemoScoreReport:
    """Score a generated memo against expected facts.

    Args:
        memo_text: The generated memo markdown text.
        expected_facts: Dict of assertions (from BenchmarkFirm.expected_facts).
        firm_name: Firm name for the report.
        analysis: Optional analysis dict for structured checks.
        risk_report: Optional risk report dict for structured checks.
        raw_data: Optional raw data dict for structured checks.

    Returns:
        MemoScoreReport with pass/fail for each assertion.
    """
    results: list[CheckResult] = []
    memo_lower = memo_text.lower()

    # Check: memo_must_contain
    for term in expected_facts.get("memo_must_contain", []):
        found = term.lower() in memo_lower
        results.append(CheckResult(
            assertion=f"memo_must_contain: '{term}'",
            passed=found,
            detail=f"Term '{term}' {'found' if found else 'NOT found'} in memo",
        ))

    # Check: memo_must_not_contain
    for term in expected_facts.get("memo_must_not_contain", []):
        absent = term.lower() not in memo_lower
        results.append(CheckResult(
            assertion=f"memo_must_not_contain: '{term}'",
            passed=absent,
            detail=f"Term '{term}' {'absent (good)' if absent else 'FOUND (bad)'} in memo",
        ))

    # Check: risk_tier_in
    if "risk_tier_in" in expected_facts and risk_report:
        tier = (risk_report.get("overall_risk_tier") or "").upper()
        allowed = expected_facts["risk_tier_in"]
        match = tier in allowed
        results.append(CheckResult(
            assertion=f"risk_tier_in: {allowed}",
            passed=match,
            detail=f"Risk tier '{tier}' {'is' if match else 'is NOT'} in {allowed}",
        ))

    # Check: has_sec_disclosure
    if "has_sec_disclosure" in expected_facts and risk_report:
        flags = risk_report.get("flags", [])
        has_disc = any(
            f.get("category") in ("Regulatory", "Disclosure")
            for f in flags
        )
        expected = expected_facts["has_sec_disclosure"]
        match = has_disc == expected
        results.append(CheckResult(
            assertion=f"has_sec_disclosure: {expected}",
            passed=match,
            detail=f"SEC disclosure {'found' if has_disc else 'not found'}, expected={expected}",
        ))

    # Check: has_13f
    if "has_13f" in expected_facts and analysis:
        has_13f = bool((analysis.get("13f_filings") or {}).get("available"))
        expected = expected_facts["has_13f"]
        match = has_13f == expected
        results.append(CheckResult(
            assertion=f"has_13f: {expected}",
            passed=match,
            detail=f"13F available={has_13f}, expected={expected}",
        ))

    # Check: aum_range_usd
    if "aum_range_usd" in expected_facts and analysis:
        pv_str = (analysis.get("13f_filings") or {}).get("portfolio_value")
        pv = _parse_aum(pv_str)
        lo, hi = expected_facts["aum_range_usd"]
        if pv is not None:
            in_range = lo <= pv <= hi
            results.append(CheckResult(
                assertion=f"aum_range_usd: ({lo:.0e}, {hi:.0e})",
                passed=in_range,
                detail=f"Portfolio value {pv:.2e} {'in' if in_range else 'NOT in'} range",
            ))
        else:
            results.append(CheckResult(
                assertion=f"aum_range_usd: ({lo:.0e}, {hi:.0e})",
                passed=False,
                detail=f"Portfolio value not parseable from '{pv_str}'",
            ))

    # Check: has_form_d_funds
    if "has_form_d_funds" in expected_facts and raw_data:
        funds = (raw_data.get("fund_discovery") or {}).get("funds", [])
        has_funds = len(funds) > 0
        expected = expected_facts["has_form_d_funds"]
        match = has_funds == expected
        results.append(CheckResult(
            assertion=f"has_form_d_funds: {expected}",
            passed=match,
            detail=f"Fund count={len(funds)}, expected has_funds={expected}",
        ))

    # Check: min_fund_count
    if "min_fund_count" in expected_facts and raw_data:
        funds = (raw_data.get("fund_discovery") or {}).get("funds", [])
        min_count = expected_facts["min_fund_count"]
        match = len(funds) >= min_count
        results.append(CheckResult(
            assertion=f"min_fund_count: {min_count}",
            passed=match,
            detail=f"Fund count={len(funds)}, min={min_count}",
        ))

    passed = sum(1 for r in results if r.passed)
    return MemoScoreReport(
        firm_name=firm_name,
        total_checks=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )


def _parse_aum(value: str | None) -> float | None:
    """Parse a USD string like '$5.00B' to float."""
    if not value or not isinstance(value, str):
        return None
    s = value.upper().replace(",", "").replace("$", "").strip()
    multiplier = 1.0
    if s.endswith("T"):
        multiplier, s = 1e12, s[:-1]
    elif s.endswith("B"):
        multiplier, s = 1e9, s[:-1]
    elif s.endswith("M"):
        multiplier, s = 1e6, s[:-1]
    elif s.endswith("K"):
        multiplier, s = 1e3, s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return None
