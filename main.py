"""
Team RA - S2ST (Live API) & Flask Hybrid Server
ターン完了ごとにセッションをリセット＋履歴を要約して文脈を維持する最適化版
"""

import asyncio
import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.wsgi import WSGIMiddleware
from google import genai
from google.genai import types

# 既存のFlaskアプリとサービスをインポート
from app import app as flask_app
import services as sv

# ロギング設定
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("team-ra-live")

fastapi_app = FastAPI()

# --- 設定 ---
API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025" 
RECENT_N = 5   # system_instruction に埋め込む直近往復数

# 固定のペルソナ設定
BASE_PERSONA = """
あなたは、フォーデイズ(Fordays)のビジネス会員のグループ「Team RA」のリーダーであり、トップランカーの思考を持つ「AIビジネスメンター」です。フォーデイズ(Fordays)の「社員」や「広報」ではありません。
ユーザーの話を親身に聞き、温かく応援する口調で話してください。
会話のキャッチボールを意識して簡潔に答えてください。
アスタリスク(*)やマークダウンは音声では読まれないので使用しないでください。
"""

# --- 履歴要約ユーティリティ ---
async def summarize_history(client, history: list[dict]) -> str:
    """直近より古い履歴を Gemini で1〜2文に要約する"""
    if not history:
        return ""
    lines = "\n".join(
        f"{'ユーザー' if e['role']=='user' else 'AI'}: {e['text']}"
        for e in history
    )
    prompt = (
        "以下の会話履歴を、AIが文脈を把握するための要約として日本語で1〜2文にまとめてください。"
        "固有名詞・重要なトピックを残してください。\n\n" + lines
    )
    try:
        # 要約には通常の generate_content を使用
        resp = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return resp.text.strip()
    except Exception as e:
        log.warning(f"履歴の要約に失敗しました: {e}")
        return ""

def build_dynamic_instruction(summary: str, recent: list[dict]) -> str:
    """動的な system_instruction を組み立てる"""
    parts = [BASE_PERSONA]

    if summary:
        parts.append(f"\n【これまでの会話の要約】\n{summary}")

    if recent:
        lines = "\n".join(
            f"{'ユーザー' if e['role']=='user' else 'AI'}: {e['text']}"
            for e in recent
        )
        parts.append(f"\n【直近のやり取り】\n{lines}")

    if summary or recent:
        parts.append("\n上記の文脈を踏まえて、自然に会話を続けてください。")

    return "\n".join(parts)

# --- RAGツール定義 ---
search_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_fordays_info",
            description="フォーデイズのビジネス情報や用語について、ユーザーの質問に関連する情報をデータベースとWebから検索します。",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "query": types.Schema(type="STRING", description="検索するキーワードや質問内容")
                },
                required=["query"]
            )
        )
    ]
)

