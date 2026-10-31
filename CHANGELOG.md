# Changelog

All notable project changes will be recorded here.

No versioned releases have been published. Milestone notes are listed under Unreleased until the project adopts versioned releases.

## Unreleased

- Project Presentation 1.0: refreshed the repository landing page, added restrained visual identity and a current/future architecture diagram, and documented evidence-backed engineering case studies. Clarified the AI Core 0.7 status and current test result (150 passed, 1 skipped on Windows). No calculator integration or GitHub metadata changes.
- Added AI Core 0.7 Phase 0 and 1 error contracts, stable sanitized provider error categories, explicit CLI signaling for partial streamed output, and clarified bounded HTTP timeout behavior. Provider and storage compatibility is preserved; automatic retries remain disabled.
- Added AI Core 0.6 guided persistent CLI chat with discoverable new/resume choices, metadata-only session listing, history/help/quit shortcuts, and recoverable turn errors. Existing one-shot and `--stream` modes remain available.
- Added AI Core 0.5 opt-in text streaming, OpenAI Responses SSE parsing, deterministic Mock streaming, bounded and atomic conversation stream commits, and CLI `--stream` support. Protocol v1, Transport Layer 0.1, and SQLite schema remain unchanged.
- Added AI Core 0.4 SQLite conversation persistence, restart restoration, session listing, transactional complete turns, revision conflict detection, and consistent backup/restore. The engine factory persists by default; direct construction remains in-memory.
- Added AI Core 0.3 in-memory conversation management, role-validated message history, deterministic bounded context, and Mock/OpenAI conversation support.
- Added AI Core 0.2 provider registry/factory, optional OpenAI Responses API adapter, model and timeout configuration, and sanitized provider failures. Mock remains the default.
- Added Protocol v1 length-prefixed stream framing, local synchronous request handling, and mock-provider end-to-end coverage (Transport Layer 0.1).
- Created the initial project structure and documentation.
- Defined the software-first development direction.
- Recorded the initial architecture and milestones.
