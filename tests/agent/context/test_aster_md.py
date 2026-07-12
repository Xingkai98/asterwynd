# tests/agent/context/test_aster_md.py
"""Unit tests for AsterMdSource: ASTER.md loading, traversal, and annotation."""
import pytest
from pathlib import Path

from agent.context.sources import (
    AsterMdSource,
    _find_git_root,
    _collect_aster_files,
    _render_aster_md,
    MAX_ASTER_SIZE_BYTES,
)
from agent.context.protocol import BuildContext
from agent.run_config import AgentMode


def make_context(cwd: str = "/tmp/test", mode: AgentMode = AgentMode.BUILD) -> BuildContext:
    return BuildContext(cwd=cwd, mode=mode, context_window=100_000, total_budget=20_000)


class TestFindGitRoot:
    """2.9: ASTER.md upper bound determination."""

    def test_returns_git_root_when_in_git_repo(self, tmp_path: Path):
        git_dir = tmp_path / "repo" / ".git"
        git_dir.mkdir(parents=True)
        cwd = tmp_path / "repo" / "src" / "backend"
        cwd.mkdir(parents=True)

        root = _find_git_root(cwd)
        assert root == (tmp_path / "repo").resolve()

    def test_returns_none_when_no_git(self, tmp_path: Path):
        # Some test environments have .git somewhere above tmp_path
        # (e.g. /tmp/.git).  Walk up from tmp_path to check.
        p = tmp_path
        has_above_git = False
        while True:
            if (p / ".git").exists():
                has_above_git = True
                break
            if p.parent == p:
                break
            p = p.parent
        if has_above_git:
            pytest.skip("test environment has .git above tmp_path")

        cwd = tmp_path / "no-git" / "sub"
        cwd.mkdir(parents=True)
        root = _find_git_root(cwd)
        assert root is None

    def test_returns_parent_git_dir(self, tmp_path: Path):
        git_dir = tmp_path / "project" / ".git"
        git_dir.mkdir(parents=True)

        root = _find_git_root(tmp_path / "project")
        assert root == (tmp_path / "project").resolve()


