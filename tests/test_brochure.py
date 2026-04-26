"""
Tests for brochure PDF download and text extraction.
All HTTP calls are mocked — no network required.
"""

from unittest.mock import patch, MagicMock

from tools.adv_parser import (
    fetch_brochure_text,
    split_brochure_into_chunks,
)


# ── fetch_brochure_text ──────────────────────────────────────────────────────

class TestFetchBrochureText:
    """Tests for fetch_brochure_text() with mocked HTTP."""

    def test_none_id_returns_none(self):
        assert fetch_brochure_text(None) is None

    def test_empty_id_returns_none(self):
        assert fetch_brochure_text("") is None

    @patch("tools.adv_parser.requests.get")
    def test_403_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp
        assert fetch_brochure_text("12345") is None

    @patch("tools.adv_parser.requests.get")
    def test_404_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        assert fetch_brochure_text("12345") is None

    @patch("tools.adv_parser.requests.get")
    def test_html_response_returns_none(self, mock_get):
        """When the endpoint returns an SPA HTML page instead of a PDF."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.content = b"<!DOCTYPE html><html>...</html>"
        mock_get.return_value = mock_resp
        assert fetch_brochure_text("12345") is None

    @patch("tools.adv_parser._extract_pdf_text")
    @patch("tools.adv_parser.requests.get")
    def test_pdf_response_extracts_text(self, mock_get, mock_extract):
        """When the endpoint returns an actual PDF."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.content = b"%PDF-fake"
        mock_get.return_value = mock_resp
        mock_extract.return_value = "Item 4 Advisory Business\nWe manage money."

        result = fetch_brochure_text("12345")
        assert result == "Item 4 Advisory Business\nWe manage money."
        mock_extract.assert_called_once_with(b"%PDF-fake", "12345")

    @patch("tools.adv_parser.requests.get")
    def test_network_error_returns_none(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("fail")
        assert fetch_brochure_text("12345") is None


# ── split_brochure_into_chunks ───────────────────────────────────────────────

class TestSplitBrochureIntoChunks:
    """Tests for split_brochure_into_chunks()."""

    def test_empty_text_returns_empty(self):
        assert split_brochure_into_chunks("") == []

    def test_none_text_returns_empty(self):
        assert split_brochure_into_chunks(None) == []

    def test_splits_on_item_headers(self):
        text = (
            "Item 4 Advisory Business\n"
            "We provide investment management services to institutional clients.\n"
            "Item 5 Fees and Compensation\n"
            "Our standard fee is 1.5% of AUM, assessed quarterly in arrears.\n"
            "Item 8 Methods of Analysis\n"
            "We use fundamental analysis combined with quantitative models.\n"
        )
        chunks = split_brochure_into_chunks(text)
        assert len(chunks) == 3

    def test_chunk_has_source_and_label(self):
        text = (
            "Item 4 Advisory Business\n"
            "We provide investment management services to institutional clients.\n"
        )
        chunks = split_brochure_into_chunks(text)
        assert len(chunks) == 1
        assert "brochure:" in chunks[0]["source"]
        assert "Item 4" in chunks[0]["label"]

    def test_short_fragments_skipped(self):
        text = "Item 1\nA\n"
        chunks = split_brochure_into_chunks(text)
        assert len(chunks) == 0  # too short (< 50 chars)

    def test_content_capped_at_3000_chars(self):
        text = "Item 4 Advisory Business\n" + "x" * 5000 + "\n"
        chunks = split_brochure_into_chunks(text)
        assert len(chunks) == 1
        assert len(chunks[0]["content"]) <= 3000
