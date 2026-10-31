# Development Log

A concise record of meaningful project decisions, experiments, and results.

## 2026-10-31 — AI Core 0.7 Phase 0 + 1

- **Goal:** Define predictable provider failure and partial-output behavior; harden provider/stream error reporting without changing public provider, storage, protocol, or transport contracts.
- **Changes:** Provider exceptions now carry stable internal categories, with timeout/network/HTTP mappings that omit raw exception and response details. The conversation engine preserves those categories while returning its existing sanitized user-facing error. One-shot `--stream` and guided chat explicitly label already displayed text as incomplete when a stream fails or is interrupted; failed turns remain uncommitted. Documentation now describes the configured `httpx` connect/pool/write/read wait bounds and clarifies that they do not constitute a total stream wall-clock deadline. Automatic retries remain disabled.
- **Verification:** Focused `.venv` pytest run for provider, conversation, CLI, and config tests: 88 passed. Full offline `.venv` pytest suite: 149 passed, one POSIX-permissions test skipped on Windows. Tests use `httpx.MockTransport` and deterministic providers; no live API request was made.
- **Compatibility:** `AIProvider.generate`, `ProviderResponse`, one-shot/`--stream`/`--chat`, SQLite schema v1, Protocol v1, and transport contracts are unchanged.
- **Limitations:** A synchronous stream that continuously produces data can exceed the configured per-operation/read-idle timeout in total duration. The CLI cannot force immediate cancellation inside an active blocking read; the configured read timeout bounds idle waiting.

## 2026-10-31 — AI Core 0.6

- **Goal:** Add a discoverable, provider-neutral persistent chat to the CLI using the existing conversation engine.
- **Changes:** Added `nspire-ai --chat` with a guided new/list/resume start prompt, metadata-only saved-chat listing, streamed multi-turn replies, and optional `:help`, `:history`, `:sessions`, and `:quit` shortcuts. Turn failures and interruptions leave prior history intact; the engine is closed on exit. Existing one-shot and `--stream` paths remain unchanged. Documented local plaintext storage and context transmission when OpenAI is selected.
- **Verification:** Full offline suite passed (148 passed, one POSIX-permissions test skipped on Windows). The 24 CLI tests cover guided creation, list/resume, multiple streamed turns, history/help/quit, invalid IDs and overlong input recovery, failed-turn recovery, interruption and stream cleanup, engine closure, and existing one-shot/`--stream` behavior. A piped mock-provider chat completed and displayed history; 11 local Markdown links resolved; `git diff --check` passed. Independent read-only review found and verified a fix for overlong-input recovery, then reported no remaining actionable findings. No live API calls were made.
- **Limitations:** Terminal interaction is line-based. Ctrl+C stops the current turn or chat; a blocked synchronous provider read is subject to the configured provider timeout.

## 2026-10-30 — AI Core 0.5

- **Goal:** Add optional incremental text streaming while retaining the existing provider, conversation storage, Protocol v1, and transport contracts.
- **Changes:** Added OpenAI Responses SSE streaming, deterministic Mock chunks, bounded conversation streaming with commit-after-completion semantics, and opt-in CLI `--stream`. Output and individual chunks default to 24,000 and 4,096 characters.
- **Verification:** The full offline suite passed with 137 tests passed and one POSIX-permissions test skipped on Windows. CLI and OpenAI streaming are covered by deterministic tests and `httpx.MockTransport`; no live AI API request was made. `git diff --check` passed.
- **Limitations:** The synchronous HTTP read observes configured timeouts; cancellation closes response and iterator resources but cannot promise immediate interruption of every blocked read. Protocol v1, transport, and SQLite schema were unchanged.
- **Review and publication:** Independently approved and committed as `3a5663c` on 2026-10-31.

## 2026-10-30 — AI Core 0.4

- **Goal:** Add durable local conversation storage and safe session management without changing provider, CLI, Protocol v1, or transport contracts.
- **Changes:** Added a provider-neutral conversation store interface, retained the in-memory backend for direct engine construction, and made the engine factory use versioned SQLite storage by default. Added conversation listing, validated restoration, revision-checked atomic turn commits, logical deletion, engine close/context-manager behavior, consistent SQLite backup and empty-store restore APIs, OS-specific data-directory configuration, restrictive POSIX file permissions, and storage domain errors. Review fixes add per-database cross-process operation locks, strict v1 schema validation, and deterministic backup concurrency coverage. Updated architecture, setup, privacy, and recovery documentation.
- **Tests:** `.venv\Scripts\python.exe -m pytest`; mock CLI smoke test; OpenAI CLI without an API key; `git diff --check`.
- **Results:** 113 tests passed and one POSIX-permissions test was skipped on Windows. Coverage includes restart persistence, cross-process restore serialization, strict schema rejection, WAL backup/restore during an active writer, revision conflicts, rollback of incomplete turns, migration/error handling, path configuration, and existing Protocol v1/transport/provider regressions. Mock CLI smoke returned the expected response. OpenAI CLI without a key returned the existing safe configuration error (exit 2); no live request was made. `git diff --check` and new-file whitespace checks passed with only Git line-ending normalization warnings. No files were staged or committed.
- **Limitations:** SQLite data and backups are plaintext. Logical deletion is not forensic erasure. Restore requires an empty target; a per-database OS lock serializes local storage operations across processes. Corruption is detected and preserved for manual recovery; automatic salvage and encryption remain out of scope.

