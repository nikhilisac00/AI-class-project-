"""Tests for ScorecardOutput validation in tools/schemas.py."""

from tools.schemas import validate_scorecard, coerce_scorecard


class TestValidateScorecard:
    def test_valid_scorecard_no_errors(self):
        data = {
            "recommendation": "PROCEED",
            "confidence": "HIGH",
            "confidence_rationale": "Strong regulatory standing.",
            "recommendation_summary": "Firm is well positioned.",
            "scores": {
                "regulatory_compliance": {"score": 8, "rationale": "Clean record"},
                "data_availability": {"score": 7, "rationale": "Good coverage"},
                "key_person_risk": {"score": 6, "rationale": "Moderate concentration"},
                "fund_structure": {"score": 7, "rationale": "Standard terms"},
                "news_reputation": {"score": 8, "rationale": "Positive press"},
                "operational_maturity": {"score": 9, "rationale": "Long track record"},
            },
            "overall_score": 7.5,
            "reasons_to_proceed": ["Strong track record"],
            "reasons_to_pause": ["Key person concentration"],
            "minimum_diligence_items": [],
            "standard_lp_asks": [],
            "data_coverage_assessment": "HIGH",
            "data_coverage_note": "All key data available.",
        }
        assert validate_scorecard(data) == []

    def test_missing_recommendation(self):
        errors = validate_scorecard({"confidence": "HIGH"})
        assert any("recommendation" in e for e in errors)

    def test_invalid_recommendation_value(self):
        data = {"recommendation": "BUY", "confidence": "HIGH"}
        errors = validate_scorecard(data)
        assert any("recommendation" in e and "BUY" in e for e in errors)

    def test_invalid_confidence_value(self):
        data = {"recommendation": "PROCEED", "confidence": "VERY HIGH"}
        errors = validate_scorecard(data)
        assert any("confidence" in e for e in errors)

    def test_scores_must_be_dict(self):
        data = {"recommendation": "PROCEED", "confidence": "HIGH", "scores": "bad"}
        errors = validate_scorecard(data)
        assert any("scores" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_scorecard("string")
        assert len(errors) > 0


class TestCoerceScorecard:
    def test_empty_dict_gets_defaults(self):
        result = coerce_scorecard({})
        assert result["recommendation"] == "REQUEST MORE INFO"
        assert result["confidence"] == "LOW"
        assert isinstance(result["reasons_to_proceed"], list)
        assert isinstance(result["reasons_to_pause"], list)

    def test_none_input(self):
        result = coerce_scorecard(None)
        assert isinstance(result, dict)
        assert "recommendation" in result
