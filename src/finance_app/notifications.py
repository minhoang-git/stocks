from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import ssl
import subprocess
import sys

import requests

from . import db
from .config import Settings


@dataclass(frozen=True)
class NotifyResult:
    ok: bool
    status: str
    detail: str


class NotificationService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db_path = settings.database_abspath

    @property
    def phone_notifications_configured(self) -> bool:
        return self.settings.phone_notifications_configured

    @property
    def notifications_configured(self) -> bool:
        return self.settings.notifications_configured

    @property
    def provider(self) -> str | None:
        return self.settings.active_notification_provider

    @property
    def provider_label(self) -> str:
        return {
            "mac_messages": "macOS Messages",
            "twilio": "Twilio SMS",
            "google_chat": "Google Chat",
            "email": "High-priority email",
        }.get(self.provider, "Not configured")

    def add_in_app(self, title: str, message: str, level: str = "info") -> int:
        return db.insert_notification(self.db_path, level, title, message)

    def _send_twilio(self, body: str) -> NotifyResult:
        if not self.settings.twilio_configured:
            return NotifyResult(False, "not_configured", "Twilio SMS credentials are not configured")

        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{self.settings.twilio_account_sid}/Messages.json"
        )
        try:
            response = requests.post(
                url,
                auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token),
                data={
                    "From": self.settings.twilio_from_number,
                    "To": self.settings.alert_to_number,
                    "Body": body,
                },
                timeout=15,
            )
            response.raise_for_status()
            sid = response.json().get("sid", "accepted")
            return NotifyResult(True, "sent", f"Twilio message {sid}")
        except requests.RequestException as exc:
            return NotifyResult(False, "failed", str(exc))

    def _send_mac_messages(self, body: str) -> NotifyResult:
        if not self.settings.mac_messages_configured:
            return NotifyResult(False, "not_configured", "macOS Messages is not configured")
        if sys.platform != "darwin":
            return NotifyResult(False, "failed", "macOS Messages is available only on a Mac")

        script = """
on run argv
    set recipientAddress to item 1 of argv
    set messageText to item 2 of argv
    tell application "Messages"
        set targetService to first service whose service type = iMessage
        set targetBuddy to buddy recipientAddress of targetService
        send messageText to targetBuddy
    end tell
end run
"""
        try:
            result = subprocess.run(
                ["osascript", "-e", script, self.settings.alert_to_number, body],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return NotifyResult(False, "failed", f"Could not start macOS Messages: {exc}")

        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "Unknown Messages error"
            return NotifyResult(False, "failed", f"macOS Messages could not send: {detail}")
        return NotifyResult(True, "sent", "Message accepted by macOS Messages")

    def _send_google_chat(self, body: str) -> NotifyResult:
        if not self.settings.google_chat_configured:
            return NotifyResult(False, "not_configured", "Google Chat webhook is not configured")

        recipient = self.settings.google_chat_recipient_email
        chat_body = f"Portfolio Pulse alert for {recipient}\n{body}" if recipient else body
        try:
            response = requests.post(
                self.settings.google_chat_webhook_url,
                json={"text": chat_body},
                timeout=15,
            )
            response.raise_for_status()
            detail = f" for {recipient}" if recipient else ""
            return NotifyResult(True, "sent", f"Message accepted by Google Chat{detail}")
        except requests.RequestException as exc:
            return NotifyResult(False, "failed", f"Google Chat could not send: {exc}")

    def _send_email(self, body: str, subject: str) -> NotifyResult:
        if not self.settings.email_configured:
            return NotifyResult(False, "not_configured", "Email delivery is not configured")

        message = EmailMessage()
        message["From"] = self.settings.email_from_address
        message["To"] = self.settings.alert_to_email
        clean_subject = subject.replace("\r", " ").replace("\n", " ").strip()
        message["Subject"] = f"[HIGH PRIORITY] {clean_subject}"
        message["Importance"] = "high"
        message["Priority"] = "urgent"
        message["X-Priority"] = "1"
        message["X-MSMail-Priority"] = "High"
        message.set_content(body)

        try:
            with smtplib.SMTP(
                self.settings.email_smtp_host,
                self.settings.email_smtp_port,
                timeout=15,
            ) as smtp:
                if self.settings.email_smtp_use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                smtp.login(
                    self.settings.email_smtp_username,
                    self.settings.email_smtp_password,
                )
                smtp.send_message(message)
            return NotifyResult(
                True,
                "sent",
                f"High-priority email accepted for {self.settings.alert_to_email}",
            )
        except (OSError, smtplib.SMTPException) as exc:
            return NotifyResult(False, "failed", f"Email could not send: {exc}")

    def send_phone_message(
        self,
        body: str,
        subject: str = "Portfolio Pulse stock alert",
    ) -> NotifyResult:
        if self.provider == "mac_messages":
            return self._send_mac_messages(body)
        if self.provider == "twilio":
            return self._send_twilio(body)
        if self.provider == "google_chat":
            return self._send_google_chat(body)
        if self.provider == "email":
            return self._send_email(body, subject)
        return NotifyResult(False, "not_configured", "No notification provider is configured")

    def send_low_alert(self, *, symbol: str, current_price: float, session_low: float, low: float) -> NotifyResult:
        message = (
            f"3-month low alert: {symbol} traded at ${session_low:,.2f}. "
            f"Rolling 3-month low ${low:,.2f}; current ${current_price:,.2f}."
        )
        self.add_in_app(f"{symbol} reached a 3-month low", message, "low")
        return self.send_phone_message(message, f"{symbol} reached a 3-month low")
