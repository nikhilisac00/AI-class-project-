"""
Tests for agents/fact_checker.py — deterministic raw-to-analysis checks.
No live API calls; all data is constructed in-process.
"""

from agents.fact_checker import run_deterministic_checks


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _make_raw_data(
    firm_name: str = "AQR Capital Management",
    crd: str = "149729",
    reg_status: str = "Active",
    portfolio_value_fmt: str = "$5.00B",
    holdings_count: int = 200,
    fund_count: int = 3,
) -> dict:
    return {
        "adv_summary": {
            "firm_name": firm_name,
            "crd_number": crd,
            "registration_status": reg_status,
        },
        "adv_xml_data": {
            "thirteenf": {
                "portfolio_value_fmt": portfolio_value_fmt,
                "portfolio_value_usd": 5_000_000_000,
                "holdings_count": holdings_count,
            }
        },
        "fund_discovery": {"funds": [{"name": f"Fund {i}"} for i in range(fund_count)]},
        "errors": [],
    }


def _make_analysis(
    name: str = "AQR Capital Management",
    crd: str = "149729",
    reg_status: str = "Active",
    portfolio_value: str = "$5.00B",
    holdings_count: int = 200,
    total_funds: int = 3,
) -> dict:
    return {
        "firm_overview": {
            "name": name,
            "crd": crd,
            "registration_status": reg_status,
        },
        "13f_filings": {
            "available": True,
            "portfolio_value": portfolio_value,
            "holdings_count": holdings_count,
        },
        "funds_analysis": {"total_funds_found": total_funds},
    }


def _make_risk_report(tier: str = "MEDIUM", flags: list | None = None) -> dict:
    if flags is None:
        flags = [
            {
                "category": "Regulatory",
                "severity": "MEDIUM",
                "finding": "Resolved fine from 2019",
                "evidence": "ADV",
            }
        ]
    return {
        "overall_risk_tier": tier,
        "flags": flags,
        "clean_items": ["Operations clean"],
        "critical_data_gaps": [],
        "overall_commentary": "Moderate risk profile.",
    }


def _make_scorecard(rec: str = "PROCEED WITH CAUTION") -> dict:
    return {"recommendation": rec, "confidence": "MEDIUM", "overall_score": 65}


SAMPLE_MEMO = """# DUE DILIGENCE MEMO — AQR Capital Management
**Overall Risk Tier: MEDIUM**
AQR Capital Management (CRD: 149729) is an Active SEC-registered adviser.
13F portfolio value is $5.00B across 200 holdings.
The firm manages 3 private funds.
## Risk Flags
| Category | Severity | Finding |
|---|---|---|
| Regulatory | MEDIUM | Resolved fine from 2019 |
"""


def _find_check(results: list[dict], name: str) -> dict:
    """Return the first check result whose 'check' key contains `name`."""
    for item in results:
        if name.lower() in item["check"].lower():
            return item
    raise KeyError(f"No check matching '{name}' found in results: {[r['check'] for r in results]}")


# ── TestFirmNameCheck ──────────────────────────────────────────────────────────

class TestFirmNameCheck:
    def test_pass_exact_match(self):
        raw = _make_raw_data(firm_name="AQR Capital Management")
        analysis = _make_analysis(name="AQR Capital Management")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "firm name")
        assert check["status"] == "PASS"

    def test_pass_abbreviation(self):
        """Analysis name is a substring / abbreviation of the raw name — should PASS."""
        raw = _make_raw_data(firm_name="AQR Capital Management LLC")
        analysis = _make_analysis(name="AQR Capital Management")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "firm name")
        assert check["status"] == "PASS"

    def test_fail_mismatch(self):
        raw = _make_raw_data(firm_name="AQR Capital Management")
        analysis = _make_analysis(name="Bridgewater Associates")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "firm name")
        assert check["status"] == "FAIL"


# ── TestCrdCheck ───────────────────────────────────────────────────────────────

class TestCrdCheck:
    def test_pass(self):
        raw = _make_raw_data(crd="149729")
        analysis = _make_analysis(crd="149729")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "crd")
        assert check["status"] == "PASS"

    def test_fail_mismatch(self):
        raw = _make_raw_data(crd="149729")
        analysis = _make_analysis(crd="999999")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "crd")
        assert check["status"] == "FAIL"


