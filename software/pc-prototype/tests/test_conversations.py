import pytest
from threading import Event, Thread

from nspire_ai.conversations import ConversationEngine, ConversationNotFoundError
from nspire_ai.errors import ConversationProviderError, ConversationStorageConflictError, ContextLimitError
from nspire_ai.messages import Message
from nspire_ai.providers.base import ProviderResponse
from nspire_ai.providers.mock import MockProvider
from nspire_ai.storage import InMemoryConversationStore


class RecordingProvider:
    name = "recording"

    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def generate(self, prompt):
        return ProviderResponse(text=prompt, provider=self.name)

    def generate_messages(self, messages):
        self.calls.append(tuple(messages))
        if self.fail:
            raise RuntimeError("private provider detail")
        return ProviderResponse(text=f"answer {len(self.calls)}", provider=self.name)


class RecordingMockProvider(MockProvider):
    def __init__(self):
        self.calls = []

    def generate_messages(self, messages):
        self.calls.append(tuple(messages))
        return super().generate_messages(messages)


def test_new_conversation_has_unique_id_and_empty_history():
    engine = ConversationEngine(MockProvider())
    first = engine.create_conversation()
    second = engine.create_conversation()
    assert first != second
    assert engine.get_history(first) == ()


def test_multiple_messages_reuse_conversation_id_and_keep_history():
    engine = ConversationEngine(MockProvider())
    conversation_id = engine.create_conversation()
    first = engine.send_message(conversation_id, "first")
    second = engine.send_message(conversation_id, "second")
    history = engine.get_history(conversation_id)
    assert first.role == second.role == "assistant"
    assert [message.role for message in history] == ["user", "assistant", "user", "assistant"]
    assert [message.content for message in history][::2] == ["first", "second"]


def test_unknown_conversation_id_fails_safely():
    engine = ConversationEngine(MockProvider())
    with pytest.raises(ConversationNotFoundError, match="not found"):
        engine.send_message("unknown-private-id", "hello")
    with pytest.raises(ConversationNotFoundError):
        engine.get_history("unknown-private-id")


def test_invalid_roles_are_rejected():
    with pytest.raises(ValueError, match="role"):
        Message(role="developer", content="user supplied")


def test_empty_and_overlong_inputs_are_rejected_without_mutating_history():
    engine = ConversationEngine(MockProvider(), max_input_chars=4)
    conversation_id = engine.create_conversation()
    with pytest.raises(ValueError, match="empty"):
        engine.send_message(conversation_id, "  ")
    with pytest.raises(ValueError, match="length"):
        engine.send_message(conversation_id, "12345")
    assert engine.get_history(conversation_id) == ()


def test_context_keeps_system_and_latest_complete_turns_with_deterministic_limits():
    provider = RecordingProvider()
    engine = ConversationEngine(
        provider,
        system_context="Follow the configured rules.",
        max_context_chars=100,
        max_context_messages=4,
    )
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "old")
    engine.send_message(conversation_id, "middle")
    engine.send_message(conversation_id, "new")
    sent = provider.calls[-1]
    assert [(message.role, message.content) for message in sent] == [
        ("system", "Follow the configured rules."),
        ("user", "middle"),
        ("assistant", "answer 2"),
        ("user", "new"),
    ]


def test_system_context_is_never_silently_removed_when_current_input_does_not_fit():
    provider = RecordingProvider()
    engine = ConversationEngine(provider, system_context="sys", max_context_chars=6)
    conversation_id = engine.create_conversation()
    with pytest.raises(ContextLimitError):
        engine.send_message(conversation_id, "large")
    assert provider.calls == []
    assert engine.get_history(conversation_id) == ()


def test_provider_failure_is_sanitized_and_does_not_append_partial_turn():
    provider = RecordingProvider()
    engine = ConversationEngine(provider)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "existing turn")
    before = engine.get_history(conversation_id)
    provider.fail = True
    with pytest.raises(ConversationProviderError) as caught:
        engine.send_message(conversation_id, "hello")
    assert "private provider detail" not in str(caught.value)
    assert engine.get_history(conversation_id) == before


def test_conversations_are_isolated_and_mock_receives_role_mapped_history():
    provider = RecordingMockProvider()
    engine = ConversationEngine(provider, system_context="trusted system context")
    first = engine.create_conversation()
    second = engine.create_conversation()
    engine.send_message(first, "private first conversation")
    engine.send_message(second, "separate conversation")
    engine.send_message(second, "follow up")
    second_history = engine.get_history(second)
    assert all("private first conversation" not in message.content for message in second_history)
    assert second_history[0].role == "user"
    assert [(message.role, message.content) for message in provider.calls[-1]] == [
        ("system", "trusted system context"),
        ("user", "separate conversation"),
        ("assistant", "Mock provider received: separate conversation"),
        ("user", "follow up"),
    ]


def test_stored_history_is_bounded_by_complete_turns():
    engine = ConversationEngine(MockProvider(), max_history_messages=2)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "first")
    engine.send_message(conversation_id, "second")
    assert [message.content for message in engine.get_history(conversation_id)] == [
        "second",
        "Mock provider received: second",
    ]


def test_delete_and_reuse_of_conversation_id_is_rejected():
    engine = ConversationEngine(MockProvider())
    conversation_id = engine.create_conversation()
    engine.delete_conversation(conversation_id)
    with pytest.raises(ConversationNotFoundError):
        engine.get_history(conversation_id)


def test_legacy_provider_implementation_still_works_through_generate_prompt():
    class LegacyProvider:
        name = "legacy"

        def __init__(self):
            self.prompt = ""

        def generate(self, prompt):
            self.prompt = prompt
            return ProviderResponse("legacy answer", self.name)

    provider = LegacyProvider()
    engine = ConversationEngine(provider)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "hello")
    assert "USER:\nhello" in provider.prompt


