import os
import glob
import sqlite3
import logging
import uuid
import re
import time
import csv
import io
import smtplib
import json
import ast
import base64
from email.mime.text import MIMEText
from dotenv import load_dotenv
import google.generativeai as genai
from google.cloud import texttospeech
from google.oauth2 import service_account
from duckduckgo_search import DDGS
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash
import backup_service as backup

load_dotenv()

DATA_DIR = os.environ.get('RENDER_DISK_PATH', '.') 
DATABASE = os.path.join(DATA_DIR, 'chat_history.db')
KNOWLEDGE_DB = os.path.join(DATA_DIR, 'chat_knowledge.db')
USER_DB = os.path.join(DATA_DIR, 'users.db')

# Gemini初期化
try:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        logging.info("Gemini 2.5 Flash モデルの初期化が完了しました。")
    else: 
        model = None
        logging.warning("GEMINI_API_KEYが設定されていません。")
except Exception as e:
    logging.exception("Gemini API初期化エラー")
    model = None

# 安全設定
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# --- データベース関連 ---
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, message TEXT, session_id TEXT, username TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS learning_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, user_message TEXT, ai_response TEXT, 
            feedback_score INTEGER, feedback_comment TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
        # ★追加: 履歴クリア位置を記録するテーブル
        conn.execute('''CREATE TABLE IF NOT EXISTS history_clears (
            username TEXT PRIMARY KEY,
            last_cleared_id INTEGER
        )''')
    
    with sqlite3.connect(USER_DB) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, info TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            hashed = generate_password_hash('admin123')
            conn.execute("INSERT INTO users (username, password_hash, info) VALUES (?, ?, ?)", ('admin', hashed, 'システム管理者'))
        conn.commit()

def get_db_connection(db_path=DATABASE):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# --- ユーザー管理 ---
def add_user(username, password, info=""):
    try:
        with sqlite3.connect(USER_DB) as conn:
            hashed = generate_password_hash(password)
            conn.execute("INSERT INTO users (username, password_hash, info) VALUES (?, ?, ?)", (username, hashed, info))
            conn.commit()
        backup.upload_db_background(USER_DB, 'users.db')
        return True, "登録しました"
    except sqlite3.IntegrityError: return False, "既に使用されています"
    except Exception as e: return False, str(e)

def update_user(username, password=None, info=None):
    try:
        with sqlite3.connect(USER_DB) as conn:
            if password and password.strip():
                hashed = generate_password_hash(password)
                conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed, username))
            if info is not None:
                conn.execute("UPDATE users SET info = ? WHERE username = ?", (info, username))
            conn.commit()
        backup.upload_db_background(USER_DB, 'users.db')
        return True, "更新しました"
    except Exception as e: return False, str(e)

def delete_user(username):
    if username == 'admin': return False, "adminは削除できません"
    try:
        with sqlite3.connect(USER_DB) as conn:
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
        backup.upload_db_background(USER_DB, 'users.db')
        return True, "削除しました"
    except Exception as e: return False, str(e)

def import_users_from_csv(file_stream):
    file_bytes = file_stream.read()
    text = ""
    try:
        text = file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode('cp932')
        except UnicodeDecodeError:
            raise Exception("CSVの文字コードを判別できませんでした (UTF-8 または Shift-JIS 推奨)")

    f = io.StringIO(text)
    reader = csv.reader(f)
    added = 0; updated = 0; skipped = 0
    for row in reader:
        if not row or len(row) < 2: continue
        u = row[0].strip(); p = row[1].strip(); i = row[2].strip() if len(row) > 2 else ""
        if u and p:
            success, msg = add_user(u, p, i)
            if success: added += 1
            elif "既に使用されています" in msg:
                up_success, _ = update_user(u, p, i)
                if up_success: updated += 1
                else: skipped += 1
            else: skipped += 1
    backup.upload_db_background(USER_DB, 'users.db')
    return added, updated, []

def verify_user(username, password):
    try:
        with sqlite3.connect(USER_DB) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row and check_password_hash(row['password_hash'], password):
                return True
    except Exception: pass
    return False

def get_all_users():
    with sqlite3.connect(USER_DB) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT username, info, created_at FROM users ORDER BY username ASC").fetchall()]