# ── TestRegistrationStatusRawToAnalysis ───────────────────────────────────────

class TestRegistrationStatusRawToAnalysis:
    def test_pass(self):
        raw = _make_raw_data(reg_status="Active")
        analysis = _make_analysis(reg_status="Active")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "registration status")
        assert check["status"] == "PASS"

    def test_fail_mismatch(self):
        raw = _make_raw_data(reg_status="Active")
        analysis = _make_analysis(reg_status="Inactive")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "registration status")
        assert check["status"] == "FAIL"

    def test_warn_one_null(self):
        raw = _make_raw_data(reg_status=None)
        analysis = _make_analysis(reg_status="Active")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "registration status")
        assert check["status"] == "WARN"


# ── TestPortfolioValueRawToAnalysis ───────────────────────────────────────────

class TestPortfolioValueRawToAnalysis:
    def test_pass(self):
        raw = _make_raw_data(portfolio_value_fmt="$5.00B")
        analysis = _make_analysis(portfolio_value="$5.00B")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "portfolio value")
        assert check["status"] == "PASS"

    def test_fail_divergence(self):
        raw = _make_raw_data(portfolio_value_fmt="$5.00B")
        analysis = _make_analysis(portfolio_value="$9.00B")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "portfolio value")
        assert check["status"] == "FAIL"

    def test_warn_one_null(self):
        raw = _make_raw_data(portfolio_value_fmt=None)
        analysis = _make_analysis(portfolio_value="$5.00B")
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "portfolio value")
        assert check["status"] == "WARN"


# ── TestFundCountCheck ─────────────────────────────────────────────────────────

class TestFundCountCheck:
    def test_pass(self):
        raw = _make_raw_data(fund_count=3)
        analysis = _make_analysis(total_funds=3)
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "fund count")
        assert check["status"] == "PASS"

    def test_warn_large_difference(self):
        raw = _make_raw_data(fund_count=3)
        analysis = _make_analysis(total_funds=10)
        results = run_deterministic_checks(
            analysis, _make_risk_report(), raw, _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "fund count")
        assert check["status"] == "WARN"


# ── TestRiskTierInMemo ─────────────────────────────────────────────────────────

class TestRiskTierInMemo:
    def test_pass(self):
        """Risk tier 'MEDIUM' appears in SAMPLE_MEMO — should PASS."""
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="MEDIUM"), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "risk tier in memo")
        assert check["status"] == "PASS"

    def test_fail_missing(self):
        """Memo text contains no risk tier string — should FAIL."""
        memo_without_tier = "This memo has no risk tier information."
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH"), _make_raw_data(),
            _make_scorecard(), memo_without_tier
        )
        check = _find_check(results, "risk tier in memo")
        assert check["status"] == "FAIL"


# ── TestHighFlagsInMemo ────────────────────────────────────────────────────────

class TestHighFlagsInMemo:
    def test_pass_all_referenced(self):
        """HIGH flag with words present in memo — should PASS."""
        high_flag = {
            "category": "Regulatory",
            "severity": "HIGH",
            "finding": "Undisclosed conflict of interest with affiliated broker",
            "evidence": "ADV Part 2",
        }
        memo_with_flag = SAMPLE_MEMO + "\n| Regulatory | HIGH | Undisclosed conflict of interest |"
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH", flags=[high_flag]),
            _make_raw_data(), _make_scorecard(), memo_with_flag
        )
        check = _find_check(results, "high flags in memo")
        assert check["status"] == "PASS"

    def test_fail_flag_missing(self):
        """HIGH flag whose words don't appear in memo — should FAIL."""
        high_flag = {
            "category": "Operational",
            "severity": "HIGH",
            "finding": "Missing audited financials for three consecutive years",
            "evidence": "EDGAR",
        }
        memo_no_flag = "This memo discusses the firm's investment strategy only."
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH", flags=[high_flag]),
            _make_raw_data(), _make_scorecard(), memo_no_flag
        )
        check = _find_check(results, "high flags in memo")
        assert check["status"] == "FAIL"

    def test_pass_no_high_flags(self):
        """No HIGH flags exist — should PASS immediately."""
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="MEDIUM"), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "high flags in memo")
        assert check["status"] == "PASS"


# ── TestPortfolioValueInMemo ───────────────────────────────────────────────────

