from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, make_response
from functools import wraps
import os
import logging
import json
import re
import services as sv
import backup_service as backup
import csv
import io

logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__)

# --- 認証設定 ---
ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user = session.get('username')
        if not current_user or current_user != ADMIN_USER:
            logger.warning(f"管理者ページへのアクセス拒否: user={current_user}")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# --- 管理画面ルート ---

@admin_bp.route('/admin')
@requires_auth
def admin_index():
    return render_template('admin.html')

@admin_bp.route('/admin/chat', methods=['POST'])
@requires_auth
def admin_chat():
    try:
        user_message = request.json.get('message')
        if not user_message:
            return jsonify({"response": "メッセージを入力してください。"}), 400

        # --- 履歴の管理 ---
        if 'admin_history' not in session:
            session['admin_history'] = []
        
        history_list = session['admin_history'][-10:] 
        history_text = "\n".join(history_list)

        # --- セミナーリスト取得 ---
        seminars = sv.get_all_seminars_status()
        seminar_list_txt = "\n".join([f"ID:{s['id']} タイトル:{s['topic_title']}" for s in seminars])

        # --- AIへの命令書 ---
        prompt = f"""
        # あなたの役割
        あなたはシステム管理者AIです。ユーザー（管理者）の指示に従い、適切な操作を行ってください。
        
        # 重要な指示
        あなたは「会話の文脈」を理解できます。
        ユーザーが「ID:2」や「それでお願いします」と短く答えた場合、**直近の会話履歴**を確認し、何に対する返答かを推測してコマンドを実行してください。

        # 現在のセミナーリスト
        {seminar_list_txt}

        # 直近の会話履歴 (文脈)
        {history_text}

        # ユーザーの現在の発言
        {user_message}

        # 指示の分類と出力形式 (必ずJSONのみを出力すること)
        ユーザーの意図を判断し、対応するJSONを出力してください。
        JSON以外の解説文は一切不要です。

        パターンA: セミナーのリセット・削除・再生成
        - 「リセット」「再生成」「削除」「修正」などの意図がある場合。
        - 出力: {{ "command": "RESET_SEMINAR", "target_id": (ID番号), "target_title": "(タイトル名)" }}
        - 該当するセミナーが見つからない場合: {{ "command": "CHAT", "response": "該当するセミナーが見つかりませんでした。タイトルを確認してください。" }}

        パターンB: ユーザー管理画面の表示
        - 「ユーザー管理」「会員登録」「CSV」などのキーワードがある場合。
        - 出力: {{ "command": "SHOW_USER_PANEL", "response": "ユーザー管理パネルを表示します。" }}
        
        パターンC: 知識データの管理・CSV出力
        - 「知識データ」「ナレッジ」「CSVダウンロード」「エクスポート」などのキーワードがある場合。
        - 出力: {{ "command": "SHOW_KNOWLEDGE_PANEL", "response": "知識データベース管理パネルを表示します。" }}

        パターンD: その他（挨拶、質問、雑談、IDの確認など）
        - 出力: {{ "command": "CHAT", "response": "(あなたの返答)" }}
        """

        ai_resp = sv._call_gemini_with_retry(prompt)
        if not ai_resp or not ai_resp.text:
            return jsonify({"response": "AIの応答がありませんでした。"}), 500

        result_text = ai_resp.text.strip()
        result_text = re.sub(r'^```json\s*', '', result_text, flags=re.MULTILINE)
        result_text = re.sub(r'\s*```$', '', result_text, flags=re.MULTILINE)
        
        intent = {}
        try:
            intent = json.loads(result_text)
        except json.JSONDecodeError:
            intent = {"command": "CHAT", "response": result_text}

        command = intent.get("command")
        final_response = ""
        action_code = "NONE"

        if command == "RESET_SEMINAR":
            target_id = intent.get("target_id")
            target_title = intent.get("target_title")
            if target_id:
                success, msg = sv.reset_seminar_data(target_id)
                if success:
                    backup.upload_db_background(sv.KNOWLEDGE_DB, 'chat_knowledge.db')
                    final_response = f"セミナー「{target_title} (ID:{target_id})」をリセットしました。\n次回アクセス時に再生成されます。"
                else:
                    final_response = f"エラー: リセットに失敗しました。\n{msg}"
            else:
                final_response = "セミナーIDを特定できませんでした。"

        elif command == "SHOW_USER_PANEL":
            final_response = intent.get("response")
            action_code = "SHOW_USER_PANEL"
        
        elif command == "SHOW_KNOWLEDGE_PANEL":
            final_response = intent.get("response")
            action_code = "SHOW_KNOWLEDGE_PANEL"

        else:
            final_response = intent.get("response", "承知いたしました。")

        session['admin_history'].append(f"User: {user_message}")
        session['admin_history'].append(f"AI: {final_response}")
        session.modified = True

        return jsonify({"response": final_response, "action": action_code})

    except Exception as e:
        logger.error(f"Admin Chat Error: {e}")
        return jsonify({"response": "システムエラーが発生しました。"}), 500


