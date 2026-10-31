# Engineering Journey

Four case studies show how the PC prototype earned its current shape. Each links to the implementation milestone and the tests that exercise it. This is a record of software behavior, not evidence of a calculator connection.

## 1. A protocol before a device

**Problem.** A future calculator client and host need a stable contract without binding messages to a particular provider or physical link.

**Decision.** Define Protocol v1 JSON envelopes and bounded length-prefixed framing, then exercise the handler locally with a socket pair. This validates serialization and request handling without claiming network or device support.

**Evidence.** [Protocol v1 implementation](https://github.com/Xanilu/nspire-ai/commit/2db4c80) · [Transport Layer 0.1 implementation](https://github.com/Xanilu/nspire-ai/commit/2009832) · [`test_protocol.py`](../software/pc-prototype/tests/test_protocol.py) · [`test_transport.py`](../software/pc-prototype/tests/test_transport.py) · [Transport Layer 0.1 specification](TRANSPORT_LAYER_V0_1.md).

**Boundary.** The local handler has no network listener, authentication, calculator client, or physical adapter.

## 2. Failed streams must not become conversation history

**Problem.** Streaming can display useful fragments before a provider fails. Saving that partial answer as a complete turn would misrepresent what happened and could corrupt later context.

**Decision.** Buffer the assembled answer, enforce character and fragment limits, and commit the user/assistant pair only after successful completion and a revision check. The CLI marks already displayed fragments as incomplete when a stream fails or is interrupted.

**Evidence.** [AI Core 0.5 streaming change](https://github.com/Xanilu/nspire-ai/commit/3a5663c) · [AI Core 0.7 failure contract](https://github.com/Xanilu/nspire-ai/commit/a21a5c1) · `test_streaming_provider_failure_midstream_is_sanitized_and_releases_lock`, `test_stream_revision_conflict_discards_stale_turn_without_retry`, and CLI interruption tests in [`test_conversations.py`](../software/pc-prototype/tests/test_conversations.py) and [`test_cli.py`](../software/pc-prototype/tests/test_cli.py).

**Boundary.** HTTP timeouts bound individual operations and idle reads; they are not a total stream deadline. Automatic retries remain disabled.

## 3. Persistence needs conflict and recovery rules

**Problem.** Multi-turn conversations must survive restarts, while concurrent writers, partial turns, and backups must not silently create inconsistent history.

**Decision.** Use a versioned SQLite store, atomic complete-turn commits, optimistic revisions, and validated backup/restore. Keep direct engine construction in-memory and make factory persistence configurable.

**Evidence.** [AI Core 0.4 persistence change](https://github.com/Xanilu/nspire-ai/commit/9ed16e7) · tests for revision conflicts, WAL backup/restore, incomplete turns, and cross-process operation locking in [`test_storage.py`](../software/pc-prototype/tests/test_storage.py).

**Boundary.** Database content and backups are plaintext; logical deletion is not forensic erasure. Restore requires an empty destination store, and corruption recovery is manual.

## 4. Safe errors are part of the provider boundary

**Problem.** Raw HTTP bodies and exception details can expose request or provider data. At the same time, users need to distinguish timeout, unavailable service, and HTTP rejection.

**Decision.** Map failures to stable internal categories and sanitized user-facing messages. Keep the existing provider and storage contracts, and do not retry uncertain requests automatically.

**Evidence.** [AI Core 0.7 hardening change](https://github.com/Xanilu/nspire-ai/commit/a21a5c1) · provider and conversation sanitization cases in [`test_provider.py`](../software/pc-prototype/tests/test_provider.py), [`test_openai_provider.py`](../software/pc-prototype/tests/test_openai_provider.py), and [`test_conversations.py`](../software/pc-prototype/tests/test_conversations.py).

**Boundary.** Automated tests use deterministic providers and `httpx.MockTransport`; they do not establish live OpenAI service behavior. A current Windows test run reports 150 passed and one POSIX-permissions test skipped.

## Evidence policy

Claims above are limited to behavior represented by repository commits, automated tests, and the [development log](DEVELOPMENT_LOG.md). See [architecture](ARCHITECTURE.md), [roadmap](../ROADMAP.md), and [hardware research](HARDWARE_RESEARCH.md) for current status and unresolved device questions.