class TestPortfolioValueInMemo:
    def test_pass(self):
        """Portfolio value '$5.00B' appears in SAMPLE_MEMO — should PASS."""
        results = run_deterministic_checks(
            _make_analysis(portfolio_value="$5.00B"), _make_risk_report(),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "portfolio value in memo")
        assert check["status"] == "PASS"

    def test_warn_missing(self):
        """Portfolio value not in memo — should WARN."""
        memo_no_value = "This memo does not mention any portfolio value."
        results = run_deterministic_checks(
            _make_analysis(portfolio_value="$9.00B"), _make_risk_report(),
            _make_raw_data(), _make_scorecard(), memo_no_value
        )
        check = _find_check(results, "portfolio value in memo")
        assert check["status"] == "WARN"


# ── TestRegistrationStatusInMemo ──────────────────────────────────────────────

class TestRegistrationStatusInMemo:
    def test_pass(self):
        """Registration status 'Active' appears in SAMPLE_MEMO — should PASS."""
        results = run_deterministic_checks(
            _make_analysis(reg_status="Active"), _make_risk_report(),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "registration in memo")
        assert check["status"] == "PASS"

    def test_warn_missing(self):
        """Registration status not found in memo — should WARN."""
        memo_no_status = "This memo covers only fund performance data."
        results = run_deterministic_checks(
            _make_analysis(reg_status="Active"), _make_risk_report(),
            _make_raw_data(), _make_scorecard(), memo_no_status
        )
        check = _find_check(results, "registration in memo")
        assert check["status"] == "WARN"


# ── TestRiskTierVsFlags ────────────────────────────────────────────────────────

class TestRiskTierVsFlags:
    def test_pass_medium_with_medium_flags(self):
        """MEDIUM tier with only MEDIUM flags — should PASS."""
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="MEDIUM"), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "risk tier vs flags")
        assert check["status"] == "PASS"

    def test_fail_low_with_high_flags(self):
        """LOW tier but a HIGH flag exists — should FAIL."""
        high_flag = {
            "category": "Fraud",
            "severity": "HIGH",
            "finding": "Fraudulent activity reported",
            "evidence": "SEC enforcement",
        }
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="LOW", flags=[high_flag]),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "risk tier vs flags")
        assert check["status"] == "FAIL"

    def test_pass_high_with_high_flags(self):
        """HIGH tier with HIGH flags — consistent, should PASS."""
        high_flags = [
            {"category": "Fraud", "severity": "HIGH", "finding": "Enforcement action", "evidence": "SEC"},
            {"category": "Ops", "severity": "HIGH", "finding": "Missing controls", "evidence": "ADV"},
        ]
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH", flags=high_flags),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "risk tier vs flags")
        assert check["status"] == "PASS"


# ── TestScorecardVsRiskTier ────────────────────────────────────────────────────

class TestScorecardVsRiskTier:
    def test_pass_consistent(self):
        """'PROCEED WITH CAUTION' with HIGH tier — not a PROCEED-without-CAUTION case, PASS."""
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH"),
            _make_raw_data(), _make_scorecard(rec="PROCEED WITH CAUTION"), SAMPLE_MEMO
        )
        check = _find_check(results, "scorecard vs risk tier")
        assert check["status"] == "PASS"

    def test_warn_proceed_with_high_risk(self):
        """'PROCEED' (no CAUTION) with HIGH tier — should WARN."""
        results = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH"),
            _make_raw_data(), _make_scorecard(rec="PROCEED"), SAMPLE_MEMO
        )
        check = _find_check(results, "scorecard vs risk tier")
        assert check["status"] == "WARN"


# ── TestHoldingsCountConsistency ──────────────────────────────────────────────

class TestHoldingsCountConsistency:
    def test_pass(self):
        """Both raw and analysis have matching holdings count — should PASS."""
        results = run_deterministic_checks(
            _make_analysis(holdings_count=200), _make_risk_report(),
            _make_raw_data(holdings_count=200), _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "holdings count")
        assert check["status"] == "PASS"

    def test_fail_mismatch(self):
        """Raw has 200 holdings, analysis claims 350 — should FAIL."""
        results = run_deterministic_checks(
            _make_analysis(holdings_count=350), _make_risk_report(),
            _make_raw_data(holdings_count=200), _make_scorecard(), SAMPLE_MEMO
        )
        check = _find_check(results, "holdings count")
        assert check["status"] == "FAIL"
