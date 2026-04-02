"""
LLM Client — Anthropic Claude (claude-sonnet-4-6).

Provides two modes:
  - complete / complete_json : single-shot LLM call (synthesis, analysis)
  - agent_loop               : tool-use agentic loop (Claude decides what to call)

Rate limiting:
  All LLMClient instances share a class-level throttle (_last_call_time / _call_lock).
  _throttle() enforces a minimum gap between consecutive API calls so the org
  never exceeds the 10,000 input token/minute limit.
  Default: 12 seconds between calls (~5 calls/min, ~8-9k tokens/min headroom).
  Adjust with: LLMClient.set_call_interval(seconds)
"""

import json
import re
import time
import threading
import anthropic
from anthropic import RateLimitError


class LLMClient:
    # ── Class-level throttle (shared across all instances) ──────────────────
    _last_call_time: float = 0.0
    _call_lock = threading.Lock()
    _min_interval: float = 12.0  # seconds between calls

    @classmethod
    def set_call_interval(cls, seconds: float) -> None:
        """Adjust the minimum gap between API calls. Call before starting a run."""
        cls._min_interval = seconds
        print(f"[LLM] Call interval set to {seconds}s")

    def _throttle(self) -> None:
        """Sleep if the last API call was too recent."""
        with LLMClient._call_lock:
            elapsed = time.time() - LLMClient._last_call_time
            if elapsed < LLMClient._min_interval:
                wait = LLMClient._min_interval - elapsed
                print(f"[LLM] Throttling — waiting {wait:.1f}s...")
                time.sleep(wait)
            LLMClient._last_call_time = time.time()

    # ── Instance setup ──────────────────────────────────────────────────

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.provider = "anthropic"
        self.model = "claude-sonnet-4-6"

    # ── Single-shot completions ───────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000,
                 thinking_tokens: int = 0, **_) -> str:
        """
        Single-shot text completion with throttle + retry on 429.
        Pass thinking_tokens > 0 to enable extended thinking.
        """
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if thinking_tokens > 0:
            kwargs["max_tokens"] = max(max_tokens, thinking_tokens + 2048)
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_tokens}

        self._throttle()
        for attempt in range(4):
            try:
                message = self._client.messages.create(**kwargs)
                break
            except RateLimitError:
                if attempt == 3:
                    raise
                wait = 2 ** (attempt + 2)  # 4, 8, 16 seconds
                print(f"[LLM] Rate limit hit — retrying in {wait}s (attempt {attempt + 1}/3)...")
                time.sleep(wait)

        return "".join(
            block.text for block in message.content
            if hasattr(block, "text")
        ).strip()

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000,
                      thinking_tokens: int = 0, **_) -> dict:
        """complete() but parses the response as JSON."""
        text = self.complete(system, user, max_tokens,
                             thinking_tokens=thinking_tokens)
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
        """Fast conversational completion using claude-haiku-4-5."""
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        convo = [m for m in messages if m["role"] != "system"]
        self._throttle()
        for attempt in range(4):
            try:
                message = self._client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=system,
                    messages=convo,
                )
                break
            except RateLimitError:
                if attempt == 3:
                    raise
                wait = 2 ** (attempt + 2)
                print(f"[LLM] Rate limit hit — retrying in {wait}s...")
                time.sleep(wait)
        return (message.content[0].text or "").strip()

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
        Run an agentic tool-use loop with throttle + retry on 429.
        Claude decides which tools to call and when to stop.
        """
        messages = [{"role": "user", "content": initial_message}]

        for iteration in range(max_iterations):
            self._throttle()
            for attempt in range(4):
                try:
                    response = self._client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        system=system,
                        tools=tools,
                        messages=messages,
                    )
                    break
                except RateLimitError:
                    if attempt == 3:
                        raise
                    wait = 2 ** (attempt + 2)
                    print(f"[LLM] Rate limit hit — retrying in {wait}s...")
                    time.sleep(wait)

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text.strip()
                return ""

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_name   = block.name
                tool_inputs = block.input
                tool_id     = block.id

                print(f"  [agent] → {tool_name}({json.dumps(tool_inputs)[:120]})")

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

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tool_id,
                    "content":     result_str,
                })

            messages.append({"role": "user", "content": tool_results})

        # Exceeded max iterations — ask for final answer
        self._throttle()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages + [{
                "role": "user",
                "content": "You've reached the maximum number of tool calls. "
                           "Please provide your final answer now.",
            }],
        )
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
