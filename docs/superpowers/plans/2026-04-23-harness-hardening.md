# Harness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add run-level tracing with atom/principal labels, a hard trust gate that produces DRAFT memos, schema validation on all remaining agents, and input validation at the pipeline entry point.

**Architecture:** Four additive harness layers on top of the existing sequential pipeline. No agent prompts or data flow changes. Each item is independently testable.

**Tech Stack:** Python 3.11+, pytest, existing TypedDict/validation patterns in `tools/schemas.py`

---

## Task 1: Run-Level Correlation ID + Atom/Principal Trace Fields

**Files:**
- Modify: `tools/trace.py`
- Test: `tests/test_trace.py` (new)

- [ ] **Step 1: Write failing tests for new trace fields**

```python
# tests/test_trace.py
"""Tests for tools/trace.py — run_id, step_id, atom/principal, agent I/O."""

import json
import os
import tempfile
from unittest.mock import patch

from tools.trace import (
    trace_llm_call,
    set_run_id,
    get_run_id,
    set_current_firm,
    _summarize,
)


def _read_last_record(log_dir: str) -> dict:
    """Read the last JSONL record from the trace log."""
    path = os.path.join(log_dir, "trace.jsonl")
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    return json.loads(lines[-1])


class TestRunId:
    """run_id context variable."""

    def test_set_and_get(self):
        set_run_id("test-uuid-123")
        assert get_run_id() == "test-uuid-123"

    def test_default_empty(self):
        # ContextVar default — may carry from prior test; just check it returns str
        assert isinstance(get_run_id(), str)


class TestSummarize:
    """_summarize truncation helper."""

    def test_short_string_unchanged(self):
        assert _summarize("hello") == "hello"

    def test_long_string_truncated(self):
        long = "x" * 1000
        result = _summarize(long, max_str_len=100)
        assert len(result) <= 103  # 100 + "..."
        assert result.endswith("...")

    def test_dict_values_truncated(self):
        data = {"key": "y" * 1000, "short": "ok"}
        result = _summarize(data, max_str_len=50)
        assert len(result["key"]) <= 53
        assert result["short"] == "ok"

    def test_list_replaced_with_summary(self):
        data = {"items": [1, 2, 3, 4, 5]}
        result = _summarize(data)
        assert result["items"] == "[list of 5 items]"

    def test_none_returns_none(self):
        assert _summarize(None) is None


class TestTraceRecord:
    """trace_llm_call writes records with new fields."""

    def test_record_contains_run_id_and_step_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TRACE_LOG_DIR": tmpdir}):
                set_run_id("run-abc")
                set_current_firm("TestFirm")
                trace_llm_call(
                    step="fund_analysis",
                    model="gpt-4o",
                    input_tokens=100,
                    output_tokens=50,
                    latency_ms=500,
                    success=True,
                    role_atom="data_analyst",
                    principal="IC_committee",
                    agent_input={"firm": "TestFirm"},
                    agent_output={"score": 8},
                )
                record = _read_last_record(tmpdir)

        assert record["run_id"] == "run-abc"
        assert isinstance(record["step_id"], int)
        assert record["role_atom"] == "data_analyst"
        assert record["principal"] == "IC_committee"
        assert record["agent_input"] == {"firm": "TestFirm"}
        assert record["agent_output"] == {"score": 8}

    def test_record_without_optional_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TRACE_LOG_DIR": tmpdir}):
                set_run_id("run-xyz")
                trace_llm_call(
                    step="ingestion",
                    model="gpt-4o",
                    input_tokens=10,
                    output_tokens=5,
                    latency_ms=100,
                    success=True,
                )
                record = _read_last_record(tmpdir)

        assert record["run_id"] == "run-xyz"
        assert record["role_atom"] is None
        assert record["principal"] is None
        assert record["agent_input"] is None
        assert record["agent_output"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_trace.py -v`
Expected: FAIL — `set_run_id`, `get_run_id`, `_summarize` not importable

- [ ] **Step 3: Implement trace.py changes**

In `tools/trace.py`, add after the existing `_current_firm` ContextVar (line 23):

```python
import itertools

_run_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_run_id", default=""
)
_step_counter: contextvars.ContextVar[itertools.count] = contextvars.ContextVar(
    "_step_counter",
)


def set_run_id(run_id: str) -> None:
    """Set the run identifier and reset step counter for this execution context."""
    _run_id.set(run_id)
    _step_counter.set(itertools.count())


def get_run_id() -> str:
    """Return the current run identifier (empty string if unset)."""
    return _run_id.get()


def _summarize(obj, max_str_len: int = 500):
    """Recursively summarize an object for trace logging.

    - Strings longer than max_str_len are truncated with '...'
    - Lists are replaced with '[list of N items]'
    - Dicts have their values recursively summarized
    - None passes through unchanged
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        if len(obj) > max_str_len:
            return obj[:max_str_len] + "..."
        return obj
    if isinstance(obj, dict):
        return {k: _summarize(v, max_str_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return f"[list of {len(obj)} items]"
    return obj
```

