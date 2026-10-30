from nspire_ai.config import Settings
from nspire_ai.errors import ConfigurationError


def test_defaults_are_safe(monkeypatch):
    for name in ("NSPIRE_AI_PROVIDER", "NSPIRE_AI_LOG_LEVEL", "NSPIRE_AI_DEBUG"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.provider == "mock"
    assert settings.log_level == "INFO"
    assert settings.debug is False


def test_environment_values_are_normalized(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_PROVIDER", " MOCK ")
    monkeypatch.setenv("NSPIRE_AI_LOG_LEVEL", "debug")
    monkeypatch.setenv("NSPIRE_AI_DEBUG", "yes")
    assert Settings.from_env() == Settings(provider="mock", log_level="DEBUG", debug=True)


def test_invalid_boolean_fails_clearly(monkeypatch):
    monkeypatch.setenv("NSPIRE_AI_DEBUG", "sometimes")
    try:
        Settings.from_env()
    except ConfigurationError as exc:
        assert "NSPIRE_AI_DEBUG" in str(exc)
    else:
        raise AssertionError("Expected invalid boolean to fail")
