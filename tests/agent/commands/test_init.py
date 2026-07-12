"""Tests for /init command: ASTER.md generation and project detection."""
import pytest
from pathlib import Path

from agent.commands.init import (
    _PROJECT_DETECTORS,
    _detect_project,
    _find_entry_file,
    _ensure_gitignore,
    generate_aster_md,
    write_aster_md,
)
from agent.commands.registry import (
    CommandContext,
    SlashCommand,
    build_default_slash_command_registry,
)


# ---- project detection -------------------------------------------------------

class TestDetectProject:
    """2.12: project type detection via marker files."""

    def test_detects_python_project(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        result = _detect_project(tmp_path)
        assert result["type"] == "Python"
        assert result["file"] == "pyproject.toml"
        assert "uv sync" in result["commands"]

    def test_detects_node_project(self, tmp_path: Path):
        (tmp_path / "package.json").write_text("{}")
        result = _detect_project(tmp_path)
        assert result["type"] == "Node.js"
        assert result["file"] == "package.json"
        assert "npm install" in result["commands"]

    def test_detects_go_project(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module x")
        result = _detect_project(tmp_path)
        assert result["type"] == "Go"
        assert result["file"] == "go.mod"

    def test_detects_rust_project(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text("[package]\nname='x'")
        result = _detect_project(tmp_path)
        assert result["type"] == "Rust"
        assert result["file"] == "Cargo.toml"

    def test_detects_makefile_project(self, tmp_path: Path):
        (tmp_path / "Makefile").write_text("all:")
        result = _detect_project(tmp_path)
        assert result["type"] == "C/C++"
        assert result["file"] == "Makefile"

    def test_unknown_when_no_marker_files(self, tmp_path: Path):
        result = _detect_project(tmp_path)
        assert result["type"] == "Unknown"
        assert result["file"] is None
        assert result["commands"] == ""

    def test_python_before_other_detectors(self, tmp_path: Path):
        """pyproject.toml takes priority over later detectors."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
        (tmp_path / "Makefile").write_text("all:")
        result = _detect_project(tmp_path)
        assert result["type"] == "Python"


# ---- entry file detection -----------------------------------------------------

class TestFindEntryFile:
    def test_finds_main_py(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("")
        assert _find_entry_file(tmp_path) == "main.py"

    def test_finds_src_main_py(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        assert _find_entry_file(tmp_path) == "src/main.py"

    def test_finds_index_js(self, tmp_path: Path):
        (tmp_path / "index.js").write_text("")
        assert _find_entry_file(tmp_path) == "index.js"

    def test_finds_main_go(self, tmp_path: Path):
        (tmp_path / "main.go").write_text("")
        assert _find_entry_file(tmp_path) == "main.go"

    def test_returns_none_when_no_entry(self, tmp_path: Path):
        assert _find_entry_file(tmp_path) is None

    def test_first_match_returned(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("")
        (tmp_path / "index.js").write_text("")
        # main.py is checked first, so it should win
        assert _find_entry_file(tmp_path) == "main.py"


# ---- gitignore ---------------------------------------------------------------

class TestEnsureGitignore:
    def test_creates_gitignore_when_missing(self, tmp_path: Path):
        assert not (tmp_path / ".gitignore").exists()
        result = _ensure_gitignore(tmp_path)
        assert result is True
        content = (tmp_path / ".gitignore").read_text()
        assert "ASTER.local.md" in content

    def test_appends_when_not_present(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("*.pyc\n")
        result = _ensure_gitignore(tmp_path)
        assert result is True
        content = (tmp_path / ".gitignore").read_text()
        assert "ASTER.local.md" in content
        assert "*.pyc" in content

    def test_noop_when_already_present(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("ASTER.local.md\n*.pyc\n")
        result = _ensure_gitignore(tmp_path)
        assert result is False


# ---- ASTER.md generation -----------------------------------------------------

class TestGenerateAsterMd:
    """2.13: AGENTS.md/CLAUDE.md import logic."""

    def test_generates_header(self, tmp_path: Path):
        content = generate_aster_md(tmp_path)
        assert "# ASTER.md" in content
        assert "Asterwynd" in content

    def test_imports_agents_md(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("# Project rules\n\n- Use pytest")
        content = generate_aster_md(tmp_path)
        assert "AGENTS.md" in content
        assert "- Use pytest" in content
        assert "从 AGENTS.md 导入" in content

    def test_imports_claude_md(self, tmp_path: Path):
        (tmp_path / "CLAUDE.md").write_text("@AGENTS.md")
        content = generate_aster_md(tmp_path)
        assert "CLAUDE.md" in content
        assert "@AGENTS.md" in content
        assert "从 CLAUDE.md 导入" in content

    def test_imports_both_agents_and_claude(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("# AGENTS")
        (tmp_path / "CLAUDE.md").write_text("@AGENTS.md")
        content = generate_aster_md(tmp_path)
        assert "AGENTS.md" in content
        assert "CLAUDE.md" in content

    def test_no_import_banner_when_no_source_files(self, tmp_path: Path):
        content = generate_aster_md(tmp_path)
        assert "导入" not in content

    def test_includes_commands_with_entry_file(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
        (tmp_path / "main.py").write_text("")
        content = generate_aster_md(tmp_path)
        assert "## 常用命令" in content
        assert "uv sync" in content
        assert "main.py" in content

    def test_includes_commands_without_entry_file(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
        content = generate_aster_md(tmp_path)
        assert "## 常用命令" in content
        assert "uv sync" in content

    def test_unknown_project_has_no_commands(self, tmp_path: Path):
        content = generate_aster_md(tmp_path)
        assert "## 常用命令" not in content


# ---- write_aster_md ----------------------------------------------------------

class TestWriteAsterMd:
    def test_creates_aster_md_file(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
        msg = write_aster_md(tmp_path)
        aster = tmp_path / "ASTER.md"
        assert aster.is_file()
        content = aster.read_text()
        assert "# ASTER.md" in content
        assert "已创建" in msg

    def test_updates_gitignore(self, tmp_path: Path):
        write_aster_md(tmp_path)
        gi = tmp_path / ".gitignore"
        assert gi.is_file()
        assert "ASTER.local.md" in gi.read_text()

    def test_returns_confirm_message(self, tmp_path: Path):
        msg = write_aster_md(tmp_path)
        assert "ASTER.md" in msg


# ---- /init slash command handler ----------------------------------------------

class TestInitSlashCommand:
    async def test_slash_command_registered(self):
        registry = build_default_slash_command_registry()
        names = [c.canonical_name for c in registry.commands()]
        assert "init" in names

    async def test_slash_init_creates_aster_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
        registry = build_default_slash_command_registry()
        cmd = registry._commands["init"]

        ctx = CommandContext(
            agent=None,
            messages=[],
            session_id="test",
            provider="test",
            model="test",
        )
        result = await cmd.handler(ctx, "")
        assert "已创建" in result.message
        assert (tmp_path / "ASTER.md").is_file()

    async def test_slash_init_twice_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        registry = build_default_slash_command_registry()
        cmd = registry._commands["init"]
        ctx = CommandContext(agent=None, messages=[], session_id="x", provider="t", model="t")

        await cmd.handler(ctx, "")
        first_content = (tmp_path / "ASTER.md").read_text()

        await cmd.handler(ctx, "")
        second_content = (tmp_path / "ASTER.md").read_text()

        assert first_content == second_content
