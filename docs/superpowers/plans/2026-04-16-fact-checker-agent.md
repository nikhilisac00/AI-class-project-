# Fact Checker Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hybrid deterministic + LLM fact checker agent that validates the full pipeline chain (raw data → agent outputs → memo) and surfaces a trust score with detailed check results.

**Architecture:** `agents/fact_checker.py` contains 12 deterministic Python checks and 1 GPT-4o narrative check. The `run()` orchestrator computes a trust score (0-100) and returns a structured verification report. On FAIL-level issues, the memo is re-generated with failures injected, then re-verified. Results display inline in the Memo tab (trust badge) and in the existing Fact Checker tab (detailed report).

**Tech Stack:** Python, pytest, OpenAI GPT-4o (via existing `tools/llm_client.py`), Streamlit

**Spec:** `docs/superpowers/specs/2026-04-16-fact-checker-agent-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `agents/fact_checker.py` | Create | 12 deterministic checks, 1 LLM narrative check, trust score calculator, orchestrator |
| `tests/test_fact_checker.py` | Create | Unit tests for all checks (PASS/WARN/FAIL cases), scoring, and orchestrator |
| `app.py` | Modify | Wire fact checker into pipeline (line ~1090), update Fact Checker tab (lines ~2451-2498), add trust badge to Memo tab (line ~2377) |
| `main.py` | Modify | Wire fact checker after memo generation (line ~248), print trust score summary |

---

### Task 1: Deterministic Checks — Raw Data → Analysis (5 checks)

**Files:**
- Create: `agents/fact_checker.py`
- Test: `tests/test_fact_checker.py`

- [ ] **Step 1: Write failing tests for the 5 raw-to-analysis checks**

```python
"""
Tests for agents/fact_checker.py — deterministic and narrative verification.
LLM calls are mocked; no live API calls.
"""

from unittest.mock import MagicMock

from agents.fact_checker import run_deterministic_checks


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_raw_data(
    firm_name: str = "AQR Capital Management",
    crd: str = "149729",
    reg_status: str = "Active",
    portfolio_value_fmt: str = "$5.00B",
    holdings_count: int = 200,
    fund_count: int = 3,
) -> dict:
    return {
        "adv_summary": {
            "firm_name": firm_name,
            "crd_number": crd,
            "registration_status": reg_status,
        },
        "adv_xml_data": {
            "thirteenf": {
                "portfolio_value_fmt": portfolio_value_fmt,
                "portfolio_value_usd": 5_000_000_000,
                "holdings_count": holdings_count,
            },
        },
        "fund_discovery": {
            "funds": [{"name": f"Fund {i}"} for i in range(fund_count)],
        },
        "errors": [],
    }


def _make_analysis(
    name: str = "AQR Capital Management",
    crd: str = "149729",
    reg_status: str = "Active",
    portfolio_value: str = "$5.00B",
    holdings_count: int = 200,
    total_funds: int = 3,
) -> dict:
    return {
        "firm_overview": {
            "name": name,
            "crd": crd,
            "registration_status": reg_status,
        },
        "13f_filings": {
            "available": True,
            "portfolio_value": portfolio_value,
            "holdings_count": holdings_count,
        },
        "funds_analysis": {
            "total_funds_found": total_funds,
        },
    }


def _make_risk_report(tier: str = "MEDIUM", flags: list = None) -> dict:
    if flags is None:
        flags = [
            {"category": "Regulatory", "severity": "MEDIUM",
             "finding": "Resolved fine from 2019", "evidence": "ADV"},
        ]
    return {
        "overall_risk_tier": tier,
        "flags": flags,
        "clean_items": ["Operations clean"],
        "critical_data_gaps": [],
        "overall_commentary": "Moderate risk profile.",
    }


def _make_scorecard(rec: str = "PROCEED WITH CAUTION") -> dict:
    return {
        "recommendation": rec,
        "confidence": "MEDIUM",
        "overall_score": 65,
    }


SAMPLE_MEMO = """# DUE DILIGENCE MEMO — AQR Capital Management

**Overall Risk Tier: MEDIUM**

AQR Capital Management (CRD: 149729) is an Active SEC-registered adviser.
13F portfolio value is $5.00B across 200 holdings.
The firm manages 3 private funds.

## Risk Flags
| Category | Severity | Finding |
|---|---|---|
| Regulatory | MEDIUM | Resolved fine from 2019 |
"""


# ── Layer 1: Raw → Analysis checks ───────────────────────────────────────────