def test_conversation_capacity_is_bounded():
    engine = ConversationEngine(MockProvider(), max_conversations=1)
    engine.create_conversation()
    with pytest.raises(ContextLimitError):
        engine.create_conversation()


def test_stored_history_character_limit_prunes_whole_old_turns():
    provider = RecordingProvider()
    engine = ConversationEngine(provider, max_history_chars=13)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "a")
    engine.send_message(conversation_id, "b")
    assert [(message.role, message.content) for message in engine.get_history(conversation_id)] == [
        ("user", "b"),
        ("assistant", "answer 2"),
    ]


def test_streaming_commits_only_after_success_and_closing_aborts():
    class Chunks:
        def stream_messages(self, messages):
            yield "first"
            yield " second"

    engine = ConversationEngine(Chunks())
    cid = engine.create_conversation()
    stream = engine.stream_message(cid, "question")
    assert next(stream) == "first"
    assert engine._conversation_lock(cid).acquire(blocking=False)
    engine._conversation_lock(cid).release()
    stream.close()
    assert engine._conversation_lock(cid).acquire(blocking=False)
    engine._conversation_lock(cid).release()
    assert engine.get_history(cid) == ()
    assert list(engine.stream_message(cid, "question")) == ["first", " second"]
    assert [m.content for m in engine.get_history(cid)] == ["question", "first second"]


def test_abandoned_stream_does_not_hold_lock_or_commit_partial_turn():
    class Chunks:
        def stream_messages(self, messages):
            yield "first"
            yield " second"

    engine = ConversationEngine(Chunks())
    cid = engine.create_conversation()
    stream = engine.stream_message(cid, "question")
    assert next(stream) == "first"

    started = Event()
    result = []

    def read_history():
        started.set()
        result.append(engine.get_history(cid))

    reader = Thread(target=read_history, daemon=True)
    reader.start()
    try:
        assert started.wait(timeout=1)
        reader.join(timeout=1)
        assert not reader.is_alive(), "get_history blocked behind a retained stream iterator"
        assert result == [()]
    finally:
        # Keep cleanup bounded even if the regression reappears.
        stream.close()
        reader.join(timeout=1)
    assert engine.get_history(cid) == ()


def test_streaming_enforces_chunk_and_total_limits_without_commit():
    class Chunks:
        def stream_messages(self, messages):
            yield "1234"
            yield "5678"

    engine = ConversationEngine(Chunks(), max_stream_chars=6, max_stream_chunk_chars=4)
    cid = engine.create_conversation()
    stream = engine.stream_message(cid, "question")
    assert next(stream) == "1234"
    with pytest.raises(ConversationProviderError):
        next(stream)
    assert engine.get_history(cid) == ()


def test_streaming_provider_failure_midstream_is_sanitized_and_releases_lock():
    class Chunks:
        def stream_messages(self, messages):
            yield "partial"
            raise RuntimeError("private streaming detail")

    engine = ConversationEngine(Chunks())
    cid = engine.create_conversation()
    stream = engine.stream_message(cid, "question")
    assert next(stream) == "partial"
    with pytest.raises(ConversationProviderError) as caught:
        next(stream)
    assert "private streaming detail" not in str(caught.value)
    assert engine.get_history(cid) == ()
    assert engine._conversation_lock(cid).acquire(blocking=False)
    engine._conversation_lock(cid).release()


def test_empty_stream_is_rejected_without_commit():
    class Empty:
        def stream_messages(self, messages):
            if False:
                yield ""

    engine = ConversationEngine(Empty())
    cid = engine.create_conversation()
    with pytest.raises(ConversationProviderError, match="empty"):
        list(engine.stream_message(cid, "question"))
    assert engine.get_history(cid) == ()


def test_legacy_fallback_splits_large_unicode_response_without_changing_text():
    response_text = ("🙂漢字é" * 1_250)

    class LegacyProvider:
        name = "legacy"

        def generate(self, prompt):
            return ProviderResponse(response_text, self.name)

    engine = ConversationEngine(
        LegacyProvider(), max_stream_chars=8_000, max_stream_chunk_chars=257,
    )
    cid = engine.create_conversation()
    fragments = list(engine.stream_message(cid, "question"))
    assert fragments
    assert all(0 < len(fragment) <= 257 for fragment in fragments)
    assert "".join(fragments) == response_text
    assert [message.content for message in engine.get_history(cid)] == ["question", response_text]


def test_legacy_fallback_rejects_output_over_total_limit_without_commit():
    class LegacyProvider:
        name = "legacy"

        def generate(self, prompt):
            return ProviderResponse("x" * 101, self.name)

    engine = ConversationEngine(
        LegacyProvider(), max_stream_chars=100, max_stream_chunk_chars=10,
    )
    cid = engine.create_conversation()
    with pytest.raises(ConversationProviderError, match="output limit"):
        list(engine.stream_message(cid, "question"))
    assert engine.get_history(cid) == ()


def test_stream_revision_conflict_discards_stale_turn_without_retry():
    store = InMemoryConversationStore()
    first = ConversationEngine(RecordingProvider(), store=store)
    second = ConversationEngine(RecordingProvider(), store=store)
    cid = first.create_conversation()
    stream = first.stream_message(cid, "stale")
    assert next(stream).startswith("answer")
    second.send_message(cid, "winner")
    with pytest.raises(ConversationStorageConflictError, match="changed during this request"):
        next(stream)
    assert [message.content for message in first.get_history(cid)] == ["winner", "answer 1"]
