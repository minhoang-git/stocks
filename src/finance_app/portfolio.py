from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
import re


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.^=-]{1,20}$")


@dataclass(frozen=True)
class PortfolioEntry:
    symbol: str
    reference_price: float | None = None
    trade_date: str | None = None
    purchase_price: float | None = None
    quantity: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_portfolio(path: str) -> list[PortfolioEntry]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Portfolio CSV not found: {csv_path}")

    entries: dict[str, PortfolioEntry] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "Symbol" not in reader.fieldnames:
            raise ValueError("Portfolio CSV must contain a Symbol column.")

        for row_number, row in enumerate(reader, start=2):
            symbol = (row.get("Symbol") or "").strip().upper()
            if not symbol:
                continue
            if not SYMBOL_PATTERN.fullmatch(symbol):
                raise ValueError(f"Invalid ticker symbol on CSV row {row_number}: {symbol!r}")

            entries[symbol] = PortfolioEntry(
                symbol=symbol,
                reference_price=_optional_float(row.get("Current Price")),
                trade_date=(row.get("Trade Date") or "").strip() or None,
                purchase_price=_optional_float(row.get("Purchase Price")),
                quantity=_optional_float(row.get("Quantity")),
            )

    if not entries:
        raise ValueError("Portfolio CSV does not contain any ticker symbols.")
    return list(entries.values())
