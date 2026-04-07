"""
LLM Client — OpenAI (gpt-4o).
"""

import json
import openai


class LLMClient:
    def __init__(self, api_key: str):
        self._client = openai.OpenAI(api_key=api_key)
        self.provider = "openai"
        self.model = "gpt-4o"

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000, **_) -> str:
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
        Fast conversational completion using gpt-4o-mini.
        messages: list of {"role": "system"|"user"|"assistant", "content": str}
        """
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            messages=messages,
        )
        return (response.choices[0].message.content or "").strip()


def make_client(api_key: str) -> LLMClient:
    return LLMClient(api_key=api_key)
