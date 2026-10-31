from nspire_ai.cli import main


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
