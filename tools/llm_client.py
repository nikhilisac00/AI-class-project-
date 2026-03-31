"""
LLM Client — Anthropic Claude (claude-sonnet-4-6).
"""

import json
import anthropic


class LLMClient:
    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.provider = "anthropic"
        self.model = "claude-sonnet-4-6"

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000, **_) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[
                {"role": "user", "content": user},
            ],
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
            # Try extracting the first JSON object/array from the response
            import re
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
        """
        Fast conversational completion using claude-haiku-4-5.
        messages: list of {"role": "system"|"user"|"assistant", "content": str}
        """
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        convo = [m for m in messages if m["role"] != "system"]
        message = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system,
            messages=convo,
        )
        return (message.content[0].text or "").strip()


def make_client(api_key: str) -> LLMClient:
    return LLMClient(api_key=api_key)
