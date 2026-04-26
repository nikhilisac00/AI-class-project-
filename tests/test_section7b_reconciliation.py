"""
Tests for Section 7.B vs Form D reconciliation check.
"""

from tools.reconciliation import check_section7b_vs_form_d


class TestSection7bVsFormD:
    """Tests for check_section7b_vs_form_d()."""

    def test_skip_when_no_section7b_data(self):
        result = check_section7b_vs_form_d({}, {"adv_summary": {}})
        assert result["status"] == "SKIP"

    def test_warn_when_no_form_d_funds(self):
        raw = {
            "adv_summary": {
                "private_funds_section7b": [
                    {"fund_name": "Alpha Fund LP"},
                ]
            },
            "fund_discovery": {"funds": []},
        }
        result = check_section7b_vs_form_d({}, raw)
        assert result["status"] == "WARN"
        assert result["section7b_count"] == 1
        assert result["form_d_count"] == 0

    def test_pass_when_all_funds_matched(self):
        raw = {
            "adv_summary": {
                "private_funds_section7b": [
                    {"fund_name": "Alpha Opportunities Fund LP"},
                ]
            },
            "fund_discovery": {
                "funds": [
                    {"fund_name": "Alpha Opportunities Fund LP", "source": "Form D"},
                ]
            },
        }
        result = check_section7b_vs_form_d({}, raw)
        assert result["status"] == "PASS"

    def test_warn_when_fund_unmatched(self):
        raw = {
            "adv_summary": {
                "private_funds_section7b": [
                    {"fund_name": "Alpha Opportunities Master Fund LP"},
                    {"fund_name": "Zephyr Global Macro Partners LLC"},
                ]
            },
            "fund_discovery": {
                "funds": [
                    {"fund_name": "Alpha Opportunities Master Fund LP"},
                ]
            },
        }
        result = check_section7b_vs_form_d({}, raw)
        assert result["status"] == "WARN"
        assert "Zephyr Global Macro Partners LLC" in result["unmatched_funds"]

    def test_fuzzy_matching_works(self):
        """Funds with slightly different names should still match (50% overlap)."""
        raw = {
            "adv_summary": {
                "private_funds_section7b": [
                    {"fund_name": "AQR Diversified Arbitrage Fund LLC"},
                ]
            },
            "fund_discovery": {
                "funds": [
                    {"fund_name": "AQR Diversified Arbitrage Fund"},
                ]
            },
        }
        result = check_section7b_vs_form_d({}, raw)
        assert result["status"] == "PASS"
