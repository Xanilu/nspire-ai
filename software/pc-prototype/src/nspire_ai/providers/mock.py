"""Local deterministic provider for smoke tests and offline development."""

from nspire_ai.errors import ProviderError
from nspire_ai.providers.base import ProviderResponse


class MockProvider:
    @property
    def name(self) -> str:
        return "mock"

    def generate(self, prompt: str) -> ProviderResponse:
        if not prompt.strip():
            raise ProviderError("Prompt cannot be empty.")
        return ProviderResponse(
            text=f"Mock provider received: {prompt.strip()}", provider=self.name
        )
