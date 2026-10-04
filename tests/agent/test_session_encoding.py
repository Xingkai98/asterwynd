"""会话存储的编码纪律与列表容错（change ``fix-windows-encoding-and-guard``）。

**为什么这个文件必须存在**：会话存储一律是 UTF-8，而未显式指定编码的 `open()` 会按
进程 locale 编解码——Windows 中文机器上是 GBK/cp936。在 Linux（CI）上 locale 就是 UTF-8，
所以这类缺陷**在 CI 上不可能变红**；本文件把「非 UTF-8 locale」变成可复现条件：

- 进程内往返：在 Windows 上就是真实故障条件（GBK）；
- 子进程 + ``LC_ALL=C`` + ``PYTHONCOERCECLOCALE=0`` + ``PYTHONUTF8=0``：在 Linux CI 上
  等价复现（ASCII locale 比 GBK 更严格）；
- ``PYTHONWARNDEFAULTENCODING=1``（PEP 597）：把「用了 locale 默认编码」变成运行时可观测
  信号，断言我们自己的代码不再触发 ``EncodingWarning``。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from agent.message import Message
from agent.run_config import AgentMode
from agent.session import CURRENT_SCHEMA_VERSION, SessionSnapshot, SessionStore

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 会打到 locale 编码边界的文本：中文、emoji（GBK 无此字符）、数学字母、引号。
EXOTIC_TEXT = "你好，世界 👋 恭喜发财 𝕏 —— “引号”"


def _snapshot(session_id: str, content: str) -> SessionSnapshot:
    return SessionSnapshot(
        schema_version=CURRENT_SCHEMA_VERSION,
        session_id=session_id,
        created_at="2026-10-04T10:00:00",
        updated_at="2026-10-04T10:01:00",
        messages=[
            Message(role="user", content=content),
            Message(role="assistant", content="收到 👌"),
        ],
        mode=AgentMode.BUILD,
        todos=[],
        active_skills=[],
        run_id="run_001",
        iteration=1,
        runtime_fingerprint={"cwd": "/tmp", "model": "test", "provider": "test",
                             "agent_version": "0.1.0"},
    )


# --- 进程内：Windows（GBK）上就是真实故障条件 -------------------------------


def test_roundtrip_keeps_emoji_and_cjk_exactly(tmp_path):
    """含 emoji/CJK 的会话必须逐字往返（未修前：写入抛 UnicodeEncodeError）。"""
    store = SessionStore(sessions_root=str(tmp_path / "sessions"))
    assert store.save(_snapshot("sess_emoji", EXOTIC_TEXT)) is True

    loaded = store.load("sess_emoji")
    assert loaded is not None, "含非 ASCII 文本的会话必须能读回"
    assert loaded.messages[0].content == EXOTIC_TEXT
    assert loaded.messages[1].content == "收到 👌"


def test_written_files_are_valid_utf8(tmp_path):
    """落盘字节必须是 UTF-8（不是 locale 编码）——用显式 UTF-8 解码验证。"""
    store = SessionStore(sessions_root=str(tmp_path / "sessions"))
    store.save(_snapshot("sess_bytes", EXOTIC_TEXT))

    raw = (tmp_path / "sessions" / "sess_bytes" / "messages.json").read_bytes()
    decoded = json.loads(raw.decode("utf-8"))       # 非 UTF-8 字节会在这里炸
    assert decoded[0]["content"] == EXOTIC_TEXT


def test_list_sessions_survives_a_non_utf8_locale_file(tmp_path):
    """列表读取遇到非 UTF-8 字节的文件必须降级，不得让整个列表失败。

    两条降级路径都要覆盖（否则变异会在另一条上存活）：
    - ``messages.json`` 坏、快照可读 → 条目保留 + 标注；
    - ``snapshot.json`` 本身就是坏的 → 条目**仍要出现**（session_id 取目录名）+ 标注。
    """
    root = tmp_path / "sessions"
    store = SessionStore(sessions_root=str(root))
    store.save(_snapshot("sess_ok", "正常会话"))

    # 造一条 GBK 编码的 messages.json（模拟旧版本/locale 写入的脏数据）
    bad_dir = root / "sess_bad"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "snapshot.json").write_text(
        json.dumps({"session_id": "sess_bad", "message_count": 1,
                    "mode": "build", "created_at": "", "updated_at": ""},
                   ensure_ascii=False),
        encoding="utf-8")
    (bad_dir / "messages.json").write_bytes(
        json.dumps([{"role": "user", "content": "中文乱码"}], ensure_ascii=False)
        .encode("gbk"))

    # 再造一条 snapshot.json 本身不可解码的（走另一条降级分支）。
    # **载荷必须含非 ASCII**：纯 ASCII 的 JSON 用 GBK 编码后仍是合法 UTF-8，
    # 那样根本触发不到解码失败——本用例第一版就踩了这个坑（断言恒失败）。
    worse_dir = root / "sess_worse"
    worse_dir.mkdir(parents=True, exist_ok=True)
    (worse_dir / "snapshot.json").write_bytes(
        json.dumps({"session_id": "sess_worse", "mode": "build", "note": "中文"},
                   ensure_ascii=False).encode("gbk"))
    (worse_dir / "messages.json").write_text("[]", encoding="utf-8")

    sessions = store.list_sessions()                # 未修前：抛 UnicodeDecodeError → 接口 500
    by_id = {s["session_id"]: s for s in sessions}
    assert "sess_ok" in by_id, "损坏条目不得拖垮其余会话"
    assert "sess_bad" in by_id, "消息不可读的条目必须**可见**（如实标注），不许静默消失"
    assert by_id["sess_bad"].get("damaged") is True
    assert by_id["sess_bad"].get("reason"), "必须给出可读原因"
    assert "sess_worse" in by_id, "快照不可读的条目也要可见（session_id 取目录名）"
    assert by_id["sess_worse"].get("damaged") is True
    assert by_id["sess_worse"].get("reason")


# --- 子进程：在 Linux CI 上等价复现非 UTF-8 locale --------------------------

#: **脚本本体必须是纯 ASCII**：它以 `python -c <script>` 的形式经 argv 传给子进程，而在
#: `LC_ALL=C` 下 argv 的编码是 ASCII——脚本里直接写中文/emoji 会在**父进程**编码 argv 时就
#: `UnicodeEncodeError: surrogates not allowed`（Linux CI 实测红，Windows 本机不复现）。
#: 非 ASCII 内容一律用 `\uXXXX` / `\U0001XXXX` 转义，语义不变。
_ROUND_TRIP_SCRIPT = textwrap.dedent(
    """
    import json, sys
    from agent.message import Message
    from agent.run_config import AgentMode
    from agent.session import CURRENT_SCHEMA_VERSION, SessionSnapshot, SessionStore

    root = sys.argv[1]
    text = "\\u4f60\\u597d\\uff0c\\u4e16\\u754c \\U0001f44b \\U0001f44c \\u2014\\u2014"
    store = SessionStore(sessions_root=root)
    snap = SessionSnapshot(
        schema_version=CURRENT_SCHEMA_VERSION, session_id="sess_sub",
        created_at="2026-10-04T10:00:00", updated_at="2026-10-04T10:01:00",
        messages=[Message(role="user", content=text)], mode=AgentMode.BUILD,
        todos=[], active_skills=[], run_id="r", iteration=1,
        runtime_fingerprint={"cwd": "/tmp", "model": "t", "provider": "t",
                             "agent_version": "0.1.0"},
    )
    saved = store.save(snap)
    loaded = store.load("sess_sub")
    ok = bool(saved) and loaded is not None and loaded.messages[0].content == text
    print(json.dumps({"ok": ok, "listing": len(store.list_sessions())}))
    """
)


def _run_child(tmp_path, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONWARNDEFAULTENCODING": "0",
    })
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", _ROUND_TRIP_SCRIPT, str(tmp_path / "sessions")],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", env=env, timeout=120,
    )


def test_roundtrip_survives_a_c_locale_child_process(tmp_path):
    """``LC_ALL=C`` 子进程（等价非 UTF-8 locale）里同样必须往返成功。

    这是在 **Linux CI** 上抓住「忘了写 encoding」的办法：不加这段，删掉任何一处
    ``encoding="utf-8"`` 在 CI 上都不会红。
    """
    proc = _run_child(tmp_path, {
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONCOERCECLOCALE": "0",     # 关掉 PEP 538 的 C→C.UTF-8 强制
        "PYTHONUTF8": "0",              # 关掉 UTF-8 模式，让 locale 真正生效
    })
    assert proc.returncode == 0, f"子进程失败：{proc.stderr[-800:]}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True, f"C locale 下往返失败：{proc.stdout}{proc.stderr}"


def test_no_default_encoding_warning_from_our_code(tmp_path):
    """PEP 597：开了 ``PYTHONWARNDEFAULTENCODING`` 后，我们自己代码不得再触发
    ``EncodingWarning``（即不得依赖 locale 默认编码）。"""
    proc = _run_child(tmp_path, {
        "PYTHONWARNDEFAULTENCODING": "1",
        "LC_ALL": "C",
        "PYTHONCOERCECLOCALE": "0",
        "PYTHONUTF8": "0",
    })
    assert proc.returncode == 0, f"子进程失败：{proc.stderr[-800:]}"
    offenders = [
        line for line in (proc.stderr or "").splitlines()
        if "EncodingWarning" in line and "agent" in line
    ]
    assert not offenders, "存储层仍在用 locale 默认编码：\n" + "\n".join(offenders)


# --- 会话不存在/损坏时的既有语义保持不变 -----------------------------------


def test_load_returns_none_for_undecodable_messages(tmp_path):
    """单条会话读取遇到不可解码字节：返回 None（不抛），与既有「损坏 → None」一致。"""
    root = tmp_path / "sessions"
    store = SessionStore(sessions_root=str(root))
    store.save(_snapshot("sess_x", "ok"))
    (root / "sess_x" / "messages.json").write_bytes(
        json.dumps([{"role": "user", "content": "中文"}], ensure_ascii=False).encode("gbk"))

    assert store.load("sess_x") is None


@pytest.mark.parametrize("sid", ["../escape", "", "/abs"])
def test_invalid_session_ids_still_rejected(tmp_path, sid):
    """路径校验语义不变（回归护栏）。"""
    store = SessionStore(sessions_root=str(tmp_path / "sessions"))
    with pytest.raises(ValueError):
        store.load(sid)
