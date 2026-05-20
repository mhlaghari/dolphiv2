from __future__ import annotations

from typing import Optional

import requests

from .json_mixin import JsonGeneratingClient


class OpenAICompatibleClient(JsonGeneratingClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        provider_name: str,
        timeout: int = 120,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._provider_name = provider_name
        self._timeout = timeout

    def generate(self, prompt: str, system: Optional[str] = None, temperature: float = 0.3) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "stream": False,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
