"""Deterministic, character-bounded context construction for conversations."""

from __future__ import annotations

from collections.abc import Sequence

from nspire_ai.errors import ContextLimitError
from nspire_ai.messages import Message


class ContextManager:
    """Preserve system context and the newest complete turns within hard limits.

    Character counts use Python string length and count message content only.
    When context is tight, the oldest complete user/assistant turns are removed.
    The configured system message is always retained; if it and the current
    input cannot fit, construction fails instead of dropping system context.
    """

    def __init__(
        self,
        *,
        system_context: str = "",
        max_context_chars: int = 24_000,
        max_context_messages: int = 32,
    ) -> None:
        if not isinstance(system_context, str):
            raise ValueError("System context must be text.")
        if type(max_context_chars) is not int or max_context_chars < 1:
            raise ValueError("Maximum context characters must be a positive integer.")
        if type(max_context_messages) is not int or max_context_messages < 1:
            raise ValueError("Maximum context messages must be a positive integer.")
        if system_context and not system_context.strip():
            raise ValueError("System context cannot contain only whitespace.")
        if len(system_context) >= max_context_chars:
            raise ValueError("System context must leave room for a user message.")
        if system_context and max_context_messages < 2:
            raise ValueError("Context message limit must leave room for system and user messages.")
        self._system = Message("system", system_context) if system_context else None
        self._max_chars = max_context_chars
        self._max_messages = max_context_messages

    @property
    def max_context_chars(self) -> int:
        return self._max_chars

    def build(self, history: Sequence[Message], current_input: str) -> tuple[Message, ...]:
        """Return required system context, a suffix of whole turns, and current input."""
        current = Message("user", current_input)
        if len(current.content) > self._max_chars:
            raise ContextLimitError("Input does not fit the configured context limit.")

        if len(history) % 2:
            raise ValueError("Conversation history must contain complete turns.")
        for index in range(0, len(history), 2):
            if history[index].role != "user" or history[index + 1].role != "assistant":
                raise ValueError("Conversation history roles are invalid.")

        selected: list[Message] = []
        required = ([self._system] if self._system is not None else []) + [current]
        if not self._fits(required):
            raise ContextLimitError("Required system and user context exceeds configured limits.")

        for index in range(len(history) - 2, -1, -2):
            turn = list(history[index : index + 2])
            candidate_history = turn + selected
            candidate = ([self._system] if self._system is not None else []) + candidate_history + [current]
            if not self._fits(candidate):
                break
            selected = candidate_history

        return tuple(([self._system] if self._system is not None else []) + selected + [current])

    def _fits(self, messages: Sequence[Message]) -> bool:
        return (
            len(messages) <= self._max_messages
            and sum(len(message.content) for message in messages) <= self._max_chars
        )
