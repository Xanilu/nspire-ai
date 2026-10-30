"""Application configuration loaded from environment variables."""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings. Secrets are read from the environment, never files."""

    app_name: str = "NSPIRE AI"
    log_level: str = "INFO"
    provider: str = "mock"
    debug: bool = False

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

        return cls(
            log_level=level,
            provider=provider,
            debug=_read_bool("NSPIRE_AI_DEBUG", False),
        )

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parents[2]
