"""AI FinOps budget & token-quota guard preventing runaway LLM API spend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    spent_jpy: float
    remaining_jpy: float
    reason: str


class TokenQuotaGuard:
    """Enforces hard monthly JPY budget limits per department/project."""

    def __init__(self, ledger_path: Path | str, monthly_limit_jpy: float) -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.monthly_limit_jpy = monthly_limit_jpy
        if not self.ledger_path.exists():
            self.ledger_path.write_text(json.dumps({"spent_jpy": 0.0}), encoding="utf-8")

    def _read_spent(self) -> float:
        return float(json.loads(self.ledger_path.read_text(encoding="utf-8"))["spent_jpy"])

    def _write_spent(self, val: float) -> None:
        self.ledger_path.write_text(json.dumps({"spent_jpy": round(val, 4)}), encoding="utf-8")

    def check_and_consume(self, estimated_cost_jpy: float) -> QuotaDecision:
        if estimated_cost_jpy < 0:
            raise ValueError("estimated_cost_jpy must be non-negative")
        current = self._read_spent()
        if current + estimated_cost_jpy > self.monthly_limit_jpy:
            return QuotaDecision(
                allowed=False,
                spent_jpy=current,
                remaining_jpy=round(max(0.0, self.monthly_limit_jpy - current), 4),
                reason="MONTHLY_BUDGET_EXCEEDED",
            )
        new_spent = current + estimated_cost_jpy
        self._write_spent(new_spent)
        return QuotaDecision(
            allowed=True,
            spent_jpy=round(new_spent, 4),
            remaining_jpy=round(self.monthly_limit_jpy - new_spent, 4),
            reason="OK",
        )