class TestFirmNameCheck:
    def test_pass_exact_match(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        name_check = next(c for c in checks if c["check"] == "Firm name match")
        assert name_check["status"] == "PASS"

    def test_pass_abbreviation(self):
        checks = run_deterministic_checks(
            _make_analysis(name="AQR Capital"),
            _make_risk_report(),
            _make_raw_data(firm_name="AQR Capital Management LLC"),
            _make_scorecard(), SAMPLE_MEMO,
        )
        name_check = next(c for c in checks if c["check"] == "Firm name match")
        assert name_check["status"] == "PASS"

    def test_fail_mismatch(self):
        checks = run_deterministic_checks(
            _make_analysis(name="Totally Different Firm"),
            _make_risk_report(),
            _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        name_check = next(c for c in checks if c["check"] == "Firm name match")
        assert name_check["status"] == "FAIL"


class TestCrdCheck:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        crd_check = next(c for c in checks if c["check"] == "CRD number match")
        assert crd_check["status"] == "PASS"

    def test_fail_mismatch(self):
        checks = run_deterministic_checks(
            _make_analysis(crd="999999"),
            _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        crd_check = next(c for c in checks if c["check"] == "CRD number match")
        assert crd_check["status"] == "FAIL"


class TestRegistrationStatusRawToAnalysis:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        reg_check = next(c for c in checks
                         if c["check"] == "Registration status match"
                         and c["layer"] == "raw_to_analysis")
        assert reg_check["status"] == "PASS"

    def test_fail_mismatch(self):
        checks = run_deterministic_checks(
            _make_analysis(reg_status="Inactive"),
            _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        reg_check = next(c for c in checks
                         if c["check"] == "Registration status match"
                         and c["layer"] == "raw_to_analysis")
        assert reg_check["status"] == "FAIL"

    def test_warn_one_null(self):
        checks = run_deterministic_checks(
            _make_analysis(reg_status=None),
            _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        reg_check = next(c for c in checks
                         if c["check"] == "Registration status match"
                         and c["layer"] == "raw_to_analysis")
        assert reg_check["status"] == "WARN"


class TestPortfolioValueRawToAnalysis:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        pv_check = next(c for c in checks
                        if c["check"] == "13F portfolio value match")
        assert pv_check["status"] == "PASS"

    def test_fail_divergence(self):
        checks = run_deterministic_checks(
            _make_analysis(portfolio_value="$10.00B"),
            _make_risk_report(),
            _make_raw_data(portfolio_value_fmt="$5.00B"),
            _make_scorecard(), SAMPLE_MEMO,
        )
        pv_check = next(c for c in checks
                        if c["check"] == "13F portfolio value match")
        assert pv_check["status"] == "FAIL"

    def test_warn_one_null(self):
        checks = run_deterministic_checks(
            _make_analysis(portfolio_value=None),
            _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        pv_check = next(c for c in checks
                        if c["check"] == "13F portfolio value match")
        assert pv_check["status"] == "WARN"


class TestFundCountCheck:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(total_funds=3),
            _make_risk_report(),
            _make_raw_data(fund_count=3),
            _make_scorecard(), SAMPLE_MEMO,
        )
        fc_check = next(c for c in checks if c["check"] == "Fund count consistency")
        assert fc_check["status"] == "PASS"

    def test_warn_large_difference(self):
        checks = run_deterministic_checks(
            _make_analysis(total_funds=10),
            _make_risk_report(),
            _make_raw_data(fund_count=3),
            _make_scorecard(), SAMPLE_MEMO,
        )
        fc_check = next(c for c in checks if c["check"] == "Fund count consistency")
        assert fc_check["status"] == "WARN"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fact_checker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.fact_checker'`

- [ ] **Step 3: Implement the 5 raw-to-analysis checks**

Create `agents/fact_checker.py`:

```python
"""
Fact Checker Agent — Hybrid Verification
=========================================
Validates the full pipeline chain: raw data → agent outputs → memo.

Two layers:
  - Deterministic: Python checks for concrete facts (numbers, dates, statuses)
  - LLM narrative: GPT-4o evaluation of memo tone, omissions, and accuracy

Each check returns: {"check", "layer", "status", "detail", "evidence"}
Status values: PASS | WARN | FAIL
"""

from __future__ import annotations

import re
from tools.llm_client import LLMClient


# ── USD parsing (reuse pattern from tools/reconciliation.py) ─────────────────

def _parse_usd(value: str | None) -> float | None:
    """Parse a USD string like '$1.2B', '$450M', '$2,300,000' into a float."""
    if not value or not isinstance(value, str):
        return None
    s = value.upper().replace(",", "").replace("$", "").strip()
    multiplier = 1.0
    if s.endswith("T"):
        multiplier = 1e12
        s = s[:-1]
    elif s.endswith("B"):
        multiplier = 1e9
        s = s[:-1]
    elif s.endswith("M"):
        multiplier = 1e6
        s = s[:-1]
    elif s.endswith("K"):
        multiplier = 1e3
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        m = re.search(r"[\d.]+", s)
        if m:
            try:
                return float(m.group()) * multiplier
            except ValueError:
                pass
    return None


def _check(name: str, layer: str, status: str, detail: str,
           evidence: dict | None = None) -> dict:
    """Build a check result dict."""
    return {
        "check": name,
        "layer": layer,
        "status": status,
        "detail": detail,
        "evidence": evidence or {},
    }


# ── Layer 1: Raw Data → Analysis ─────────────────────────────────────────────

def _check_firm_name(analysis: dict, raw_data: dict) -> dict:
    """Check that firm name in analysis matches raw data."""
    raw_name = (raw_data.get("adv_summary") or {}).get("firm_name", "") or ""
    analysis_name = ((analysis.get("firm_overview") or {}).get("name", "")
                     or "")
    raw_lower = raw_name.lower().strip()
    analysis_lower = analysis_name.lower().strip()

    if not raw_lower or not analysis_lower:
        return _check("Firm name match", "raw_to_analysis", "WARN",
                       "One or both firm names are missing",
                       {"raw": raw_name, "analysis": analysis_name})

    if raw_lower == analysis_lower:
        return _check("Firm name match", "raw_to_analysis", "PASS",
                       f"Exact match: {raw_name}",
                       {"raw": raw_name, "analysis": analysis_name})

    # Fuzzy: check if shorter name is contained in longer
    if raw_lower in analysis_lower or analysis_lower in raw_lower:
        return _check("Firm name match", "raw_to_analysis", "PASS",
                       f"Partial match: '{analysis_name}' ⊂ '{raw_name}'",
                       {"raw": raw_name, "analysis": analysis_name})

    # Check word overlap
    raw_words = set(raw_lower.split())
    analysis_words = set(analysis_lower.split())
    overlap = raw_words & analysis_words
    filler = {"llc", "lp", "inc", "corp", "ltd", "the", "and", "of", "group"}
    meaningful_overlap = overlap - filler
    if meaningful_overlap:
        return _check("Firm name match", "raw_to_analysis", "PASS",
                       f"Word overlap: {meaningful_overlap}",
                       {"raw": raw_name, "analysis": analysis_name})

    return _check("Firm name match", "raw_to_analysis", "FAIL",
                   f"No match: raw='{raw_name}' vs analysis='{analysis_name}'",
                   {"raw": raw_name, "analysis": analysis_name})


def _check_crd(analysis: dict, raw_data: dict) -> dict:
    """Check that CRD number matches between raw data and analysis."""
    raw_crd = str((raw_data.get("adv_summary") or {}).get("crd_number", "")
                  or "")
    analysis_crd = str((analysis.get("firm_overview") or {}).get("crd", "")
                       or "")

    if not raw_crd or not analysis_crd:
        return _check("CRD number match", "raw_to_analysis", "WARN",
                       "One or both CRD numbers are missing",
                       {"raw": raw_crd, "analysis": analysis_crd})

    if raw_crd == analysis_crd:
        return _check("CRD number match", "raw_to_analysis", "PASS",
                       f"CRD match: {raw_crd}",
                       {"raw": raw_crd, "analysis": analysis_crd})

    return _check("CRD number match", "raw_to_analysis", "FAIL",
                   f"CRD mismatch: raw={raw_crd} vs analysis={analysis_crd}",
                   {"raw": raw_crd, "analysis": analysis_crd})


def _check_registration_status(analysis: dict, raw_data: dict) -> dict:
    """Check registration status matches between raw data and analysis."""
    raw_status = (raw_data.get("adv_summary") or {}).get(
        "registration_status")
    analysis_status = (analysis.get("firm_overview") or {}).get(
        "registration_status")

    if raw_status is None or analysis_status is None:
        return _check("Registration status match", "raw_to_analysis", "WARN",
                       "One or both registration statuses are null",
                       {"raw": raw_status, "analysis": analysis_status})

    if str(raw_status).lower() == str(analysis_status).lower():
        return _check("Registration status match", "raw_to_analysis", "PASS",
                       f"Status match: {raw_status}",
                       {"raw": raw_status, "analysis": analysis_status})

    return _check("Registration status match", "raw_to_analysis", "FAIL",
                   f"Status mismatch: raw='{raw_status}' vs "
                   f"analysis='{analysis_status}'",
                   {"raw": raw_status, "analysis": analysis_status})


def _check_portfolio_value(analysis: dict, raw_data: dict) -> dict:
    """Check 13F portfolio value matches between raw data and analysis."""
    raw_val_str = ((raw_data.get("adv_xml_data") or {}).get("thirteenf")
                   or {}).get("portfolio_value_fmt")
    analysis_val_str = ((analysis.get("13f_filings") or {}).get(
        "portfolio_value"))

    raw_val = _parse_usd(raw_val_str)
    analysis_val = _parse_usd(analysis_val_str)

    if raw_val is None and analysis_val is None:
        return _check("13F portfolio value match", "raw_to_analysis", "PASS",
                       "Both null — no 13F data available",
                       {"raw": raw_val_str, "analysis": analysis_val_str})

    if raw_val is None or analysis_val is None:
        return _check("13F portfolio value match", "raw_to_analysis", "WARN",
                       "One value is null",
                       {"raw": raw_val_str, "analysis": analysis_val_str})

    if raw_val == 0:
        return _check("13F portfolio value match", "raw_to_analysis", "WARN",
                       "Raw 13F value is zero",
                       {"raw": raw_val_str, "analysis": analysis_val_str})

    ratio = abs(analysis_val - raw_val) / raw_val
    if ratio <= 0.01:
        return _check("13F portfolio value match", "raw_to_analysis", "PASS",
                       f"Values match within 1%: {raw_val_str} vs "
                       f"{analysis_val_str}",
                       {"raw": raw_val_str, "analysis": analysis_val_str,
                        "divergence_pct": round(ratio * 100, 2)})

    return _check("13F portfolio value match", "raw_to_analysis", "FAIL",
                   f"Values diverge by {ratio:.1%}: raw={raw_val_str} vs "
                   f"analysis={analysis_val_str}",
                   {"raw": raw_val_str, "analysis": analysis_val_str,
                    "divergence_pct": round(ratio * 100, 2)})


def _check_fund_count(analysis: dict, raw_data: dict) -> dict:
    """Check fund count consistency between analysis and raw data."""
    fd = raw_data.get("fund_discovery") or {}
    raw_count = len(fd.get("funds") or [])
    analysis_count = (analysis.get("funds_analysis") or {}).get(
        "total_funds_found")

    if analysis_count is None:
        return _check("Fund count consistency", "raw_to_analysis", "WARN",
                       f"Analysis fund count is null; raw has {raw_count}",
                       {"raw": raw_count, "analysis": None})

    diff = abs(int(analysis_count) - raw_count)
    if diff <= 2:
        return _check("Fund count consistency", "raw_to_analysis", "PASS",
                       f"Counts align: analysis={analysis_count}, "
                       f"raw={raw_count}",
                       {"raw": raw_count, "analysis": int(analysis_count)})

    return _check("Fund count consistency", "raw_to_analysis", "WARN",
                   f"Count difference of {diff}: analysis={analysis_count}, "
                   f"raw={raw_count}",
                   {"raw": raw_count, "analysis": int(analysis_count)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fact_checker.py -v`
Expected: All Layer 1 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/fact_checker.py tests/test_fact_checker.py
git commit -m "Add fact checker agent: 5 raw-to-analysis deterministic checks"
```

---

### Task 2: Deterministic Checks — Analysis/Risk → Memo (4 checks)

**Files:**
- Modify: `agents/fact_checker.py`
- Modify: `tests/test_fact_checker.py`

- [ ] **Step 1: Write failing tests for the 4 memo checks**

Append to `tests/test_fact_checker.py`:

```python
# ── Layer 2: Analysis + Risk → Memo checks ───────────────────────────────────

class TestRiskTierInMemo:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="MEDIUM"),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks if c["check"] == "Risk tier in memo")
        assert check["status"] == "PASS"

    def test_fail_missing(self):
        memo_no_tier = "This memo has no risk tier mentioned anywhere."
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH"),
            _make_raw_data(), _make_scorecard(), memo_no_tier,
        )
        check = next(c for c in checks if c["check"] == "Risk tier in memo")
        assert check["status"] == "FAIL"


class TestHighFlagsInMemo:
    def test_pass_all_referenced(self):
        flags = [
            {"category": "Regulatory", "severity": "HIGH",
             "finding": "Criminal disclosure on IAPD", "evidence": "ADV"},
        ]
        memo_with_flag = SAMPLE_MEMO + "\nCriminal disclosure found on IAPD."
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(flags=flags),
            _make_raw_data(), _make_scorecard(), memo_with_flag,
        )
        check = next(c for c in checks
                     if c["check"] == "HIGH flags in memo")
        assert check["status"] == "PASS"

    def test_fail_flag_missing(self):
        flags = [
            {"category": "Regulatory", "severity": "HIGH",
             "finding": "Criminal disclosure on IAPD", "evidence": "ADV"},
        ]
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(flags=flags),
            _make_raw_data(), _make_scorecard(),
            "This memo mentions nothing about criminal issues.",
        )
        check = next(c for c in checks
                     if c["check"] == "HIGH flags in memo")
        assert check["status"] == "FAIL"

    def test_pass_no_high_flags(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "HIGH flags in memo")
        assert check["status"] == "PASS"


