import os
import uuid
import logging
import threading
from datetime import timedelta
from flask import Flask, jsonify, render_template, session, send_from_directory, request, redirect, url_for, make_response
from logging.handlers import RotatingFileHandler
from datetime import datetime
from zoneinfo import ZoneInfo

import services as sv
import backup_service as backup
import create_database

from routes_concierge import concierge_bp
from routes_seminar import seminar_bp
from routes_search import search_bp
from routes_admin import admin_bp

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-for-dev')

# セッションの有効期限を10年に設定 (永続化ログイン)
app.permanent_session_lifetime = timedelta(days=3650)

# --- メンテナンスモード設定 ---
MAINTENANCE_MODE = os.environ.get('MAINTENANCE_MODE', 'false').lower() == 'true'
ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')

@app.route('/maintenance')
def maintenance():
    if not MAINTENANCE_MODE:
        return redirect(url_for('index'))
    return render_template('maintenance.html')

@app.before_request
def check_maintenance_mode():
    if not MAINTENANCE_MODE:
        return
    if request.path.startswith('/static') or request.path.startswith('/data') or request.path == '/health':
        return
    if request.path == '/maintenance':
        return
    if request.path == '/login':
        return
    if session.get('username') == ADMIN_USER:
        return
    return redirect(url_for('maintenance'))

# --- ★追加: ORB/CORS対策ヘッダー & エラーハンドリング ---

@app.after_request
def add_security_headers(response):
    # クロスオリジン許可とORB対策
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    # MIMEタイプスニッフィングを許可しない(セキュリティ)設定を少し緩める必要がある場合もあるが
    # 基本は nosniff で、Content-Typeを正しく返すことが重要
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

# APIリクエストでエラーが起きてもHTMLを返さないようにする
@app.errorhandler(404)
def not_found(e):
    # staticファイルやdataファイルの404は、ログに残しつつ404を返す
    if request.path.startswith('/static/') or request.path.startswith('/data/'):
        return make_response("File Not Found", 404)
    # APIへのアクセスならJSONを返す
    if request.is_json or request.path.startswith('/chat') or request.path.startswith('/process_chat'):
        return jsonify({"error": "Not Found"}), 404
    return render_template('index.html'), 404 # 基本はトップへ戻すか、indexを表示

@app.errorhandler(500)
def server_error(e):
    if request.is_json or request.path.startswith('/chat'):
        return jsonify({"error": "Server Error"}), 500
    return "Internal Server Error", 500

# -------------------------------------------------------

# ログ設定
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = logging.Formatter(log_format)
file_handler = RotatingFileHandler('app.log', encoding='utf-8', maxBytes=10*1024*1024, backupCount=3)
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logging.root.setLevel(logging.INFO)
logging.root.addHandler(file_handler)
logging.root.addHandler(console_handler)
logger = logging.getLogger(__name__)

logger.info("==================================================")
logger.info("アプリケーション起動プロセス開始")
logger.info("==================================================")

# DB復元
if not os.path.exists(sv.USER_DB):
    logger.info("ユーザーDB復元中...")
    if backup.download_db(sv.USER_DB, 'users.db'): logger.info("ユーザーDB復元完了")
    else: logger.info("ユーザーDBなし(新規作成)")

if not os.path.exists(sv.KNOWLEDGE_DB):
    logger.info("知識DB復元中...")
    if not backup.download_db(sv.KNOWLEDGE_DB, 'chat_knowledge.db'):
        logger.info("知識DBなし(CSVから構築)")
        try: create_database.create_knowledge_db()
        except Exception as e: logger.error(f"構築エラー: {e}")

sv.init_db()

# ★追加: 待機音声を起動時に確実に生成しておく
try:
    sv.ensure_hold_message_exists()
    logger.info("待機音声の確認・生成完了")
except Exception as e:
    logger.warning(f"待機音声生成警告: {e}")

def restore_audio_bg():
    try: backup.restore_audio_cache(); logger.info("音声キャッシュ同期完了")
    except Exception as e: logger.error(f"音声同期エラー: {e}")
threading.Thread(target=restore_audio_bg, daemon=True).start()

app.register_blueprint(concierge_bp)
app.register_blueprint(seminar_bp)
app.register_blueprint(search_bp)
app.register_blueprint(admin_bp)

# =========================================================
# ルーティング
# =========================================================

@app.route('/data/<path:filename>')
def serve_data_file(filename):
    try: return send_from_directory(os.path.join(sv.DATA_DIR, 'data'), filename)
    except: return jsonify({"error": "File Not Found"}), 404

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'username' in session:
            return redirect(url_for('index'))
        return render_template('login.html')
    
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if sv.verify_user(username, password):
        session.permanent = True
        session['username'] = username
        session['session_id'] = str(uuid.uuid4())
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "error", "message": "IDまたはパスワードが違います"})

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('session_id', None)
    session.permanent = False
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))

    if 'session_id' not in session: 
        session['session_id'] = str(uuid.uuid4())
        session.permanent = True
    
    history = []
    if os.path.exists(sv.DATABASE):
        try:
            with sv.get_db_connection(sv.DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT sender, message FROM messages WHERE session_id = ? ORDER BY id ASC", (session['session_id'],))
                history = [{'sender': row['sender'], 'message': row['message']} for row in cursor.fetchall()]
        except Exception as e: logger.error(f"履歴エラー: {e}")
    
    return render_template('index.html', history=history)

@app.route('/health')
def health(): return jsonify({"status": "ok"})

@app.route('/reset_session', methods=['POST'])
def reset_session():
    session['session_id'] = str(uuid.uuid4())
    session.permanent = True 
    return jsonify({"status": "ok"})

@app.route('/get_greeting', methods=['GET'])
def get_greeting():
    try:
        h = datetime.now(ZoneInfo("Asia/Tokyo")).hour
        text = "おはようございます！" if 5<=h<11 else "こんにちは！" if 11<=h<17 else "こんばんは！"
        text += "何かご質問はありますか？"

        # 音声は固定ファイルを使い回すためAPIコールしないロジックに変更しても良いが、
        # 挨拶は時間帯で変わるため都度生成か、3パターン生成推奨。
        # 現状はサービスの generate_speech_audio に任せる。
        
        audio = sv.generate_speech_audio(text)
        if 'session_id' in session:
            with sv.get_db_connection(sv.DATABASE) as conn:
                conn.execute("INSERT INTO messages (sender, message, session_id, username) VALUES (?, ?, ?, ?)", ('ai', text, session['session_id'], session.get('username')))
                conn.commit()
        return jsonify({'text': text, 'audio_url': audio})
    except: return jsonify({"error": "Error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)