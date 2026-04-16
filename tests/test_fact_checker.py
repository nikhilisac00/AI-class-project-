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
