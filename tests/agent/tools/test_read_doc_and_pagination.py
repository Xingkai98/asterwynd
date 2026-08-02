# tests/agent/tools/test_read_doc_and_pagination.py
"""Sub-change ③ tests: ReadTool offset/pagination progress and ReadDoc tool."""
import pytest

from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.read_doc import ReadDocTool, MAX_DOC_SIZE_BYTES
from agent.workspace_policy import WorkspacePolicy


def _make_file(tmp_path, lines: int, prefix: str = "line") -> str:
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"{prefix}-{i}" for i in range(lines)))
    return str(f)


# ---------------------------------------------------------------------------
# ReadTool offset/pagination (task 3.1)
# ---------------------------------------------------------------------------


class TestReadOffset:
    @pytest.mark.asyncio
    async def test_limit_only_unchanged_no_note(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("hello world")
        tool = ReadTool(policy=WorkspacePolicy(tmp_path))
        assert await tool.execute(path=str(f)) == "hello world"

    @pytest.mark.asyncio
    async def test_offset_slices_and_notes_progress(self, tmp_path):
        path = _make_file(tmp_path, 100)
        tool = ReadTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path=path, offset=40, limit=20)
        assert "line-40" in result
        assert "line-59" in result
        assert "line-60" not in result
        assert '[ReadProgress file="' in result
        assert "offset=40; total=100]" in result

    @pytest.mark.asyncio
    async def test_offset_is_zero_based(self, tmp_path):
        path = _make_file(tmp_path, 10)
        tool = ReadTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path=path, offset=0, limit=1)
        assert "line-0" in result

    @pytest.mark.asyncio
    async def test_offset_without_limit_reads_to_eof(self, tmp_path):
        path = _make_file(tmp_path, 50)
        tool = ReadTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path=path, offset=48)
        assert "line-48" in result
        assert "line-49" in result
        assert "line-0" not in result

    @pytest.mark.asyncio
    async def test_offset_beyond_total_returns_empty_plus_note(self, tmp_path):
        path = _make_file(tmp_path, 10)
        tool = ReadTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path=path, offset=100)
        assert result.lstrip("\n").startswith("[ReadProgress")
        assert "offset=100; total=10]" in result

    @pytest.mark.asyncio
    async def test_negative_offset_clamped_to_zero(self, tmp_path):
        path = _make_file(tmp_path, 5)
        tool = ReadTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path=path, offset=-5, limit=1)
        assert "line-0" in result
        assert "offset=0" in result

    @pytest.mark.asyncio
    async def test_progress_note_format_matches_regex(self, tmp_path):
        import re
        from agent.memory.manager import _READ_PROGRESS_RE
        path = _make_file(tmp_path, 100)
        tool = ReadTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path=path, offset=40, limit=20)
        match = _READ_PROGRESS_RE.search(result)
        assert match is not None
        assert match.group(1) == path
        assert int(match.group(2)) == 40
        assert int(match.group(3)) == 100


# ---------------------------------------------------------------------------
# ReadDocTool (task 3.3)
# ---------------------------------------------------------------------------


class TestReadDoc:
    @pytest.mark.asyncio
    async def test_reads_deep_md(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        deep = docs / "nested.md"
        deep.write_text("# Deep doc\n\ncontent here")
        tool = ReadDocTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path="docs/nested.md")
        assert "# Deep doc" in result
        assert "content here" in result

    @pytest.mark.asyncio
    async def test_rejects_non_md(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("not a doc")
        tool = ReadDocTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path="notes.txt")
        assert "Error" in result
        assert "只支持 Markdown" in result

    @pytest.mark.asyncio
    async def test_missing_doc(self, tmp_path):
        tool = ReadDocTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path="missing.md")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_size_cap_truncates_with_note(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        big = docs / "big.md"
        big.write_text("# H" + "x" * (MAX_DOC_SIZE_BYTES + 1000))
        tool = ReadDocTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path="docs/big.md")
        assert "已截断" in result
        assert len(result) <= MAX_DOC_SIZE_BYTES + 200

    @pytest.mark.asyncio
    async def test_size_cap_is_byte_based_for_multibyte(self, tmp_path):
        """CJK 多字节内容按字节截断，不突破字节上限（finding M2）。"""
        docs = tmp_path / "docs"
        docs.mkdir()
        big = docs / "cjk.md"
        # 中文每字 3 字节：内容超过 32KB 但字符数远小于该值。
        big.write_text("中" * (MAX_DOC_SIZE_BYTES // 3 + 500))
        tool = ReadDocTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute(path="docs/cjk.md")
        assert "已截断" in result
        assert len(result.encode("utf-8")) <= MAX_DOC_SIZE_BYTES + 200

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tmp_path):
        outside = tmp_path.parent / f"{tmp_path.name}-secret.md"
        outside.write_text("secret")
        tool = ReadDocTool(policy=WorkspacePolicy(tmp_path))
        try:
            result = await tool.execute(path="../secret.md")
            assert "Error" in result
        finally:
            outside.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_readonly_and_workspace_permission(self, tmp_path):
        from agent.tool_permissions import WORKSPACE_READ_PERMISSION

        tool = ReadDocTool(policy=WorkspacePolicy(tmp_path))
        assert tool.read_only is True
        assert tool.permission == WORKSPACE_READ_PERMISSION


# ---------------------------------------------------------------------------
# Registry / factory registration (task 3.3)
# ---------------------------------------------------------------------------


class TestReadDocRegistration:
    def test_registered_in_default_factory(self, tmp_path):
        from agent.tools.factory import build_default_tool_registry

        registry = build_default_tool_registry(policy=WorkspacePolicy(tmp_path))
        assert registry.get_schema("ReadDoc")["function"]["name"] == "ReadDoc"
        names = {s["function"]["name"] for s in registry.get_all_schemas()}
        assert "ReadDoc" in names

    def test_registered_in_coding_factory(self, tmp_path):
        from agent.tools.factory import build_coding_tool_registry

        registry = build_coding_tool_registry(policy=WorkspacePolicy(tmp_path))
        names = {s["function"]["name"] for s in registry.get_all_schemas()}
        assert "ReadDoc" in names

    def test_known_builtin_names_include_read_doc(self):
        from agent.tools.factory import KNOWN_BUILTIN_TOOL_NAMES

        assert "ReadDoc" in KNOWN_BUILTIN_TOOL_NAMES