Update the `trace_llm_call` function signature to accept new params:

```python
def trace_llm_call(
    step: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    retry_count: int = 0,
    firm_id: Optional[str] = None,
    role_atom: Optional[str] = None,
    principal: Optional[str] = None,
    agent_input: Optional[dict] = None,
    agent_output: Optional[dict] = None,
) -> None:
```

Update the `record` dict inside `trace_llm_call` to include:

```python
    # Get step_id from counter (create counter if not set)
    try:
        counter = _step_counter.get()
    except LookupError:
        _step_counter.set(itertools.count())
        counter = _step_counter.get()
    step_id = next(counter)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": _run_id.get(),
        "step_id": step_id,
        "firm_id": firm_id or get_current_firm(),
        "step": step,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "estimated_cost_usd": estimate_cost(input_tokens, output_tokens),
        "success": success,
        "retry_count": retry_count,
        "role_atom": role_atom,
        "principal": principal,
        "agent_input": _summarize(agent_input) if agent_input else None,
        "agent_output": _summarize(agent_output) if agent_output else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_trace.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/trace.py tests/test_trace.py
git commit -m "Add run_id, step_id, atom/principal, and agent I/O to execution trace"
```

---

## Task 2: Wire Trace Fields Into Pipeline (main.py)

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add run_id generation and atom/principal mapping to main.py**

At the top of `main.py`, add to imports:

```python
import uuid
from tools.trace import set_run_id
```

(`set_current_firm` is already imported.)

Define the agent-to-atom/principal mapping after imports (before `main()`):

```python
# Harness seam map — which role atom and principal each agent serves
AGENT_ROLES = {
    "data_ingestion":    {"role_atom": "data_analyst",         "principal": "system_integrity"},
    "fund_analysis":     {"role_atom": "data_analyst",         "principal": "IC_committee"},
    "reconciliation":    {"role_atom": "compliance_checker",   "principal": "system_integrity"},
    "news_research":     {"role_atom": "research_synthesizer", "principal": "IC_committee"},
    "risk_flagging":     {"role_atom": "risk_assessor",        "principal": "LP_investor"},
    "memo_generation":   {"role_atom": "investment_advisor",   "principal": "IC_committee"},
    "ic_scorecard":      {"role_atom": "investment_advisor",   "principal": "IC_committee"},
    "fact_checker":      {"role_atom": "fact_verifier",        "principal": "compliance"},
    "comparables":       {"role_atom": "data_analyst",         "principal": "IC_committee"},
    "research_director": {"role_atom": "risk_assessor",        "principal": "LP_investor"},
}
```

At the top of `main()`, after `api_key = validate_env()`, add:

```python
    # Generate run-level correlation ID for trace
    run_id = str(uuid.uuid4())
    set_run_id(run_id)
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All existing tests still pass

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "Wire run_id and agent role mapping into CLI pipeline"
```

---

## Task 3: Input Validation

**Files:**
- Create: `tools/validation.py`
- Modify: `main.py`
- Test: `tests/test_validation.py` (new)

- [ ] **Step 1: Write failing tests for input validation**

```python
# tests/test_validation.py
"""Tests for tools/validation.py — firm name / CRD input validation."""

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation.py -v`
Expected: FAIL — `tools.validation` module not found

- [ ] **Step 3: Implement validation module**

```python
# tools/validation.py
"""Input validation for pipeline entry points."""

import re


# Characters allowed in firm name input
_ALLOWED_PATTERN = re.compile(r"^[a-zA-Z0-9 .,\'&()\-/]+$")


def validate_firm_input(value: str) -> str:
    """Validate and sanitize firm name or CRD input.

    Returns cleaned input string.
    Raises ValueError if input is invalid.
    """
    cleaned = value.strip()

    if not cleaned:
        raise ValueError("Firm name or CRD is required")

    if len(cleaned) > 200:
        raise ValueError("Input too long (max 200 characters)")

    # CRD validation: purely numeric input
    if cleaned.isdigit():
        if len(cleaned) > 10:
            raise ValueError(
                f"CRD number must be 1-10 digits, got {len(cleaned)}"
            )
        return cleaned

    # Firm name character validation
    if not _ALLOWED_PATTERN.match(cleaned):
        bad_chars = set(re.findall(r"[^a-zA-Z0-9 .,\'&()\-/]", cleaned))
        raise ValueError(
            f"Invalid characters in firm name: {bad_chars}"
        )

    return cleaned
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Wire validation into main.py**

Add import at top of `main.py`:

```python
from tools.validation import validate_firm_input
```

In `main()`, after `args = parser.parse_args()` (line 172) and before `api_key = validate_env()` (line 174), add:

```python
    try:
        args.firm = validate_firm_input(args.firm)
    except ValueError as exc:
        console.print(f"[bold red]Input error:[/] {exc}")
        sys.exit(1)
```

- [ ] **Step 6: Run all tests to verify no regressions**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/validation.py tests/test_validation.py main.py
git commit -m "Add input validation for firm name and CRD at pipeline entry"
```