class TestPortfolioValueInMemo:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Portfolio value in memo")
        assert check["status"] == "PASS"

    def test_warn_missing(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), "A memo with no dollar figures.",
        )
        check = next(c for c in checks
                     if c["check"] == "Portfolio value in memo")
        assert check["status"] == "WARN"


class TestRegistrationStatusInMemo:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Registration status in memo")
        assert check["status"] == "PASS"

    def test_warn_missing(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), "A memo with no registration info.",
        )
        check = next(c for c in checks
                     if c["check"] == "Registration status in memo")
        assert check["status"] == "WARN"
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `pytest tests/test_fact_checker.py::TestRiskTierInMemo -v`
Expected: FAIL — check name not found (functions not implemented yet)

- [ ] **Step 3: Implement the 4 memo checks**

Add to `agents/fact_checker.py`:

```python
# ── Layer 2: Analysis + Risk → Memo ──────────────────────────────────────────

def _check_risk_tier_in_memo(risk_report: dict, memo_text: str) -> dict:
    """Check that the risk tier from risk_report appears in the memo."""
    tier = (risk_report or {}).get("overall_risk_tier", "")
    if not tier:
        return _check("Risk tier in memo", "analysis_to_memo", "WARN",
                       "No risk tier in risk report",
                       {"risk_tier": None})

    if tier.upper() in memo_text.upper():
        return _check("Risk tier in memo", "analysis_to_memo", "PASS",
                       f"Risk tier '{tier}' found in memo",
                       {"risk_tier": tier})

    return _check("Risk tier in memo", "analysis_to_memo", "FAIL",
                   f"Risk tier '{tier}' not found in memo text",
                   {"risk_tier": tier})


def _check_high_flags_in_memo(risk_report: dict, memo_text: str) -> dict:
    """Check that all HIGH-severity flags are referenced in the memo."""
    flags = (risk_report or {}).get("flags", [])
    high_flags = [f for f in flags if f.get("severity") == "HIGH"]

    if not high_flags:
        return _check("HIGH flags in memo", "analysis_to_memo", "PASS",
                       "No HIGH flags to check",
                       {"high_flag_count": 0})

    memo_lower = memo_text.lower()
    missing = []
    for flag in high_flags:
        finding = flag.get("finding", "")
        # Extract key words (3+ chars) from the finding
        words = [w for w in finding.lower().split() if len(w) >= 4]
        # Check if at least 2 key words appear in memo, or the category does
        category = flag.get("category", "").lower()
        word_hits = sum(1 for w in words if w in memo_lower)
        if word_hits < 2 and category not in memo_lower:
            missing.append(finding[:60])

    if not missing:
        return _check("HIGH flags in memo", "analysis_to_memo", "PASS",
                       f"All {len(high_flags)} HIGH flag(s) referenced in memo",
                       {"high_flag_count": len(high_flags)})

    return _check("HIGH flags in memo", "analysis_to_memo", "FAIL",
                   f"{len(missing)} HIGH flag(s) not found in memo: "
                   f"{missing}",
                   {"high_flag_count": len(high_flags),
                    "missing": missing})


def _check_portfolio_value_in_memo(analysis: dict, memo_text: str) -> dict:
    """Check that the portfolio value figure appears in the memo."""
    pv = (analysis.get("13f_filings") or {}).get("portfolio_value")
    if not pv:
        return _check("Portfolio value in memo", "analysis_to_memo", "PASS",
                       "No portfolio value in analysis to check",
                       {"portfolio_value": None})

    if str(pv) in memo_text:
        return _check("Portfolio value in memo", "analysis_to_memo", "PASS",
                       f"Portfolio value '{pv}' found in memo",
                       {"portfolio_value": pv})

    return _check("Portfolio value in memo", "analysis_to_memo", "WARN",
                   f"Portfolio value '{pv}' not found in memo text",
                   {"portfolio_value": pv})


def _check_registration_in_memo(analysis: dict, memo_text: str) -> dict:
    """Check that registration status appears in the memo."""
    status = (analysis.get("firm_overview") or {}).get("registration_status")
    if not status:
        return _check("Registration status in memo", "analysis_to_memo",
                       "PASS", "No registration status in analysis",
                       {"registration_status": None})

    if str(status).lower() in memo_text.lower():
        return _check("Registration status in memo", "analysis_to_memo",
                       "PASS",
                       f"Registration status '{status}' found in memo",
                       {"registration_status": status})

    return _check("Registration status in memo", "analysis_to_memo", "WARN",
                   f"Registration status '{status}' not found in memo",
                   {"registration_status": status})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fact_checker.py -v`
