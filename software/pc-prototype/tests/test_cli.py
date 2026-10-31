from nspire_ai.cli import main
from nspire_ai.conversations import ConversationEngine
from nspire_ai.providers.mock import MockProvider
from nspire_ai.storage import InMemoryConversationStore


def test_cli_smoke(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["nspire-ai", "test prompt"])
    assert main() == 0
    assert "test prompt" in capsys.readouterr().out


def test_cli_stream_is_incremental_and_opt_in(capsys, monkeypatch):
    class StreamProvider:
        def stream(self, prompt):
            yield "first"
            yield " second"

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 0
    assert capsys.readouterr().out == "first second\n"


def test_cli_stream_interruption_has_stable_status(capsys, monkeypatch):
    state = {"closed": False}

    def provider_stream():
        try:
            yield "partial"
            raise KeyboardInterrupt
        finally:
            state["closed"] = True

    class TrackedProvider:
        def stream(self, prompt):
            return provider_stream()

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: TrackedProvider())
    assert main() == 130
    assert capsys.readouterr().out == "partial"
    assert state["closed"]


def test_cli_closes_generator_stream_after_provider_failure(capsys, monkeypatch):
    state = {"closed": False}

    def provider_stream():
        try:
            yield "partial"
            raise RuntimeError("private provider detail")
        finally:
            state["closed"] = True

    class StreamProvider:
        def stream(self, prompt):
            return provider_stream()

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == "partial"
    assert state["closed"]


def test_cli_closes_same_source_and_iterator_once(capsys, monkeypatch):
    class TrackedStream:
        def __init__(self):
            self.items = iter(("partial", ""))
            self.close_calls = 0

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.items)

        def close(self):
            self.close_calls += 1

    provider_stream = TrackedStream()

    class StreamProvider:
        def stream(self, prompt):
            return provider_stream

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == "partial"
    assert provider_stream.close_calls == 1


def test_cli_closes_source_if_iterator_creation_fails(capsys, monkeypatch):
    class BadIterable:
        closed = False

        def __iter__(self):
            raise RuntimeError("private provider detail")

        def close(self):
            self.closed = True

    provider_stream = BadIterable()

    class StreamProvider:
        def stream(self, prompt):
            return provider_stream

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == ""
    assert provider_stream.closed


def test_cli_closes_source_if_interrupted_during_iterator_creation(capsys, monkeypatch):
    class InterruptedIterable:
        closed = False

        def __iter__(self):
            raise KeyboardInterrupt

        def close(self):
            self.closed = True

    provider_stream = InterruptedIterable()

    class StreamProvider:
        def stream(self, prompt):
            return provider_stream

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 130
    assert capsys.readouterr().out == ""
    assert provider_stream.closed


def test_cli_stream_rejects_oversized_fragment_before_writing(capsys, monkeypatch):
    class StreamProvider:
        def stream(self, prompt):
            yield "ok"
            yield "too-large"

    monkeypatch.setenv("NSPIRE_AI_MAX_STREAM_CHUNK_CHARS", "4")
    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == "ok"


def test_cli_stream_rejects_cumulative_overflow_before_writing_and_closes(capsys, monkeypatch):
    class TrackedStream:
        closed = False

        def __iter__(self):
            yield "1234"
            yield "5678"

        def close(self):
            self.closed = True

    provider_stream = TrackedStream()

    class StreamProvider:
        def stream(self, prompt):
            return provider_stream

    monkeypatch.setenv("NSPIRE_AI_MAX_STREAM_CHARS", "6")
    monkeypatch.setenv("NSPIRE_AI_MAX_STREAM_CHUNK_CHARS", "4")
    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == "1234"
    assert provider_stream.closed


def test_cli_stream_closes_after_provider_failure(capsys, monkeypatch):
    class TrackedStream:
        closed = False

        def __iter__(self):
            yield "partial"
            raise RuntimeError("private provider detail")

        def close(self):
            self.closed = True

    provider_stream = TrackedStream()

    class StreamProvider:
        def stream(self, prompt):
            return provider_stream

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == "partial"
    assert provider_stream.closed


def test_cli_stream_rejects_invalid_or_empty_fragments_before_writing(capsys, monkeypatch):
    class StreamProvider:
        def stream(self, prompt):
            yield "ok"
            yield ""

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == "ok"


