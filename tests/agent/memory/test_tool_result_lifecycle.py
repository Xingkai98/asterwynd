"""工具结果生命周期（change ``tool-result-lifecycle``）：判定纯函数 + ``messages`` 剪枝 +
压缩硬顶。

对应 design Testing Strategy 的 messages 侧用例：
- 判定纯函数（单条阈 token/字节双维度、图片字节、预览保尾）；
- ``prune_tool_results``：陈旧被替换 / 当轮保留 / 穿透窗口 / 预览保尾 / ``_tokens`` 重置 /
  无 ref 不谎称 / 残余边界（后台注入不被剪）；
- ``compact_if_needed`` 硬顶：token + 字节双维度、无视 gap、次序=剪枝→硬顶。
"""
import weakref

import pytest

from agent.artifact_store import AgentArtifactStore, extract_result_ref
from agent.memory import manager as _manager_mod
from agent.memory.manager import MemoryManager, _READ_PROGRESS_RE
from agent.memory.tool_result_policy import (
    MAX_BYTES,
    PREVIEW_CHARS,
    READ_PROGRESS_RE,
    TRUNCATED_MARKER,
    content_bytes,
    content_tokens,
    exceeds_single_threshold,
    make_preview,
    preserved_tail,
)
from agent.message import ImageBlock, ImageUrl, Message, TextBlock, tool_result_message


def _counter(text: str) -> int:
    return len(text) // 4


@pytest.fixture(autouse=True)
def _fast_token_counter(monkeypatch):
    """用 O(1) 近似计数替换 tiktoken——真实 tiktoken 在 100KB 重复串上要 15s。

    近似口径（``len // 4``）与 ``_count_tokens`` 的 tiktoken-缺失回退一致，故
    阈值 / 硬顶语义不变。``test_memory.py`` 已有同款 monkeypatch 先例。
    """
    monkeypatch.setattr(_manager_mod, "_count_tokens", _counter)


def _big(n_chars: int) -> str:
    return "A" * n_chars


class _WeakStr(str):
    """可弱引用的 ``str`` 子类（``weakref.ref(str)`` 抛 TypeError）。"""


# ── 判定纯函数 ────────────────────────────────────────────────────────────


def test_single_threshold_token_dimension():
    small = _big(1000)          # 250 tokens
    big = _big(400_000)         # 100_000 tokens > 20_000
    assert not exceeds_single_threshold(small, max_tokens=80_000, counter=_counter)
    assert exceeds_single_threshold(big, max_tokens=80_000, counter=_counter)


def test_single_threshold_byte_dimension_independent_of_token_budget():
    """字节维度独立生效（token 预算调大也拦得住）。"""
    body = _big(200_000)  # 200KB > 128KB 字节阈；token 估 50K < 100K 预算
    assert not (content_tokens(body, _counter) > 100_000)
    assert content_bytes(body) > MAX_BYTES
    assert exceeds_single_threshold(body, max_tokens=400_000, counter=_counter)


def test_image_content_bytes_counts_url_length_not_fixed_1000_tokens():
    """D6：图片 token 固定 1000/张，但字节按 base64 长度——token 硬顶对图片失效。"""
    data_url = "data:image/png;base64," + "Q" * (6 * 1024 * 1024)  # ~6MB
    content = [TextBlock(text="[image]"), ImageBlock(image_url=ImageUrl(url=data_url))]
    assert content_tokens(content, _counter) < 20_000        # token 账本几乎不动
    assert content_bytes(content) > MAX_BYTES * 10           # 字节维度拦得住
    assert exceeds_single_threshold(content, max_tokens=80_000, counter=_counter)


def test_preview_preserves_read_progress_tail():
    note = '[ReadProgress file="/big.py"; offset=2000; total=8000; truncated=true]'
    body = _big(50_000) + "\n\n" + note
    preview = make_preview(body, ref="artifact://agent/s-1/k")
    assert preview.startswith("A" * PREVIEW_CHARS)
    assert note in preview
    # 结构契约：预览仍能被 manager 的提取正则识别（跨模块）。
    assert READ_PROGRESS_RE.search(preview) is not None
    assert _READ_PROGRESS_RE.search(preview).group(1) == "/big.py"


def test_preserved_tail_is_last_wins():
    first = '[ReadProgress file="/a.py"; offset=10; total=100]'
    second = '[ReadProgress file="/a.py"; offset=50; total=100]'
    assert preserved_tail(f"{first}\nmid\n{second}") == second
    assert preserved_tail("no note") == ""


def test_preview_marker_honest_about_ref():
    with_ref = make_preview(_big(9000), ref="artifact://agent/s-1/k")
    assert extract_result_ref(with_ref) == "artifact://agent/s-1/k"
    no_ref = make_preview(_big(9000))
    assert extract_result_ref(no_ref) is None
    assert no_ref.endswith(TRUNCATED_MARKER)


