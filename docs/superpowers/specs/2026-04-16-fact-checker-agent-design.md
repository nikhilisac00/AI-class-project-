# Fact Checker Agent — Design Spec

**Date:** 2026-04-16
**Status:** Approved
**Purpose:** Post-pipeline verification agent that validates the full chain (raw data → agent outputs → memo) and flags discrepancies to increase IC memo trustworthiness.

---

## Problem

The memo generation agent is instructed not to hallucinate, but there is no programmatic verification that its claims match the underlying data. The existing reconciliation tool checks data sources against each other but does not check agent outputs or memo content against the data they were derived from.

## Approach: Hybrid (Deterministic + LLM)

- **Deterministic layer:** Python functions that extract and compare concrete facts (numbers, dates, statuses, flag counts) across pipeline layers. Fast, cheap, 100% reproducible.
- **LLM layer:** Single GPT-4o call that evaluates narrative accuracy — tone, omissions, and subtle misrepresentations that regex cannot catch.
- **Auto-retry:** If FAIL-level issues are found, the memo is re-generated with failures injected into the prompt (same pattern as `fund_analysis.py` and `risk_flagging.py` schema validation retries). Verification report is always shown regardless.

## Architecture

### Module: `agents/fact_checker.py`

Three public functions:

```python
def run_deterministic_checks(
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    scorecard: dict,
    memo_text: str,
) -> list[dict]:
    """Run ~12 deterministic checks. Returns list of check result dicts."""

def run_narrative_check(
    analysis: dict,
    risk_report: dict,
    memo_text: str,
    client: LLMClient,
) -> list[dict]:
    """Run LLM narrative verification. Returns list of check result dicts."""

def run(
    analysis: dict,
    risk_report: dict,
    raw_data: dict,
    scorecard: dict,
    memo_text: str,
    client: LLMClient,
) -> dict:
    """Orchestrator: runs both check types, computes trust score, returns report."""
```

### Output Schema

```json
{
    "trust_score": 92,
    "trust_label": "HIGH | MEDIUM | LOW",
    "checks": [
        {
            "check": "Risk tier matches",
            "layer": "cross_agent",
            "status": "PASS",
            "detail": "Memo states HIGH, risk_report says HIGH",
            "evidence": {"memo_value": "HIGH", "source_value": "HIGH"}
        }
    ],
    "summary": {
        "total": 15,
        "passed": 13,
        "warnings": 1,
        "failures": 1
    },
    "retry_triggered": false,
    "failures_fixed_on_retry": []
}
```

**Trust labels:**
- HIGH: score >= 85
- MEDIUM: score 60-84
- LOW: score < 60

**Trust score formula:**
```
FAIL = 0 points, WARN = 0.5, PASS = 1.0
trust_score = (sum of points / total checks) * 100
```

## Deterministic Checks (12 checks)

### Layer 1: Raw Data → Analysis (5 checks)

| # | Check | Method | Status Logic |
|---|-------|--------|-------------|
| 1 | Firm name match | Lowercase contains (LLM may abbreviate) | FAIL if no overlap |
| 2 | CRD number match | Exact string match | FAIL if mismatch |
| 3 | Registration status match | Exact match between `raw_data.adv_summary.registration_status` and `analysis.firm_overview.registration_status` | FAIL if mismatch, WARN if one is null |
| 4 | 13F portfolio value match | Parse USD strings, compare with 1% tolerance | FAIL if >1% divergence, WARN if one is null |
| 5 | Fund count consistency | Compare `analysis.funds_analysis.total_funds_found` vs `len(raw_data.fund_discovery.funds)` | WARN if >2 difference, PASS otherwise |

### Layer 2: Analysis + Risk → Memo (4 checks)

