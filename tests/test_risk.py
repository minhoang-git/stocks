from finance_app.risk import compute_position_size, evaluate_risk


def test_position_size_positive():
    qty = compute_position_size(equity=10000, entry_price=100, stop_loss_pct=0.05)
    assert qty > 0


def test_risk_gate_daily_limit():
    result = evaluate_risk(
        day_pnl_pct=-0.03,
        drawdown_pct=0.01,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
    )
    assert result.allow_trade is False
