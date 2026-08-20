from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SignalDecision:
    signal: str
    total_score: float
    tech_score: float
    news_score: float
    macro_score: float
    reason: str


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def compute_technical_score(intraday_df: pd.DataFrame, daily_df: pd.DataFrame) -> tuple[float, str]:
    intraday = intraday_df.copy()
    daily = daily_df.copy()

    intraday["ema9"] = intraday["Close"].ewm(span=9).mean()
    intraday["ema21"] = intraday["Close"].ewm(span=21).mean()
    intraday["rsi14"] = compute_rsi(intraday["Close"])

    daily["sma20"] = daily["Close"].rolling(window=20).mean()

    latest = intraday.iloc[-1]
    prev = intraday.iloc[-2] if len(intraday) > 1 else latest
    latest_daily = daily.iloc[-1]

    score = 0.0
    reasons: list[str] = []

    if latest["ema9"] > latest["ema21"]:
        score += 0.35
        reasons.append("EMA9 above EMA21")
    else:
        score -= 0.35
        reasons.append("EMA9 below EMA21")

    rsi = float(latest["rsi14"])
    if rsi >= 55:
        score += 0.15
        reasons.append(f"RSI bullish ({rsi:.1f})")
    elif rsi <= 45:
        score -= 0.15
        reasons.append(f"RSI bearish ({rsi:.1f})")
    else:
        reasons.append(f"RSI neutral ({rsi:.1f})")

    sma20 = float(latest_daily["sma20"]) if pd.notna(latest_daily["sma20"]) else float(latest_daily["Close"])
    if latest_daily["Close"] >= sma20:
        score += 0.2
        reasons.append("Daily close above SMA20")
    else:
        score -= 0.2
        reasons.append("Daily close below SMA20")

    avg_volume = intraday["Volume"].tail(30).mean() if "Volume" in intraday else 0.0
    if avg_volume and latest.get("Volume", 0.0) > avg_volume * 1.3:
        if latest["Close"] > prev["Close"]:
            score += 0.1
            reasons.append("Bullish volume expansion")
        else:
            score -= 0.1
            reasons.append("Bearish volume expansion")

    return float(max(-1.0, min(1.0, score))), "; ".join(reasons)


def compute_macro_score(macro: dict[str, float]) -> tuple[float, str]:
    spy = macro.get("SPY", 0.0)
    qqq = macro.get("QQQ", 0.0)
    vix = macro.get("VIX", 0.0)
    tnx = macro.get("TNX", 0.0)

    score = 0.0
    reasons: list[str] = []

    eq_momentum = (spy + qqq) / 2
    if eq_momentum > 0.003:
        score += 0.25
        reasons.append("Risk-on index move")
    elif eq_momentum < -0.003:
        score -= 0.25
        reasons.append("Risk-off index move")

    if vix > 0.02:
        score -= 0.2
        reasons.append("VIX rising")
    elif vix < -0.02:
        score += 0.1
        reasons.append("VIX easing")

    if tnx > 0.01:
        score -= 0.1
        reasons.append("10Y yield rising")
    elif tnx < -0.01:
        score += 0.1
        reasons.append("10Y yield falling")

    return float(max(-1.0, min(1.0, score))), "; ".join(reasons) if reasons else "Macro neutral"


def choose_take_profit_pct(score: float, min_tp: float, max_tp: float) -> float:
    scaled = min_tp + (max_tp - min_tp) * min(1.0, abs(score))
    return max(min_tp, min(max_tp, scaled))


def decide_signal(
    tech_score: float,
    news_score: float,
    macro_score: float,
    tech_reason: str,
    macro_reason: str,
    top_news_titles: list[str],
    allow_short: bool,
) -> SignalDecision:
    total_score = 0.60 * tech_score + 0.25 * news_score + 0.15 * macro_score

    if total_score >= 0.35:
        signal = "BUY"
    elif total_score <= -0.35 and allow_short:
        signal = "SELL_SHORT"
    else:
        signal = "HOLD"

    reason_parts = [f"Tech: {tech_reason}", f"Macro: {macro_reason}"]
    if top_news_titles:
        reason_parts.append(f"News: {top_news_titles[0]}")

    return SignalDecision(
        signal=signal,
        total_score=float(max(-1.0, min(1.0, total_score))),
        tech_score=tech_score,
        news_score=news_score,
        macro_score=macro_score,
        reason=" | ".join(reason_parts),
    )
