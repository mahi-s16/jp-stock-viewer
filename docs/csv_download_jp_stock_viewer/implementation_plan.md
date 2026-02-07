# 実装計画: 全銘柄データのCSVダウンロード機能追加

「株需給レポート」の全16銘柄について、表示されている全ての詳細データ（価格、勢い、RSI、信用残など）を一つのCSVファイルとしてダウンロードできる機能を追加します。

## 変更内容の概要
現在のレポート生成スクリプトを拡張し、HTML内に全銘柄の構造化データをJSON形式で保持させます。ユーザーが「CSV保存」ボタンをクリックした際に、ブラウザ側でそのJSONデータを解析し、BOM付きUTF-8（Excel対応）のCSVファイルを生成してダウンロードさせます。

## Proposed Changes

### [Component] データ収集とレポート生成 (Python)

#### [MODIFY] [generate_static_report.py](file:///Users/mahi/.gemini/antigravity/scratch/stock_app_deploy/generate_static_report.py)
- `process_ticker` の戻り値、または `main` ループ内の収集処理を拡張し、信用残明細（買残・売残・日付）を含めた全項目を保持するようにします。
- `main` 関数で、収集した全データをJSON文字列に変換し、HTMLテンプレートの所定の位置に埋め込みます。

### [Component] ユーザーインターフェース (HTML/JS)

#### [MODIFY] [generate_static_report.py](file:///Users/mahi/.gemini/antigravity/scratch/stock_app_deploy/generate_static_report.py) (HTML出力部分)
- **HTML/CSS**: ページのヘッダー付近（更新日時の下など）に「CSV保存」ボタンを追加します。
- **JavaScript**: JSONデータを読み取り、以下の項目を含むCSVを生成する `downloadFullCSV()` 関数を追加します。
    - 取得時刻
    - コード
    - 銘柄名
    - 現在値
    - 前日比(%)
    - 勢いスコア
    - 壁の名前 (しこり/真空)
    - 壁までの距離(%)
    - RSI(14)
    - 信用買残
    - 信用売残
    - 信用倍率
    - 信用残更新日

## Verification Plan

### Automated Verification
- `generate_static_report.py` を実行し、エラーなく `index.html` が生成されることを確認します。

### Manual Verification
- 生成された `index.html` をブラウザで開き、追加された「CSV保存」ボタンが表示されていることを確認します。
- ボタンをクリックし、CSVファイルがダウンロードされることを確認します。
- ダウンロードされたCSVをExcelまたはテキストエディタで開き、データが正しく並んでいること、文字化け（BOM）がないことを確認します。