def test_is_spilled_preview_anchors_not_bare_substring():
    """M1：幂等判据锚定完整标记，不误伤含 ``[truncated`` 字面量的真实结果。"""
    from agent.memory.tool_result_policy import is_spilled_preview

    assert is_spilled_preview(make_preview(_big(9000), ref="artifact://agent/s-1/k"))
    assert is_spilled_preview(make_preview(_big(9000)))
    # Real results that merely CONTAIN the literal must not be judged a preview.
    assert not is_spilled_preview(_big(400_000) + "\n[truncated] more text")
    assert not is_spilled_preview("prefix [truncated; full result in result_ref: not-a-ref] trailing")
    assert not is_spilled_preview("…[truncated] but more content follows")


# ── messages 剪枝 ─────────────────────────────────────────────────────────


def _tool_then_assistant(tool_call_id: str, content):
    assistant = Message(
        role="assistant",
        content="",
        tool_calls=[_tc(tool_call_id, "Read")],
    )
    return [assistant, tool_result_message(tool_call_id, content)]


class _TC:
    def __init__(self, id, name):
        self.id = id
        self.name = name


def _tc(id, name):
    return _TC(id, name)


def test_prune_skips_fresh_unconsumed_result():
    """当轮（未消费一轮）结果保留全文（A1）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=3, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert stats.messages_spilled == 0
    assert isinstance(messages[-1].content, str)
    assert messages[-1].content.startswith("AAA")  # still full text


def test_prune_replaces_stale_result_with_preview_and_ref():
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    saved = {}

    def save(text):
        saved["len"] = len(text)
        return "artifact://agent/s-1/k1"

    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3}, save=save,
    )
    assert stats.messages_spilled == 1
    assert saved["len"] == 400_000                       # full text went to store
    body = messages[-1].content
    assert extract_result_ref(body) == "artifact://agent/s-1/k1"
    assert messages[-1].tool_call_id == "c1"             # chain intact
    assert stats.bytes_released > 0


def test_prune_pierces_recent_window_for_oversized_single_result():
    """单条超阈独立于窗口生效（穿透窗口，spec scenario）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=100)  # 大窗口，仍在窗内
    messages = [
        Message(role="user", content="task"),
        *_tool_then_assistant("c1", _big(400_000)),
    ]
    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=3, added_iterations={"c1": 2},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert stats.messages_spilled == 1
    assert extract_result_ref(messages[-1].content) is not None


def test_prune_spills_small_result_once_it_slides_out_of_window():
    manager = MemoryManager(max_tokens=80_000, recent_window=4)
    messages = _tool_then_assistant("c1", "small result")  # 2 msgs
    messages += [Message(role="user", content=f"m{i}") for i in range(6)]  # push out
    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=9, added_iterations={"c1": 1},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert stats.messages_spilled == 1
    assert extract_result_ref(messages[1].content) is not None


def test_prune_resets_token_cache():
    """D10 红线：改 content 后 MUST 置 ``_tokens=None``（否则 count_tokens 返旧值）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.count_tokens(messages)               # prime cache
    old = messages[-1]._tokens
    assert old and old > 20_000
    manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert messages[-1]._tokens is None          # invalidated
    assert manager.count_tokens([messages[-1]]) < 5_000   # recomputed, small


def test_prune_without_ref_marks_truncated_not_fake_ref():
    """D8：落盘不可用时剪枝也让内存有界，但标记如实为 ``[truncated]``，不指向 ref。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3}, save=None,
    )
    assert stats.messages_spilled == 1
    assert extract_result_ref(messages[-1].content) is None
    assert messages[-1].content.endswith(TRUNCATED_MARKER)
    assert stats.bytes_released > 0


def test_prune_still_spills_result_containing_truncated_literal():
    """M1 回归：一个 400KB 结果正文含 ``[truncated]`` 字面量（但非 preview 形态）→ 仍被剪。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    body = _big(400_000) + "\n[truncated] more"   # real result containing the literal
    messages = _tool_then_assistant("c1", body)
    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert stats.messages_spilled == 1
    assert extract_result_ref(messages[-1].content) is not None
    assert len(messages[-1].content) < 400_000


def test_prune_is_idempotent():
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    first = manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    second = manager.tool_result_spiller.spill(
        messages, current_iteration=5, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert first.messages_spilled == 1
    assert second.messages_spilled == 0          # already a preview, no double shrink


def test_prune_preserves_read_progress_tail_end_to_end():
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    note = '[ReadProgress file="/big.py"; offset=2000; total=8000]'
    messages = _tool_then_assistant("c1", _big(400_000) + "\n\n" + note)
    manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    # 剪枝后，_extract_read_progress 仍能识别续读位点。
    progress = manager._extract_read_progress(messages)
    assert ("/big.py", 2000, 8000) in progress


def test_prune_leaves_non_tool_large_content_untouched():
    """残余边界（D7/Q-new5）：大 user 粘贴不属工具结果，不被剪——锁定「已知不覆盖」。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    huge_user = Message(role="user", content=_big(400_000))
    messages = [huge_user, Message(role="assistant", content="ok")]
    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=9, added_iterations={},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert stats.messages_spilled == 0
    assert len(messages[0].content) == 400_000


