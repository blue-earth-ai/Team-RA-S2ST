import sqlite3
import csv
import os

# 設定
DATA_DIR = os.environ.get('RENDER_DISK_PATH', '.')
DATABASE = os.path.join(DATA_DIR, 'chat_knowledge.db')
CSV_FILE = 'FD-BUSINESS.csv'

def import_business_data():
    if not os.path.exists(DATABASE):
        print(f"エラー: データベース {DATABASE} が見つかりません。")
        return

    if not os.path.exists(CSV_FILE):
        print(f"エラー: CSVファイル {CSV_FILE} が見つかりません。")
        return

    print("--- ビジネスデータのインポート(検索最適化版)を開始します ---")

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            
            # CSV読み込み
            with open(CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                count = 0
                for row in reader:
                    # データを取得
                    category = row.get('カテゴリー', '').strip()
                    item = row.get('項目', '').strip()
                    detail = row.get('内容詳細', '').strip()
                    doc_name = row.get('資料名', '').strip()

                    # タイトル作成 (表示用)
                    if item:
                        topic_title = item
                        if category:
                            topic_title = f"{item} ({category})"
                    else:
                        continue # 項目名がないデータはスキップ

                    # ★修正ポイント: 全情報を結合して検索用テキスト(transcript)を作成
                    # AIが文脈を理解しやすいようにラベル付きで記述し、
                    # 検索ヒット率を上げるために社名なども含める。
                    transcript = f"""
【フォーデイズ(Fordays) ビジネス情報】
■カテゴリー: {category}
■項目: {item}
■内容詳細:
{detail}
■関連資料: {doc_name}
"""
                    # 余分な空白行を削除
                    transcript = transcript.strip()

                    # 重複チェック（トピックタイトルで判定）
                    cursor.execute("SELECT id FROM knowledge WHERE topic_title = ?", (topic_title,))
                    existing = cursor.fetchone()

                    # 既存データがあれば上書き、なければ新規作成
                    # original_no は 9000番台を割り当てて、既存のセミナーデータ等と区別する
                    
                    if existing:
                        # 更新 (UPDATE)
                        cursor.execute("""
                            UPDATE knowledge 
                            SET transcript = ?, pdf_file = ?, original_no = ?
                            WHERE id = ?
                        """, (transcript, doc_name, 9000 + count, existing[0]))
                        print(f"更新: {topic_title}")
                    else:
                        # 新規登録 (INSERT)
                        cursor.execute("""
                            INSERT INTO knowledge (original_no, topic_title, transcript, pdf_file)
                            VALUES (?, ?, ?, ?)
                        """, (9000 + count, topic_title, transcript, doc_name))
                        print(f"新規: {topic_title}")
                    
                    count += 1

            conn.commit()
            print(f"\n完了: {count} 件のデータを処理しました。")
            
            # バックアップ処理の呼び出し (VPS/Render環境用)
            try:
                import backup_service as backup
                backup.upload_db_background(DATABASE, 'chat_knowledge.db')
                print("バックアップ処理（FTPアップロード）を開始しました。")
            except Exception as e:
                print(f"バックアップ処理スキップ(ローカル環境など): {e}")

    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")

if __name__ == '__main__':
    import_business_data()