"""
Tests for tools/edgar_client.py — parsing and extraction logic.
HTTP calls are mocked.
"""

import pytest
from tools.edgar_client import extract_adv_summary


# ── extract_adv_summary ────────────────────────────────────────────────────────

class TestExtractAdvSummary:
    def _make_detail(self, **overrides):
        """Minimal iacontent matching real IAPD API field names."""
        base = {
            "basicInformation": {
                "firmName": "Test Capital Management LLC",
                "firmId": "123456",
                "iaSECNumberType": "801",
                "iaSECNumber": "99999",
                "iaScope": "Active",
                "advFilingDate": "2025-01-15",
            },
            "orgScopeStatusFlags": {
                "isSECRegistered": "Y",
                "isStateRegistered": "N",
                "isERARegistered": "N",
            },
            "iaFirmAddressDetails": {
                "officeAddress": {
                    "city": "New York",
                    "state": "NY",
                    "country": "US",
                    "postalCode": "10001",
                }
            },
            "noticeFilings": [],
            "brochures": [],
        }
        base.update(overrides)
        return base

    def test_extracts_firm_name(self):
        result = extract_adv_summary(self._make_detail())
        assert result["firm_name"] == "Test Capital Management LLC"

    def test_extracts_crd_from_firmid(self):
        result = extract_adv_summary(self._make_detail())
        assert result["crd_number"] == "123456"

    def test_extracts_sec_number(self):
        result = extract_adv_summary(self._make_detail())
        assert result["sec_number"] == "801-99999"

    def test_sec_registered_flag_true(self):
        result = extract_adv_summary(self._make_detail())
        assert result["is_sec_registered"] is True

    def test_state_registered_flag_false(self):
        result = extract_adv_summary(self._make_detail())
        assert result["is_state_registered"] is False

    def test_registration_status_from_iascope(self):
        result = extract_adv_summary(self._make_detail())
        assert result["registration_status"] == "Active"

    def test_city_and_state_from_office_address(self):
        result = extract_adv_summary(self._make_detail())
        assert result["city"] == "New York"
        assert result["state"] == "NY"

    def test_empty_detail_returns_empty_dict(self):
        result = extract_adv_summary({})
        assert result == {}

    def test_none_detail_returns_empty_dict(self):
        result = extract_adv_summary(None)
        assert result == {}

    def test_aum_is_always_null(self):
        """AUM is not available in IAPD API — should always be None."""
        result = extract_adv_summary(self._make_detail())
        assert result["aum_regulatory"] is None

    def test_key_personnel_is_always_empty(self):
        """Key personnel not available in IAPD API."""
        result = extract_adv_summary(self._make_detail())
        assert result["key_personnel"] == []

    def test_has_disclosures_none_without_search_hit(self):
        result = extract_adv_summary(self._make_detail())
        assert result["has_disclosures"] is None

    def test_has_disclosures_from_search_hit(self):
        result = extract_adv_summary(
            self._make_detail(),
            search_hit={"has_disclosures": True},
        )
        assert result["has_disclosures"] is True

    def test_notice_filing_states_extracted(self):
        detail = self._make_detail()
        detail["noticeFilings"] = [
            {"stateCode": "CA"},
            {"stateCode": "TX"},
        ]
        result = extract_adv_summary(detail)
        assert "CA" in result["notice_filing_states"]
        assert "TX" in result["notice_filing_states"]
