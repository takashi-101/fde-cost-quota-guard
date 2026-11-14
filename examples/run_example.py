"""examples/sample_requests.json の見積額を順に TokenQuotaGuard.check_and_consume に渡し、判定を表示します。

台帳ファイルは一時ディレクトリに作り、終了時に削除します。
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cost_guard import TokenQuotaGuard  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_requests.json"


def main() -> None:
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    limit = data["monthly_limit_jpy"]
    print(f"input: examples/{SAMPLE.name} (monthly_limit_jpy={limit})")
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.json"
        guard = TokenQuotaGuard(ledger, monthly_limit_jpy=limit)
        for req in data["requests"]:
            d = guard.check_and_consume(req["estimated_cost_jpy"])
            print(
                f"{req['request_id']} estimated={req['estimated_cost_jpy']} -> "
                f"allowed={d.allowed} spent={d.spent_jpy} remaining={d.remaining_jpy} reason={d.reason}"
            )
        print(f"ledger.json: {ledger.read_text(encoding='utf-8')}")


if __name__ == "__main__":
    main()
