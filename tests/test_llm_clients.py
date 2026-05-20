from types import SimpleNamespace

import pytest

from dolphi.llm import AnthropicClient, OpenAICompatibleClient, create_llm_client


def test_openai_compatible_client_calls_chat_completions(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"score": 0.8}'}}]}

    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return Response()

    monkeypatch.setattr("requests.post", fake_post)

    client = OpenAICompatibleClient(
        base_url="https://api.deepseek.com",
        api_key="deepseek-key",
        model="deepseek-v4-flash",
        provider_name="deepseek",
    )

    result = client.generate_json("Score this", system="Return JSON")

    assert result == {"score": 0.8}
    assert calls[0][0] == "https://api.deepseek.com/chat/completions"
    assert calls[0][1]["Authorization"] == "Bearer deepseek-key"
    assert calls[0][2]["model"] == "deepseek-v4-flash"
    assert calls[0][2]["messages"][0] == {"role": "system", "content": "Return JSON"}


# ---------- Anthropic native client ------------------------------------------


class _StubResponse:
    def __init__(self, body, status_code: int = 200):
        self._body = body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


def test_anthropic_client_posts_to_messages_endpoint(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return _StubResponse({"content": [{"type": "text", "text": "ok"}]})

    monkeypatch.setattr("requests.post", fake_post)

    client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
    client.generate("hello", system="be brief", temperature=0.2)

    url, headers, body, _timeout = calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["content-type"] == "application/json"
    assert body["model"] == "claude-sonnet-4-6"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["system"] == "be brief"
    assert body["temperature"] == 0.2
    assert "max_tokens" in body


def test_anthropic_client_returns_text_from_content_array(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _StubResponse({"content": [{"type": "text", "text": "the answer"}]}),
    )
    client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
    assert client.generate("q") == "the answer"


def test_anthropic_client_returns_empty_on_empty_content(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _StubResponse({"content": []}))
    client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
    assert client.generate("q") == ""


def test_anthropic_client_returns_empty_on_non_text_block(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _StubResponse({"content": [{"type": "tool_use", "id": "x"}]}),
    )
    client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
    assert client.generate("q") == ""


def test_anthropic_client_returns_empty_on_unexpected_shape(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _StubResponse({"error": {"message": "rate limited"}}),
    )
    client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
    assert client.generate("q") == ""


def test_anthropic_client_raises_on_http_error(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _StubResponse({}, status_code=429))
    client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
    import requests
    with pytest.raises(requests.HTTPError):
        client.generate("q")


def test_anthropic_client_omits_system_when_not_supplied(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["json"] = json
        return _StubResponse({"content": [{"type": "text", "text": "ok"}]})

    monkeypatch.setattr("requests.post", fake_post)
    AnthropicClient(api_key="sk", model="m").generate("hi")
    assert "system" not in captured["json"]


# ---------- factory routing ---------------------------------------------------


def test_factory_routes_anthropic_provider(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _StubResponse({"content": [{"type": "text", "text": "ok"}]}),
    )
    config = SimpleNamespace(
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        anthropic_api_key="sk-ant-test",
    )
    client = create_llm_client(config)
    assert isinstance(client, AnthropicClient)


def test_factory_anthropic_missing_key_exits():
    config = SimpleNamespace(
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        anthropic_api_key=None,
    )
    with pytest.raises(SystemExit):
        create_llm_client(config)
