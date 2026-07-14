from __future__ import annotations

from dataclasses import dataclass, field

from agent.workflow.models import RoleAgentType

ROLE_SYSTEM_PROMPTS: dict[RoleAgentType, str] = {
    "planner": (
        "你是一个 Planner agent，负责 OpenSpec change 的 planning 阶段。"
        "你的工作流程：exploring（探索代码库和需求）→ writing_proposal（编写 proposal.md）"
        "→ writing_design（编写 design.md）⇄ grilling_design（设计追问迭代）"
        "→ writing_specs（编写 spec delta）→ writing_tasks（编写 tasks.md）"
        "→ ready_for_review（等待 human review gate）。"
        "产出物：proposal.md、design.md、spec delta、tasks.md。"
        "所有产出物放到 openspec/changes/<change-id>/ 目录下。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase planning --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
    "reviewer": (
        "你是一个 Reviewer agent，负责对已完成的设计文档做独立评审。"
        "你的工作流程：reading_docs（通读 proposal/design/spec delta/tasks）"
        "→ reviewing_design（检查方案的完整性、自洽性、风险覆盖、可行性）"
        "→ ready_for_review（输出评审结论）。"
        "评审结论写入 .handoff/<change-id>/review-report.md。"
        "如果发现问题需要修改，在评审报告中列出具体问题和建议。"
        "不要直接修改设计文档——你的职责是评审，修改由 Planner 负责。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase reviewing --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
    "builder": (
        "你是一个 Builder agent，负责 change 的代码实现。"
        "你的工作流程：writing_tests ⇄ test_failing（TDD 测试编写）"
        "→ implementing ⇄ all_tests_passing（实现代码）"
        "→ smoke_validating（冒烟验证）→ ready_for_review。"
        "测试先行：先写测试确保失败，再写实现让测试通过。"
        "遵循项目 AGENTS.md 中的所有编码规则和工作区约束。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase building --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
    "code-reviewer": (
        "你是一个 CodeReviewer agent，负责对实现代码做独立审查。"
        "你的工作流程：reading_diff（阅读 git diff）→ analyzing_tests（分析测试覆盖）"
        "→ reviewing_code ⇄ requesting_changes（审查代码并请求修改）"
        "→ ready_for_review。"
        "审查要点：代码与设计文档的一致性、测试覆盖充分性、代码质量和安全性。"
        "发现问题时进入 requesting_changes 并给出具体修改建议，触发回退到 building 阶段。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase code-review --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
    "closer": (
        "你是一个 Closer agent，负责 change 的收尾归档。"
        "你的工作流程：syncing_specs（合并 spec delta 到 openspec/specs/）"
        "→ archiving（归档 change 到 archive/）→ updating_backlog（更新 backlog）"
        "→ validating（运行 openspec validate 和 artifact checker）"
        "→ pr_ready（准备 PR）→ ready_for_review → done。"
        "收尾过程中发现任何未收敛的 open question 或 TODO，先回写到 change 文档。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase closing --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
}


@dataclass
class RoleAgentConfig:
    type: RoleAgentType
    name: str
    description: str
    system_prompt: str
    executor_hints: dict[str, str] = field(default_factory=dict)


def build_role_configs() -> dict[RoleAgentType, RoleAgentConfig]:
    descriptions: dict[RoleAgentType, str] = {
        "planner": "负责 planning 阶段：探索、提案、设计、规格和任务拆解",
        "reviewer": "负责 reviewing 阶段：对设计文档做独立评审",
        "builder": "负责 building 阶段：测试先行，实现代码",
        "code-reviewer": "负责 code-review 阶段：审查代码质量、测试覆盖和设计一致性",
        "closer": "负责 closing 阶段：spec 同步、归档、backlog 更新和校验",
    }

    executor_hints: dict[RoleAgentType, dict[str, str]] = {
        "planner": {"inline": "当前会话直接处理", "subagent": "创建 Planner 子会话"},
        "reviewer": {"subagent": "创建 Reviewer 子会话", "codex": "通过 Codex CLI 评审"},
        "builder": {"inline": "当前会话直接处理", "subagent": "创建 Builder 子会话"},
        "code-reviewer": {"subagent": "创建 CodeReviewer 子会话", "codex": "通过 Codex CLI 评审"},
        "closer": {"inline": "当前会话直接处理", "subagent": "创建 Closer 子会话"},
    }

    configs: dict[RoleAgentType, RoleAgentConfig] = {}
    for role_type in ("planner", "reviewer", "builder", "code-reviewer", "closer"):
        configs[role_type] = RoleAgentConfig(
            type=role_type,
            name=_role_display_name(role_type),
            description=descriptions[role_type],
            system_prompt=ROLE_SYSTEM_PROMPTS[role_type],
            executor_hints=executor_hints[role_type],
        )
    return configs


def _role_display_name(role_type: RoleAgentType) -> str:
    names: dict[RoleAgentType, str] = {
        "planner": "Planner",
        "reviewer": "Reviewer",
        "builder": "Builder",
        "code-reviewer": "CodeReviewer",
        "closer": "Closer",
    }
    return names[role_type]


def get_role_config(role_type: RoleAgentType) -> RoleAgentConfig:
    configs = build_role_configs()
    if role_type not in configs:
        raise ValueError(f"unknown role agent type: {role_type!r}")
    return configs[role_type]


def build_subagent_task(
    role_type: RoleAgentType,
    change_id: str,
    state_summary: dict,
    handoff_note_path: str | None = None,
) -> str:
    """Build the task prompt for spawning a role subagent."""
    config = get_role_config(role_type)

    lines = [
        f"## 任务：{config.name} — {config.description}",
        "",
        f"### Change: `{change_id}`",
        f"当前状态：phase=`{state_summary['state']['phase']}`, "
        f"sub_state=`{state_summary['state']['sub_state']}`",
        "",
        "### 工作目录",
        f"openspec/changes/{change_id}/",
        "",
        f"### 角色系统提示",
        config.system_prompt,
    ]

    if handoff_note_path:
        lines.extend([
            "",
            f"### Handoff 笔记",
            f"请先阅读交接笔记：`{handoff_note_path}`",
        ])

    lines.extend([
        "",
        "### 状态文件",
        f"工作过程中随时读取 `openspec/changes/{change_id}/handoff.json` 了解当前状态。",
        f"完成一个 sub_state 后更新 handoff.json 的 state 字段并追加 transition 记录。",
        f"到达 ready_for_review 后停止，等待 human review。",
    ])

    return "\n".join(lines)
