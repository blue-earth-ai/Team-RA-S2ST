from flask import Blueprint, request, jsonify, session
import services as sv
import uuid
import logging
import time

logger = logging.getLogger(__name__)
concierge_bp = Blueprint('concierge', __name__)

@concierge_bp.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message')
        if not user_message: return jsonify({"error": "No message"}), 400
        
        if 'session_id' not in session: session['session_id'] = str(uuid.uuid4())
        session_id = session['session_id']
        username = session.get('username', 'guest')
        
        logger.info(f"[Chat] User: {user_message[:30]}... ({username})")
        
        with sv.get_db_connection(sv.DATABASE) as conn:
            conn.execute("INSERT INTO messages (sender, message, session_id, username) VALUES (?, ?, ?, ?)", ('user', user_message, session_id, username))
            conn.commit()
        
        quick = sv.get_quick_response(user_message)
        if quick:
            audio = sv.generate_speech_audio(quick)
            with sv.get_db_connection(sv.DATABASE) as conn:
                conn.execute("INSERT INTO messages (sender, message, session_id, username) VALUES (?, ?, ?, ?)", ('ai', quick, session_id, username))
                conn.commit()
            return jsonify({'final_response': quick, 'final_audio_url': audio})
        
        msg = "承知いたしました。内容を確認しますので、少々お待ちください。"
        audio = sv.get_hold_message_audio(msg)
        return jsonify({'interim_response': msg, 'interim_audio_url': audio})
        
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return jsonify({"error": str(e)}), 500

@concierge_bp.route('/process_chat', methods=['POST'])
def process_chat():
    try:
        start_time = time.time()
        user_message = request.json.get('message')
        session_id = session.get('session_id')
        username = session.get('username', 'guest')
        
        # 履歴取得
        history = []
        with sv.get_db_connection(sv.DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sender, message FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
            history = [{'sender': row['sender'], 'message': row['message']} for row in cursor.fetchall()]

        # 1. 意図判定
        analysis = sv.analyze_query_intent(user_message)
        is_business = analysis.get("is_business", True)
        
        search_results = {"db": [], "web": ""}
        
        # 2. ビジネス関連なら、AIに「調査」を依頼 (DB + Web)
        if is_business:
            logger.info("AIによる総合調査を開始...")
            search_results = sv.perform_comprehensive_search(user_message)
            logger.info(f"調査完了: DBヒット={len(search_results['db'])}件, Webヒット={'あり' if search_results['web'] else 'なし'}")

        # 3. 調査結果を持たせて、AIに回答を作成させる
        resp_text = sv.generate_answer_from_ai(user_message, search_results, history, is_business)
        
        audio_url = sv.generate_speech_audio(resp_text)
        
        # ログ保存
        with sv.get_db_connection(sv.DATABASE) as conn:
            conn.execute("INSERT INTO messages (sender, message, session_id, username) VALUES (?, ?, ?, ?)", ('ai', resp_text, session_id, username))
            conn.commit()
            
        return jsonify({
            'final_response': resp_text, 
            'final_audio_url': audio_url,
            'elapsed_time': f"{(time.time() - start_time):.2f}"
        })

    except Exception as e:
        logger.error(f"ProcessChat Error: {e}")
        return jsonify({'final_response': "申し訳ありません。エラーが発生しました。", 'final_audio_url': None}), 500

@concierge_bp.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        user_message = data.get('user_message', '')
        ai_response = data.get('ai_response', '')
        score = data.get('score', 0)
        comment = data.get('comment', '')
        session_id = session.get('session_id', 'unknown')
        username = session.get('username', 'guest')
        
        logger.info(f"[Feedback] 受信: score={score}, comment={comment[:20]}..., user={username}, session={session_id}")

        with sv.get_db_connection(sv.DATABASE) as conn:
            conn.execute('''
                INSERT INTO learning_logs 
                (session_id, user_message, ai_response, feedback_score, feedback_comment) 
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, user_message, ai_response, score, comment))
            conn.commit()
        
        if score == 0 and comment:
            subject = f"【Team RA】フィードバック報告（低評価） from {username}"
            body = f"""
以下のフィードバックが届きました。
■ユーザー: {username}
■評価: 低評価 (Bad)
■コメント: {comment}
■会話内容:
[ユーザー]: {user_message}
[AI]: {ai_response}
---
Session ID: {session_id}
"""
            if sv.send_email_notification(subject, body):
                logger.info("[Feedback] メール通知送信完了")
            else:
                logger.warning("[Feedback] メール通知送信失敗")

        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Feedback Error: {e}")
        return jsonify({"error": str(e)}), 500

# ... (既存のコード) ...

# ★変更: 履歴取得API (クリア済みを除外するロジックを追加)
@concierge_bp.route('/get_user_history', methods=['GET'])
def get_user_history():
    try:
        username = session.get('username')
        if not username:
            return jsonify([])

        with sv.get_db_connection(sv.DATABASE) as conn:
            cursor = conn.cursor()
            
            # 1. このユーザーがどこまで履歴をクリアしたか確認
            cursor.execute("SELECT last_cleared_id FROM history_clears WHERE username = ?", (username,))
            row = cursor.fetchone()
            last_cleared_id = row['last_cleared_id'] if row else 0

            # 2. クリア済みIDより大きい（新しい）メッセージだけを取得
            cursor.execute("""
                SELECT sender, message 
                FROM messages 
                WHERE username = ? AND id > ?
                ORDER BY id DESC 
                LIMIT 100
            """, (username, last_cleared_id))
            rows = cursor.fetchall()

        # メッセージを解析して Q&A のペアを作る
        qa_pairs = []
        current_ai_msg = None

        for row in rows:
            sender = row['sender']
            message = row['message']

            if sender == 'ai':
                current_ai_msg = message
            elif sender == 'user':
                if current_ai_msg:
                    qa_pairs.append({
                        'question': message,
                        'answer': current_ai_msg
                    })
                    current_ai_msg = None 

        return jsonify(qa_pairs)

    except Exception as e:
        logger.error(f"History Error: {e}")
        return jsonify([])

# ★追加: 履歴クリアAPI
@concierge_bp.route('/clear_user_history', methods=['POST'])
def clear_user_history():
    try:
        username = session.get('username')
        if not username:
            return jsonify({"error": "Unauthorized"}), 401

        with sv.get_db_connection(sv.DATABASE) as conn:
            cursor = conn.cursor()
            
            # 現在の最新メッセージIDを取得
            cursor.execute("SELECT MAX(id) as max_id FROM messages WHERE username = ?", (username,))
            row = cursor.fetchone()
            max_id = row['max_id'] if row and row['max_id'] else 0
            
            # 履歴クリアテーブルを更新 (Upsert: なければ挿入、あれば更新)
            # SQLiteの `INSERT OR REPLACE` を使用
            cursor.execute("""
                INSERT OR REPLACE INTO history_clears (username, last_cleared_id)
                VALUES (?, ?)
            """, (username, max_id))
            
            conn.commit()
            
        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"Clear History Error: {e}")
        return jsonify({"error": str(e)}), 500