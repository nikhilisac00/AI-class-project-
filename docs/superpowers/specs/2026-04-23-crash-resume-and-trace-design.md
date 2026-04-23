# Crash-Resumable RawData Cache & Per-Step Execution Trace

## Problem

1. If the pipeline crashes after ThreadPoolExecutor ingestion but before fund analysis, all parallel IAPD/EDGAR work is lost.
2. No structured per-LLM-call trace exists for cost tracking or debugging.

## Task 1: RawData Cache

### New module: `tools/raw_data_cache.py`

Two public functions:

- `save_raw_data(firm_key: str, raw_data: dict) -> Path` — serializes RawData with `_cached_at` ISO timestamp to `.cache/raw_data/{sanitized_key}.json`.
- `load_raw_data(firm_key: str, ttl_hours: float = 24) -> Optional[dict]` — returns cached payload if file exists and age < TTL; otherwise `None`.

Cache key: lowercased firm name or CRD, non-alphanumeric chars replaced with `_`.

Cache path: `RAW_DATA_CACHE_DIR` env var, default `.cache/raw_data/`.

File format:
```json
{"_cached_at": "2026-04-23T12:00:00Z", "data": { ...RawData... }}
```

### Integration points

- `agents/data_ingestion.py run()`: check cache at top (unless `force_refresh=True`), save after assembly before return.
- `main.py`: accept `--force-refresh` CLI flag, pass through to `run()`.
- `app.py`: add "Force refresh" checkbox, pass through to `run()`.

### Behavior

- Cache hit (fresh): skip all HTTP calls, return cached RawData, print `[Ingestion] Loaded from cache`.
- Cache miss or stale: fetch normally, save result to cache before returning.
- `force_refresh=True`: skip load, fetch normally, save result.
- Cache write errors are logged and swallowed — never crash the pipeline over caching.

## Task 2: Execution Trace

### New module: `tools/trace.py`

Components:

- `set_current_firm(firm_id: str)` — sets a `contextvars.ContextVar` for the current firm CRD/CIK.
- `trace_llm_call(step, model, input_tokens, output_tokens, latency_ms, success, retry_count)` — appends one JSON line to `logs/trace.jsonl`.
- Cost constants for GPT-4o pricing.

### Trace record schema (one JSON line)

```json
{
  "timestamp": "2026-04-23T12:00:00.000Z",
  "firm_id": "149729",
  "step": "fund_analysis",
  "model": "gpt-4o",
  "input_tokens": 3200,
  "output_tokens": 1800,
  "latency_ms": 4521,
  "estimated_cost_usd": 0.034,
  "success": true,
  "retry_count": 0
}
```

### Integration

Instrument `LLMClient.complete()` internally — this is the single call path for `complete_json()` and `agent_loop_json()`. Add:
- `time.perf_counter()` before/after the API call
- Extract `response.usage.prompt_tokens` and `response.usage.completion_tokens`
- Call `trace_llm_call()` with all fields
- Accept optional `step_name` parameter on `complete()` for caller identification

Firm context: `main.py` calls `set_current_firm(crd)` before each pipeline run.

### Log path

`TRACE_LOG_DIR` env var, default `logs/`. File: `trace.jsonl`. Created on first write.

## Constraints

- No new dependencies.
- No changes to agent logic, schemas, or test structure.
- 5-firm benchmark must still pass.
- `.cache/` and `logs/trace.jsonl` added to `.gitignore`.
