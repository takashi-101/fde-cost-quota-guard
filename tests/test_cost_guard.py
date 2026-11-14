import json
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cost_guard import QuotaDecision, TokenQuotaGuard


class TestCostGuard(unittest.TestCase):
    def test_blocks_when_monthly_budget_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            guard = TokenQuotaGuard(Path(tmp) / "ledger.json", monthly_limit_jpy=100.0)
            d1 = guard.check_and_consume(70.0)
            d2 = guard.check_and_consume(40.0)
            self.assertTrue(d1.allowed)
            self.assertFalse(d2.allowed)
            self.assertEqual(d2.reason, "MONTHLY_BUDGET_EXCEEDED")


class _LedgerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = Path(self._tmp.name) / "ledger.json"

    def read_ledger(self) -> dict:
        return json.loads(self.ledger.read_text(encoding="utf-8"))


# 正常系
class TestNormal(_LedgerTestCase):
    def test_constructor_creates_ledger_with_zero(self) -> None:
        TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        self.assertEqual(self.read_ledger(), {"spent_jpy": 0.0})

    def test_constructor_creates_missing_parent_directories(self) -> None:
        nested = Path(self._tmp.name) / "dept-a" / "2026-11" / "ledger.json"
        TokenQuotaGuard(nested, monthly_limit_jpy=100.0)
        self.assertTrue(nested.exists())

    def test_ledger_path_can_be_str(self) -> None:
        guard = TokenQuotaGuard(str(self.ledger), monthly_limit_jpy=100.0)
        self.assertTrue(guard.check_and_consume(10.0).allowed)
        self.assertEqual(self.read_ledger(), {"spent_jpy": 10.0})

    def test_allowed_decision_and_ledger_update(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        d = guard.check_and_consume(30.0)
        self.assertEqual(
            d, QuotaDecision(allowed=True, spent_jpy=30.0, remaining_jpy=70.0, reason="OK")
        )
        self.assertEqual(self.read_ledger(), {"spent_jpy": 30.0})

    def test_spending_accumulates(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        guard.check_and_consume(30.0)
        d = guard.check_and_consume(25.5)
        self.assertEqual((d.spent_jpy, d.remaining_jpy), (55.5, 44.5))

    def test_existing_ledger_is_kept_by_new_instance(self) -> None:
        TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0).check_and_consume(60.0)
        guard2 = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        self.assertEqual(self.read_ledger(), {"spent_jpy": 60.0})
        self.assertFalse(guard2.check_and_consume(50.0).allowed)


# 境界値
class TestBoundary(_LedgerTestCase):
    def test_reaching_limit_exactly_is_allowed(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        d = guard.check_and_consume(100.0)
        self.assertTrue(d.allowed)
        self.assertEqual((d.spent_jpy, d.remaining_jpy), (100.0, 0.0))

    def test_slightly_over_limit_is_denied_and_ledger_unchanged(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        guard.check_and_consume(99.0)
        d = guard.check_and_consume(1.0001)
        self.assertEqual(
            d,
            QuotaDecision(
                allowed=False, spent_jpy=99.0, remaining_jpy=1.0, reason="MONTHLY_BUDGET_EXCEEDED"
            ),
        )
        self.assertEqual(self.read_ledger(), {"spent_jpy": 99.0})

    def test_zero_cost_is_allowed_at_limit(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        guard.check_and_consume(100.0)
        self.assertTrue(guard.check_and_consume(0).allowed)

    def test_zero_limit_allows_only_zero_cost(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=0)
        self.assertTrue(guard.check_and_consume(0).allowed)
        self.assertFalse(guard.check_and_consume(0.0001).allowed)

    def test_remaining_is_clamped_to_zero_when_ledger_exceeds_new_limit(self) -> None:
        TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0).check_and_consume(80.0)
        lowered = TokenQuotaGuard(self.ledger, monthly_limit_jpy=50.0)
        d = lowered.check_and_consume(0)
        self.assertFalse(d.allowed)
        self.assertEqual((d.spent_jpy, d.remaining_jpy), (80.0, 0.0))

    def test_ledger_is_rounded_to_four_decimals(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        guard.check_and_consume(0.1)
        d = guard.check_and_consume(0.2)
        self.assertEqual(d.spent_jpy, 0.3)
        self.assertEqual(self.read_ledger(), {"spent_jpy": 0.3})

    def test_cost_below_rounding_precision_is_not_recorded(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        d = guard.check_and_consume(0.00004)
        self.assertTrue(d.allowed)
        self.assertEqual(self.read_ledger(), {"spent_jpy": 0.0})

    def test_infinite_cost_is_denied(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        d = guard.check_and_consume(float("inf"))
        self.assertFalse(d.allowed)
        self.assertEqual(self.read_ledger(), {"spent_jpy": 0.0})

    def test_decision_is_frozen(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        d = guard.check_and_consume(1.0)
        with self.assertRaises(FrozenInstanceError):
            d.allowed = False  # type: ignore[misc]


# 異常系
class TestError(_LedgerTestCase):
    def test_negative_cost_raises_and_ledger_unchanged(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        with self.assertRaises(ValueError) as ctx:
            guard.check_and_consume(-0.01)
        self.assertEqual(str(ctx.exception), "estimated_cost_jpy must be non-negative")
        self.assertEqual(self.read_ledger(), {"spent_jpy": 0.0})

    def test_nan_cost_raises_and_does_not_disable_the_guard(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        with self.assertRaises(ValueError):
            guard.check_and_consume(float("nan"))
        self.assertEqual(self.read_ledger(), {"spent_jpy": 0.0})
        self.assertFalse(guard.check_and_consume(1000.0).allowed)

    def test_non_numeric_cost_raises_type_error(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        with self.assertRaises(TypeError):
            guard.check_and_consume("10")  # type: ignore[arg-type]

    def test_broken_ledger_raises_and_is_not_overwritten(self) -> None:
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        self.ledger.write_text("{broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            guard.check_and_consume(1.0)
        self.assertEqual(self.ledger.read_text(encoding="utf-8"), "{broken")

    def test_ledger_without_spent_key_raises_key_error(self) -> None:
        self.ledger.write_text("{}", encoding="utf-8")
        guard = TokenQuotaGuard(self.ledger, monthly_limit_jpy=100.0)
        with self.assertRaises(KeyError):
            guard.check_and_consume(1.0)


if __name__ == "__main__":
    unittest.main()
