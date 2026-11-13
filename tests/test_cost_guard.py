import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cost_guard import TokenQuotaGuard


class TestCostGuard(unittest.TestCase):
    def test_blocks_when_monthly_budget_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            guard = TokenQuotaGuard(Path(tmp) / "ledger.json", monthly_limit_jpy=100.0)
            d1 = guard.check_and_consume(70.0)
            d2 = guard.check_and_consume(40.0)
            self.assertTrue(d1.allowed)
            self.assertFalse(d2.allowed)
            self.assertEqual(d2.reason, "MONTHLY_BUDGET_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
