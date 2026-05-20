"""Native Anthropic Messages-API client.

Mirrors the contract of :class:`OpenAICompatibleClient` but speaks
Anthropic's Messages API directly via ``requests`` so the package
doesn't carry an ``anthropic`` SDK dependency.

Until v0.2.0 Anthropic models were reachable only via OpenRouter
(``openrouter:anthropic/claude-sonnet-4-6``). Direct native access is
cleaner for the eval harness (``python -m dolphi.eval``) and avoids
the extra hop's latency / cost markup.

Endpoint: ``POST https://api.anthropic.com/v1/messages``
Required headers: ``x-api-key``, ``anthropic-version``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from .json_mixin import JsonGeneratingClient

logger = logging.getLogger(__name__)

ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"


class AnthropicClient(JsonGeneratingClient):
    """HTTP client for Anthropic's Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 120,
        max_tokens: int = 4096,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_tokens = max_tokens

    def generate(self, prompt: str, system: Optional[str] = None, temperature: float = 0.3) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        response = requests.post(
            f"{self._base_url}/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return _extract_text(response.json())


def _extract_text(body: Any) -> str:
    """Pull the assistant text out of a Messages-API response.

    Defensive: returns ``""`` (and logs a warning) on any unexpected shape
    rather than raising, so the caller's ``generate_json`` retry / repair
    path still has a chance to recover.
    """
    if not isinstance(body, dict):
        logger.warning("Anthropic response was not a dict: %r", type(body))
        return ""
    content = body.get("content")
    if not isinstance(content, list) or not content:
        logger.warning("Anthropic response missing 'content' array; keys=%s", list(body.keys())[:8])
        return ""
    first = content[0]
    if not isinstance(first, dict):
        return ""
    if first.get("type") != "text":
        # Tool-use / image / other content blocks aren't expected here yet —
        # the eval harness only uses text generation.
        logger.warning("Anthropic first content block has unexpected type=%s", first.get("type"))
        return ""
    return str(first.get("text", ""))
