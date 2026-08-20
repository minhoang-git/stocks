from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

POSITIVE_WORDS = {
    "beat",
    "beats",
    "growth",
    "strong",
    "surge",
    "rally",
    "upgrade",
    "expansion",
    "profit",
    "record",
    "bullish",
    "outperform",
    "upside",
    "guidance raise",
    "partnership",
    "wins",
    "ai demand",
}

NEGATIVE_WORDS = {
    "miss",
    "misses",
    "downgrade",
    "weak",
    "drop",
    "selloff",
    "lawsuit",
    "investigation",
    "bearish",
    "recession",
    "layoff",
    "warning",
    "guidance cut",
    "tariff",
    "risk",
    "antitrust",
    "slowdown",
}

TOKEN_PATTERN = re.compile(r"[a-zA-Z]{2,}")


def score_text(text: str) -> float:
    if not text:
        return 0.0

    normalized = text.lower().strip()
    tokens = TOKEN_PATTERN.findall(normalized)
    if not tokens:
        return 0.0

    pos = sum(1 for token in tokens if token in POSITIVE_WORDS)
    neg = sum(1 for token in tokens if token in NEGATIVE_WORDS)

    for phrase in POSITIVE_WORDS:
        if " " in phrase and phrase in normalized:
            pos += 2
    for phrase in NEGATIVE_WORDS:
        if " " in phrase and phrase in normalized:
            neg += 2

    total = pos + neg
    if total == 0:
        return 0.0

    score = (pos - neg) / total
    return max(-1.0, min(1.0, score))


def aggregate_news_score(items: list[dict]) -> tuple[float, list[str]]:
    if not items:
        return 0.0, []

    now = datetime.now(timezone.utc)
    weighted_scores: list[float] = []
    weighted_sum = 0.0
    top_titles: list[str] = []

    for item in items:
        score = float(item.get("sentiment", 0.0))
        published = item.get("published_at")
        weight = 1.0

        if published:
            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if now - published_dt > timedelta(hours=24):
                    weight = 0.6
                if now - published_dt > timedelta(days=3):
                    weight = 0.35
            except ValueError:
                weight = 0.8

        weighted_scores.append(weight)
        weighted_sum += score * weight

    denom = sum(weighted_scores)
    aggregate = weighted_sum / denom if denom else 0.0

    sorted_items = sorted(items, key=lambda x: abs(float(x.get("sentiment", 0.0))), reverse=True)
    for item in sorted_items[:3]:
        title = item.get("title")
        if title:
            top_titles.append(title)

    return max(-1.0, min(1.0, aggregate)), top_titles
