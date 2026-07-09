# tests/agent/test_uploads.py
import hashlib

import pytest
from agent.uploads import save_upload, create_image_message, _parse_data_url, _mime_to_ext
from agent.message import ImageBlock


def test_parse_data_url_png():
    mime, data = _parse_data_url("data:image/png;base64,iVBORw0KGgo=")
    assert mime == "image/png"
    assert isinstance(data, bytes)


def test_parse_data_url_jpeg():
    mime, data = _parse_data_url("data:image/jpeg;base64,/9j/4AAQ=")
    assert mime == "image/jpeg"


def test_parse_data_url_not_data_url():
    with pytest.raises(ValueError, match="not a data URL"):
        _parse_data_url("not-a-data-url")


def test_mime_to_ext():
    assert _mime_to_ext("image/png") == ".png"
    assert _mime_to_ext("image/jpeg") == ".jpg"
    assert _mime_to_ext("image/gif") == ".gif"
    assert _mime_to_ext("image/webp") == ".webp"
    assert _mime_to_ext("image/unknown") == ".png"


def test_save_upload_writes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 最小的 1x1 PNG base64
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/"
        "PchI7wAAAABJRU5ErkJggg=="
    )
    data_url = f"data:image/png;base64,{png_b64}"

    path = save_upload(data_url, workdir=str(tmp_path))
    assert path.startswith(str(tmp_path))
    assert ".asterwynd/uploads/sha256_" in path
    assert path.endswith(".png")

    # 文件存在且可读
    from pathlib import Path
    assert Path(path).exists()


def test_save_upload_deduplicates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/"
        "PchI7wAAAABJRU5ErkJggg=="
    )
    data_url = f"data:image/png;base64,{png_b64}"

    path1 = save_upload(data_url, workdir=str(tmp_path))
    path2 = save_upload(data_url, workdir=str(tmp_path))

    assert path1 == path2


def test_create_image_message_returns_image_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/"
        "PchI7wAAAABJRU5ErkJggg=="
    )
    data_url = f"data:image/png;base64,{png_b64}"

    block = create_image_message(data_url, workdir=str(tmp_path))

    assert isinstance(block, ImageBlock)
    assert block.image_url.url == data_url
    assert block.file_path is not None
    assert ".asterwynd/uploads/sha256_" in block.file_path
    assert block.file_path.endswith(".png")
