"""
LLM Client — OpenAI (gpt-4o).

Provides three interaction modes:
  - complete()        : single-turn text completion
  - complete_json()   : single-turn completion parsed as JSON
  - agent_loop_json() : multi-turn tool-use loop (for autonomous agents)
"""

import json
import re

import openai


class LLMClient:
    """Thin wrapper around the OpenAI API for the agent pipeline."""

    def __init__(self, api_key: str):
        self._client = openai.OpenAI(api_key=api_key)
        self.provider = "openai"
        self.model = "gpt-4o"

    # ── Single-turn completions ──────────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000, **_) -> str:
        """Return a plain-text completion."""
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000, **_) -> dict:
        """Return a completion parsed as a JSON dict."""
        text = self.complete(system, user, max_tokens)
        return self._parse_json(text)

    def chat(self, messages: list[dict], max_tokens: int = 2000) -> str:
        """Fast conversational completion using gpt-4o-mini."""
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            messages=messages,
        )
        return (response.choices[0].message.content or "").strip()

    # ── Tool-use agent loop ──────────────────────────────────────────────────

    def agent_loop_json(
        self,
        system: str,
        initial_message: str,
        tools: list[dict],
        tool_executor: dict,
        max_tokens: int = 4096,
        max_iterations: int = 15,
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
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
                tools=openai_tools if openai_tools else None,
            )

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
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            raise ValueError(
                f"LLM returned non-JSON response. "
                f"First 200 chars: {text[:200]!r}"
            )


def make_client(api_key: str) -> LLMClient:
    """Factory function for creating an LLMClient."""
    return LLMClient(api_key=api_key)
