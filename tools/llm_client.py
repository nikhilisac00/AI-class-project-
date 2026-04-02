"""
LLM Client — OpenAI GPT-4o.

Provides two modes:
  - complete / complete_json : single-shot LLM call (synthesis, analysis)
  - agent_loop               : tool-use agentic loop (GPT decides what to call)
"""

import json
import re
from openai import OpenAI


class LLMClient:
    def __init__(self, api_key: str):
        self._client = OpenAI(api_key=api_key)
        self.provider = "openai"
        self.model = "gpt-4o"

    # ── Single-shot completions ───────────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000,
                 thinking_tokens: int = 0, **_) -> str:
        """
        Single-shot text completion.
        thinking_tokens is accepted for API compatibility but not used
        (OpenAI models reason via system prompt instructions).
        """
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
        """Fast conversational completion using gpt-4o-mini."""
        openai_messages = []
        for m in messages:
            openai_messages.append({"role": m["role"], "content": m["content"]})

        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            messages=openai_messages,
        )
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
        Run an agentic tool-use loop. GPT decides which tools to call and when to stop.

        Args:
            system          : system prompt defining the agent's role and goal
            initial_message : the user message that starts the loop
            tools           : list of tool definitions (Anthropic or OpenAI format accepted)
            tool_executor   : dict mapping tool_name -> callable(inputs: dict) -> str
            max_tokens      : max tokens per LLM call
            max_iterations  : safety cap on tool-use rounds

        Returns:
            The agent's final text response (after all tool calls are complete).
        """
        openai_tools = self._convert_tools(tools)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": initial_message},
        ]

        for iteration in range(max_iterations):
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
                tools=openai_tools,
            )

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
