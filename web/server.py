# web/server.py
"""FastAPI web server for my-agent: chat UI + debug UI via WebSocket."""
import logging
import os
from pathlib import Path

from agent.config import MyAgentConfig
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.debug_hook import debug_enabled
from web.session import SessionManager

logger = logging.getLogger("myagent.web.server")

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    llm,
    mode: str | None = None,
    config: MyAgentConfig | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    config = config or MyAgentConfig()
    resolved_mode = mode or config.agent.default_mode.value
    app = FastAPI(title="MyAgent Web UI", version="0.1.0")
    session_manager = SessionManager(
        debug_enabled=debug_enabled(),
        mode=resolved_mode,
        config=config,
    )

    # Mount static files at /static
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def chat_page():
        html_path = STATIC_DIR / "index.html"
        if not html_path.exists():
            return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/debug", response_class=HTMLResponse)
    async def debug_page():
        if not debug_enabled():
            return JSONResponse({"error": "Debug mode disabled"}, status_code=404)
        html_path = STATIC_DIR / "index.html"
        if not html_path.exists():
            return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/api/debug-status")
    async def debug_status():
        return {"enabled": debug_enabled()}

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(ws: WebSocket, session_id: str):
        await ws.accept()

        session = session_manager.get_session(session_id)
        if not session:
            session = session_manager.create_session(llm)
            await ws.send_json({
                "type": "session_created",
                "session_id": session.session_id,
                "mode": session.agent.run_config.mode.value,
            })

        elif session.session_id != session_id:
            session = session_manager.get_session(session.session_id)

        try:
            while True:
                raw = await ws.receive_json()
                msg_type = raw.get("type")

                if msg_type == "chat":
                    user_text = raw.get("content", "").strip()
                    if not user_text:
                        continue

                    await session_manager.run_session(
                        session, user_text,
                        ws_send=lambda e: ws.send_json(e),
                    )

                elif msg_type == "reset":
                    session_manager.remove_session(session.session_id)
                    session = session_manager.create_session(llm)
                    await ws.send_json({
                        "type": "session_created",
                        "session_id": session.session_id,
                        "mode": session.agent.run_config.mode.value,
                    })

                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {session_id}")

    return app
