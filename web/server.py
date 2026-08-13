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
_INDEX_HTML_CACHE: str | None = None


def _read_index_html() -> str:
    """读取 index.html 内容，带内存缓存避免每次请求读盘。"""
    global _INDEX_HTML_CACHE
    if _INDEX_HTML_CACHE is None:
        html_path = STATIC_DIR / "index.html"
        _INDEX_HTML_CACHE = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    return _INDEX_HTML_CACHE


def create_app(
    llm,
    mode: str | None = None,
    config: AsterwyndConfig | None = None,
    resume: str | None = None,
    workspace_root: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    config = config or AsterwyndConfig()
    resolved_mode = mode or config.agent.default_mode.value
    app = FastAPI(title="Asterwynd · Asterwynd Web UI", version="0.1.0")
    app.state.resume_session_id = resume
    # 有效 workspace 集合（issue #117 D4）：主 workspace + allowlist 中存在路径。
    # allowlist 中不存在或不可解析的路径打 warning 并从有效集合排除。
    primary_workspace = (workspace_root or Path.cwd()).resolve()
    allowed_workspaces: list[Path] = []
    for ws in config.web.workspaces:
        resolved = ws.resolve() if isinstance(ws, Path) else Path(str(ws)).resolve()
        if resolved == primary_workspace:
            continue
        if resolved.exists():
            allowed_workspaces.append(resolved)
        else:
            logger.warning("web.workspaces 路径不存在，已排除: %s", resolved)
    session_manager = SessionManager(
        debug_enabled=debug_enabled(),
        mode=resolved_mode,
        config=config,
        workspace_root=workspace_root,
        allowed_workspaces=allowed_workspaces,
    )
    app.state.session_manager = session_manager

    # Mount static files at /static
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if BRAND_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(BRAND_ASSETS_DIR)), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def chat_page():
        html = _read_index_html()
        if not html:
            return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
        return HTMLResponse(html)

    @app.get("/resume", response_class=HTMLResponse)
    async def resume_page():
        """显式恢复入口：返回 Chat 页面 HTML，前端配合 ``?session=<id>`` 恢复。

        桌面端与移动端共用同一页面（无额外依赖）。
        """
        html = _read_index_html()
        if not html:
            return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
        return HTMLResponse(html)

    @app.get("/debug", response_class=HTMLResponse)
    async def debug_page():
        if not debug_enabled():
            return JSONResponse({"error": "Debug mode disabled"}, status_code=404)
        html = _read_index_html()
        if not html:
            return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
        return HTMLResponse(html)

    @app.get("/api/debug-status")
    async def debug_status():
        return {"enabled": debug_enabled()}

    @app.get("/api/sessions/{session_id}/timeline")
    async def session_timeline(session_id: str):
        """Return a session's tool-call timeline (durations desc + bar widths).

        Gated by debug mode, matching the ``/debug`` view that hosts the
        Timeline panel: tool arguments are execution detail only shown when
        ``ASTERWYND_DEBUG`` is enabled.
        """
        from web.session import build_timeline_payload

        if not debug_enabled():
            return JSONResponse({"error": "Debug mode disabled"}, status_code=404)
        session = session_manager.get_session(session_id)
        if not session:
            return JSONResponse({"error": "session not found"}, status_code=404)
        return build_timeline_payload(session)

    @app.get("/api/slash-commands")
    async def slash_commands():
        command_registry = build_default_slash_command_registry(
            SkillRuntime.from_roots(config.skills.roots)
        )
        return {"commands": command_registry.catalog()}

    @app.get("/api/workspaces")
    async def api_workspaces():
        """Hub workspace 列表（issue #117 D1）：主 workspace 置顶 + allowlist。

        ``exists`` 反映运行期目录状态（集合启动时一次性解析）；``session_count``
        为该 workspace store 下的已保存会话数。
        """
        workspaces = []
        for ws, is_primary in session_manager.list_workspaces():
            try:
                session_count = len(session_manager._store_for(ws).list_sessions())
            except Exception:
                session_count = 0
            workspaces.append({
                "path": str(ws),
                "is_primary": is_primary,
                "exists": ws.exists(),
                "session_count": session_count,
            })
        return {"workspaces": workspaces}

    @app.get("/api/sessions")
    async def api_sessions(workspace: str | None = None):
        """Hub 会话列表：复用 ``SessionStore.list_sessions()`` 元数据。

        缺省 workspace 用主 workspace；workspace 不在有效集合或路径不存在 →
        HTTP 403 + 结构化错误。
        """
        try:
            ws = session_manager.resolve_workspace(workspace)
        except ValueError:
            return JSONResponse({"error": "workspace_not_allowed"}, status_code=403)
        sessions = session_manager._store_for(ws).list_sessions()
        return {"workspace": str(ws), "sessions": sessions}

    @app.delete("/api/sessions/{session_id}")
    async def api_delete_session(session_id: str, workspace: str | None = None):
        """删除会话（issue #117 D1）：内存 + 指定 workspace store 的磁盘快照。

        workspace 必须显式传入（冷会话无内存 workspace_root 可查）；缺省 →
        400；未授权 → 403。畸形 session_id 由 SessionStore._validate_session_id
        拒绝 → 400（design review I4）。
        """
        if not workspace:
            return JSONResponse({"error": "missing_workspace"}, status_code=400)
        try:
            ws = session_manager.resolve_workspace(workspace)
        except ValueError:
            return JSONResponse({"error": "workspace_not_allowed"}, status_code=403)
        try:
            session_manager.remove_session(session_id, workspace=ws)
        except ValueError:
            return JSONResponse({"error": "invalid_session_id"}, status_code=400)
        return {"deleted": True, "session_id": session_id, "workspace": str(ws)}

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
        query = ws.query_params
        requested_mode = str(query.get("mode", "")).strip()
        requested_workspace = str(query.get("workspace", "")).strip()
        # /ws/new 带显式参数（mode 或 workspace）→ 跳过 --resume 拦截直接新建
        # （issue #117 grill R2/Q8）；仅裸 /ws/new 保留 --resume 语义。
        has_explicit_new_params = session_id == "new" and bool(requested_mode or requested_workspace)
        # 恢复路径的 workspace 参数先校验（issue #117 R1/Q7）：非法 → error 后关闭。
        resume_workspace: Path | None = None
        if requested_workspace:
            try:
                resume_workspace = session_manager.resolve_workspace(requested_workspace)
            except ValueError:
                await ws.send_json({"error": "workspace_not_allowed"})
                await ws.close()
                return

        session = session_manager.get_session(session_id)
        if session is None:
            # /ws/new 是默认入口：若 CLI 传了 --resume 且无显式新建参数，则用
            # resume 目标；其他 session id 直接用该 id 尝试恢复。
            resume_target = (
                session_id if session_id != "new" else app.state.resume_session_id
            )
            if has_explicit_new_params:
                resume_target = None
            if resume_target:
                session = await session_manager.resume_session_async(
                    resume_target, llm, workspace=resume_workspace,
                )

        if session is None:
            # 新建：校验 mode / workspace（issue #117 D2）。
            create_mode: str | None = None
            create_workspace: Path | None = None
            if requested_mode:
                try:
                    from agent.run_config import parse_agent_mode
                    parse_agent_mode(requested_mode)
                    create_mode = requested_mode
                except ValueError:
                    await ws.send_json({"error": "invalid_mode"})
                    await ws.close()
                    return
            if requested_workspace:
                create_workspace = resume_workspace
            session = await session_manager.create_session_async(
                llm,
                mode=create_mode,
                workspace_root=create_workspace,
            )
            await ws.send_json({
                "type": "session_created",
                "session_id": session.session_id,
                "mode": session.current_mode,
                "workspace": str(session.workspace_root) if session.workspace_root else None,
            })
        else:
            from web.session import build_history_payload

            await ws.send_json({
                "type": "session_resumed",
                "session_id": session.session_id,
                "mode": session.current_mode,
                "workspace": str(session.workspace_root) if session.workspace_root else None,
            })
            await ws.send_json(build_history_payload(session))

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

                elif msg_type == "user_answer":
                    question_id = str(raw.get("question_id", "")).strip()
                    answer = str(raw.get("answer", "")).strip()
                    accepted = session.question_handler.submit_answer(question_id, answer)
                    await ws.send_json({
                        "type": "user_answer",
                        "data": {
                            "question_id": question_id,
                            "status": "received" if accepted else "unavailable",
                        },
                    })

                elif msg_type == "reset":
                    session.approval_handler.fail_pending("session reset")
                    session.question_handler.fail_pending("session reset")
                    # reset 保留原 workspace/mode（issue #117 grill R7/Q9），
                    # 替换会话用同 workspace + 同 mode 创建。
                    old_workspace = session.workspace_root
                    old_mode = session.current_mode
                    session_manager.remove_session(session.session_id)
                    session = await session_manager.create_session_async(
                        llm,
                        mode=old_mode,
                        workspace_root=old_workspace,
                    )
                    await ws.send_json({
                        "type": "session_created",
                        "session_id": session.session_id,
                        "mode": session.current_mode,
                        "workspace": str(session.workspace_root) if session.workspace_root else None,
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
