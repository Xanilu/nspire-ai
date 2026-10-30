# Architecture

## Status

The system described here remains a design direction, with the PC foundation implemented under `software/pc-prototype`. AI Core 0.4 adds bounded local SQLite conversations over the provider-neutral core. No calculator connection is implemented.

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
The PC foundation exposes a provider-neutral `AIProvider` protocol and `ProviderResponse` type. A registry/factory selects providers using `NSPIRE_AI_PROVIDER`; mock is the safe default. `ConversationEngine` uses a small `ConversationStore` seam; direct construction uses memory, while the engine factory uses SQLite by default. The SQLite store keeps opaque conversation IDs, timestamps, revisions, and validated user/assistant messages in a versioned local database. Turns and pruning are atomic, foreign keys cascade deletion, and optimistic revisions prevent concurrent engines from silently overwriting committed history. A per-database OS lock serializes storage operations across engine instances and processes, including restore's empty-target check and file replacement. Backups use SQLite's backup API; restore validates the complete v1 schema and data and requires an empty target store. The OS data directory can be overridden by `NSPIRE_AI_DATA_DIR`, and persistence can be disabled with `NSPIRE_AI_PERSISTENCE=false`. `ContextManager` always includes configured system context, then selects the newest contiguous sequence of complete turns within character and message limits. The OpenAI adapter maps those roles to Responses API input messages; Mock and legacy prompt-only providers remain supported. Provider failures do not append a turn and are surfaced as generic conversation errors. The OpenAI adapter uses `httpx`, with model (`NSPIRE_AI_MODEL`) and request timeout (`NSPIRE_AI_REQUEST_TIMEOUT`) settings. Credentials come only from `OPENAI_API_KEY`, remain on the host, and are never included in logs or stored with conversations. Conversation text is plaintext locally; logical deletion does not guarantee forensic erasure, and no encryption-at-rest is provided. The existing core maps provider exceptions to a stable Protocol v1 `provider_error` response. See the [PC prototype guide](../software/pc-prototype/README.md) for setup, backup/restore, and limits.

## Protocol

Protocol v1 defines provider- and transport-neutral JSON request and response envelopes. Requests carry `protocol_version`, `request_id`, `input`, and optional metadata. Responses echo the version and request ID and carry a status and text, with structured error details on failures. The schema and compatibility rules are specified in [PROTOCOL_V1.md](PROTOCOL_V1.md); the Python reference implementation lives in `nspire_ai.protocol`.

## Constraints and open questions

- The calculator model has no built-in Wi-Fi or Bluetooth.
- A phone hotspot alone does not give the calculator a network interface.
- Any external adapter would need a supported physical connection and suitable software/firmware; it will not automatically behave like a network card.
- Ndless compatibility, available I/O APIs, cable options, and OS-specific behavior need hands-on verification.
- Cloud AI requires a network-connected host device and careful handling of credentials and user data. OpenAI prompts are sent to the configured service; live API behavior was not exercised by offline tests.
- The OpenAI adapter is synchronous, non-streaming, and has no retry or tool support. SQLite storage is local to the host and not synchronized; simultaneous writers use optimistic conflict detection, and a conflicting provider response is not retried automatically.

## Design principles

- Keep components replaceable.
- Use explicit protocol versions and request IDs.
- Handle timeouts, malformed messages, and unavailable services.
- Keep secrets outside the repository.
- Test on a PC before attempting calculator integration.
