import sqlite3
import csv
import os
from dotenv import load_dotenv

# .env読み込み
load_dotenv()

# 設定
DATA_DIR = os.environ.get('RENDER_DISK_PATH', '.')
DATABASE = os.path.join(DATA_DIR, 'chat_knowledge.db')
CSV_FILE = 'knowledge_export.csv'

def update_knowledge_from_csv():
    """
    エクスポートされたCSV(knowledge_export.csv)を読み込み、
    IDが存在すれば更新、なければ新規登録を行う。
    """
    if not os.path.exists(DATABASE):
        print(f"❌ エラー: データベース {DATABASE} が見つかりません。")
        return

    if not os.path.exists(CSV_FILE):
        print(f"❌ エラー: CSVファイル {CSV_FILE} が見つかりません。")
        print("   先に管理者画面からエクスポートを行い、ファイルを配置してください。")
        return

    print(f"--- {CSV_FILE} によるデータベース更新を開始します ---")

    try:
        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # CSV読み込み (BOM付きUTF-8対応)
            with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                # DBのカラム名リストを取得（CSVヘッダーと照合するため）
                # CSVのヘッダーがDBのカラム名と一致している前提
                valid_columns = [description[0] for description in cursor.execute("SELECT * FROM knowledge LIMIT 1").description]
                
                updated_count = 0
                inserted_count = 0
                
                for row in reader:
                    # CSVの各行データを処理
                    
                    # IDの取得（空文字の場合はNoneにする）
                    record_id = row.get('id')
                    if record_id and record_id.strip():
                        record_id = int(record_id)
                    else:
                        record_id = None

                    # 更新・挿入用のデータを準備
                    # CSVにあるカラムのうち、DBに存在するカラムだけを抽出
                    data_to_save = {}
                    for col in valid_columns:
                        if col in row and col != 'id': # IDはSET句には含めない
                            val = row[col]
                            # 空文字をNone(NULL)として扱うか、空文字のままにするか
                            # ここでは元のデータ運用に合わせてそのまま文字列として扱う
                            data_to_save[col] = val

                    # -------------------------------------------------
                    # 1. 更新 (IDがあり、かつDBに存在する場合)
                    # -------------------------------------------------
                    is_updated = False
                    if record_id:
                        # 存在確認
                        cursor.execute("SELECT 1 FROM knowledge WHERE id = ?", (record_id,))
                        if cursor.fetchone():
                            # UPDATE文の構築
                            # "UPDATE knowledge SET col1=?, col2=? ... WHERE id=?"
                            set_clause = ", ".join([f"{col} = ?" for col in data_to_save.keys()])
                            values = list(data_to_save.values())
                            values.append(record_id)
                            
                            sql = f"UPDATE knowledge SET {set_clause} WHERE id = ?"
                            cursor.execute(sql, values)
                            updated_count += 1
                            is_updated = True
                            print(f"更新(ID:{record_id}): {data_to_save.get('topic_title', 'No Title')}")

                    # -------------------------------------------------
                    # 2. 新規登録 (IDがない、またはDBに存在しないIDの場合)
                    # -------------------------------------------------
                    if not is_updated:
                        # INSERT文の構築
                        # "INSERT INTO knowledge (col1, col2...) VALUES (?, ?...)"
                        columns = ", ".join(data_to_save.keys())
                        placeholders = ", ".join(["?" for _ in data_to_save.keys()])
                        values = list(data_to_save.values())
                        
                        sql = f"INSERT INTO knowledge ({columns}) VALUES ({placeholders})"
                        cursor.execute(sql, values)
                        inserted_count += 1
                        print(f"新規追加: {data_to_save.get('topic_title', 'No Title')}")

            conn.commit()
            print("--------------------------------------------------")
            print(f"✅ 処理完了")
            print(f"   更新した件数: {updated_count}")
            print(f"   新規追加件数: {inserted_count}")
            
            # バックアップ処理（VPS/Render用）
            try:
                import backup_service as backup
                print("☁️ バックアップ処理（FTPアップロード）を開始します...")
                backup.upload_db_background(DATABASE, 'chat_knowledge.db')
                # バックグラウンド処理だとスクリプトが即終了してしまう可能性があるため
                # ここでは少し待つか、ログで確認を促す
                print("   (バックグラウンドでアップロード中)")
            except Exception as e:
                print(f"⚠️ バックアップスキップ: {e}")

    except Exception as e:
        print(f"❌ 予期せぬエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    update_knowledge_from_csv()