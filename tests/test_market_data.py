from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from finance_app.market_data import build_quote


def test_build_quote_detects_session_touch_of_three_month_low():
    intraday_index = pd.to_datetime(["2026-08-20 09:30", "2026-08-20 10:00"])
    intraday = pd.DataFrame(
        {"Close": [101.0, 103.0], "Low": [99.0, 102.0]},
        index=intraday_index,
    )
    daily_index = pd.to_datetime(["2026-08-18", "2026-08-19", "2026-08-20"])
    daily = pd.DataFrame(
        {"Close": [105.0, 104.0, 103.0], "Low": [100.0, 101.0, 99.0]},
        index=daily_index,
    )

    quote = build_quote(
        "TEST",
        intraday,
        daily,
        now=datetime(2026, 8, 20, 12, tzinfo=ZoneInfo("America/New_York")),
    )

    assert quote.price == 103.0
    assert quote.previous_close == 104.0
    assert quote.session_low == 99.0
    assert quote.three_month_low == 99.0
    assert quote.at_three_month_low is True
    assert round(quote.day_change_pct, 4) == -0.0096


def test_build_quote_respects_near_low_tolerance():
    index = pd.to_datetime(["2026-08-19"])
    intraday = pd.DataFrame({"Close": [100.7], "Low": [100.4]}, index=index)
    daily = pd.DataFrame({"Close": [101.0], "Low": [100.0]}, index=index)

    quote = build_quote("TEST", intraday, daily, tolerance_pct=0.005)

    assert quote.at_three_month_low is True


def test_build_quote_calculates_six_month_support_and_three_day_volume_spike():
    daily_index = pd.date_range("2026-02-02", periods=140, freq="B")
    daily_lows = [70.0, *([95.0] * 138), 90.0]
    daily_volumes = [100.0] * 137 + [200.0, 200.0, 200.0]
    daily = pd.DataFrame(
        {
            "Close": [110.0] * 140,
            "Low": daily_lows,
            "Volume": daily_volumes,
        },
        index=daily_index,
    )
    intraday = pd.DataFrame(
        {"Close": [112.0], "Low": [109.0]},
        index=pd.to_datetime(["2026-08-21 10:00"]),
    )

    quote = build_quote(
        "TEST",
        intraday,
        daily,
        now=datetime(2026, 8, 21, 12, tzinfo=ZoneInfo("America/New_York")),
    )

    assert quote.six_month_low == 70.0
    assert quote.three_month_low == 90.0
    assert quote.three_day_avg_volume == 200.0
    assert quote.volume_spike_ratio == 2.0
