# FDE Cost Quota Guard（円建ての累計額と上限の判定）

[![tests](https://github.com/takashi-101/fde-cost-quota-guard/actions/workflows/tests.yml/badge.svg)](https://github.com/takashi-101/fde-cost-quota-guard/actions/workflows/tests.yml)

呼び出し側が見積もった金額（円）を受け取り、JSONの台帳ファイルに記録した累計額に足しても上限を超えないかを判定するPythonのクラスです。超えない場合は加算後の累計額を台帳に書き込み、超える場合は書き込まずに `allowed=False` を返します。標準ライブラリだけで動きます。

## 30秒で読む要点
- **判定と記録だけを行います**：LLM API（大規模言語モデルを呼び出すWebのAPI）の呼び出し、料金の取得、トークン（LLMが文章を処理する単位）数の計測はしません。クラス名に Token とありますが、扱うのは呼び出し側が渡す円の見積額です。APIを呼ぶ前に見積額を渡し、`allowed` が `False` なら呼ばない、という使い方を想定しています。呼ぶかどうかは呼び出し側のコードが決めます。
- **上限ちょうどまでは許可します**：累計額＋見積額が上限を超える（`>`）ときだけ拒否し、拒否したときは台帳を変えません。負の値とNaN（非数）は `ValueError` です。
- **月の切り替えはしません**：引数名は `monthly_limit_jpy` ですが日付は扱わず、累計額は自動では0に戻りません。1つの台帳ファイルにつき1つの累計額です。

## 実行
```
python examples/run_example.py
```
`examples/sample_requests.json`（架空の依頼5件の見積額と、上限1000円）の見積額を、順に `check_and_consume` に渡します。台帳ファイルは一時ディレクトリに作り、終了時に削除します。出力：
```
input: examples/sample_requests.json (monthly_limit_jpy=1000)
REQ-001 estimated=300 -> allowed=True spent=300.0 remaining=700.0 reason=OK
REQ-002 estimated=450.5 -> allowed=True spent=750.5 remaining=249.5 reason=OK
REQ-003 estimated=300 -> allowed=False spent=750.5 remaining=249.5 reason=MONTHLY_BUDGET_EXCEEDED
REQ-004 estimated=249.5 -> allowed=True spent=1000.0 remaining=0.0 reason=OK
REQ-005 estimated=1 -> allowed=False spent=1000.0 remaining=0.0 reason=MONTHLY_BUDGET_EXCEEDED
ledger.json: {"spent_jpy": 1000.0}
```
REQ-003 は累計額750.5円に300円を足すと上限を超えるため拒否され、台帳は変わりません。REQ-004 は足すとちょうど1000円になるため許可されます。

テスト：
```
python -m unittest discover -s tests -v
```

## 判定の内容
`check_and_consume(estimated_cost_jpy)` の動きです。

| 条件 | 戻り値（`QuotaDecision`） | 台帳 |
|---|---|---|
| 見積額が負、またはNaN | `ValueError` を送出 | 変えない |
| 累計額＋見積額 ≦ 上限 | `allowed=True`、`reason="OK"`、`spent_jpy` は加算後の累計額、`remaining_jpy` は上限との差 | 加算後の累計額を書き込む |
| 累計額＋見積額 ＞ 上限 | `allowed=False`、`reason="MONTHLY_BUDGET_EXCEEDED"`、`spent_jpy` は現在の累計額、`remaining_jpy` は上限との差（0未満は0） | 変えない |

- 金額は小数第4位に丸めて返し、台帳にも丸めて書き込みます。`0.00004` のような小さな見積額は、許可されても台帳に残りません。
- 無限大（`float("inf")`）は上限を超えるため拒否します。数値でない値は `TypeError` です。
- 台帳は `{"spent_jpy": 累計額}` という形のJSONファイルです。インスタンスの生成時に、ファイルが無ければ親ディレクトリごと作って `{"spent_jpy": 0.0}` を書き込み、ファイルがあればそのまま使います。
- 台帳が読めない場合（JSONとして壊れている、`spent_jpy` が無い）は例外（`json.JSONDecodeError`、`KeyError`）になり、許可を返さず、台帳も上書きしません。

## 公開しているクラス
| 名前 | 内容 |
|---|---|
| `cost_guard.TokenQuotaGuard(ledger_path, monthly_limit_jpy)` | `ledger_path` は台帳ファイルのパス（`str` か `Path`）、`monthly_limit_jpy` は上限（円）です。判定は `check_and_consume(estimated_cost_jpy)` で行います。 |
| `cost_guard.QuotaDecision` | 判定結果のデータクラス（値をまとめて持つクラス。`frozen` 指定で変更できません）。`allowed`、`spent_jpy`、`remaining_jpy`、`reason` を持ちます。 |

パッケージは `src/` にあり、インストール用の設定（`pyproject.toml`）はありません。テストと `examples/run_example.py` は、先頭で `src` をimportパスに加えています。

## テスト（22件）
- 正常系：台帳の作成（親ディレクトリを含む）、`str` のパス、許可したときの戻り値と台帳の更新、累計、既存の台帳の引き継ぎ
- 境界値：上限ちょうどの許可、わずかに超えた場合の拒否と台帳の不変、上限に達した後の0円、上限0円、上限を下げた場合の残額0、小数第4位の丸め、丸めで残らない少額、無限大の拒否、結果が変更できないこと
- 異常系：負の値、NaN（拒否した後も上限が効くこと）、数値でない値、壊れた台帳（上書きしないこと）、`spent_jpy` の無い台帳
- READMEの「実行」に載せた出力が、`examples/run_example.py` の実際の出力と一致すること

CI（GitHub Actionsによる自動テスト）は、push と pull request のたびに、Python 3.11 と 3.12 でテストとサンプルの実行を行う設定です（`.github/workflows/tests.yml`）。

## 制約
- 月の切り替え（累計額のリセット）はしません。
- 記録するのは見積額です。実際の請求額との突き合わせはしません。
- 台帳の読み書きに排他制御（同時の書き込みを防ぐ仕組み）はありません。複数のプロセスから同じ台帳を同時に使う前提にはなっていません。
- 上限（`monthly_limit_jpy`）の値は検査しません。

## ファイル構成
```
src/cost_guard/
  quota.py                   判定と台帳の読み書き
  __init__.py                TokenQuotaGuard と QuotaDecision を公開
examples/
  sample_requests.json       見本データ（架空）
  run_example.py             見本データの見積額を順に判定して表示
tests/                       ユニットテスト
.github/workflows/tests.yml  CI
```

## 根拠（学習）

| 機能 | 裏付けになる学習（発行元・名称・発行日） | 照会先（Credly） |
|---|---|---|
| 見積額と台帳の合計を上限と比べる予算の判定 | Amazon Web Services Training and Certification「AWS Knowledge: Cloud Essentials - Training Badge」2025年5月7日 | https://www.credly.com/badges/e6ee93e4-e882-41d5-ae3e-9bda27c1bf10 |

## ライセンス
MIT（[LICENSE](LICENSE)）
