"""Provider contract and response type."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    text: str
    provider: str


class AIProvider(Protocol):
    """Minimal synchronous seam for providers; implementations may wrap I/O later."""

    @property
    def name(self) -> str: ...

    def generate(self, prompt: str) -> ProviderResponse: ...
