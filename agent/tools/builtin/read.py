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
        },
        "required": ["path"],
    },
)
class ReadTool(Tool):
    read_only = True
    parallelizable = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(self, policy: WorkspacePolicy | None = None):
        self.policy = policy or WorkspacePolicy()

    async def execute(self, path: str, limit: int = None, **kwargs) -> str | list["ContentBlock"]:
        try:
            p = self.policy.assert_read_allowed(path)
            if not p.exists():
                return f"Error: 文件不存在: {path}"

            ext = Path(path).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                return self._read_image(p, path)

            content = p.read_text(errors="replace")
            if limit:
                lines = content.splitlines()
                content = "\n".join(lines[:limit])
            return content
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
