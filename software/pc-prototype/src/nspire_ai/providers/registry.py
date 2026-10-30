"""Provider registry and configuration-based factory."""

from __future__ import annotations

from collections.abc import Callable

from nspire_ai.config import Settings
from nspire_ai.errors import ConfigurationError
from nspire_ai.providers.base import AIProvider
from nspire_ai.providers.mock import MockProvider
from nspire_ai.providers.openai import OpenAIProvider

ProviderBuilder = Callable[[Settings], AIProvider]


class ProviderRegistry:
    def __init__(self) -> None:
        self._builders: dict[str, ProviderBuilder] = {}

    def register(self, name: str, builder: ProviderBuilder) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Provider name cannot be empty.")
        if normalized in self._builders:
            raise ValueError(f"Provider '{normalized}' is already registered.")
        self._builders[normalized] = builder

    def create(self, settings: Settings) -> AIProvider:
        try:
            builder = self._builders[settings.provider]
        except KeyError as exc:
            raise ConfigurationError(f"Unsupported provider '{settings.provider}'.") from exc
        return builder(settings)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._builders)


def _build_mock(settings: Settings) -> AIProvider:
    return MockProvider()


def _build_openai(settings: Settings) -> AIProvider:
    return OpenAIProvider(model=settings.model, timeout=settings.request_timeout)


DEFAULT_PROVIDER_REGISTRY = ProviderRegistry()
DEFAULT_PROVIDER_REGISTRY.register("mock", _build_mock)
DEFAULT_PROVIDER_REGISTRY.register("openai", _build_openai)


def create_provider(settings: Settings, registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY) -> AIProvider:
    return registry.create(settings)
