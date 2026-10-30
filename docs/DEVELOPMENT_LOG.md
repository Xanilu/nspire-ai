# Development Log

A concise record of meaningful project decisions, experiments, and results.

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
