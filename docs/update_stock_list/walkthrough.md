# 銘柄リスト更新とタイトル修正の確認

以下の修正を完了しました。

## 実施内容

### 1. 銘柄リストの更新 (`stock_app_deploy`)
- **[除外]** `5586` (Laboro.AI), `3687` (フィックスターズ) を監視リストから削除
- **[追加]** `6701` (NEC) を監視リストへ追加
- 対象ファイル: [generate_static_report.py](file:///Users/mahi/.gemini/antigravity/scratch/stock_app_deploy/generate_static_report.py)

### 2. タイトルの変更
- アプリのタイトルおよび見出しを「株需給レポート一括確認」から「**株需給レポート**」に変更しました。
- 対象ファイル: [generate_static_report.py](file:///Users/mahi/.gemini/antigravity/scratch/stock_app_deploy/generate_static_report.py)

### 3. 他プロジェクトの残存定義の削除 (`tdnet_summary`)
- `3687` が残っていた設定ファイルを修正し、データファイルを削除しました。
- 対象ファイル:
    - [generate_missing_stocks.py](file:///Users/mahi/.gemini/antigravity/scratch/tdnet_summary/stock_chart/scripts/generate_missing_stocks.py)
    - [stock_sector_mapping.json](file:///Users/mahi/.gemini/antigravity/scratch/tdnet_summary/stock_chart/scripts/stock_sector_mapping.json)
    - `3687.json` (DELETE)

## 検証結果

- `generate_static_report.py` を再実行し、生成された `index.html` において以下を確認済みです。
    - [x] タイトルが「株需給レポート」になっている
    - [x] `5586`, `3687` が含まれていない
    - [x] `6701` が含まれている
    - [x] 全16銘柄が正しく表示されている

> [!NOTE]
> `5595.T` については、yfinance側でデータ取得エラーが発生していますが、これはリスト更新とは無関係な yfinance 側の事象です。
