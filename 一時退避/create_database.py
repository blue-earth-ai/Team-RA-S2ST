import sqlite3
import csv
import os

# 設定
DATA_DIR = os.environ.get('RENDER_DISK_PATH', '.')
CSV_FILE = 'Hontake_DB_Base002.csv' 
DATABASE = os.path.join(DATA_DIR, 'chat_knowledge.db')

def create_knowledge_db():
    # 古いDBがあれば削除（完全リセット）
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
        print(f"既存のデータベース {DATABASE} を削除しました。")

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # ★修正: knowledge テーブルから transcript_path に対応するカラムを削除
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_no INTEGER,
                topic_title TEXT,
                transcript TEXT,             -- ★このカラムにテキストファイルの内容を格納
                video_link_url TEXT,
                avatar_url TEXT,
                ai_lecture_audio_url TEXT,
                ai_script TEXT,
                pdf_file TEXT,
                pdf_file_url TEXT,
                page INTEGER,
                related_doc_name TEXT,
                related_doc_url TEXT,
                seminar_doc_name TEXT,
                seminar_doc_url TEXT,
                lecture_audio_url TEXT
            )
        ''')

        if not os.path.exists(CSV_FILE):
            print(f"エラー: CSVファイル {CSV_FILE} が見つかりません。")
            return

        print(f"{CSV_FILE} の読み込みを開始します...")
        
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            count = 0
            for row in reader:
                # 1. テキストファイルの読み込み処理 (ここは変更なし)
                transcript_content = ""
                txt_path = row.get('transcript_path', '').strip()
                
                if txt_path and os.path.exists(txt_path):
                    try:
                        with open(txt_path, 'r', encoding='utf-8') as tf:
                            transcript_content = tf.read()
                    except Exception as e:
                        print(f"警告: テキストファイル読み込みエラー ({txt_path}): {e}")
                elif txt_path:
                    # ★修正: 警告を出しつつ、ファイルが見つからなくても続行
                    print(f"警告: 指定されたテキストファイルが見つかりません: {txt_path} - 空の内容で登録します。")

                try:
                    data = (
                        row.get('id', 0),
                        row.get('topic_title', ''),
                        transcript_content,                    # ★テキストファイルの内容
                        row.get('video_url', ''),
                        row.get('avatar_path', ''),
                        '', 
                        '', 
                        row.get('textbook_name', ''),
                        row.get('textbook_path', ''),
                        row.get('textbook_page', 0),
                        row.get('related_doc_name', ''),
                        row.get('related_doc_path', ''),
                        row.get('seminar_doc_name', ''),
                        row.get('seminar_doc_url', ''),
                        row.get('lecture_audio_url', '')
                    )
                    
                    # 3. INSERT文の修正（DBの列数に合わせる）
                    cursor.execute('''
                        INSERT INTO knowledge 
                        (original_no, topic_title, transcript, video_link_url, avatar_url, ai_lecture_audio_url, ai_script, pdf_file, pdf_file_url, page, related_doc_name, related_doc_url, seminar_doc_name, seminar_doc_url, lecture_audio_url) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', data)
                    count += 1
                except Exception as e:
                    print(f"行の挿入エラー: {e} | Row: {row}")

            conn.commit()
            print(f"完了: 合計 {count} 件のデータを {DATABASE} に登録しました。")

if __name__ == '__main__':
    create_knowledge_db()