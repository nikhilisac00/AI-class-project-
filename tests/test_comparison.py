"""
Tests for agents/comparison.py — comparison agent logic.
LLM calls are mocked; no live API calls.
"""

from unittest.mock import MagicMock

from agents.comparison import run, SYSTEM_PROMPT


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_analysis(name: str = "Test Fund") -> dict:
    """Minimal analysis dict matching fund_analysis agent output."""
    return {
        "firm_overview": {
            "name": name,
            "registration_status": "Active",
            "aum": None,
        },
        "fee_structure": {"management_fee": "2%", "performance_fee": "20%"},
        "investment_team": {"professionals_count": 5},
    }


def _make_risk_report(tier: str = "MEDIUM", flag_count: int = 2) -> dict:
    """Minimal risk report dict matching risk_flagging agent output."""
    flags = [
        {"category": "Regulatory", "severity": "HIGH" if i == 0 else "LOW",
         "finding": f"Flag {i + 1}", "evidence": "test"}
        for i in range(flag_count)
    ]
    return {
        "overall_risk_tier": tier,
        "flags": flags,
        "clean_items": ["Operations appear clean"],
        "critical_data_gaps": [],
    }


def _make_raw_data(crd: str = "123456") -> dict:
    """Minimal raw ingestion data dict."""
    return {
        "adv_summary": {
            "firm_name": "Test Capital",
            "crd_number": crd,
            "registration_status": "Active",
        },
        "adv_xml_data": {
            "thirteenf": {"portfolio_value_fmt": "$5.00B"},
        },
        "fund_discovery": {"funds": [{"name": "Fund I"}, {"name": "Fund II"}]},
        "errors": [],
    }


def _make_scorecard(rec: str = "PROCEED WITH CAUTION") -> dict:
    """Minimal IC scorecard dict."""
    return {
        "recommendation": rec,
        "confidence": "MEDIUM",
        "overall_score": 65,
        "scores": {"regulatory": 7, "operations": 6},
        "reasons_to_proceed": ["Strong track record"],
        "reasons_to_pause": ["Key person risk"],
    }


MOCK_COMPARISON_RESPONSE = {
    "manager_a": "Firm A",
    "manager_b": "Firm B",
    "dimensions": [
        {
            "dimension": "Regulatory / Compliance",
            "manager_a_value": "Clean record",
            "manager_b_value": "One resolved fine",
            "winner": "A",
            "rationale": "Firm A has no regulatory issues",
        },
        {
            "dimension": "Risk Profile",
            "manager_a_value": "MEDIUM tier, 2 flags",
            "manager_b_value": "LOW tier, 1 flag",
            "winner": "B",
            "rationale": "Firm B has fewer risk flags",
        },
    ],
    "overall_winner": "A",
    "overall_rationale": "Firm A is stronger on regulatory and operational maturity.",
    "key_differentiators": [
        "Firm A has a clean regulatory record",
        "Firm B has lower fees",
    ],
    "recommendation": "PREFER A",
    "recommendation_detail": "Recommend Firm A for institutional allocation.",
}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestComparisonRun:
    def _mock_client(self, response: dict = None) -> MagicMock:
        client = MagicMock()
        client.complete_json.return_value = response or MOCK_COMPARISON_RESPONSE
        return client

    def test_returns_comparison_dict(self):
        client = self._mock_client()
        result = run(
            firm_a_name="Firm A",
            firm_b_name="Firm B",
            analysis_a=_make_analysis("Firm A"),
            analysis_b=_make_analysis("Firm B"),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report("LOW", 1),
            raw_data_a=_make_raw_data("111"),
            raw_data_b=_make_raw_data("222"),
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard("PROCEED"),
            client=client,
        )
        assert result["overall_winner"] == "A"
        assert result["recommendation"] == "PREFER A"
        assert len(result["dimensions"]) == 2

    def test_calls_llm_with_system_prompt(self):
        client = self._mock_client()
        run(
            firm_a_name="Firm A",
            firm_b_name="Firm B",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a=_make_raw_data(),
            raw_data_b=_make_raw_data(),
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        call_kwargs = client.complete_json.call_args
        assert call_kwargs.kwargs["system"] == SYSTEM_PROMPT

    def test_user_prompt_contains_both_firm_names(self):
        client = self._mock_client()
        run(
            firm_a_name="Alpha Capital",
            firm_b_name="Beta Partners",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a=_make_raw_data(),
            raw_data_b=_make_raw_data(),
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        user_msg = client.complete_json.call_args.kwargs["user"]
        assert "Alpha Capital" in user_msg
        assert "Beta Partners" in user_msg

    def test_handles_none_analysis(self):
        """Agent should not crash when analysis dicts are None."""
        client = self._mock_client()
        result = run(
            firm_a_name="Firm A",
            firm_b_name="Firm B",
            analysis_a=None,
            analysis_b=None,
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a=_make_raw_data(),
            raw_data_b=_make_raw_data(),
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        assert result is not None

    def test_handles_none_risk_reports(self):
        """Agent should not crash when risk reports are None."""
        client = self._mock_client()
        result = run(
            firm_a_name="Firm A",
            firm_b_name="Firm B",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=None,
            risk_report_b=None,
            raw_data_a=_make_raw_data(),
            raw_data_b=_make_raw_data(),
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        assert result is not None

    def test_handles_none_scorecards(self):
        """Agent should not crash when scorecards are None."""
        client = self._mock_client()
        result = run(
            firm_a_name="Firm A",
            firm_b_name="Firm B",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a=_make_raw_data(),
            raw_data_b=_make_raw_data(),
            scorecard_a=None,
            scorecard_b=None,
            client=client,
        )
        assert result is not None

    def test_handles_empty_raw_data(self):
        """Agent should handle raw_data with missing keys."""
        client = self._mock_client()
        result = run(
            firm_a_name="Firm A",
            firm_b_name="Firm B",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a={},
            raw_data_b={},
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        assert result is not None

    def test_dimensions_in_user_prompt(self):
        """User prompt should request specific comparison dimensions."""
        client = self._mock_client()
        run(
            firm_a_name="A",
            firm_b_name="B",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a=_make_raw_data(),
            raw_data_b=_make_raw_data(),
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        user_msg = client.complete_json.call_args.kwargs["user"]
        assert "Regulatory" in user_msg
        assert "overall_winner" in user_msg
        assert "key_differentiators" in user_msg

    def test_key_differentiators_returned(self):
        client = self._mock_client()
        result = run(
            firm_a_name="A",
            firm_b_name="B",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a=_make_raw_data(),
            raw_data_b=_make_raw_data(),
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        assert len(result["key_differentiators"]) == 2

    def test_raw_data_fields_included_in_summary(self):
        """The _summary helper should pull 13F and fund discovery data."""
        client = self._mock_client()
        raw = _make_raw_data()
        run(
            firm_a_name="A",
            firm_b_name="B",
            analysis_a=_make_analysis(),
            analysis_b=_make_analysis(),
            risk_report_a=_make_risk_report(),
            risk_report_b=_make_risk_report(),
            raw_data_a=raw,
            raw_data_b=raw,
            scorecard_a=_make_scorecard(),
            scorecard_b=_make_scorecard(),
            client=client,
        )
        user_msg = client.complete_json.call_args.kwargs["user"]
        assert "$5.00B" in user_msg
        assert "fund_count" in user_msg