# --- セミナー管理 ---
def get_all_seminars_status():
    if not os.path.exists(KNOWLEDGE_DB): return []
    try:
        with get_db_connection(KNOWLEDGE_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, topic_title, ai_lecture_audio_url FROM knowledge WHERE transcript IS NOT NULL AND transcript != '' ORDER BY original_no")
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                item['is_generated'] = bool(item.get('ai_lecture_audio_url'))
                results.append(item)
            return results
    except Exception as e:
        logging.error(f"セミナー状況取得エラー: {e}")
        return []

def reset_seminar_data(seminar_id):
    try:
        with get_db_connection(KNOWLEDGE_DB) as conn:
            conn.execute("UPDATE knowledge SET ai_lecture_audio_url = '', ai_script = '' WHERE id = ?", (seminar_id,))
            conn.commit()
        return True, "リセットしました"
    except Exception as e: return False, str(e)

# ★追加: 知識DBの全データを取得する関数 (CSVエクスポート用)
def get_all_knowledge_data():
    if not os.path.exists(KNOWLEDGE_DB): return [], []
    try:
        with get_db_connection(KNOWLEDGE_DB) as conn:
            cursor = conn.cursor()
            # 全データを取得
            cursor.execute("SELECT * FROM knowledge ORDER BY original_no")
            rows = cursor.fetchall()
            # カラム名(ヘッダー)を取得
            headers = [description[0] for description in cursor.description]
            return headers, rows
    except Exception as e:
        logging.error(f"全知識データ取得エラー: {e}")
        return [], []

# --- 情報取得 ---
def get_all_topics():
    if not os.path.exists(KNOWLEDGE_DB): return []
    try:
        with get_db_connection(KNOWLEDGE_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT topic_title FROM knowledge ORDER BY topic_title")
            return [row[0] for row in cursor.fetchall()]
    except Exception: return []

def get_bad_feedbacks(limit=5):
    if not os.path.exists(DATABASE): return []
    try:
        with get_db_connection(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_message, ai_response, feedback_comment FROM learning_logs WHERE feedback_score = 0 ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception: return []

# --- 認証 & 音声処理 ---

def _get_credentials_object():
    cred_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not cred_env: return None

    try:
        clean_content = cred_env.strip()
        parsed_data = None

        # 1. Base64
        try:
            decoded_bytes = base64.b64decode(clean_content)
            parsed_data = json.loads(decoded_bytes.decode('utf-8'))
        except: pass

        # 2. Raw JSON
        if parsed_data is None:
            try: parsed_data = json.loads(clean_content)
            except: pass
        
        # 3. Python Dict str
        if parsed_data is None:
            try: parsed_data = ast.literal_eval(clean_content)
            except: 
                try:
                    if (clean_content.startswith('"') and clean_content.endswith('"')) or (clean_content.startswith("'") and clean_content.endswith("'")):
                        parsed_data = json.loads(clean_content.strip().replace('\\"', '"'))
                except: pass

        if isinstance(parsed_data, dict):
            return service_account.Credentials.from_service_account_info(parsed_data)
        return None
    except Exception as e:
        logging.error(f"認証オブジェクト生成エラー: {e}")
        return None

def cleanup_old_audio_files():
    try:
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'audio')
        if not os.path.exists(static_dir): return
        protected_files = set()
        
        # 固定ファイルは削除しない
        protected_files.add('hold_message.mp3')

        try:
            with get_db_connection(KNOWLEDGE_DB) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ai_lecture_audio_url FROM knowledge WHERE ai_lecture_audio_url IS NOT NULL AND ai_lecture_audio_url != ''")
                for row in cursor.fetchall():
                    if row[0]: protected_files.add(os.path.basename(row[0]))
        except: pass
        now = time.time()
        for f in os.listdir(static_dir):
            if f.endswith('.mp3') and f not in protected_files:
                if (now - os.path.getmtime(os.path.join(static_dir, f))) > 86400:
                    os.remove(os.path.join(static_dir, f))
    except: pass

def split_text_for_tts(text, max_bytes=4000):
    SSML_OVERHEAD = 100
    effective_max = max_bytes - SSML_OVERHEAD
    chunks = []
    current_chunk = ""
    sentences = re.split(r'([。！？\n])', text)
    combined_sentences = []
    for i in range(0, len(sentences), 2):
        s = sentences[i]
        sep = sentences[i+1] if i+1 < len(sentences) else ''
        combined_sentences.append(s + sep)
    for sentence in combined_sentences:
        if not sentence.strip(): continue
        if len((current_chunk + sentence).encode('utf-8')) <= effective_max:
            current_chunk += sentence
        else:
            if current_chunk: chunks.append(current_chunk)
            current_chunk = sentence
    if current_chunk: chunks.append(current_chunk)
    return chunks

def _rewrite_for_tts(text):
    if not model: return text
    if len(text) < 30 and "Team" not in text: return text
    
    # ★二重読み防止のための、厳密な書き換え指示プロンプト
    prompt = f"""
    # 命令書
    以下のテキストは音声合成（TTS）システムで読み上げられます。
    読み間違いや二重読みを防ぐため、以下のルールに従って「読み上げ用原稿」に書き換えてください。

    # 書き換えルール
    1. **読み間違いやすい漢字や固有名詞は、カッコ書きを使わず、そのまま「ひらがな」または「カタカナ」に置き換えてください。**
       - 悪い例: 明日(あす)
       - 良い例: あす
       - 悪い例: 人気(ひとけ)
       - 良い例: ひとけ
    2. 「Team RA」は「チーム・ラー」に置き換えてください。
    3. URL、[リンク]、markdown記号は削除するか、音声で自然な言葉に置き換えてください。
    4. 文脈に合わせて読点（、）を適切に補ってください。
    5. 出力は書き換えたテキストのみを行ってください。

    # 元テキスト
    {text}
    """
    try:
        resp = _call_gemini_with_retry(prompt, retries=1)
        if resp and resp.text: return resp.text.strip()
        return text
    except: return text

# ★追加: 起動時に確実に待機音声を生成する関数
def ensure_hold_message_exists():
    msg = "承知いたしました。内容を確認しますので、少々お待ちください。"
    get_hold_message_audio(msg)

def get_hold_message_audio(text):
    """思考中メッセージ用の音声を生成または取得する"""
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'audio')
    os.makedirs(static_dir, exist_ok=True)
    filename = "hold_message.mp3"
    filepath = os.path.join(static_dir, filename)
    if os.path.exists(filepath):
        return f"/static/audio/{filename}"
    return generate_speech_audio(text, fixed_filename=filename)

def generate_speech_audio(text_to_speak, fixed_filename=None):
    cleanup_old_audio_files()
    try:
        text = re.sub(r'https?://[^\s]+', '', text_to_speak)
        text = re.sub(r'data/[^\s]+', '', text)
        tags = [r'\[元動画URL\]', r'\[教科書\]', r'\[教科書URL\]', r'\[レジュメ\]', r'\[レジュメURL\]', r'\[関連資料\]', r'\[関連資料URL\]']
        for tag in tags: text = re.sub(fr'.*{tag}.*', '', text)
        text = text.replace('**', '').replace('*', '').replace('#', '').replace('\n+', '\n')
        
        if not fixed_filename:
            text = _rewrite_for_tts(text)
        
        text = text.replace('Team RA', 'チーム・ラー').replace('TeamRA', 'チーム・ラー')

        if not text.strip(): return None
        
        creds = _get_credentials_object()
        tts_client = texttospeech.TextToSpeechClient(credentials=creds) if creds else texttospeech.TextToSpeechClient()

        voice = texttospeech.VoiceSelectionParams(language_code="ja-JP", name="ja-JP-Standard-C")
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        chunks = split_text_for_tts(text, max_bytes=4000)
        if not chunks: return None
        
        combined_audio = b''
        for chunk in chunks:
            if not chunk.strip(): continue
            ssml = f"<speak>{chunk.replace(chr(10), '<break time=\"0.5s\"/>')}</speak>"
            try:
                s_input = texttospeech.SynthesisInput(ssml=ssml)
                combined_audio += tts_client.synthesize_speech(input=s_input, voice=voice, audio_config=audio_config).audio_content
            except: continue

        if not combined_audio: return None
        
        filename = fixed_filename if fixed_filename else f"{uuid.uuid4()}.mp3"
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'audio')
        os.makedirs(static_dir, exist_ok=True)
        path = os.path.join(static_dir, filename)
        with open(path, "wb") as out: out.write(combined_audio)
        
        try: backup.upload_audio_background(path, filename)
        except: pass
        return f"/static/audio/{filename}"
    except Exception as e:
        logging.error(f"TTSエラー: {e}")
        return None

