"""工具结果有界化的**判定纯函数**（change ``tool-result-lifecycle``，D1/D3/D6/D6b）。

本模块**无状态、不碰 I/O**。D1 的两段式：判定在这里，落盘与 scope 注入由 ``loop.py``
在 ``run()`` 期完成（``MemoryManager`` 构造期拿不到 ``workspace_root``，子 agent 的
scope id（``run_id``）也只在 ``run()`` 期才知道）。

三个执行点共享同一套判据：

- ``loop.py`` 写 ``messages`` / ``trace`` / ``tool_calls_made`` 时调用 ``make_preview``；
- ``MemoryManager.prune_tool_results`` 判「哪些 messages 该剪」时调用
  ``exceeds_single_threshold``；
- 剪枝替换正文时调用 ``make_preview``（保头 + **保尾** ``[ReadProgress]`` 注记）。

判据（D3，用户 2026-10-03 拍板）：

- **双维度**（D6）：``token > max(TOKEN_MIN, max_tokens × TOKEN_RATIO)`` **或**
  ``bytes > MAX_BYTES``——取先到。字节维度对 ``ImageBlock`` 计 ``len(url)``：图片在
  token 账本上是固定 1000/张（``message.py:97-98``），但 base64 可达 MB 级，纯 token
  判据对图片失效。
- **预览保尾**（对抗验证 Q-new1）：head-only 预览会剪掉 ``[ReadProgress ...]`` 续读
  注记，破坏既有「Pagination Progress Preservation」能力。预览 = 头 + 尾部注记。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from agent.message import ContentBlock

#: 单条阈的 token 下限——小预算 loop（如 ``MemoryManager(max_tokens=8_000)``）不至于
#: 把每条正常结果都剪掉。
TOKEN_MIN = 2_000

#: 单条阈 = ``max(TOKEN_MIN, max_tokens × TOKEN_RATIO)``。0.25 与 ``max_tokens=80_000``
#: 组合给出 20K token —— 一次默认 Read（B 后 ≤128KB ≈ 32K token）即超阈。
TOKEN_RATIO = 0.25

#: 单条阈的字节上限，与 B（``read-output-bound``）的 Read 默认输出界同值。
MAX_BYTES = 128 * 1024

#: 预览保留的头字符数（有界预览 = 头 + 可选尾注记 + 标记）。
PREVIEW_CHARS = 2_000

#: ReadTool 分页进度注记（见 ``agent/tools/builtin/read.py``）：
#:   ``[ReadProgress file="<path>"; offset=<n>; total=<m>]``
#: 默认上界截断的注记额外带 ``; truncated=true`` 后缀（change ``read-output-bound``）——
#: 该注记不是续读位点，``MemoryManager._extract_read_progress`` 会跳过它。
#:
#: **单一来源**：``manager.py`` 从这里导入，避免预览侧与提取侧各持一份正则漂移。
READ_PROGRESS_RE = re.compile(
    r'\[ReadProgress file="([^"]*)"; offset=(\d+); total=(\d+)(?:; truncated=(?P<truncated>true))?\]'
)

#: 有 ref 的截断标记（形态与 ``subagent/manager._bounded_summary`` 同族，多带可解析 ref）。
TRUNCATED_WITH_REF = "\n…[truncated; full result in result_ref: {ref}]"

#: 无 ref 的诚实标记——**MUST NOT** 指向任何 ref（D8：落盘没成功就不谎称可回读）。
TRUNCATED_MARKER = "\n…[truncated]"


def content_tokens(content: "str | list[ContentBlock]", counter: Callable[[str], int]) -> int:
    """content 的 token 估算（图片按 ``count_tokens_for_content`` 的固定 1000/张）。"""
    from agent.message import count_tokens_for_content

    return count_tokens_for_content(content, counter)


def content_bytes(content: "str | list[ContentBlock]") -> int:
    """content 的**常驻字节**估算（D6）。

    ``str`` 按 UTF-8 编码长度（中文与 emoji 才不会低估）；``ImageBlock`` 按
    ``len(image_url.url)``（base64 data URL 的真实常驻体量）。
    """
    from agent.message import ImageBlock

    if isinstance(content, str):
        return len(content.encode("utf-8"))
    total = 0
    for block in content:
        if isinstance(block, ImageBlock):
            total += len(block.image_url.url.encode("utf-8"))
        else:
            total += len(getattr(block, "text", "").encode("utf-8"))
    return total


def token_budget_for(max_tokens: int) -> int:
    return max(TOKEN_MIN, int(max_tokens * TOKEN_RATIO))


def exceeds_single_threshold(
    content: "str | list[ContentBlock]",
    *,
    max_tokens: int,
    counter: Callable[[str], int],
) -> bool:
    """D3 的**单条阈**：token 或字节任一超阈即真（双判据取先到）。"""
    return (
        content_tokens(content, counter) > token_budget_for(max_tokens)
        or content_bytes(content) > MAX_BYTES
    )


def flatten_content(
    content: "str | list[ContentBlock]",
    *,
    image_refs: dict[int, str] | None = None,
) -> str:
    """把 ``str | list[ContentBlock]`` 摊平成文本（图片 → ``[image: <...>]``）。

    图片占位复用 trace 既有形态（``trace_recorder._sanitize_observation``）：
    ``file_path`` 优先（模型可 ``Read`` 该路径取回像素），否则用调用方预先落盘的
    ``image_refs[i]``（粘贴图），再否则 ``pasted image``。**本函数不碰 I/O**——
    ``image_refs`` 由调用方在落盘后传入。
    """
    if isinstance(content, str):
        return content
    from agent.message import ImageBlock, TextBlock

    refs = image_refs or {}
    parts: list[str] = []
    for index, block in enumerate(content):
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ImageBlock):
            ref = block.file_path or refs.get(index) or "pasted image"
            parts.append(f"[image: {ref}]")
    return "\n".join(parts)


def preserved_tail(text: str) -> str:
    """最后一个 ``[ReadProgress ...]`` 注记（没有则空串）。

    last-wins 与 ``MemoryManager._extract_read_progress`` 的语义一致：某文件的续读
    位点取最近一条注记。
    """
    last: str | None = None
    for match in READ_PROGRESS_RE.finditer(text):
        last = match.group(0)
    return last or ""


def make_preview(
    content: "str | list[ContentBlock]",
    *,
    ref: str | None = None,
    image_refs: dict[int, str] | None = None,
) -> str:
    """生成有界预览：头 ``PREVIEW_CHARS`` + 保尾 ``[ReadProgress]`` + 诚实标记。

    ``ref`` 存在 ⇒ 标记如实指向它（可无损回读）；否则用 ``[truncated]``（D8）。
    """
    text = flatten_content(content, image_refs=image_refs)
    head = text[:PREVIEW_CHARS]
    tail = preserved_tail(text)
    marker = TRUNCATED_WITH_REF.format(ref=ref) if ref else TRUNCATED_MARKER
    if tail and tail not in head:
        return f"{head}\n…\n{tail}{marker}"
    return f"{head}{marker}"
