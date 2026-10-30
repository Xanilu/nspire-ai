import pytest

from nspire_ai.config import Settings
from nspire_ai.errors import ConfigurationError


@pytest.fixture(autouse=True)
def clear_config_environment(monkeypatch):
    for name in (
        "NSPIRE_AI_PROVIDER",
        "NSPIRE_AI_LOG_LEVEL",
        "NSPIRE_AI_MODEL",
        "NSPIRE_AI_REQUEST_TIMEOUT",
        "NSPIRE_AI_DEBUG",
        "NSPIRE_AI_SYSTEM_CONTEXT",
        "NSPIRE_AI_MAX_INPUT_CHARS",
        "NSPIRE_AI_MAX_CONTEXT_CHARS",
        "NSPIRE_AI_MAX_CONTEXT_MESSAGES",
        "NSPIRE_AI_MAX_HISTORY_MESSAGES",
        "NSPIRE_AI_MAX_HISTORY_CHARS",
        "NSPIRE_AI_MAX_CONVERSATIONS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_safe(monkeypatch):
    for name in (
        "NSPIRE_AI_PROVIDER",
        "NSPIRE_AI_LOG_LEVEL",
        "NSPIRE_AI_DEBUG",
        "NSPIRE_AI_SYSTEM_CONTEXT",
        "NSPIRE_AI_MAX_INPUT_CHARS",
        "NSPIRE_AI_MAX_CONTEXT_CHARS",
        "NSPIRE_AI_MAX_CONTEXT_MESSAGES",
        "NSPIRE_AI_MAX_HISTORY_MESSAGES",
        "NSPIRE_AI_MAX_HISTORY_CHARS",
        "NSPIRE_AI_MAX_CONVERSATIONS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.provider == "mock"
    assert settings.log_level == "INFO"
    assert settings.debug is False
    assert settings.model == "gpt-4.1-mini"
    assert settings.request_timeout == 30.0
    assert settings.max_history_chars == 100_000


def test_environment_values_are_normalized(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_PROVIDER", " MOCK ")
    monkeypatch.setenv("NSPIRE_AI_LOG_LEVEL", "debug")
    monkeypatch.setenv("NSPIRE_AI_DEBUG", "yes")
    assert Settings.from_env() == Settings(provider="mock", log_level="DEBUG", debug=True)


def test_model_and_timeout_are_configurable(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_MODEL", " custom-model ")
    monkeypatch.setenv("NSPIRE_AI_REQUEST_TIMEOUT", "2.5")
    assert Settings.from_env().model == "custom-model"
    assert Settings.from_env().request_timeout == 2.5


def test_empty_model_and_invalid_timeout_are_rejected(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_MODEL", "  ")
    try:
        Settings.from_env()
    except ConfigurationError:
        pass
    else:
        raise AssertionError("Expected empty model to fail")
    monkeypatch.setenv("NSPIRE_AI_MODEL", "ok")
    for value in ("0", "-1", "nan", "inf", "bad"):
        monkeypatch.setenv("NSPIRE_AI_REQUEST_TIMEOUT", value)
        try:
            Settings.from_env()
        except ConfigurationError:
            continue
        raise AssertionError(f"Expected invalid timeout {value!r} to fail")


def test_invalid_boolean_fails_clearly(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_DEBUG", "sometimes")
    try:
        Settings.from_env()
    except ConfigurationError as exc:
        assert "NSPIRE_AI_DEBUG" in str(exc)
    else:
        raise AssertionError("Expected invalid boolean to fail")


def test_conversation_limits_and_system_context_are_configurable(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_SYSTEM_CONTEXT", "Be concise.")
    monkeypatch.setenv("NSPIRE_AI_MAX_INPUT_CHARS", "120")
    monkeypatch.setenv("NSPIRE_AI_MAX_CONTEXT_CHARS", "900")
    monkeypatch.setenv("NSPIRE_AI_MAX_CONTEXT_MESSAGES", "8")
    monkeypatch.setenv("NSPIRE_AI_MAX_HISTORY_MESSAGES", "40")
    monkeypatch.setenv("NSPIRE_AI_MAX_HISTORY_CHARS", "12000")
    monkeypatch.setenv("NSPIRE_AI_MAX_CONVERSATIONS", "25")
    settings = Settings.from_env()
    assert settings.system_context == "Be concise."
    assert settings.max_input_chars == 120
    assert settings.max_context_chars == 900
    assert settings.max_context_messages == 8
    assert settings.max_history_messages == 40
    assert settings.max_history_chars == 12000
    assert settings.max_conversations == 25


def test_invalid_conversation_limits_are_rejected(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_MAX_INPUT_CHARS", "0")
    try:
        Settings.from_env()
    except ConfigurationError as exc:
        assert "NSPIRE_AI_MAX_INPUT_CHARS" in str(exc)
    else:
        raise AssertionError("Expected a zero input limit to fail")
    monkeypatch.setenv("NSPIRE_AI_MAX_INPUT_CHARS", "100")
    monkeypatch.setenv("NSPIRE_AI_MAX_HISTORY_MESSAGES", "3")
    try:
        Settings.from_env()
    except ConfigurationError as exc:
        assert "even integer" in str(exc)
    else:
        raise AssertionError("Expected an odd history limit to fail")


def test_system_context_requires_room_for_two_messages(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_SYSTEM_CONTEXT", "Be concise.")
    monkeypatch.setenv("NSPIRE_AI_MAX_CONTEXT_MESSAGES", "1")

    with pytest.raises(ConfigurationError, match="NSPIRE_AI_MAX_CONTEXT_MESSAGES.*at least two"):
        Settings.from_env()


def test_system_context_allows_two_messages(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_SYSTEM_CONTEXT", "Be concise.")
    monkeypatch.setenv("NSPIRE_AI_MAX_CONTEXT_MESSAGES", "2")

    settings = Settings.from_env()

    assert settings.system_context == "Be concise."
    assert settings.max_context_messages == 2


def test_single_message_limit_is_valid_without_system_context(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_MAX_CONTEXT_MESSAGES", "1")

    settings = Settings.from_env()

    assert settings.system_context == ""
    assert settings.max_context_messages == 1