---

## Task 4: Schema Validation + Retry for IC Scorecard

**Files:**
- Modify: `tools/schemas.py`
- Modify: `agents/ic_scorecard.py`
- Test: `tests/test_schemas_scorecard.py` (new)

- [ ] **Step 1: Write failing tests for scorecard validation**

```python
# tests/test_schemas_scorecard.py
"""Tests for ScorecardOutput validation in tools/schemas.py."""

from tools.schemas import validate_scorecard, coerce_scorecard


class TestValidateScorecard:
    """validate_scorecard returns errors for invalid output."""

    def test_valid_scorecard_no_errors(self):
        data = {
            "recommendation": "PROCEED",
            "confidence": "HIGH",
            "confidence_rationale": "Strong regulatory standing.",
            "recommendation_summary": "Firm is well positioned.",
            "scores": {
                "regulatory_compliance": {"score": 8, "rationale": "Clean record"},
                "data_availability": {"score": 7, "rationale": "Good coverage"},
                "key_person_risk": {"score": 6, "rationale": "Moderate concentration"},
                "fund_structure": {"score": 7, "rationale": "Standard terms"},
                "news_reputation": {"score": 8, "rationale": "Positive press"},
                "operational_maturity": {"score": 9, "rationale": "Long track record"},
            },
            "overall_score": 7.5,
            "reasons_to_proceed": ["Strong track record"],
            "reasons_to_pause": ["Key person concentration"],
            "minimum_diligence_items": [],
            "standard_lp_asks": [],
            "data_coverage_assessment": "HIGH",
            "data_coverage_note": "All key data available.",
        }
        assert validate_scorecard(data) == []

    def test_missing_recommendation(self):
        errors = validate_scorecard({"confidence": "HIGH"})
        assert any("recommendation" in e for e in errors)

    def test_invalid_recommendation_value(self):
        data = {"recommendation": "BUY", "confidence": "HIGH"}
        errors = validate_scorecard(data)
        assert any("recommendation" in e and "BUY" in e for e in errors)

    def test_invalid_confidence_value(self):
        data = {"recommendation": "PROCEED", "confidence": "VERY HIGH"}
        errors = validate_scorecard(data)
        assert any("confidence" in e for e in errors)

    def test_scores_must_be_dict(self):
        data = {"recommendation": "PROCEED", "confidence": "HIGH", "scores": "bad"}
        errors = validate_scorecard(data)
        assert any("scores" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_scorecard("string")
        assert len(errors) > 0


class TestCoerceScorecard:
    """coerce_scorecard fills defaults for missing fields."""

    def test_empty_dict_gets_defaults(self):
        result = coerce_scorecard({})
        assert result["recommendation"] == "REQUEST MORE INFO"
        assert result["confidence"] == "LOW"
        assert isinstance(result["reasons_to_proceed"], list)
        assert isinstance(result["reasons_to_pause"], list)

    def test_none_input(self):
        result = coerce_scorecard(None)
        assert isinstance(result, dict)
        assert "recommendation" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schemas_scorecard.py -v`
Expected: FAIL — `validate_scorecard`, `coerce_scorecard` not importable

- [ ] **Step 3: Add ScorecardOutput TypedDict, validator, and coercer to schemas.py**

At the end of `tools/schemas.py`, before the closing validation section, add:

```python
# ════════════════════════════════════════════════════════════════════════════════
# ic_scorecard output
# ════════════════════════════════════════════════════════════════════════════════

class ScoreDimension(TypedDict, total=False):
    score: int
    rationale: str


class ScorecardScores(TypedDict, total=False):
    regulatory_compliance: ScoreDimension
    data_availability: ScoreDimension
    key_person_risk: ScoreDimension
    fund_structure: ScoreDimension
    news_reputation: ScoreDimension
    operational_maturity: ScoreDimension


class DiligenceItem(TypedDict, total=False):
    item: str
    priority: str
    why: str


class ScorecardOutput(TypedDict, total=False):
    """Output of agents/ic_scorecard.py."""
    recommendation: str
    confidence: str
    confidence_rationale: str
    recommendation_summary: str
    scores: ScorecardScores
    overall_score: float
    reasons_to_proceed: List[str]
    reasons_to_pause: List[str]
    minimum_diligence_items: List[DiligenceItem]
    standard_lp_asks: List[str]
    data_coverage_assessment: str
    data_coverage_note: str
```

Add the coercer:

```python
def coerce_scorecard(data: Any) -> ScorecardOutput:
    """Normalise raw ic_scorecard LLM output into ScorecardOutput."""
    if not isinstance(data, dict):
        data = {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("recommendation",          "REQUEST MORE INFO")
    data.setdefault("confidence",              "LOW")
    data.setdefault("confidence_rationale",    "")
    data.setdefault("recommendation_summary",  "")
    data.setdefault("scores",                  {})
    data.setdefault("overall_score",           0)
    data.setdefault("reasons_to_proceed",      _ensure_list(data.get("reasons_to_proceed")))
    data.setdefault("reasons_to_pause",        _ensure_list(data.get("reasons_to_pause")))
    data.setdefault("minimum_diligence_items", _ensure_list(data.get("minimum_diligence_items")))
    data.setdefault("standard_lp_asks",        _ensure_list(data.get("standard_lp_asks")))
    data.setdefault("data_coverage_assessment", "LOW")
    data.setdefault("data_coverage_note",      "")

    return data  # type: ignore[return-value]
```