def test_cli_stream_rejects_empty_final_output(capsys, monkeypatch):
    class StreamProvider:
        def stream(self, prompt):
            return iter(())

    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: StreamProvider())
    assert main() == 2
    assert capsys.readouterr().out == ""


def test_cli_stream_bounds_legacy_generate_fallback(capsys, monkeypatch):
    class LegacyProvider:
        def generate(self, prompt):
            from nspire_ai.providers.base import ProviderResponse
            return ProviderResponse("abcdefgh", "legacy")

    monkeypatch.setenv("NSPIRE_AI_MAX_STREAM_CHARS", "6")
    monkeypatch.setenv("NSPIRE_AI_MAX_STREAM_CHUNK_CHARS", "4")
    monkeypatch.setattr("sys.argv", ["nspire-ai", "--stream", "test prompt"])
    monkeypatch.setattr("nspire_ai.cli.create_provider", lambda settings: LegacyProvider())
    assert main() == 2
    assert capsys.readouterr().out == ""


def _interactive_engine(provider=None):
    return ConversationEngine(provider or MockProvider(), store=InMemoryConversationStore())


def test_chat_guides_new_user_and_streams_multiple_turns():
    class Provider:
        def stream_messages(self, messages):
            yield f"answer to {messages[-1].content}"

    engine = _interactive_engine(Provider())
    prompts = iter(("", "first question", "second question", ":quit"))
    output = __import__("io").StringIO()
    assert __import__("nspire_ai.cli", fromlist=["run_interactive"]).run_interactive(
        engine, input_fn=lambda prompt: next(prompts), output=output
    ) == 0
    result = output.getvalue()
    assert "Press Enter to start a new chat" in result
    assert "Actions:" in result
    assert "answer to first question" in result
    assert "answer to second question" in result
    conversation_id = engine.list_conversations()[0].conversation_id
    assert [m.content for m in engine.get_history(conversation_id)] == [
        "first question", "answer to first question", "second question", "answer to second question"
    ]


def test_chat_lists_and_resumes_by_id_without_showing_session_content():
    from io import StringIO
    from nspire_ai.cli import run_interactive

    engine = _interactive_engine()
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "private text must not appear in session list")
    prompts = iter(("L", conversation_id, ":history", ":quit"))
    output = StringIO()
    assert run_interactive(engine, input_fn=lambda prompt: next(prompts), output=output) == 0
    result = output.getvalue()
    assert conversation_id in result
    assert "2 message(s), 1 turn(s)" in result
    assert "private text must not appear in session list" not in result.split("Saved chats")[1].split("Enter a chat ID")[0]
    assert "You: private text must not appear in session list" in result


def test_chat_invalid_id_can_recover_by_listing_and_resuming():
    from io import StringIO
    from nspire_ai.cli import run_interactive

    engine = _interactive_engine()
    conversation_id = engine.create_conversation()
    prompts = iter(("invalid", "L", conversation_id, ":quit"))
    output = StringIO()
    assert run_interactive(engine, input_fn=lambda prompt: next(prompts), output=output) == 0
    assert "was not found" in output.getvalue()
    assert f"Chat ID: {conversation_id}" in output.getvalue()


def test_chat_turn_error_recovers_and_does_not_persist_failed_turn():
    from io import StringIO
    from nspire_ai.cli import run_interactive
    class Provider:
        def __init__(self):
            self.calls = 0

        def stream_messages(self, messages):
            self.calls += 1
            if self.calls == 1:
                yield "partial"
                raise RuntimeError("private provider detail")
            yield "recovered"

    engine = _interactive_engine(Provider())
    conversation_id = engine.create_conversation()
    prompts = iter(("first", "second", ":history", ":help", ":quit"))
    output = StringIO()
    assert run_interactive(engine, conversation_id=conversation_id,
                           input_fn=lambda prompt: next(prompts), output=output) == 0
    result = output.getvalue()
    assert "Could not complete that turn" in result
    assert "private provider detail" not in result
    assert "Your earlier history is still available" in result
    assert [m.content for m in engine.get_history(conversation_id)] == ["second", "recovered"]
    assert "Type a message and press Enter" in result
    assert "first" not in result.split("You: ")[-1]


