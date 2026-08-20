from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_path: str
    portfolio_path: str
    refresh_interval_minutes: int
    alert_cooldown_hours: float
    low_tolerance_pct: float
    notification_provider: str
    mac_messages_enabled: bool
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    alert_to_number: str

    @property
    def database_abspath(self) -> str:
        return str(Path(self.database_path).resolve())

    @property
    def portfolio_abspath(self) -> str:
        return str(Path(self.portfolio_path).resolve())

    @property
    def twilio_configured(self) -> bool:
        return all(
            (
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.twilio_from_number,
                self.alert_to_number,
            )
        )

    @property
    def mac_messages_configured(self) -> bool:
        return self.mac_messages_enabled and bool(self.alert_to_number)

    @property
    def active_notification_provider(self) -> str | None:
        if self.notification_provider == "mac_messages":
            return "mac_messages" if self.mac_messages_configured else None
        if self.notification_provider == "twilio":
            return "twilio" if self.twilio_configured else None
        if self.twilio_configured:
            return "twilio"
        if self.mac_messages_configured:
            return "mac_messages"
        return None

    @property
    def phone_notifications_configured(self) -> bool:
        return self.active_notification_provider is not None


def get_settings() -> Settings:
    return Settings(
        secret_key=os.getenv("SECRET_KEY", "change-me"),
        database_path=os.getenv("MONITOR_DATABASE_PATH", "./portfolio_monitor.db"),
        portfolio_path=os.getenv("PORTFOLIO_PATH", "./portfolio.csv"),
        refresh_interval_minutes=max(1, _get_int("REFRESH_INTERVAL_MINUTES", 5)),
        alert_cooldown_hours=max(0.0, _get_float("ALERT_COOLDOWN_HOURS", 24.0)),
        low_tolerance_pct=max(0.0, _get_float("LOW_TOLERANCE_PCT", 0.0)),
        notification_provider=os.getenv("NOTIFICATION_PROVIDER", "auto").strip().lower(),
        mac_messages_enabled=_get_bool("MAC_MESSAGES_ENABLED", False),
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
        twilio_from_number=os.getenv("TWILIO_FROM_NUMBER", "").strip(),
        alert_to_number=os.getenv("ALERT_TO_NUMBER", "").strip(),
    )
