"""Tests for the DRAFT memo gate in main.py."""

from main import _build_draft_header, _is_trust_low


class TestIsTrustLow:
    def test_low_returns_true(self):
        assert _is_trust_low({"trust_label": "LOW", "trust_score": 25}) is True

    def test_medium_returns_false(self):
        assert _is_trust_low({"trust_label": "MEDIUM", "trust_score": 55}) is False

    def test_high_returns_false(self):
        assert _is_trust_low({"trust_label": "HIGH", "trust_score": 85}) is False

    def test_missing_label_returns_false(self):
        assert _is_trust_low({}) is False


class TestBuildDraftHeader:
    def test_contains_draft_warning(self):
        header = _build_draft_header(score=25, timestamp="2026-04-23T12:00:00")
        assert "DRAFT" in header
        assert "DO NOT DISTRIBUTE" in header
        assert "25" in header

    def test_contains_timestamp(self):
        header = _build_draft_header(score=30, timestamp="2026-04-23T15:30:00")
        assert "2026-04-23T15:30:00" in header
