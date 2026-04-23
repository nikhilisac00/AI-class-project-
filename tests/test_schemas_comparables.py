# tests/test_schemas_comparables.py
"""Tests for ComparablesOutput validation in tools/schemas.py."""

from tools.schemas import validate_comparables, coerce_comparables


class TestValidateComparables:
    def test_valid_output_no_errors(self):
        data = {
            "target": {"firm_name": "AQR", "is_target": True},
            "peers": [],
            "table": [{"firm_name": "AQR", "is_target": True}],
            "size_rank": None,
            "total_in_comparison": 1,
            "note": "Peers sourced from IAPD universe.",
        }
        assert validate_comparables(data) == []

    def test_missing_target(self):
        errors = validate_comparables({"peers": [], "table": []})
        assert any("target" in e for e in errors)

    def test_peers_must_be_list(self):
        data = {"target": {}, "peers": "bad", "table": []}
        errors = validate_comparables(data)
        assert any("peers" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_comparables(42)
        assert len(errors) > 0


class TestCoerceComparables:
    def test_empty_dict_gets_defaults(self):
        result = coerce_comparables({})
        assert isinstance(result["peers"], list)
        assert isinstance(result["table"], list)
        assert result["target"] == {}

    def test_none_input(self):
        result = coerce_comparables(None)
        assert isinstance(result, dict)
