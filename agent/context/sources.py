# agent/context/sources.py
"""Built-in ContextSource implementations.

Each source corresponds to one of the P0-P6 layers in the ContextBuilder
priority model.  Content-generation logic is lifted from AgentLoop methods
without modification.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from agent.context.protocol import BuildContext, ContextSource
from agent.run_config import AgentMode

logger = logging.getLogger("asterwynd.context")

if TYPE_CHECKING:
    from agent.memory.persistent import PersistentMemory
    from agent.skills.runtime import SkillRuntime
    from agent.planning import PlanningManager


def _get_asterwynd_version() -> str:
    """Read Asterwynd version from installed package metadata.

    Falls back to reading ``pyproject.toml`` when run from a source checkout
    that hasn't been installed as a distribution.
    """
    try:
        from importlib.metadata import version
        return version("asterwynd")
    except Exception:
        pass

    # Fallback: scan pyproject.toml in parent directories
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return "unknown"

    current = Path(__file__).resolve().parent
    while True:
        pyproject = current / "pyproject.toml"
        if pyproject.is_file():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                ver = data.get("project", {}).get("version")
                if ver:
                    return str(ver)
            except Exception:
                pass
        parent = current.parent
        if parent == current:
            break
        current = parent

    return "unknown"


def _render_system_prompt(cwd: str, user_system_prompt: str = "") -> str:
    """Render the default three-section system prompt."""
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    asterwynd_version = _get_asterwynd_version()

    prompt = (
        f"## 身份\n\n"
        f"你是 Asterwynd，一个运行在本地的 coding agent。你的工作目录是 {cwd}。\n"
        f"你通过工具调用来读取、搜索、编辑代码，完成用户提出的工程任务。\n\n"
        f"技术栈：Python {python_version}，Asterwynd {asterwynd_version}\n\n"
        f"## 约束\n\n"
        f"### NEVER（红线圈死）\n"
        f"- NEVER 修改 .git/、.env、secrets、缓存文件或 benchmark 产物\n"
        f"- NEVER 在没有先用 Read 工具查看文件内容的情况下编辑文件\n"
        f"- NEVER 跳过工具调用直接编造文件内容作为回答\n"
        f"- NEVER 在用户或项目指令未明确要求的情况下创建测试文件或文档文件\n"
        f"- NEVER 做任务范围之外的修改或重构\n\n"
        f"### ALWAYS（每次必做）\n"
        f"- ALWAYS 对已有文件使用 Edit 工具做精确替换；Write 工具仅用于创建新文件\n"
        f"- ALWAYS 有意义的代码修改后，使用 InspectGitDiff 检查变更\n\n"
        f"## 工具使用约定\n\n"
        f"- 调用工具前，确保理解其参数和副作用\n"
        f"- 工具调用失败时，分析错误原因后再重试，不要盲目重复相同调用\n"
        f"- 对不确定的操作（删除文件、强制推送、修改配置），先向用户确认\n"
        f"- 可以并行调用多个无依赖的工具，减少往返次数"
    )

    if user_system_prompt.strip():
        prompt += f"\n\n---\n\n{user_system_prompt.strip()}"

    return prompt


class SystemPromptSource:
    """P0: coding-agent system prompt (identity, constraints, tool conventions).

    Critical — never truncated.  The --system user parameter is appended
    after the default prompt with a ``---`` separator.
    """
    name = "SystemPrompt"
    priority = 0
    budget = 1500  # ~1.5K
    critical = True

    async def render(self, context: BuildContext) -> str:
        return _render_system_prompt(context.cwd, context.user_system_prompt)


# ---------------------------------------------------------------------------
# ASTER.md helpers
# ---------------------------------------------------------------------------

MAX_ASTER_SIZE_BYTES = 32 * 1024


def _find_git_root(path: Path) -> Path | None:
    """Walk upward from *path* and return the first directory containing .git."""
    current = path.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _collect_aster_files(
    cwd: Path, upper_bound: Path
) -> list[tuple[Path, Path]]:
    """Walk from *upper_bound* down to *cwd*, collecting ASTER files.

    Each directory contributes up to two entries:
      - ASTER.md  (if present)
      - ASTER.local.md (if present)

    Returns a list of (file_path, directory) tuples ordered root→leaf.
    """
    cwd = cwd.resolve()
    upper_bound = upper_bound.resolve()

    # Build the directory chain from upper_bound → cwd
    chain: list[Path] = []
    current = cwd
    while current != upper_bound.parent:
        chain.append(current)
        if current == upper_bound:
            break
        current = current.parent
    chain.reverse()  # root first, CWD last

    result: list[tuple[Path, Path]] = []
    for directory in chain:
        aster = directory / "ASTER.md"
        if aster.is_file():
            result.append((aster, directory))
        aster_local = directory / "ASTER.local.md"
        if aster_local.is_file():
            result.append((aster_local, directory))
    return result


def _render_aster_md(
    files: list[tuple[Path, Path]], upper_bound: Path
) -> str:
    """Render collected ASTER files with source annotations and precedence.

    Format::

        ## ASTER.md ({relative_path})
        {file_content}

        ## ASTER.local.md ({relative_path})
        {file_content}

        > precedence declaration

    """
    if not files:
        return ""

    upper_bound = upper_bound.resolve()
    candidates: list[str] = []

    for file_path, directory in files:
        # Check file size before reading to avoid memory spikes from
        # accidentally large files (e.g. a multi-MB log renamed to ASTER.md).
        try:
            file_size = file_path.stat().st_size
        except OSError:
            logger.warning("Failed to stat %s — skipped", file_path, exc_info=True)
            continue
        if file_size > MAX_ASTER_SIZE_BYTES:
            logger.warning(
                "ASTER.md file %s is %d bytes (limit %d) — skipping",
                file_path, file_size, MAX_ASTER_SIZE_BYTES,
            )
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            logger.warning("Failed to read %s — skipped", file_path, exc_info=True)
            continue

        # Build relative path annotation
        if directory == upper_bound:
            label = "项目根"
        else:
            try:
                rel = directory.relative_to(upper_bound)
                label = str(rel) + "/"
            except ValueError:
                label = str(directory)

        file_name = file_path.name
        section = f"## {file_name} ({label})\n{content}"
        candidates.append(section)

    # Apply size cap, dropping from the front (ancestors) so that
    # closer-to-CWD files (higher precedence) are preserved when
    # the total exceeds the limit.
    sections: list[str] = []
    total_bytes = 0
    for section in reversed(candidates):
        section_bytes = len(section.encode("utf-8"))
        if total_bytes + section_bytes > MAX_ASTER_SIZE_BYTES:
            logger.warning(
                "ASTER.md total size would exceed limit %d — omitting ancestor file(s)",
                MAX_ASTER_SIZE_BYTES,
            )
            break
        sections.insert(0, section)
        total_bytes += section_bytes

    if not sections:
        return ""

    body = "\n\n".join(sections)
    return body + (
        "\n\n> 以上 ASTER.md 文件中，越靠近当前工作目录的指令优先级越高。"
        "如有冲突，以靠近工作目录的为准。"
    )


class AsterMdSource:
    """P1: ASTER.md project instructions.

    Walks from the Git root (or CWD when not in a Git repo) downward to
    CWD, collecting ``ASTER.md`` and ``ASTER.local.md`` from each directory.
    Files are concatenated with source-path annotations and a precedence
    declaration appended at the end.

    Critical — never truncated (together with P0, ~4.5K combined).
    """
    name = "AsterMd"
    priority = 1
    budget = 3000  # ~3K
    critical = True

    async def render(self, context: BuildContext) -> str:
        cwd = Path(context.cwd)
        upper_bound = _find_git_root(cwd) or cwd
        files = _collect_aster_files(cwd, upper_bound)
        return _render_aster_md(files, upper_bound)


class MemoryIndexSource:
    """P2: memory index from PersistentMemory (MEMORY.md summary).

    Always loaded; content is static per session.
    """
    name = "MemoryIndex"
    priority = 2
    budget = 2000  # ~2K
    critical = False

    def __init__(self, persistent_memory: PersistentMemory | None = None) -> None:
        self._persistent_memory = persistent_memory

    async def render(self, context: BuildContext) -> str:
        if self._persistent_memory is None:
            return ""
        memory_index = self._persistent_memory.load_index()
        if not memory_index:
            return ""
        return (
            "## Project Memory\n"
            "The following persistent memories from prior sessions are available. "
            "Use RecallMemory to retrieve specific entries.\n"
            "---\n"
            f"{memory_index}\n"
            "---"
        )


class SkillIndexSource:
    """P4: skill index listing available skills."""
    name = "SkillIndex"
    priority = 4
    budget = 2500  # ~2.5K (shared in P4 5K budget with SkillActive)
    critical = False

    def __init__(self, skill_runtime: SkillRuntime | None = None) -> None:
        self._skill_runtime = skill_runtime

    async def render(self, context: BuildContext) -> str:
        if self._skill_runtime is None:
            return ""
        return self._skill_runtime.render_skill_index()


class SkillActiveSource:
    """P4: active skill context (full prompt of activated skills)."""
    name = "SkillActive"
    priority = 4
    budget = 2500  # ~2.5K
    critical = False

    def __init__(self, skill_runtime: SkillRuntime | None = None) -> None:
        self._skill_runtime = skill_runtime

    async def render(self, context: BuildContext) -> str:
        if self._skill_runtime is None:
            return ""
        return self._skill_runtime.render_active_skill_context()


class PlanModeSource:
    """P5: plan-mode instructions when agent is in plan mode."""
    name = "PlanMode"
    priority = 5
    budget = 2500  # ~2.5K (shared in P5 5K budget with PlanningState + Todo)
    critical = False

    async def render(self, context: BuildContext) -> str:
        if context.mode is not AgentMode.PLAN:
            return ""
        return (
            "You are running in plan mode. Inspect the repository with read-only "
            "tools and discuss the plan with the user until it is clear. When the "
            "draft changes materially, call UpdatePlan with the current Markdown "
            "Plan Document and high-level steps. When the user confirms the plan "
            "or the plan is ready to finalize, call ExitPlanMode with the final "
            "Plan Document and steps. Steps can seed a later build-mode todo list. "
            "Do not edit files, run shell commands, or implement changes in plan "
            "mode."
        )


class PlanningStateSource:
    """P5: structured planning state (current plan items and status)."""
    name = "PlanningState"
    priority = 5
    budget = 1500  # ~1.5K
    critical = False

    def __init__(self, planning_manager: PlanningManager | None = None) -> None:
        self._planning = planning_manager

    async def render(self, context: BuildContext) -> str:
        if self._planning is None:
            return ""
        return self._planning.render_context()


class TodoSource:
    """P5: execution-progress todo list in build / read_only modes."""
    name = "Todo"
    priority = 5
    budget = 1000  # ~1K
    critical = False

    def __init__(self, todo_renderer: callable = None) -> None:
        self._renderer = todo_renderer

    async def render(self, context: BuildContext) -> str:
        if self._renderer is None:
            return ""
        return self._renderer()
