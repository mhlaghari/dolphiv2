from __future__ import annotations

import logging
from typing import Any

from .json_mixin import JsonGeneratingClient
from .ollama_client import OllamaClient
from .openai_compatible import OpenAICompatibleClient

logger = logging.getLogger(__name__)

_OPENAI_COMPATIBLE = {
    "openai": ("https://api.openai.com/v1", "openai_api_key"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter_api_key"),
    "deepseek": ("https://api.deepseek.com", "deepseek_api_key"),
}


def create_llm_client(config: Any) -> JsonGeneratingClient:
    provider = str(getattr(config, "llm_provider", "ollama")).lower()
    model = str(getattr(config, "llm_model", getattr(config, "ollama_model", "llama3:8b")))

    if provider == "ollama":
        return OllamaClient(endpoint=config.ollama_endpoint, model=model)

    if provider in _OPENAI_COMPATIBLE:
        base_url, key_attr = _OPENAI_COMPATIBLE[provider]
        api_key = getattr(config, key_attr, None)
        if not api_key:
            logger.error("%s requires %s in .env", provider, key_attr.upper())
            raise SystemExit(1)
        return OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            provider_name=provider,
        )

    logger.error("Unsupported LLM provider: %s", provider)
    raise SystemExit(1)
