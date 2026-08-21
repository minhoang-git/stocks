import base64

import finance_app.app as app_module
from finance_app.config import Settings


def _authorization(username: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def test_dashboard_accepts_legacy_and_additional_users(tmp_path, monkeypatch):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text("Symbol\nTEST\n", encoding="utf-8")
    settings = Settings(
        secret_key="test",
        database_path=str(tmp_path / "monitor.db"),
        portfolio_path=str(csv_file),
        refresh_interval_minutes=5,
        low_tolerance_pct=0,
        web_auth_username="portfolio",
        web_auth_password="primary-password",
        web_auth_users='{"minhoang":"cisco123"}',
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    app = app_module.create_app(start_scheduler=False)
    client = app.test_client()

    assert client.get("/").status_code == 401
    assert client.get(
        "/", headers=_authorization("portfolio", "primary-password")
    ).status_code == 200
    assert client.get("/", headers=_authorization("minhoang", "cisco123")).status_code == 200
    assert client.get("/", headers=_authorization("minhoang", "wrong")).status_code == 401
    assert client.post(
        "/notifications/test-message",
        headers=_authorization("minhoang", "cisco123"),
    ).status_code == 404
