# Changelog

All notable project changes will be recorded here.

The project is in its initial planning stage. There are no released versions yet.

## Unreleased

- Added AI Core 0.4 SQLite conversation persistence, restart restoration, session listing, transactional complete turns, revision conflict detection, and consistent backup/restore. The engine factory persists by default; direct construction remains in-memory.
- Added AI Core 0.3 in-memory conversation management, role-validated message history, deterministic bounded context, and Mock/OpenAI conversation support.
- Added AI Core 0.2 provider registry/factory, optional OpenAI Responses API adapter, model and timeout configuration, and sanitized provider failures. Mock remains the default.
- Added Protocol v1 length-prefixed stream framing, local synchronous request handling, and mock-provider end-to-end coverage (Transport Layer 0.1).
- Created the initial project structure and documentation.
- Defined the software-first development direction.
- Recorded the initial architecture and milestones.
