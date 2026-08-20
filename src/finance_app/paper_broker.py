from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db

EASTERN_TZ = ZoneInfo("America/New_York")


@dataclass
class AccountSnapshot:
    equity: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float
    day_pnl_pct: float
    drawdown_pct: float


class PaperBroker:
    def __init__(self, db_path: str, symbol: str, starting_equity: float):
        self.db_path = db_path
        self.symbol = symbol
        self.starting_equity = starting_equity
        self._bootstrap()

    def _bootstrap(self) -> None:
        if db.get_state(self.db_path, "realized_pnl") is None:
            db.set_state(self.db_path, "realized_pnl", 0.0)
        if db.get_state(self.db_path, "peak_equity") is None:
            db.set_state(self.db_path, "peak_equity", self.starting_equity)

    def _get_realized(self) -> float:
        return float(db.get_state(self.db_path, "realized_pnl", 0.0))

    def _set_realized(self, value: float) -> None:
        db.set_state(self.db_path, "realized_pnl", value)

    def _get_peak(self) -> float:
        return float(db.get_state(self.db_path, "peak_equity", self.starting_equity))

    def _set_peak(self, value: float) -> None:
        db.set_state(self.db_path, "peak_equity", value)

    def _today_key(self) -> str:
        today = datetime.now(EASTERN_TZ).date().isoformat()
        return f"day_start_equity::{today}"

    def get_open_position(self) -> dict | None:
        return db.get_open_order(self.db_path, self.symbol)

    def _calc_unrealized(self, current_price: float) -> float:
        position = self.get_open_position()
        if not position:
            return 0.0

        entry = float(position["entry_price"])
        qty = int(position["qty"])
        side = position["side"]

        if side == "LONG":
            return (current_price - entry) * qty
        return (entry - current_price) * qty

    def snapshot(self, current_price: float) -> AccountSnapshot:
        realized = self._get_realized()
        unrealized = self._calc_unrealized(current_price)
        cash = self.starting_equity + realized
        equity = cash + unrealized

        day_start_key = self._today_key()
        day_start_equity = db.get_state(self.db_path, day_start_key)
        if day_start_equity is None:
            db.set_state(self.db_path, day_start_key, equity)
            day_start_equity = equity

        peak = self._get_peak()
        if equity > peak:
            peak = equity
            self._set_peak(peak)

        day_pnl_pct = 0.0 if day_start_equity == 0 else (equity - day_start_equity) / day_start_equity
        drawdown_pct = 0.0 if peak == 0 else max(0.0, (peak - equity) / peak)

        db.save_snapshot(
            self.db_path,
            equity=equity,
            cash=cash,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            drawdown_pct=drawdown_pct,
            day_pnl_pct=day_pnl_pct,
        )

        return AccountSnapshot(
            equity=equity,
            cash=cash,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            day_pnl_pct=day_pnl_pct,
            drawdown_pct=drawdown_pct,
        )

    def open_position(
        self,
        side: str,
        qty: int,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        alert_id: int | None,
    ) -> int:
        if qty <= 0:
            raise ValueError("Quantity must be positive.")
        if self.get_open_position():
            raise RuntimeError("An open position already exists for this symbol.")

        return db.insert_order(
            self.db_path,
            {
                "alert_id": alert_id,
                "symbol": self.symbol,
                "side": side,
                "qty": qty,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "take_profit_price": take_profit_price,
            },
        )

    def close_position(self, order_id: int, close_price: float, close_reason: str) -> float:
        order = db.fetch_one(self.db_path, "SELECT * FROM orders WHERE id = ?", (order_id,))
        if not order or order["status"] != "OPEN":
            raise RuntimeError("Order is not open.")

        qty = int(order["qty"])
        entry = float(order["entry_price"])
        side = order["side"]

        if side == "LONG":
            pnl = (close_price - entry) * qty
        else:
            pnl = (entry - close_price) * qty

        db.close_order(self.db_path, order_id, close_price, pnl, close_reason)

        realized = self._get_realized() + pnl
        self._set_realized(realized)
        return pnl

    def enforce_exit_rules(self, current_price: float) -> tuple[bool, str]:
        position = self.get_open_position()
        if not position:
            return False, "No open position"

        side = position["side"]
        stop = float(position["stop_price"])
        target = float(position["take_profit_price"])

        if side == "LONG":
            if current_price <= stop:
                self.close_position(position["id"], current_price, "Stop loss hit")
                return True, "Closed long on stop"
            if current_price >= target:
                self.close_position(position["id"], current_price, "Take profit hit")
                return True, "Closed long on target"
        else:
            if current_price >= stop:
                self.close_position(position["id"], current_price, "Stop loss hit")
                return True, "Closed short on stop"
            if current_price <= target:
                self.close_position(position["id"], current_price, "Take profit hit")
                return True, "Closed short on target"

        return False, "Position remains open"

    def flatten(self, current_price: float, reason: str = "End of day close") -> tuple[bool, str]:
        position = self.get_open_position()
        if not position:
            return False, "No open position"
        self.close_position(int(position["id"]), current_price, reason)
        return True, "Position flattened"
