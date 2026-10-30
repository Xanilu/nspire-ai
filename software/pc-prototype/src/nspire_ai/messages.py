"""Validated role-tagged messages used by conversation-aware providers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

MessageRole = Literal["system", "user", "assistant"]
_ALLOWED_ROLES = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True, slots=True)
class Message:
    """A single text message with a role controlled by the application."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or self.role not in _ALLOWED_ROLES:
            raise ValueError("Message role is invalid.")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Message content cannot be empty.")


def validate_provider_messages(messages: Sequence[Message]) -> tuple[Message, ...]:
    """Validate the safe system/user/assistant shape sent to a provider."""
    if not isinstance(messages, (tuple, list)) or not messages:
        raise ValueError("Provider messages must be a non-empty sequence.")
    if any(not isinstance(message, Message) for message in messages):
        raise ValueError("Provider messages contain an invalid item.")
    roles = [message.role for message in messages]
    if roles[0] == "system":
        roles = roles[1:]
    if not roles or roles[-1] != "user":
        raise ValueError("Provider context must end with a user message.")
    if any(role not in {"user", "assistant"} for role in roles):
        raise ValueError("Provider context contains an invalid role.")
    if roles != ["user", "assistant"] * (len(roles) // 2) + (["user"] if len(roles) % 2 else []):
        raise ValueError("Provider context message roles are out of order.")
    return tuple(messages)
