"""
Tests for ADV Section 7.B private fund parsing.
All HTTP calls are mocked — no network required.
"""

from unittest.mock import patch

from tools.edgar_client import (
    parse_section_7b,
    _find_section_7b_start,
    _normalize_pdf_text,
    _parse_fund_block,
    fetch_private_funds_section7b,
)


# ── Sample PDF text fragments ────────────────────────────────────────────────

SAMPLE_SECTION_7B_TEXT = """
SECTION 7.B. Private Fund Reporting

Name of the private fund: Alpha Opportunities Fund LP
Type of private fund: Hedge Fund
Gross asset value: $2,500,000,000
Number of beneficial owners: 150
Is the private fund a feeder fund: No

Name of the private fund: Beta Real Estate Partners II
Type of private fund: Real Estate Fund
Gross asset value: $800,000,000
Number of beneficial owners: 45
Is the private fund a feeder fund: Yes

SECTION 8. Participation or Interest in Client Transactions
"""

MINIMAL_SECTION_7B = """
Some preamble text here.
SECTION 7.B.
Name of the private fund: Solo Fund
SECTION 9.
"""


class TestParseSection7b:
    """Tests for parse_section_7b()."""

    def test_empty_text_returns_empty_list(self):
        assert parse_section_7b("") == []

    def test_none_text_returns_empty_list(self):
        assert parse_section_7b(None) == []

    def test_no_section_7b_returns_empty(self):
        assert parse_section_7b("This is a document with no section 7B.") == []

    def test_parses_two_funds(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert len(funds) == 2

    def test_first_fund_name(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert funds[0]["fund_name"] == "Alpha Opportunities Fund LP"

    def test_first_fund_type(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert funds[0]["fund_type"] == "Hedge Fund"

    def test_first_fund_gav(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert funds[0]["gross_asset_value"] == 2_500_000_000

    def test_first_fund_owners(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert funds[0]["number_of_beneficial_owners"] == 150

    def test_first_fund_not_feeder(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert funds[0]["is_feeder_fund"] is False

    def test_second_fund_is_feeder(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert funds[1]["is_feeder_fund"] is True

    def test_second_fund_type_real_estate(self):
        funds = parse_section_7b(SAMPLE_SECTION_7B_TEXT)
        assert funds[1]["fund_type"] == "Real Estate Fund"

    def test_minimal_section_7b(self):
        funds = parse_section_7b(MINIMAL_SECTION_7B)
        assert len(funds) == 1
        assert funds[0]["fund_name"] == "Solo Fund"


class TestFindSection7bStart:
    """Tests for _find_section_7b_start()."""

    def test_finds_standard_header(self):
        assert _find_section_7b_start("blah SECTION 7.B blah") >= 0

    def test_finds_schedule_d_variant(self):
        assert _find_section_7b_start("Schedule D Section 7.B") >= 0

    def test_finds_private_fund_reporting(self):
        assert _find_section_7b_start("PRIVATE FUND REPORTING") >= 0

    def test_returns_negative_when_missing(self):
        assert _find_section_7b_start("no section here") < 0


class TestNormalizePdfText:
    """Tests for _normalize_pdf_text() — pypdf artifact fixes."""

    def test_removes_page_number_lines(self):
        text = "Some content\n  42  \nMore content"
        result = _normalize_pdf_text(text)
        assert "42" not in result.split("\n")[1].strip() or "42" not in result

    def test_rejoins_wrapped_label_phrase(self):
        text = "Name of the private\nfund: Alpha Fund LP"
        result = _normalize_pdf_text(text)
        assert "Name of the private fund:" in result

    def test_rejoins_gross_asset_value(self):
        text = "Gross asset\nvalue: $1.2B"
        result = _normalize_pdf_text(text)
        assert "Gross asset value:" in result

    def test_collapses_value_on_next_line(self):
        text = "Name of the private fund:\n  Alpha Opportunities Fund LP"
        result = _normalize_pdf_text(text)
        assert "Name of the private fund: Alpha Opportunities Fund LP" in result

    def test_parse_section7b_handles_wrapped_labels(self):
        """End-to-end: parse_section_7b should extract fund from wrapped-label PDF text."""
        wrapped_text = """
SECTION 7.B. Private Fund Reporting

Name of the private
fund: Wrapped Label Fund LP
Type of private fund: Hedge Fund
Gross asset
value: $500,000,000
beneficial owners: 80
Is the private fund a feeder fund: No

SECTION 8.
"""
        funds = parse_section_7b(wrapped_text)
        assert len(funds) == 1
        assert funds[0]["fund_name"] == "Wrapped Label Fund LP"
        assert funds[0]["gross_asset_value"] == 500_000_000
        assert funds[0]["number_of_beneficial_owners"] == 80


class TestParseFundBlock:
    """Tests for _parse_fund_block()."""

    def test_empty_block(self):
        result = _parse_fund_block("")
        assert result["fund_name"] is None

    def test_extracts_name(self):
        block = "Name of the private fund: Test Fund LP\nSome other stuff"
        result = _parse_fund_block(block)
        assert result["fund_name"] == "Test Fund LP"

    def test_extracts_beneficial_owners(self):
        block = "Name of the private fund: X\nbeneficial owners: 75\n"
        result = _parse_fund_block(block)
        assert result["number_of_beneficial_owners"] == 75

    def test_infers_fund_type_from_keywords(self):
        block = "Name of the private fund: Y\nThis is a venture capital fund\n"
        result = _parse_fund_block(block)
        assert result["fund_type"] == "Venture Capital Fund"


class TestFetchPrivateFundsSection7b:
    """Tests for fetch_private_funds_section7b() with mocked PDF download."""

    @patch("tools.edgar_client.fetch_adv_pdf_text")
    def test_returns_empty_when_pdf_unavailable(self, mock_fetch):
        mock_fetch.return_value = None
        result = fetch_private_funds_section7b("123456")
        assert result == []

    @patch("tools.edgar_client.fetch_adv_pdf_text")
    def test_parses_funds_from_pdf_text(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_SECTION_7B_TEXT
        result = fetch_private_funds_section7b("123456")
        assert len(result) == 2
        assert result[0]["fund_name"] == "Alpha Opportunities Fund LP"
