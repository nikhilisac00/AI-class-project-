"""
Tests for agents/portfolio_fit.py — portfolio fit agent logic.
LLM calls are mocked; no live API calls.
"""

from unittest.mock import MagicMock

from agents.portfolio_fit import run, SYSTEM_PROMPT


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


def _make_risk_report(tier: str = "MEDIUM") -> dict:
    """Minimal risk report dict."""
    return {
        "overall_risk_tier": tier,
        "flags": [
            {"category": "Regulatory", "severity": "LOW",
             "finding": "Minor flag", "evidence": "test"},
        ],
        "clean_items": ["Operations clean"],
        "critical_data_gaps": [],
    }


def _make_raw_data() -> dict:
    """Minimal raw ingestion data dict."""
    return {
        "adv_summary": {
            "firm_name": "Test Capital",
            "crd_number": "123456",
            "registration_status": "Active",
        },
        "adv_xml_data": {
            "thirteenf": {"portfolio_value_fmt": "$2.50B"},
        },
        "fund_discovery": {"funds": [{"name": "Fund I"}]},
        "errors": [],
    }


def _make_lp_portfolio() -> dict:
    """LP portfolio allocation dict matching the expected input shape."""
    return {
        "strategies": {
            "Long/Short Equity": 30,
            "Private Credit": 25,
            "Venture Capital": 20,
            "Real Estate": 15,
            "Multi-Strategy": 10,
        },
        "geographies": {
            "North America": 60,
            "Europe": 25,
            "Asia Pacific": 15,
        },
        "vintage_exposure": {
            "2020": 15,
            "2021": 25,
            "2022": 20,
            "2023": 20,
            "2024": 20,
        },
        "num_managers": 12,
        "target_managers": 15,
        "typical_check_size_mm": 25,
        "risk_budget_remaining": 35,
    }


MOCK_FIT_RESPONSE = {
    "fit_score": 72,
    "fit_label": "GOOD FIT",
    "recommendation": "CONSIDER",
    "recommendation_detail": "The manager fills a gap in private credit exposure.",
    "dimension_scores": {
        "strategy_fit": {
            "score": 80,
            "rationale": "Fills private credit gap",
        },
        "geographic_diversification": {
            "score": 65,
            "rationale": "Primarily North America — limited diversification benefit",
        },
        "vintage_exposure": {
            "score": 70,
            "rationale": "2024 vintage helps balance concentration",
        },
        "size_fit": {
            "score": 75,
            "rationale": "Fund size appropriate for check size",
        },
        "risk_budget_alignment": {
            "score": 60,
            "rationale": "MEDIUM risk uses moderate budget",
        },
        "manager_count": {
            "score": 85,
            "rationale": "Adding moves closer to target of 15",
        },
    },
    "fit_gaps": ["Private credit allocation currently below target"],
    "fit_concerns": ["North America concentration would increase"],
}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPortfolioFitRun:
    def _mock_client(self, response: dict = None) -> MagicMock:
        client = MagicMock()
        client.provider = "openai"
        client.model = "gpt-4o"
        client.complete_json.return_value = response or MOCK_FIT_RESPONSE
        return client

    def test_returns_fit_dict(self):
        client = self._mock_client()
        result = run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        assert result["fit_score"] == 72
        assert result["fit_label"] == "GOOD FIT"
        assert result["recommendation"] == "CONSIDER"

    def test_calls_llm_with_system_prompt(self):
        client = self._mock_client()
        run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        call_kwargs = client.complete_json.call_args
        assert call_kwargs.kwargs["system"] == SYSTEM_PROMPT

    def test_user_prompt_contains_firm_name(self):
        client = self._mock_client()
        run(
            firm_name="Alpha Capital",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        user_msg = client.complete_json.call_args.kwargs["user"]
        assert "Alpha Capital" in user_msg

    def test_user_prompt_contains_lp_portfolio(self):
        client = self._mock_client()
        portfolio = _make_lp_portfolio()
        run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=portfolio,
            client=client,
        )
        user_msg = client.complete_json.call_args.kwargs["user"]
        assert "Long/Short Equity" in user_msg
        assert "risk_budget_remaining" in user_msg

    def test_dimension_scores_present(self):
        client = self._mock_client()
        result = run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        dims = result["dimension_scores"]
        assert "strategy_fit" in dims
        assert "geographic_diversification" in dims
        assert "risk_budget_alignment" in dims
        assert "manager_count" in dims

    def test_handles_none_risk_report(self):
        """Should not crash when risk_report is None."""
        client = self._mock_client()
        result = run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=None,
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        assert result is not None

    def test_handles_empty_raw_data(self):
        """Should handle raw_data with missing keys."""
        client = self._mock_client()
        result = run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data={},
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        assert result is not None

    def test_handles_minimal_lp_portfolio(self):
        """Should work with a sparse LP portfolio dict."""
        client = self._mock_client()
        result = run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio={"strategies": {}, "num_managers": 5},
            client=client,
        )
        assert result is not None

    def test_fit_gaps_and_concerns_returned(self):
        client = self._mock_client()
        result = run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        assert len(result["fit_gaps"]) >= 1
        assert len(result["fit_concerns"]) >= 1

    def test_raw_data_fields_in_prompt(self):
        """Prompt should include registration status and 13F value."""
        client = self._mock_client()
        run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        user_msg = client.complete_json.call_args.kwargs["user"]
        assert "$2.50B" in user_msg
        assert "Active" in user_msg

    def test_prompt_requests_json_schema(self):
        """Prompt should specify the expected JSON output schema."""
        client = self._mock_client()
        run(
            firm_name="Test Fund",
            analysis=_make_analysis(),
            risk_report=_make_risk_report(),
            raw_data=_make_raw_data(),
            lp_portfolio=_make_lp_portfolio(),
            client=client,
        )
        user_msg = client.complete_json.call_args.kwargs["user"]
        assert "fit_score" in user_msg
        assert "dimension_scores" in user_msg
        assert "fit_gaps" in user_msg
        assert "fit_concerns" in user_msg
