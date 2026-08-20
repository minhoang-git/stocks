from finance_app.sentiment import score_text


def test_positive_sentiment():
    assert score_text("Arista beats estimates with strong growth") > 0


def test_negative_sentiment():
    assert score_text("Arista faces lawsuit and guidance cut") < 0
