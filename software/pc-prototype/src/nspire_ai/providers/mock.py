"""Local deterministic provider for smoke tests and offline development."""

from nspire_ai.errors import ProviderError
from nspire_ai.messages import Message, validate_provider_messages
from nspire_ai.providers.base import ProviderResponse
from collections.abc import Iterator


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

    def generate_messages(self, messages: tuple[Message, ...]) -> ProviderResponse:
        validated = validate_provider_messages(messages)
        latest_user_message = next(message for message in reversed(validated) if message.role == "user")
        return self.generate(latest_user_message.content)

    def stream(self, prompt: str) -> Iterator[str]:
        text = self.generate(prompt).text
        for character in text:
            yield character

    def stream_messages(self, messages: tuple[Message, ...]) -> Iterator[str]:
        validated = validate_provider_messages(messages)
        latest_user_message = next(message for message in reversed(validated) if message.role == "user")
        yield from self.stream(latest_user_message.content)