Expected: All Layer 1 + Layer 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/fact_checker.py tests/test_fact_checker.py
git commit -m "Add fact checker: 4 analysis-to-memo deterministic checks"
```

---

### Task 3: Deterministic Checks — Cross-Agent Consistency (3 checks)

**Files:**
- Modify: `agents/fact_checker.py`
- Modify: `tests/test_fact_checker.py`

- [ ] **Step 1: Write failing tests for the 3 cross-agent checks**

Append to `tests/test_fact_checker.py`:

```python
# ── Layer 3: Cross-agent consistency checks ──────────────────────────────────

class TestRiskTierVsFlags:
    def test_pass_medium_with_medium_flags(self):
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="MEDIUM"),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Risk tier vs flag distribution")
        assert check["status"] == "PASS"

    def test_fail_low_with_high_flags(self):
        flags = [{"category": "Regulatory", "severity": "HIGH",
                  "finding": "Fraud", "evidence": "ADV"}]
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="LOW", flags=flags),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Risk tier vs flag distribution")
        assert check["status"] == "FAIL"

    def test_pass_high_with_high_flags(self):
        flags = [{"category": "Regulatory", "severity": "HIGH",
                  "finding": "Fraud", "evidence": "ADV"}]
        checks = run_deterministic_checks(
            _make_analysis(), _make_risk_report(tier="HIGH", flags=flags),
            _make_raw_data(), _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Risk tier vs flag distribution")
        assert check["status"] == "PASS"


class TestScorecardVsRiskTier:
    def test_pass_consistent(self):
        checks = run_deterministic_checks(
            _make_analysis(),
            _make_risk_report(tier="MEDIUM"),
            _make_raw_data(),
            _make_scorecard(rec="PROCEED WITH CAUTION"),
            SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Scorecard vs risk tier alignment")
        assert check["status"] == "PASS"

    def test_warn_proceed_with_high_risk(self):
        checks = run_deterministic_checks(
            _make_analysis(),
            _make_risk_report(tier="HIGH"),
            _make_raw_data(),
            _make_scorecard(rec="PROCEED"),
            SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Scorecard vs risk tier alignment")
        assert check["status"] == "WARN"


class TestHoldingsCountConsistency:
    def test_pass(self):
        checks = run_deterministic_checks(
            _make_analysis(holdings_count=200),
            _make_risk_report(),
            _make_raw_data(holdings_count=200),
            _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Holdings count consistency")
        assert check["status"] == "PASS"

    def test_fail_mismatch(self):
        checks = run_deterministic_checks(
            _make_analysis(holdings_count=500),
            _make_risk_report(),
            _make_raw_data(holdings_count=200),
            _make_scorecard(), SAMPLE_MEMO,
        )
        check = next(c for c in checks
                     if c["check"] == "Holdings count consistency")
        assert check["status"] == "FAIL"
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `pytest tests/test_fact_checker.py::TestRiskTierVsFlags -v`
Expected: FAIL

- [ ] **Step 3: Implement the 3 cross-agent checks**

Add to `agents/fact_checker.py`:

```python
# ── Layer 3: Cross-Agent Consistency ──────────────────────────────────────────

def _check_risk_tier_vs_flags(risk_report: dict) -> dict:
    """Check that risk tier is consistent with flag severity distribution."""
    tier = (risk_report or {}).get("overall_risk_tier", "")
    flags = (risk_report or {}).get("flags", [])
    high_count = sum(1 for f in flags if f.get("severity") == "HIGH")

    if tier == "LOW" and high_count > 0:
        return _check("Risk tier vs flag distribution", "cross_agent", "FAIL",
                       f"Risk tier is LOW but {high_count} HIGH flag(s) exist",
                       {"tier": tier, "high_flags": high_count})

    if tier == "MEDIUM" and high_count > 2:
        return _check("Risk tier vs flag distribution", "cross_agent", "WARN",
                       f"Risk tier is MEDIUM but {high_count} HIGH flags "
                       f"(>2) may warrant HIGH",
                       {"tier": tier, "high_flags": high_count})

    return _check("Risk tier vs flag distribution", "cross_agent", "PASS",
                   f"Tier '{tier}' consistent with {high_count} HIGH flag(s)",
                   {"tier": tier, "high_flags": high_count})


def _check_scorecard_vs_risk(risk_report: dict, scorecard: dict) -> dict:
    """Check scorecard recommendation is directionally consistent with risk."""
    tier = (risk_report or {}).get("overall_risk_tier", "")
    rec = (scorecard or {}).get("recommendation", "")
    rec_upper = rec.upper()

    if tier == "HIGH" and "PROCEED" in rec_upper and "CAUTION" not in rec_upper:
        return _check("Scorecard vs risk tier alignment", "cross_agent",
                       "WARN",
                       f"Scorecard says '{rec}' but risk tier is HIGH",
                       {"tier": tier, "recommendation": rec})

    if tier == "LOW" and "PASS" in rec_upper:
        return _check("Scorecard vs risk tier alignment", "cross_agent",
                       "WARN",
                       f"Scorecard says '{rec}' but risk tier is only LOW",
                       {"tier": tier, "recommendation": rec})

    return _check("Scorecard vs risk tier alignment", "cross_agent", "PASS",
                   f"'{rec}' is consistent with '{tier}' risk tier",
                   {"tier": tier, "recommendation": rec})


def _check_holdings_count(analysis: dict, raw_data: dict) -> dict:
    """Check holdings count consistency between analysis and raw data."""
    raw_count = ((raw_data.get("adv_xml_data") or {}).get("thirteenf")
                 or {}).get("holdings_count")
    analysis_count = (analysis.get("13f_filings") or {}).get("holdings_count")

    if raw_count is None or analysis_count is None:
        return _check("Holdings count consistency", "cross_agent", "PASS",
                       "One or both holdings counts unavailable",
                       {"raw": raw_count, "analysis": analysis_count})

    if int(raw_count) == int(analysis_count):
        return _check("Holdings count consistency", "cross_agent", "PASS",
                       f"Holdings count match: {raw_count}",
                       {"raw": raw_count, "analysis": analysis_count})

    return _check("Holdings count consistency", "cross_agent", "FAIL",
                   f"Holdings count mismatch: raw={raw_count} vs "
                   f"analysis={analysis_count}",
                   {"raw": raw_count, "analysis": analysis_count})
```

- [ ] **Step 4: Wire all 12 checks into `run_deterministic_checks()`**

Add to `agents/fact_checker.py`:

```python
def run_deterministic_checks(
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    scorecard: dict,
    memo_text: str,
) -> list[dict]:
    """Run all deterministic checks across three layers.

    Returns:
        List of check result dicts.
    """
    return [
        # Layer 1: Raw → Analysis
        _check_firm_name(analysis, raw_data),
        _check_crd(analysis, raw_data),
        _check_registration_status(analysis, raw_data),
        _check_portfolio_value(analysis, raw_data),
        _check_fund_count(analysis, raw_data),
        # Layer 2: Analysis + Risk → Memo
        _check_risk_tier_in_memo(risk_report, memo_text),
        _check_high_flags_in_memo(risk_report, memo_text),
        _check_portfolio_value_in_memo(analysis, memo_text),
        _check_registration_in_memo(analysis, memo_text),
        # Layer 3: Cross-agent
        _check_risk_tier_vs_flags(risk_report),
        _check_scorecard_vs_risk(risk_report, scorecard),
        _check_holdings_count(analysis, raw_data),
    ]
```

- [ ] **Step 5: Run full test suite to verify all pass**

Run: `pytest tests/test_fact_checker.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add agents/fact_checker.py tests/test_fact_checker.py
git commit -m "Add fact checker: cross-agent checks and wire run_deterministic_checks"
```

---

### Task 4: LLM Narrative Check + Trust Score + Orchestrator

**Files:**
- Modify: `agents/fact_checker.py`
- Modify: `tests/test_fact_checker.py`

- [ ] **Step 1: Write failing tests for narrative check, scoring, and orchestrator**

Append to `tests/test_fact_checker.py`:

```python
from agents.fact_checker import (
    run_deterministic_checks,
    run_narrative_check,
    run,
    compute_trust_score,
)


# ── Narrative check ──────────────────────────────────────────────────────────

class TestNarrativeCheck:
    def _mock_client(self, response: dict = None) -> MagicMock:
        client = MagicMock()
        client.provider = "openai"
        client.model = "gpt-4o"
        client.complete_json.return_value = response or {
            "findings": [
                {
                    "status": "PASS",
                    "detail": "Executive summary accurately reflects MEDIUM risk.",
                },
            ]
        }
        return client

    def test_returns_check_list(self):
        client = self._mock_client()
        checks = run_narrative_check(
            _make_analysis(), _make_risk_report(), SAMPLE_MEMO, client,
        )
        assert isinstance(checks, list)
        assert len(checks) >= 1
        assert checks[0]["layer"] == "narrative"

    def test_calls_llm(self):
        client = self._mock_client()
        run_narrative_check(
            _make_analysis(), _make_risk_report(), SAMPLE_MEMO, client,
        )
        assert client.complete_json.called


# ── Trust score ──────────────────────────────────────────────────────────────

class TestTrustScore:
    def test_all_pass(self):
        checks = [{"status": "PASS"}] * 10
        score, label = compute_trust_score(checks)
        assert score == 100
        assert label == "HIGH"

    def test_all_fail(self):
        checks = [{"status": "FAIL"}] * 10
        score, label = compute_trust_score(checks)
        assert score == 0
        assert label == "LOW"

    def test_mixed(self):
        checks = ([{"status": "PASS"}] * 7
                   + [{"status": "WARN"}] * 2
                   + [{"status": "FAIL"}] * 1)
        score, label = compute_trust_score(checks)
        assert score == 80  # (7*1 + 2*0.5 + 1*0) / 10 * 100
        assert label == "MEDIUM"

    def test_empty(self):
        score, label = compute_trust_score([])
        assert score == 0
        assert label == "LOW"


# ── Orchestrator ─────────────────────────────────────────────────────────────

class TestRun:
    def _mock_client(self) -> MagicMock:
        client = MagicMock()
        client.provider = "openai"
        client.model = "gpt-4o"
        client.complete_json.return_value = {
            "findings": [
                {"status": "PASS", "detail": "Narrative is accurate."},
            ]
        }
        return client

    def test_returns_full_report(self):
        result = run(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO, self._mock_client(),
        )
        assert "trust_score" in result
        assert "trust_label" in result
        assert "checks" in result
        assert "summary" in result
        assert result["summary"]["total"] >= 12

    def test_trust_score_is_numeric(self):
        result = run(
            _make_analysis(), _make_risk_report(), _make_raw_data(),
            _make_scorecard(), SAMPLE_MEMO, self._mock_client(),
        )
        assert isinstance(result["trust_score"], (int, float))
        assert 0 <= result["trust_score"] <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fact_checker.py::TestNarrativeCheck -v`
Expected: FAIL — `ImportError: cannot import name 'run_narrative_check'`

- [ ] **Step 3: Implement narrative check, trust score, and orchestrator**

Add to `agents/fact_checker.py`:

```python
import json


NARRATIVE_SYSTEM_PROMPT = """You are a fact-checking editor at an institutional LP.
You review due diligence memos for accuracy against the underlying structured data.

Your job is to identify:
1. Claims in the memo that contradict the data
2. Material omissions (HIGH/MEDIUM flags not addressed)
3. Tone mismatches (reassuring summary for a HIGH-risk firm)
4. Invented facts not supported by any data field
5. Null fields that should say "Not Disclosed" but are silently omitted

For each finding, assess severity:
- PASS: The memo accurately reflects this aspect of the data
- WARN: Minor omission or imprecision, not materially misleading
- FAIL: Material misstatement, omission of HIGH flag, or invented fact"""


def run_narrative_check(
    analysis: dict,
    risk_report: dict,
    memo_text: str,
    client: LLMClient,
) -> list[dict]:
    """Run LLM narrative verification.

    Returns:
        List of check result dicts with layer="narrative".
    """
    user_message = f"""
Review this due diligence memo against the structured data it was generated from.

<memo>
{memo_text[:8000]}
</memo>

<risk_report>
Overall tier: {(risk_report or {}).get("overall_risk_tier")}
Commentary: {(risk_report or {}).get("overall_commentary")}
Flags: {json.dumps((risk_report or {}).get("flags", []), indent=2, default=str)}
</risk_report>

<firm_overview>
{json.dumps((analysis or {}).get("firm_overview", {}), indent=2, default=str)}
</firm_overview>

Return ONLY a JSON object:
{{
  "findings": [
    {{
      "status": "PASS | WARN | FAIL",
      "detail": "specific, factual description of what you found"
    }}
  ]
}}

Return 1-3 findings covering the most important accuracy checks.
"""

    try:
        result = client.complete_json(
            system=NARRATIVE_SYSTEM_PROMPT,
            user=user_message,
            max_tokens=2000,
        )
        findings = result.get("findings", [])
        return [
            _check(
                f"Narrative: {f.get('detail', 'check')[:50]}",
                "narrative",
                f.get("status", "WARN"),
                f.get("detail", ""),
            )
            for f in findings[:3]
        ]
    except Exception as exc:
        return [_check("Narrative check", "narrative", "WARN",
                        f"Narrative check failed: {exc}")]


def compute_trust_score(checks: list[dict]) -> tuple[int, str]:
    """Compute trust score from check results.

    Returns:
        Tuple of (score 0-100, label HIGH|MEDIUM|LOW).
    """
    if not checks:
        return 0, "LOW"

    points = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}
    total = sum(points.get(c.get("status", "FAIL"), 0) for c in checks)
    score = round(total / len(checks) * 100)

    if score >= 85:
        label = "HIGH"
    elif score >= 60:
        label = "MEDIUM"
    else:
        label = "LOW"

    return score, label


def run(
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    scorecard: dict,
    memo_text: str,
    client: LLMClient,
) -> dict:
    """Run full fact-checking pipeline.

    Runs deterministic checks + LLM narrative check, computes trust score.

    Returns:
        Structured verification report dict.
    """
    print("[Fact Checker] Running deterministic checks...")
    det_checks = run_deterministic_checks(
        analysis, risk_report, raw_data, scorecard, memo_text,
    )

    print(f"[Fact Checker] Calling {client.provider} ({client.model}) "
          f"for narrative check...")
    narr_checks = run_narrative_check(analysis, risk_report, memo_text, client)

    all_checks = det_checks + narr_checks
    trust_score, trust_label = compute_trust_score(all_checks)

    passed = sum(1 for c in all_checks if c["status"] == "PASS")
    warnings = sum(1 for c in all_checks if c["status"] == "WARN")
    failures = sum(1 for c in all_checks if c["status"] == "FAIL")

    print(f"[Fact Checker] Trust score: {trust_score} ({trust_label}) — "
          f"{passed} passed, {warnings} warnings, {failures} failures")

    return {
        "trust_score": trust_score,
        "trust_label": trust_label,
        "checks": all_checks,
        "summary": {
            "total": len(all_checks),
            "passed": passed,
            "warnings": warnings,
            "failures": failures,
        },
        "retry_triggered": False,
        "failures_fixed_on_retry": [],
    }
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/test_fact_checker.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run ruff check**

Run: `python -m ruff check agents/fact_checker.py tests/test_fact_checker.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add agents/fact_checker.py tests/test_fact_checker.py
git commit -m "Add fact checker: narrative check, trust score, and orchestrator"
```

---

### Task 5: Pipeline Integration — main.py

**Files:**
- Modify: `main.py:33-37` (imports), `main.py:242-248` (after memo generation)

- [ ] **Step 1: Add import and wire fact checker into CLI pipeline**

At `main.py` line 33, add import:

```python
import agents.fact_checker    as fact_checker_agent
```

After the memo generation block (line 248), before the timestamp line (line 251), add:

```python
    # ── Fact Checker ──────────────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Fact-checking memo (deterministic + narrative)...", total=None)
        verification = fact_checker_agent.run(
            analysis, risk_report, raw_data, scorecard, memo, client,
        )
        p.update(task, description="Fact check complete", completed=True)

    # Auto-retry memo if FAIL-level issues found
    if verification["summary"]["failures"] > 0:
        console.print(f"[yellow]Fact checker found {verification['summary']['failures']} "
                      f"failure(s) — re-generating memo...[/]")
        failure_details = "\n".join(
            f"- FAIL: {c['detail']}" for c in verification["checks"]
            if c["status"] == "FAIL"
        )
        memo = memo_agent.run(
            analysis, risk_report, raw_data, client,
            news_report=news_report,
        )
        re_verification = fact_checker_agent.run(
            analysis, risk_report, raw_data, scorecard, memo, client,
        )
        fixed = [
            c["check"] for c in verification["checks"]
            if c["status"] == "FAIL"
            and next((r for r in re_verification["checks"]
                       if r["check"] == c["check"]), {}).get("status") != "FAIL"
        ]
        re_verification["retry_triggered"] = True
        re_verification["failures_fixed_on_retry"] = fixed
        verification = re_verification

    # Print trust score
    ts_color = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}.get(
        verification["trust_label"], "white")
    console.print(
        f"\n[bold {ts_color}]Trust Score: {verification['trust_score']}/100 "
        f"({verification['trust_label']})[/] — "
        f"{verification['summary']['passed']} passed, "
        f"{verification['summary']['warnings']} warnings, "
        f"{verification['summary']['failures']} failures"
    )
    if verification.get("retry_triggered"):
        console.print(f"[dim]Auto-retry fixed: {verification['failures_fixed_on_retry']}[/]")
```

Note: The `scorecard` variable is used in the fact checker call but is defined later in main.py (line 258). Move the fact checker call to after the scorecard generation. Insert the fact checker block after line 261 (`scorecard = scorecard_agent.run(...)`) and after the scorecard console output (line 269).

- [ ] **Step 2: Run CLI with a test firm to verify it works**

Run: `python main.py "AQR Capital Management" --no-news`
Expected: Trust score printed after memo generation, no crashes

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "Wire fact checker agent into CLI pipeline with auto-retry"
```

---

### Task 6: Pipeline Integration — app.py

**Files:**
- Modify: `app.py:476-486` (imports)
- Modify: `app.py:1088-1121` (pipeline, wire fact checker after memo)
- Modify: `app.py:2377-2449` (Memo tab, add trust badge)
- Modify: `app.py:2451-2498` (Fact Checker tab, replace with new schema)
- Modify: `app.py:1570-1571` (badge in tab header)

- [ ] **Step 1: Add import**

At `app.py` line 486 (after portfolio_fit import), add:

```python
import agents.fact_checker      as fact_checker_agent  # noqa: E402
```

- [ ] **Step 2: Wire fact checker into pipeline**

Replace `app.py` line 1090 (`fact_check = None`) with:

```python
        status_box.info("⏳ Step 5b — Fact-checking memo (deterministic + narrative)...")
        fact_check = fact_checker_agent.run(
            analysis, risk_report, raw_data,
            scorecard if 'scorecard' in dir() else {},
            memo, client,
        )
        if fact_check["summary"]["failures"] > 0:
            status_box.warning(
                f"Fact checker found {fact_check['summary']['failures']} "
                f"issue(s) — re-generating memo..."
            )
            memo = memo_agent.run(analysis, risk_report, raw_data, client,
                                  news_report=news_report)
            re_check = fact_checker_agent.run(
                analysis, risk_report, raw_data, {}, memo, client,
            )
            fixed = [
                c["check"] for c in fact_check["checks"]
                if c["status"] == "FAIL"
                and next((r for r in re_check["checks"]
                           if r["check"] == c["check"]),
                         {}).get("status") != "FAIL"
            ]
            re_check["retry_triggered"] = True
            re_check["failures_fixed_on_retry"] = fixed
            fact_check = re_check
        step[0] += 1
        progress_bar.progress(_pct(step[0]), text=(
            f"Fact check: {fact_check['trust_score']}/100 "
            f"({fact_check['trust_label']})"
        ))
```

- [ ] **Step 3: Update the Fact Checker tab badge**

Replace `app.py` lines 1570-1571 with:

```python
    _fc_score     = (fact_check or {}).get("trust_score", 0)
    _fc_label     = (fact_check or {}).get("trust_label", "")
    _fc_badge     = (" ✅" if _fc_label == "HIGH"
                     else (" ⚠️" if _fc_label == "MEDIUM"
                           else (" 🔴" if _fc_label == "LOW" else "")))
```

- [ ] **Step 4: Add trust badge to Memo tab**

After the download bar closing `</div>` tag (line 2438) and before the memo preview `<div>` (line 2441), insert:

```python
            # ── Trust badge ──────────────────────────────────────────────
            if fact_check and fact_check.get("trust_score") is not None:
                _ts = fact_check["trust_score"]
                _tl = fact_check.get("trust_label", "")
                _tc = ("#27ae60" if _ts >= 85 else
                       ("#e67e22" if _ts >= 60 else "#c0392b"))
                _s = fact_check.get("summary", {})
                st.markdown(
                    f'<div style="background:{_tc}18;border:1px solid {_tc}40;'
                    f'border-radius:8px;padding:10px 16px;margin-bottom:14px;'
                    f'display:flex;align-items:center;gap:14px">'
                    f'<span style="background:{_tc};color:#fff;font-weight:800;'
                    f'font-size:1.1rem;padding:6px 14px;border-radius:20px">'
                    f'{_ts}</span>'
                    f'<span style="color:{_tc};font-weight:700;font-size:0.95rem">'
                    f'Trust: {_tl}</span>'
                    f'<span style="color:#8fa3bb;font-size:0.82rem">'
                    f'{_s.get("passed",0)}/{_s.get("total",0)} checks passed'
                    f' · {_s.get("warnings",0)} warnings'
                    f' · {_s.get("failures",0)} failures</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if fact_check.get("retry_triggered"):
                    fixed = fact_check.get("failures_fixed_on_retry", [])
                    st.caption(
                        f"Auto-retry corrected {len(fixed)} issue(s): "
                        + ", ".join(fixed)
                    )
```

- [ ] **Step 5: Replace Fact Checker tab content with new schema**

Replace `app.py` lines 2451-2498 (the entire `with tab_fact_check:` block) with:

```python
    # ─ Fact Checker ──────────────────────────────────────────────────────
    with tab_fact_check:
        if fact_check and fact_check.get("checks"):
            _ts = fact_check["trust_score"]
            _tl = fact_check["trust_label"]
            _tc = ("#27ae60" if _ts >= 85 else
                   ("#e67e22" if _ts >= 60 else "#c0392b"))
            _s = fact_check["summary"]

            # Score banner
            st.markdown(
                f'<div style="background:{_tc}18;border:1px solid {_tc}40;'
                f'border-radius:10px;padding:18px 24px;margin-bottom:16px">'
                f'<div style="display:flex;align-items:center;gap:16px">'
                f'<span style="background:{_tc};color:#fff;font-weight:900;'
                f'font-size:1.5rem;padding:10px 22px;border-radius:24px">'
                f'{_ts}</span>'
                f'<div><div style="color:{_tc};font-weight:700;'
                f'font-size:1.1rem">Trust: {_tl}</div>'
                f'<div style="color:#8fa3bb;font-size:0.85rem">'
                f'{_s["passed"]} passed · {_s["warnings"]} warnings · '
                f'{_s["failures"]} failures '
                f'(out of {_s["total"]} checks)</div>'
                f'</div></div></div>',
                unsafe_allow_html=True,
            )

            if fact_check.get("retry_triggered"):
                fixed = fact_check.get("failures_fixed_on_retry", [])
                st.info(
                    f"Auto-retry corrected {len(fixed)} issue(s): "
                    + ", ".join(fixed)
                )

            # Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Checks", _s["total"])
            m2.metric("Passed", _s["passed"])
            m3.metric("Warnings", _s["warnings"])
            m4.metric("Failures", _s["failures"])

            # Check table by layer
            import pandas as pd
            layer_order = ["raw_to_analysis", "analysis_to_memo",
                           "cross_agent", "narrative"]
            layer_labels = {
                "raw_to_analysis": "Raw Data → Analysis",
                "analysis_to_memo": "Analysis → Memo",
                "cross_agent": "Cross-Agent Consistency",
                "narrative": "Narrative Accuracy (LLM)",
            }
            status_icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}

            for layer in layer_order:
                layer_checks = [c for c in fact_check["checks"]
                                if c.get("layer") == layer]
                if not layer_checks:
                    continue
                st.markdown(f"**{layer_labels.get(layer, layer)}**")
                df = pd.DataFrame([{
                    "Status": status_icon.get(c["status"], c["status"]),
                    "Check": c["check"],
                    "Detail": c["detail"],
                } for c in layer_checks])
                st.dataframe(df, use_container_width=True, hide_index=True)

            # Evidence expander
            with st.expander("Raw Check Evidence", expanded=False):
                st.json(fact_check["checks"])
        else:
            st.info("Fact check not available for this analysis.")
```

- [ ] **Step 6: Run ruff check**

Run: `python -m ruff check app.py agents/fact_checker.py`
Expected: All checks passed

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "Wire fact checker into Streamlit UI with trust badge and detailed tab"
```

---

### Task 7: Final Verification

**Files:** All modified files

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/test_benchmark.py`
Expected: All tests pass (existing + new fact checker tests)

- [ ] **Step 2: Run ruff on all modified files**

Run: `python -m ruff check agents/fact_checker.py tests/test_fact_checker.py app.py main.py`
Expected: All checks passed

- [ ] **Step 3: Commit and push**

```bash
git add -A
git commit -m "Fact checker agent: hybrid deterministic + LLM verification with auto-retry"
git push origin main
```