@fastapi_app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    username = websocket.query_params.get("username", "guest")
    session_id = websocket.query_params.get("session_id", "live_session")
    voice_name = websocket.query_params.get("voice", "Aoede")
    
    log.info(f"=== S2ST Session Start [{session_id}] User: {username}, Voice: {voice_name} ===")

    # セッション内の全履歴を保持するリスト
    full_history: list[dict] = []
    _buf = {"user": "", "ai": ""}

    if not API_KEY:
        await websocket.send_text("ERROR: API_KEY missing")
        await websocket.close()
        return

    client = genai.Client(api_key=API_KEY)

    # ─── メインループ（ターン完了ごとにセッションを張り直す）──
    try:
        while True:
            # 直近の履歴と古い履歴の分離
            recent = full_history[-(RECENT_N * 2):]
            older = full_history[:-(RECENT_N * 2)] if len(full_history) > RECENT_N * 2 else []
            
            # 要約の生成
            summary = await summarize_history(client, older) if older else ""
            
            # 命令文の組み立て
            current_instruction = build_dynamic_instruction(summary, recent)
            
            # コンフィグの作成（毎回最新の命令文を注入）
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
                system_instruction=types.Content(
                    parts=[types.Part.from_text(text=current_instruction)],
                ),
                tools=[search_tool],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                    )
                )
            )

            # Gemini Live セッション確立
            async with client.aio.live.connect(model=MODEL, config=config) as session:
                log.info(f"✅ Gemini Session Established (History: {len(full_history)} items)")

                turn_done = asyncio.Event()
                ws_closed = asyncio.Event()

                async def browser_to_gemini():
                    try:
                        while not turn_done.is_set():
                            try:
                                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=1.0)
                                await session.send(
                                    input=types.LiveClientRealtimeInput(
                                        media_chunks=[types.Blob(data=data, mime_type="audio/pcm;rate=16000")]
                                    )
                                )
                            except asyncio.TimeoutError:
                                continue
                    except WebSocketDisconnect:
                        ws_closed.set()
                        turn_done.set()
                    except Exception as e:
                        log.error(f"[browser_to_gemini] {e}")
                        turn_done.set()

                async def gemini_to_browser():
                    try:
                        async for response in session.receive():
                            # 1. 音声/テキストデータの転送
                            sc = response.server_content
                            if sc:
                                if sc.model_turn:
                                    for part in sc.model_turn.parts:
                                        if part.inline_data and part.inline_data.data:
                                            await websocket.send_bytes(part.inline_data.data)

                                if sc.input_transcription and sc.input_transcription.text:
                                    txt = sc.input_transcription.text
                                    _buf["user"] += txt
                                    await websocket.send_text(f"USER:{txt}")

                                if sc.output_transcription and sc.output_transcription.text:
                                    txt = sc.output_transcription.text
                                    _buf["ai"] += txt
                                    await websocket.send_text(f"AI:{txt}")

                                # ターン完了時の処理
                                if getattr(sc, 'turn_complete', False):
                                    # 履歴に保存
                                    u_text = _buf["user"].strip()
                                    a_text = _buf["ai"].strip()
                                    if u_text: full_history.append({"role": "user", "text": u_text})
                                    if a_text: full_history.append({"role": "ai", "text": a_text})
                                    
                                    # SQLite DBにも保存 (既存の履歴画面用)
                                    if u_text or a_text:
                                        try:
                                            with sv.get_db_connection(sv.DATABASE) as conn:
                                                if u_text:
                                                    conn.execute("INSERT INTO messages (sender, message, session_id, username) VALUES (?, ?, ?, ?)", ("user", u_text, session_id, username))
                                                if a_text:
                                                    conn.execute("INSERT INTO messages (sender, message, session_id, username) VALUES (?, ?, ?, ?)", ("ai", a_text, session_id, username))
                                                conn.commit()
                                        except: pass

                                    # バッファクリア
                                    _buf["user"] = ""
                                    _buf["ai"] = ""
                                    
                                    log.info("✔️ Turn Complete - Triggering Session Reset")
                                    await websocket.send_text("TURN_COMPLETE")
                                    turn_done.set() # ループを抜けてセッションを張り直す

                                if getattr(sc, 'interrupted', False):
                                    _buf["user"] = ""
                                    _buf["ai"] = ""

                            # 2. RAGツールの処理 (Tool Call)
                            if getattr(response, "tool_call", None):
                                function_responses = []
                                for fc in response.tool_call.function_calls:
                                    if fc.name == "search_fordays_info":
                                        query = fc.args.get("query", "")
                                        log.info(f"🔍 Tool Search: {query}")
                                        res = await asyncio.to_thread(sv.perform_comprehensive_search, query)
                                        
                                        texts = []
                                        if isinstance(res, dict):
                                            if res.get("db"): texts.extend(res["db"])
                                            if res.get("web"): texts.append(res["web"])
                                        
                                        result_str = "\n\n".join(texts) if texts else "情報なし。一般的知識で回答。"
                                        function_responses.append(types.FunctionResponse(name=fc.name, id=fc.id, response={"result": result_str}))
                                
                                if function_responses:
                                    await session.send(input=types.LiveClientToolResponse(function_responses=function_responses))
                                    
                    except WebSocketDisconnect:
                        ws_closed.set()
                        turn_done.set()
                    except Exception as e:
                        log.error(f"[gemini_to_browser] {e}")
                        turn_done.set()

                await asyncio.gather(browser_to_gemini(), gemini_to_browser())

            if ws_closed.is_set():
                break
            
            log.info("🔄 Re-connecting to Gemini Live with updated context...")

    except Exception as e:
        log.error(f"WebSocket Loop Error: {e}\n{traceback.format_exc()}")
    finally:
        log.info(f"=== S2ST Session End [{session_id}] ===")

# Flaskマウント
fastapi_app.mount("/", WSGIMiddleware(flask_app))