"""Tests for tools.trace — run-level correlation, summarization, and extended trace fields."""

import contextvars
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.trace import (
    _summarize,
    get_run_id,
    set_run_id,
    trace_llm_call,
)


# ---------------------------------------------------------------------------
# set_run_id / get_run_id
# ---------------------------------------------------------------------------


class TestRunId:
    """Tests for the run_id context variable helpers."""

    def test_default_run_id_is_empty(self) -> None:
        """get_run_id returns empty string when no run_id has been set."""
        ctx = contextvars.copy_context()
        result = ctx.run(get_run_id)
        assert result == ""

    def test_set_and_get_run_id(self) -> None:
        """set_run_id stores a value retrievable via get_run_id."""
        ctx = contextvars.copy_context()

        def _inner() -> str:
            set_run_id("run-abc-123")
            return get_run_id()

        assert ctx.run(_inner) == "run-abc-123"

    def test_set_run_id_resets_step_counter(self) -> None:
        """Calling set_run_id resets the step counter back to 0."""
        ctx = contextvars.copy_context()

        def _inner() -> list[int]:
            set_run_id("run-1")
            # Import the internal counter to peek at values
            from tools.trace import _step_counter

            counter = _step_counter.get()
            first = next(counter)
            second = next(counter)
            # Now reset
            set_run_id("run-2")
            counter2 = _step_counter.get()
            after_reset = next(counter2)
            return [first, second, after_reset]

        values = ctx.run(_inner)
        assert values == [0, 1, 0], "step counter should restart at 0 after set_run_id"


# ---------------------------------------------------------------------------
# _summarize
# ---------------------------------------------------------------------------


class TestSummarize:
    """Tests for the _summarize helper."""

    def test_none_passthrough(self) -> None:
        """None is returned unchanged."""
        assert _summarize(None) is None

    def test_short_string_unchanged(self) -> None:
        """Strings within max_str_len are returned as-is."""
        assert _summarize("hello") == "hello"

    def test_long_string_truncated(self) -> None:
        """Strings exceeding max_str_len are truncated with '...'."""
        long = "x" * 600
        result = _summarize(long, max_str_len=500)
        assert len(result) == 503  # 500 chars + "..."
        assert result.endswith("...")

    def test_list_replaced(self) -> None:
        """Lists are replaced with a summary string."""
        assert _summarize([1, 2, 3]) == "[list of 3 items]"

    def test_empty_list(self) -> None:
        """Empty list summarizes correctly."""
        assert _summarize([]) == "[list of 0 items]"

    def test_dict_values_summarized(self) -> None:
        """Dict values are recursively summarized."""
        data = {"key": "short", "big": "y" * 600}
        result = _summarize(data, max_str_len=500)
        assert result["key"] == "short"
        assert result["big"].endswith("...")
        assert len(result["big"]) == 503

    def test_dict_with_nested_list(self) -> None:
        """Dict containing a list summarizes the list."""
        data = {"items": [1, 2, 3, 4]}
        result = _summarize(data)
        assert result["items"] == "[list of 4 items]"

    def test_non_matching_types_passthrough(self) -> None:
        """Integers and other types pass through unchanged."""
        assert _summarize(42) == 42
        assert _summarize(3.14) == 3.14


# ---------------------------------------------------------------------------
# trace_llm_call — extended fields
# ---------------------------------------------------------------------------


class TestTraceLlmCallExtended:
    """Tests for the new fields added to trace_llm_call."""

    @pytest.fixture(autouse=True)
    def _use_tmp_log_dir(self, tmp_path: Path) -> None:
        """Redirect trace logs to a temp directory."""
        self._log_dir = tmp_path
        self._log_file = tmp_path / "trace.jsonl"

    def _call_trace(self, **kwargs: object) -> dict:
        """Call trace_llm_call with defaults and return the written record."""
        defaults = dict(
            step="test_step",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            latency_ms=200,
            success=True,
        )
        defaults.update(kwargs)
        with patch.dict(os.environ, {"TRACE_LOG_DIR": str(self._log_dir)}):
            trace_llm_call(**defaults)
        line = self._log_file.read_text(encoding="utf-8").strip().split("\n")[-1]
        return json.loads(line)

    def test_run_id_included_in_record(self) -> None:
        """Record contains run_id from the context variable."""
        ctx = contextvars.copy_context()

        def _inner() -> dict:
            set_run_id("run-xyz")
            return self._call_trace()

        record = ctx.run(_inner)
        assert record["run_id"] == "run-xyz"

    def test_step_id_increments(self) -> None:
        """step_id increments on successive calls within the same run."""
        ctx = contextvars.copy_context()

        def _inner() -> list[int]:
            set_run_id("run-inc")
            r1 = self._call_trace()
            r2 = self._call_trace()
            return [r1["step_id"], r2["step_id"]]

        ids = ctx.run(_inner)
        assert ids == [0, 1]

    def test_role_atom_and_principal(self) -> None:
        """role_atom and principal are stored in the record."""
        record = self._call_trace(role_atom="analyzer", principal="user:danny")
        assert record["role_atom"] == "analyzer"
        assert record["principal"] == "user:danny"

    def test_role_atom_defaults_none(self) -> None:
        """role_atom defaults to None when not provided."""
        record = self._call_trace()
        assert record["role_atom"] is None

    def test_agent_input_summarized(self) -> None:
        """agent_input dict values are summarized before storage."""
        big_input = {"prompt": "z" * 600, "items": [1, 2, 3]}
        record = self._call_trace(agent_input=big_input)
        ai = record["agent_input"]
        assert ai["prompt"].endswith("...")
        assert ai["items"] == "[list of 3 items]"

    def test_agent_output_summarized(self) -> None:
        """agent_output dict values are summarized before storage."""
        big_output = {"response": "w" * 600}
        record = self._call_trace(agent_output=big_output)
        ao = record["agent_output"]
        assert ao["response"].endswith("...")

    def test_agent_input_none_passthrough(self) -> None:
        """agent_input=None is stored as None."""
        record = self._call_trace(agent_input=None)
        assert record["agent_input"] is None

    def test_step_id_without_prior_set_run_id(self) -> None:
        """step_id works even if set_run_id was never called (counter auto-created)."""
        # Just verify that trace_llm_call produces an integer step_id
        # even when the counter hasn't been explicitly initialised via
        # set_run_id — the auto-create LookupError path handles this.
        record = self._call_trace()
        assert isinstance(record["step_id"], int)
