from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from threading import Lock
from typing import Any

from . import db
from .config import Settings
from .market_data import YahooMarketDataClient
from .notifications import NotificationService
from .portfolio import load_portfolio, load_portfolio_text


class PortfolioMonitorService:
    def __init__(
        self,
        settings: Settings,
        *,
        market_data: YahooMarketDataClient | None = None,
        notifier: NotificationService | None = None,
    ):
        self.settings = settings
        self.db_path = settings.database_abspath
        self.market_data = market_data or YahooMarketDataClient()
        self.notifier = notifier or NotificationService(settings)
        self._cycle_lock = Lock()
        self.sync_portfolio()

    def sync_portfolio(self) -> list[dict[str, Any]]:
        portfolio = (
            load_portfolio_text(self.settings.portfolio_csv)
            if self.settings.portfolio_csv
            else load_portfolio(self.settings.portfolio_abspath)
        )
        entries = [entry.as_dict() for entry in portfolio]
        db.sync_watchlist(self.db_path, entries)
        db.seed_reference_quotes(self.db_path, entries)
        return entries

    def _alert_is_due(self, symbol: str, now: datetime) -> bool:
        last = db.latest_low_alert(self.db_path, symbol)
        if not last:
            return True
        try:
            last_at = datetime.fromisoformat(last["created_at"])
        except (TypeError, ValueError):
            return True
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        cooldown = timedelta(hours=self.settings.alert_cooldown_hours)
        return now - last_at >= cooldown

    def run_cycle(self) -> dict[str, Any]:
        if not self._cycle_lock.acquire(blocking=False):
            return {"ok": False, "reason": "A market refresh is already running."}

        try:
            entries = self.sync_portfolio()
            symbols = [entry["symbol"] for entry in entries]
            run_id = db.create_monitor_run(self.db_path, len(symbols))
            now = datetime.now(timezone.utc)

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
                self.notifier.add_in_app("Market data refresh failed", message, "error")
                return {"ok": False, "reason": message}

            new_alerts: list[str] = []
            for symbol, quote in quotes.items():
                db.upsert_quote(self.db_path, quote.as_dict())
                if quote.at_three_month_low and self._alert_is_due(symbol, now):
                    result = self.notifier.send_low_alert(
                        symbol=symbol,
                        current_price=quote.price,
                        session_low=quote.session_low,
                        low=quote.three_month_low,
                    )
                    db.insert_low_alert(
                        self.db_path,
                        symbol=symbol,
                        trigger_price=quote.session_low,
                        three_month_low=quote.three_month_low,
                        sms_status=result.status,
                        sms_detail=result.detail,
                    )
                    new_alerts.append(symbol)

            for symbol, error in errors.items():
                db.mark_quote_error(self.db_path, symbol, error)

            status = "partial" if errors else "complete"
            summary = (
                f"Updated {len(quotes)} of {len(symbols)} symbols; "
                f"{len(new_alerts)} new low alert(s); {len(errors)} error(s)."
            )
            db.finish_monitor_run(
                self.db_path,
                run_id,
                status=status,
                hit_count=len(new_alerts),
                error_count=len(errors),
                summary=summary,
            )
            return {
                "ok": not errors,
                "reason": summary,
                "updated": len(quotes),
                "errors": errors,
                "new_alerts": new_alerts,
            }
        finally:
            self._cycle_lock.release()

    def dashboard_data(self) -> dict[str, Any]:
        rows = db.portfolio_rows(self.db_path)
        tracked_value = 0.0
        cost_basis = 0.0
        for row in rows:
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
            "alerts": db.list_low_alerts(self.db_path, limit=30),
            "notifications": db.list_notifications(self.db_path, limit=40),
            "unread_count": db.unread_notification_count(self.db_path),
            "phone_notifications_configured": self.notifier.phone_notifications_configured,
            "notification_provider": self.notifier.provider,
            "notification_provider_label": self.notifier.provider_label,
            "refresh_interval_minutes": self.settings.refresh_interval_minutes,
            "alert_cooldown_hours": self.settings.alert_cooldown_hours,
            "portfolio_filename": (
                "hosted portfolio" if self.settings.portfolio_csv
                else self.settings.portfolio_abspath.rsplit("/", 1)[-1]
            ),
            "is_cloud_run": bool(os.getenv("K_SERVICE")),
        }

    def mark_notification_read(self, notification_id: int) -> None:
        db.mark_notification_read(self.db_path, notification_id)

    def mark_all_notifications_read(self) -> None:
        db.mark_all_notifications_read(self.db_path)

    def send_test_message(self):
        return self.notifier.send_phone_message(
            f"Portfolio Pulse test: {self.notifier.provider_label} notifications are configured correctly."
        )
