"""Length-prefixed JSON framing for blocking binary streams."""

from __future__ import annotations

import struct
from typing import BinaryIO

HEADER_SIZE = 4
DEFAULT_MAX_MESSAGE_SIZE = 1_048_576
ABSOLUTE_MAX_MESSAGE_SIZE = 16_777_216
_HEADER = struct.Struct("!I")


class TransportError(Exception):
    """Transport failure with a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def write_frame(
    stream: BinaryIO,
    payload: bytes,
    *,
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
) -> None:
    """Write one non-empty payload as a 4-byte big-endian length plus bytes."""
    if not isinstance(payload, bytes):
        raise TransportError("invalid_payload", "Frame payload must be bytes.")
    validate_max_message_size(max_message_size)
    size = len(payload)
    if size == 0:
        raise TransportError("invalid_length", "Frame payload cannot be empty.")
    if size > max_message_size:
        raise TransportError(
            "message_too_large",
            f"Frame size {size} exceeds the {max_message_size}-byte limit.",
        )
    _write_all(stream, _HEADER.pack(size) + payload)


def read_frame(
    stream: BinaryIO,
    *,
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
) -> bytes | None:
    """Read one frame; return None only for clean EOF before a header starts."""
    validate_max_message_size(max_message_size)
    header = _read_exact(stream, HEADER_SIZE, allow_clean_eof=True)
    if header is None:
        return None
    (size,) = _HEADER.unpack(header)
    if size == 0:
        raise TransportError("invalid_length", "Frame length must be greater than zero.")
    if size > max_message_size:
        raise TransportError(
            "message_too_large",
            f"Frame size {size} exceeds the {max_message_size}-byte limit.",
        )
    payload = _read_exact(stream, size)
    assert payload is not None
    return payload


def _read_exact(stream: BinaryIO, size: int, *, allow_clean_eof: bool = False) -> bytes | None:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        try:
            chunk = stream.read(remaining)
        except OSError as exc:
            raise TransportError("read_failed", "Binary stream read failed.") from exc
        if not chunk:
            received = size - remaining
            if allow_clean_eof and received == 0:
                return None
            raise TransportError(
                "truncated_frame",
                f"Stream ended after {received} of {size} expected bytes.",
            )
        if not isinstance(chunk, bytes):
            raise TransportError("read_failed", "Binary stream returned non-byte data.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _write_all(stream: BinaryIO, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        try:
            count = stream.write(view[written:])
        except OSError as exc:
            raise TransportError("write_failed", "Binary stream write failed.") from exc
        if count is None or count <= 0:
            raise TransportError("write_failed", "Binary stream did not accept any data.")
        written += count
    flush = getattr(stream, "flush", None)
    if flush is not None:
        try:
            flush()
        except OSError as exc:
            raise TransportError("write_failed", "Binary stream flush failed.") from exc


def validate_max_message_size(limit: int) -> None:
    """Validate a payload limit between one byte and the absolute 16 MiB cap."""
    if type(limit) is not int or limit < 1 or limit > ABSOLUTE_MAX_MESSAGE_SIZE:
        raise TransportError(
            "invalid_limit",
            f"Maximum message size must be between 1 and {ABSOLUTE_MAX_MESSAGE_SIZE} bytes.",
        )