# --- AI生成ロジック ---
def _call_gemini_with_retry(prompt, retries=3):
    if not model: return None
    for i in range(retries):
        try: 
            return model.generate_content(prompt, safety_settings=SAFETY_SETTINGS)
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e): time.sleep(2**i)
            else: break
    return None

def analyze_query_intent(question):
    if not model: return {"is_business": True, "keywords": [question]} 
    
    prompt = f"""
    # 命令書
    ユーザーの質問を分析し、以下の2点を出力してください。
    
    1. **is_business**: この質問は「ビジネス」「仕事」「自己啓発」「Team RA」「会社に関する知識」に関連しますか？
       - 挨拶（こんにちは）、感謝（ありがとう）、無関係な雑談（映画、芸能、今日の天気、気候、季節の話題など）は `false`
       - ビジネス用語、会社名、仕組み、悩み相談などは `true`
    2. **keywords**: データベース検索用のキーワード（固有名詞、重要単語）を3〜5つ抽出してください。
       - `is_business`が`false`の場合は空リスト `[]` で構いません。
    
    # 出力フォーマット (JSONのみ)
    {{ "is_business": true, "keywords": ["フォーデイズ", "核酸", "評判"] }}
    
    # 質問
    {question}
    """
    try:
        resp = _call_gemini_with_retry(prompt)
        if not resp or not resp.text: 
            return {"is_business": True, "keywords": [question]}
        
        # ★JSON解析の強化（マークダウン除去）
        text = resp.text.strip()
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        
        return json.loads(text)
    except:
        return {"is_business": True, "keywords": [question]}

