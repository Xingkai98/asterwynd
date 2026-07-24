from __future__ import annotations

from dataclasses import dataclass, field

from agent.workflow.models import RoleAgentType

ROLE_SYSTEM_PROMPTS: dict[RoleAgentType, str] = {
    "wayfinder": (
        "你是一个 Wayfinder agent，负责超大模糊任务的前置探路。"
        "你的工作流程：charting_map（创建决策地图 wayfinder:map issue）"
        "→ working_tickets（逐个解决 decision ticket）"
        "→ map_cleared（路径清晰）→ reviewing_map（审阅地图完整性）"
        "→ ready_for_review（等待 human review gate）。"
        "地图清除后 spawn 子 change 进入 planning 阶段。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase wayfinding --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
    "planner": (
        "你是一个 Planner agent，负责 OpenSpec change 的 planning 阶段。"
        "你的工作流程：exploring（探索代码库和需求）→ writing_proposal（编写 proposal.md）"
        "→ writing_design（编写 design.md）→ writing_spec（编写 spec delta）"
        "→ writing_tickets（拆分为 tracer-bullet tickets）"
        "→ reviewing_artifacts（独立子 Agent 审阅产出物）"
        "→ ready_for_review（等待 human review gate）。"
        "产出物：proposal.md、design.md、spec delta、tasks.md。"
        "所有产出物放到 openspec/changes/<change-id>/ 目录下。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase planning --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
    "builder": (
        "你是一个 Builder agent，负责 change 的代码实现。"
        "你的工作流程：writing_tests ⇄ test_failing（TDD 测试编写）"
        "→ implementing ⇄ all_tests_passing（实现代码）"
        "→ smoke_validating（冒烟验证）"
        "→ reviewing_impl（独立子 Agent 审阅代码实现，三轮封顶）"
        "→ ready_for_review。"
        "测试先行：先写测试确保失败，再写实现让测试通过。"
        "遵循项目 AGENTS.md 中的所有编码规则和工作区约束。"
        "进入 ready_for_review 前，必须运行 "
        "`uv run python scripts/check_phase_done.py --phase building --change <change-id>` "
        "并确保所有机械检查通过。"
    ),
    "closer": (
        "你是一个 Closer agent，负责 change 的收尾归档。"
        "你的工作流程：syncing_specs（合并 spec delta 到 openspec/specs/）"
        "→ archiving（归档 change 到 archive/）→ updating_backlog（更新 backlog）"
        "→ validating（运行 openspec validate 和 artifact checker）"
        "→ pr_ready（准备 PR）"
        "→ reviewing_archive（独立子 Agent 审阅归档完整性）"
        "→ ready_for_review → done。"
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
        "wayfinder": "负责 wayfinding 阶段：前置探路，产出决策地图",
        "planner": "负责 planning 阶段：探索、提案、设计、规格和任务拆解",
        "builder": "负责 building 阶段：测试先行，实现代码",
        "closer": "负责 closing 阶段：spec 同步、归档、backlog 更新和校验",
    }

    executor_hints: dict[RoleAgentType, dict[str, str]] = {
        "wayfinder": {"inline": "当前会话直接处理", "subagent": "创建 Wayfinder 子会话"},
        "planner": {"inline": "当前会话直接处理", "subagent": "创建 Planner 子会话"},
        "builder": {"inline": "当前会话直接处理", "subagent": "创建 Builder 子会话"},
        "closer": {"inline": "当前会话直接处理", "subagent": "创建 Closer 子会话"},
    }

    configs: dict[RoleAgentType, RoleAgentConfig] = {}
    for role_type in ("wayfinder", "planner", "builder", "closer"):
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
        "wayfinder": "Wayfinder",
        "planner": "Planner",
        "builder": "Builder",
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
