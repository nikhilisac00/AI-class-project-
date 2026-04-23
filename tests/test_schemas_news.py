"""Tests for validate_news_report in tools/schemas.py."""

from tools.schemas import validate_news_report


class TestValidateNewsReport:
    """Validation tests for news research agent output schema."""

    def test_valid_report_no_errors(self):
        """A fully valid report should produce zero errors."""
        data = {
            "firm_name": "AQR",
            "research_rounds": 2,
            "total_sources": 5,
            "news_flags": [],
            "news_summary": "No material news found.",
            "overall_news_risk": "CLEAN",
            "findings": [],
            "sources_consulted": [],
            "queries_used": ["AQR Capital enforcement"],
            "coverage_gaps": [],
            "errors": [],
        }
        assert validate_news_report(data) == []

    def test_missing_firm_name(self):
        """Missing firm_name should be flagged."""
        errors = validate_news_report({"overall_news_risk": "LOW"})
        assert any("firm_name" in e for e in errors)

    def test_invalid_risk_level(self):
        """An unrecognised overall_news_risk value should be flagged."""
        data = {"firm_name": "Test", "overall_news_risk": "EXTREME"}
        errors = validate_news_report(data)
        assert any("overall_news_risk" in e for e in errors)

    def test_news_flags_must_be_list(self):
        """news_flags must be a list, not a string."""
        data = {"firm_name": "Test", "news_flags": "bad"}
        errors = validate_news_report(data)
        assert any("news_flags" in e for e in errors)

    def test_not_a_dict(self):
        """Non-dict input should return at least one error."""
        errors = validate_news_report(None)
        assert len(errors) > 0
