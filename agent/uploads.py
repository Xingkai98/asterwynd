# agent/uploads.py
"""图片上传持久化：写入 .asterwynd/uploads/ 目录，sha256 hash 命名"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.message import ImageBlock

logger = logging.getLogger("asterwynd.uploads")

UPLOADS_DIR = ".asterwynd/uploads"
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})

_MAGIC_BYTES: dict[str, bytes] = {
    "image/png": b'\x89PNG\r\n\x1a\n',
    "image/jpeg": b'\xff\xd8\xff',
    "image/gif": b'GIF8',
    "image/webp": b'RIFF',
}


def _validate_image_bytes(data: bytes, mime: str) -> None:
    """验证图片数据的魔数和基本有效性"""
    if mime not in ALLOWED_MIMES:
        raise ValueError(f"不支持的图片类型: {mime}")
    magic = _MAGIC_BYTES.get(mime)
    if magic and not data.startswith(magic):
        raise ValueError(f"文件魔数与声明类型 {mime} 不匹配")
    if mime == "image/webp" and len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] != b'WEBP':
        raise ValueError("非 WEBP 格式的 RIFF 文件")


def _parse_data_url(data_url: str) -> tuple[str, bytes]:
    """解析 data URL，返回 (mime_type, raw_bytes)"""
    if not data_url.startswith("data:"):
        raise ValueError("not a data URL")
    header, b64 = data_url.split(",", 1)
    mime = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
    data = base64.b64decode(b64, validate=True)
    return mime, data


def _ext_to_mime(ext: str) -> str:
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mapping.get(ext.lower(), "image/png")


def _mime_to_ext(mime: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    return mapping.get(mime, ".png")


def save_upload(data_url: str, *, workdir: str | None = None) -> str:
    """保存上传图片到 .asterwynd/uploads/，返回绝对文件路径。已存在则跳过写入。"""
    mime, data = _parse_data_url(data_url)

    if len(data) > MAX_UPLOAD_SIZE:
        size_mb = len(data) / (1024 * 1024)
        raise ValueError(f"图片过大 ({size_mb:.1f}MB)，超过 {MAX_UPLOAD_SIZE // (1024*1024)}MB 限制")

    _validate_image_bytes(data, mime)

    file_hash = hashlib.sha256(data).hexdigest()[:16]
    ext = _mime_to_ext(mime)

    base = Path(workdir) if workdir else Path.cwd()
    uploads_dir = base / UPLOADS_DIR
    uploads_dir.mkdir(parents=True, exist_ok=True)

    filename = f"sha256_{file_hash}{ext}"
    filepath = uploads_dir / filename

    if not filepath.exists():
        filepath.write_bytes(data)
        logger.info(f"Saved upload: {filepath}")

    return str(filepath.resolve())


def create_image_message(
    data_url: str,
    *,
    workdir: str | None = None,
) -> "ImageBlock":
    """从 data URL 创建 ImageBlock（含持久化路径）"""
    from agent.message import ImageBlock, ImageUrl

    file_path = save_upload(data_url, workdir=workdir)
    return ImageBlock(
        image_url=ImageUrl(url=data_url),
        file_path=file_path,
    )
