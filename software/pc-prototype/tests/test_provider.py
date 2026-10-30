import pytest

from nspire_ai.config import Settings
from nspire_ai.errors import ConfigurationError, ProviderError
from nspire_ai.providers.base import AIProvider
from nspire_ai.providers.mock import MockProvider
from nspire_ai.providers.registry import ProviderRegistry, create_provider


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


def test_registry_and_factory_select_mock_and_openai():
    registry = ProviderRegistry()
    registry.register("mock", lambda settings: MockProvider())
    assert registry.names == ("mock",)
    assert create_provider(Settings(), registry).name == "mock"
    assert create_provider(Settings(provider="openai")).name == "openai"
    with pytest.raises(ValueError):
        registry.register("mock", lambda settings: MockProvider())
    with pytest.raises(ConfigurationError):
        create_provider(Settings(provider="missing"), registry)
