import json

import pytest

from nspire_ai.protocol import (
    PROTOCOL_VERSION,
    ProtocolRequest,
    ProtocolResponse,
    ProtocolValidationError,
)


def test_valid_request_and_roundtrip():
    request = ProtocolRequest("req-123", "Explain gravity", {"locale": "de-DE"})
    decoded = ProtocolRequest.from_json(request.to_json())
    assert decoded == request
    assert json.loads(request.to_json())["protocol_version"] == PROTOCOL_VERSION


def test_request_rejects_missing_required_field():
    with pytest.raises(ProtocolValidationError, match="missing_field") as exc:
        ProtocolRequest.from_dict({"protocol_version": 1, "request_id": "req-1"})
    assert exc.value.path == "$.input"


def test_request_rejects_invalid_datatype():
    with pytest.raises(ProtocolValidationError, match="invalid_type") as exc:
        ProtocolRequest.from_dict({"protocol_version": 1, "request_id": "req-1", "input": 7})
    assert exc.value.path == "$.input"


def test_malformed_json_has_clear_error():
    with pytest.raises(ProtocolValidationError, match="malformed_json"):
        ProtocolRequest.from_json('{"protocol_version": 1,')


def test_unsupported_version_is_rejected():
    with pytest.raises(ProtocolValidationError, match="unsupported_version"):
        ProtocolRequest.from_dict({"protocol_version": 2, "request_id": "req-1", "input": "Hi"})


def test_valid_success_response_roundtrip():
    response = ProtocolResponse("req-123", "success", "Gravity attracts masses.")
    assert ProtocolResponse.from_json(response.to_json()) == response


def test_valid_error_response_roundtrip():
    response = ProtocolResponse(
        "req-123", "error", "The request could not be processed.",
        {"code": "provider_unavailable", "message": "Provider is unavailable.", "details": {"retryable": True}},
        {"locale": "de-DE"},
    )
    assert ProtocolResponse.from_json(response.to_json()) == response


def test_response_requires_error_details_for_error_status():
    with pytest.raises(ProtocolValidationError, match="missing_field") as exc:
        ProtocolResponse("req-123", "error", "Failed")
    assert exc.value.path == "$.error"


def test_response_rejects_invalid_datatype():
    with pytest.raises(ProtocolValidationError, match="invalid_type"):
        ProtocolResponse.from_dict({
            "protocol_version": 1, "request_id": "req-1", "status": "success", "text": ["bad"]
        })


def test_unknown_fields_are_rejected():
    with pytest.raises(ProtocolValidationError, match="unknown_field"):
        ProtocolRequest.from_dict({
            "protocol_version": 1, "request_id": "req-1", "input": "Hi", "task": "explain"
        })
