"""Provider contract and response type."""

from dataclasses import dataclass
from collections.abc import Iterator, Sequence
from typing import Protocol

from nspire_ai.messages import Message


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    text: str
    provider: str


class AIProvider(Protocol):
    """Minimal synchronous seam for providers; implementations may wrap I/O later."""

    @property
    def name(self) -> str: ...

    def generate(self, prompt: str) -> ProviderResponse: ...


class StreamingAIProvider(Protocol):
    """Optional synchronous streaming capability; chunks are text fragments."""

    def stream(self, prompt: str) -> Iterator[str]: ...

    def stream_messages(self, messages: Sequence[Message]) -> Iterator[str]: ...
