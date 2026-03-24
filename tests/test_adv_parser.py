"""
Tests for tools/adv_parser.py — pure-function logic only.
No real HTTP calls; all external I/O is mocked.
"""

import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock
import pytest

from tools.adv_parser import (
    parse_iapd_disclosures,
    parse_brochure_metadata,
    _parse_13f_xml,
)


# ── parse_iapd_disclosures ─────────────────────────────────────────────────────

class TestParseIapdDisclosures:
    def test_empty_iacontent_returns_empty_list(self):
        assert parse_iapd_disclosures({}) == []

    def test_single_criminal_disclosure(self):
        iacontent = {
            "iaCriminalDisclosures": [{
                "disclosureDate": "2018-03-15",
                "disclosureType": "Felony",
                "disclosureResolution": "Dismissed",
            }]
        }
        result = parse_iapd_disclosures(iacontent)
        assert len(result) == 1
        assert result[0]["type"] == "Criminal"
        assert result[0]["date"] == "2018-03-15"
        assert result[0]["description"] == "Felony"
        assert result[0]["resolution"] == "Dismissed"

    def test_multiple_disclosure_types(self):
        iacontent = {
            "iaCriminalDisclosures": [{"disclosureDate": "2015-01-01"}],
            "iaRegulatoryDisclosures": [{"disclosureDate": "2019-06-01"}],
            "iaCivilDisclosures": [],  # empty list — should be skipped
        }
        result = parse_iapd_disclosures(iacontent)
        assert len(result) == 2

    def test_non_list_disclosure_value_is_skipped(self):
        # compilationData in real IAPD responses is sometimes a list not a dict
        iacontent = {
            "iaCriminalDisclosures": "not-a-list",
        }
        result = parse_iapd_disclosures(iacontent)
        assert result == []

    def test_disclosure_with_details(self):
        iacontent = {
            "iaRegulatoryDisclosures": [{
                "disclosureDate": "2020-09-01",
                "disclosureType": "SEC Order",
                "disclosureDetails": [
                    {"disclosureDetailType": "Sanction", "disclosureDetailValue": "$500K fine"},
                ],
            }]
        }
        result = parse_iapd_disclosures(iacontent)
        assert len(result) == 1
        assert result[0]["details"] == [{"label": "Sanction", "value": "$500K fine"}]


# ── parse_brochure_metadata ────────────────────────────────────────────────────

class TestParseBrochureMetadata:
    def test_empty_iacontent_returns_empty_dict(self):
        assert parse_brochure_metadata({}) == {}

    def test_no_brochuredetails_returns_empty(self):
        assert parse_brochure_metadata({"brochures": {}}) == {}

    def test_returns_most_recent_brochure(self):
        iacontent = {
            "brochures": {
                "brochuredetails": [
                    {"brochureName": "Old Brochure", "dateSubmitted": "2020-01-01", "brochureVersionID": "v1"},
                    {"brochureName": "New Brochure", "dateSubmitted": "2023-05-15", "brochureVersionID": "v2"},
                ]
            }
        }
        result = parse_brochure_metadata(iacontent)
        assert result["brochure_name"] == "New Brochure"
        assert result["brochure_date"] == "2023-05-15"
        assert result["brochure_version"] == "v2"

    def test_list_format_brochures(self):
        iacontent = {
            "brochures": [
                {"brochureName": "Brochure A", "dateSubmitted": "2022-11-01"},
            ]
        }
        result = parse_brochure_metadata(iacontent)
        assert result["brochure_name"] == "Brochure A"

    def test_note_always_present(self):
        iacontent = {
            "brochures": {
                "brochuredetails": [
                    {"brochureName": "Test", "dateSubmitted": "2023-01-01"},
                ]
            }
        }
        result = parse_brochure_metadata(iacontent)
        assert "note" in result
        assert "adviserinfo.sec.gov" in result["note"]


# ── _parse_13f_xml (value unit detection) ─────────────────────────────────────

MOCK_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission>
  <schemaVersion>{schema}</schemaVersion>
  <formData>
    <summaryPage>
      <tableEntryTotal>{entry_total}</tableEntryTotal>
      <tableValueTotal>{value_total}</tableValueTotal>
    </summaryPage>
  </formData>
</edgarSubmission>"""


class TestParse13fXml:
    def _mock_text(self, schema, entry_total, value_total):
        return MOCK_XML_TEMPLATE.format(
            schema=schema, entry_total=entry_total, value_total=value_total
        )

    def test_new_schema_x0202_uses_dollars_directly(self):
        """X0202 schema (2025+): value is already in dollars, no * 1000."""
        xml = self._mock_text("X0202", "100", "50000000000")  # $50B
        with patch("tools.adv_parser._text", return_value=xml):
            result = _parse_13f_xml("123", "0001234567-26-000001", "primary_doc.xml", "2025-12-31")
        assert result["portfolio_value_usd"] == 50_000_000_000
        assert result["portfolio_value_fmt"] == "$50.00B"
        assert result["holdings_count"] == 100

    def test_old_schema_uses_thousands(self):
        """Pre-X0202 schema: value is in thousands, multiply by 1000."""
        xml = self._mock_text("X0200", "50", "25000000")  # 25,000,000 * 1000 = $25B
        with patch("tools.adv_parser._text", return_value=xml):
            result = _parse_13f_xml("123", "0001234567-22-000001", "primary_doc.xml", "2022-09-30")
        assert result["portfolio_value_usd"] == 25_000_000_000
        assert result["portfolio_value_fmt"] == "$25.00B"

    def test_period_date_triggers_dollar_mode(self):
        """Even without schema tag, period >= 2024-12-31 uses dollars."""
        xml = self._mock_text("", "10", "1000000000")  # $1B in dollars
        with patch("tools.adv_parser._text", return_value=xml):
            result = _parse_13f_xml("123", "0001234567-25-000001", "primary_doc.xml", "2024-12-31")
        assert result["portfolio_value_usd"] == 1_000_000_000

    def test_trillion_formatting(self):
        xml = self._mock_text("X0202", "5000", "2500000000000")  # $2.5T
        with patch("tools.adv_parser._text", return_value=xml):
            result = _parse_13f_xml("123", "0001234567-26-000001", "primary_doc.xml", "2025-12-31")
        assert result["portfolio_value_fmt"] == "$2.50T"

    def test_million_formatting(self):
        xml = self._mock_text("X0202", "5", "250000000")  # $250M
        with patch("tools.adv_parser._text", return_value=xml):
            result = _parse_13f_xml("123", "0001234567-26-000001", "primary_doc.xml", "2025-12-31")
        assert result["portfolio_value_fmt"] == "$250.0M"

    def test_no_xml_returns_empty_dict(self):
        with patch("tools.adv_parser._text", return_value=None):
            result = _parse_13f_xml("123", "0001234567-26-000001", "primary_doc.xml", "2025-12-31")
        assert result == {}

    def test_malformed_xml_returns_empty_dict(self):
        with patch("tools.adv_parser._text", return_value="<broken xml"):
            result = _parse_13f_xml("123", "0001234567-26-000001", "primary_doc.xml", "2025-12-31")
        assert result == {}
