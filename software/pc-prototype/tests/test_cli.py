from nspire_ai.cli import main


def test_cli_smoke(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["nspire-ai", "test prompt"])
    assert main() == 0
    assert "test prompt" in capsys.readouterr().out
