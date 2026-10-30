# NSPIRE AI Transport Layer 0.1

Transport Layer 0.1 adds synchronous framed message exchange over an already-connected, blocking binary stream. It uses Protocol v1 messages and the Python standard library. The transport does not depend on an AI provider; request processing is a separate application-core function.

## Architecture and responsibilities

- `nspire_ai.transport.framing` reads and writes bounded length-prefixed frames. It knows nothing about JSON schemas or AI providers.
- `nspire_ai.transport.local.LocalStreamClient` sends a `ProtocolRequest`, receives a `ProtocolResponse`, and verifies the response version and request ID.
- `serve_requests` validates incoming Protocol v1 requests, passes each to a handler, checks the matching response ID/version, and writes responses in order. It handles messages sequentially until clean EOF.
- `nspire_ai.core.handle_request` calls an `AIProvider`, maps the result to a Protocol v1 response, and maps expected provider failures to structured error responses.
- `nspire_ai.protocol` remains the canonical schema and JSON validation layer.

No layer in this milestone opens a listening port, connects to a remote host, or communicates with calculator hardware. The end-to-end test connects two local stream endpoints with the operating system's socket-pair primitive. Client and server run in separate threads of the same test process; this is not an inter-process test and creates no network listener.

## Framing and message layout

Every frame has a 4-byte unsigned big-endian payload length followed immediately by exactly that many bytes:

```text
+----------------------+------------------------------+
| length (4 bytes, !I)  | UTF-8 encoded JSON payload    |
+----------------------+------------------------------+
```

The length counts payload bytes, not characters, and excludes the header. The payload is one Protocol v1 JSON request or response object. A stream can carry multiple frames consecutively. The reader loops until the requested byte count is received, so ordinary short/fragmented reads are supported. The writer loops on partial writes.

## Size limits and failures

The default maximum payload is 1,048,576 bytes (1 MiB). Callers may choose a lower limit, but no configured limit may exceed the absolute cap of 16,777,216 bytes (16 MiB). Limits must be integers greater than zero; invalid values are rejected before stream processing. The 4-byte length prefix can represent larger values, but the implementation rejects them to bound memory use. Empty frames are invalid.

`TransportError` exposes a stable `code` and a readable message. Codes include `invalid_length`, `invalid_limit`, `message_too_large`, `truncated_frame`, `invalid_utf8`, `invalid_request`, `invalid_response`, `request_id_mismatch`, `version_mismatch`, and `unexpected_eof`. EOF before any byte of the next header is clean end-of-stream; EOF after a partial header or during a payload raises `truncated_frame`. Malformed JSON and schema validation failures are surfaced as `invalid_request` or `invalid_response`, with the underlying validation description retained. Provider failures return a generic Protocol v1 error message; raw provider exception details and request content are not included in that response or logged by the core handler.

An invalid request is not answered with a protocol error response: the request ID may be absent or untrustworthy. The server raises a transport error and the caller must decide whether to close the stream or log/report the failure. Expected provider failures are different: the core can return a normal Protocol v1 `error` response because it has a validated request ID.

## Local test

From `software/pc-prototype`, install the project as described in its README and run:

```powershell
python -m pytest
```

`tests/test_transport.py` includes framing/serialization checks, simulated short reads and writes, multiple consecutive frames, invalid and oversized lengths, invalid limit configuration, truncated frames, invalid UTF-8, malformed request and response JSON, request-ID correlation, safe provider-error mapping, and a local socket-pair end-to-end exchange using `MockProvider`. The client and server run in separate threads of the same process. No internet connection or external AI service is used.

## Limitations and extensions

- Streams are blocking and have no built-in timeout, cancellation, retry, authentication, or encryption.
- One client instance supports a synchronous request followed by its response; concurrent outstanding requests and multiplexing are not supported.
- The server processes one request at a time and leaves stream ownership and lifecycle to its caller.
- OS socket-pair behavior is used only for the local end-to-end test; no production listener/client connector is provided.
- Hardware, USB, WLAN, Bluetooth, Ndless, and remote network transports are out of scope and their feasibility is unverified.

Future adapters can supply any compatible blocking binary stream and reuse the framing functions and Protocol v1 models. A later network or device transport will need a separately reviewed lifecycle, timeout, security, and compatibility design.
