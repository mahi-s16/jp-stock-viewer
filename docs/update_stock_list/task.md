# タスク: jp-stock-viewer の銘柄リスト更新とタイトル修正

- [x] `stock_app_deploy/generate_static_report.py` の `TARGET_TICKERS` 更新 (5586, 3687除外、6701追加)
- [x] `stock_app_deploy/generate_static_report.py` のタイトルを「株需給レポート」に変更
- [x] `tdnet_summary/stock_chart/` 内の各ファイルから 5586, 3687 を完全に除外
    - `scripts/generate_missing_stocks.py`
    - `scripts/stock_sector_mapping.json`
- [x] 各プロジェクトのレポート再生成と動作確認
- [x] GitHub (mainブランチ) へのプッシュによるデプロイ
- [x] 最終的な修正内容のドキュメント化
