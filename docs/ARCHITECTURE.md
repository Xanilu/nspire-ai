# Architecture

## Status

This document describes the intended direction. It is a design hypothesis, not a record of a fully working system.

## Core idea

The TI-Nspire CX II should provide the user interface and input experience. More demanding work—especially language-model inference—should run on an external host or a cloud service.

## Logical components

### 1. Calculator client
A lightweight Ndless application may eventually handle input, display, and message exchange. Exact APIs and compatibility must be verified on the target calculator and OS version.

### 2. Communication layer
A transport adapter moves structured requests and responses between the calculator and the external host. The protocol should remain independent of the physical transport so that alternatives can be tested.

### 3. Host application
The host receives requests, validates them, routes tasks, and returns formatted results. The first implementation will run on a PC to simplify development and debugging.

### 4. AI engine
The AI engine exposes a provider-neutral interface for model calls and task-specific behavior. API credentials must remain on the host and must never be embedded in calculator files or committed to Git.

## Initial message shape

A first protocol can use a small structured envelope:

```json
{
  "version": 1,
  "request_id": "example-001",
  "task": "explain",
  "input": "Explain Newton's second law."
}
```

The response should carry the same request identifier, a status, and a text result. The final schema will be specified alongside the first implementation.

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
