"""In-memory conversation lifecycle and provider orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock, RLock
from uuid import uuid4

from nspire_ai.config import Settings
from nspire_ai.context import ContextManager
from nspire_ai.errors import (
    ConversationNotFoundError,
    ConversationProviderError,
    ContextLimitError,
)
from nspire_ai.messages import Message
from nspire_ai.providers.base import AIProvider, ProviderResponse
from nspire_ai.providers.registry import create_provider


@dataclass(slots=True)
class _Conversation:
    messages: list[Message] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)


class InMemoryConversationStore:
    """Process-local store; contents disappear when the process exits."""

    def __init__(self, *, max_conversations: int = 1_000) -> None:
        if type(max_conversations) is not int or max_conversations < 1:
            raise ValueError("Maximum conversations must be a positive integer.")
        self._max_conversations = max_conversations
        self._items: dict[str, _Conversation] = {}
        self._lock = RLock()

    def create(self) -> str:
        with self._lock:
            if len(self._items) >= self._max_conversations:
                raise ContextLimitError("The in-memory conversation limit has been reached.")
            conversation_id = uuid4().hex
            self._items[conversation_id] = _Conversation()
            return conversation_id

    def get(self, conversation_id: str) -> _Conversation:
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ConversationNotFoundError("Conversation was not found.")
        with self._lock:
            conversation = self._items.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("Conversation was not found.")
        return conversation

    def ensure_current(self, conversation_id: str, conversation: _Conversation) -> None:
        with self._lock:
            if self._items.get(conversation_id) is not conversation:
                raise ConversationNotFoundError("Conversation was not found.")

    def delete(self, conversation_id: str) -> None:
        conversation = self.get(conversation_id)
        with conversation.lock:
            with self._lock:
                if self._items.get(conversation_id) is not conversation:
                    raise ConversationNotFoundError("Conversation was not found.")
                del self._items[conversation_id]


class ConversationEngine:
    """Manage independent conversations and commit only successful turns."""

    def __init__(
        self,
        provider: AIProvider,
        *,
        system_context: str = "",
        max_input_chars: int = 10_000,
        max_context_chars: int = 24_000,
        max_context_messages: int = 32,
        max_history_messages: int = 200,
        max_history_chars: int = 100_000,
        max_conversations: int = 1_000,
    ) -> None:
        if type(max_input_chars) is not int or max_input_chars < 1:
            raise ValueError("Maximum input characters must be a positive integer.")
        if type(max_history_messages) is not int or max_history_messages < 2 or max_history_messages % 2:
            raise ValueError("Maximum stored history messages must be an even integer of at least two.")
        if type(max_history_chars) is not int or max_history_chars < 1:
            raise ValueError("Maximum stored history characters must be a positive integer.")
        self._provider = provider
        self._max_input_chars = max_input_chars
        self._max_history_messages = max_history_messages
        self._max_history_chars = max_history_chars
        self._store = InMemoryConversationStore(max_conversations=max_conversations)
        self._context = ContextManager(
            system_context=system_context,
            max_context_chars=max_context_chars,
            max_context_messages=max_context_messages,
        )

    def create_conversation(self) -> str:
        """Create and return a new opaque conversation ID."""
        return self._store.create()

    def get_history(self, conversation_id: str) -> tuple[Message, ...]:
        """Return a snapshot of the retained user/assistant message history."""
        conversation = self._store.get(conversation_id)
        with conversation.lock:
            self._store.ensure_current(conversation_id, conversation)
            return tuple(conversation.messages)

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation and its retained history."""
        self._store.delete(conversation_id)

    def send_message(self, conversation_id: str, content: str) -> Message:
        """Submit user text and append the turn only after a valid provider reply."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Message cannot be empty.")
        if len(content) > self._max_input_chars:
            raise ValueError("Message exceeds the configured input length limit.")

        conversation = self._store.get(conversation_id)
        with conversation.lock:
            self._store.ensure_current(conversation_id, conversation)
            context = self._context.build(conversation.messages, content)
            try:
                result = self._generate(context)
            except Exception:
                raise ConversationProviderError("The configured provider could not process the message.") from None
            if (
                not isinstance(result, ProviderResponse)
                or not isinstance(result.text, str)
                or not result.text.strip()
                or len(result.text) > self._context.max_context_chars
                or not isinstance(result.provider, str)
                or not result.provider.strip()
            ):
                raise ConversationProviderError("The configured provider returned an invalid response.")

            user_message = Message("user", content)
            assistant_message = Message("assistant", result.text)
            turn_chars = len(user_message.content) + len(assistant_message.content)
            if turn_chars > self._max_history_chars:
                raise ContextLimitError("The completed turn exceeds the stored history limit.")
            conversation.messages.extend((user_message, assistant_message))
            while (
                len(conversation.messages) > self._max_history_messages
                or sum(len(message.content) for message in conversation.messages) > self._max_history_chars
            ):
                del conversation.messages[:2]
            return assistant_message

    def _generate(self, messages: tuple[Message, ...]) -> ProviderResponse:
        generate_messages = getattr(self._provider, "generate_messages", None)
        if callable(generate_messages):
            return generate_messages(messages)
        # Legacy AIProvider implementations keep working through the original seam.
        prompt = "\n\n".join(f"{message.role.upper()}:\n{message.content}" for message in messages)
        return self._provider.generate(prompt)


def create_conversation_engine(
    settings: Settings,
    *,
    provider: AIProvider | None = None,
) -> ConversationEngine:
    """Build an engine using the configured provider and conversation limits."""
    return ConversationEngine(
        provider if provider is not None else create_provider(settings),
        system_context=settings.system_context,
        max_input_chars=settings.max_input_chars,
        max_context_chars=settings.max_context_chars,
        max_context_messages=settings.max_context_messages,
        max_history_messages=settings.max_history_messages,
        max_history_chars=settings.max_history_chars,
        max_conversations=settings.max_conversations,
    )