class TestCollectAsterFiles:
    """2.10: Full concatenation traversal from upper bound to CWD."""

    def test_collects_aster_md_in_each_directory(self, tmp_path: Path):
        # Setup: create ASTER.md in root and subdirectory
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# Root rules")

        sub = root / "src"
        sub.mkdir()
        (sub / "ASTER.md").write_text("# Src rules")

        cwd = sub

        files = _collect_aster_files(cwd, upper_bound=root)
        assert len(files) == 2
        assert files[0] == (root / "ASTER.md", root)
        assert files[1] == (sub / "ASTER.md", sub)

    def test_collects_local_md_alongside_md(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# Team rules")
        (root / "ASTER.local.md").write_text("# Personal rules")

        files = _collect_aster_files(root, upper_bound=root)
        assert len(files) == 2
        # ASTER.md before ASTER.local.md in same directory
        paths = [f[0].name for f in files]
        assert paths == ["ASTER.md", "ASTER.local.md"]

    def test_cwd_outside_git_root_only_collects_cwd(self, tmp_path: Path):
        # Git root at /tmp/project, but CWD is /tmp/other — no traversal across
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# ignored")

        cwd = tmp_path / "other"
        cwd.mkdir(parents=True)
        (cwd / "ASTER.md").write_text("# only this")

        # When there's no Git root in the CWD chain, upper bound = CWD
        files = _collect_aster_files(cwd, upper_bound=cwd)
        assert len(files) == 1
        assert files[0][0] == cwd / "ASTER.md"

    def test_no_aster_files_returns_empty(self, tmp_path: Path):
        cwd = tmp_path / "empty"
        cwd.mkdir(parents=True)
        (cwd / ".git").mkdir()

        files = _collect_aster_files(cwd, upper_bound=cwd)
        assert files == []

    def test_traverse_does_not_go_above_upper_bound(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# root")

        # Create parent dir above root with ASTER.md — should be ignored
        parent = tmp_path
        (parent / "ASTER.md").write_text("# should be ignored")

        files = _collect_aster_files(root, upper_bound=root)
        assert len(files) == 1
        assert files[0][0] == root / "ASTER.md"


class TestRenderAsterMd:
    """2.10-2.11: rendering format with source annotations and precedence."""

    def test_renders_with_source_annotations(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# Root")

        result = _render_aster_md([(root / "ASTER.md", root)], upper_bound=root)
        assert "## ASTER.md (项目根)" in result
        assert "# Root" in result

    def test_subdirectory_relative_path_in_annotation(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# Root")
        sub = root / "src"
        sub.mkdir()
        (sub / "ASTER.md").write_text("# Src")

        result = _render_aster_md(
            [(root / "ASTER.md", root), (sub / "ASTER.md", sub)],
            upper_bound=root,
        )
        assert "## ASTER.md (项目根)" in result
        assert "## ASTER.md (src/)" in result

    def test_local_md_annotation(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.local.md").write_text("# Local")

        result = _render_aster_md(
            [(root / "ASTER.local.md", root)],
            upper_bound=root,
        )
        assert "## ASTER.local.md (项目根)" in result

    def test_includes_precedence_declaration(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# Root")

        result = _render_aster_md([(root / "ASTER.md", root)], upper_bound=root)
        assert "优先级" in result or "precedence" in result.lower()

    def test_empty_files_empty_result(self):
        result = _render_aster_md([], upper_bound=Path("/tmp"))
        assert result == ""

    def test_ordering_root_first_cwd_last(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("ROOT")
        mid = root / "src"
        mid.mkdir()
        (mid / "ASTER.md").write_text("MID")
        cwd = root / "src" / "backend"
        cwd.mkdir()
        (cwd / "ASTER.md").write_text("CWD")

        result = _render_aster_md(
            [(root / "ASTER.md", root), (mid / "ASTER.md", mid), (cwd / "ASTER.md", cwd)],
            upper_bound=root,
        )
        assert result.index("ROOT") < result.index("MID") < result.index("CWD")


class TestSizeLimit:
    """Size limit: concatenated total ≤ 32 KiB."""

    def test_max_size_constant(self):
        assert MAX_ASTER_SIZE_BYTES == 32 * 1024

    def test_oversized_file_skipped_but_subdir_still_collected(self, tmp_path: Path):
        """When an ancestor file is oversized, closer-to-CWD files still load."""
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / "ASTER.md").write_text("x" * (MAX_ASTER_SIZE_BYTES + 1))
        sub = root / "src"
        sub.mkdir()
        (sub / "ASTER.md").write_text("# Subdir rules")

        result = _render_aster_md(
            [(root / "ASTER.md", root), (sub / "ASTER.md", sub)],
            upper_bound=root,
        )
        # Root file is too large so skipped; sub directory still present
        assert "# Subdir rules" in result
        assert "x" not in result

    def test_closer_files_preserved_when_total_exceeds_cap(self, tmp_path: Path):
        """When combined files exceed the cap, ancestor files are dropped first."""
        root = tmp_path / "project"
        root.mkdir(parents=True)
        # Make root file large enough that combined with subdir it exceeds the cap
        # Header "## ASTER.md (项目根)\n" adds ~25 bytes, subdir ~39 bytes.
        # Root payload sized so root alone fits but combined exceeds 32 KiB.
        root_payload = "y" * (MAX_ASTER_SIZE_BYTES - 30)
        (root / "ASTER.md").write_text(root_payload)
        sub = root / "src"
        sub.mkdir()
        (sub / "ASTER.md").write_text("# Subdir rules")

        result = _render_aster_md(
            [(root / "ASTER.md", root), (sub / "ASTER.md", sub)],
            upper_bound=root,
        )
        # Closer file (higher precedence) is preserved; ancestor is dropped
        assert "# Subdir rules" in result
        assert root_payload not in result


class TestAsterMdSource:
    """Integration: AsterMdSource as a ContextSource."""

    async def test_render_empty_when_no_aster_files(self, tmp_path: Path):
        cwd = tmp_path / "empty"
        cwd.mkdir(parents=True)
        (cwd / ".git").mkdir()

        src = AsterMdSource()
        ctx = make_context(cwd=str(cwd))
        result = await src.render(ctx)
        assert result == ""

    async def test_render_collects_and_annotates(self, tmp_path: Path):
        root = tmp_path / "project"
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "ASTER.md").write_text("# Project rules\nUse pytest")

        src = AsterMdSource()
        ctx = make_context(cwd=str(root))
        result = await src.render(ctx)

        assert "ASTER.md" in result
        assert "Use pytest" in result
        assert "优先级" in result or "precedence" in result.lower()

    async def test_priority_is_one(self):
        assert AsterMdSource.priority == 1

    async def test_critical(self):
        assert AsterMdSource.critical is True

    async def test_cwd_without_git_uses_cwd_as_upper_bound(self, tmp_path: Path):
        cwd = tmp_path / "no-git-dir"
        cwd.mkdir(parents=True)
        (cwd / "ASTER.md").write_text("# Local only")

        src = AsterMdSource()
        ctx = make_context(cwd=str(cwd))
        result = await src.render(ctx)

        assert "# Local only" in result