def generate_keywords_from_ai(question):
    return []

def _search_fordays_web(query):
    try:
        search_query = f"site:fordays.jp {query}"
        results = DDGS().text(search_query, max_results=3)
        if not results: return ""
        web_text = "【公式サイト検索結果】\n"
        for r in results:
            web_text += f"- タイトル: {r['title']}\n  URL: {r['href']}\n  抜粋: {r['body']}\n\n"
        return web_text
    except Exception as e:
        logging.warning(f"Web検索エラー: {e}")
        return ""

# ★追加: AIに全トピックリストから最適なものを推論させる
def find_best_topic_match(question, all_topics):
    if not model or not all_topics: return None
    
    topics_str = "\n".join(all_topics)
    prompt = f"""
    # 命令書
    ユーザーの質問に最も関連するデータベースの「項目名」を、以下のリストから1つだけ選んでください。
    
    # 質問
    {question}
    
    # データベースの項目リスト
    {topics_str}
    
    # 制約
    - リストの中にある文字列を**そのまま**出力してください。
    - 関連するものがなければ「None」と出力してください。
    - 余計な説明は不要です。
    """
    try:
        resp = _call_gemini_with_retry(prompt)
        if resp and resp.text:
            topic = resp.text.strip()
            if topic in all_topics:
                return topic
    except: pass
    return None

# 総合調査関数
def perform_comprehensive_search(question):
    search_results = {"db": [], "web": ""}
    
    # 1. DB検索
    if os.path.exists(KNOWLEDGE_DB):
        try:
            all_topics = get_all_topics()
            if all_topics:
                inferred_topic = find_best_topic_match(question, all_topics)
                if inferred_topic:
                    with get_db_connection(KNOWLEDGE_DB) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT topic_title, transcript FROM knowledge WHERE topic_title = ?", (inferred_topic,))
                        row = cursor.fetchone()
                        if row: search_results["db"].append(f"■データベース情報: {row['topic_title']}\n{row['transcript']}")
        except: pass

    # 2. Web検索 (DBヒットなしの場合のみ実行)
    # search_results["db"] が空の場合だけ検索する
    if not search_results["db"]:
        try:
            results = DDGS().text(f"site:fordays.jp {question}", max_results=2)
            if results:
                web_text = "■Web検索結果 (公式サイト):\n"
                for r in results:
                    web_text += f"- {r['title']}: {r['body']}\n"
                search_results["web"] = web_text
        except Exception as e: logging.error(f"Web Search Error: {e}")
    else:
        logging.info("DB検索でヒットしたため、Web検索をスキップしました。")
    
    return search_results

