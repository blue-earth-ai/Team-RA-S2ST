from flask import Blueprint, jsonify
import os
import logging
import services as sv

logger = logging.getLogger(__name__)

search_bp = Blueprint('search', __name__)

@search_bp.route('/get_knowledge_data', methods=['GET'])
def get_knowledge_data():
    if not os.path.exists(sv.KNOWLEDGE_DB): 
        return jsonify([])
    try:
        with sv.get_db_connection(sv.KNOWLEDGE_DB) as conn:
            cursor = conn.cursor()
            # ★修正: avatar_url の取得を削除
            cursor.execute("""
                SELECT 
                    topic_title, 
                    lecture_audio_url, 
                    pdf_file_url 
                FROM knowledge 
                ORDER BY original_no
            """)
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                item['has_pdf'] = bool(item.get('pdf_file_url') and item['pdf_file_url'].strip())
                item['has_audio'] = bool(item.get('lecture_audio_url') and item['lecture_audio_url'].strip())
                # ★注意: avatar_url はDBから取得しないため、この辞書には含まれません
                results.append(item)
            
            logger.info(f"資料検索データ取得: {len(results)}件")
            return jsonify(results)
            
    except Exception as e:
        logger.error(f"Search Data Error: {e}", exc_info=True)
        return jsonify({"error": "Error"}), 500