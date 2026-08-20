from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    reference_price REAL,
    trade_date TEXT,
    purchase_price REAL,
    quantity REAL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quote_snapshots (
    symbol TEXT PRIMARY KEY,
    price REAL,
    previous_close REAL,
    day_change REAL,
    day_change_pct REAL,
    session_low REAL,
    three_month_low REAL,
    low_date TEXT,
    distance_to_low_pct REAL,
    at_three_month_low INTEGER NOT NULL DEFAULT 0,
    market_time TEXT,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'waiting',
    error TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(symbol) REFERENCES watchlist(symbol)
);

CREATE TABLE IF NOT EXISTS low_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trigger_price REAL NOT NULL,
    three_month_low REAL NOT NULL,
    sms_status TEXT NOT NULL,
    sms_detail TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    symbol_count INTEGER NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: str):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def fetch_all(db_path: str, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def fetch_one(db_path: str, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def execute(db_path: str, query: str, params: tuple[Any, ...] = ()) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(query, params)
        return int(cursor.lastrowid)


def sync_watchlist(db_path: str, entries: Iterable[dict[str, Any]]) -> None:
    rows = list(entries)
    if not rows:
        return
    now = utc_now_iso()
    symbols = [row["symbol"] for row in rows]
    with connect(db_path) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO watchlist (
                    symbol, reference_price, trade_date, purchase_price, quantity, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    reference_price = excluded.reference_price,
                    trade_date = excluded.trade_date,
                    purchase_price = excluded.purchase_price,
                    quantity = excluded.quantity,
                    imported_at = excluded.imported_at
                """,
                (
                    row["symbol"], row.get("reference_price"), row.get("trade_date"),
                    row.get("purchase_price"), row.get("quantity"), now,
                ),
            )
        placeholders = ",".join("?" for _ in symbols)
        conn.execute(f"DELETE FROM watchlist WHERE symbol NOT IN ({placeholders})", symbols)


def seed_reference_quotes(db_path: str, entries: Iterable[dict[str, Any]]) -> None:
    now = utc_now_iso()
    with connect(db_path) as conn:
        for row in entries:
            if row.get("reference_price") is None:
                continue
            conn.execute(
                """
                INSERT INTO quote_snapshots (symbol, price, updated_at, status, error)
                VALUES (?, ?, ?, 'csv_snapshot', NULL)
                ON CONFLICT(symbol) DO NOTHING
                """,
                (row["symbol"], row["reference_price"], now),
            )


def upsert_quote(db_path: str, quote: dict[str, Any]) -> None:
    execute(
        db_path,
        """
        INSERT INTO quote_snapshots (
            symbol, price, previous_close, day_change, day_change_pct, session_low,
            three_month_low, low_date, distance_to_low_pct, at_three_month_low,
            market_time, currency, status, error, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live', NULL, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            price = excluded.price,
            previous_close = excluded.previous_close,
            day_change = excluded.day_change,
            day_change_pct = excluded.day_change_pct,
            session_low = excluded.session_low,
            three_month_low = excluded.three_month_low,
            low_date = excluded.low_date,
            distance_to_low_pct = excluded.distance_to_low_pct,
            at_three_month_low = excluded.at_three_month_low,
            market_time = excluded.market_time,
            currency = excluded.currency,
            status = 'live',
            error = NULL,
            updated_at = excluded.updated_at
        """,
        (
            quote["symbol"], quote["price"], quote["previous_close"], quote["day_change"],
            quote["day_change_pct"], quote["session_low"], quote["three_month_low"],
            quote["low_date"], quote["distance_to_low_pct"],
            1 if quote["at_three_month_low"] else 0, quote["market_time"],
            quote.get("currency", "USD"), utc_now_iso(),
        ),
    )


def mark_quote_error(db_path: str, symbol: str, error: str) -> None:
    execute(
        db_path,
        """
        INSERT INTO quote_snapshots (symbol, status, error, updated_at)
        VALUES (?, 'error', ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            status = 'error', error = excluded.error, updated_at = excluded.updated_at
        """,
        (symbol, error[:500], utc_now_iso()),
    )


def portfolio_rows(db_path: str) -> list[dict[str, Any]]:
    return fetch_all(
        db_path,
        """
        SELECT w.*, q.price, q.previous_close, q.day_change, q.day_change_pct,
               q.session_low, q.three_month_low, q.low_date, q.distance_to_low_pct,
               q.at_three_month_low, q.market_time, q.currency, q.status,
               q.error, q.updated_at
        FROM watchlist w
        LEFT JOIN quote_snapshots q ON q.symbol = w.symbol
        ORDER BY q.at_three_month_low DESC,
                 CASE WHEN q.distance_to_low_pct IS NULL THEN 1 ELSE 0 END,
                 q.distance_to_low_pct ASC,
                 w.symbol ASC
        """,
    )


def create_monitor_run(db_path: str, symbol_count: int) -> int:
    return execute(
        db_path,
        "INSERT INTO monitor_runs (started_at, status, symbol_count) VALUES (?, 'running', ?)",
        (utc_now_iso(), symbol_count),
    )


def finish_monitor_run(
    db_path: str,
    run_id: int,
    *,
    status: str,
    hit_count: int,
    error_count: int,
    summary: str,
) -> None:
    execute(
        db_path,
        """
        UPDATE monitor_runs
        SET completed_at = ?, status = ?, hit_count = ?, error_count = ?, summary = ?
        WHERE id = ?
        """,
        (utc_now_iso(), status, hit_count, error_count, summary, run_id),
    )


def latest_monitor_run(db_path: str) -> dict[str, Any] | None:
    return fetch_one(db_path, "SELECT * FROM monitor_runs ORDER BY id DESC LIMIT 1")


def insert_low_alert(
    db_path: str,
    *,
    symbol: str,
    trigger_price: float,
    three_month_low: float,
    sms_status: str,
    sms_detail: str,
) -> int:
    return execute(
        db_path,
        """
        INSERT INTO low_alerts (
            created_at, symbol, trigger_price, three_month_low, sms_status, sms_detail
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (utc_now_iso(), symbol, trigger_price, three_month_low, sms_status, sms_detail[:500]),
    )


def latest_low_alert(db_path: str, symbol: str) -> dict[str, Any] | None:
    return fetch_one(
        db_path,
        "SELECT * FROM low_alerts WHERE symbol = ? ORDER BY id DESC LIMIT 1",
        (symbol,),
    )


def list_low_alerts(db_path: str, limit: int = 30) -> list[dict[str, Any]]:
    return fetch_all(db_path, "SELECT * FROM low_alerts ORDER BY id DESC LIMIT ?", (limit,))


def insert_notification(db_path: str, level: str, title: str, message: str) -> int:
    return execute(
        db_path,
        """
        INSERT INTO notifications (created_at, level, title, message, is_read)
        VALUES (?, ?, ?, ?, 0)
        """,
        (utc_now_iso(), level, title, message),
    )


def list_notifications(db_path: str, limit: int = 40) -> list[dict[str, Any]]:
    return fetch_all(db_path, "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))


def mark_notification_read(db_path: str, notification_id: int) -> None:
    execute(db_path, "UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))


def mark_all_notifications_read(db_path: str) -> None:
    execute(db_path, "UPDATE notifications SET is_read = 1 WHERE is_read = 0")


def unread_notification_count(db_path: str) -> int:
    row = fetch_one(db_path, "SELECT COUNT(*) AS total FROM notifications WHERE is_read = 0")
    return int(row["total"]) if row else 0