def test_prune_leaves_background_injection_untouched():
    """后台注入走 ``role=user``（无 tool_call_id），D3 剪不到——残余边界。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    injected = Message(role="user", content="[Background task bg1 completed]\n" + _big(50_000))
    messages = [injected, Message(role="assistant", content="ok")]
    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=9, added_iterations={},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert stats.messages_spilled == 0


def test_prune_image_result_flattened_to_path_reference():
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    data_url = "data:image/png;base64," + "Q" * (6 * 1024 * 1024)
    content = [
        TextBlock(text="[image: shot.png, 6.0MB]"),
        ImageBlock(image_url=ImageUrl(url=data_url), file_path="/ws/shot.png"),
    ]
    messages = _tool_then_assistant("c1", content)
    manager.count_tokens(messages)
    manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    body = messages[-1].content
    assert isinstance(body, str)
    assert "[image: /ws/shot.png]" in body
    # 图片字节被释放（不再是 6MB 的 ImageBlock）。
    assert content_bytes(messages[-1].content) < 10_000


# ── 压缩硬顶（D7）────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hard_ceiling_forces_compact_ignoring_gap():
    manager = MemoryManager(max_tokens=1_000, recent_window=10, compaction_gap=100)
    # 超过硬顶（max_tokens×2 = 2000 token）但未到 gap。
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content=_big(200_000)),  # 50_000 tokens ≫ 硬顶
        Message(role="assistant", content="ack"),
    ]
    compacted = await manager.compact_if_needed(messages, iteration=1)
    assert compacted is True


@pytest.mark.asyncio
async def test_hard_ceiling_byte_dimension_forces_compact():
    """字节维度驱动硬顶（token 估算偏低但常驻字节已失控）——图片场景。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10, compaction_gap=100)
    data_url = "data:image/png;base64," + "Q" * (2 * 1024 * 1024)  # ~2MB/张
    msgs = [Message(role="system", content="sys")]
    msgs += [Message(role="user", content=[
        TextBlock(text="[image]"),
        ImageBlock(image_url=ImageUrl(url=data_url)),
    ]) for _ in range(4)]  # ~8MB 常驻
    assert manager.count_tokens(msgs) < 80_000 * 2        # token 未达硬顶（1000/张）
    compacted = await manager.compact_if_needed(msgs, iteration=1)
    assert compacted is True


@pytest.mark.asyncio
async def test_hard_ceiling_counts_assistant_tool_call_arguments():
    """D6b：assistant ``tool_calls[].arguments``（一次 Write 的大正文）计入字节预算。

    内容住在 arguments 而非 content；只算 content 会漏掉整条大参数通道。
    """
    manager = MemoryManager(max_tokens=80_000, recent_window=10, compaction_gap=100)
    manager._last_compaction_iteration = 0  # 让 gap 生效，只有字节硬顶能触发
    assistant = Message(
        role="assistant", content="",
        tool_calls=[_tc("c1", "Write")],
    )
    assistant.tool_calls[0].arguments = {"content": "W" * (1 * 1024 * 1024)}  # 1MB
    msgs = [Message(role="system", content="sys"), Message(role="user", content="go"), assistant]
    assert manager.count_tokens(msgs) < 80_000 * 2        # token 维度未达硬顶
    compacted = await manager.compact_if_needed(msgs, iteration=1)
    assert compacted is True


@pytest.mark.asyncio
async def test_threshold_with_gap_and_no_hard_ceiling_still_skips():
    """既有行为回归：达到阈值但 gap 未到且未到硬顶 → 仍跳过。"""
    manager = MemoryManager(
        max_tokens=100_000, compact_trigger_tokens=1_000, recent_window=10, compaction_gap=10,
    )
    manager._last_compaction_iteration = 0  # 模拟刚刚compact过
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content=_big(8_000)),  # ~2K tokens ≥ 1000 阈，< 硬顶
        Message(role="assistant", content="ack"),
    ]
    assert await manager.compact_if_needed(messages, iteration=1) is False
