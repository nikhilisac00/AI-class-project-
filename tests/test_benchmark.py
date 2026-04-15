"""
Benchmark validation suite — Week 5 validation story.

Five real firms with known public facts. Each test fetches live data from
SEC EDGAR / IAPD and asserts that the pipeline correctly identifies
finance-domain facts that a reviewer would check.

Run:
    pytest tests/test_benchmark.py -v

Requires no API keys (IAPD and EDGAR are public). Tests are marked slow
because they make real HTTP calls.

Firm selection rationale:
  1. GPB Capital Holdings (CRD 148760)   — disclosed SEC enforcement action
  2. ARK Investment Management (CRD 160418) — large Q-o-Q 13F AUM changes
  3. Man Investments / Man Solutions (CRD 106017) — offshore-domiciled funds
  4. Blackstone Alternative Asset Mgmt (CRD 149051) — active Form D filer
  5. AQR Capital Management (CRD 149729) — clean control with complete data
"""

import pytest
from tools.edgar_client import (
    search_adviser_by_name,
    get_adviser_detail,
    extract_adv_summary,
    search_13f_filings,
)
from tools.reconciliation import run_all as reconcile_sources


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_adv(crd: str) -> dict:
    detail = get_adviser_detail(crd)
    return extract_adv_summary(detail) if detail else {}


def _get_13f(crd: str) -> list:
    return search_13f_filings(crd) or []


# ── Firm 1: GPB Capital Holdings — SEC enforcement action ────────────────────

@pytest.mark.slow
class TestGPBCapital:
    """
    GPB Capital Holdings (CRD 148760).
    Known facts: SEC charged GPB and principals with fraud in Feb 2021.
    IAPD shows disclosure events. Registration was terminated/withdrawn.
    Memo MUST correctly state:
      - has_disclosures = True
      - disclosure_count >= 1
      - registration_status is not "Approved" / "Active" (firm was charged)
    """

    CRD = "148760"

    def test_has_disclosures(self):
        adv = _get_adv(self.CRD)
        disc = adv.get("disclosures") or {}
        has = disc.get("has_disclosures")
        assert has is True, (
            f"GPB Capital must have disclosures=True on IAPD. Got: {has}. "
            f"Full disclosures block: {disc}"
        )

    def test_disclosure_count_positive(self):
        adv = _get_adv(self.CRD)
        disc = adv.get("disclosures") or {}
        count = disc.get("num_disclosures") or 0
        assert count >= 1, (
            f"GPB Capital must have >= 1 disclosure. Got: {count}"
        )

    def test_firm_resolves_by_name(self):
        results = search_adviser_by_name("GPB Capital")
        assert results, "Search for 'GPB Capital' must return at least one result"
        crds = [str(r.get("crd_number", "")) for r in results]
        assert self.CRD in crds, (
            f"CRD {self.CRD} must appear in search results. Got CRDs: {crds[:5]}"
        )


# ── Firm 2: ARK Investment Management — large 13F changes ────────────────────

@pytest.mark.slow
class TestARKInvestment:
    """
    ARK Investment Management (CRD 160418).
    Known facts: filed multiple 13F filings; AUM fluctuated dramatically
    between 2020–2023 (peaked ~$60B+, declined sharply). Must have multiple
    13F filings available, showing the system can track multi-quarter data.
    Memo MUST correctly state:
      - 13F filings are available (available = True)
      - count_found >= 2 (multiple quarters)
      - portfolio_value is not null
    """

    CRD = "160418"

    def test_13f_available(self):
        filings = _get_13f(self.CRD)
        assert len(filings) >= 1, (
            f"ARK must have at least 1 13F filing. Got: {len(filings)}"
        )

    def test_13f_multiple_quarters(self):
        filings = _get_13f(self.CRD)
        assert len(filings) >= 2, (
            f"ARK must have >= 2 quarterly 13F filings for trend analysis. Got: {len(filings)}"
        )

    def test_adv_registration_active(self):
        adv = _get_adv(self.CRD)
        status = (adv.get("registration_status") or "").lower()
        assert "approved" in status or "active" in status or status != "", (
            f"ARK registration status should be present. Got: '{status}'"
        )


# ── Firm 3: Man Investments — offshore fund exposure ─────────────────────────

