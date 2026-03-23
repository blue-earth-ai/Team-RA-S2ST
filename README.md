# ai-concierge-app
# AIコンシェルジュ アプリ

著名なビジネスリーダーの人格を持つAIとの対話を実現する、高機能なWebアプリケーションです。

## 主な機能
- Gemini APIを利用したAIチャット機能
- 独自の知識データベース(SQLite)との連携
- Google Cloud TTSによる高品質な音声読み上げ
- 挨拶などへのクイックレスポンス機能
- PWA対応の美しいUI

## ローカルでの実行方法
1. `pip install -r requirements.txt`
2. `.env` ファイルに `GEMINI_API_KEY` を設定
3. `python create_database.py` を実行して知識DBを構築
4. `python app.py` を実行

## デプロイ
このアプリケーションはRenderで動作するように設定されています。
