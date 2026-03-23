"""
Team RA - S2ST (Live API) & Flask Hybrid Server
"""

import asyncio
import logging
import os
import traceback
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.wsgi import WSGIMiddleware
from google import genai
from google.genai import types

# 既存のFlaskアプリとサービスをインポート
from app import app as flask_app
import services as sv

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("team-ra-live")

fastapi_app = FastAPI()

API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025" 

persona = """
あなたは、フォーデイズ(Fordays)のビジネス会員のグループ「Team RA」のリーダーであり、トップランカーの思考を持つ「AIビジネスメンター」です。フォーデイズ(Fordays)の「社員」や「広報」ではありません。
ユーザーの話を親身に聞き、温かく応援する口調で話してください。
長すぎる回答は避け、会話のキャッチボールを意識して簡潔に答えてください。
アスタリスク(*)やマークダウンは音声では読まれないので使用しないでください。
"""

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

# ★重要: FastAPI側で @fastapi_app.get("/") を定義してはいけません。
# 定義すると Flask 側のログインチェックや index() 処理がスキップされてしまいます。

@fastapi_app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    username = websocket.query_params.get("username", "guest")
    session_id = websocket.query_params.get("session_id", "live_session")
    voice_name = websocket.query_params.get("voice", "Aoede")
    
    log.info(f"=== S2ST Session Start [{session_id}] User: {username}, Voice: {voice_name} ===")

    _buf = {"user": "", "ai": "", "user_time": "", "ai_time": ""}

    def flush(role: str) -> None:
        text = _buf[role].strip()
        if not text:
            return
        
        try:
            with sv.get_db_connection(sv.DATABASE) as conn:
                conn.execute(
                    "INSERT INTO messages (sender, message, session_id, username) VALUES (?, ?, ?, ?)",
                    (role, text, session_id, username)
                )
                conn.commit()
        except Exception as e:
            log.error(f"DB保存エラー: {e}")
            
        icon = "👤" if role == "user" else "🤖"
        log.info(f"{icon} {text}")
        _buf[role] = ""
        _buf[f"{role}_time"] = ""

    if not API_KEY:
        await websocket.send_text("ERROR: GEMINI_API_KEY が設定されていません")
        await websocket.close()
        return

    client = genai.Client(api_key=API_KEY)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=persona)],
        ),
        tools=[search_tool],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name
                )
            )
        )
    )

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            log.info("✅ Gemini セッション確立")

            async def browser_to_gemini():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await session.send(
                            input=types.LiveClientRealtimeInput(
                                media_chunks=[types.Blob(data=data, mime_type="audio/pcm;rate=16000")]
                            )
                        )
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    log.error(f"[browser_to_gemini] {e}")

            async def gemini_to_browser():
                try:
                    while True:
                        async for response in session.receive():
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

                                if getattr(sc, 'turn_complete', False):
                                    flush("user")
                                    flush("ai")
                                    await websocket.send_text("TURN_COMPLETE")

                                if getattr(sc, 'interrupted', False):
                                    flush("user")
                                    flush("ai")

                            if getattr(response, "tool_call", None):
                                function_responses =[]
                                for fc in response.tool_call.function_calls:
                                    if fc.name == "search_fordays_info":
                                        query = fc.args.get("query", "")
                                        log.info(f"🔍 ツール検索実行: {query}")
                                        
                                        res = await asyncio.to_thread(sv.perform_comprehensive_search, query)
                                        
                                        texts =[]
                                        if isinstance(res, dict):
                                            if res.get("db"): texts.extend(res["db"])
                                            if res.get("web"): texts.append(res["web"])
                                        elif isinstance(res, list):
                                            for ref in res:
                                                texts.append(f"テーマ:{ref.get('topic_title','')}\n{ref.get('transcript','')}")
                                                
                                        result_str = "\n\n".join(texts) if texts else "情報が見つかりませんでした。一般的な知識で回答してください。"
                                        
                                        function_responses.append(
                                            types.FunctionResponse(
                                                name=fc.name,
                                                id=fc.id,
                                                response={"result": result_str}
                                            )
                                        )
                                
                                if function_responses:
                                    await session.send(
                                        input=types.LiveClientToolResponse(function_responses=function_responses)
                                    )
                                    
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    log.error(f"[gemini_to_browser] {e}")

            await asyncio.gather(browser_to_gemini(), gemini_to_browser())

    except Exception as e:
        log.error(f"Live API 接続エラー: {e}\n{traceback.format_exc()}")
    finally:
        flush("user")
        flush("ai")
        log.info(f"=== S2ST Session End [{session_id}] ===")

# 全てのリクエストを Flask アプリに転送
fastapi_app.mount("/", WSGIMiddleware(flask_app))