| # | Check | Method | Status Logic |
|---|-------|--------|-------------|
| 6 | Risk tier in memo | Search memo text for `risk_report.overall_risk_tier` | FAIL if tier string not found |
| 7 | HIGH flags in memo | For each HIGH flag, search memo for keywords from `finding` field | FAIL if any HIGH flag not referenced |
| 8 | Portfolio value in memo | Search memo for the portfolio value string from analysis | WARN if not found (may be legitimately absent) |
| 9 | Registration status in memo | Search memo for registration status string | WARN if not found |

### Layer 3: Cross-Agent Consistency (3 checks)

| # | Check | Method | Status Logic |
|---|-------|--------|-------------|
| 10 | Risk tier vs flag distribution | Count HIGH flags; LOW tier must have 0 HIGH flags, MEDIUM allows 1-2 | FAIL if LOW tier + any HIGH flags |
| 11 | Scorecard vs risk tier alignment | PROCEED + HIGH risk = suspicious, PASS + LOW risk = expected | WARN if directionally inconsistent |
| 12 | Holdings count consistency | Compare `analysis.13f_filings.holdings_count` vs `raw_data.adv_xml_data.thirteenf.holdings_count` | FAIL if mismatch when both present |

## LLM Narrative Check (1 GPT-4o call)

### Input

GPT-4o receives:
- The full memo text
- `risk_report` (overall tier, all flags, commentary)
- `analysis.firm_overview` (key facts the memo should reflect)

### Evaluation Criteria

1. Executive summary tone matches the actual risk picture (a HIGH-risk firm shouldn't have a reassuring summary)
2. No material flags omitted or minimized in prose (all HIGH/MEDIUM flags should be substantively addressed)
3. Null fields presented as "Not Disclosed" rather than silently omitted
4. No invented facts or embellished language beyond what the data supports

### Output

Returns 1-3 narrative findings, each as a check result dict with status PASS/WARN/FAIL. Narrative checks are weighted the same as deterministic checks in the trust score.

## Pipeline Integration

### Execution Flow

After `memo_agent.run()` returns the memo:

1. Run `fact_checker.run(analysis, risk_report, raw_data, scorecard, memo_text, client)`
2. If any check has status `FAIL`:
   - Build a retry prompt with the failure details appended
   - Re-generate memo via `memo_agent` with failures injected
   - Run `fact_checker.run()` again on the retried memo
   - Record which failures were fixed in `failures_fixed_on_retry`
   - Set `retry_triggered = true`
3. Return final memo + verification report

### Integration Points

- **`main.py`:** Run fact checker after memo generation, print trust score summary to CLI
- **`app.py`:** Run fact checker after memo generation, display verification UI in Memo tab

## UI: Memo Tab (Collapsible Verification Section)

At the top of the Memo tab, before the memo content:

1. **Trust score badge:** Colored pill (green >= 85, amber 60-84, red < 60) with numeric score and label
2. **One-line summary:** "13/15 checks passed · 1 warning · 1 failure"
3. **Collapsible expander** ("Verification Details"): Full check table with columns: Check | Layer | Status | Detail
4. **Retry note** (if applicable): "1 issue was auto-corrected on retry" with details of what changed

### Badge Colors

```
GREEN (#27ae60): trust_score >= 85 (HIGH)
AMBER (#e67e22): trust_score 60-84 (MEDIUM)
RED   (#c0392b): trust_score < 60  (LOW)
```

## Testing Strategy

- **Deterministic checks:** Unit tests with mock data for each of the 12 checks — PASS, WARN, and FAIL cases. Follow the pattern in `tests/test_adv_parser.py` (mock data, no live API calls).
- **Narrative check:** Mock the LLM client, verify correct prompt construction and response parsing.
- **Trust score calculation:** Test edge cases (all pass, all fail, mixed).
- **Integration:** Test the retry flow with a mock memo that has known failures.

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `agents/fact_checker.py` | Create | Fact checker agent with deterministic + LLM checks |
| `tests/test_fact_checker.py` | Create | Unit tests for all checks and scoring |
| `app.py` | Modify | Add verification UI to Memo tab, call fact checker after memo generation |
| `main.py` | Modify | Call fact checker after memo generation, print trust score to CLI |
