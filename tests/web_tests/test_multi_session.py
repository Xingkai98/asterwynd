# tests/web_tests/test_multi_session.py
"""Integration tests for the multi-session hub (issue #117).

Covers: hub list APIs, workspace allowlist boundary, /ws/new mode+workspace,
per-session run mutual exclusion, cross-workspace storage/resume, session
delete (incl. cold sessions), reset workspace preservation.
"""
import asyncio

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent.config import AsterwyndConfig, WebConfig
from agent.llm import LLMResponse
from agent.message import Message
from agent.run_config import AgentMode
from agent.session import CURRENT_SCHEMA_VERSION, SessionSnapshot, SessionStore
from tests.support.llm_harness import ScriptedLLM
from typer.testing import CliRunner
from web.server import create_app


def _make_snapshot(session_id: str = "deadbeef0000", content: str = "hello"):
    return SessionSnapshot(
        schema_version=CURRENT_SCHEMA_VERSION,
        session_id=session_id,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        messages=[Message(role="user", content=content)],
        mode=AgentMode.BUILD,
        todos=[],
        active_skills=[],
        run_id="run-1",
        iteration=0,
        user_system_prompt="",
        runtime_fingerprint={},
    )


def _recv_until_closed(ws) -> list[dict]:
    """接收 WebSocket 事件直到连接关闭（服务端 error + close 场景）。"""
    events = []
    try:
        while True:
            events.append(ws.receive_json())
    except WebSocketDisconnect:
        pass
    return events


# ---------------------------------------------------------------------------
# /api/workspaces
# ---------------------------------------------------------------------------


def test_api_workspaces_lists_primary_and_allowlist(tmp_path):
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        resp = client.get("/api/workspaces")
        assert resp.status_code == 200
        data = resp.json()["workspaces"]
        assert len(data) == 2
        primary = next(w for w in data if w["is_primary"])
        assert primary["path"] == str(tmp_path.resolve())
        assert primary["exists"] is True
        assert primary["session_count"] == 0
        allowed = next(w for w in data if not w["is_primary"])
        assert allowed["path"] == str(ws_a.resolve())
        assert allowed["is_primary"] is False


def test_api_workspaces_excludes_missing_allowlist(tmp_path, caplog):
    ws_missing = tmp_path / "does-not-exist"
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_missing,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        resp = client.get("/api/workspaces")
        assert resp.status_code == 200
        workspaces = resp.json()["workspaces"]
        assert len(workspaces) == 1  # 只有主 workspace，不存在的 allowlist 被排除
        assert workspaces[0]["is_primary"] is True

    assert any("不存在" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# POST /api/workspaces（hub「+ 添加」新增 workspace 路径）
# ---------------------------------------------------------------------------


def _sidecar_path(root):
    """侧车 workspace 配置文件（机器独占写入，用户手写 yaml 不受影响）。"""
    return root / ".asterwynd" / "workspaces.yaml"


def test_add_workspace_creates_directory_and_persists(tmp_path):
    """不存在的路径 → mkdir -p 建出来 + 写侧车 + 响应含更新后的列表。"""
    new_ws = tmp_path / "新项目"
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": str(new_ws)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace"] == str(new_ws.resolve())
        assert data["created"] is True
        assert data["persisted"] is True
        assert new_ws.is_dir()
        entry = next(w for w in data["workspaces"] if w["path"] == str(new_ws.resolve()))
        assert entry["is_primary"] is False
        assert entry["exists"] is True

    assert yaml.safe_load(_sidecar_path(tmp_path).read_text())["workspaces"] == [str(new_ws.resolve())]


def test_add_workspace_usable_without_restart(tmp_path):
    """注册后立即可用：同一进程内 GET /api/sessions 接受该 workspace。"""
    new_ws = tmp_path / "ws-new"
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        assert client.get("/api/sessions", params={"workspace": str(new_ws)}).status_code == 403
        assert client.post("/api/workspaces", json={"path": str(new_ws)}).status_code == 200
        resp = client.get("/api/sessions", params={"workspace": str(new_ws)})
        assert resp.status_code == 200
        assert resp.json()["workspace"] == str(new_ws.resolve())


