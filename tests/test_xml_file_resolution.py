"""
Tests for improved EDGAR XML file resolution (_xml_file_from_filing).
All HTTP calls are mocked — no network required.
"""

from unittest.mock import patch, MagicMock

from tools.adv_parser import (
    _xml_file_from_filing,
    _xml_file_from_submissions,
    _xml_file_from_html_index,
)


# ── Mock EDGAR HTML index pages ──────────────────────────────────────────────

STANDARD_HTML_INDEX = """
<html><body>
<table>
<tr><td>primary_doc.xml</td><td><a href="primary_doc.xml">primary_doc.xml</a></td></tr>
<tr><td>infotable.xml</td><td><a href="infotable.xml">infotable.xml</a></td></tr>
</table>
</body></html>
"""

NON_STANDARD_HTML_INDEX = """
<html><body>
<table>
<tr><td><a href="form13fInfoTable_2025q1.xml">form13fInfoTable_2025q1.xml</a></td></tr>
<tr><td><a href="xslFormN-CSR.xml">xslFormN-CSR.xml</a></td></tr>
</table>
</body></html>
"""

EMPTY_HTML_INDEX = """
<html><body><table></table></body></html>
"""


# ── Mock submissions API response ────────────────────────────────────────────

MOCK_SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": [
                "0001234567-26-000001",
                "0001234567-25-000099",
            ],
            "primaryDocument": [
                "primary_doc.xml",
                "form13f_summary.xml",
            ],
            "form": ["13F-HR", "13F-HR"],
        }
    }
}


class TestXmlFileFromSubmissions:
    """Tests for _xml_file_from_submissions() — submissions API approach."""

    @patch("tools.adv_parser._json")
    def test_finds_primary_doc_by_accession(self, mock_json):
        mock_json.return_value = MOCK_SUBMISSIONS
        result = _xml_file_from_submissions("1234567", "0001234567-26-000001")
        assert result == "primary_doc.xml"

    @patch("tools.adv_parser._json")
    def test_finds_second_filing(self, mock_json):
        mock_json.return_value = MOCK_SUBMISSIONS
        result = _xml_file_from_submissions("1234567", "0001234567-25-000099")
        assert result == "form13f_summary.xml"

    @patch("tools.adv_parser._json")
    def test_returns_none_for_unknown_accession(self, mock_json):
        mock_json.return_value = MOCK_SUBMISSIONS
        result = _xml_file_from_submissions("1234567", "0009999999-99-999999")
        assert result is None

    @patch("tools.adv_parser._json")
    def test_returns_none_when_api_fails(self, mock_json):
        mock_json.return_value = None
        result = _xml_file_from_submissions("1234567", "0001234567-26-000001")
        assert result is None

    @patch("tools.adv_parser._json")
    def test_skips_non_xml_primary_doc(self, mock_json):
        mock_json.return_value = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001234567-26-000001"],
                    "primaryDocument": ["form13f.htm"],
                    "form": ["13F-HR"],
                }
            }
        }
        result = _xml_file_from_submissions("1234567", "0001234567-26-000001")
        assert result is None


class TestXmlFileFromHtmlIndex:
    """Tests for _xml_file_from_html_index() — HTML scraping fallback."""

    @patch("tools.adv_parser._text")
    def test_finds_primary_doc_xml(self, mock_text):
        mock_text.return_value = STANDARD_HTML_INDEX
        result = _xml_file_from_html_index("1234567", "0001234567-26-000001")
        assert result == "primary_doc.xml"

    @patch("tools.adv_parser._text")
    def test_finds_non_standard_xml(self, mock_text):
        mock_text.return_value = NON_STANDARD_HTML_INDEX
        result = _xml_file_from_html_index("1234567", "0001234567-26-000001")
        assert result == "form13fInfoTable_2025q1.xml"

    @patch("tools.adv_parser._text")
    def test_returns_none_for_empty_index(self, mock_text):
        mock_text.return_value = EMPTY_HTML_INDEX
        result = _xml_file_from_html_index("1234567", "0001234567-26-000001")
        assert result is None

    @patch("tools.adv_parser._text")
    def test_returns_none_when_fetch_fails(self, mock_text):
        mock_text.return_value = None
        result = _xml_file_from_html_index("1234567", "0001234567-26-000001")
        assert result is None


class TestXmlFileFromFiling:
    """Tests for _xml_file_from_filing() — integrated resolution with fallback."""

    @patch("tools.adv_parser._xml_file_from_html_index")
    @patch("tools.adv_parser._xml_file_from_submissions")
    def test_prefers_submissions_api(self, mock_sub, mock_html):
        mock_sub.return_value = "primary_doc.xml"
        mock_html.return_value = "other.xml"
        result = _xml_file_from_filing("1234567", "0001234567-26-000001")
        assert result == "primary_doc.xml"
        mock_html.assert_not_called()  # should not fall back when primary succeeds

    @patch("tools.adv_parser._xml_file_from_html_index")
    @patch("tools.adv_parser._xml_file_from_submissions")
    def test_falls_back_to_html_when_submissions_fails(self, mock_sub, mock_html):
        mock_sub.return_value = None
        mock_html.return_value = "primary_doc.xml"
        result = _xml_file_from_filing("1234567", "0001234567-26-000001")
        assert result == "primary_doc.xml"
        mock_html.assert_called_once()

    @patch("tools.adv_parser._xml_file_from_html_index")
    @patch("tools.adv_parser._xml_file_from_submissions")
    def test_returns_none_when_both_fail(self, mock_sub, mock_html):
        mock_sub.return_value = None
        mock_html.return_value = None
        result = _xml_file_from_filing("1234567", "0001234567-26-000001")
        assert result is None
