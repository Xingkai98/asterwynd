# tests/agent/tools/test_read_output_bound.py
"""ReadTool default output bound (change: read-output-bound).

Covers the design decisions from ``openspec/changes/read-output-bound/design.md``:

- D1 — default line (2000) / byte (128KB) bound, whichever is reached first;
- D2 — truncation is *explicit* in the progress note (``truncated=true`` + next
  offset) and the note stays parseable by the memory manager's regex;
- D3 — a file within the bound is byte-identical to the pre-bound output;
- D5 — the escape hatches (``limit=0``, ``offset`` without ``limit``,
  non-positive limits) do not fall back to the unbounded path;
- D6 — the default read's ``offset=0`` note must not overwrite real paging
  progress recorded for the same file;
- D7 — ``total`` is always the file's total line count.
"""
import pytest

from agent.memory.manager import MemoryManager, _READ_PROGRESS_RE
from agent.message import Message
from agent.tools.builtin.read import (
    DEFAULT_MAX_READ_BYTES,
    DEFAULT_MAX_READ_LINES,
    ReadTool,
)
from agent.workspace_policy import WorkspacePolicy


def _many_lines(tmp_path, count: int, name: str = "big.txt") -> str:
    """Write ``count`` lines joined without a trailing newline."""
    f = tmp_path / name
    f.write_text("\n".join(f"line-{i}" for i in range(count)), encoding="utf-8")
    return str(f)


def _split(result: str) -> tuple[str, str]:
    """Split a read result into (body, note); note is '' when absent.

    The progress note is appended after a blank line, so the split point is the
    first ``\\n\\n[ReadProgress`` — the body then excludes the separator.
    """
    marker = "\n\n[ReadProgress"
    index = result.find(marker)
    if index == -1:
        return result, ""
    return result[:index], result[index + 2:]


def _tool(tmp_path) -> ReadTool:
    return ReadTool(policy=WorkspacePolicy(tmp_path))


# ---------------------------------------------------------------------------
# D1 — default bound on the plain read (no arguments)
# ---------------------------------------------------------------------------


