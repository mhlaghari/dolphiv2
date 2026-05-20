from dolphi.llm import OpenAICompatibleClient


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
