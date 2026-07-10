# web/server.py
"""FastAPI web server for asterwynd: chat UI + debug UI via WebSocket."""
import base64
import binascii
import logging
import os
from pathlib import Path

from agent.commands import CommandContext, build_default_slash_command_registry
from agent.config import AsterwyndConfig
from agent.skills import SkillRuntime
from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.debug_hook import debug_enabled
from web.session import SessionManager

logger = logging.getLogger("asterwynd.web.server")

STATIC_DIR = Path(__file__).parent / "static"
BRAND_ASSETS_DIR = Path(__file__).parent.parent / "docs" / "assets"


def create_app(
    llm,
    mode: str | None = None,
    config: AsterwyndConfig | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    config = config or AsterwyndConfig()
    resolved_mode = mode or config.agent.default_mode.value
    app = FastAPI(title="Asterwynd · Asterwynd Web UI", version="0.1.0")
    session_manager = SessionManager(
        debug_enabled=debug_enabled(),
        mode=resolved_mode,
        config=config,
    )

    # Mount static files at /static
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if BRAND_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(BRAND_ASSETS_DIR)), name="assets")

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

    @app.get("/api/slash-commands")
    async def slash_commands():
        command_registry = build_default_slash_command_registry(
            SkillRuntime.from_roots(config.skills.roots)
        )
        return {"commands": command_registry.catalog()}

    @app.post("/api/upload-image")
    async def upload_image(request: dict):
        """接收 base64 图片，写入 .asterwynd/uploads/，返回 file_path 和 data_url"""
        from agent.uploads import create_image_message, MAX_UPLOAD_SIZE
        data_url = request.get("data_url", "")
        if not data_url:
            return JSONResponse({"error": "missing data_url"}, status_code=400)
        if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
            return JSONResponse({"error": "invalid data_url"}, status_code=400)
        if len(data_url) > MAX_UPLOAD_SIZE * 2:
            return JSONResponse({"error": "data_url too large"}, status_code=400)
        try:
            image_block = create_image_message(data_url)
            return {
                "file_path": image_block.file_path,
                "url": image_block.image_url.url,
            }
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception as e:
            logger.exception("Upload failed")
            return JSONResponse({"error": "internal error"}, status_code=500)

    @app.post("/api/uploads")
    async def upload_file(file: UploadFile):
        """接收 multipart 图片上传，写入 .asterwynd/uploads/，返回 upload_id。"""
        from agent.uploads import MAX_UPLOAD_SIZE, save_upload_bytes

        mime = (file.content_type or "").lower()
        if not mime.startswith("image/"):
            return JSONResponse({"error": "invalid image type"}, status_code=400)
        try:
            data = await file.read(MAX_UPLOAD_SIZE + 1)
            if len(data) > MAX_UPLOAD_SIZE:
                return JSONResponse({"error": "image too large"}, status_code=400)
            file_path = save_upload_bytes(data, mime)
            return {
                "upload_id": Path(file_path).name,
                "file_path": file_path,
                "mime": mime,
                "size": len(data),
            }
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception:
            logger.exception("Upload failed")
            return JSONResponse({"error": "internal error"}, status_code=500)

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(ws: WebSocket, session_id: str):
        await ws.accept()
        upload_buffers: dict[str, dict] = {}

        session = session_manager.get_session(session_id)
        if not session:
            session = await session_manager.create_session_async(llm)
            await ws.send_json({
                "type": "session_created",
                "session_id": session.session_id,
                "mode": session.current_mode,
            })

        elif session.session_id != session_id:
            session = session_manager.get_session(session.session_id)

        try:
            while True:
                raw = await ws.receive_json()
                msg_type = raw.get("type")

                if msg_type == "chat":
                    user_text = raw.get("content", "").strip()
                    images = raw.get("images") or []
                    if not user_text and not images:
                        continue

                    command_context = CommandContext(
                        agent=session.agent,
                        messages=session.messages,
                        session_id=session.session_id,
                        provider=llm.__class__.__name__,
                        model=str(getattr(llm, "model", "default")),
                    )
                    command_registry = build_default_slash_command_registry(
                        getattr(session.agent, "skill_runtime", None)
                    )
                    command_result = await command_registry.try_execute(
                        user_text,
                        command_context,
                    )
                    if command_result is not None:
                        await ws.send_json({
                            "type": "command_result",
                            "data": {
                                "message": command_result.message,
                                "metadata": command_result.metadata,
                                "continue_session": command_result.continue_session,
                            },
                        })
                        if command_result.metadata.get("run_agent"):
                            skill_runtime = getattr(session.agent, "skill_runtime", None)
                            skill_name = command_result.metadata.get("skill_name")
                            if skill_runtime is not None and skill_name:
                                skill_runtime.queue_activation(
                                    str(skill_name),
                                    source=str(
                                        command_result.metadata.get(
                                            "activation_source",
                                            "slash_command",
                                        )
                                    ),
                                )
                            agent_input = str(
                                command_result.metadata.get("agent_input") or ""
                            ).strip()
                            if not agent_input:
                                agent_input = user_text
                            await session_manager.run_session(
                                session,
                                agent_input,
                                ws_send=lambda e: ws.send_json(e),
                                ws_receive=ws.receive_json,
                            )
                            continue
                        await ws.send_json({
                            "type": "done",
                            "data": {
                                "content": command_result.message,
                                "stop_reason": "command",
                            },
                        })
                        if not command_result.continue_session:
                            await ws.close()
                            break
                        continue

                    images = raw.get("images") or []
                    try:
                        await session_manager.run_session(
                            session, user_text,
                            ws_send=lambda e: ws.send_json(e),
                            ws_receive=ws.receive_json,
                            images=images,
                        )
                    except ValueError as exc:
                        await ws.send_json({
                            "type": "error",
                            "data": {"message": f"ValueError: {exc}"},
                        })

                elif msg_type == "image_upload_start":
                    from agent.uploads import MAX_UPLOAD_SIZE

                    client_upload_id = str(raw.get("client_upload_id", "")).strip()
                    mime = str(raw.get("mime", "")).strip().lower()
                    if not client_upload_id:
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "missing client_upload_id"},
                        })
                        continue
                    raw_total_chars = raw.get("total_chars")
                    try:
                        if raw_total_chars is None or isinstance(raw_total_chars, bool):
                            raise ValueError
                        total_chars = int(raw_total_chars)
                    except (TypeError, ValueError):
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "invalid image size"},
                        })
                        continue
                    if total_chars < 0:
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "invalid image size"},
                        })
                        continue
                    if not mime.startswith("image/"):
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "invalid image type"},
                        })
                        continue
                    if total_chars > MAX_UPLOAD_SIZE * 2:
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "image too large"},
                        })
                        continue
                    upload_buffers[client_upload_id] = {
                        "mime": mime,
                        "chunks": [],
                        "received_chars": 0,
                    }
                    await ws.send_json({
                        "type": "image_upload_started",
                        "data": {"client_upload_id": client_upload_id},
                    })

                elif msg_type == "image_upload_chunk":
                    from agent.uploads import MAX_UPLOAD_SIZE

                    client_upload_id = str(raw.get("client_upload_id", "")).strip()
                    chunk = str(raw.get("chunk", ""))
                    upload = upload_buffers.get(client_upload_id)
                    if upload is None:
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "upload not started"},
                        })
                        continue
                    upload["chunks"].append(chunk)
                    upload["received_chars"] += len(chunk)
                    if upload["received_chars"] > MAX_UPLOAD_SIZE * 2:
                        upload_buffers.pop(client_upload_id, None)
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "image too large"},
                        })
                        continue
                    await ws.send_json({
                        "type": "image_upload_chunk_ack",
                        "data": {
                            "client_upload_id": client_upload_id,
                            "index": raw.get("index"),
                        },
                    })

                elif msg_type == "image_upload_finish":
                    from agent.uploads import save_upload_bytes

                    client_upload_id = str(raw.get("client_upload_id", "")).strip()
                    upload = upload_buffers.pop(client_upload_id, None)
                    if upload is None:
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": "upload not started"},
                        })
                        continue
                    try:
                        data = base64.b64decode("".join(upload["chunks"]), validate=True)
                        file_path = save_upload_bytes(data, upload["mime"])
                    except (binascii.Error, ValueError) as exc:
                        await ws.send_json({
                            "type": "image_upload_error",
                            "data": {"client_upload_id": client_upload_id, "message": str(exc)},
                        })
                        continue
                    await ws.send_json({
                        "type": "image_upload_complete",
                        "data": {
                            "client_upload_id": client_upload_id,
                            "upload_id": Path(file_path).name,
                            "file_path": file_path,
                            "mime": upload["mime"],
                            "size": len(data),
                        },
                    })

                elif msg_type == "approval_response":
                    approval_id = str(raw.get("approval_id", "")).strip()
                    decision = str(raw.get("decision", "")).strip()
                    accepted = session.approval_handler.submit_response(
                        approval_id,
                        decision,
                    )
                    await ws.send_json({
                        "type": "approval_response",
                        "data": {
                            "approval_id": approval_id,
                            "status": "received" if accepted else "unavailable",
                            "reason": (
                                "received"
                                if accepted
                                else "no matching pending approval"
                            ),
                            "session_id": session.session_id,
                        },
                    })

                elif msg_type == "reset":
                    session.approval_handler.fail_pending("session reset")
                    session_manager.remove_session(session.session_id)
                    session = await session_manager.create_session_async(llm)
                    await ws.send_json({
                        "type": "session_created",
                        "session_id": session.session_id,
                        "mode": session.current_mode,
                    })

                elif msg_type == "set_mode":
                    requested_mode = str(raw.get("mode", "")).strip()
                    if not requested_mode:
                        await ws.send_json({
                            "type": "error",
                            "data": {"message": "ValueError: mode is required"},
                        })
                        continue
                    try:
                        transition = await session_manager.set_mode(session, requested_mode)
                    except Exception as exc:
                        await ws.send_json({
                            "type": "error",
                            "data": {"message": f"{type(exc).__name__}: {exc}"},
                        })
                        continue
                    await ws.send_json({"type": "mode_changed", "data": transition})

                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {session_id}")

    return app
