from __future__ import annotations

import logging
import subprocess
from typing import Any, Optional

import requests

from .json_mixin import JsonGeneratingClient

logger = logging.getLogger(__name__)


class OllamaClient(JsonGeneratingClient):
    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "llama3:8b"):
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._ensure_running()
        self._ensure_model()

    def _ensure_running(self) -> None:
        try:
            resp = requests.get(f"{self._endpoint}/api/tags", timeout=5)
            resp.raise_for_status()
        except requests.ConnectionError:
            logger.error(
                "Ollama is not running at %s.\n"
                "  Start it with: ollama serve\n"
                "  Then pull a model: ollama pull %s",
                self._endpoint, self._model,
            )
            raise SystemExit(1) from None

    def _ensure_model(self) -> None:
        try:
            resp = requests.get(f"{self._endpoint}/api/tags", timeout=10)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            installed = {m.get("name") for m in models}
            if self._model not in installed and f"{self._model}:latest" not in installed:
                logger.info("Model %s not found locally. Pulling...", self._model)
                subprocess.run(
                    ["ollama", "pull", self._model],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.info("Model %s pulled successfully.", self._model)
        except subprocess.CalledProcessError:
            logger.warning("Auto-pull failed. Please run: ollama pull %s", self._model)

    def generate(self, prompt: str, system: Optional[str] = None, temperature: float = 0.3) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        resp = requests.post(
            f"{self._endpoint}/api/generate",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

