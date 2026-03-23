from flask import Blueprint, request, jsonify
import os
import logging
import services as sv
import backup_service as backup

logger = logging.getLogger(__name__)

seminar_bp = Blueprint('seminar', __name__)

@seminar_bp.route('/get_seminar_list', methods=['GET'])
def get_seminar_list():
    if not os.path.exists(sv.KNOWLEDGE_DB): 
        return jsonify([])
    try:
        with sv.get_db_connection(sv.KNOWLEDGE_DB) as conn:
            cursor = conn.cursor()
            # ★修正: seminar_doc_name を追加で取得
            cursor.execute("""
                SELECT 
                    id, 
                    topic_title, 
                    avatar_url,
                    pdf_file_url AS textbook_path,
                    page AS textbook_page,
                    seminar_doc_name
                FROM knowledge 
                WHERE transcript IS NOT NULL AND transcript != ''
                ORDER BY original_no
            """)
            results = [dict(row) for row in cursor.fetchall()]
            logger.info(f"セミナーリスト取得: {len(results)}件")
            return jsonify(results)
    except Exception as e:
        logger.error(f"Seminar List Error: {e}", exc_info=True)
        return jsonify({"error": "Error"}), 500

@seminar_bp.route('/start_seminar', methods=['POST'])
def start_seminar():
    try:
        sid = request.json.get('id')
        if not sid: 
            return jsonify({"error": "No ID"}), 400

        logger.info(f"セミナー開始リクエスト: ID={sid}")

        with sv.get_db_connection(sv.KNOWLEDGE_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    topic_title, 
                    transcript, 
                    avatar_url, 
                    ai_lecture_audio_url,
                    ai_script
                FROM knowledge 
                WHERE id = ?
            """, (sid,))
            row = cursor.fetchone()
            
            if not row: 
                return jsonify({"error": "Not Found"}), 404
            
            data = dict(row)
            audio_url = data.get('ai_lecture_audio_url')
            saved_script = data.get('ai_script')
            
            # --- キャッシュがある場合 ---
            if audio_url and saved_script and os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), audio_url.lstrip('/'))):
                logger.info(f"キャッシュ音声使用: {audio_url}")
                return jsonify({
                    'audio_url': audio_url, 
                    'topic_title': data['topic_title'], 
                    'avatar_url': data['avatar_url'],
                    'transcript_text': saved_script
                })

            # --- 新規生成の場合 ---
            if not sv.model: 
                return jsonify({"error": "AI Model Error"}), 500
            
            # アプリ向けに原稿をリライトするプロンプト
            prompt = f"""
# 命令書
あなたは、ビジネス学習アプリ「Team RA」の**「専属AI講師」**です。
以下の「元原稿」の内容を基に、アプリで学習しているユーザーに向けた、分かりやすく魅力的な「音声講義用の原稿」を新規に作成してください。

# シチュエーション設定
- ユーザーはアプリを通じて、オンラインであなたの講義を聴いています。
- **重要:** ユーザーは手元に「教材テキスト」を持っています。「お手元のテキストをご覧ください」「テキストの図表にあるように」などの表現を自然に交えて解説してください。
- 元原稿にあるリアルの会場に向けた言葉は、アプリ向けに修正するか削除してください。

# 原稿の構成指示
1. **導入**: 「こんにちは、Team RA専属AI講師です。」と名乗り、今回のテーマ「{data['topic_title']}」を紹介してください。
2. **本編**: 元原稿の要点を、語りかけるような口調で解説。
3. **結び**: 学習への励まし。

# 元原稿
{data['transcript']}

# 制約事項
- 出力は「AIが読み上げるためのテキスト」のみを行ってください。
- **「〇〇」や「（※名前が入ります）」のような伏せ字や注釈は絶対に出力しないでください。**
- 全体を3分〜5分程度で聴ける長さに要約・構成してください。
"""
            
            full_text = ""
            try:
                logger.info("AI講義スクリプト生成開始...")
                full_text = sv.model.generate_content(prompt).text.strip()
                logger.info(f"AI講義スクリプト生成完了: {len(full_text)}文字")
            except Exception as e:
                logger.warning(f"講義スクリプト生成失敗: {e}")
                full_text = f"こんにちは、Team RA専属AI講師です。今回は「{data['topic_title']}」について解説します。\n\n{data['transcript']}"
            
            new_audio_url = sv.generate_speech_audio(full_text)
            
            if new_audio_url:
                cursor.execute(
                    "UPDATE knowledge SET ai_lecture_audio_url = ?, ai_script = ? WHERE id = ?", 
                    (new_audio_url, full_text, sid)
                )
                conn.commit()
                
                logger.info("変更を検知: バックアップを開始します...")
                backup.upload_db_background(sv.KNOWLEDGE_DB, 'chat_knowledge.db')
                
                return jsonify({
                    'audio_url': new_audio_url, 
                    'topic_title': data['topic_title'], 
                    'avatar_url': data['avatar_url'],
                    'transcript_text': full_text 
                })
            else:
                return jsonify({"error": "Audio Gen Error"}), 500
                
    except Exception as e:
        logger.exception("Start Seminar Error")
        return jsonify({"error": "Error"}), 500