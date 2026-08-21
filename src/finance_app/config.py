from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
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


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_path: str
    portfolio_path: str
    refresh_interval_minutes: int
    low_tolerance_pct: float
    web_auth_username: str = ""
    web_auth_password: str = ""
    web_auth_users: str = ""
    scheduler_token: str = ""
    portfolio_csv: str = ""

    @property
    def database_abspath(self) -> str:
        return str(Path(self.database_path).resolve())

    @property
    def portfolio_abspath(self) -> str:
        return str(Path(self.portfolio_path).resolve())

    @property
    def web_auth_configured(self) -> bool:
        return bool(self.web_auth_credentials)

    @property
    def web_auth_credentials(self) -> tuple[tuple[str, str], ...]:
        credentials: list[tuple[str, str]] = []
        if self.web_auth_username and self.web_auth_password:
            credentials.append((self.web_auth_username, self.web_auth_password))
        if self.web_auth_users:
            try:
                users = json.loads(self.web_auth_users)
            except (TypeError, ValueError):
                users = {}
            if isinstance(users, dict):
                credentials.extend(
                    (str(username), str(password))
                    for username, password in users.items()
                    if username and password
                )
        return tuple(dict.fromkeys(credentials))


def get_settings() -> Settings:
    default_database_path = (
        "/tmp/portfolio_monitor.db" if os.getenv("VERCEL") else "./portfolio_monitor.db"
    )
    return Settings(
        secret_key=os.getenv("SECRET_KEY", "change-me"),
        database_path=os.getenv("MONITOR_DATABASE_PATH", default_database_path),
        portfolio_path=os.getenv("PORTFOLIO_PATH", "./portfolio.csv"),
        refresh_interval_minutes=max(1, _get_int("REFRESH_INTERVAL_MINUTES", 5)),
        low_tolerance_pct=max(0.0, _get_float("LOW_TOLERANCE_PCT", 0.0)),
        web_auth_username=os.getenv("WEB_AUTH_USERNAME", "").strip(),
        web_auth_password=os.getenv("WEB_AUTH_PASSWORD", ""),
        web_auth_users=os.getenv("WEB_AUTH_USERS", ""),
        scheduler_token=os.getenv("SCHEDULER_TOKEN", ""),
        portfolio_csv=os.getenv("PORTFOLIO_CSV", ""),
    )