# --- ユーザー管理API ---

@admin_bp.route('/admin/users', methods=['GET'])
@requires_auth
def list_users():
    users = sv.get_all_users()
    return jsonify(users)

@admin_bp.route('/admin/users/add', methods=['POST'])
@requires_auth
def api_add_user():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    info = data.get('info', '')
    if not username or not password:
        return jsonify({"status": "error", "message": "IDとパスワードが必要です"}), 400
    
    success, msg = sv.add_user(username, password, info)
    if success:
        return jsonify({"status": "success", "message": msg})
    else:
        return jsonify({"status": "error", "message": msg}), 400

@admin_bp.route('/admin/users/update', methods=['POST'])
@requires_auth
def api_update_user():
    data = request.json
    username = data.get('username')
    password = data.get('password') 
    info = data.get('info')         
    
    if not username:
        return jsonify({"status": "error", "message": "IDが必要です"}), 400
    
    success, msg = sv.update_user(username, password, info)
    if success:
        return jsonify({"status": "success", "message": msg})
    else:
        return jsonify({"status": "error", "message": msg}), 400

@admin_bp.route('/admin/users/delete', methods=['POST'])
@requires_auth
def api_delete_user():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({"status": "error", "message": "IDが必要です"}), 400
    
    success, msg = sv.delete_user(username)
    if success:
        return jsonify({"status": "success", "message": msg})
    else:
        return jsonify({"status": "error", "message": msg}), 400

@admin_bp.route('/admin/users/upload_csv', methods=['POST'])
@requires_auth
def api_upload_users_csv():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "ファイルがありません"}), 400
    file = request.files['file']
    try:
        added, updated, skipped_list = sv.import_users_from_csv(file.stream)
        msg = f"登録: {added}件, 更新: {updated}件"
        if skipped_list: msg += f" (スキップ: {len(skipped_list)}件)"
        return jsonify({"status": "success", "message": msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/users/export_csv', methods=['GET'])
@requires_auth
def api_export_users_csv():
    users = sv.get_all_users()
    si = io.StringIO()
    cw = csv.writer(si)
    for u in users:
        cw.writerow([u['username'], '', u['info'] or ''])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=users_export.csv"
    # ★変更: 強制ダウンロードのため octet-stream に変更
    output.headers["Content-type"] = "application/octet-stream"
    return output

# --- セミナー管理API ---

@admin_bp.route('/admin/seminars', methods=['GET'])
@requires_auth
def list_seminars():
    seminars = sv.get_all_seminars_status()
    return jsonify(seminars)

@admin_bp.route('/admin/seminars/reset', methods=['POST'])
@requires_auth
def api_reset_seminar():
    data = request.json
    seminar_id = data.get('id')
    if not seminar_id:
        return jsonify({"status": "error", "message": "IDが必要です"}), 400
    
    success, msg = sv.reset_seminar_data(seminar_id)
    if success:
        backup.upload_db_background(sv.KNOWLEDGE_DB, 'chat_knowledge.db')
        return jsonify({"status": "success", "message": msg})
    else:
        return jsonify({"status": "error", "message": msg}), 400

# --- 知識DBのCSVエクスポート ---
@admin_bp.route('/admin/knowledge/export_csv', methods=['GET'])
@requires_auth
def api_export_knowledge_csv():
    headers, rows = sv.get_all_knowledge_data()
    si = io.StringIO()
    cw = csv.writer(si)
    
    cw.writerow(headers)
    for row in rows:
        cw.writerow([x if x is not None else "" for x in row])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=knowledge_export.csv"
    # ★変更: 強制ダウンロードのため octet-stream に変更
    output.headers["Content-type"] = "application/octet-stream"
    return output