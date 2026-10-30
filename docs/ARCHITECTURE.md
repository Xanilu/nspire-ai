# Architecture

## Status

The system described here remains a design direction, with the milestone 0.1 PC foundation implemented under `software/pc-prototype`. That foundation includes a provider-neutral interface and a local mock provider; it does not yet connect to an AI service or calculator.

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
The PC foundation exposes a provider-neutral `AIProvider` protocol and `ProviderResponse` type. The mock implementation is deterministic and offline. Later adapters can connect to local or cloud models; API credentials must remain on the host, must never be embedded in calculator files or committed to Git, and must not be logged.

## Protocol

Protocol v1 defines provider- and transport-neutral JSON request and response envelopes. Requests carry `protocol_version`, `request_id`, `input`, and optional metadata. Responses echo the version and request ID and carry a status and text, with structured error details on failures. The schema and compatibility rules are specified in [PROTOCOL_V1.md](PROTOCOL_V1.md); the Python reference implementation lives in `nspire_ai.protocol`.

## Constraints and open questions

- The calculator model has no built-in Wi-Fi or Bluetooth.
- A phone hotspot alone does not give the calculator a network interface.
- Any external adapter would need a supported physical connection and suitable software/firmware; it will not automatically behave like a network card.
- Ndless compatibility, available I/O APIs, cable options, and OS-specific behavior need hands-on verification.
- Cloud AI requires a network-connected host device and careful handling of credentials and user data.

## Design principles

- Keep components replaceable.
- Use explicit protocol versions and request IDs.
- Handle timeouts, malformed messages, and unavailable services.
- Keep secrets outside the repository.
- Test on a PC before attempting calculator integration.
