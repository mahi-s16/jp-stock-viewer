# タスクリスト: CSVダウンロード機能の追加 (jp-stock-viewer)

## 準備
- [x] ドキュメント保存用ディレクトリの作成 (`docs/csv_download_jp_stock_viewer`)
- [/] 実装計画の作成と承認

## 実装
- [ ] `generate_static_report.py` の修正
    - [ ] 全銘柄のデータを収集するデータ構造の追加
    - [ ] HTMLにJSONデータを埋め込むロジックの追加
    - [ ] HTML/CSSに「CSVダウンロード」ボタンを追加
    - [ ] CSV生成・ダウンロード用のJavaScript関数の追加
- [ ] スクリプトの実行と `index.html` の更新

## 検証
- [ ] ローカル環境での `index.html` の動作確認
- [ ] CSVダウンロードボタンの動作確認
- [ ] 生成されたCSVの内容（全ての項目が含まれているか、Excelで開けるか）の確認

## 最終処理
- [ ] 修正内容の確認ドキュメント (`walkthrough.md`) の作成
- [ ] GitHubへのコミット・プッシュ
