import json

import httpx

from words_generator.api.client import APIConfig, OpenAICompatibleClient
from words_generator.models.sampling import SamplingSettings


def test_chat_completions_request_uses_v1_path_and_sampling() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "forest"}}]},
        )

    client = OpenAICompatibleClient(
        APIConfig("http://localhost:9000", "local-model", "secret"),
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.generate_word(
            system_prompt="only one word",
            user_prompt="one noun",
            sampling=SamplingSettings(temperature=0.7, max_tokens=16),
        )
    finally:
        client.close()

    assert result == "forest"
    assert str(requests[0].url) == "http://localhost:9000/v1/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    body = json.loads(requests[0].content)
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 16
    assert body["stream"] is False


def test_models_endpoint_accepts_v1_base_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:9000/v1/models"
        return httpx.Response(200, json={"data": [{"id": "model-a"}, {"id": "model-b"}]})

    client = OpenAICompatibleClient(
        APIConfig("http://localhost:9000/v1/", "model-a"),
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.list_models() == ["model-a", "model-b"]
    finally:
        client.close()
