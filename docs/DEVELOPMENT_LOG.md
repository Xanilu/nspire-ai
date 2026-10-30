# Development Log

A concise record of meaningful project decisions, experiments, and results.

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
