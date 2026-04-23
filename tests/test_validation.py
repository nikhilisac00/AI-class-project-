# tests/test_validation.py
"""Tests for tools/validation.py -- firm name / CRD input validation."""

import pytest

from tools.validation import validate_firm_input


class TestValidateFirmInput:
    """validate_firm_input accepts clean input, rejects bad input."""

    def test_valid_firm_name(self):
        assert validate_firm_input("AQR Capital Management") == "AQR Capital Management"

    def test_valid_crd(self):
        assert validate_firm_input("149729") == "149729"

    def test_strips_whitespace(self):
        assert validate_firm_input("  Bridgewater Associates  ") == "Bridgewater Associates"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="required"):
            validate_firm_input("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="required"):
            validate_firm_input("   ")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="too long"):
            validate_firm_input("A" * 201)

    def test_accepts_max_length(self):
        name = "A" * 200
        assert validate_firm_input(name) == name

    def test_rejects_special_characters(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            validate_firm_input("Firm<script>alert('xss')</script>")

    def test_accepts_common_punctuation(self):
        assert validate_firm_input("O'Brien & Partners, Inc.") == "O'Brien & Partners, Inc."

    def test_accepts_hyphens_and_slashes(self):
        assert validate_firm_input("Two-Sigma Investments/LP") == "Two-Sigma Investments/LP"

    def test_accepts_parentheses(self):
        assert validate_firm_input("BlackRock (UK)") == "BlackRock (UK)"

    def test_rejects_semicolons(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            validate_firm_input("Firm; DROP TABLE")

    def test_crd_rejects_too_long_numeric(self):
        with pytest.raises(ValueError, match="CRD.*digits"):
            validate_firm_input("12345678901")  # 11 digits

    def test_crd_accepts_short_numeric(self):
        assert validate_firm_input("1") == "1"
