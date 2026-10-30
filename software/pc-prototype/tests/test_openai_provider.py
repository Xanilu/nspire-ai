import httpx
import pytest

from nspire_ai.errors import ProviderError
from nspire_ai.providers.openai import OpenAIProvider


def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openai_request_and_response_parsing():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"status": "completed", "output": [{"content": [{"type": "output_text", "text": "Hello"}]}]})

    client = make_client(handler)
    try:
        result = OpenAIProvider("model-x", 7, api_key="test-secret", client=client).generate("question")
    finally:
        client.close()
    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert seen["auth"] == "Bearer test-secret"
    assert '"model":"model-x"' in seen["body"]
    assert '"input":"question"' in seen["body"]
    assert result.text == "Hello"
    assert result.provider == "openai"


def test_api_key_is_read_from_environment_and_not_in_errors(monkeypatch, caplog):
    secret = "sentinel-api-secret"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {secret}"
        return httpx.Response(401, json={"error": {"message": secret}})

    client = make_client(handler)
    try:
        with pytest.raises(ProviderError) as caught:
            OpenAIProvider(client=client).generate("question")
    finally:
        client.close()
    assert secret not in str(caught.value)
    assert secret not in caplog.text


def test_missing_api_key_fails_without_request(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="not configured"):
        OpenAIProvider().generate("question")


@pytest.mark.parametrize(
    "exception, message",
    [
        (httpx.ReadTimeout("sensitive timeout detail"), "timed out"),
        (httpx.ConnectError("sensitive network detail"), "unavailable"),
    ],
)
def test_timeout_and_network_errors_are_sanitized(exception, message):
    def handler(request):
        raise exception

    client = make_client(handler)
    try:
        with pytest.raises(ProviderError, match=message) as caught:
            OpenAIProvider(api_key="test", client=client).generate("question")
    finally:
        client.close()
    assert "sensitive" not in str(caught.value)


def test_http_error_is_sanitized():
    client = make_client(lambda request: httpx.Response(500, text="secret provider body"))
    try:
        with pytest.raises(ProviderError, match="request failed") as caught:
            OpenAIProvider(api_key="test", client=client).generate("question")
    finally:
        client.close()
    assert "secret" not in str(caught.value)


def test_malformed_json_response_is_sanitized():
    client = make_client(lambda request: httpx.Response(200, text="not-json-secret"))
    try:
        with pytest.raises(ProviderError, match="invalid response") as caught:
            OpenAIProvider(api_key="test", client=client).generate("question")
    finally:
        client.close()
    assert "not-json-secret" not in str(caught.value)


@pytest.mark.parametrize("payload", [None, [], {}, {"status": "completed", "output": "bad"}, {"status": "completed", "output": [{"content": "bad"}]}, {"status": "completed", "output": [{"content": [{"type": "output_text", "text": 4}]}]}])
def test_invalid_response_shapes_fail_safely(payload):
    client = make_client(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ProviderError, match="invalid response"):
            OpenAIProvider(api_key="test", client=client).generate("question")
    finally:
        client.close()


@pytest.mark.parametrize("payload", [{"status": "completed", "output": []}, {"status": "completed", "output": [{"content": []}]}, {"status": "completed", "output": [{"content": [{"type": "output_text", "text": "  "}]}]}])
def test_empty_or_missing_model_output_is_rejected(payload):
    client = make_client(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ProviderError):
            OpenAIProvider(api_key="test", client=client).generate("question")
    finally:
        client.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "incomplete", "output": [{"content": [{"type": "output_text", "text": "Partial answer"}]}]},
        {"status": "failed", "output": [{"content": [{"type": "output_text", "text": "Partial answer"}]}]},
        {"output": [{"content": [{"type": "output_text", "text": "Partial answer"}]}]},
        {"status": "queued", "output": [{"content": [{"type": "output_text", "text": "Partial answer"}]}]},
        {"status": {"unexpected": "provider-private"}, "output": [{"content": [{"type": "output_text", "text": "Partial answer"}]}]},
        {"status": ["completed"], "output": [{"content": [{"type": "output_text", "text": "Partial answer"}]}]},
    ],
)
def test_only_completed_status_can_return_output_text(payload):
    client = make_client(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ProviderError) as caught:
            OpenAIProvider(api_key="test", client=client).generate("question")
    finally:
        client.close()
    assert "Partial answer" not in str(caught.value)
    assert "provider-private" not in str(caught.value)


def test_incomplete_max_output_tokens_response_never_returns_partial_text():
    payload = {
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [{"content": [{"type": "output_text", "text": "Partial answer"}]}],
    }
    client = make_client(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ProviderError) as caught:
            OpenAIProvider(api_key="test", client=client).generate("question")
    finally:
        client.close()
    assert "Partial answer" not in str(caught.value)
    assert "max_output_tokens" not in str(caught.value)