Add the validator:

```python
_VALID_RECOMMENDATIONS = {"PROCEED", "REQUEST MORE INFO", "PASS"}
_VALID_CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}
_VALID_DATA_COVERAGE = {"HIGH", "MEDIUM", "LOW"}
_SCORE_DIMENSIONS = {
    "regulatory_compliance", "data_availability", "key_person_risk",
    "fund_structure", "news_reputation", "operational_maturity",
}


def validate_scorecard(data: Any) -> list[str]:
    """Validate ic_scorecard agent output. Returns error strings; empty = valid."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    # Required keys
    for key in ("recommendation", "confidence"):
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    rec = data.get("recommendation")
    if rec is not None and rec not in _VALID_RECOMMENDATIONS:
        errors.append(
            f"recommendation must be one of {sorted(_VALID_RECOMMENDATIONS)}, got: '{rec}'"
        )

    conf = data.get("confidence")
    if conf is not None and conf not in _VALID_CONFIDENCES:
        errors.append(
            f"confidence must be one of {sorted(_VALID_CONFIDENCES)}, got: '{conf}'"
        )

    scores = data.get("scores")
    if scores is not None and not isinstance(scores, dict):
        errors.append("scores must be a dict")

    for key in ("reasons_to_proceed", "reasons_to_pause",
                "minimum_diligence_items", "standard_lp_asks"):
        val = data.get(key)
        if val is not None and not isinstance(val, list):
            errors.append(f"{key} must be a list")

    dc = data.get("data_coverage_assessment")
    if dc is not None and dc not in _VALID_DATA_COVERAGE:
        errors.append(
            f"data_coverage_assessment must be one of "
            f"{sorted(_VALID_DATA_COVERAGE)}, got: '{dc}'"
        )

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schemas_scorecard.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Wire validation into ic_scorecard.py**

Replace the last 3 lines of `agents/ic_scorecard.py` (lines 122-127):

```python
    from tools.schemas import validate_scorecard, format_validation_errors

    print(f"[IC Scorecard] Calling {client.provider} ({client.model})...")
    result = client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=16000,
    )

    errors = validate_scorecard(result)
    if errors:
        print(f"[IC Scorecard] Schema validation failed ({len(errors)} errors) — retrying...")
        retry_message = user_message + format_validation_errors(errors)
        result = client.complete_json(
            system=SYSTEM_PROMPT,
            user=retry_message,
            max_tokens=16000,
        )
        remaining = validate_scorecard(result)
        if remaining:
            print(f"[IC Scorecard] Retry still has {len(remaining)} schema errors: {remaining}")

    return result
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/schemas.py agents/ic_scorecard.py tests/test_schemas_scorecard.py
git commit -m "Add schema validation and retry to IC scorecard agent"
```

---

## Task 5: Schema Validation + Retry for Research Director

**Files:**
- Modify: `tools/schemas.py`
- Modify: `agents/research_director.py`
- Test: `tests/test_schemas_director.py` (new)

- [ ] **Step 1: Write failing tests for director validation**

```python
# tests/test_schemas_director.py
"""Tests for DirectorReviewOutput validation in tools/schemas.py."""

from tools.schemas import validate_director_review, coerce_director_review


