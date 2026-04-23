# Harness Hardening: Tracing, Trust Gate, Validation, Input Safety

## Motivation

The current system is a sequential multi-agent pipeline producing IC-grade due diligence memos. Mapping it against the AI Harness framework exposes four gaps: incomplete execution tracing (no run-level correlation or agent I/O logging), soft guardrails (LOW-trust memos still served), inconsistent output validation (only 2 of 6+ agents have schema validation), and no input sanitization at the entry point. This spec addresses all four.

---

## Item 1: Run-Level Correlation ID + Full I/O Tracing

### Problem

The existing `tools/trace.py` logs per-LLM-call metadata (tokens, cost, latency) but does not:
- Correlate calls to a single pipeline run
- Record agent inputs or outputs
- Provide sequential ordering within a run

This means you cannot reconstruct which agent produced which claim, or replay a run for audit.

### Design

**New context variable:** `run_id` — a UUID4 string, set once at pipeline start. Uses `contextvars.ContextVar` (same pattern as existing `firm_id`).

**New context variable:** `step_counter` — an `itertools.count` instance stored in a `ContextVar`, incremented each time `log_step()` is called. Provides deterministic ordering.

**Extended `log_step()` signature:**
```python
def log_step(
    step: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    success: bool,
    retry_count: int = 0,
    agent_input: dict | None = None,   # NEW
    agent_output: dict | None = None,  # NEW
) -> None:
```

**New fields in JSONL record:**
- `run_id`: str (UUID4)
- `step_id`: int (sequential per run)
- `agent_input`: dict or null — truncated summary of what was passed to the agent (keys only for large dicts, first 500 chars for strings)
- `agent_output`: dict or null — truncated summary of agent return value (same truncation rules)

**Truncation helper:** `_summarize(obj, max_str_len=500) -> dict | str | None` — recursively walks dicts, truncates string values, replaces lists with `"[list of N items]"`. Prevents trace bloat from large raw_data payloads.

**Integration points:**
- `main.py`: Generate `run_id` at top of `run_pipeline()`, set context var. Pass `agent_input`/`agent_output` to `log_step()` after each agent call.
- `app.py`: Same — generate `run_id` at top of Streamlit run.
- `tools/trace.py`: Add `run_id` and `step_counter` ContextVars. Update `log_step()` and `_build_record()`.

### Files touched
- `tools/trace.py`
- `main.py`
- `app.py`

---

## Item 2: Hard Gate on LOW Trust Scores (DRAFT Memo)

### Problem

If the fact-checker returns `trust_label: "LOW"`, the memo is still served as IC-ready. Downstream agents (IC scorecard, research director) evaluate unreliable work.

### Design

**After fact-checker completes (including retry):**

```
if trust_label == "LOW":
    1. Prepend warning header to memo text
    2. Save as DRAFT_{timestamp}_{firm}.md
    3. Skip IC scorecard, research director, comparables
    4. Log WARNING
    5. Return early with draft status
else:
    Proceed normally (save as {timestamp}_{firm}_memo.md)
```

**Warning header prepended to DRAFT memos:**
```markdown
> **DRAFT — DO NOT DISTRIBUTE**
> This memo failed automated fact-checking (trust score: {score}/100, label: LOW).
> It requires manual review before IC submission.
> Generated: {timestamp}
---
```

**Streamlit behavior:** Same logic. UI shows a red warning banner instead of the normal success message. Memo is still downloadable but labeled as DRAFT.

**What gets skipped:** IC scorecard, research director review, and comparables agent. These agents should not evaluate a memo that failed verification — their outputs would be unreliable.

### Files touched
- `main.py`
- `app.py`

---

## Item 3: Schema Validation + Retry on All Agent Outputs

### Problem

Only `fund_analysis.py` and `risk_flagging.py` validate their outputs against TypedDict schemas and retry once on failure. The other agents (`ic_scorecard`, `research_director`, `comparables`, `news_research`) return unvalidated output — a malformed response silently propagates.

### Design

**Pattern to replicate** (from `fund_analysis.py`):
1. Agent returns JSON output
2. Validate against TypedDict schema using existing `validate_schema()` from `tools/schemas.py`
3. If validation fails: append error details to prompt, retry LLM call once
4. If retry also fails: return None and log error

**Agents to update:**

| Agent | Schema (TypedDict) | Notes |
|-------|-------------------|-------|
| `ic_scorecard.py` | `ScorecardOutput` | Add TypedDict if missing |
| `research_director.py` | `DirectorReviewOutput` | Add TypedDict if missing |
| `comparables.py` | `ComparablesOutput` | Add TypedDict if missing |
| `news_research.py` | `NewsReport` | Already exists, wire up validation |

**New TypedDicts in `tools/schemas.py`** (if not already present):

```python
class ScorecardOutput(TypedDict):
    recommendation: str
    confidence: str
    score: int
    rationale: str

class DirectorReviewOutput(TypedDict):
    verdict: str
    revised_recommendation: str
    rationale: str
    key_concerns: list

class ComparablesOutput(TypedDict):
    peers: list
    comparison_summary: str
```

Exact fields will be confirmed by reading each agent's current output structure before implementation.

### Files touched
- `tools/schemas.py`
- `agents/ic_scorecard.py`
- `agents/research_director.py`
- `agents/comparables.py`
- `agents/news_research.py`

---

## Item 4: Input Validation at Entry Point

### Problem

Firm name / CRD is user-controlled input that flows into filesystem paths (output filenames), SEC API query parameters, and LLM prompts. No validation exists beyond filename sanitization.

### Design

**New function:** `validate_firm_input(value: str) -> str` in `tools/validation.py`

```python
def validate_firm_input(value: str) -> str:
    """Validate and sanitize firm name or CRD input.

    Returns cleaned input string.
    Raises ValueError if input is invalid.
    """
```

**Rules:**
1. Strip whitespace
2. Reject empty string → `ValueError("Firm name or CRD is required")`
3. Reject length > 200 chars → `ValueError("Input too long (max 200 characters)")`
4. If input is purely numeric: treat as CRD, validate it's a reasonable length (1-10 digits)
5. If input contains characters outside `[a-zA-Z0-9 .,'&()\-/]`: reject with `ValueError` listing the offending characters
6. Return cleaned string

**Integration:**
- `main.py`: Call at top of `run_pipeline()`, before any other work. Catch `ValueError`, print error, exit with code 1.
- `app.py`: Call when user submits input. Catch `ValueError`, show `st.error()`.

### Files touched
- `tools/validation.py` (new file)
- `main.py`
- `app.py`

---

## Out of Scope

- Agent prompt changes
- Data flow restructuring between steps
- Output file format changes (beyond DRAFT prefix)
- Firm history store (future session)
- Seam documentation / information barriers (future session)
- Container isolation