# ★トップリーダー人格 + アスタリスク除去 + JSONクリーニング対応版
def generate_answer_from_ai(question, search_results, history, is_business):
    if not model: return "申し訳ありません。AIが利用できません。"
    
    hist_text = "\n".join([f"{h['sender']}:{h['message']}" for h in history])
    
    # 調査結果のテキスト化
    materials = ""
    if isinstance(search_results, dict):
        materials = "\n\n".join(search_results.get("db", []))
        materials += "\n" + search_results.get("web", "")
    elif isinstance(search_results, list):
        for ref in search_results:
             materials += f"\nテーマ:{ref.get('topic_title','')}\n{ref.get('transcript','')}"

    # ペルソナ定義
    persona = """
    あなたは、フォーデイズ(Fordays)のビジネス会員のグループ「Team RA」のリーダーであり、トップランカーの思考を持つ「AIビジネスメンター」です。フォーデイズ(Fordays)の「社員」や「広報」ではありません。
    """

    prompt = f"""
    # あなたの役割
    {persona}

    # ユーザーの質問
    {question}

    # 調査結果 (あなたの手持ち資料)
    {materials}

    # 回答のガイドライン
    手持ちの資料を自由に活用し、ビジネスメンターとしてのアドバイスを作成してください。
    1. **資料の活用**: 資料の中に答えがあれば、それを根拠に回答してください。
    2. **Web情報の活用**: DB資料に情報がなかった場合のみ、Web検索結果を参考に補足してください。
    3. **回答までのスピードを最優先してください。できる限り回答は、300文字以内におさめてください。
    4. **柔軟な対応**: 資料にズバリそのものの答えがなくても、「資料にはありませんでしたが、一般的には〜」「Webの情報によると〜」といった形で、知っている範囲で精一杯答えてください。「わかりません」と即答するのは避けてください。
    5. **人格**: 誠実で、ユーザーを応援する温かい口調で話してください。
    6. **禁止事項**: 出力にアスタリスク(*)や(#)などのマークダウン記号は使わないでください。また、ハルシネーションが起こらぬように細心の注意を払ってください。
    
    # 会話履歴
    {hist_text}

    回答:
    """
    
    if not is_business:
         prompt = f"""
         # あなたの役割
         {persona}
         
         # 命令
         ユーザーから雑談や挨拶が届きました。
         トップリーダーとしての余裕と愛嬌を持って対応してください。
         
         質問: {question}
         会話履歴: {hist_text}
         
         ルール:
         1. 挨拶には元気に返す。
         2. 無関係な話題は否定せず、自然に「ビジネスの目標」や「最近の調子」の話へ誘導する。
         3. 「弊社」などの社員言葉は禁止。
         4. アスタリスク(*)や(#)は使わない。
         """

    try:
        resp = _call_gemini_with_retry(prompt)
        text = resp.text.strip() if resp else "申し訳ありません。考えがまとまりませんでした。すこし時間をおいてからやり直していただけますか？"
        return text.replace('*', '')
    except: return "申し訳ありません。エラーが発生しました。すこし時間をおいてからやり直してください"

def get_quick_response(message):
    if 'こんにちは' in message: return 'こんにちは！何かお手伝いしましょうか？'
    if 'ありがとう' in message: return 'どういたしまして！'
    return None

def send_email_notification(subject, body):
    s_server = os.environ.get('SMTP_SERVER')
    s_port = int(os.environ.get('SMTP_PORT', 587))
    s_user = os.environ.get('SMTP_USER')
    s_pass = os.environ.get('SMTP_PASS')     
    to = os.environ.get('TARGET_EMAIL')    
    frm = os.environ.get('MAIL_FROM', s_user) 
    if not all([s_server, s_user, s_pass, to]): return False
    msg = MIMEText(body); msg['Subject']=subject; msg['From']=frm; msg['To']=to
    msg.add_header('Content-Type','text/plain; charset=UTF-8')
    try:
        with smtplib.SMTP(s_server, s_port) as s:
            s.ehlo(); s.starttls(); s.ehlo(); s.login(s_user, s_pass); s.send_message(msg)
        return True
    except: return False