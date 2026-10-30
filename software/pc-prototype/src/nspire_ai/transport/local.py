"""Request/response exchange over a connected, blocking binary stream."""

from __future__ import annotations

from typing import BinaryIO, Callable

from nspire_ai.protocol import (
    ProtocolRequest,
    ProtocolResponse,
    ProtocolValidationError,
)
from nspire_ai.transport.framing import (
    DEFAULT_MAX_MESSAGE_SIZE,
    TransportError,
    read_frame,
    validate_max_message_size,
    write_frame,
)

RequestHandler = Callable[[ProtocolRequest], ProtocolResponse]


class LocalStreamClient:
    """Synchronous client for an already-connected blocking stream."""

    def __init__(
        self,
        stream: BinaryIO,
        *,
        max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
    ) -> None:
        validate_max_message_size(max_message_size)
        self._stream = stream
        self._max_message_size = max_message_size

    def request(self, request: ProtocolRequest) -> ProtocolResponse:
        """Send one request and ensure its response matches the request ID/version."""
        write_frame(
            self._stream,
            request.to_json().encode("utf-8"),
            max_message_size=self._max_message_size,
        )
        payload = read_frame(self._stream, max_message_size=self._max_message_size)
        if payload is None:
            raise TransportError("unexpected_eof", "Stream ended before a response arrived.")
        response = _decode_response(payload)
        if response.request_id != request.request_id:
            raise TransportError(
                "request_id_mismatch",
                f"Response ID {response.request_id!r} does not match request ID {request.request_id!r}.",
            )
        if response.protocol_version != request.protocol_version:
            raise TransportError(
                "version_mismatch",
                "Response protocol version does not match the request.",
            )
        return response


def serve_requests(
    stream: BinaryIO,
    handler: RequestHandler,
    *,
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
) -> int:
    """Serve sequential requests until clean EOF; return the number handled."""
    validate_max_message_size(max_message_size)
    handled = 0
    while True:
        payload = read_frame(stream, max_message_size=max_message_size)
        if payload is None:
            return handled
        request = _decode_request(payload)
        response = handler(request)
        if response.request_id != request.request_id:
            raise TransportError(
                "request_id_mismatch",
                "Handler response ID does not match the received request ID.",
            )
        if response.protocol_version != request.protocol_version:
            raise TransportError(
                "version_mismatch",
                "Handler response version does not match the received request.",
            )
        write_frame(
            stream,
            response.to_json().encode("utf-8"),
            max_message_size=max_message_size,
        )
        handled += 1


def _decode_request(payload: bytes) -> ProtocolRequest:
    try:
        return ProtocolRequest.from_json(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise TransportError("invalid_utf8", "Request payload is not valid UTF-8.") from exc
    except ProtocolValidationError as exc:
        raise TransportError("invalid_request", str(exc)) from exc


def _decode_response(payload: bytes) -> ProtocolResponse:
    try:
        return ProtocolResponse.from_json(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise TransportError("invalid_utf8", "Response payload is not valid UTF-8.") from exc
    except ProtocolValidationError as exc:
        raise TransportError("invalid_response", str(exc)) from exc
