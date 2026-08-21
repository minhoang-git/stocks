from pathlib import Path

from finance_app import db
from finance_app.config import Settings
from finance_app.market_data import MarketQuote
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


def _settings(tmp_path: Path, csv_file: Path) -> Settings:
    return Settings(
        secret_key="test",
        database_path=str(tmp_path / "monitor.db"),
        portfolio_path=str(csv_file),
        refresh_interval_minutes=5,
        low_tolerance_pct=0.0,
    )


def test_monitor_records_low_status(tmp_path: Path):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text("Symbol,Current Price\nTEST,100\n", encoding="utf-8")
    settings = _settings(tmp_path, csv_file)
    db.init_db(settings.database_abspath)
    service = PortfolioMonitorService(
        settings,
        market_data=FakeMarketData(),
    )

    result = service.run_cycle()

    assert result["low_hits"] == 1
    assert db.portfolio_rows(settings.database_abspath)[0]["at_three_month_low"] == 1


def test_database_has_no_notification_tables(tmp_path: Path):
    database_path = str(tmp_path / "monitor.db")
    db.init_db(database_path)

    tables = {
        row["name"]
        for row in db.fetch_all(
            database_path,
            "SELECT name FROM sqlite_schema WHERE type = 'table'",
        )
    }

    assert "notifications" not in tables
    assert "low_alerts" not in tables


def test_market_benchmarks_are_added_and_pinned_in_requested_order(tmp_path: Path):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text("Symbol\nTEST\n", encoding="utf-8")
    settings = _settings(tmp_path, csv_file)
    db.init_db(settings.database_abspath)
    service = PortfolioMonitorService(
        settings,
        market_data=FakeMarketData(),
    )

    symbols = [row["symbol"] for row in service.dashboard_data()["stocks"]]

    assert symbols[:6] == ["^IXIC", "^DJI", "^GSPC", "^VIX", "BTC-USD", "CL=F"]
    assert symbols[6:] == ["TEST"]
