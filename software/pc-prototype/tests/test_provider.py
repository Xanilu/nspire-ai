from nspire_ai.errors import ProviderError
from nspire_ai.providers.base import AIProvider
from nspire_ai.providers.mock import MockProvider


def test_mock_provider_satisfies_contract():
    provider: AIProvider = MockProvider()
    response = provider.generate("hello")
    assert response.provider == "mock"
    assert "hello" in response.text


def test_mock_provider_rejects_blank_prompt():
    try:
        MockProvider().generate("  ")
    except ProviderError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("Expected blank prompt to fail")
