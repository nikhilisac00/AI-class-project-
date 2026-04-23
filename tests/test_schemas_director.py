# tests/test_schemas_director.py
"""Tests for DirectorReviewOutput validation in tools/schemas.py."""

from tools.schemas import validate_director_review, coerce_director_review


class TestValidateDirectorReview:
    def test_valid_review_no_errors(self):
        data = {
            "verdict": "CONFIRMED",
            "original_recommendation": "PROCEED",
            "revised_recommendation": "PROCEED",
            "director_commentary": "The analysis is consistent with the data.",
            "inconsistencies": [],
            "missed_signals": [],
            "questions_for_gp": ["What is the fund's liquidity provision?"],
            "cleared_for_ic": True,
        }
        assert validate_director_review(data) == []

    def test_missing_verdict(self):
        errors = validate_director_review({"revised_recommendation": "PROCEED"})
        assert any("verdict" in e for e in errors)

    def test_invalid_verdict_value(self):
        data = {"verdict": "APPROVED", "revised_recommendation": "PROCEED"}
        errors = validate_director_review(data)
        assert any("verdict" in e and "APPROVED" in e for e in errors)

    def test_invalid_revised_recommendation(self):
        data = {"verdict": "CONFIRMED", "revised_recommendation": "BUY"}
        errors = validate_director_review(data)
        assert any("revised_recommendation" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_director_review([])
        assert len(errors) > 0


class TestCoerceDirectorReview:
    def test_empty_dict_gets_defaults(self):
        result = coerce_director_review({})
        assert result["verdict"] == "INCONCLUSIVE"
        assert isinstance(result["inconsistencies"], list)
        assert isinstance(result["missed_signals"], list)

    def test_none_input(self):
        result = coerce_director_review(None)
        assert isinstance(result, dict)
        assert "verdict" in result
