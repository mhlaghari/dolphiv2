from dolphi.config import Config


def test_config_loads_llm_provider_and_model_from_json(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """
{
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash"
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOLPHI_CONFIG", str(config_path))

    config = Config()

    assert config.llm_provider == "deepseek"
    assert config.llm_model == "deepseek-v4-flash"


def test_config_loads_optional_llm_provider_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")

    config = Config()

    assert config.openai_api_key == "openai-key"
    assert config.openrouter_api_key == "openrouter-key"
    assert config.deepseek_api_key == "deepseek-key"
    assert config.anthropic_api_key == "claude-key"
