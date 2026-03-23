"""
LLM Client — OpenAI only (o3 reasoning model)
"""

import json
from dataclasses import dataclass


@dataclass
class LLMClient:
    api_key: str
    model:   str = "o3"
    _client: object = None

    def __post_init__(self):
        import openai
        self._client = openai.OpenAI(api_key=self.api_key)

    def complete(self, system: str, user: str,
                 max_tokens: int = 8000, **_) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user",      "content": user},
            ],
            max_completion_tokens=max_tokens,
            reasoning_effort="high",
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
        except json.JSONDecodeError as e:
            return {"parse_error": str(e), "raw_response": text}


def make_client(api_key: str) -> LLMClient:
    return LLMClient(api_key=api_key)