## 2026-10-30 — PC prototype foundation 0.1

- **Goal:** Establish a small, provider-neutral Python foundation for local PC development.
- **Changes:** Added an installable Python 3.13 package, environment-based settings with validation, console logging, domain errors, an `AIProvider` protocol, deterministic mock provider, CLI entry point, and pytest coverage. Added package setup/run/test instructions and updated architecture and roadmap status.
- **Tests:** `python -m pytest`; `python -m nspire_ai.cli "smoke test"`.
- **Results:** All 6 automated tests passed on Python 3.13.17. Both the module CLI and installed `nspire-ai` command returned the expected mock response. `git diff --check` passed.
- **Open questions:** Define a versioned request/response contract before adding transport or calculator integration.

## 2026-10-30 — Protocol v1

- **Goal:** Define a versioned provider- and transport-neutral request/response format.
- **Changes:** Added request and response models, strict JSON validation and serialization, structured validation errors, the Protocol v1 specification, and automated protocol tests. Updated the architecture document to reference the implemented contract.
- **Tests:** `.venv\Scripts\python.exe -m pytest`; module and installed-command CLI smoke runs; `git diff --check`.
- **Results:** All 16 tests passed on Python 3.13.17. Both CLI smoke runs returned the expected mock response. `git diff --check` passed (Git reported only existing line-ending normalization warnings).
- **Open questions:** A future transport must define framing, timeouts, authentication, and request ID generation policy.

## 2026-10-30 — Transport Layer 0.1

- **Goal:** Add a bounded, local request/response stream layer on Protocol v1.
- **Changes:** Added length-prefixed framing, a synchronous stream client/server, an application-core handler using the provider seam, transport tests, and transport documentation. The end-to-end test uses an OS socket pair only; no network listener or device connection was added.
- **Tests:** `..\..\.venv\Scripts\python.exe -m pytest`; CLI module smoke run; focused socket-pair end-to-end test; `git diff --check`.
- **Results:** After review fixes, all 38 tests passed on Python 3.13.17. The CLI returned the expected mock response, the focused local transport end-to-end test passed, and a sentinel exception test confirmed that provider details are neither returned nor logged. `git diff --check` passed (Git emitted only line-ending normalization warnings).
- **Open questions:** Timeouts, authentication, and concrete device/network adapters need a separately reviewed design.

## 2026-10-30 — AI Core 0.2

- **Goal:** Add an optional real provider without coupling the application core to a vendor.
- **Changes:** Added provider registry/factory, model and positive finite timeout settings, and a synchronous OpenAI Responses API adapter using `httpx`. The API key is read from `OPENAI_API_KEY`; HTTP, timeout, network, and response errors are converted to safe provider errors. Mock remains the default. Added offline HTTP-mock coverage and setup/limitations documentation.
- **Tests:** `.venv\Scripts\python.exe -m pytest -q`; CLI mock smoke test; CLI OpenAI-without-key check; `git diff --check`; full diff and Git status review.
- **Results:** All 57 tests passed, including Protocol v1 and Transport Layer regression tests. Mock CLI smoke returned its expected response (exit 0); OpenAI without a key returned the safe configuration error (exit 2). `git diff --check` passed (Git emitted line-ending normalization warnings). No live OpenAI request was made.
- **Open questions:** No streaming, retries, tools, or conversation state are implemented.

## 2026-10-30 — AI Core 0.3

- **Goal:** Add bounded multi-turn conversation management without changing Protocol v1, transport, or the existing one-shot CLI contract.
- **Changes:** Added validated role-tagged messages, deterministic context building, an in-memory conversation store/engine, configured input/context/history/conversation limits, and role-aware Mock/OpenAI provider calls. Provider failures do not commit partial turns; legacy providers retain the original `generate(prompt)` path.
- **Limits:** Conversations live only for the engine/process lifetime. Storage is capped by active conversation count and per-conversation history message and character limits. Context trimming removes oldest whole turns and never drops configured system context.
- **Verification:** Full suite passed (81 tests). The mock CLI smoke returned its reply (exit 0); OpenAI CLI without `OPENAI_API_KEY` returned the generic configuration error (exit 2). `git diff --check` passed with only Git line-ending normalization warnings. A repository scan found no API-key-shaped secrets. No live OpenAI request was made.

## 2026-10-30 — Repository foundation

- Created the initial private repository structure.
- Confirmed the project will begin with a PC prototype.
- Deferred internal hardware work and purchases.
- Recorded the main architecture as a hypothesis to validate, not an implemented system.

## Log template

### YYYY-MM-DD — Short title
- **Goal:**
- **Changes:**
- **Tests:**
- **Results:**
- **Open questions:**
