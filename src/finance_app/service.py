from __future__ import annotations

from threading import Lock
from typing import Any

from . import db
from .config import Settings
from .market_data import YahooMarketDataClient
from .portfolio import load_portfolio, load_portfolio_text


MARKET_BENCHMARKS = (
    ("^IXIC", "Nasdaq Composite"),
    ("^DJI", "Dow 30"),
    ("^GSPC", "S&P 500"),
    ("^VIX", "VIX"),
    ("BTC-USD", "Bitcoin"),
    ("CL=F", "Crude Oil WTI"),
)
BENCHMARK_LABELS = dict(MARKET_BENCHMARKS)


class PortfolioMonitorService:
    def __init__(
        self,
        settings: Settings,
        *,
        market_data: YahooMarketDataClient | None = None,
    ):
        self.settings = settings
        self.db_path = settings.database_abspath
        self.market_data = market_data or YahooMarketDataClient()
        self._cycle_lock = Lock()
        self.sync_portfolio()

    def sync_portfolio(self) -> list[dict[str, Any]]:
        portfolio = (
            load_portfolio_text(self.settings.portfolio_csv)
            if self.settings.portfolio_csv
            else load_portfolio(self.settings.portfolio_abspath)
        )
        portfolio_entries = [entry.as_dict() for entry in portfolio]
        benchmark_entries = [
            {
                "symbol": symbol,
                "reference_price": None,
                "trade_date": None,
                "purchase_price": None,
                "quantity": None,
            }
            for symbol, _ in MARKET_BENCHMARKS
        ]
        benchmark_symbols = set(BENCHMARK_LABELS)
        entries = benchmark_entries + [
            entry for entry in portfolio_entries if entry["symbol"] not in benchmark_symbols
        ]
        db.sync_watchlist(self.db_path, entries)
        db.seed_reference_quotes(self.db_path, entries)
        return entries

    def run_cycle(self) -> dict[str, Any]:
        if not self._cycle_lock.acquire(blocking=False):
            return {"ok": False, "reason": "A market refresh is already running."}

        try:
            entries = self.sync_portfolio()
            symbols = [entry["symbol"] for entry in entries]
            run_id = db.create_monitor_run(self.db_path, len(symbols))

            try:
                quotes, errors = self.market_data.fetch_quotes(
                    symbols,
                    tolerance_pct=self.settings.low_tolerance_pct,
                )
            except Exception as exc:  # noqa: BLE001
                message = f"Yahoo Finance refresh failed: {exc}"
                for symbol in symbols:
                    db.mark_quote_error(self.db_path, symbol, message)
                db.finish_monitor_run(
                    self.db_path,
                    run_id,
                    status="failed",
                    hit_count=0,
                    error_count=len(symbols),
                    summary=message,
                )
                return {"ok": False, "reason": message}

            low_hits = 0
            for symbol, quote in quotes.items():
                db.upsert_quote(self.db_path, quote.as_dict())
                low_hits += int(quote.at_three_month_low)

            for symbol, error in errors.items():
                db.mark_quote_error(self.db_path, symbol, error)

            status = "partial" if errors else "complete"
            summary = (
                f"Updated {len(quotes)} of {len(symbols)} symbols; "
                f"{low_hits} at 3-month low; {len(errors)} error(s)."
            )
            db.finish_monitor_run(
                self.db_path,
                run_id,
                status=status,
                hit_count=low_hits,
                error_count=len(errors),
                summary=summary,
            )
            return {
                "ok": not errors,
                "reason": summary,
                "updated": len(quotes),
                "errors": errors,
                "low_hits": low_hits,
            }
        finally:
            self._cycle_lock.release()

    def dashboard_data(self) -> dict[str, Any]:
        rows = db.portfolio_rows(self.db_path)
        tracked_value = 0.0
        cost_basis = 0.0
        for row in rows:
            row["is_benchmark"] = row["symbol"] in BENCHMARK_LABELS
            row["display_name"] = BENCHMARK_LABELS.get(row["symbol"], row["symbol"])
            price = row.get("price")
            quantity = row.get("quantity")
            purchase_price = row.get("purchase_price")
            row["holding_value"] = price * quantity if price is not None and quantity else None
            row["unrealized_pnl"] = (
                (price - purchase_price) * quantity
                if price is not None and purchase_price is not None and quantity
                else None
            )
            if row["holding_value"] is not None:
                tracked_value += row["holding_value"]
            if purchase_price is not None and quantity:
                cost_basis += purchase_price * quantity

        benchmark_order = {symbol: index for index, (symbol, _) in enumerate(MARKET_BENCHMARKS)}
        rows.sort(
            key=lambda row: (
                0 if row["is_benchmark"] else 1,
                benchmark_order.get(row["symbol"], 0),
            )
        )

        latest_run = db.latest_monitor_run(self.db_path)
        return {
            "stocks": rows,
            "stock_count": len(rows),
            "low_count": sum(1 for row in rows if row.get("at_three_month_low")),
            "error_count": sum(1 for row in rows if row.get("status") == "error"),
            "tracked_value": tracked_value,
            "cost_basis": cost_basis,
            "tracked_pnl": tracked_value - cost_basis if cost_basis else None,
            "latest_run": latest_run,
            "refresh_interval_minutes": self.settings.refresh_interval_minutes,
            "portfolio_filename": (
                "hosted portfolio" if self.settings.portfolio_csv
                else self.settings.portfolio_abspath.rsplit("/", 1)[-1]
            ),
        }
