import pandas as pd

from finance_app.strategy import compute_technical_score


def test_technical_score_bounds():
    intraday = pd.DataFrame(
        {
            "Close": [100 + i * 0.1 for i in range(60)],
            "Open": [100 + i * 0.1 for i in range(60)],
            "Volume": [1000 + i * 3 for i in range(60)],
        }
    )
    daily = pd.DataFrame(
        {
            "Close": [90 + i * 0.4 for i in range(40)],
            "Open": [90 + i * 0.4 for i in range(40)],
            "Volume": [2000 + i * 10 for i in range(40)],
        }
    )

    score, reason = compute_technical_score(intraday, daily)
    assert -1.0 <= score <= 1.0
    assert isinstance(reason, str)
