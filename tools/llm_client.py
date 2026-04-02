"""
LLM Client — OpenAI GPT-4o.

Provides two modes:
  - complete / complete_json : single-shot LLM call (synthesis, analysis)
  - agent_loop               : tool-use agentic loop (GPT decides what to call)

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
from openai import OpenAI, RateLimitError


class _TokenBucket:
    """Thread-safe sliding-window token rate limiter."""

    def __init__(self, tpm_limit: int = 30_000):
        self._lock = threading.Lock()
        self._tpm_limit = tpm_limit
        self._window: deque[tuple[float, int]] = deque()  # (timestamp, tokens)

    @property
    def tpm_limit(self) -> int:
        return self._tpm_limit

    @tpm_limit.setter
    def tpm_limit(self, value: int) -> None:
        with self._lock:
            self._tpm_limit = value

    def _purge_old(self) -> None:
        """Remove entries older than 60 seconds."""
        cutoff = time.time() - 60.0
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def tokens_used(self) -> int:
        """Tokens consumed in the current 60-second window."""
        with self._lock:
            self._purge_old()
            return sum(t for _, t in self._window)

    def acquire(self, estimated_tokens: int) -> None:
        """Block until estimated_tokens can fit under the TPM limit."""
        while True:
            with self._lock:
                self._purge_old()
                used = sum(t for _, t in self._window)
                if used + estimated_tokens <= self._tpm_limit:
                    # Reserve the tokens now (will be corrected after the call)
                    self._window.append((time.time(), estimated_tokens))
                    return
                # Calculate how long until enough tokens expire
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
        """Correct the reservation with actual usage from the API response."""
        with self._lock:
            # Find and update the most recent entry matching our estimate
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
        """Set the tokens-per-minute limit for rate limiting."""
        _bucket.tpm_limit = tpm
        print(f"[LLM] TPM limit set to {tpm:,}")

    def __init__(self, api_key: str):
        self._client = OpenAI(api_key=api_key)
        self.provider = "openai"
        self.model = "gpt-4o"

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return max(100, len(text) // 4)

    def _call_with_budget(self, estimated_input: int, max_output: int, api_call):
        """Acquire token budget, make the API call, record actual usage."""
        estimated_total = estimated_input + max_output
        _bucket.acquire(estimated_total)
        try:
            response = api_call()
        except RateLimitError:
            # On 429, the reservation stays but we'll retry after backoff
            raise
        # Record actual usage
        usage = getattr(response, "usage", None)
        if usage:
            actual = usage.prompt_tokens + usage.completion_tokens
            _bucket.record_actual(estimated_total, actual)
            print(f"[LLM] Tokens: {usage.prompt_tokens:,} in + "
                  f"{usage.completion_tokens:,} out = {actual:,} "
                  f"({_bucket.tokens_used():,}/{_bucket.tpm_limit:,} TPM window)")
        return response

    def _retry(self, estimated_input: int, max_output: int, api_call, retries: int = 3):
        """Call with token budget + exponential backoff on 429."""
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

    # ── Single-shot completions ───────────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000,
                 thinking_tokens: int = 0, **_) -> str:
        """
        Single-shot text completion with token-aware rate limiting.
        thinking_tokens is accepted for API compatibility but not used.
        """
        est_input = self._estimate_tokens(system) + self._estimate_tokens(user)
        response = self._retry(est_input, max_tokens, lambda: (
            self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        ))
        return (response.choices[0].message.content or "").strip()

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000,
                      thinking_tokens: int = 0, **_) -> dict:
        """complete() but uses OpenAI JSON mode for guaranteed valid JSON."""
        augmented_system = system + "\n\nYou MUST respond with valid JSON."
        est_input = self._estimate_tokens(augmented_system) + self._estimate_tokens(user)
        response = self._retry(est_input, max_tokens, lambda: (
            self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": augmented_system},
                    {"role": "user", "content": user},
                ],
            )
        ))
        text = (response.choices[0].message.content or "").strip()
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
                f"LLM returned non-JSON response from {self.model}. "
                f"First 200 chars: {text[:200]!r}"
            )

    def chat(self, messages: list[dict], max_tokens: int = 2000) -> str:
        """Fast conversational completion using gpt-4o-mini."""
        openai_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        est_input = sum(self._estimate_tokens(m["content"]) for m in messages)
        response = self._retry(est_input, max_tokens, lambda: (
            self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=max_tokens,
                messages=openai_messages,
            )
        ))
        return (response.choices[0].message.content or "").strip()

    # ── Agentic tool-use loop ─────────────────────────────────────────────────

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """Convert Anthropic-format tool definitions to OpenAI function-calling format."""
        openai_tools = []
        for tool in tools:
            if "type" in tool and tool["type"] == "function":
                openai_tools.append(tool)
            else:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", tool.get("parameters", {})),
                    },
                })
        return openai_tools

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
        Run an agentic tool-use loop with token-aware rate limiting.
        GPT decides which tools to call and when to stop.
        """
        openai_tools = self._convert_tools(tools)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": initial_message},
        ]

        for iteration in range(max_iterations):
            est_input = sum(
                self._estimate_tokens(
                    m["content"] if isinstance(m, dict) and "content" in m
                    else str(m)
                )
                for m in messages
            )
            response = self._retry(est_input, max_tokens, lambda: (
                self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=messages,
                    tools=openai_tools,
                )
            ))

            choice = response.choices[0]
            assistant_msg = choice.message

            messages.append(assistant_msg)

            if choice.finish_reason == "stop" or not assistant_msg.tool_calls:
                return (assistant_msg.content or "").strip()

            for tool_call in assistant_msg.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_inputs = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_inputs = {}

                print(f"  [agent] -> {tool_name}({json.dumps(tool_inputs)[:120]})")

                if tool_name in tool_executor:
                    try:
                        result = tool_executor[tool_name](tool_inputs)
                        result_str = (
                            json.dumps(result, default=str)
                            if not isinstance(result, str)
                            else result
                        )
                    except Exception as e:
                        result_str = f"Tool error: {e}"
                else:
                    result_str = f"Unknown tool: {tool_name}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str,
                })

        # Exceeded max iterations — ask for final answer
        messages.append({
            "role": "user",
            "content": "You've reached the maximum number of tool calls. "
                       "Please provide your final answer now.",
        })
        est_input = sum(
            self._estimate_tokens(
                m["content"] if isinstance(m, dict) and "content" in m
                else str(m)
            )
            for m in messages
        )
        response = self._retry(est_input, max_tokens, lambda: (
            self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )
        ))
        return (response.choices[0].message.content or "").strip()

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
