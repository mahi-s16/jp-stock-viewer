# 銘柄リスト更新の実装計画

`jp-stock-viewer` (実体は `stock_app_deploy` ディレクトリ内のツール群) で表示・レポート出力される銘柄リストを、ユーザーから指定された新しい銘柄リストに更新します。

## 提案される変更

### stock_app_deploy

#### [MODIFY] [generate_static_report.py](file:///Users/mahi/.gemini/antigravity/scratch/stock_app_deploy/generate_static_report.py)
- (完了) `TARGET_TICKERS` 定数を更新。

#### [NEW] [scheduler.py](file:///Users/mahi/.gemini/antigravity/scratch/stock_app_deploy/scheduler.py)
- 平日の9:00〜15:30の間、10分おきに `generate_static_report.py` を実行するスケジューラーを作成します。
- 日本時間 (JST) を基準に判定を行います。

#### [MODIFY] [.github/workflows/update_report.yml](file:///Users/mahi/.gemini/antigravity/scratch/stock_app_deploy/.github/workflows/update_report.yml)
- すでに設定されていますが、GitHub Actions のスケジュール（cron）は数分の遅延が発生する可能性があるため、確実性を高めるための微調整を検討します。

## 検証計画

### 自動テスト
- `scheduler.py` を実行し、時間外の場合は待機状態になり、時間内の場合は実行されるロジックをテストします（テスト用に時間を偽装するフラグを持たせることも検討）。

### 手動検証
- 生成された `index.html` をブラウザで開き、指定した銘柄が表示されていることを確認します。