def test_chat_overlong_input_shows_retry_hint_and_accepts_next_turn():
    from io import StringIO
    from nspire_ai.cli import run_interactive

    engine = ConversationEngine(MockProvider(), max_input_chars=4, store=InMemoryConversationStore())
    conversation_id = engine.create_conversation()
    prompts = iter(("too long", "good", ":quit"))
    output = StringIO()
    assert run_interactive(engine, conversation_id=conversation_id,
                           input_fn=lambda _prompt: next(prompts), output=output) == 0
    assert "Message exceeds the configured input length limit. Please try again." in output.getvalue()
    assert [message.content for message in engine.get_history(conversation_id)] == [
        "good", "Mock provider received: good"
    ]


def test_chat_keyboard_interrupt_and_eof_close_cleanly():
    from io import StringIO
    from nspire_ai.cli import run_interactive

    engine = _interactive_engine()
    conversation_id = engine.create_conversation()

    def interrupted(_prompt):
        raise KeyboardInterrupt

    output = StringIO()
    assert run_interactive(engine, conversation_id=conversation_id, input_fn=interrupted, output=output) == 130
    assert "Chat interrupted" in output.getvalue()
    engine.close()


def test_chat_interrupt_during_stream_closes_provider_stream_and_does_not_commit():
    from io import StringIO
    from nspire_ai.cli import run_interactive

    state = {"closed": False}

    class Provider:
        def stream_messages(self, messages):
            try:
                yield "partial"
                raise KeyboardInterrupt
            finally:
                state["closed"] = True

    engine = _interactive_engine(Provider())
    conversation_id = engine.create_conversation()
    prompts = iter(("hello", ":quit"))
    output = StringIO()
    assert run_interactive(engine, conversation_id=conversation_id,
                           input_fn=lambda _prompt: next(prompts), output=output) == 0
    assert state["closed"]
    assert "Turn interrupted; it was not saved" in output.getvalue()
    assert engine.get_history(conversation_id) == ()

    engine = _interactive_engine()
    conversation_id = engine.create_conversation()

    def eof(_prompt):
        raise EOFError

    assert run_interactive(engine, conversation_id=conversation_id, input_fn=eof, output=StringIO()) == 0
    engine.close()


def test_chat_command_line_defaults_to_create_and_engine_is_closed(monkeypatch):
    from nspire_ai.cli import run_interactive

    engine = _interactive_engine()
    seen = {}
    monkeypatch.setattr("nspire_ai.cli.create_conversation_engine", lambda settings: engine)
    monkeypatch.setattr("nspire_ai.cli.run_interactive", lambda received, **kwargs: seen.update(kwargs) or 0)
    monkeypatch.setattr("sys.argv", ["nspire-ai", "--chat"])
    assert main() == 0
    assert seen == {"conversation_id": None}
    try:
        engine.list_conversations()
    except Exception as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("interactive engine was not closed")


def test_chat_command_line_passes_explicit_id_for_resume(monkeypatch):
    engine = _interactive_engine()
    conversation_id = engine.create_conversation()
    seen = {}
    monkeypatch.setattr("nspire_ai.cli.create_conversation_engine", lambda settings: engine)
    monkeypatch.setattr("nspire_ai.cli.run_interactive", lambda received, **kwargs: seen.update(kwargs) or 0)
    monkeypatch.setattr("sys.argv", ["nspire-ai", "--chat", conversation_id])
    assert main() == 0
    assert seen == {"conversation_id": conversation_id}


def test_chat_help_and_quit_from_start_prompt():
    from io import StringIO
    from nspire_ai.cli import run_interactive

    output = StringIO()
    assert run_interactive(_interactive_engine(), input_fn=lambda _prompt: "q", output=output) == 0
    assert "Goodbye" in output.getvalue()


def test_chat_can_be_interrupted_before_creating_a_conversation():
    from io import StringIO
    from nspire_ai.cli import run_interactive

    engine = _interactive_engine()

    def interrupted(_prompt):
        raise KeyboardInterrupt

    output = StringIO()
    assert run_interactive(engine, input_fn=interrupted, output=output) == 130
    assert "saved chats are unchanged" in output.getvalue()
    assert engine.list_conversations() == ()
