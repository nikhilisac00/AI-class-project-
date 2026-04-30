"""
LLM Client — OpenAI (gpt-4o).

Provides three interaction modes:
  - complete()        : single-turn text completion
  - complete_json()   : single-turn completion parsed as JSON
  - agent_loop_json() : multi-turn tool-use loop (for autonomous agents)
"""

import json
import re
import time
from datetime import datetime

import openai

from tools.context_prep import trim_json_arrays
from tools.trace import trace_llm_call

# Default timeout for all OpenAI API calls (seconds). Bug #20.
_API_TIMEOUT = 90


class LLMClient:
    """Thin wrapper around the OpenAI API for the agent pipeline."""

    # Rough characters-per-token ratio for estimation (GPT-4o averages ~3.5-4)
    _CHARS_PER_TOKEN = 4
    # Default max input tokens — leaves room for output within a 30k TPM cap.
    # Can be overridden via the tpm_limit parameter.
    _DEFAULT_TPM_LIMIT = 30_000

    def __init__(self, api_key: str, tpm_limit: int | None = None):
        self._client = openai.OpenAI(api_key=api_key, timeout=_API_TIMEOUT)
        self.provider = "openai"
        self.model = "gpt-4o"
        self._trace: list[dict] = []
        self._current_agent: str | None = None
        self._tpm_limit = tpm_limit or self._DEFAULT_TPM_LIMIT

    def _record(self, response, latency_ms: int) -> None:
        """Append one trace row after each successful API call."""
        usage = getattr(response, "usage", None)
        self._trace.append({
            "agent": self._current_agent,
            "model": getattr(response, "model", self.model),
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
            "latency_ms": latency_ms,
            "ts": datetime.now().isoformat(),
        })

    def get_trace(self) -> list[dict]:
        return list(self._trace)

    def reset_trace(self) -> None:
        self._trace.clear()

    # ── Context budget enforcement ──────────────────────────────────────────

    def _estimate_tokens(self, text: str) -> int:
        """Rough token count estimate from character length."""
        return max(1, len(text) // self._CHARS_PER_TOKEN)

    def _enforce_budget(self, system: str, user: str,
                        max_tokens: int) -> tuple[str, str]:
        """Ensure the request fits within the TPM limit.

        Uses structured trimming: finds the largest JSON arrays in the
        user message and compresses them (keep first N + count) rather
        than blindly truncating. This preserves all sections of the prompt
        while reducing only the heaviest data (13F holdings, fund lists, etc.).

        Returns (system, user) — possibly with user compressed.
        The harness owns the token budget; individual agents should not need
        to worry about prompt size.
        """
        sys_tokens = self._estimate_tokens(system)
        user_tokens = self._estimate_tokens(user)
        total = sys_tokens + user_tokens + max_tokens

        if total <= self._tpm_limit:
            return system, user

        # Budget available for the user message
        budget_for_user = max(500, self._tpm_limit - sys_tokens - max_tokens)
        max_user_chars = budget_for_user * self._CHARS_PER_TOKEN

        original_tokens = user_tokens
        user = trim_json_arrays(user, max_user_chars)

        trimmed_tokens = self._estimate_tokens(user)
        print(
            f"[LLMClient] Context budget: compressed user prompt from "
            f"~{original_tokens} to ~{trimmed_tokens} tokens "
            f"(TPM limit: {self._tpm_limit}, max_tokens: {max_tokens})"
        )
        return system, user

    # ── Retry logic ────────────────────────────────────────────────────────

    _MAX_RETRIES = 3
    _RETRY_DELAYS = [30, 60, 90]  # seconds — escalating backoff

    def _call_with_retry(self, model: str, messages: list[dict],
                         max_tokens: int, step_name: str = "",
                         **kwargs) -> "openai.ChatCompletion":
        """Make an OpenAI API call with retry on rate limits.

        Retries up to _MAX_RETRIES times with escalating backoff.
        Raises RuntimeError on auth errors (no retry).
        """
        for attempt in range(self._MAX_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                return self._client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=messages,
                    **kwargs,
                )
            except openai.AuthenticationError as e:
                self._emit_trace(step_name, t0, None, False)
                raise RuntimeError(
                    f"[LLMClient] OpenAI API key is invalid or revoked: {e}"
                ) from e
            except openai.RateLimitError as e:
                if attempt >= self._MAX_RETRIES:
                    self._emit_trace(step_name, t0, None, False)
                    raise RuntimeError(
                        f"[LLMClient] Rate limit exceeded after {self._MAX_RETRIES} "
                        f"retries: {e}"
                    ) from e
                delay = self._RETRY_DELAYS[min(attempt, len(self._RETRY_DELAYS) - 1)]
                print(
                    f"[LLMClient] Rate limit hit (attempt {attempt + 1}/"
                    f"{self._MAX_RETRIES}) — waiting {delay}s: {e}"
                )
                time.sleep(delay)

    # ── Single-turn completions ──────────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000, step_name: str = "", **_) -> str:
        """Return a plain-text completion."""
        system, user = self._enforce_budget(system, user, max_tokens)
        t0 = time.perf_counter()
        response = self._call_with_retry(
            self.model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens, step_name=step_name,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        self._record(response, latency_ms)
        self._emit_trace(step_name, t0, response, True)
        content = (response.choices[0].message.content or "").strip()
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "length":
            print(f"[LLMClient] WARNING: response hit max_tokens={max_tokens} — will attempt JSON repair")
        return content

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000, step_name: str = "", **_) -> dict:
        """Return a completion parsed as a JSON dict."""
        system_msg, user_msg = self._enforce_budget(system, user, max_tokens)
        t0 = time.perf_counter()
        response = self._call_with_retry(
            self.model,
            [{"role": "system", "content": system_msg},
             {"role": "user", "content": user_msg}],
            max_tokens, step_name=step_name,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        self._record(response, latency_ms)
        self._emit_trace(step_name, t0, response, True)
        text = (response.choices[0].message.content or "").strip()
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "length":
            print(f"[LLMClient] WARNING: response hit max_tokens={max_tokens} — attempting JSON repair")
            repaired = LLMClient._repair_truncated_json(text)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

        return self._parse_json(text)

    def chat(self, messages: list[dict], max_tokens: int = 2000) -> str:
        """Fast conversational completion using gpt-4o-mini."""
        response = self._call_with_retry("gpt-4o-mini", messages, max_tokens)
        return (response.choices[0].message.content or "").strip()

    def chat_stream(self, messages: list[dict], max_tokens: int = 2000):
        """Stream a chat response, yielding text chunks as they arrive."""
        stream = self._client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    # ── Tool-use agent loop ──────────────────────────────────────────────────

    def agent_loop_json(
        self,
        system: str,
        initial_message: str,
        tools: list[dict],
        tool_executor: dict,
        max_tokens: int = 4096,
        max_iterations: int = 15,
        step_name: str = "",
    ) -> dict:
        """Run a multi-turn tool-use loop until the model produces a final JSON answer.

        Args:
            system:          System prompt for the agent.
            initial_message: First user message to kick off the loop.
            tools:           List of tool definitions (OpenAI function-calling format).
            tool_executor:   Dict mapping tool name -> callable(inputs) -> result.
            max_tokens:      Max tokens per model response.
            max_iterations:  Safety cap on the number of loop iterations.

        Returns:
            Parsed JSON dict from the model's final (non-tool-call) response.
            If parsing fails, returns {"parse_error": "<message>"}.
        """
        openai_tools = self._to_openai_tools(tools)

        system, initial_message = self._enforce_budget(
            system, initial_message, max_tokens,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": initial_message},
        ]

        for iteration in range(max_iterations):
            t0 = time.perf_counter()
            response = self._call_with_retry(
                self.model, messages, max_tokens,
                step_name=step_name,
                tools=openai_tools if openai_tools else None,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            self._record(response, latency_ms)
            self._emit_trace(step_name, t0, response, True)

            choice = response.choices[0]
            message = choice.message

            # If the model made tool calls, execute them and loop
            if message.tool_calls:
                messages.append(message)
                for tool_call in message.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    executor = tool_executor.get(fn_name)
                    if executor:
                        try:
                            result = executor(fn_args)
                        except Exception as exc:
                            result = {"error": str(exc)}
                    else:
                        result = {"error": f"Unknown tool: {fn_name}"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    })
                continue

            # No tool calls — model is done; parse the final text as JSON
            text = (message.content or "").strip()
            try:
                return self._parse_json(text)
            except (json.JSONDecodeError, ValueError) as exc:
                return {"parse_error": str(exc), "_raw_text": text}

        # Exhausted iterations
        return {"parse_error": f"Agent loop hit max iterations ({max_iterations})"}

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _emit_trace(self, step_name: str, t0: float,
                    response, success: bool) -> None:
        """Log one trace record for an API call."""
        latency_ms = int((time.perf_counter() - t0) * 1000)
        input_tokens = output_tokens = 0
        if response and hasattr(response, "usage") and response.usage:
            input_tokens = response.usage.prompt_tokens or 0
            output_tokens = response.usage.completion_tokens or 0
        trace_llm_call(
            step=step_name or "unknown",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            success=success,
        )

    @staticmethod
    def _to_openai_tools(tools: list[dict]) -> list[dict]:
        """Convert our tool defs to OpenAI function-calling format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        return openai_tools

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """Close unclosed JSON braces/brackets left by a truncated response.

        Handles two truncation cases:
        1. Between values — unclosed { or [ with no mid-string truncation
        2. Inside a string value — must find the last safe rollback point
        """
        def _scan(s: str):
            """Return (stack, in_string, last_safe_outside_string_idx)."""
            stack = []
            in_str = False
            esc = False
            last_safe = 0
            for i, ch in enumerate(s):
                if esc:
                    esc = False
                    continue
                if ch == "\\" and in_str:
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                # Outside string: track last safe rollback positions
                if ch in ',':
                    last_safe = i          # just after last complete value
                elif ch in '{[':
                    stack.append("}" if ch == "{" else "]")
                    last_safe = i          # opening bracket is a safe point
                elif ch in '}]' and stack and stack[-1] == ch:
                    stack.pop()
                    last_safe = i
            return stack, in_str, last_safe

        stack, in_string, last_safe = _scan(text)

        if not in_string:
            # Case 1: clean truncation between values
            repaired = text.rstrip().rstrip(",")
            return repaired + "".join(reversed(stack))

        # Case 2: truncated inside a string
        # Strategy A: close the string, close structures, see if it parses
        closing = "".join(reversed(stack))
        candidate_a = text + '"' + closing
        try:
            json.loads(candidate_a)
            print("[LLMClient] Repaired: closed unclosed string + structures")
            return candidate_a
        except json.JSONDecodeError:
            pass

        # Strategy B: roll back to last safe boundary outside any string.
        # If last_safe itself is inside a string (can happen with complex values),
        # scan backward until we find a position that is outside a string.
        for rollback in (last_safe, last_safe - 1):
            if rollback <= 0:
                continue
            truncated = text[:rollback].rstrip().rstrip(",")
            stack2, in_str2, _ = _scan(truncated)
            if not in_str2:
                closing2 = "".join(reversed(stack2))
                candidate_b = truncated + closing2
                try:
                    json.loads(candidate_b)
                    print("[LLMClient] Repaired: rolled back to last safe boundary")
                    return candidate_b
                except json.JSONDecodeError:
                    pass

        # Strategy C: walk backward, close any remaining open structures
        for end in range(len(text) - 1, 0, -1):
            if text[end] in ('}', ']'):
                prefix = text[:end + 1]
                stack_c, in_str_c, _ = _scan(prefix)
                if not in_str_c:
                    candidate_c = prefix + "".join(reversed(stack_c))
                    try:
                        return json.loads(candidate_c)
                    except json.JSONDecodeError:
                        pass

        # Strategy D: minimal shell with only the safely-parsed prefix
        first_brace = text.find('{')
        if first_brace != -1 and last_safe > first_brace:
            return text[first_brace:last_safe].rstrip().rstrip(",") + "}"
        return text.rstrip().rstrip(",") + "".join(reversed(stack))

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract and parse JSON from model output, stripping markdown fences."""
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try regex extraction first
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            # Try repairing truncated JSON (response hit max_tokens)
            try:
                repaired = LLMClient._repair_truncated_json(text)
                result = json.loads(repaired)
                print("[LLMClient] Warning: response was truncated — repaired JSON by closing open structures")
                return result
            except (json.JSONDecodeError, Exception):
                pass
            raise ValueError(
                f"LLM returned non-JSON response. "
                f"First 200 chars: {text[:200]!r}"
            )


def make_client(api_key: str) -> LLMClient:
    """Factory function for creating an LLMClient."""
    return LLMClient(api_key=api_key)
