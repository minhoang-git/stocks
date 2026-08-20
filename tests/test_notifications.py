from types import SimpleNamespace

from finance_app.config import Settings
from finance_app.notifications import NotificationService


def test_mac_messages_uses_argument_list_without_shell_interpolation(tmp_path, monkeypatch):
    settings = Settings(
        secret_key="test",
        database_path=str(tmp_path / "monitor.db"),
        portfolio_path=str(tmp_path / "portfolio.csv"),
        refresh_interval_minutes=5,
        alert_cooldown_hours=24,
        low_tolerance_pct=0,
        notification_provider="mac_messages",
        mac_messages_enabled=True,
        twilio_account_sid="",
        twilio_auth_token="",
        twilio_from_number="",
        alert_to_number="+14155550123",
    )
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("finance_app.notifications.sys.platform", "darwin")
    monkeypatch.setattr("finance_app.notifications.subprocess.run", fake_run)

    result = NotificationService(settings).send_phone_message("test message")

    assert result.ok is True
    assert captured["args"][0] == "osascript"
    assert captured["args"][-2:] == ["+14155550123", "test message"]
    assert "shell" not in captured["kwargs"]
