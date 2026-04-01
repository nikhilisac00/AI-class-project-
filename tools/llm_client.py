"""
LLM Client — Anthropic Claude (claude-sonnet-4-6).

Provides two modes:
  - complete / complete_json : single-shot LLM call (synthesis, analysis)
  - agent_loop               : tool-use agentic loop (Claude decides what to call)
"""

import json
import re
import anthropic


class LLMClient:
    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.provider = "anthropic"
        self.model = "claude-sonnet-4-6"

    # ── Single-shot completions ───────────────────────────────────────────────

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000, **_) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return (message.content[0].text or "").strip()

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000, **_) -> dict:
        text = self.complete(system, user, max_tokens)
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
        message = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system,
            messages=convo,
        )
        return (message.content[0].text or "").strip()

    # ── Agentic tool-use loop ─────────────────────────────────────────────────

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
        Run an agentic tool-use loop. Claude decides which tools to call and when to stop.

        Args:
            system          : system prompt defining the agent's role and goal
            initial_message : the user message that starts the loop
            tools           : list of Anthropic tool definitions (name, description, input_schema)
            tool_executor   : dict mapping tool_name → callable(inputs: dict) → str
            max_tokens      : max tokens per LLM call
            max_iterations  : safety cap on tool-use rounds

        Returns:
            The agent's final text response (after all tool calls are complete).
        """
        messages = [{"role": "user", "content": initial_message}]

        for iteration in range(max_iterations):
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            )

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            # Done — no more tool calls
            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text.strip()
                return ""

            # Process tool_use blocks
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