def test_add_workspace_persists_across_restart(tmp_path):
    """重启（新建 app）后侧车里的 workspace 仍在列表内。"""
    new_ws = tmp_path / "ws-restart"
    first = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)
    with TestClient(first) as client:
        assert client.post("/api/workspaces", json={"path": str(new_ws)}).status_code == 200

    second = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)
    with TestClient(second) as client:
        paths = [w["path"] for w in client.get("/api/workspaces").json()["workspaces"]]
    assert paths == [str(tmp_path.resolve()), str(new_ws.resolve())]


def test_add_workspace_accepts_existing_directory(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        data = client.post("/api/workspaces", json={"path": str(existing)}).json()
        assert data["created"] is False
        assert data["persisted"] is True
        assert str(existing.resolve()) in [w["path"] for w in data["workspaces"]]


def test_add_workspace_expands_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path / "primary")

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": "~/tilde-ws"})
        assert resp.status_code == 200
        assert resp.json()["workspace"] == str((tmp_path / "tilde-ws").resolve())
    assert (tmp_path / "tilde-ws").is_dir()


def test_add_workspace_idempotent(tmp_path):
    new_ws = tmp_path / "ws-once"
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        first = client.post("/api/workspaces", json={"path": str(new_ws)}).json()
        second = client.post("/api/workspaces", json={"path": str(new_ws)}).json()
        assert first["persisted"] is True
        assert second["created"] is False
        assert second["persisted"] is False
        paths = [w["path"] for w in second["workspaces"]]
        assert paths.count(str(new_ws.resolve())) == 1

    assert yaml.safe_load(_sidecar_path(tmp_path).read_text())["workspaces"] == [str(new_ws.resolve())]


def test_add_workspace_primary_workspace_is_noop(tmp_path):
    """已注册路径（主 workspace）→ 不建目录、不写侧车。"""
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        data = client.post("/api/workspaces", json={"path": str(tmp_path)}).json()
        assert data["created"] is False
        assert data["persisted"] is False
        assert data["workspace"] == str(tmp_path.resolve())

    assert not _sidecar_path(tmp_path).exists()


@pytest.mark.parametrize("payload", [{}, {"path": ""}, {"path": "   "}, {"path": 123}, {"path": None}])
def test_add_workspace_rejects_missing_path(tmp_path, payload):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json=payload)
        assert resp.status_code == 400
        assert resp.json()["error"] == "missing_path"

    assert not _sidecar_path(tmp_path).exists()


def test_add_workspace_rejects_relative_path(tmp_path):
    """相对路径拒绝（且不能按 cwd 解析建出目录）。"""
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": "relative/dir"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "workspace_must_be_absolute"

    assert not (tmp_path / "relative").exists()
    assert not _sidecar_path(tmp_path).exists()


def test_add_workspace_rejects_file_path(tmp_path):
    target = tmp_path / "a-file.txt"
    target.write_text("x")
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": str(target)})
        assert resp.status_code == 400
        assert resp.json()["error"] == "workspace_not_a_directory"

    assert not _sidecar_path(tmp_path).exists()


@pytest.mark.parametrize("sensitive", ["/", "/etc", "/etc/hosts", "/dev", "/root"])
def test_add_workspace_rejects_sensitive_path(tmp_path, sensitive):
    """文件系统根与系统敏感目录拒绝（与 CLI /workspace add 同判定）。"""
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": sensitive})
        assert resp.status_code == 400
        assert resp.json()["error"] == "workspace_sensitive_path"

    assert not _sidecar_path(tmp_path).exists()


def test_add_workspace_rejects_nul_byte_path(tmp_path):
    """含 NUL 的路径 → 结构化错误码，不透传底层 OS 文案。"""
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": "/tmp/x\x00y"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "workspace_path_invalid"


def test_add_workspace_reports_create_failure(tmp_path):
    """mkdir 失败（父级是普通文件）→ 500 + 结构化错误，不注册。"""
    blocker = tmp_path / "blocker-file"
    blocker.write_text("not a directory")
    target = blocker / "sub"
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": str(target)})
        assert resp.status_code == 500
        assert resp.json()["error"] == "workspace_create_failed"
        assert client.get("/api/sessions", params={"workspace": str(target)}).status_code == 403


