import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional

import dotenv

dotenv.load_dotenv()


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


_BASE_DIR = Path.home() / ".dolphi"


def _load_json_config() -> dict[str, Any]:
    path = Path(os.getenv("DOLPHI_CONFIG") or os.getenv("PORTFOLIO_AGENT_CONFIG", "config.json"))
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_path(*keys: str, default: Any = None) -> Any:
    current: Any = _load_json_config()
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _default_llm_provider() -> str:
    return str(os.getenv("LLM_PROVIDER") or _json_path("llm", "provider", default="ollama")).lower()


def _default_llm_model() -> str:
    return str(os.getenv("LLM_MODEL") or _json_path("llm", "model", default="llama3:8b"))


def _default_research_depth() -> str:
    return str(os.getenv("RESEARCH_DEPTH") or _json_path("research", "depth", default="standard")).lower()


@dataclass
class Config:
    llm_provider: str = field(default_factory=_default_llm_provider)
    llm_model: str = field(default_factory=_default_llm_model)
    ollama_endpoint: str = field(default_factory=lambda: os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: str(os.getenv("OLLAMA_MODEL") or _json_path("llm", "models", "ollama", default="llama3:8b")))
    cache_path: Path = field(default_factory=lambda: _ensure_dir(_BASE_DIR) / "cache.db")
    chroma_path: Path = field(default_factory=lambda: _ensure_dir(_BASE_DIR / "chroma_db"))
    decision_log_path: Path = field(default_factory=lambda: _ensure_dir(_BASE_DIR) / "decision_log.md")
    universe_cache_dir: Path = field(default_factory=lambda: _ensure_dir(_BASE_DIR / "universe"))
    universe_max_age_hours: int = 24
    alpha_vantage_key: Optional[str] = field(default_factory=lambda: os.getenv("ALPHA_VANTAGE_KEY"))
    newsapi_key: Optional[str] = field(default_factory=lambda: os.getenv("NEWSAPI_KEY"))
    brave_api_key: Optional[str] = field(default_factory=lambda: os.getenv("BRAVE_API_KEY"))
    searxng_base_url: Optional[str] = field(default_factory=lambda: os.getenv("SEARXNG_BASE_URL"))
    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openrouter_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY"))
    deepseek_api_key: Optional[str] = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY"))
    anthropic_api_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    api_timeout: int = 60
    research_depth: str = field(default_factory=_default_research_depth)
    max_retries: int = 5
    retry_base_delay: float = 1.0
    lru_ttl_seconds: int = 300
    sqlite_cache_ttl_hours: int = 1
    verbose: bool = False
    use_memory: bool = False
    skip_cache: bool = False
    mock_data: bool = False
