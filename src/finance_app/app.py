from __future__ import annotations

import atexit
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, jsonify, redirect, render_template, url_for

from .config import get_settings
from .db import init_db
from .service import PortfolioMonitorService


def create_app(*, start_scheduler: bool = True) -> Flask:
    settings = get_settings()
    project_root = Path(__file__).resolve().parents[2]
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config["SECRET_KEY"] = settings.secret_key

    init_db(settings.database_abspath)
    service = PortfolioMonitorService(settings)
    app.extensions["portfolio_monitor"] = service

    scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    scheduler.add_job(
        service.run_cycle,
        trigger="interval",
        minutes=settings.refresh_interval_minutes,
        next_run_time=datetime.now(timezone.utc),
        id="portfolio-refresh",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    if start_scheduler:
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False))

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", data=service.dashboard_data())

    @app.post("/refresh")
    def refresh_now():
        result = service.run_cycle()
        flash(result["reason"], "success" if result.get("ok") else "warning")
        return redirect(url_for("dashboard"))

    @app.post("/notifications/test-message")
    @app.post("/notifications/test-sms")
    def test_message():
        result = service.send_test_message()
        flash(result.detail, "success" if result.ok else "warning")
        return redirect(url_for("dashboard"))

    @app.post("/notifications/<int:notification_id>/read")
    def mark_notification_read(notification_id: int):
        service.mark_notification_read(notification_id)
        return redirect(url_for("dashboard"))

    @app.post("/notifications/read-all")
    def mark_all_notifications_read():
        service.mark_all_notifications_read()
        return redirect(url_for("dashboard"))

    @app.get("/api/state")
    def api_state():
        return jsonify(service.dashboard_data())

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "stocks": service.dashboard_data()["stock_count"]})

    return app
