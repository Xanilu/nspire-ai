# Architecture

## Status

The system described here remains a design direction, with the PC foundation implemented under `software/pc-prototype`. AI Core 0.5 adds opt-in synchronous streaming over bounded local SQLite conversations. No calculator connection is implemented.

## Core idea

The TI-Nspire CX II should provide the user interface and input experience. More demanding work—especially language-model inference—should run on an external host or a cloud service.

## Logical components

### 1. Calculator client
A lightweight Ndless application may eventually handle input, display, and message exchange. Exact APIs and compatibility must be verified on the target calculator and OS version.

### 2. Communication layer
A transport adapter moves structured requests and responses between the calculator and the external host. Protocol v1 framing is implemented for blocking binary streams with a bounded four-byte length prefix; it remains independent of the physical transport. See [TRANSPORT_LAYER_V0_1.md](TRANSPORT_LAYER_V0_1.md). No remote or calculator transport is implemented.

### 3. Host application
The host receives requests, validates them, routes tasks, and returns formatted results. The PC foundation includes a minimal local CLI and a stream request handler that can invoke the application core.

### 4. AI engine
The PC foundation exposes a provider-neutral `AIProvider` protocol and `ProviderResponse` type. An optional streaming capability preserves compatibility with existing providers; providers without it use a one-shot fallback. OpenAI uses the Responses API SSE stream and yields text deltas. `ConversationEngine.stream_message` snapshots history under the per-conversation lock, then streams without holding the lock; it enforces output and chunk bounds and commits only after successful completion with a revision check. Closing early or any provider/validation/storage failure leaves history unchanged. Synchronous HTTP cancellation relies on iterator and response cleanup plus configured HTTP timeouts; an in-progress blocking read cannot always be interrupted immediately. Stream limits use `NSPIRE_AI_MAX_STREAM_CHARS` (24,000) and `NSPIRE_AI_MAX_STREAM_CHUNK_CHARS` (4,096). The CLI stream flag is opt-in. The SQLite schema and Protocol v1 remain unchanged. See the [PC prototype guide](../software/pc-prototype/README.md) for setup, backup/restore, streaming and limits.

## Protocol

Protocol v1 defines provider- and transport-neutral JSON request and response envelopes. Requests carry `protocol_version`, `request_id`, `input`, and optional metadata. Responses echo the version and request ID and carry a status and text, with structured error details on failures. The schema and compatibility rules are specified in [PROTOCOL_V1.md](PROTOCOL_V1.md); the Python reference implementation lives in `nspire_ai.protocol`.

## Constraints and open questions

- The calculator model has no built-in Wi-Fi or Bluetooth.
- A phone hotspot alone does not give the calculator a network interface.
- Any external adapter would need a supported physical connection and suitable software/firmware; it will not automatically behave like a network card.
- Ndless compatibility, available I/O APIs, cable options, and OS-specific behavior need hands-on verification.
- Cloud AI requires a network-connected host device and careful handling of credentials and user data. OpenAI prompts are sent to the configured service; live API behavior was not exercised by offline tests.
- The OpenAI adapter is synchronous and has no retry or tool support. SQLite storage is local to the host and not synchronized; simultaneous writers use optimistic conflict detection, and a conflicting provider response is not retried automatically.

## Design principles

- Keep components replaceable.
- Use explicit protocol versions and request IDs.
- Handle timeouts, malformed messages, and unavailable services.
- Keep secrets outside the repository.
- Test on a PC before attempting calculator integration.
