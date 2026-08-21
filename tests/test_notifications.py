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


def test_email_uses_gmail_smtp_and_high_priority_headers(tmp_path, monkeypatch):
    settings = Settings(
        secret_key="test",
        database_path=str(tmp_path / "monitor.db"),
        portfolio_path=str(tmp_path / "portfolio.csv"),
        refresh_interval_minutes=5,
        alert_cooldown_hours=24,
        low_tolerance_pct=0,
        notification_provider="email",
        mac_messages_enabled=False,
        twilio_account_sid="",
        twilio_auth_token="",
        twilio_from_number="",
        alert_to_number="",
        email_smtp_host="smtp.gmail.com",
        email_smtp_port=587,
        email_smtp_use_tls=True,
        email_smtp_username="mhoangcong@gmail.com",
        email_smtp_password="app-password",
        email_from_address="mhoangcong@gmail.com",
        alert_to_email="mhoangcong@gmail.com",
    )
    captured = {}

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            captured.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self, *, context):
            captured["tls"] = context is not None

        def login(self, username, password):
            captured["login"] = (username, password)

        def send_message(self, message):
            captured["message"] = message

    monkeypatch.setattr("finance_app.notifications.smtplib.SMTP", FakeSmtp)

    notifier = NotificationService(settings)
    result = notifier.send_phone_message(
        "AAPL traded at its rolling low.",
        "AAPL reached a 3-month low",
    )

    message = captured["message"]
    assert result.ok is True
    assert notifier.provider_label == "High-priority email"
    assert captured["host"] == "smtp.gmail.com"
    assert captured["port"] == 587
    assert captured["tls"] is True
    assert captured["login"] == ("mhoangcong@gmail.com", "app-password")
    assert message["To"] == "mhoangcong@gmail.com"
    assert message["Subject"] == "[HIGH PRIORITY] AAPL reached a 3-month low"
    assert message["Importance"] == "high"
    assert message["Priority"] == "urgent"
    assert message["X-Priority"] == "1"
    assert message["X-MSMail-Priority"] == "High"