class TestDefaultBound:
    @pytest.mark.asyncio
    async def test_oversized_file_truncated_with_explicit_note(self, tmp_path):
        total = DEFAULT_MAX_READ_LINES + 500
        path = _many_lines(tmp_path, total)

        result = await _tool(tmp_path).execute(path=path)

        body, note = _split(result)
        assert body.count("\n") + 1 == DEFAULT_MAX_READ_LINES
        assert body.startswith("line-0")
        assert body.endswith(f"line-{DEFAULT_MAX_READ_LINES - 1}")
        assert "truncated=true" in note
        assert f"offset=0; total={total}" in note
        assert f"continue with offset={DEFAULT_MAX_READ_LINES}" in note

    @pytest.mark.asyncio
    async def test_r0_single_read_bounded_on_both_dimensions(self, tmp_path):
        """R0: a 3196-line file is bounded by lines *and* bytes."""
        path = _many_lines(tmp_path, 3196)

        result = await _tool(tmp_path).execute(path=path)

        body, note = _split(result)
        assert body.count("\n") + 1 == DEFAULT_MAX_READ_LINES
        assert len(body.encode("utf-8")) <= DEFAULT_MAX_READ_BYTES
        assert f"total=3196" in note

    @pytest.mark.asyncio
    async def test_few_but_huge_line_bounded_by_bytes(self, tmp_path):
        """A minified single-line file is caught by the byte dimension."""
        f = tmp_path / "bundle.min.js"
        f.write_text("a;" * ((DEFAULT_MAX_READ_BYTES + 10_000) // 2), encoding="utf-8")

        result = await _tool(tmp_path).execute(path=str(f))

        body, note = _split(result)
        assert "truncated=true" in note
        assert len(body.encode("utf-8")) <= DEFAULT_MAX_READ_BYTES
        assert len(result.encode("utf-8")) < DEFAULT_MAX_READ_BYTES + 1000

    @pytest.mark.asyncio
    async def test_many_lines_bounded_by_bytes_before_line_bound(self, tmp_path):
        """Byte bound can win even when the line count is below the line bound."""
        f = tmp_path / "wide.txt"
        f.write_text("\n".join("y" * 10_000 for _ in range(DEFAULT_MAX_READ_LINES)), encoding="utf-8")

        result = await _tool(tmp_path).execute(path=str(f))

        body, note = _split(result)
        assert "truncated=true" in note
        assert len(body.encode("utf-8")) <= DEFAULT_MAX_READ_BYTES
        assert body.count("\n") + 1 < DEFAULT_MAX_READ_LINES


# ---------------------------------------------------------------------------
# D1 boundary conditions — exactly N lines / N+1 lines / exactly B / B+1 bytes
# ---------------------------------------------------------------------------


class TestBoundsAreExact:
    @pytest.mark.asyncio
    async def test_exactly_n_lines_returned_in_full(self, tmp_path):
        path = _many_lines(tmp_path, DEFAULT_MAX_READ_LINES)

        result = await _tool(tmp_path).execute(path=path)

        assert "[ReadProgress" not in result
        assert result == (tmp_path / "big.txt").read_text(errors="replace", encoding="utf-8")

    @pytest.mark.asyncio
    async def test_n_plus_one_lines_truncated(self, tmp_path):
        path = _many_lines(tmp_path, DEFAULT_MAX_READ_LINES + 1)

        result = await _tool(tmp_path).execute(path=path)

        body, note = _split(result)
        assert body.count("\n") + 1 == DEFAULT_MAX_READ_LINES
        assert "truncated=true" in note

    @pytest.mark.asyncio
    async def test_exactly_b_bytes_returned_in_full(self, tmp_path):
        f = tmp_path / "exact.txt"
        f.write_text("x" * DEFAULT_MAX_READ_BYTES, encoding="utf-8")

        result = await _tool(tmp_path).execute(path=str(f))

        assert result == "x" * DEFAULT_MAX_READ_BYTES
        assert "[ReadProgress" not in result

    @pytest.mark.asyncio
    async def test_b_plus_one_bytes_truncated(self, tmp_path):
        f = tmp_path / "over.txt"
        f.write_text("x" * (DEFAULT_MAX_READ_BYTES + 1), encoding="utf-8")

        result = await _tool(tmp_path).execute(path=str(f))

        body, note = _split(result)
        assert "truncated=true" in note
        assert len(body.encode("utf-8")) <= DEFAULT_MAX_READ_BYTES


# ---------------------------------------------------------------------------
# D5 — escape hatches
# ---------------------------------------------------------------------------


class TestEscapeHatches:
    @pytest.mark.asyncio
    async def test_limit_zero_does_not_return_whole_file(self, tmp_path):
        path = _many_lines(tmp_path, DEFAULT_MAX_READ_LINES + 300)

        result = await _tool(tmp_path).execute(path=path, limit=0)

        body, note = _split(result)
        assert body.count("\n") + 1 == DEFAULT_MAX_READ_LINES
        assert "truncated=true" in note

    @pytest.mark.asyncio
    async def test_limit_zero_with_offset_stays_bounded(self, tmp_path):
        total = DEFAULT_MAX_READ_LINES * 2
        path = _many_lines(tmp_path, total)

        result = await _tool(tmp_path).execute(path=path, offset=0, limit=0)

        assert len(result.encode("utf-8")) < DEFAULT_MAX_READ_BYTES
        body, note = _split(result)
        assert body.count("\n") + 1 == DEFAULT_MAX_READ_LINES
        assert "truncated=true" in note

    @pytest.mark.asyncio
    async def test_negative_limit_does_not_bypass_bound(self, tmp_path):
        path = _many_lines(tmp_path, DEFAULT_MAX_READ_LINES + 10)

        result = await _tool(tmp_path).execute(path=path, limit=-5)

        body, note = _split(result)
        assert body.count("\n") + 1 == DEFAULT_MAX_READ_LINES
        assert "truncated=true" in note

    @pytest.mark.asyncio
    async def test_offset_without_limit_stays_bounded(self, tmp_path):
        total = DEFAULT_MAX_READ_LINES * 2 + 10
        path = _many_lines(tmp_path, total)

        result = await _tool(tmp_path).execute(path=path, offset=DEFAULT_MAX_READ_LINES)

        body, note = _split(result)
        assert body.count("\n") + 1 == DEFAULT_MAX_READ_LINES
        assert body.startswith(f"line-{DEFAULT_MAX_READ_LINES}")
        assert f"offset={DEFAULT_MAX_READ_LINES}; total={total}" in note
        assert "truncated=true" in note
        assert f"continue with offset={DEFAULT_MAX_READ_LINES * 2}" in note

    @pytest.mark.asyncio
    async def test_offset_without_limit_on_small_file_reads_to_eof(self, tmp_path):
        """A file within the bound still reads to EOF from ``offset`` (D5 note)."""
        path = _many_lines(tmp_path, 50)

        result = await _tool(tmp_path).execute(path=path, offset=48)

        body, note = _split(result)
        assert body == "line-48\nline-49"
        assert "truncated" not in note
        assert "offset=48; total=50" in note


# ---------------------------------------------------------------------------
# D3 — within the bound the output is byte-identical to the pre-bound output
# ---------------------------------------------------------------------------


class TestWithinBoundIsUnchanged:
    @pytest.mark.asyncio
    async def test_small_file_byte_identical_to_unbounded(self, tmp_path):
        f = tmp_path / "small.txt"
        raw = "alpha\r\nbeta\n\ngamma\n"
        f.write_bytes(raw.encode("utf-8"))

        result = await _tool(tmp_path).execute(path=str(f))

        assert result == f.read_text(errors="replace", encoding="utf-8")
        assert "[ReadProgress" not in result

    @pytest.mark.asyncio
    async def test_non_utf8_bytes_are_normalized_identically(self, tmp_path):
        f = tmp_path / "raw.txt"
        f.write_bytes(b"ok\xff\xfe\x00tail\n")

        result = await _tool(tmp_path).execute(path=str(f))

        assert result == f.read_text(errors="replace", encoding="utf-8")
        assert "[ReadProgress" not in result

    @pytest.mark.asyncio
    async def test_empty_file_unchanged(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")

        result = await _tool(tmp_path).execute(path=str(f))

        assert result == ""


# ---------------------------------------------------------------------------
# Explicit positive limit — behavior unchanged (spec: "explicit positive limit
# is unchanged"; the caller controls the size)
# ---------------------------------------------------------------------------


class TestExplicitLimitUnchanged:
    @pytest.mark.asyncio
    async def test_positive_limit_only_unchanged(self, tmp_path):
        path = _many_lines(tmp_path, 1000)

        result = await _tool(tmp_path).execute(path=path, limit=10)

        assert result == "\n".join(f"line-{i}" for i in range(10))
        assert "[ReadProgress" not in result

    @pytest.mark.asyncio
    async def test_huge_explicit_limit_still_returns_whole_file(self, tmp_path):
        """The bound is a *default*; an explicit positive limit still wins."""
        f = tmp_path / "big.txt"
        f.write_text("z" * (DEFAULT_MAX_READ_BYTES + 10_000), encoding="utf-8")

        result = await _tool(tmp_path).execute(path=str(f), limit=5)

        assert result == "z" * (DEFAULT_MAX_READ_BYTES + 10_000)
        assert "[ReadProgress" not in result

    @pytest.mark.asyncio
    async def test_positive_limit_with_offset_note_format_unchanged(self, tmp_path):
        path = _many_lines(tmp_path, 100)

        result = await _tool(tmp_path).execute(path=path, offset=40, limit=20)

        body, note = _split(result)
        assert body == "\n".join(f"line-{i}" for i in range(40, 60))
        assert note == f'[ReadProgress file="{path}"; offset=40; total=100]'


# ---------------------------------------------------------------------------
# D2 — cross-module contract: the note stays parseable by the memory manager
# ---------------------------------------------------------------------------


class TestProgressNoteContract:
    @pytest.mark.asyncio
    async def test_truncated_note_matches_regex(self, tmp_path):
        total = DEFAULT_MAX_READ_LINES + 1
        path = _many_lines(tmp_path, total)

        result = await _tool(tmp_path).execute(path=path)

        match = _READ_PROGRESS_RE.search(result)
        assert match is not None
        assert match.group(1) == path
        assert int(match.group(2)) == 0
        assert int(match.group(3)) == total
        assert match.group("truncated") == "true"

    @pytest.mark.asyncio
    async def test_bounded_continuation_note_matches_regex(self, tmp_path):
        # More lines than offset+line-bound, so the read really is cut short.
        total = DEFAULT_MAX_READ_LINES * 2 + 500
        path = _many_lines(tmp_path, total)

        result = await _tool(tmp_path).execute(path=path, offset=DEFAULT_MAX_READ_LINES)

        match = _READ_PROGRESS_RE.search(result)
        assert match is not None
        assert match.group(1) == path
        assert int(match.group(2)) == DEFAULT_MAX_READ_LINES
        assert int(match.group(3)) == total
        assert match.group("truncated") == "true"

    def test_legacy_note_without_truncated_field_still_matches(self):
        text = '[ReadProgress file="big.txt"; offset=40; total=100]'

        match = _READ_PROGRESS_RE.search(text)

        assert match is not None
        assert match.group(1) == "big.txt"
        assert int(match.group(2)) == 40
        assert int(match.group(3)) == 100
        assert match.group("truncated") is None


# ---------------------------------------------------------------------------
# D6 — the default read's offset=0 note must not overwrite paging progress
# ---------------------------------------------------------------------------


class TestDefaultReadDoesNotOverwriteProgress:
    @staticmethod
    def _extract(*contents: str) -> list[tuple[str, int, int]]:
        mgr = MemoryManager()
        messages = [
            Message(role="tool", content=content, tool_call_id=f"c{i}")
            for i, content in enumerate(contents)
        ]
        return mgr._extract_read_progress(messages)

    @pytest.mark.asyncio
    async def test_default_read_after_paging_keeps_progress(self, tmp_path):
        total = DEFAULT_MAX_READ_LINES * 3
        path = _many_lines(tmp_path, total)

        paged = await _tool(tmp_path).execute(
            path=path, offset=DEFAULT_MAX_READ_LINES, limit=10
        )
        default = await _tool(tmp_path).execute(path=path)

        assert self._extract(paged, default) == [(path, DEFAULT_MAX_READ_LINES, total)]

    @pytest.mark.asyncio
    async def test_paging_after_default_read_records_progress(self, tmp_path):
        total = DEFAULT_MAX_READ_LINES * 3
        path = _many_lines(tmp_path, total)

        default = await _tool(tmp_path).execute(path=path)
        paged = await _tool(tmp_path).execute(
            path=path, offset=DEFAULT_MAX_READ_LINES, limit=10
        )

        assert self._extract(default, paged) == [(path, DEFAULT_MAX_READ_LINES, total)]

    @pytest.mark.asyncio
    async def test_bounded_continuation_counts_as_progress(self, tmp_path):
        total = DEFAULT_MAX_READ_LINES * 3
        path = _many_lines(tmp_path, total)

        continuation = await _tool(tmp_path).execute(path=path, offset=DEFAULT_MAX_READ_LINES)

        # A truncated note at a non-zero offset is a genuine resume position.
        assert self._extract(continuation) == [(path, DEFAULT_MAX_READ_LINES, total)]

    @pytest.mark.asyncio
    async def test_default_read_alone_yields_no_progress(self, tmp_path):
        path = _many_lines(tmp_path, DEFAULT_MAX_READ_LINES * 3)

        default = await _tool(tmp_path).execute(path=path)

        # offset=0 default truncation is not a resume position.
        assert self._extract(default) == []


# ---------------------------------------------------------------------------
# D4 — image path is untouched
# ---------------------------------------------------------------------------


class TestImagePathUnchanged:
    @pytest.mark.asyncio
    async def test_large_image_not_subject_to_text_bound(self, tmp_path):
        png = tmp_path / "img.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (DEFAULT_MAX_READ_BYTES + 5000))

        result = await _tool(tmp_path).execute(path=str(png))

        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Q4 — the bound is configurable (built-in defaults + config override)
# ---------------------------------------------------------------------------


class TestBoundIsConfigurable:
    def test_config_default_matches_read_constants(self):
        """The config dataclass defaults must match the read.py module constants."""
        from agent.config import ReadOutputConfig

        defaults = ReadOutputConfig()
        assert defaults.max_lines == DEFAULT_MAX_READ_LINES
        assert defaults.max_bytes == DEFAULT_MAX_READ_BYTES

    @pytest.mark.asyncio
    async def test_tool_bound_override_truncates_small_file(self, tmp_path):
        """A smaller configured bound truncates a file the default would keep."""
        path = _many_lines(tmp_path, 50)
        tool = ReadTool(policy=WorkspacePolicy(tmp_path), max_lines=10, max_bytes=1024)

        result = await tool.execute(path=path)

        body, note = _split(result)
        assert body.count("\n") + 1 == 10
        assert "truncated=true" in note
        assert f"continue with offset=10" in note

    @pytest.mark.asyncio
    async def test_tool_byte_override_truncates(self, tmp_path):
        f = tmp_path / "wide.txt"
        f.write_text("z" * 5000, encoding="utf-8")
        tool = ReadTool(policy=WorkspacePolicy(tmp_path), max_lines=2000, max_bytes=100)

        result = await tool.execute(path=str(f))

        body, note = _split(result)
        assert len(body.encode("utf-8")) <= 100
        assert "truncated=true" in note

    def test_registry_wires_read_output_config(self, tmp_path):
        from agent.config import ReadOutputConfig
        from agent.tools.factory import build_default_tool_registry

        registry = build_default_tool_registry(
            policy=WorkspacePolicy(tmp_path),
            read_output_config=ReadOutputConfig(max_lines=77, max_bytes=8888),
        )
        read_tool = registry.get_tool("Read")
        assert read_tool.max_lines == 77
        assert read_tool.max_bytes == 8888

    def test_registry_read_defaults_when_no_config(self, tmp_path):
        from agent.tools.factory import build_default_tool_registry

        registry = build_default_tool_registry(policy=WorkspacePolicy(tmp_path))
        read_tool = registry.get_tool("Read")
        assert read_tool.max_lines == DEFAULT_MAX_READ_LINES
        assert read_tool.max_bytes == DEFAULT_MAX_READ_BYTES
