"""Conversation lifecycle and provider orchestration."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock, RLock
from typing import Iterator

from nspire_ai.config import Settings
from nspire_ai.context import ContextManager
from nspire_ai.errors import (
    ContextLimitError,
    ConversationNotFoundError,
    ConversationProviderError,
    ConversationStorageError,
    ProviderError,
)
from nspire_ai.messages import Message
from nspire_ai.providers.base import AIProvider, ProviderResponse
from nspire_ai.providers.registry import create_provider
from nspire_ai.storage import (
    ConversationStore,
    ConversationSummary,
    InMemoryConversationStore,
    SQLiteConversationStore,
    validate_conversation_id,
)


def _close_stream_resources(iterator, source) -> None:
    """Close each distinct provider stream object once."""
    seen: set[int] = set()
    for resource in (iterator, source):
        if resource is None or id(resource) in seen:
            continue
        seen.add(id(resource))
        close = getattr(resource, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


class ConversationEngine:
    """Manage independent conversations and commit only successful turns."""

    def __init__(
        self,
        provider: AIProvider,
        *,
        system_context: str = "",
        max_input_chars: int = 10_000,
        max_context_chars: int = 24_000,
        max_stream_chars: int | None = None,
        max_stream_chunk_chars: int = 4_096,
        max_context_messages: int = 32,
        max_history_messages: int = 200,
        max_history_chars: int = 100_000,
        max_conversations: int = 1_000,
        store: ConversationStore | None = None,
    ) -> None:
        if type(max_input_chars) is not int or max_input_chars < 1:
            raise ValueError("Maximum input characters must be a positive integer.")
        if type(max_history_messages) is not int or max_history_messages < 2 or max_history_messages % 2:
            raise ValueError("Maximum stored history messages must be an even integer of at least two.")
        if type(max_history_chars) is not int or max_history_chars < 1:
            raise ValueError("Maximum stored history characters must be a positive integer.")
        if max_stream_chars is None:
            max_stream_chars = max_context_chars
        if type(max_stream_chars) is not int or max_stream_chars < 1:
            raise ValueError("Maximum streamed output characters must be a positive integer.")
        if type(max_stream_chunk_chars) is not int or max_stream_chunk_chars < 1:
            raise ValueError("Maximum stream chunk characters must be a positive integer.")
        self._provider = provider
        self._max_input_chars = max_input_chars
        self._max_history_messages = max_history_messages
        self._max_history_chars = max_history_chars
        self._max_stream_chars = max_stream_chars
        self._max_stream_chunk_chars = max_stream_chunk_chars
        self._store = store or InMemoryConversationStore(max_conversations=max_conversations)
        self._context = ContextManager(
            system_context=system_context,
            max_context_chars=max_context_chars,
            max_context_messages=max_context_messages,
        )
        self._locks: dict[str, Lock] = {}
        self._locks_guard = RLock()
        self._closed = False

    def _conversation_lock(self, conversation_id: str) -> Lock:
        conversation_id = validate_conversation_id(conversation_id)
        with self._locks_guard:
            return self._locks.setdefault(conversation_id, Lock())

    @contextmanager
    def _locked_conversation(self, conversation_id: str) -> Iterator[str]:
        conversation_id = validate_conversation_id(conversation_id)
        lock = self._conversation_lock(conversation_id)
        try:
            with lock:
                yield conversation_id
        except ConversationNotFoundError:
            with self._locks_guard:
                if self._locks.get(conversation_id) is lock:
                    self._locks.pop(conversation_id, None)
            raise

    def create_conversation(self) -> str:
        """Create and persist an empty conversation, returning its opaque ID."""
        self._ensure_open()
        conversation_id = self._store.create()
        self._conversation_lock(conversation_id)
        return conversation_id

    def get_history(self, conversation_id: str) -> tuple[Message, ...]:
        """Return a validated snapshot of retained user/assistant history."""
        self._ensure_open()
        with self._locked_conversation(conversation_id) as valid_id:
            return self._store.load(valid_id).messages

    def list_conversations(self) -> tuple[ConversationSummary, ...]:
        """List conversation metadata, newest activity first."""
        self._ensure_open()
        return self._store.list()

    def delete_conversation(self, conversation_id: str) -> None:
        """Logically delete a conversation and its messages."""
        self._ensure_open()
        with self._locked_conversation(conversation_id) as valid_id:
            self._store.delete(valid_id)
        with self._locks_guard:
            self._locks.pop(conversation_id, None)

    def send_message(self, conversation_id: str, content: str) -> Message:
        """Submit user text and atomically append the turn after a valid reply."""
        self._ensure_open()
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Message cannot be empty.")
        if len(content) > self._max_input_chars:
            raise ValueError("Message exceeds the configured input length limit.")

        with self._locked_conversation(conversation_id) as valid_id:
            snapshot = self._store.load(valid_id)
            context = self._context.build(snapshot.messages, content)
            try:
                result = self._generate(context)
            except ProviderError as exc:
                raise ConversationProviderError("The configured provider could not process the message.", code=exc.code) from None
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
            if len(user_message.content) + len(assistant_message.content) > self._max_history_chars:
                raise ContextLimitError("The completed turn exceeds the stored history limit.")
            self._store.commit_turn(
                valid_id,
                snapshot.revision,
                user_message,
                assistant_message,
                max_history_messages=self._max_history_messages,
                max_history_chars=self._max_history_chars,
            )
            return assistant_message

    def stream_message(self, conversation_id: str, content: str) -> Iterator[str]:
        """Yield response fragments and commit the complete turn after clean completion.

        Providers without streaming support use a one-shot compatibility fallback,
        split into bounded fragments.
        """
        self._ensure_open()
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Message cannot be empty.")
        if len(content) > self._max_input_chars:
            raise ValueError("Message exceeds the configured input length limit.")

        def run() -> Iterator[str]:
            # Keep the lock only for the snapshot. Provider consumption and each
            # yield happen after leaving this block, so a retained iterator can
            # never strand conversation reads behind a suspended generator.
            with self._locked_conversation(conversation_id) as valid_id:
                snapshot = self._store.load(valid_id)
                context = self._context.build(snapshot.messages, content)
            stream_method = getattr(self._provider, "stream_messages", None)
            source = None
            iterator = None
            try:
                if callable(stream_method):
                    source = stream_method(context)
                else:
                    prompt = "\n\n".join(f"{message.role.upper()}:\n{message.content}" for message in context)
                    stream_method = getattr(self._provider, "stream", None)
                    if callable(stream_method):
                        source = stream_method(prompt)
                    else:
                        result = self._generate(context)
                        if (not isinstance(result, ProviderResponse) or not isinstance(result.text, str)
                                or not result.text.strip() or not isinstance(result.provider, str)
                                or not result.provider.strip()):
                            raise ConversationProviderError("The configured provider returned an invalid response.")
                        if len(result.text) > self._max_stream_chars:
                            raise ConversationProviderError("The configured provider response exceeds the output limit.")
                        source = (result.text[offset:offset + self._max_stream_chunk_chars]
                                  for offset in range(0, len(result.text), self._max_stream_chunk_chars))
                iterator = iter(source)
            except ConversationProviderError:
                _close_stream_resources(iterator, source)
                raise
            except ProviderError as exc:
                _close_stream_resources(iterator, source)
                raise ConversationProviderError("The configured provider could not process the message.", code=exc.code) from None
            except Exception:
                _close_stream_resources(iterator, source)
                raise ConversationProviderError("The configured provider could not process the message.") from None
            except BaseException:
                _close_stream_resources(iterator, source)
                raise
            parts: list[str] = []
            total = 0
            try:
                while True:
                    try:
                        chunk = next(iterator)
                    except StopIteration:
                        break
                    except ProviderError as exc:
                        raise ConversationProviderError("The configured provider could not complete the stream.", code=exc.code) from None
                    except Exception:
                        raise ConversationProviderError("The configured provider could not complete the stream.") from None
                    if not isinstance(chunk, str) or not chunk or len(chunk) > self._max_stream_chunk_chars:
                        raise ConversationProviderError("The configured provider returned an invalid stream chunk.")
                    total += len(chunk)
                    if total > self._max_stream_chars:
                        raise ConversationProviderError("The configured provider response exceeds the output limit.")
                    parts.append(chunk)
                    yield chunk
                text = "".join(parts)
                if not text.strip():
                    raise ConversationProviderError("The configured provider returned an empty response.")
                if len(text) > self._context.max_context_chars:
                    raise ConversationProviderError("The configured provider response exceeds the output limit.")
                user_message, assistant_message = Message("user", content), Message("assistant", text)
                if len(content) + len(text) > self._max_history_chars:
                    raise ContextLimitError("The completed turn exceeds the stored history limit.")
                with self._locked_conversation(conversation_id) as valid_id:
                    self._store.commit_turn(valid_id, snapshot.revision, user_message, assistant_message,
                        max_history_messages=self._max_history_messages, max_history_chars=self._max_history_chars)
            finally:
                _close_stream_resources(iterator, source)
        return run()

    def backup(self, destination: str | Path) -> str:
        """Create a consistent SQLite backup at a new destination path."""
        self._ensure_open()
        return str(self._store.backup(destination))

    def restore_backup(self, source: str | Path) -> None:
        """Restore a validated backup only when this storage has no conversations."""
        self._ensure_open()
        self._store.restore_backup(source)

    def close(self) -> None:
        """Close storage; subsequent engine operations fail clearly."""
        if not self._closed:
            self._store.close()
            self._closed = True

    def __enter__(self) -> "ConversationEngine":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise ConversationStorageError("Conversation engine is closed.")

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
    persistence_enabled: bool | None = None,
) -> ConversationEngine:
    """Build an engine using configured provider, limits, and durable storage."""
    if persistence_enabled is not None and type(persistence_enabled) is not bool:
        raise ValueError("Persistence option must be a boolean.")
    persistent = settings.persistence_enabled if persistence_enabled is None else persistence_enabled
    if type(persistent) is not bool:
        raise ValueError("Persistence setting must be a boolean.")
    store: ConversationStore
    if persistent:
        store = SQLiteConversationStore(
            settings.storage_directory,
            max_conversations=settings.max_conversations,
            max_history_messages=settings.max_history_messages,
            max_history_chars=settings.max_history_chars,
        )
    else:
        store = InMemoryConversationStore(max_conversations=settings.max_conversations)
    return ConversationEngine(
        provider if provider is not None else create_provider(settings),
        system_context=settings.system_context,
        max_input_chars=settings.max_input_chars,
        max_context_chars=settings.max_context_chars,
        max_context_messages=settings.max_context_messages,
        max_stream_chars=settings.max_stream_chars,
        max_stream_chunk_chars=settings.max_stream_chunk_chars,
        max_history_messages=settings.max_history_messages,
        max_history_chars=settings.max_history_chars,
        max_conversations=settings.max_conversations,
        store=store,
    )
