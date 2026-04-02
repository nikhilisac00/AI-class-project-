"""
LLM Client — Anthropic Claude (claude-sonnet-4-6).

Provides two modes:
  - complete / complete_json : single-shot LLM call (synthesis, analysis)
  - agent_loop               : tool-use agentic loop (Claude decides what to call)

Rate limiting:
  A sliding-window TokenBucket tracks actual tokens consumed per minute across
  all threads. Before each API call, _acquire_tokens() blocks until there is
  enough headroom under the TPM cap. After each call, actual usage from the
  response is recorded.
  Default: 30,000 TPM. Adjust with: LLMClient.set_tpm_limit(tokens)
"""

import json
import re
import time
import threading
from collections import deque
import anthropic
from anthropic import RateLimitError


class _TokenBucket:
    """Thread-safe sliding-window token rate limiter."""

    def __init__(self, tpm_limit: int = 30_000):
        self._lock = threading.Lock()
        self._tpm_limit = tpm_limit
        self._window: deque[tuple[float, int]] = deque()

    @property
    def tpm_limit(self) -> int:
        return self._tpm_limit

    @tpm_limit.setter
    def tpm_limit(self, value: int) -> None:
        with self._lock:
            self._tpm_limit = value

    def _purge_old(self) -> None:
        cutoff = time.time() - 60.0
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def tokens_used(self) -> int:
        with self._lock:
            self._purge_old()
            return sum(t for _, t in self._window)

    def acquire(self, estimated_tokens: int) -> None:
        while True:
            with self._lock:
                self._purge_old()
                used = sum(t for _, t in self._window)
                if used + estimated_tokens <= self._tpm_limit:
                    self._window.append((time.time(), estimated_tokens))
                    return
                needed = used + estimated_tokens - self._tpm_limit
                cumulative = 0
                wait_until = time.time()
                for ts, tok in self._window:
                    cumulative += tok
                    if cumulative >= needed:
                        wait_until = ts + 60.0
                        break
            wait = max(0.5, wait_until - time.time())
            print(f"[LLM] Token budget full ({used:,}/{self._tpm_limit:,} TPM) "
                  f"— waiting {wait:.1f}s...")
            time.sleep(wait)

    def record_actual(self, estimated_tokens: int, actual_tokens: int) -> None:
        with self._lock:
            for i in range(len(self._window) - 1, -1, -1):
                ts, tok = self._window[i]
                if tok == estimated_tokens:
                    self._window[i] = (ts, actual_tokens)
                    break


# Shared global bucket
_bucket = _TokenBucket(tpm_limit=30_000)