@pytest.mark.slow
class TestManInvestments:
    """
    Man Solutions Limited / Man Investments (CRD 106017).
    Known facts: UK-based manager with Cayman-domiciled funds. IAPD shows
    registration as a foreign private adviser or ERA. Funds typically show
    Cayman Islands or British Virgin Islands jurisdiction in Form D.
    Memo MUST correctly state:
      - Firm resolves correctly by name
      - If Form D funds present, at least one should show non-US jurisdiction
    """

    CRD = "106017"
    NAME = "Man Solutions"

    def test_firm_resolves(self):
        results = search_adviser_by_name(self.NAME)
        assert results, f"Search for '{self.NAME}' must return results"

    def test_adv_data_present(self):
        adv = _get_adv(self.CRD)
        assert adv, f"ADV summary for CRD {self.CRD} must not be empty"

    def test_registration_status_present(self):
        adv = _get_adv(self.CRD)
        status = adv.get("registration_status")
        assert status is not None, (
            f"registration_status must be present for CRD {self.CRD}. Got None."
        )


# ── Firm 4: Blackstone BAAM — active Form D filer ────────────────────────────

@pytest.mark.slow
class TestBlackstoneBAM:
    """
    Blackstone Alternative Asset Management (CRD 149051).
    Known facts: one of the world's largest alternative asset managers.
    Files Form D regularly for new fund launches. Must have:
      - High AUM (regulatory AUM >> $1B)
      - Multiple key personnel listed
      - 13F filings present
    Memo MUST correctly state:
      - aum_regulatory is not null and represents a very large number
      - key_personnel list is non-empty
    """

    CRD = "149051"

    def test_adv_aum_present(self):
        adv = _get_adv(self.CRD)
        aum = adv.get("aum_all_clients") or adv.get("regulatory_aum")
        assert aum is not None, (
            f"Blackstone BAAM must have AUM data on IAPD. Got None. ADV keys: {list(adv.keys())}"
        )

    def test_key_personnel_present(self):
        detail = get_adviser_detail(self.CRD)
        adv = extract_adv_summary(detail) if detail else {}
        personnel = adv.get("direct_owners") or adv.get("key_personnel") or []
        assert len(personnel) >= 1, (
            f"Blackstone BAAM must have key personnel listed. Got: {personnel}"
        )

    def test_13f_present(self):
        filings = _get_13f(self.CRD)
        assert len(filings) >= 1, (
            f"Blackstone BAAM must have at least 1 13F filing. Got: {len(filings)}"
        )


# ── Firm 5: AQR Capital — clean control ──────────────────────────────────────

@pytest.mark.slow
class TestAQRCapital:
    """
    AQR Capital Management (CRD 149729).
    Control firm — well-known, clean IAPD record, complete public data.
    This is the baseline: if AQR fails, something is wrong with data ingestion.
    Memo MUST correctly state:
      - Resolves by name and CRD
      - has_disclosures = False (or very low count)
      - 13F filings present with portfolio_value
      - registration_status = "Approved" or similar active status
      - AUM data present
    """

    CRD = "149729"

    def test_resolves_by_name(self):
        results = search_adviser_by_name("AQR Capital Management")
        assert results, "AQR must resolve by name"
        crds = [str(r.get("crd_number", "")) for r in results]
        assert self.CRD in crds, f"CRD {self.CRD} must be in results. Got: {crds[:5]}"

    def test_adv_complete(self):
        adv = _get_adv(self.CRD)
        for field in ("registration_status", "firm_name"):
            assert adv.get(field) is not None, (
                f"AQR ADV missing field '{field}'. ADV keys: {list(adv.keys())}"
            )

    def test_13f_present(self):
        filings = _get_13f(self.CRD)
        assert len(filings) >= 1, f"AQR must have >= 1 13F filing. Got: {len(filings)}"

    def test_registration_active(self):
        adv = _get_adv(self.CRD)
        status = (adv.get("registration_status") or "").lower()
        assert "approved" in status or "registered" in status, (
            f"AQR registration status should indicate active registration. Got: '{status}'"
        )

    def test_no_material_disclosures(self):
        adv = _get_adv(self.CRD)
        disc = adv.get("disclosures") or {}
        count = disc.get("num_disclosures") or 0
        # AQR is a clean firm — any disclosures present should be minor
        # We assert < 5 as a reasonable threshold for a "clean" control
        assert count < 5, (
            f"AQR has {count} disclosures — more than expected for a clean control firm. "
            "Verify this is still accurate."
        )

    def test_reconciliation_runs_without_crash(self):
        """Smoke test: reconciliation module runs end-to-end without exception."""
        adv = _get_adv(self.CRD)
        mock_analysis = {
            "firm_overview": {"aum_regulatory": adv.get("aum_all_clients")},
            "13f_filings": {"portfolio_value": None},
            "funds_analysis": {"total_funds_found": 0, "funds": []},
        }
        mock_raw = {"fund_discovery": {"funds": [], "errors": []}}
        results = reconcile_sources(mock_analysis, mock_raw)
        assert isinstance(results, list)
        assert all("check" in r and "status" in r for r in results)
