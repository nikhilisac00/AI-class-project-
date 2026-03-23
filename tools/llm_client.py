"""
LLM Client — Anthropic Claude with extended thinking.
Provides a simple wrapper so agents don't depend on the raw SDK.
"""

import json
import re
import anthropic


MODEL = "claude-opus-4-6"


class LLMClient:
    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.provider = "anthropic"
        self.model = MODEL

    def complete(self, system: str, user: str,
                 max_tokens: int = 10000, thinking_tokens: int = 6000, **_) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            thinking={"type": "enabled", "budget_tokens": thinking_tokens},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text.strip()
        return ""

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 8000, thinking_tokens: int = 5000, **_) -> dict:
        text = self.complete(system, user, max_tokens, thinking_tokens)
        # Strip markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            return {"parse_error": str(e), "raw_response": text}


def make_client(api_key: str) -> LLMClient:
    return LLMClient(api_key=api_key)
