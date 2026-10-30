"""Application configuration loaded from environment variables."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from nspire_ai.errors import ConfigurationError


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value (true/false).")


def _read_positive_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be a positive integer.")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings. Secrets are read from the environment, never files."""

    app_name: str = "NSPIRE AI"
    log_level: str = "INFO"
    provider: str = "mock"
    model: str = "gpt-4.1-mini"
    request_timeout: float = 30.0
    debug: bool = False
    system_context: str = ""
    max_input_chars: int = 10_000
    max_context_chars: int = 24_000
    max_context_messages: int = 32
    max_history_messages: int = 200
    max_history_chars: int = 100_000
    max_conversations: int = 1_000

    @classmethod
    def from_env(cls) -> "Settings":
        level = os.getenv("NSPIRE_AI_LOG_LEVEL", "INFO").strip().upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ConfigurationError(
                "NSPIRE_AI_LOG_LEVEL must be CRITICAL, ERROR, WARNING, INFO, or DEBUG."
            )

        provider = os.getenv("NSPIRE_AI_PROVIDER", "mock").strip().lower()
        if not provider:
            raise ConfigurationError("NSPIRE_AI_PROVIDER cannot be empty.")

        model = os.getenv("NSPIRE_AI_MODEL", "gpt-4.1-mini").strip()
        if not model:
            raise ConfigurationError("NSPIRE_AI_MODEL cannot be empty.")
        timeout_raw = os.getenv("NSPIRE_AI_REQUEST_TIMEOUT", "30")
        try:
            request_timeout = float(timeout_raw)
        except ValueError as exc:
            raise ConfigurationError("NSPIRE_AI_REQUEST_TIMEOUT must be a positive number of seconds.") from exc
        if not math.isfinite(request_timeout) or request_timeout <= 0:
            raise ConfigurationError("NSPIRE_AI_REQUEST_TIMEOUT must be a positive number of seconds.")

        system_context = os.getenv("NSPIRE_AI_SYSTEM_CONTEXT", "")
        max_input_chars = _read_positive_int("NSPIRE_AI_MAX_INPUT_CHARS", 10_000)
        max_context_chars = _read_positive_int("NSPIRE_AI_MAX_CONTEXT_CHARS", 24_000)
        max_context_messages = _read_positive_int("NSPIRE_AI_MAX_CONTEXT_MESSAGES", 32)
        max_history_messages = _read_positive_int("NSPIRE_AI_MAX_HISTORY_MESSAGES", 200)
        max_history_chars = _read_positive_int("NSPIRE_AI_MAX_HISTORY_CHARS", 100_000)
        max_conversations = _read_positive_int("NSPIRE_AI_MAX_CONVERSATIONS", 1_000)
        if max_history_messages < 2 or max_history_messages % 2:
            raise ConfigurationError("NSPIRE_AI_MAX_HISTORY_MESSAGES must be an even integer of at least two.")
        if system_context and max_context_messages < 2:
            raise ConfigurationError(
                "NSPIRE_AI_MAX_CONTEXT_MESSAGES must be at least two when NSPIRE_AI_SYSTEM_CONTEXT is configured."
            )
        if system_context and (not system_context.strip() or len(system_context) >= max_context_chars):
            raise ConfigurationError("NSPIRE_AI_SYSTEM_CONTEXT must leave room within the context character limit.")

        return cls(
            log_level=level,
            provider=provider,
            model=model,
            request_timeout=request_timeout,
            debug=_read_bool("NSPIRE_AI_DEBUG", False),
            system_context=system_context,
            max_input_chars=max_input_chars,
            max_context_chars=max_context_chars,
            max_context_messages=max_context_messages,
            max_history_messages=max_history_messages,
            max_history_chars=max_history_chars,
            max_conversations=max_conversations,
        )

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parents[2]
