# agent/tools/builtin/read.py
import base64
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import WORKSPACE_READ_PERMISSION
from agent.workspace_policy import WorkspacePolicy

if TYPE_CHECKING:
    from agent.message import ContentBlock

logger = logging.getLogger("asterwynd.tools.read")

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB

# Default output bound for the text path: a read without an explicit positive
# `limit` returns at most this many leading lines, or this many bytes,
# whichever is reached first, so a single read cannot pull an unbounded file
# into the context. A file within the bound is still returned in full.
# See openspec/changes/read-output-bound/design.md (D1/D5).
DEFAULT_MAX_READ_LINES = 2000
DEFAULT_MAX_READ_BYTES = 128 * 1024


def _cap_bytes(text: str, limit_bytes: int) -> str:
    """Return at most ``limit_bytes`` UTF-8 bytes of ``text`` (never splitting a char)."""
    raw = text.encode("utf-8")
    if len(raw) <= limit_bytes:
        return text
    return raw[:limit_bytes].decode("utf-8", errors="ignore")


def _progress_note(path: str, offset: int, total: int) -> str:
    """Machine-parseable paging progress note.

    Parsed by ``agent/memory/manager.py:_READ_PROGRESS_RE``; any change to this
    format MUST be mirrored in that regex.
    """
    return f'\n\n[ReadProgress file="{path}"; offset={offset}; total={total}]'


def _truncated_note(path: str, offset: int, total: int, next_offset: int) -> str:
    """Progress note for a read cut by the default bound.

    ``truncated=true`` makes the cut explicit (never silent) and tells the
    memory manager this note is not a resume position.
    """
    return (
        f'\n\n[ReadProgress file="{path}"; offset={offset}; total={total}; truncated=true]'
        f"\n[Read output truncated at the default bound; continue with offset={next_offset}]"
    )


def _bounded_prefix(
    lines: list[str],
    start: int,
    max_lines: int = DEFAULT_MAX_READ_LINES,
    max_bytes: int = DEFAULT_MAX_READ_BYTES,
) -> tuple[str, int, bool]:
    """Bound ``lines[start:]`` by the default line/byte limits.

    Returns ``(body, next_offset, truncated)``: the text to return, the offset a
    caller should pass to continue, and whether anything was left out.
    """
    window = lines[start:start + max_lines]
    truncated_by_lines = (start + len(window)) < len(lines)

    included: list[str] = []
    size = 0
    byte_capped = False
    for line in window:
        # +1 for the newline the join will insert before this line.
        cost = len(line.encode("utf-8")) + (1 if included else 0)
        if size + cost > max_bytes:
            byte_capped = True
            break
        included.append(line)
        size += cost

    if byte_capped and not included:
        # A single line already exceeds the byte bound (e.g. a minified bundle):
        # keep a byte-limited prefix of it and resume at the next line.
        return _cap_bytes(window[0], max_bytes), start + 1, True

    return "\n".join(included), start + len(included), byte_capped or truncated_by_lines


_MAGIC_BYTES: dict[str, bytes] = {
    ".png": b'\x89PNG\r\n\x1a\n',
    ".jpg": b'\xff\xd8\xff',
    ".jpeg": b'\xff\xd8\xff',
    ".gif": b'GIF8',
    ".webp": b'RIFF',
}


def _get_image_dimensions(file_path: str) -> tuple[int, int] | None:
    """尝试获取图片尺寸，PIL 不可用时返回 None"""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(file_path) as img:
            return img.size  # (width, height)
    except Exception:
        return None


def _guess_mime_type(ext: str) -> str:
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mapping.get(ext.lower(), "image/png")


@tool_parameters(
    name="Read",
    description="读取文件内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "limit": {"type": "integer", "description": "最多读取行数", "default": None},
            "offset": {
                "type": "integer",
                "description": "从第几行开始读取（0 起）；配合 limit 分页续读大文件。返回末尾带 [ReadProgress] 进度注记",
                "default": None,
            },
        },
        "required": ["path"],
    },
)
class ReadTool(Tool):
    read_only = True
    parallelizable = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        *,
        max_lines: int = DEFAULT_MAX_READ_LINES,
        max_bytes: int = DEFAULT_MAX_READ_BYTES,
    ):
        self.policy = policy or WorkspacePolicy()
        self.max_lines = max_lines
        self.max_bytes = max_bytes

    async def execute(self, path: str, limit: int = None, offset: int = None, **kwargs) -> str | list["ContentBlock"]:
        try:
            p = self.policy.assert_read_allowed(path)
            if not p.exists():
                return f"Error: 文件不存在: {path}"

            ext = Path(path).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                return self._read_image(p, path)

            content = p.read_text(errors="replace", encoding="utf-8")
            lines = content.splitlines()
            total = len(lines)

            # A positive `limit` is the caller taking explicit control: slice
            # exactly and emit the legacy note (offset present) or bare body.
            if limit is not None and limit > 0:
                if offset is not None:
                    start = max(0, offset)
                    body = "\n".join(lines[start:start + limit])
                    return body + _progress_note(path, start, total)
                return "\n".join(lines[:limit])

            # Otherwise (no limit, limit<=0, or offset-only) apply the default
            # bound so none of these paths can return an unbounded file.
            if (
                offset is None
                and total <= self.max_lines
                and len(content.encode("utf-8")) <= self.max_bytes
            ):
                # Within the bound: return the decoded content verbatim (not
                # re-joined from splitlines) so this path is byte-identical to
                # the pre-bound output, trailing newline included.
                return content

            start = max(0, offset) if offset is not None else 0
            body, next_offset, truncated = _bounded_prefix(
                lines, start, self.max_lines, self.max_bytes
            )
            if truncated:
                return body + _truncated_note(path, start, total, next_offset)
            if offset is not None:
                return body + _progress_note(path, start, total)
            return body
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"

    def _read_image(self, target_path, display_path: str) -> list["ContentBlock"]:
        from agent.message import TextBlock, ImageBlock, ImageUrl

        file_size = os.path.getsize(str(target_path))

        if file_size > MAX_IMAGE_SIZE:
            size_mb = file_size / (1024 * 1024)
            return [TextBlock(
                text=f"Error: 图片文件过大 ({size_mb:.1f}MB)，超过 {MAX_IMAGE_SIZE // (1024*1024)}MB 限制: {display_path}"
            )]

        try:
            data = target_path.read_bytes()
        except Exception as e:
            return [TextBlock(text=f"Error: 无法读取图片 {display_path}: {e}")]

        ext = Path(display_path).suffix.lower()
        magic = _MAGIC_BYTES.get(ext)
        if magic and not data.startswith(magic):
            return [TextBlock(
                text=f"Error: 文件魔数与扩展名 {ext} 不匹配: {display_path}"
            )]
        if ext == ".webp" and len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] != b'WEBP':
            return [TextBlock(text=f"Error: 非 WEBP 格式的 RIFF 文件: {display_path}")]

        try:
            encoded = base64.b64encode(data).decode("ascii")
        except Exception as e:
            return [TextBlock(text=f"Error: 无法编码图片 {display_path}: {e}")]
        mime = _guess_mime_type(ext)
        data_url = f"data:{mime};base64,{encoded}"

        dimensions = _get_image_dimensions(str(target_path))
        size_desc = f"{dimensions[0]}x{dimensions[1]}" if dimensions else "unknown"

        return [
            TextBlock(text=f"[image: {display_path}, {size_desc}]"),
            ImageBlock(
                image_url=ImageUrl(url=data_url),
                file_path=str(target_path),
            ),
        ]
