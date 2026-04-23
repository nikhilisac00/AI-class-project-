"""
Execution trace — structured per-LLM-call logging.

Appends one JSON line per call to ``logs/trace.jsonl`` with token counts,
latency, estimated cost, and success/failure status.

The firm context is set once per pipeline run via ``set_current_firm()``
using a ``contextvars.ContextVar`` so agents don't need to thread the
firm identifier through every LLM call.

Trace log directory: ``TRACE_LOG_DIR`` env var, default ``logs/``.
"""

import contextvars
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_current_firm: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_firm", default=""
)

# GPT-4o pricing (USD per token) as of 2025-05
_COST_PER_INPUT_TOKEN = 2.50 / 1_000_000   # $2.50 / 1M input tokens
_COST_PER_OUTPUT_TOKEN = 10.00 / 1_000_000  # $10.00 / 1M output tokens

_DEFAULT_LOG_DIR = "logs"
_LOG_FILE = "trace.jsonl"

# Thread lock for atomic file appends
_write_lock = threading.Lock()


def set_current_firm(firm_id: str) -> None:
    """Set the firm identifier for the current execution context."""
    _current_firm.set(firm_id)


def get_current_firm() -> str:
    """Return the current firm identifier (empty string if unset)."""
    return _current_firm.get()


def _log_path() -> Path:
    """Return the trace log file path, creating the directory if needed."""
    d = Path(os.getenv("TRACE_LOG_DIR", _DEFAULT_LOG_DIR))
    d.mkdir(parents=True, exist_ok=True)
    return d / _LOG_FILE


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a GPT-4o call."""
    return round(
        input_tokens * _COST_PER_INPUT_TOKEN + output_tokens * _COST_PER_OUTPUT_TOKEN,
        6,
    )


def trace_llm_call(
    step: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    retry_count: int = 0,
    firm_id: Optional[str] = None,
) -> None:
    """Append one structured trace record to ``logs/trace.jsonl``.

    Args:
        step:          Agent or stage name (e.g. ``"fund_analysis"``).
        model:         Model identifier (e.g. ``"gpt-4o"``).
        input_tokens:  Prompt token count from the API response.
        output_tokens: Completion token count from the API response.
        latency_ms:    Wall-clock milliseconds for the API call.
        success:       Whether the call returned a usable response.
        retry_count:   Number of schema-validation retries (from caller).
        firm_id:       Override for the firm identifier (uses context var if omitted).
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "firm_id": firm_id or get_current_firm(),
        "step": step,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "estimated_cost_usd": estimate_cost(input_tokens, output_tokens),
        "success": success,
        "retry_count": retry_count,
    }
    try:
        with _write_lock:
            with open(_log_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        print(f"[Trace] WARNING: could not write trace record: {exc}")
