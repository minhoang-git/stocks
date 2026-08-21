from dataclasses import replace
from pathlib import Path

from finance_app import db
from finance_app.config import Settings
from finance_app.market_data import MarketQuote
from finance_app.notifications import NotifyResult
from finance_app.service import PortfolioMonitorService


class FakeMarketData:
    def fetch_quotes(self, symbols, *, tolerance_pct=0.0):
        symbols = list(symbols)
        symbol = "TEST" if "TEST" in symbols else symbols[0]
        return {
            symbol: MarketQuote(
                symbol=symbol,
                price=101.0,
                previous_close=102.0,
                day_change=-1.0,
                day_change_pct=-1 / 102,
                session_low=99.0,
                three_month_low=99.0,
                low_date="2026-08-20",
                distance_to_low_pct=2 / 99,
                at_three_month_low=True,
                market_time="2026-08-20T16:00:00-04:00",
            )
        }, {}


class FakeNotifier:
    phone_notifications_configured = True
    provider = "mac_messages"
    provider_label = "macOS Messages"

    def __init__(self):
        self.sent = []

    def send_low_alert(self, **payload):
        self.sent.append(payload)
        return NotifyResult(True, "sent", "test-message")

    def add_in_app(self, *args, **kwargs):
        return 1

    def send_phone_message(self, body):
        return NotifyResult(True, "sent", "test-message")


def _settings(tmp_path: Path, csv_file: Path) -> Settings:
    return Settings(
        secret_key="test",
        database_path=str(tmp_path / "monitor.db"),
        portfolio_path=str(csv_file),
        refresh_interval_minutes=5,
        alert_cooldown_hours=24,
        low_tolerance_pct=0.0,
        notification_provider="mac_messages",
        mac_messages_enabled=True,
        twilio_account_sid="ACtest",
        twilio_auth_token="token",
        twilio_from_number="+14155550100",
        alert_to_number="+14155550101",
    )


def test_monitor_sends_one_low_alert_within_cooldown(tmp_path: Path):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text("Symbol,Current Price\nTEST,100\n", encoding="utf-8")
    settings = _settings(tmp_path, csv_file)
    db.init_db(settings.database_abspath)
    notifier = FakeNotifier()
    service = PortfolioMonitorService(
        settings,
        market_data=FakeMarketData(),
        notifier=notifier,
    )

    first = service.run_cycle()
    second = service.run_cycle()

    assert first["new_alerts"] == ["TEST"]
    assert second["new_alerts"] == []
    assert len(notifier.sent) == 1
    assert db.portfolio_rows(settings.database_abspath)[0]["at_three_month_low"] == 1


def test_zero_cooldown_allows_a_new_alert(tmp_path: Path):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text("Symbol,Current Price\nTEST,100\n", encoding="utf-8")
    settings = replace(_settings(tmp_path, csv_file), alert_cooldown_hours=0)
    db.init_db(settings.database_abspath)
    notifier = FakeNotifier()
    service = PortfolioMonitorService(settings, market_data=FakeMarketData(), notifier=notifier)

    service.run_cycle()
    service.run_cycle()

    assert len(notifier.sent) == 2


def test_market_benchmarks_are_added_and_pinned_in_requested_order(tmp_path: Path):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text("Symbol\nTEST\n", encoding="utf-8")
    settings = _settings(tmp_path, csv_file)
    db.init_db(settings.database_abspath)
    service = PortfolioMonitorService(
        settings,
        market_data=FakeMarketData(),
        notifier=FakeNotifier(),
    )

    symbols = [row["symbol"] for row in service.dashboard_data()["stocks"]]

    assert symbols[:6] == ["^IXIC", "^DJI", "^GSPC", "^VIX", "BTC-USD", "CL=F"]
    assert symbols[6:] == ["TEST"]
