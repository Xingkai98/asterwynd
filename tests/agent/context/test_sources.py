# tests/agent/context/test_sources.py
"""Unit tests for built-in ContextSource implementations."""
import pytest
from agent.context.protocol import BuildContext
from agent.context.sources import (
    SystemPromptSource,
    _get_asterwynd_version,
    _render_system_prompt,
)
from agent.run_config import AgentMode


def make_context(cwd: str = "/tmp/test", mode: AgentMode = AgentMode.BUILD,
                 context_window: int = 100_000, total_budget: int = 20_000,
                 user_system_prompt: str = "") -> BuildContext:
    return BuildContext(cwd=cwd, mode=mode, context_window=context_window,
                        total_budget=total_budget,
                        user_system_prompt=user_system_prompt)


class TestSystemPromptSource:
    """2.6: System Prompt three-section structure."""

    async def test_renders_three_sections(self):
        src = SystemPromptSource()
        ctx = make_context()
        result = await src.render(ctx)

        assert "## 身份" in result
        assert "## 约束" in result
        assert "## 工具使用约定" in result
        # Sections must appear in order
        assert result.index("## 身份") < result.index("## 约束") < result.index("## 工具使用约定")

    async def test_contains_never_and_always_subsections(self):
        src = SystemPromptSource()
        ctx = make_context()
        result = await src.render(ctx)

        assert "### NEVER" in result
        assert "### ALWAYS" in result
        assert result.index("### NEVER") < result.index("### ALWAYS")

    async def test_includes_cwd_in_identity(self):
        src = SystemPromptSource()
        ctx = make_context(cwd="/home/user/my-project")
        result = await src.render(ctx)

        assert "/home/user/my-project" in result

    async def test_includes_python_version(self):
        import sys
        src = SystemPromptSource()
        ctx = make_context()
        result = await src.render(ctx)

        expected_py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        assert f"Python {expected_py}" in result

    async def test_includes_asterwynd_version(self):
        src = SystemPromptSource()
        ctx = make_context()
        result = await src.render(ctx)

        assert "Asterwynd" in result
        version = _get_asterwynd_version()
        assert version in result


class TestSystemPromptUserAppend:
    """2.8: --system parameter appended with --- separator."""

    async def test_user_system_prompt_appended_with_separator(self):
        src = SystemPromptSource()
        ctx = make_context(user_system_prompt="custom rule: always use pytest")
        result = await src.render(ctx)

        assert "---" in result
        assert "custom rule: always use pytest" in result
        # User prompt appears after the default sections
        assert result.index("---") > result.index("## 工具使用约定")

    async def test_no_separator_without_user_prompt(self):
        src = SystemPromptSource()
        ctx = make_context(user_system_prompt="")
        result = await src.render(ctx)

        assert "---" not in result

    async def test_user_prompt_strips_whitespace(self):
        src = SystemPromptSource()
        ctx = make_context(user_system_prompt="  \n  neat  \n  ")
        result = await src.render(ctx)

        assert "neat" in result
        # Trailing whitespace should be stripped
        assert not result.endswith(" \n")


class TestSystemPromptSourceProtocol:
    """P0 characteristics."""

    async def test_priority_is_zero(self):
        assert SystemPromptSource.priority == 0

    async def test_critical(self):
        assert SystemPromptSource.critical is True

    async def test_budget_is_reasonable(self):
        assert SystemPromptSource.budget > 0


class TestAsterwyndVersion:
    """2.7: version parsing from installed package."""

    def test_version_is_non_empty_string(self):
        version = _get_asterwynd_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_version_not_literal_unknown_in_editable_install(self):
        version = _get_asterwynd_version()
        # In an editable install / development env, this should still resolve
        # to a real version string (e.g. "0.1.0"), not the fallback "unknown".
        assert version != "unknown"


class TestRenderSystemPromptFunction:
    """Unit tests for the pure _render_system_prompt helper."""

    def test_basic_structure(self):
        result = _render_system_prompt("/tmp")
        assert "## 身份" in result
        assert "## 约束" in result
        assert "## 工具使用约定" in result

    def test_cwd_placeholder(self):
        result = _render_system_prompt("/custom/path")
        assert "/custom/path" in result

    def test_user_append(self):
        result = _render_system_prompt("/tmp", "extra instructions")
        assert "extra instructions" in result
        assert "---" in result

    def test_user_append_at_end(self):
        result = _render_system_prompt("/tmp", "extra")
        assert result.endswith("extra")