class TestValidateDirectorReview:
    """validate_director_review returns errors for invalid output."""

    def test_valid_review_no_errors(self):
        data = {
            "verdict": "CONFIRMED",
            "original_recommendation": "PROCEED",
            "revised_recommendation": "PROCEED",
            "director_commentary": "The analysis is consistent with the data.",
            "inconsistencies": [],
            "missed_signals": [],
            "questions_for_gp": ["What is the fund's liquidity provision?"],
            "cleared_for_ic": True,
        }
        assert validate_director_review(data) == []

    def test_missing_verdict(self):
        errors = validate_director_review({"revised_recommendation": "PROCEED"})
        assert any("verdict" in e for e in errors)

    def test_invalid_verdict_value(self):
        data = {"verdict": "APPROVED", "revised_recommendation": "PROCEED"}
        errors = validate_director_review(data)
        assert any("verdict" in e and "APPROVED" in e for e in errors)

    def test_invalid_revised_recommendation(self):
        data = {"verdict": "CONFIRMED", "revised_recommendation": "BUY"}
        errors = validate_director_review(data)
        assert any("revised_recommendation" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_director_review([])
        assert len(errors) > 0


class TestCoerceDirectorReview:
    """coerce_director_review fills defaults for missing fields."""

    def test_empty_dict_gets_defaults(self):
        result = coerce_director_review({})
        assert result["verdict"] == "INCONCLUSIVE"
        assert isinstance(result["inconsistencies"], list)
        assert isinstance(result["missed_signals"], list)

    def test_none_input(self):
        result = coerce_director_review(None)
        assert isinstance(result, dict)
        assert "verdict" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schemas_director.py -v`
Expected: FAIL — `validate_director_review`, `coerce_director_review` not importable

- [ ] **Step 3: Add DirectorReviewOutput TypedDict, validator, and coercer to schemas.py**

Add to `tools/schemas.py`:

```python
# ════════════════════════════════════════════════════════════════════════════════
# research_director output
# ════════════════════════════════════════════════════════════════════════════════

class Inconsistency(TypedDict, total=False):
    finding: str
    field_a: str
    field_b: str
    implication: str


class MissedSignal(TypedDict, total=False):
    signal: str
    severity: Severity
    why_it_matters: str


class DirectorReviewOutput(TypedDict, total=False):
    """Output of agents/research_director.py."""
    verdict: str
    original_recommendation: str
    revised_recommendation: str
    director_commentary: str
    inconsistencies: List[Inconsistency]
    missed_signals: List[MissedSignal]
    questions_for_gp: List[str]
    cleared_for_ic: bool
```

Coercer:

```python
def coerce_director_review(data: Any) -> DirectorReviewOutput:
    """Normalise raw research_director LLM output into DirectorReviewOutput."""
    if not isinstance(data, dict):
        data = {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("verdict",                  "INCONCLUSIVE")
    data.setdefault("original_recommendation",  "")
    data.setdefault("revised_recommendation",   "REQUEST MORE INFO")
    data.setdefault("director_commentary",      "")
    data.setdefault("inconsistencies",          _ensure_list(data.get("inconsistencies")))
    data.setdefault("missed_signals",           _ensure_list(data.get("missed_signals")))
    data.setdefault("questions_for_gp",         _ensure_list(data.get("questions_for_gp")))
    data.setdefault("cleared_for_ic",           False)

    return data  # type: ignore[return-value]
```

Validator:

```python
_VALID_VERDICTS = {"CONFIRMED", "DOWNGRADED", "UPGRADED", "INCONCLUSIVE"}


def validate_director_review(data: Any) -> list[str]:
    """Validate research_director agent output. Returns error strings; empty = valid."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    for key in ("verdict", "revised_recommendation"):
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    verdict = data.get("verdict")
    if verdict is not None and verdict not in _VALID_VERDICTS:
        errors.append(
            f"verdict must be one of {sorted(_VALID_VERDICTS)}, got: '{verdict}'"
        )

    rev_rec = data.get("revised_recommendation")
    if rev_rec is not None and rev_rec not in _VALID_RECOMMENDATIONS:
        errors.append(
            f"revised_recommendation must be one of "
            f"{sorted(_VALID_RECOMMENDATIONS)}, got: '{rev_rec}'"
        )

    for key in ("inconsistencies", "missed_signals", "questions_for_gp"):
        val = data.get(key)
        if val is not None and not isinstance(val, list):
            errors.append(f"{key} must be a list")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schemas_director.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Wire validation into research_director.py**

Replace the last 4 lines of `agents/research_director.py` (lines 109-114):

```python
    from tools.schemas import validate_director_review, format_validation_errors

    print(f"[Research Director] Calling {client.provider} ({client.model})...")
    result = client.complete_json(
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=8000,
    )

    errors = validate_director_review(result)
    if errors:
        print(f"[Research Director] Schema validation failed ({len(errors)} errors) — retrying...")
        retry_message = user_message + format_validation_errors(errors)
        result = client.complete_json(
            system=SYSTEM_PROMPT,
            user=retry_message,
            max_tokens=8000,
        )
        remaining = validate_director_review(result)
        if remaining:
            print(f"[Research Director] Retry still has {len(remaining)} schema errors: {remaining}")

    return result
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/schemas.py agents/research_director.py tests/test_schemas_director.py
git commit -m "Add schema validation and retry to research director agent"
```

---

## Task 6: Schema Validation for Comparables (No LLM Retry)

**Files:**
- Modify: `tools/schemas.py`
- Modify: `agents/comparables.py`
- Test: `tests/test_schemas_comparables.py` (new)

Note: Comparables agent has no LLM call — it's pure IAPD search. Validation here ensures the output shape is consistent for downstream consumers, but there's no retry loop.

- [ ] **Step 1: Write failing tests for comparables validation**

```python
# tests/test_schemas_comparables.py
"""Tests for ComparablesOutput validation in tools/schemas.py."""

from tools.schemas import validate_comparables, coerce_comparables


class TestValidateComparables:
    """validate_comparables returns errors for invalid output."""

    def test_valid_output_no_errors(self):
        data = {
            "target": {"firm_name": "AQR", "is_target": True},
            "peers": [],
            "table": [{"firm_name": "AQR", "is_target": True}],
            "size_rank": None,
            "total_in_comparison": 1,
            "note": "Peers sourced from IAPD universe.",
        }
        assert validate_comparables(data) == []

    def test_missing_target(self):
        errors = validate_comparables({"peers": [], "table": []})
        assert any("target" in e for e in errors)

    def test_peers_must_be_list(self):
        data = {"target": {}, "peers": "bad", "table": []}
        errors = validate_comparables(data)
        assert any("peers" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_comparables(42)
        assert len(errors) > 0


class TestCoerceComparables:
    """coerce_comparables fills defaults for missing fields."""

    def test_empty_dict_gets_defaults(self):
        result = coerce_comparables({})
        assert isinstance(result["peers"], list)
        assert isinstance(result["table"], list)
        assert result["target"] == {}

    def test_none_input(self):
        result = coerce_comparables(None)
        assert isinstance(result, dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schemas_comparables.py -v`
Expected: FAIL — `validate_comparables`, `coerce_comparables` not importable

- [ ] **Step 3: Add ComparablesOutput TypedDict, validator, and coercer to schemas.py**

Add to `tools/schemas.py`:

```python
# ════════════════════════════════════════════════════════════════════════════════
# comparables output
# ════════════════════════════════════════════════════════════════════════════════

class ComparablePeerRow(TypedDict, total=False):
    firm_name: str
    is_target: bool
    crd: Optional[str]
    registration_status: Optional[str]
    is_sec_registered: Optional[bool]
    has_disclosures: Optional[bool]
    city: Optional[str]
    state: Optional[str]
    adv_filing_date: Optional[str]
    portfolio_value_fmt: Optional[str]
    portfolio_value_usd: Optional[float]
    holdings_count: Optional[int]


class ComparablesOutput(TypedDict, total=False):
    """Output of agents/comparables.py."""
    target: ComparablePeerRow
    peers: List[ComparablePeerRow]
    table: List[ComparablePeerRow]
    size_rank: Optional[int]
    total_in_comparison: int
    note: str
```

Coercer:

```python
def coerce_comparables(data: Any) -> ComparablesOutput:
    """Normalise comparables agent output into ComparablesOutput."""
    if not isinstance(data, dict):
        data = {}

    def _ensure_list(val: Any) -> list:
        return val if isinstance(val, list) else []

    data.setdefault("target",              data.get("target") or {})
    data.setdefault("peers",               _ensure_list(data.get("peers")))
    data.setdefault("table",               _ensure_list(data.get("table")))
    data.setdefault("size_rank",           None)
    data.setdefault("total_in_comparison", len(data.get("table", [])))
    data.setdefault("note",                "")

    return data  # type: ignore[return-value]
```

Validator:

```python
def validate_comparables(data: Any) -> list[str]:
    """Validate comparables agent output. Returns error strings; empty = valid."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    if "target" not in data:
        errors.append("Missing required key: 'target'")

    for key in ("peers", "table"):
        val = data.get(key)
        if val is not None and not isinstance(val, list):
            errors.append(f"{key} must be a list")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schemas_comparables.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Add validation call to comparables.py**

At the end of `agents/comparables.py`, in the `run()` function, before the final `return` statement (line 183), add validation logging (no retry since there's no LLM):

```python
    from tools.schemas import validate_comparables

    result = {
        "target":     target_row,
        "peers":      peers,
        "table":      table,
        "size_rank":  size_rank,
        "total_in_comparison": len(table),
        "note": (
            "Peers sourced from IAPD universe by strategy keyword + geography. "
            "13F portfolio value used as AUM proxy (US public equity managers only). "
            "This is a screening comparison — not a definitive peer set."
        ),
    }

    schema_errors = validate_comparables(result)
    if schema_errors:
        print(f"[Comparables] WARNING: output has {len(schema_errors)} schema issues: {schema_errors}")

    return result
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/schemas.py agents/comparables.py tests/test_schemas_comparables.py
git commit -m "Add schema validation to comparables agent output"
```

---

## Task 7: Schema Validation for News Research

**Files:**
- Modify: `agents/news_research.py`
- Test: `tests/test_schemas_news.py` (new)

Note: `NewsReport` TypedDict and `coerce_news_report` already exist in `tools/schemas.py`. We need to add a `validate_news_report` function and wire it into the agent.

- [ ] **Step 1: Write failing tests for news validation**

```python
# tests/test_schemas_news.py
"""Tests for validate_news_report in tools/schemas.py."""

from tools.schemas import validate_news_report


class TestValidateNewsReport:
    """validate_news_report returns errors for invalid output."""

    def test_valid_report_no_errors(self):
        data = {
            "firm_name": "AQR",
            "research_rounds": 2,
            "total_sources": 5,
            "news_flags": [],
            "news_summary": "No material news found.",
            "overall_news_risk": "CLEAN",
            "findings": [],
            "sources_consulted": [],
            "queries_used": ["AQR Capital enforcement"],
            "coverage_gaps": [],
            "errors": [],
        }
        assert validate_news_report(data) == []

    def test_missing_firm_name(self):
        errors = validate_news_report({"overall_news_risk": "LOW"})
        assert any("firm_name" in e for e in errors)

    def test_invalid_risk_level(self):
        data = {"firm_name": "Test", "overall_news_risk": "EXTREME"}
        errors = validate_news_report(data)
        assert any("overall_news_risk" in e for e in errors)

    def test_news_flags_must_be_list(self):
        data = {"firm_name": "Test", "news_flags": "bad"}
        errors = validate_news_report(data)
        assert any("news_flags" in e for e in errors)

    def test_not_a_dict(self):
        errors = validate_news_report(None)
        assert len(errors) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schemas_news.py -v`
Expected: FAIL — `validate_news_report` not importable

- [ ] **Step 3: Add validate_news_report to schemas.py**

Add to `tools/schemas.py` in the validation section:

```python
_VALID_NEWS_RISK = {"HIGH", "MEDIUM", "LOW", "CLEAN", "UNKNOWN"}


def validate_news_report(data: Any) -> list[str]:
    """Validate news_research agent output. Returns error strings; empty = valid."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Expected dict, got {type(data).__name__}"]

    if "firm_name" not in data:
        errors.append("Missing required key: 'firm_name'")

    risk = data.get("overall_news_risk")
    if risk is not None and risk not in _VALID_NEWS_RISK:
        errors.append(
            f"overall_news_risk must be one of {sorted(_VALID_NEWS_RISK)}, got: '{risk}'"
        )

    for key in ("news_flags", "findings", "sources_consulted",
                "queries_used", "coverage_gaps", "errors"):
        val = data.get(key)
        if val is not None and not isinstance(val, list):
            errors.append(f"{key} must be a list")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schemas_news.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Wire validation into news_research.py**

In `agents/news_research.py`, after the existing post-processing block (after line 288, `news_report["research_rounds"] = ...`), add:

```python
    from tools.schemas import validate_news_report

    schema_errors = validate_news_report(news_report)
    if schema_errors:
        print(f"[News Research Agent] WARNING: output has {len(schema_errors)} schema issues: {schema_errors}")
        news_report["errors"].extend(
            f"Schema: {e}" for e in schema_errors
        )
```

Note: No LLM retry here because the news agent uses `agent_loop_json` (tool-use loop), not a simple `complete_json`. The validation logs warnings and appends to the errors list for downstream visibility.

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/schemas.py agents/news_research.py tests/test_schemas_news.py
git commit -m "Add schema validation to news research agent output"
```

---

## Task 8: Hard Gate on LOW Trust Scores (DRAFT Memo)

**Files:**
- Modify: `main.py`
- Test: `tests/test_draft_gate.py` (new)

- [ ] **Step 1: Write failing tests for DRAFT gate logic**

```python
# tests/test_draft_gate.py
"""Tests for the DRAFT memo gate in main.py."""

from main import _build_draft_header, _is_trust_low


class TestIsTrustLow:
    """_is_trust_low checks trust_label from fact checker output."""

    def test_low_returns_true(self):
        assert _is_trust_low({"trust_label": "LOW", "trust_score": 25}) is True

    def test_medium_returns_false(self):
        assert _is_trust_low({"trust_label": "MEDIUM", "trust_score": 55}) is False

    def test_high_returns_false(self):
        assert _is_trust_low({"trust_label": "HIGH", "trust_score": 85}) is False

    def test_missing_label_returns_false(self):
        assert _is_trust_low({}) is False


class TestBuildDraftHeader:
    """_build_draft_header creates the warning block."""

    def test_contains_draft_warning(self):
        header = _build_draft_header(score=25, timestamp="2026-04-23T12:00:00")
        assert "DRAFT" in header
        assert "DO NOT DISTRIBUTE" in header
        assert "25" in header

    def test_contains_timestamp(self):
        header = _build_draft_header(score=30, timestamp="2026-04-23T15:30:00")
        assert "2026-04-23T15:30:00" in header
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_draft_gate.py -v`
Expected: FAIL — `_build_draft_header`, `_is_trust_low` not importable

- [ ] **Step 3: Add helper functions to main.py**

Add after the `_normalize_check_name` function (after line 68):

```python
def _is_trust_low(verification: dict) -> bool:
    """Return True if the fact checker rated trust as LOW."""
    return verification.get("trust_label") == "LOW"


def _build_draft_header(score: int, timestamp: str) -> str:
    """Build the warning header prepended to DRAFT memos."""
    return (
        "> **DRAFT — DO NOT DISTRIBUTE**\n"
        f"> This memo failed automated fact-checking "
        f"(trust score: {score}/100, label: LOW).\n"
        "> It requires manual review before IC submission.\n"
        f"> Generated: {timestamp}\n"
        "---\n\n"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_draft_gate.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Wire the DRAFT gate into main.py pipeline**

In `main.py`, after the fact-checker section (after line 388 — the retry_triggered print), replace the save/scorecard/director section with gated logic:

After the trust score print block (line 384), add the gate:

```python
    # ── DRAFT gate: refuse to serve LOW-trust memos as IC-ready ──────────
    if _is_trust_low(verification):
        console.print(
            "\n[bold red]DRAFT GATE:[/] Trust score is LOW — memo will be saved as DRAFT.\n"
            "IC Scorecard, Research Director, and Comparables will be skipped."
        )
        draft_ts = datetime.now().isoformat()
        memo = _build_draft_header(verification["trust_score"], draft_ts) + memo

        # Save as DRAFT
        base = Path(args.output_dir)
        base.mkdir(parents=True, exist_ok=True)
        draft_path = base / f"DRAFT_{ts}_{safe_name}_DD_MEMO.md"
        draft_path.write_text(memo, encoding="utf-8")

        # Still save raw data, analysis, risk report for review
        (base / f"{ts}_{safe_name}_raw_data.json").write_text(
            json.dumps(raw_data, indent=2, default=str), encoding="utf-8"
        )
        (base / f"{ts}_{safe_name}_analysis.json").write_text(
            json.dumps(analysis, indent=2, default=str), encoding="utf-8"
        )
        (base / f"{ts}_{safe_name}_risk_report.json").write_text(
            json.dumps(risk_report, indent=2, default=str), encoding="utf-8"
        )
        (base / f"{ts}_{safe_name}_verification.json").write_text(
            json.dumps(verification, indent=2, default=str), encoding="utf-8"
        )
        if news_report:
            (base / f"{ts}_{safe_name}_news_report.json").write_text(
                json.dumps(news_report, indent=2, default=str), encoding="utf-8"
            )

        console.print(Panel(
            f"[bold yellow]DRAFT memo saved.[/]\n"
            f"Path: [cyan]{draft_path}[/]\n"
            f"Trust: {verification['trust_score']}/100 (LOW)\n"
            f"Action: Manual review required before IC submission.",
            title="Draft — Not IC-Ready",
            expand=False,
        ))
        return  # Exit pipeline — do not run scorecard, director, comparables
```

The existing code from "Save outputs" through "Research Director" (lines 390-454) stays unchanged but now only runs when trust is not LOW (the `return` above exits early).

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_draft_gate.py
git commit -m "Add hard DRAFT gate on LOW trust score — skip IC/director/comparables"
```

---

## Task 9: Wire DRAFT Gate and Validation Into Streamlit (app.py)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add input validation to app.py**

Find the Streamlit run button handler. Around line 1024, where `from tools.trace import set_current_firm` is imported, add:

```python
        from tools.trace import set_current_firm, set_run_id
        from tools.validation import validate_firm_input
        import uuid
```

Before the pipeline starts (before the first `status_box.info` call for Step 1), add:

```python
        try:
            firm_input = validate_firm_input(firm_input)
        except ValueError as exc:
            st.error(f"Input error: {exc}")
            st.stop()

        run_id = str(uuid.uuid4())
        set_run_id(run_id)
```

- [ ] **Step 2: Add DRAFT gate to app.py**

After the fact-checker section in `app.py` (around line 1148, after `fact_check = re_check`), and before the scorecard step (line 1155), add:

```python
        # DRAFT gate: refuse to serve LOW-trust memos as IC-ready
        if fact_check.get("trust_label") == "LOW":
            status_box.error(
                "DRAFT GATE: Trust score is LOW — memo saved as DRAFT. "
                "IC Scorecard, Research Director, and Comparables skipped."
            )
            draft_ts = datetime.now().isoformat()
            draft_header = (
                "> **DRAFT — DO NOT DISTRIBUTE**\n"
                f"> This memo failed automated fact-checking "
                f"(trust score: {fact_check['trust_score']}/100, label: LOW).\n"
                "> It requires manual review before IC submission.\n"
                f"> Generated: {draft_ts}\n"
                "---\n\n"
            )
            memo = draft_header + memo

            st.session_state.pipeline_result = dict(
                raw_data=raw_data, analysis=analysis, risk_report=risk_report,
                memo=memo, scorecard={}, comparables={},
                director_review={}, pal_review=pal_review,
                news_report=news_report, firm_name=firm_name_resolved,
                fact_check=fact_check, is_draft=True,
            )
            st.session_state.pipeline_done = True
            progress_bar.progress(100, text="Done (DRAFT)")
            st.stop()
```

- [ ] **Step 3: Verify app.py is syntactically valid**

Run: `uv run python -c "import ast; ast.parse(open('app.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "Wire input validation and DRAFT trust gate into Streamlit UI"
```

---

## Task 10: Run Full Test Suite and Final Verification

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass, no regressions

- [ ] **Step 2: Verify imports work end-to-end**

Run: `uv run python -c "from tools.trace import set_run_id, get_run_id, _summarize; from tools.validation import validate_firm_input; from tools.schemas import validate_scorecard, validate_director_review, validate_comparables, validate_news_report; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Verify main.py parses cleanly**

Run: `uv run python -c "import ast; ast.parse(open('main.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit any remaining changes**

If any fixes were needed, commit them:

```bash
git add -A
git commit -m "Fix test suite issues from harness hardening implementation"
```
