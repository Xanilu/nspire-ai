# NSPIRE AI Protocol v1

Protocol v1 defines provider-neutral request and response envelopes. It does not prescribe a transport, AI provider, retry policy, or client implementation. The Python reference models are in `software/pc-prototype/src/nspire_ai/protocol.py` and use only the standard library.

## JSON messages

Each message is one UTF-8 JSON object. Field names and types are case-sensitive. `protocol_version` is the integer `1`. Unknown fields are rejected by the v1 reference implementation so that misspellings do not pass silently.

### Request

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `protocol_version` | yes | integer | Protocol schema version; v1 is `1`. |
| `request_id` | yes | string | Non-empty identifier chosen by the sender. Responses echo it exactly. |
| `input` | yes | string | Non-empty user input text. The protocol assigns no semantics to its contents. |
| `metadata` | no | object | Optional application-defined JSON values; not interpreted by the protocol. |

```json
{
  "protocol_version": 1,
  "request_id": "req-20261030-001",
  "input": "Erkläre die zweite Newtonsche Regel.",
  "metadata": {"locale": "de-DE"}
}
```

### Response

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `protocol_version` | yes | integer | Must match the request protocol version. |
| `request_id` | yes | string | Identifier copied from the corresponding request. |
| `status` | yes | string | `success` or `error`. |
| `text` | yes | string | Result text, or a human-readable summary when status is `error`. |
| `error` | conditional | object | Required for `error`, forbidden for `success`; includes non-empty `code` and `message`, and may include `details`. |
| `metadata` | no | object | Optional application-defined JSON values. |

Successful response:

```json
{
  "protocol_version": 1,
  "request_id": "req-20261030-001",
  "status": "success",
  "text": "Die zweite Regel lautet F = m · a."
}
```

Error response:

```json
{
  "protocol_version": 1,
  "request_id": "req-20261030-001",
  "status": "error",
  "text": "Die Anfrage konnte nicht verarbeitet werden.",
  "error": {
    "code": "provider_unavailable",
    "message": "Der konfigurierte Anbieter ist nicht erreichbar.",
    "details": {"retryable": true}
  }
}
```

## Validation and failures

Implementations must check required fields, JSON types, non-empty identifiers and text, supported versions, and status/error consistency. Metadata and error details must be representable as JSON. The Python implementation raises `ProtocolValidationError`, which exposes a stable `code` and a JSON `path` (for example, `$.request_id`) alongside a readable message. JSON parsing failures use `malformed_json`; absent fields use `missing_field`; type mismatches use `invalid_type`; unsupported versions use `unsupported_version`.

Invalid request example (missing `input`):

```json
{"protocol_version": 1, "request_id": "req-1"}
```

Unsupported version example:

```json
{"protocol_version": 2, "request_id": "req-1", "input": "Hello"}
```

Malformed JSON example:

```text
{"protocol_version": 1,
```

These are rejected; implementations should report a local protocol/validation error where possible. A response cannot be relied on when the message is malformed or its request ID cannot be read.

## Versioning and compatibility

Version 1 uses an integer major schema version. A change that alters required fields, field types, status meanings, or validation rules incompatibly requires a new protocol version. Additive fields or statuses must not be assumed compatible with v1 consumers: v1 implementations reject unknown fields and statuses. Negotiate or explicitly select a newer version before sending it. A response uses the same version as its request. Keep `request_id` opaque and unique among outstanding requests; this specification does not mandate a UUID format.

Metadata is reserved for optional context agreed by communicating applications; it must not redefine core fields. No credentials or provider-specific control fields belong in the protocol envelope. Transport framing, authentication, timeouts, retries, and privacy policy are out of scope and must be defined by a future communication layer.
