"""
LLM Client Abstraction
Supports Anthropic (claude-opus-4-6 + extended thinking) and OpenAI (gpt-4o / o3).
All agents call this instead of the SDK directly.
"""

import json
from dataclasses import dataclass
from enum import Enum


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI    = "openai"


@dataclass
class LLMClient:
    provider:   Provider
    api_key:    str
    model:      str          # set automatically based on provider
    _client:    object = None

    def __post_init__(self):
        if self.provider == Provider.ANTHROPIC:
            import anthropic as _ant
            self._client = _ant.Anthropic(api_key=self.api_key)
        else:
            import openai as _oai
            self._client = _oai.OpenAI(api_key=self.api_key)

    def complete(
        self,
        system: str,
        user:   str,
        max_tokens:    int  = 8000,
        thinking_tokens: int = 5000,   # Anthropic only — ignored for OpenAI
    ) -> str:
        """
        Send a system + user message and return the text response.
        Anthropic: uses extended thinking for deeper reasoning.
        OpenAI: uses o3 reasoning_effort=high or gpt-4o.
        """
        if self.provider == Provider.ANTHROPIC:
            return self._anthropic_complete(system, user, max_tokens, thinking_tokens)
        else:
            return self._openai_complete(system, user, max_tokens)

    def _anthropic_complete(self, system, user, max_tokens, thinking_tokens) -> str:
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

    def _openai_complete(self, system, user, max_tokens) -> str:
        # o3/o3-mini use developer role instead of system
        is_reasoning = self.model.startswith("o")
        messages = []
        if is_reasoning:
            messages.append({"role": "developer", "content": system})
        else:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        kwargs = dict(
            model=self.model,
            messages=messages,
            max_completion_tokens=max_tokens,
        )
        if is_reasoning:
            kwargs["reasoning_effort"] = "high"

        response = self._client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()

    def complete_json(
        self,
        system: str,
        user:   str,
        max_tokens:    int = 8000,
        thinking_tokens: int = 5000,
    ) -> dict:
        """
        Like complete(), but strips markdown fences and parses JSON.
        Returns dict, or {"parse_error": ..., "raw_response": ...} on failure.
        """
        text = self.complete(system, user, max_tokens, thinking_tokens)

        # Strip ```json ... ``` fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            return {"parse_error": str(e), "raw_response": text}


def make_client(provider: str, api_key: str) -> LLMClient:
    """
    Factory. provider is 'anthropic' or 'openai'.
    Picks the best available model for each provider.
    """
    if provider == "openai":
        return LLMClient(
            provider=Provider.OPENAI,
            api_key=api_key,
            model="o3",          # best reasoning; falls back gracefully
        )
    else:
        return LLMClient(
            provider=Provider.ANTHROPIC,
            api_key=api_key,
            model="claude-opus-4-6",
        )