def test_add_workspace_reports_persist_failure(tmp_path):
    """侧车写入失败 → 500 + workspace_persist_failed，且不注册到运行期集合。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")  # base_dir 指向文件 → 侧车父目录无法创建
    config = AsterwyndConfig(path=blocker / "asterwynd.yaml")
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    new_ws = tmp_path / "ws-persist-fail"
    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": str(new_ws)})
        assert resp.status_code == 500
        assert resp.json()["error"] == "workspace_persist_failed"
        assert client.get("/api/sessions", params={"workspace": str(new_ws)}).status_code == 403

    assert new_ws.is_dir()  # 目录已建出（已知副作用，见 register_workspace docstring）


def test_add_workspace_does_not_touch_user_config(tmp_path):
    """用户手写的 asterwynd.yaml 零改动；侧车落在配置文件同级 .asterwynd/。"""
    project = tmp_path / "proj"
    project.mkdir()
    config_file = project / "asterwynd.yaml"
    original = "agent:\n  default_mode: build\n"
    config_file.write_text(original, encoding="utf-8")
    config = AsterwyndConfig(path=config_file)
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    new_ws = tmp_path / "elsewhere" / "ws"
    with TestClient(app) as client:
        assert client.post("/api/workspaces", json={"path": str(new_ws)}).status_code == 200

    assert config_file.read_text(encoding="utf-8") == original
    sidecar = yaml.safe_load((project / ".asterwynd" / "workspaces.yaml").read_text())
    assert sidecar["workspaces"] == [str(new_ws.resolve())]


def test_corrupt_sidecar_is_ignored(tmp_path, caplog):
    sidecar = _sidecar_path(tmp_path)
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("workspaces: [unclosed\n", encoding="utf-8")
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        data = client.get("/api/workspaces").json()["workspaces"]
        assert [w["is_primary"] for w in data] == [True]

    assert any("侧车" in rec.message for rec in caplog.records)


def test_sidecar_skips_invalid_entries(tmp_path, caplog):
    """非字符串 / 相对路径 / 不存在的绝对路径都不进有效集合。"""
    sidecar = _sidecar_path(tmp_path)
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text(
        yaml.safe_dump({"workspaces": ["relative/path", 42, "", str(tmp_path / "gone")]}),
        encoding="utf-8",
    )
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        data = client.get("/api/workspaces").json()["workspaces"]

    assert [w["is_primary"] for w in data] == [True]
    assert any("侧车" in rec.message for rec in caplog.records)  # 非法条目被跳过
    assert any("不存在" in rec.message for rec in caplog.records)  # 不存在的绝对路径被排除


# ---------------------------------------------------------------------------
# /api/sessions
# ---------------------------------------------------------------------------


def test_api_sessions_lists_primary_workspace(tmp_path):
    store = SessionStore(str(tmp_path / ".asterwynd" / "sessions"))
    store.save(_make_snapshot(session_id="aaaa11111111"))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace"] == str(tmp_path.resolve())
        assert len(data["sessions"]) == 1
        s = data["sessions"][0]
        assert s["session_id"] == "aaaa11111111"
        assert s["mode"] == "build"
        assert s["messages"] == 1
        assert "created_at" in s
        assert "updated_at" in s


def test_api_sessions_rejects_unauthorized_workspace(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.get("/api/sessions", params={"workspace": "/etc"})
        assert resp.status_code == 403
        assert resp.json()["error"] == "workspace_not_allowed"


def test_api_sessions_rejects_path_traversal(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.get("/api/sessions", params={"workspace": str(tmp_path / ".." / ".." / "etc")})
        assert resp.status_code == 403


def test_api_sessions_rejects_symlink_escape(tmp_path):
    """符号链接解析到 allowlist 外路径 → 拒绝（resolve 后不在有效集合）。"""
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)
    link = tmp_path / "ws-link"
    link.symlink_to("/etc", target_is_directory=True)

    with TestClient(app) as client:
        resp = client.get("/api/sessions", params={"workspace": str(link)})
        assert resp.status_code == 403


def test_api_sessions_accepts_trailing_slash(tmp_path):
    """尾部斜杠归一化后匹配 allowlist（不被误拒）。"""
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        resp = client.get("/api/sessions", params={"workspace": str(ws_a) + "/"})
        assert resp.status_code == 200
        assert resp.json()["workspace"] == str(ws_a.resolve())


def test_api_sessions_rejects_case_variant(tmp_path):
    """大小写变体（Linux 敏感）resolve 后不匹配 allowlist → 拒绝。"""
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)
    upper = str(ws_a).replace(str(ws_a.name), str(ws_a.name).upper())

    with TestClient(app) as client:
        resp = client.get("/api/sessions", params={"workspace": upper})
        assert resp.status_code == 403


def test_api_sessions_rejects_nonexistent_path(tmp_path):
    """不存在路径（即使拼写近似 allowlist）→ 拒绝。"""
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        resp = client.get("/api/sessions", params={"workspace": str(tmp_path / "ws-a-but-not-exist")})
        assert resp.status_code == 403


def test_api_sessions_per_workspace(tmp_path):
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)
    # 主 workspace 一个会话，allowlist 一个会话
    SessionStore(str(tmp_path / ".asterwynd" / "sessions")).save(_make_snapshot(session_id="aaaa11111111"))
    SessionStore(str(ws_a / ".asterwynd" / "sessions")).save(_make_snapshot(session_id="bbbb22222222"))

    with TestClient(app) as client:
        primary_resp = client.get("/api/sessions")
        assert [s["session_id"] for s in primary_resp.json()["sessions"]] == ["aaaa11111111"]
        allow_resp = client.get("/api/sessions", params={"workspace": str(ws_a)})
        assert [s["session_id"] for s in allow_resp.json()["sessions"]] == ["bbbb22222222"]


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{id}
# ---------------------------------------------------------------------------


def test_api_delete_session_removes_memory_and_snapshot(tmp_path):
    store = SessionStore(str(tmp_path / ".asterwynd" / "sessions"))
    store.save(_make_snapshot(session_id="aaaa11111111"))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.delete("/api/sessions/aaaa11111111", params={"workspace": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "session_id": "aaaa11111111", "workspace": str(tmp_path.resolve())}
        assert store.load("aaaa11111111") is None
        list_resp = client.get("/api/sessions")
        assert list_resp.json()["sessions"] == []


def test_api_delete_cold_session(tmp_path):
    """冷会话（磁盘有快照、内存无）也可按请求 workspace 定位删除。"""
    store = SessionStore(str(tmp_path / ".asterwynd" / "sessions"))
    store.save(_make_snapshot(session_id="aaaa11111111"))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.delete("/api/sessions/aaaa11111111", params={"workspace": str(tmp_path)})
        assert resp.status_code == 200
        assert store.load("aaaa11111111") is None


def test_api_delete_requires_workspace(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.delete("/api/sessions/aaaa11111111")
        assert resp.status_code == 400
        assert resp.json()["error"] == "missing_workspace"


def test_api_delete_rejects_invalid_session_id(tmp_path):
    """畸形 session_id（含 / 的路径穿越）不被处理：路由层 404 或 handler 400，
    绝不返回 500（design review I4）。"""
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.delete("/api/sessions/..%2F..%2Fetc", params={"workspace": str(tmp_path)})
        assert resp.status_code in (400, 404)
        assert resp.status_code != 500


def test_api_delete_rejects_unauthorized_workspace(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        resp = client.delete("/api/sessions/aaaa11111111", params={"workspace": "/etc"})
        assert resp.status_code == 403
        assert resp.json()["error"] == "workspace_not_allowed"


# ---------------------------------------------------------------------------
# /ws/new?mode=&workspace=
# ---------------------------------------------------------------------------


def test_websocket_new_with_mode_and_workspace(tmp_path):
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/new?mode=plan&workspace={ws_a}") as ws:
            created = ws.receive_json()

    assert created["type"] == "session_created"
    assert created["mode"] == "plan"
    assert created["workspace"] == str(ws_a.resolve())
    assert created["session_id"]


def test_websocket_new_rejects_invalid_mode(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new?mode=invalid") as ws:
            events = _recv_until_closed(ws)

    assert any(e.get("error") == "invalid_mode" for e in events)


def test_websocket_new_rejects_unauthorized_workspace(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new?workspace=/etc") as ws:
            events = _recv_until_closed(ws)

    assert any(e.get("error") == "workspace_not_allowed" for e in events)


def test_websocket_new_skips_resume_when_explicit(tmp_path):
    """/ws/new 带显式参数时跳过 --resume 拦截（grill R2/Q8）。"""
    store = SessionStore(str(tmp_path / ".asterwynd" / "sessions"))
    store.save(_make_snapshot(session_id="resume000001"))
    app = create_app(
        ScriptedLLM([LLMResponse(content="hi")]),
        workspace_root=tmp_path,
        resume="resume000001",
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new?mode=read_only") as ws:
            created = ws.receive_json()

    assert created["type"] == "session_created"
    assert created["session_id"] != "resume000001"  # 新建，不是 resume
    assert created["mode"] == "read_only"


def test_websocket_new_bare_keeps_resume_semantics(tmp_path):
    """裸 /ws/new 仍保留 --resume 语义（design review I5）。"""
    store = SessionStore(str(tmp_path / ".asterwynd" / "sessions"))
    store.save(_make_snapshot(session_id="resume000001"))
    app = create_app(
        ScriptedLLM([LLMResponse(content="hi")]),
        workspace_root=tmp_path,
        resume="resume000001",
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            resumed = ws.receive_json()
            history = ws.receive_json()

    assert resumed["type"] == "session_resumed"
    assert resumed["session_id"] == "resume000001"
    assert history["type"] == "session_history"


# ---------------------------------------------------------------------------
# resume with workspace / cross-workspace
# ---------------------------------------------------------------------------


def test_websocket_resume_with_workspace(tmp_path):
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    SessionStore(str(ws_a / ".asterwynd" / "sessions")).save(_make_snapshot(session_id="aaaa11111111"))
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/aaaa11111111?workspace={ws_a}") as ws:
            resumed = ws.receive_json()
            history = ws.receive_json()

    assert resumed["type"] == "session_resumed"
    assert resumed["session_id"] == "aaaa11111111"
    assert resumed["workspace"] == str(ws_a.resolve())
    assert history["type"] == "session_history"


def test_websocket_resume_rejects_unauthorized_workspace(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/aaaa11111111?workspace=/etc") as ws:
            events = _recv_until_closed(ws)

    assert any(e.get("error") == "workspace_not_allowed" for e in events)
    # 不得回退创建/恢复会话
    assert not any(e.get("type") in {"session_created", "session_resumed"} for e in events)


def test_websocket_resume_without_workspace_searches_primary_first(tmp_path):
    """未带 workspace 恢复时按确定性顺序取主 → allowlist；同 id 取主。"""
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    # 同一 session_id 同时存在于主 workspace 与 allowlist（异常场景，验证确定性）
    SessionStore(str(tmp_path / ".asterwynd" / "sessions")).save(
        _make_snapshot(session_id="aaaa11111111", content="primary copy")
    )
    SessionStore(str(ws_a / ".asterwynd" / "sessions")).save(
        _make_snapshot(session_id="aaaa11111111", content="allowlist copy")
    )
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/aaaa11111111") as ws:
            resumed = ws.receive_json()
            history = ws.receive_json()

    assert resumed["type"] == "session_resumed"
    assert resumed["workspace"] == str(tmp_path.resolve())  # 主 workspace 优先
    texts = [m["content"] for m in history["data"]["messages"]]
    assert "primary copy" in texts


def test_websocket_resume_allowlist_rerun_stays_in_allowlist_store(tmp_path):
    """归属闭环（design review I2）：无 workspace 恢复 allowlist 会话后 re-run
    仍写入 allowlist store，主 store 不新增。"""
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)
    sid = "aaaa11111111"
    SessionStore(str(ws_a / ".asterwynd" / "sessions")).save(_make_snapshot(session_id=sid))

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/{sid}?workspace={ws_a}") as ws:
            ws.receive_json()  # session_resumed
            ws.receive_json()  # session_history
            ws.send_json({"type": "chat", "content": "继续"})
            while True:
                event = ws.receive_json()
                if event["type"] == "done":
                    break

    allow_store = SessionStore(str(ws_a / ".asterwynd" / "sessions"))
    primary_store = SessionStore(str(tmp_path / ".asterwynd" / "sessions"))
    assert allow_store.load(sid) is not None
    # 主 store 不应有该 session 的新快照（恢复时归属 allowlist workspace）
    assert primary_store.load(sid) is None


# ---------------------------------------------------------------------------
# per-session run mutual exclusion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_session_mutual_exclusion(tmp_path):
    mock_llm = ScriptedLLM([LLMResponse(content="hi")])
    app = create_app(mock_llm, workspace_root=tmp_path)
    mgr = app.state.session_manager
    session = await mgr.create_session_async(mock_llm)

    # 占锁模拟进行中的 run
    await session.run_lock.acquire()
    events: list[dict] = []

    async def send(event: dict):
        events.append(event)

    await mgr.run_session(session, "hello", ws_send=send)
    assert any(
        e["type"] == "error" and "already in progress" in e["data"]["message"]
        for e in events
    ), f"并发 run 未被拒绝: {events}"

    # 释放后可正常 run
    session.run_lock.release()
    events.clear()
    await mgr.run_session(session, "hello", ws_send=send)
    assert any(e["type"] == "done" for e in events)


# ---------------------------------------------------------------------------
# reset preserves workspace/mode
# ---------------------------------------------------------------------------


def test_websocket_reset_preserves_workspace_and_mode(tmp_path):
    ws_a = tmp_path / "ws-a"
    ws_a.mkdir()
    config = AsterwyndConfig(web=WebConfig(workspaces=(ws_a,)))
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path, config=config)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/new?mode=read_only&workspace={ws_a}") as ws:
            created = ws.receive_json()
            sid = created["session_id"]
            ws.send_json({"type": "reset"})
            # reset 后回发 session_created
            reset_created = ws.receive_json()

    assert reset_created["type"] == "session_created"
    assert reset_created["mode"] == "read_only"
    assert reset_created["workspace"] == str(ws_a.resolve())
    assert reset_created["session_id"] != sid


# ---------------------------------------------------------------------------
# allowlist empty keeps primary available
# ---------------------------------------------------------------------------


def test_allowlist_empty_primary_still_works(tmp_path):
    app = create_app(ScriptedLLM([LLMResponse(content="hi")]), workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new?mode=plan") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"
            assert created["mode"] == "plan"
        with client.websocket_connect("/ws/new?workspace=" + str(tmp_path)) as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"


# ---------------------------------------------------------------------------
# CLI: --host 默认 127.0.0.1（design review I17）
# ---------------------------------------------------------------------------


def test_cli_web_default_host_is_127_0_0_1(monkeypatch, tmp_path):
    """web 命令 --host 默认值为 127.0.0.1，显式 --host 0.0.0.0 才开放 LAN。"""
    import agent.main as cli

    captured = {}

    def fake_uvicorn_run(app, host, port, log_level):
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(cli, "_setup_logging", lambda: None)
    monkeypatch.setattr(cli, "build_llm", lambda provider, model=None: type("FakeLLM", (), {"model": "fake-model"})())
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)

    from web import server
    fake_app = object()
    monkeypatch.setattr(server, "create_app", lambda llm, mode, config, resume, workspace_root: fake_app)

    result = CliRunner().invoke(cli.app, ["web", "--port", "0"])
    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1", f"默认 host 应为 127.0.0.1: {captured}"

    captured.clear()
    result = CliRunner().invoke(cli.app, ["web", "--port", "0", "--host", "0.0.0.0"])
    assert result.exit_code == 0
    assert captured["host"] == "0.0.0.0"
