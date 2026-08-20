from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


EASTERN_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    price: float
    previous_close: float
    day_change: float
    day_change_pct: float
    session_low: float
    three_month_low: float
    low_date: str
    distance_to_low_pct: float
    at_three_month_low: bool
    market_time: str
    currency: str = "USD"

    def as_dict(self) -> dict:
        return asdict(self)


def _ticker_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    if isinstance(frame.columns, pd.MultiIndex):
        first_level = set(frame.columns.get_level_values(0))
        second_level = set(frame.columns.get_level_values(1))
        if symbol in first_level:
            return frame[symbol].copy()
        if symbol in second_level:
            return frame.xs(symbol, axis=1, level=1).copy()
    return frame.copy()


def _last_valid(series: pd.Series) -> float:
    values = series.dropna()
    if values.empty:
        raise ValueError("Price series is empty")
    return float(values.iloc[-1])


def build_quote(
    symbol: str,
    intraday: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    tolerance_pct: float = 0.0,
    now: datetime | None = None,
) -> MarketQuote:
    intraday = intraday.dropna(how="all")
    daily = daily.dropna(how="all")
    if intraday.empty or "Close" not in intraday:
        raise ValueError("No intraday close price returned")
    if daily.empty or "Low" not in daily or "Close" not in daily:
        raise ValueError("No three-month daily history returned")

    price = _last_valid(intraday["Close"])
    session_low = float(intraday["Low"].dropna().min()) if "Low" in intraday else price

    lows = daily["Low"].dropna()
    rolling_low = float(lows.min())
    low_index = lows.idxmin()
    low_date = low_index.date().isoformat() if hasattr(low_index, "date") else str(low_index)

    closes = daily["Close"].dropna()
    today = (now or datetime.now(EASTERN_TZ)).astimezone(EASTERN_TZ).date()
    last_index = closes.index[-1]
    last_date = last_index.date() if hasattr(last_index, "date") else None
    if last_date == today and len(closes) >= 2:
        previous_close = float(closes.iloc[-2])
    else:
        previous_close = float(closes.iloc[-1])

    day_change = price - previous_close
    day_change_pct = day_change / previous_close if previous_close else 0.0
    distance_to_low_pct = (price - rolling_low) / rolling_low if rolling_low else 0.0
    at_low = session_low <= rolling_low * (1.0 + tolerance_pct)

    market_index = intraday["Close"].dropna().index[-1]
    if hasattr(market_index, "isoformat"):
        market_time = market_index.isoformat()
    else:
        market_time = str(market_index)

    return MarketQuote(
        symbol=symbol,
        price=price,
        previous_close=previous_close,
        day_change=day_change,
        day_change_pct=day_change_pct,
        session_low=session_low,
        three_month_low=rolling_low,
        low_date=low_date,
        distance_to_low_pct=distance_to_low_pct,
        at_three_month_low=at_low,
        market_time=market_time,
    )


class YahooMarketDataClient:
    def fetch_quotes(
        self,
        symbols: Iterable[str],
        *,
        tolerance_pct: float = 0.0,
    ) -> tuple[dict[str, MarketQuote], dict[str, str]]:
        tickers = sorted(set(symbols))
        if not tickers:
            return {}, {}

        intraday = yf.download(
            tickers=tickers,
            period="1d",
            interval="1m",
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker",
            timeout=25,
        )
        daily = yf.download(
            tickers=tickers,
            period="3mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker",
            timeout=25,
        )

        quotes: dict[str, MarketQuote] = {}
        errors: dict[str, str] = {}
        for symbol in tickers:
            try:
                quotes[symbol] = build_quote(
                    symbol,
                    _ticker_frame(intraday, symbol),
                    _ticker_frame(daily, symbol),
                    tolerance_pct=tolerance_pct,
                )
            except Exception as exc:  # noqa: BLE001
                errors[symbol] = str(exc)
        return quotes, errors
