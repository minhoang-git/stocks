from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskGateResult:
    allow_trade: bool
    reason: str


def compute_position_size(
    equity: float,
    entry_price: float,
    stop_loss_pct: float,
    risk_per_trade_pct: float = 0.005,
) -> int:
    if equity <= 0 or entry_price <= 0 or stop_loss_pct <= 0:
        return 0

    risk_budget = equity * risk_per_trade_pct
    stop_distance = entry_price * stop_loss_pct
    if stop_distance <= 0:
        return 0

    qty = int(risk_budget / stop_distance)
    max_qty_by_notional = int(equity / entry_price)
    return max(0, min(qty, max_qty_by_notional))


def evaluate_risk(
    day_pnl_pct: float,
    drawdown_pct: float,
    max_daily_loss_pct: float,
    max_drawdown_pct: float,
) -> RiskGateResult:
    if day_pnl_pct <= -abs(max_daily_loss_pct):
        return RiskGateResult(
            allow_trade=False,
            reason=f"Daily loss limit hit ({day_pnl_pct:.2%}).",
        )
    if drawdown_pct >= abs(max_drawdown_pct):
        return RiskGateResult(
            allow_trade=False,
            reason=f"Max drawdown limit hit ({drawdown_pct:.2%}).",
        )
    return RiskGateResult(allow_trade=True, reason="Risk checks passed.")
