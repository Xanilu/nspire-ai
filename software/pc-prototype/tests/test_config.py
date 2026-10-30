from nspire_ai.config import Settings
from nspire_ai.errors import ConfigurationError


def test_defaults_are_safe(monkeypatch):
    for name in ("NSPIRE_AI_PROVIDER", "NSPIRE_AI_LOG_LEVEL", "NSPIRE_AI_DEBUG"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.provider == "mock"
    assert settings.log_level == "INFO"
    assert settings.debug is False
    assert settings.model == "gpt-4.1-mini"
    assert settings.request_timeout == 30.0


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