class LLMClient:

    @classmethod
    def set_tpm_limit(cls, tpm: int) -> None:
        _bucket.tpm_limit = tpm
        print(f"[LLM] TPM limit set to {tpm:,}")

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.provider = "anthropic"
        self.model = "claude-sonnet-4-6"

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(100, len(text) // 4)

    def _call_with_budget(self, estimated_input: int, max_output: int, api_call):
        estimated_total = estimated_input + max_output
        _bucket.acquire(estimated_total)
        try:
            response = api_call()
        except RateLimitError:
            raise
        usage = getattr(response, "usage", None)
        if usage:
            actual = usage.input_tokens + usage.output_tokens
            _bucket.record_actual(estimated_total, actual)
            print(f"[LLM] Tokens: {usage.input_tokens:,} in + "
                  f"{usage.output_tokens:,} out = {actual:,} "
                  f"({_bucket.tokens_used():,}/{_bucket.tpm_limit:,} TPM window)")
        return response

    def _retry(self, estimated_input: int, max_output: int, api_call, retries: int = 3):
        for attempt in range(retries + 1):
            try:
                return self._call_with_budget(estimated_input, max_output, api_call)
            except RateLimitError:
                if attempt == retries:
                    raise
                wait = 2 ** (attempt + 2)
                print(f"[LLM] Rate limit 429 — retrying in {wait}s "
                      f"(attempt {attempt + 1}/{retries})...")
                time.sleep(wait)

    # ── Single-shot completions ───────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000,
                 thinking_tokens: int = 0, **_) -> str:
        est_input = self._estimate_tokens(system) + self._estimate_tokens(user)
        response = self._retry(est_input, max_tokens, lambda: (
            self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        ))
        for block in response.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return ""

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000,
                      thinking_tokens: int = 0, **_) -> dict:
        augmented_system = system + "\n\nYou MUST respond with valid JSON only. No markdown fences, no explanation outside the JSON."
        est_input = self._estimate_tokens(augmented_system) + self._estimate_tokens(user)
        response = self._retry(est_input, max_tokens, lambda: (
            self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=augmented_system,
                messages=[{"role": "user", "content": user}],
            )
        ))
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                break
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            raise ValueError(
                f"LLM returned non-JSON from {self.model}. "
                f"First 200 chars: {text[:200]!r}"
            )

    def chat(self, messages: list[dict], max_tokens: int = 2000) -> str:
        """Conversational completion — separates system message from the turn list."""
        system = ""
        turn_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                turn_messages.append({"role": m["role"], "content": m["content"]})

        est_input = sum(self._estimate_tokens(m["content"]) for m in messages)
        kwargs: dict = dict(model=self.model, max_tokens=max_tokens, messages=turn_messages)
        if system:
            kwargs["system"] = system

        response = self._retry(est_input, max_tokens, lambda: self._client.messages.create(**kwargs))
        for block in response.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return ""

    # ── Agentic tool-use loop ─────────────────────────────────────────────

    def agent_loop(
        self,
        system: str,
        initial_message: str,
        tools: list[dict],
        tool_executor: dict,
        max_tokens: int = 4096,
        max_iterations: int = 15,
    ) -> str:
        """
        Run an agentic tool-use loop using Anthropic tool use.
        Tools should be in Anthropic format (with input_schema).
        """
        messages: list[dict] = [{"role": "user", "content": initial_message}]

        for _ in range(max_iterations):
            est_input = sum(
                self._estimate_tokens(
                    m["content"] if isinstance(m["content"], str)
                    else json.dumps(m["content"], default=str)
                )
                for m in messages
            )
            response = self._retry(est_input, max_tokens, lambda: (
                self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    tools=tools,
                    messages=messages,
                )
            ))

            # If no tool use, return the text response
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses or response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text.strip()
                return ""

            # Add assistant turn with all content blocks
            messages.append({"role": "assistant", "content": response.content})

            # Execute tools and collect results
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_inputs = tool_use.input
                print(f"  [agent] -> {tool_name}({json.dumps(tool_inputs)[:120]})")

                if tool_name in tool_executor:
                    try:
                        result = tool_executor[tool_name](tool_inputs)
                        result_str = (
                            json.dumps(result, default=str)
                            if not isinstance(result, str) else result
                        )
                    except Exception as e:
                        result_str = f"Tool error: {e}"
                else:
                    result_str = f"Unknown tool: {tool_name}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_str,
                })

            messages.append({"role": "user", "content": tool_results})

        # Max iterations — ask for final answer
        messages.append({"role": "user", "content": "You've reached the maximum number of tool calls. Please provide your final answer now."})
        est_input = sum(
            self._estimate_tokens(
                m["content"] if isinstance(m["content"], str)
                else json.dumps(m["content"], default=str)
            )
            for m in messages
        )
        response = self._retry(est_input, max_tokens, lambda: (
            self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
        ))
        for block in response.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return ""

    def agent_loop_json(self, system: str, initial_message: str,
                        tools: list[dict], tool_executor: dict,
                        max_tokens: int = 4096, max_iterations: int = 15) -> dict:
        """agent_loop but parses the final response as JSON."""
        text = self.agent_loop(
            system, initial_message, tools, tool_executor,
            max_tokens=max_tokens, max_iterations=max_iterations,
        )
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            return {"parse_error": text[:500]}


def make_client(api_key: str) -> LLMClient:
    return LLMClient(api_key=api_key)
