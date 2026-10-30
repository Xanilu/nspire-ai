import io
import socket
import struct
import threading

import pytest

from nspire_ai.core import handle_request
from nspire_ai.errors import ProviderError
from nspire_ai.protocol import ProtocolRequest, ProtocolResponse
from nspire_ai.providers.mock import MockProvider
from nspire_ai.transport.framing import (
    ABSOLUTE_MAX_MESSAGE_SIZE,
    DEFAULT_MAX_MESSAGE_SIZE,
    TransportError,
    read_frame,
    write_frame,
)
from nspire_ai.transport.local import LocalStreamClient, serve_requests


class FragmentedReader:
    def __init__(self, data: bytes, chunk_size: int = 2):
        self._source = io.BytesIO(data)
        self._chunk_size = chunk_size

    def read(self, size: int = -1) -> bytes:
        return self._source.read(min(size, self._chunk_size))


class FragmentedWriter:
    def __init__(self, chunk_size: int = 3):
        self.data = bytearray()
        self._chunk_size = chunk_size

    def write(self, data) -> int:
        chunk = bytes(data[: self._chunk_size])
        self.data.extend(chunk)
        return len(chunk)

    def flush(self) -> None:
        pass


class DuplexStream:
    def __init__(self, incoming: bytes):
        self._incoming = io.BytesIO(incoming)
        self.outgoing = io.BytesIO()

    def read(self, size: int = -1) -> bytes:
        return self._incoming.read(size)

    def write(self, data) -> int:
        return self.outgoing.write(data)

    def flush(self) -> None:
        pass


class FailingReader:
    def read(self, size: int = -1) -> bytes:
        raise OSError("closed stream")


class FailingWriter:
    def write(self, data) -> int:
        raise OSError("closed stream")


def frame(payload: bytes) -> bytes:
    return struct.pack("!I", len(payload)) + payload


def test_length_prefixed_frame_handles_fragmented_reads_and_writes():
    payload = '{"message":"Grüße 🌍"}'.encode("utf-8")
    writer = FragmentedWriter()
    write_frame(writer, payload)
    assert read_frame(FragmentedReader(bytes(writer.data))) == payload


def test_multiple_frames_can_be_read_sequentially():
    stream = io.BytesIO(frame(b"first") + frame(b"second"))
    assert read_frame(stream) == b"first"
    assert read_frame(stream) == b"second"
    assert read_frame(stream) is None


def test_zero_length_frame_is_rejected():
    with pytest.raises(TransportError, match="invalid_length"):
        read_frame(io.BytesIO(struct.pack("!I", 0)))


def test_oversized_frame_is_rejected_on_read_and_write():
    with pytest.raises(TransportError, match="message_too_large"):
        read_frame(io.BytesIO(frame(b"12345")), max_message_size=4)
    with pytest.raises(TransportError, match="message_too_large"):
        write_frame(io.BytesIO(), b"12345", max_message_size=4)


def test_default_and_absolute_message_size_limits():
    assert DEFAULT_MAX_MESSAGE_SIZE == 1_048_576
    assert ABSOLUTE_MAX_MESSAGE_SIZE == 16_777_216
    assert read_frame(io.BytesIO(), max_message_size=ABSOLUTE_MAX_MESSAGE_SIZE) is None


@pytest.mark.parametrize(
    "limit", [0, -1, 1.5, True, ABSOLUTE_MAX_MESSAGE_SIZE + 1]
)
def test_invalid_message_size_limits_are_rejected_immediately(limit):
    with pytest.raises(TransportError, match="invalid_limit"):
        read_frame(io.BytesIO(), max_message_size=limit)
    with pytest.raises(TransportError, match="invalid_limit"):
        LocalStreamClient(io.BytesIO(), max_message_size=limit)
    with pytest.raises(TransportError, match="invalid_limit"):
        serve_requests(io.BytesIO(), lambda request: None, max_message_size=limit)


def test_stream_io_errors_are_reported_as_transport_errors():
    with pytest.raises(TransportError, match="read_failed"):
        read_frame(FailingReader())
    with pytest.raises(TransportError, match="write_failed"):
        write_frame(FailingWriter(), b"payload")


@pytest.mark.parametrize("data", [b"\x00\x00", frame(b"abc")[:-1]])
def test_truncated_header_or_payload_is_reported(data):
    with pytest.raises(TransportError, match="truncated_frame"):
        read_frame(io.BytesIO(data))


