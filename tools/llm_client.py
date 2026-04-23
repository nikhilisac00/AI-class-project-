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

import openai

from tools.trace import trace_llm_call

# Default timeout for all OpenAI API calls (seconds). Bug #20.
_API_TIMEOUT = 90


class LLMClient:
    """Thin wrapper around the OpenAI API for the agent pipeline."""

    def __init__(self, api_key: str):
        self._client = openai.OpenAI(api_key=api_key, timeout=_API_TIMEOUT)
        self.provider = "openai"
        self.model = "gpt-4o"

    # ── Single-turn completions ──────────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000, step_name: str = "", **_) -> str:
        """Return a plain-text completion."""
        # Bug #3: catch auth/rate-limit errors explicitly so mid-run failures
        # surface clearly rather than propagating as opaque KeyError/AttributeError.
        t0 = time.perf_counter()
        success = True
        response = None
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except openai.AuthenticationError as e:
            success = False
            self._emit_trace(step_name, t0, response, success)
            raise RuntimeError(
                f"[LLMClient] OpenAI API key is invalid or revoked: {e}"
            ) from e
        except openai.RateLimitError as e:
            print(f"[LLMClient] Rate limit hit — waiting 60s before retry: {e}")
            time.sleep(60)
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        self._emit_trace(step_name, t0, response, success)
        content = (response.choices[0].message.content or "").strip()
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "length":
            print(f"[LLMClient] WARNING: response hit max_tokens={max_tokens} — will attempt JSON repair")
        return content

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000, step_name: str = "", **_) -> dict:
        """Return a completion parsed as a JSON dict."""
        text = self.complete(system, user, max_tokens, step_name=step_name)
        return self._parse_json(text)

    def chat(self, messages: list[dict], max_tokens: int = 2000) -> str:
        """Fast conversational completion using gpt-4o-mini."""
        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=max_tokens,
                messages=messages,
            )
        except openai.AuthenticationError as e:
            raise RuntimeError(
                f"[LLMClient] OpenAI API key is invalid or revoked: {e}"
            ) from e
        except openai.RateLimitError as e:
            print(f"[LLMClient] Rate limit hit — waiting 60s before retry: {e}")
            time.sleep(60)
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=max_tokens,
                messages=messages,
            )
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

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": initial_message},
        ]

        for iteration in range(max_iterations):
            t0 = time.perf_counter()
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                )
            except openai.AuthenticationError as e:
                self._emit_trace(step_name, t0, None, False)
                raise RuntimeError(
                    f"[LLMClient] OpenAI API key is invalid or revoked: {e}"
                ) from e
            except openai.RateLimitError as e:
                print(f"[LLMClient] Rate limit hit in agent loop — waiting 60s: {e}")
                time.sleep(60)
                continue
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
                return {"parse_error": str(exc)}

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

        # Strategy B: roll back to last safe boundary outside any string,
        # strip trailing comma/colon, close structures
        truncated = text[:last_safe].rstrip().rstrip(",")
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

        # Strategy C: strip back to the outermost { and return minimal valid object
        first_brace = text.find('{')
        if first_brace != -1:
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
