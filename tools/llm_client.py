"""
LLM Client — OpenAI GPT-4o.

Provides two modes:
  - complete / complete_json : single-shot LLM call (synthesis, analysis)
  - agent_loop               : tool-use agentic loop (GPT decides what to call)

Rate limiting:
  All LLMClient instances share a class-level throttle (_last_call_time / _call_lock).
  _throttle() enforces a minimum gap between consecutive API calls.
  Default: 2 seconds between calls.
  Adjust with: LLMClient.set_call_interval(seconds)
"""

import json
import re
import time
import threading
from openai import OpenAI, RateLimitError


class LLMClient:
    # ── Class-level throttle (shared across all instances) ──────────────────
    _last_call_time: float = 0.0
    _call_lock = threading.Lock()
    _min_interval: float = 2.0  # seconds between calls

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
        self._client = OpenAI(api_key=api_key)
        self.provider = "openai"
        self.model = "gpt-4o"

    # ── Single-shot completions ───────────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000,
                 thinking_tokens: int = 0, **_) -> str:
        """
        Single-shot text completion with throttle + retry on 429.
        thinking_tokens is accepted for API compatibility but not used
        (OpenAI models reason via system prompt instructions).
        """
        self._throttle()
        for attempt in range(4):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                break
            except RateLimitError:
                if attempt == 3:
                    raise
                wait = 2 ** (attempt + 2)
                print(f"[LLM] Rate limit hit — retrying in {wait}s (attempt {attempt + 1}/3)...")
                time.sleep(wait)
        return (response.choices[0].message.content or "").strip()

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000,
                      thinking_tokens: int = 0, **_) -> dict:
        """complete() but uses OpenAI JSON mode for guaranteed valid JSON."""
        self._throttle()
        for attempt in range(4):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system + "\n\nYou MUST respond with valid JSON."},
                        {"role": "user", "content": user},
                    ],
                )
                break
            except RateLimitError:
                if attempt == 3:
                    raise
                wait = 2 ** (attempt + 2)
                print(f"[LLM] Rate limit hit — retrying in {wait}s (attempt {attempt + 1}/3)...")
                time.sleep(wait)
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
        openai_messages = []
        for m in messages:
            openai_messages.append({"role": m["role"], "content": m["content"]})

        self._throttle()
        for attempt in range(4):
            try:
                response = self._client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=max_tokens,
                    messages=openai_messages,
                )
                break
            except RateLimitError:
                if attempt == 3:
                    raise
                wait = 2 ** (attempt + 2)
                print(f"[LLM] Rate limit hit — retrying in {wait}s...")
                time.sleep(wait)
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
        Run an agentic tool-use loop with throttle + retry on 429.
        GPT decides which tools to call and when to stop.
        """
        openai_tools = self._convert_tools(tools)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": initial_message},
        ]

        for iteration in range(max_iterations):
            self._throttle()
            for attempt in range(4):
                try:
                    response = self._client.chat.completions.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        messages=messages,
                        tools=openai_tools,
                    )
                    break
                except RateLimitError:
                    if attempt == 3:
                        raise
                    wait = 2 ** (attempt + 2)
                    print(f"[LLM] Rate limit hit — retrying in {wait}s...")
                    time.sleep(wait)

            choice = response.choices[0]
            assistant_msg = choice.message

            # Append assistant turn
            messages.append(assistant_msg)

            # Done — no more tool calls
            if choice.finish_reason == "stop" or not assistant_msg.tool_calls:
                return (assistant_msg.content or "").strip()

            # Process tool calls
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
        self._throttle()
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
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
