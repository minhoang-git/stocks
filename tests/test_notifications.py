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


def test_google_chat_posts_to_webhook_without_exposing_it(tmp_path, monkeypatch):
    settings = Settings(
        secret_key="test",
        database_path=str(tmp_path / "monitor.db"),
        portfolio_path=str(tmp_path / "portfolio.csv"),
        refresh_interval_minutes=5,
        alert_cooldown_hours=24,
        low_tolerance_pct=0,
        notification_provider="google_chat",
        mac_messages_enabled=False,
        twilio_account_sid="",
        twilio_auth_token="",
        twilio_from_number="",
        alert_to_number="",
        google_chat_webhook_url="https://chat.googleapis.com/v1/spaces/test/messages?key=secret",
        google_chat_recipient_email="mhoangcong@gmail.com",
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr("finance_app.notifications.requests.post", fake_post)

    notifier = NotificationService(settings)
    result = notifier.send_phone_message("AAPL reached a new low")

    assert notifier.provider == "google_chat"
    assert notifier.provider_label == "Google Chat"
    assert result.ok is True
    assert "chat.googleapis.com" not in result.detail
    assert captured["url"] == settings.google_chat_webhook_url
    assert captured["kwargs"] == {
        "json": {
            "text": "Portfolio Pulse alert for mhoangcong@gmail.com\n"
            "AAPL reached a new low"
        },
        "timeout": 15,
    }