def test_invalid_json_request_is_reported_by_server():
    with pytest.raises(TransportError, match="invalid_request"):
        serve_requests(io.BytesIO(frame(b"not json")), lambda request: None)


def test_server_rejects_invalid_utf8_request():
    with pytest.raises(TransportError, match="invalid_utf8"):
        serve_requests(io.BytesIO(frame(b"\xff")), lambda request: None)


def test_client_rejects_invalid_utf8_response():
    client = LocalStreamClient(DuplexStream(frame(b"\xff")))
    with pytest.raises(TransportError, match="invalid_utf8"):
        client.request(ProtocolRequest("req-utf8", "question"))


def test_client_rejects_invalid_response_json():
    client = LocalStreamClient(DuplexStream(frame(b"not json")))
    with pytest.raises(TransportError, match="invalid_response"):
        client.request(ProtocolRequest("req-json", "question"))


def test_client_rejects_response_with_wrong_request_id():
    response = ProtocolResponse("different-id", "success", "answer")
    stream = DuplexStream(frame(response.to_json().encode("utf-8")))
    client = LocalStreamClient(stream)
    with pytest.raises(TransportError, match="request_id_mismatch"):
        client.request(ProtocolRequest("expected-id", "question"))


def test_server_rejects_handler_response_with_wrong_request_id():
    request = ProtocolRequest("request-id", "question")
    response = ProtocolResponse("wrong-id", "success", "answer")
    incoming = io.BytesIO(frame(request.to_json().encode("utf-8")))
    with pytest.raises(TransportError, match="request_id_mismatch"):
        serve_requests(incoming, lambda received: response)


def test_core_maps_provider_failure_to_protocol_error_response():
    class BrokenProvider:
        @property
        def name(self):
            return "broken"

        def generate(self, prompt):
            raise ProviderError("provider offline")

    response = handle_request(ProtocolRequest("req-fail", "question"), BrokenProvider())
    assert response.request_id == "req-fail"
    assert response.status == "error"
    assert response.error == {
        "code": "provider_error",
        "message": "The configured provider could not process the request.",
    }


def test_provider_exception_secret_is_not_returned_or_logged(caplog):
    sentinel = "SENTINEL-SECRET-DO-NOT-LEAK"

    class SecretFailingProvider:
        @property
        def name(self):
            return "secret-test-provider"

        def generate(self, prompt):
            raise RuntimeError(f"provider failed with credential {sentinel}")

    request = ProtocolRequest("req-secret", f"request body {sentinel}")
    response = handle_request(request, SecretFailingProvider())

    serialized = response.to_json()
    assert sentinel not in serialized
    assert sentinel not in caplog.text
    assert response.protocol_version == 1
    assert response.request_id == request.request_id
    assert response.status == "error"
    assert response.text == "The request could not be processed."
    assert response.error == {
        "code": "provider_error",
        "message": "The configured provider could not process the request.",
    }


def test_local_socketpair_end_to_end_with_mock_provider_and_multiple_requests():
    client_socket, server_socket = socket.socketpair()
    client_socket.settimeout(3)
    server_socket.settimeout(3)
    client_stream = client_socket.makefile("rwb", buffering=0)
    server_stream = server_socket.makefile("rwb", buffering=0)
    errors = []

    def serve():
        try:
            count = serve_requests(
                server_stream,
                lambda request: handle_request(request, MockProvider()),
            )
            assert count == 2
        except BaseException as exc:  # surfaced in the test thread
            errors.append(exc)

    worker = threading.Thread(target=serve)
    worker.start()
    client = LocalStreamClient(client_stream)
    try:
        first = client.request(ProtocolRequest("req-1", "Explain gravity"))
        second = client.request(ProtocolRequest("req-2", "Explain friction"))
        client_socket.shutdown(socket.SHUT_WR)
        worker.join(timeout=3)
        assert not worker.is_alive()
        assert errors == []
        assert first.request_id == "req-1"
        assert first.status == "success"
        assert first.text == "Mock provider received: Explain gravity"
        assert first.metadata == {"provider": "mock"}
        assert second.request_id == "req-2"
        assert second.text == "Mock provider received: Explain friction"
    finally:
        client_stream.close()
        server_stream.close()
        client_socket.close()
        server_socket.close()
