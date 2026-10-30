"""Transport- and provider-neutral JSON message models for NSPIRE AI Protocol v1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1


class ProtocolValidationError(ValueError):
    """Invalid protocol data, with a stable machine-readable code and field path."""

    def __init__(self, code: str, message: str, path: str = "$") -> None:
        self.code = code
        self.path = path.strip()
        self.message = message
        super().__init__(f"{code} at {self.path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolValidationError("invalid_type", "Expected a JSON object.", path)
    return value


def _validate_version(data: dict[str, Any]) -> None:
    if "protocol_version" not in data:
        raise ProtocolValidationError("missing_field", "Required field is missing.", "$.protocol_version")
    version = data["protocol_version"]
    if type(version) is not int:
        raise ProtocolValidationError("invalid_type", "Expected an integer.", "$.protocol_version")
    if version != PROTOCOL_VERSION:
        raise ProtocolValidationError(
            "unsupported_version", f"Protocol version {version} is not supported; expected {PROTOCOL_VERSION}.", "$.protocol_version"
        )


def _required_string(data: dict[str, Any], name: str) -> str:
    path = f"$.{name}"
    if name not in data:
        raise ProtocolValidationError("missing_field", "Required field is missing.", path)
    value = data[name]
    if not isinstance(value, str):
        raise ProtocolValidationError("invalid_type", "Expected a string.", path)
    if not value.strip():
        raise ProtocolValidationError("invalid_value", "Value cannot be empty or whitespace.", path)
    return value


def _metadata(data: dict[str, Any]) -> dict[str, Any] | None:
    if "metadata" not in data:
        return None
    value = data["metadata"]
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ProtocolValidationError("invalid_type", "Expected an object with string keys.", "$.metadata")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProtocolValidationError("invalid_value", "Metadata must contain JSON-compatible values.", "$.metadata") from exc
    return value


def _reject_unknown(data: dict[str, Any], allowed: set[str]) -> None:
    for key in data:
        if key not in allowed:
            raise ProtocolValidationError("unknown_field", "Field is not defined by Protocol v1.", f"$.{key}")


@dataclass(frozen=True, slots=True)
class ProtocolRequest:
    request_id: str
    input: str
    metadata: dict[str, Any] | None = None
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if type(self.protocol_version) is not int or self.protocol_version != PROTOCOL_VERSION:
            raise ProtocolValidationError("unsupported_version", f"Only protocol version {PROTOCOL_VERSION} is supported.", "$.protocol_version")
        for name, value in (("request_id", self.request_id), ("input", self.input)):
            if not isinstance(value, str):
                raise ProtocolValidationError("invalid_type", "Expected a string.", f"$.{name}")
            if not value.strip():
                raise ProtocolValidationError("invalid_value", "Value cannot be empty or whitespace.", f"$.{name}")
        if self.metadata is not None:
            _metadata({"metadata": self.metadata})

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "input": self.input,
        }
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_dict(cls, value: Any) -> "ProtocolRequest":
        data = _object(value, "$")
        _reject_unknown(data, {"protocol_version", "request_id", "input", "metadata"})
        _validate_version(data)
        return cls(_required_string(data, "request_id"), _required_string(data, "input"), _metadata(data))

    @classmethod
    def from_json(cls, value: str) -> "ProtocolRequest":
        return cls.from_dict(_parse_json(value))


@dataclass(frozen=True, slots=True)
class ProtocolResponse:
    request_id: str
    status: str
    text: str
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if type(self.protocol_version) is not int or self.protocol_version != PROTOCOL_VERSION:
            raise ProtocolValidationError("unsupported_version", f"Only protocol version {PROTOCOL_VERSION} is supported.", "$.protocol_version")
        for name, value in (("request_id", self.request_id), ("status", self.status), ("text", self.text)):
            if not isinstance(value, str):
                raise ProtocolValidationError("invalid_type", "Expected a string.", f"$.{name}")
            if not value.strip():
                raise ProtocolValidationError("invalid_value", "Value cannot be empty or whitespace.", f"$.{name}")
        if self.status not in {"success", "error"}:
            raise ProtocolValidationError("invalid_value", "Status must be 'success' or 'error'.", "$.status")
        if self.error is not None:
            if not isinstance(self.error, dict):
                raise ProtocolValidationError("invalid_type", "Expected an object.", "$.error")
            if not isinstance(self.error.get("code"), str) or not self.error["code"].strip():
                raise ProtocolValidationError("missing_field", "Error requires a non-empty string code.", "$.error.code")
            if not isinstance(self.error.get("message"), str) or not self.error["message"].strip():
                raise ProtocolValidationError("missing_field", "Error requires a non-empty string message.", "$.error.message")
            try:
                json.dumps(self.error, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ProtocolValidationError("invalid_value", "Error must contain JSON-compatible values.", "$.error") from exc
        if self.status == "error" and self.error is None:
            raise ProtocolValidationError("missing_field", "Error responses require error details.", "$.error")
        if self.status == "success" and self.error is not None:
            raise ProtocolValidationError("invalid_value", "Success responses cannot include error details.", "$.error")
        if self.metadata is not None:
            _metadata({"metadata": self.metadata})

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "status": self.status,
            "text": self.text,
        }
        if self.error is not None:
            result["error"] = self.error
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_dict(cls, value: Any) -> "ProtocolResponse":
        data = _object(value, "$")
        _reject_unknown(data, {"protocol_version", "request_id", "status", "text", "error", "metadata"})
        _validate_version(data)
        return cls(
            _required_string(data, "request_id"),
            _required_string(data, "status"),
            _required_string(data, "text"),
            data.get("error"),
            _metadata(data),
        )

    @classmethod
    def from_json(cls, value: str) -> "ProtocolResponse":
        return cls.from_dict(_parse_json(value))


def _parse_json(value: str) -> Any:
    if not isinstance(value, str):
        raise ProtocolValidationError("invalid_type", "JSON input must be a string.", "$")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProtocolValidationError("malformed_json", f"Invalid JSON at line {exc.lineno}, column {exc.colno}.", "$") from exc
