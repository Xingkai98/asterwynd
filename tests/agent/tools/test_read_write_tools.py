import json

import pytest
from agent.tools.builtin.bash import BashTool
from agent.tools.builtin.grep import GrepTool
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.write import WriteTool
from agent.workspace_policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")

    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(f))
    assert result == "hello world"


@pytest.mark.asyncio
async def test_read_file_not_found():
    tool = ReadTool()
    result = await tool.execute(path="/nonexistent/file.txt")
    assert "Error" in result or "not found" in result.lower()


@pytest.mark.asyncio
async def test_read_default_policy_uses_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.txt").write_text("hello cwd")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside")
    tool = ReadTool()

    try:
        assert await tool.execute(path="test.txt") == "hello cwd"
        result = await tool.execute(path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "outside\n" not in result


@pytest.mark.asyncio
async def test_read_directory_returns_error(tmp_path):
    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(tmp_path))
    assert "Error" in result


@pytest.mark.asyncio
async def test_read_rejects_path_outside_workspace(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret")
    tool = ReadTool(policy=WorkspacePolicy(tmp_path))

    try:
        result = await tool.execute(path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "secret" not in result


@pytest.mark.asyncio
async def test_read_rejects_denied_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=secret\n")
    tool = ReadTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(path=".env")

    assert "denied" in result.lower()
    assert "TOKEN=secret" not in result


@pytest.mark.asyncio
async def test_write_file(tmp_path):
    tool = WriteTool()
    file_path = tmp_path / "output.txt"
    result = await tool.execute(path=str(file_path), content="hello")
    assert "已写入" in result
    assert file_path.read_text() == "hello"


@pytest.mark.asyncio
async def test_write_existing_file_is_rejected(tmp_path):
    tool = WriteTool()
    file_path = tmp_path / "output.txt"
    file_path.write_text("old")

    result = await tool.execute(path=str(file_path), content="new")

    assert "file already exists" in result
    assert file_path.read_text() == "old"


@pytest.mark.asyncio
async def test_write_existing_file_still_rejected_with_unrecognized_overwrite_kwarg(tmp_path):
    tool = WriteTool()
    file_path = tmp_path / "output.txt"
    file_path.write_text("old")

    result = await tool.execute(path=str(file_path), content="new", overwrite=True)

    assert "file already exists" in result
    assert file_path.read_text() == "old"


@pytest.mark.asyncio
async def test_write_directory_path_returns_error(tmp_path):
    tool = WriteTool()
    result = await tool.execute(path=str(tmp_path), content="hello")
    assert "Error" in result


@pytest.mark.asyncio
async def test_bash_timeout():
    tool = BashTool()
    result = await tool.execute(cmd="sleep 1", timeout=0.05)
    data = json.loads(result)
    assert data["timed_out"]


@pytest.mark.asyncio
async def test_bash_non_zero_exit():
    tool = BashTool()
    result = await tool.execute(cmd="sh -c 'echo failed >&2; exit 7'")
    data = json.loads(result)
    assert data["exit_code"] == 7
    assert data["stderr"] == "failed"


@pytest.mark.asyncio
async def test_grep_invalid_regex_returns_error(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    tool = GrepTool()
    result = await tool.execute(pattern="[", path=str(f))
    assert "Error" in result


@pytest.mark.asyncio
async def test_grep_default_policy_uses_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.txt").write_text("needle cwd\n")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("needle outside\n")
    tool = GrepTool()

    try:
        assert "needle cwd" in await tool.execute(pattern="needle", path="test.txt")
        result = await tool.execute(pattern="needle", path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "needle outside" not in result


@pytest.mark.asyncio
async def test_grep_rejects_path_outside_workspace(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret")
    tool = GrepTool(policy=WorkspacePolicy(tmp_path))

    try:
        result = await tool.execute(pattern="secret", path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "secret" not in result


@pytest.mark.asyncio
async def test_grep_recursive_skips_denied_files(tmp_path):
    (tmp_path / "visible.txt").write_text("needle visible\n")
    (tmp_path / ".env").write_text("needle secret\n")
    tool = GrepTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(pattern="needle", path=".", recursive=True)

    assert "visible.txt" in result
    assert ".env" not in result
    assert "secret" not in result


# ── Read tool image support ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_image_returns_blocks(tmp_path):
    """读取 PNG 返回 [TextBlock, ImageBlock]"""
    # 最小的 1x1 PNG (valid)
    png_data = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f'
        b'\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    img = tmp_path / "test.png"
    img.write_bytes(png_data)

    from agent.tools.builtin.read import ReadTool
    from agent.workspace_policy import WorkspacePolicy
    from agent.message import TextBlock, ImageBlock

    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(img))

    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], TextBlock)
    assert "image:" in result[0].text
    assert isinstance(result[1], ImageBlock)
    assert result[1].image_url.url.startswith("data:image/png;base64,")
    assert result[1].file_path == str(img)


@pytest.mark.asyncio
async def test_read_image_jpeg_also_returns_blocks(tmp_path):
    """读取 JPEG 也返回 [TextBlock, ImageBlock]"""
    # 最小的 valid JPEG
    jpg_data = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01'
        b'\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07'
        b'\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14'
        b'\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444'
        b'\x1f\'9=82<.342\xff\xdb\x00C\x01\t\t\t\x0c\x0b\x0c\x18\r\r\x182!\x1c!22222222222222222222222222222222222222222222222222'
        b'\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01'
        b'\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02'
        b'\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142'
        b'\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%'
        b'&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87'
        b'\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6'
        b'\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5'
        b'\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3'
        b'\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa'
        b'\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00'
        b'\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4'
        b'\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01'
        b'\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQaq\x13"2\x81\x08\x14B'
        b'\x91\xa1\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19'
        b'\x1a&\'()*56789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84\x85\x86'
        b'\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5'
        b'\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4'
        b'\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3'
        b'\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xd9'
    )
    img = tmp_path / "test.jpg"
    img.write_bytes(jpg_data)

    from agent.tools.builtin.read import ReadTool
    from agent.workspace_policy import WorkspacePolicy
    from agent.message import ImageBlock

    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(img))

    assert isinstance(result, list)
    assert isinstance(result[1], ImageBlock)


@pytest.mark.asyncio
async def test_read_py_file_still_returns_str(tmp_path):
    """读取 .py 文件仍返回 str"""
    f = tmp_path / "test.py"
    f.write_text("print('hello')")

    from agent.tools.builtin.read import ReadTool
    from agent.workspace_policy import WorkspacePolicy

    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(f))

    assert isinstance(result, str)
    assert result == "print('hello')"


@pytest.mark.asyncio
async def test_read_large_image_returns_error(tmp_path):
    """超大图片 (>20MB) 返回错误"""
    import io
    # 创建一个远大于 20MB 的"图片"文件
    img = tmp_path / "huge.png"
    # 写入 21MB 数据
    with open(str(img), "wb") as f:
        f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * (21 * 1024 * 1024))

    from agent.tools.builtin.read import ReadTool
    from agent.workspace_policy import WorkspacePolicy
    from agent.message import TextBlock

    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(img))

    # 大图片错误也返回 list[ContentBlock]（含 TextBlock）
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], TextBlock)
    assert "Error" in result[0].text
