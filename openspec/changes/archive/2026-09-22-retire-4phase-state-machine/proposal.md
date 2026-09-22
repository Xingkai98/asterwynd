# Proposal: 四阶段状态机子系统退役（retire-4phase-state-machine）

关联跟踪 issue：[#227](https://github.com/Xingkai98/asterwynd/issues/227)（四个 legacy 子命令对当代 change 失效）、[#228](https://github.com/Xingkai98/asterwynd/issues/228)（当代 change 与 `handoff.json` 三层耦合）。两 issue 是同一根问题的两面，本 change 一并收口。

## Change Type

- primary: refactor
- secondary: []

## Why

AGENTS.md 已声明「旧的四阶段状态机仪式（phase/sub_state 推进、`handoff.json`、gate 停止）已停用」，但**代码里整套子系统仍在**，且实测是一具自洽的僵尸：

```
flow approve ──→ check_phase_done.py (591行) ──→ doc_artifact_protocol_openspec.py (731行)
     ↑                        ↑
  只被 AGENTS.md 文档        CI 不跑，只被 flow approve 调
  提到，无生产调用方
```

实测证据（盘点，见 `design.md` D1 完整表）：

- `check_phase_done.py` 除 `flow approve` 外**无调用方**，CI 无引用；
- `dispatcher.py` / `role_registry.py` **只有测试**；
- `discover` / `current` / `validate` / `spawn` 四个子命令**均无生产调用方**（`discover` 输出的 `approve_command` → `flow approve`、`spawn_command` → `spawn` 是**悬空指针**）；
- `flow approve` 在当代 change 上**必报错**（实测 `期望 gate planning.ready_for_review，实际 planning.exploring`）——无人推进 sub_state；
- 三个 `awaiting_*` 等待态**只由 `flow block` 自己写入**，活流程无一处使用。

保留它们的唯一效果是误导：`discover` 对当代 change 静默零输出（`active_count: 2` 但 `active_changes: []`）、`flow approve` 必报错、`spawn` 指向已停用阶段。

**本 change 的方向：整体退役**（用户 2026-09-22 拍板「全删，旧的更替掉」）。`discover` 独有的 `path`/`next_action`/`gate_check` 丰富输出作为可选增强，记 issue 留待日后（非本次范围）。

## 需求

1. **删除 legacy 子命令**：`workflow_state.py` 的 `discover` / `current` / `validate` / `spawn`。
2. **删除停用状态机的 gate 家族**：`flow approve` / `flow advance` / `flow block` / `flow confirm`（保留活的 `flow status`）。
3. **删除其专属实现**：`scripts/check_phase_done.py`、`agent/workflow/doc_artifact_protocol.py`、`doc_artifact_protocol_openspec.py`、`dispatcher.py`、`role_registry.py` 及对应测试。
4. **消除 `handoff.json` 耦合**（#228 三层）：
   - 层 1：`_refresh_workflow_state` 不再映射写 `handoff.json`（gate 家族删除后无人再要求它）；
   - 层 2：随 `check_phase_done` / `doc_artifact_protocol` 删除自然消失（协议的 `FileRequirement(handoff.json)` 是其唯一来源）；
   - 层 3：`handoff.json` / `workflow-state.json` 落 `.gitignore`。
5. **同步文档与规则**：`AGENTS.md`（删 flow 家族命令段、改「不删 phase/sub_state 段」的显式规则）、`docs/requirements-process.md`（停用四阶段描述）、`docs/development-guide.md`。
6. **处置 benchmark 任务** `benchmarks/tasks/asterwynd-b03-awaiting-grill-state/`（其 `test_command` 指向的状态机生命周期测试将随子系统消失）——处置方式见 D3（grill 裁定）。
7. **`workflow_methods.json` 的 phase/sub_state 段**：删除 `discover` 后无代码读者，随之清理；但需同步改 `AGENTS.md:213` 的「**不删 phase/sub_state 段**」显式规则与 `test_declarative_flow_engine.py:352-373` 的兼容测试（见 D4）。

## 背景

本 change 由 #227 + #228 合并而来。盘点（2026-09-22，主 session 实测）显示两者不是「修 4 个 CLI 子命令」，而是**整个四阶段状态机子系统退役**——规模远超原 issue 描述，故按架构级 change 走全流程（含 grill）。

## 非目标

- **不动 `agent/workflow/event_log.py` 与 `state_machine.py` 的活的部分**：`event_log.py` 是当代投影与事件的核心（`verify_projection` 被 checker 使用），**保留**。`state_machine.py` 中服务于 `init_handoff_json` / `StateMachineError` 的部分仍需评估（见 D2）。
- **不动 `flow/` 声明式引擎的存废**——这是本 change 最大的待定项（见 D2），由 grill 裁定。
- 不新增能力（如 `discover` 的 `path`/`next_action` 输出迁移到 `flow status`）——记 issue 日后可选。
- 不改 `flow status`（它是活的，`AGENTS.md:195` 与多处测试依赖）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 开发流程 CLI | `workflow_state.py` 删除 8 个子命令（4 legacy + 4 gate 家族），保留 `flow status` / `artifact-event` / `review-manifest` / `policy-*` |
| 代码删除 | `check_phase_done.py`(591) + `doc_artifact_protocol*.py`(845) + `dispatcher.py`(243) + `role_registry.py`(154) + `workflow_state.py` 内 legacy 段 ≈ **1800+ 行** |
| 测试删除/改写 | 约 850 行（`test_check_phase_done.py` 487 + `test_dispatcher.py` 254 + `test_role_registry.py` 112 + `test_workflow_state_cli.py` 部分 + `test_declarative_flow_engine.py` 部分） |
| **CI 门禁（净损失）** | `check_phase_done.py` 承载的「100% 要求全勾」与 TODO 残留扫描（`_find_todo_residuals` / `_load_known_debt`）**在新机制中无等价替代**：checker 的 `requires_building_review` 由 `_tasks_all_complete` 驱动（不勾即绕开），`SELF_ADMITTED_INCOMPLETE_PHRASES` 只扫自认未完成短语。属能力面净损失，**放大 issue #235**——处置见 D9（迁入 checker 或记 `docs/known-debt.md`） |
| `handoff.json` 耦合 | 三层全消（#228） |
| `workflow_methods.json` | phase/sub_state 段删除（随 `discover`）；`review_protocol` 段无代码读者、可去可留（见 D4） |
| Benchmark | 1 个 B-track 任务可能作废（见 D3） |
| Guard / flow-policy | `workflow_guard.py` 白名单含 `flow (status|confirm|approve|block|advance)` → 需收窄为 `flow status`（受保护路径规则表 `flow-policy.json` 同步） |
| Specs | `dev-workflow-state-machine`（四阶段状态机、合法流转表、handoff schema、flow 命令等 Requirement 需 MODIFIED/REMOVED）；`change-documentation`（如涉及）；`flow-policy.json` 改动须走 `policy-set` CLI |
| Docs | `AGENTS.md`（flow 命令段 + phase 段规则）、`docs/requirements-process.md`（四阶段描述漂移）、`docs/development-guide.md` |
| Migration / compatibility | 无生产调用方，不破坏活流程；`flow status` 与事件投影不受影响 |
| 明确不受影响 | AgentLoop、ToolRegistry、Web UI、subagent 编排、benchmark harness、记忆系统、`flow status` 投影 |

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 架构级改造（删除约 1800 行子系统 + 动受保护 spec 与 AGENTS.md 显式规则）。需对标「已停用机制的退役实践」——如何在不破坏活路径的前提下移除死代码、如何处置其测试资产与文档规则。属 grill 档（非平凡 change）。
- research questions:
  - 删除 CLI 子命令的兼容性策略（硬删 vs 保留 stub 报错 vs deprecation 期）在此场景下哪种合适？
  - 成熟项目退役一个已停用子系统时，如何处理「测试资产」——直接删除，还是保留为「已删除行为的负向回归测试」？
  - 当 parity 测试的一半被删除时（`flow/engine.py` 对照 `state_machine.py`），CI 门的正确处置是什么？
- findings:
  - **业界层（deprecation 实践）**：公开 CLI 的成文实践（GNU Guix 政策、Azure/AWS CLI breaking-change 流程）普遍要求「先弃用、保留可用期（Guix 明确 ≥1 年）、打迁移警告、绑定大版本移除」。**关键对照**：这套流程的**唯一目的是保护外部消费者**——Guix 原文即以「subcommand 应被视为永久可用」为前提，并建议移除前做用户调查。本仓库的这 8 个子命令**零外部消费者、零生产调用方**（实测），前提不成立，缓释期是纯粹的成本而非保护。业界亦有「移除冗余向后兼容桥」的直删范式（vm0 的 `vm0 zero` epic：目标是删除"redundant backward-compatibility bridge"以减少维护负担与用户困惑），与本场景同形。
  - **本地参考仓库层**：`.dev/reference-repos.txt` 不存在，无可比对外部仓库。改用**仓库内先例**（更强，因同仓库同文件）：`flow-event-projection`（归档 `2026-08-15`）已就**同类决策**达成用户裁决——其 grill Q2 原文「废旧 `advance`/`approve` 的处理——直接删除还是保留兼容提示？」，用户答复记录在 `reviews/grill-design.md` 的 `## User Confirmation`：「**废旧 advance/approve 直接删除，不留兼容 stub**，全部迁移到 flow 命令（discover 输出 approve_command 改指 flow，4 个 CLI 测试同步更新）」。该次删除**已成功落地**（现 `workflow_state.py` 中确无 `cmd_approve`/`cmd_advance`），并确立了配套纪律：**删除子命令必须同步改 `discover` 输出（否则输出指向不存在的命令）与删/改测试**。
  - **对「测试资产」的处置**：仓库先例的做法是**同步删除/改写测试**（`flow-event-projection` 删 4 个 advance/approve CLI 测试）；未采用「保留为负向回归测试」。本 change 额外补一条**负向回归**（调用已删子命令应以明确错误退出），以覆盖「静默成功」这一比"命令消失"更坏的失败模式。
- design impact:
  - **退役策略取「硬删」**，不设 deprecation 期、不留兼容 stub——依据是仓库内同文件先例的用户裁决（`flow-event-projection` Q2）+ 零消费者事实；业界缓释期范式在无外部消费者时不适用。
  - **测试处置**：随子命令删除对应测试；另补负向回归（已删子命令 → 明确错误退出，非静默成功）。
  - **删除的配套面已由先例圈定**：同步改 `discover` 输出引用（本 change 中 `discover` 整体删除，悬空指针自然消失）+ 同步改 guard 白名单（`flow-policy.json`）。
  - 待定项（`flow/` 引擎存废、benchmark 任务处置、`workflow_methods.json` phase 段）见 `design.md` D2/D3/D4，交 grill 裁定。

## 测试计划

- 删除对应测试（`test_check_phase_done.py`、`test_dispatcher.py`、`test_role_registry.py` 及 `test_workflow_state_cli.py` / `test_declarative_flow_engine.py` 的 legacy 用例）。
- **新增负向回归**：被删子命令调用时 CLI 以明确错误退出（argparse 未知子命令），而非静默成功。
- 活路径回归：`flow status` / `artifact-event` / `review-manifest` / `policy-*` 全绿；`tests/test_workflow_protected_write_channel.py`（14 条）不受影响。
- `handoff.json` 不再被自愈产出（`flow status` 后目录无该文件）。
- guard 白名单收窄后，`flow status` 仍被豁免、已删子命令不再出现于白名单。
- 全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker。
