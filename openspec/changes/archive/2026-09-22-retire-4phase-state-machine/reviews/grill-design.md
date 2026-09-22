# Grill: retire-4phase-state-machine 设计追问

## Reviewer

- run id: grill-zero-memory
- 时间: 2026-09-22
- 零记忆声明: 本报告由不继承开发上下文的独立 subagent 产出，所有事实经工具实测复核（grep/read/git worktree/pytest 实跑），不采信 design.md 的转述。

## Confirmed Decisions

- **决策**: D2 取 (a) 全删 `flow/`（`engine.py` + `statechart.json` + `tests/test_declarative_flow_engine.py`）；`state_machine.py` 的 `validate_transition` **必须保留**（被活 `event_log.py:12→:540 _validate_transition_dict` 依赖），且 `compute_next_hints` / `get_legal_targets` / `get_recommended_role` / `_is_gate` / `WITHIN_PHASE_ADJACENT` / `CROSS_PHASE_FORWARD` 作为其**传递闭包**一并保留——但删 `flow/` 后 `state_machine.py` 里的四阶段转移表（`WITHIN_PHASE_ADJACENT`/`CROSS_PHASE_FORWARD`/`PHASE_SUB_STATES`）仍全量留存，故失去的 parity 链只是「statechart 与 Python 常量必须同步」这一条**冗余声明约束**，不是四阶段模型本身；缓释 = `tests/agent/workflow/test_state_machine.py`（459 行符号级单测）继续直接 pin 住这些常量与转移语义。理由: 实测 `flow/engine.py` 唯一消费者是 parity 测试（`grep -rn 'flow.engine\|FlowEngine'` 全仓仅命中 `tests/test_declarative_flow_engine.py` 与 `AGENTS.md`/归档文档）；保留 statechart 等于让一个**活符号**（`validate_transition`）永久被 31 个已停用状态钉住，未来任何 gen-1 replay 语义微调都要连带改退役声明。来源: grill-zero-memory

- **决策**: D3 裁定 **(a) 随子系统删除**，但 design.md D3 的裁定**理由必须重写**——实测证明「该函数现已不存在（0 命中）→ 任务在本次删除前就已失效」这一前提是**错的**。`test_awaiting_grill_confirmation_wired_end_to_end` 由该任务自己的 `test.patch` **新增**（`test.patch` 内 `+    def test_awaiting_...`），HEAD 0 命中是 SWE-bench 式任务的**设计使然**。真实理由：该任务的目标能力面（statechart 新增 awaiting 态 + 引擎驱动 flow 生命周期 + `flow block`/`flow confirm` 恢复默认值表）**正是本 change 要退役的对象**，任务在 `base_commit` 597d121 上仍可自洽复现（实测 test.patch 红 → +gold.patch 绿），但退役后已无教学/评测意义。数字影响（实测非转述）：本地任务 34 → 33（A 轨 22 不变，B 轨 12 → 11）；Verified 38 不变；task.json 目录总数 72 → 71；`benchmarks/tasks/manifest.json` `coverage` 段 34 → 33 条。来源: grill-zero-memory

- **决策**: D5 的符号切分必须**比 design.md 的版本更保守**：`get_legal_targets` / `get_recommended_role` / `_is_gate` / `WITHIN_PHASE_ADJACENT` / `CROSS_PHASE_FORWARD` / `_phase_index` / `_validate_sub_state` **全部保留**（design.md 把 `get_recommended_role` 标为「评估」是错的）。理由: 活 `event_log.py:286` 调 `compute_next_hints`，后者在 `state_machine.py:449-453` 调 `get_recommended_role` 与 `get_legal_targets`，`get_legal_targets` 又调 `_is_gate` 并读 `WITHIN_PHASE_ADJACENT`/`CROSS_PHASE_FORWARD`——这是一条**活调用链**（实测在真实归档 gen-1 change 上 0 触发，因为仓库当前**没有任何 `transition_applied` 事件**：`grep` 全部 `workflow-events.jsonl` 命中 0；但 checker 的 `_check_archived_projectable`（`check_openspec_artifacts.py:1057`）对**每一个**归档 change 跑 `project_workflow_state`，任何 gen-1 change 一旦含 `transition_applied` 事件即走 `replay_handoff_projection → _apply_transition_event → compute_next_hints` 并 AttributeError）。这是「0 命中 ≠ 死代码」的典型陷阱。来源: grill-zero-memory

- **决策**: D7 的**机制描述错误**，必须改：`flow (status|confirm|approve|block|advance)` 白名单**不在** `scripts/flow-policy.json`，而在 `scripts/workflow_guard.py:266-274` 的 `_is_privileged_cli` **硬编码正则**里（实测 `flow-policy.json` 全文无 `flow`/子命令字样）。`policy-set` CLI 只写 `protected_paths` 数组（`workflow_state.py:1238-1285`），**改不到该正则**；`flow-policy.json` 本次**无需任何改动**。收窄 = 直接改 `workflow_guard.py` 的正则为 `flow\s+status`（该文件不在受保护路径，agent 可直改）+ 改 `tests/test_workflow_guard.py:552-566` 的 `test_guard_allows_flow_cli_commands`（现断言 4 条命令豁免，收窄后 3 条应转为「拒绝豁免」断言）。来源: grill-zero-memory

- **决策**: D8 的 spec delta **不满足** `openspec archive` 的整段替换语义，必须重做（详见下表）。10 条 Requirement 名与正式 spec **逐字全匹配**（含「阻塞状态」——历史上误写为「四阶段阻塞状态」的错误在本 delta **不存在**，实测通过）；但 **MODIFIED 段把 10 条仍活的 Scenario 静默删除**（其中 8 条有活代码/活测试支撑），且 delta **漏列 5 条应 REMOVED 的 Requirement**。裁定：MODIFIED 必须改为「变更后完整正文」并把仍活 Scenario 保留改写；5 条漏列 Requirement 全部 REMOVED；`阻塞状态` 的 REMOVED 必须先**迁出** 2 条活 Scenario。来源: grill-zero-memory

- **决策**: D9 取 **(b) 显式接受能力面消失 + 记 `docs/known-debt.md`**，不迁入 `check_openspec_artifacts`。理由: 本 change 的性质是「退役」，迁入两项检查属**新增能力面**、扩大变更边界，且 `_find_todo_residuals` 依赖 `git diff origin/master`（`check_phase_done.py:200`）在 checker 的 `--base-ref` 语境下语义不同，移植需重新设计而非搬运。但「显式接受」必须**具体**：debt 条目须写明失去的是哪两项、各自的触发条件、以及 #235 是收口入口。两项断言已实测成立（见下）。来源: grill-zero-memory

## D5 逐符号保留/删除清单（实测消费者）

`agent/workflow/state_machine.py`（459 行）。

| 符号（行） | 处置 | 依据（文件:行号） |
|---|---|---|
| `StateMachineError` (:32) | **保留** | `agent/workflow/event_log.py:10`（活）；`scripts/workflow_state.py:73` |
| `_validate_phase` (:36) | **删除** | 仅 `_validate_handoff_json_structure:336`（同删）+ `tests/agent/workflow/test_state_machine.py:29,34` |
| `_validate_sub_state` (:42) | **保留** | `validate_transition:126,128,206`（活链） |
| `_is_gate` (:55) | **保留** | `compute_next_hints:452`（活链，design.md 未列） |
| `_phase_index` (:59) | **保留** | `validate_transition:197`（活链） |
| `CROSS_PHASE_FORWARD` (:64) | **保留** | `validate_transition:216`；`get_legal_targets:248`（活链）。注：`workflow_state.py:693` 的消费者 `cmd_flow_approve` 将删 |
| `WITHIN_PHASE_ADJACENT` (:80) | **保留** | `validate_transition:183`；`get_legal_targets:238`（活链） |
| `validate_transition` (:118) | **保留** | `event_log.py:12`→`:540` `_validate_transition_dict`（活） |
| `get_legal_targets` (:227) | **保留** | `compute_next_hints:453`（活链，design.md 列为「评估」→ **纠正为保留**） |
| `create_transition` (:254) | **删除** | 仅 `manager.py:168`（同删）+ `test_state_machine.py:190,203,213` |
| `init_handoff_json` (:281) | **删除** | 仅 `workflow_state.py:1031`(cmd_spawn 同删) + `manager.py:71` + `__init__.py:48` + 3 个测试文件 |
| `load_handoff_json` (:308) | **删除** | 仅 `manager.py:78` + `__init__.py:49` |
| `save_handoff_json` (:318) | **删除** | 仅 `manager.py:72,186,315,327,352` + `__init__.py:50` + `test_dispatcher.py:121` |
| `_validate_handoff_json_structure` (:326) | **删除** | 仅 `load_handoff_json:314`（同删） |
| `apply_transition` (:345) | **删除** | 仅 `manager.py:181` + `test_state_machine.py:195,208,219`。注：`flow/engine.py:412` 有**同名不同物**的 `FlowEngine.apply_transition`，随 `flow/` 删 |
| `enter_blocked` (:371) | **删除** | 仅 `manager.py:314` |
| `resolve_blocked` (:405) | **删除** | 仅 `manager.py:326` |
| `get_recommended_role` (:437) | **保留** | `compute_next_hints:449`（活链，design.md 列为「评估」→ **纠正为保留**） |
| `compute_next_hints` (:444) | **保留** | `event_log.py:11`→`:286`（活） |

`RoleAgentType` 定义在 `agent/workflow/models.py:26`（**不在** `state_machine.py`）。`PHASE_TO_ROLE: dict[Phase, RoleAgentType]`（`models.py:38`）被活链 `get_recommended_role:441` 使用，故 `RoleAgentType` 与 `models.py` 一并**保留**。

**`init_handoff_json` 删除后两条活测试的种子改法**（实测已跑通）：把 `init_handoff_json(cid)` 换成等价字面量

```python
{"schema_version": "1.0", "change_id": cid,
 "state": {"phase": "planning", "sub_state": "exploring"},
 "transitions": [], "current_agent": None, "last_gate": None,
 "blockers": [], "routing": {}, "next_hints": {}}
```

- `tests/test_workflow_protected_write_channel.py:26,71`（`_seed_gen1_change`）
- `tests/test_workflow_state_cli.py:13,229,259` — 但 `:229`/`:259` 属 `test_spawn_*` 两个用例，随 `cmd_spawn` 删除而整段删除；实际只需改 `:13` 一处 import。

实测验证：用上述字面量造 gen-1 种子后，`project_workflow_state` 正常投影（`planning.exploring`）、`verify_projection == []`、`verify_handoff_projection == []`——即字典形状与 `init_handoff_json` 输出在该 replay 路径上等价。

## D8 逐 Requirement 处置清单（22 条）

名字核对：delta 的 10 条 `### Requirement:` 名与正式 spec **逐字全匹配**（Python 集合比对，0 mismatch）。「阻塞状态」等曾出问题的名字本次**正确**。

| # | 正式 spec 名（行号） | 处置 | 理由 |
|---|---|---|---|
| 1 | 工作流事件日志与 handoff.json projection (:7) | **MODIFIED** | 去 handoff 映射；但 delta 正文不完整（见下） |
| 2 | Protected artifact 变更解释 (:108) | 保留不动 | 纯活：`flow-policy.json` 事件门禁，checker 在用 |
| 3 | Review evidence manifest (:140) | 保留不动 | 纯活：#232 归档校验 |
| 4 | Workflow 总开关 (:181) | **MODIFIED** | 去 `discover`/`check_phase_done`/`WorkflowDispatcher` 引用；delta 正文不完整（见下） |
| 5 | 四阶段生命周期 (:215) | **REMOVED** | 四阶段本体 |
| 6 | Phase 内部 sub_state 定义 (:241) | **REMOVED** | 同上 |
| 7 | Human review gate (:276) | **REMOVED** | gate 家族删除 |
| 8 | Agent 间 handoff (:304) | **REMOVED（delta 漏列！）** | handoff note 机制退役；`handoff_note.py` 实测零消费者 |
| 9 | handoff.json schema (:335) | **REMOVED（delta 漏列！）** | `handoff.json` 退役（#228 三层全消） |
| 10 | 合法流转表 (:384) | **REMOVED（delta 漏列！）** | 四阶段流转表；`flow approve`/`advance` 删除 |
| 11 | 流程状态机声明化 (:417) | **REMOVED（delta 漏列！）** | `flow/statechart.json` 随 D2(a) 删除 |
| 12 | 状态机声明与执行方法分工 (:442) | **REMOVED（delta 漏列！）** | 同上，声明文件不存在则分工无对象 |
| 13 | 角色 Agent 类型 (:458) | **REMOVED**（delta 已列） | `role_registry.py` 删除 |
| 14 | 单 Agent 全流程兼容 (:490) | **REMOVED**（delta 已列） | 四阶段语义 |
| 15 | 路由配置 (:510) | **REMOVED**（delta 已列） | `handoff.json.routing` 退役 |
| 16 | 阻塞状态 (:589) | **REMOVED（但须先迁出 2 条活 Scenario）** | 见下 |
| 17 | flow 命令与受保护路径 (:630) | **MODIFIED** | 收窄为 `flow status`；delta 正文不完整 |
| 18 | 开发流程精简为 OpenSpec 主干 + 强制审阅闭环 (:654) | 保留不动 | 活口径，已在 AGENTS.md 落地 |
| 19 | 开发流程策略单一源 (:679) | 保留不动 | `flow-policy.json` 单一源，活 |
| 20 | guard 写操作门禁顺序与路径归一化 (:702) | **MODIFIED（delta 漏列）** | `:704` 正文含 `flow (status\|confirm\|approve\|block\|advance)` 豁免清单 → 须随 D7 收窄为 `flow status`。**这是 delta 漏掉的一处 MODIFIED** |
| 21 | 内容门槛阶段感知 (:724) | 保留不动 | 活：checker 内容门槛 |
| 22 | 阶段执行者 agent schema 定义 (:741) | **保留不动**（不建议 REMOVED） | 该 Requirement 定义的是 `flow-policy.json` 的 `phases.<phase>.agent` / `review.agent` **schema**，由 checker 做结构校验（`test_checker_agent_schema_validation` 活）。它挂在 `flow-policy.json`，不挂 `role_registry.py`——`role_registry` 删除**不**使其失去对象。design.md 的「（评估）」应裁定为保留 |

### delta 正文不完整的实测证据（MODIFIED 段逐 Scenario 比对）

`openspec archive` 是整段替换，delta 未列出的 Scenario 会被**静默删除**。实测丢失：

**`工作流事件日志与 handoff.json projection`**：正式 13 个 Scenario → delta 5 个，**丢 10 个**，其中**仍活**的有 7 条：`当代 change 投影为 workflow-state.json`（形状断言 `source_event_seq`/无 `updated_at`）、`投影被手动篡改`（checker `verify_projection` 在用）、`非状态 artifact 事件`（`ALLOWED_PROTECTED_ARTIFACT_EVENT_TYPES`）、`新建 change 时初始化 workflow event log`、`老世代 change 仍可投影`、**`受保护写通道拒绝非法目标`**（`tests/test_workflow_protected_write_channel.py:220+` 专测）、**`受保护写通道拒绝归档语境下的非法 change id`**（`tests/test_workflow_archive_write_channel.py` 专测）。仅 2 条真死（`WorkflowEngine 更新状态`、`agent 读取当前状态`）+ 1 条被 delta 的 `受保护写通道支持已归档 change` 覆盖。

**`Workflow 总开关`**：正式 4 → delta 2，**丢 4 个**，其中 2 条**仍活**：`禁用期间存在未恢复改动`、`禁用期间改动被恢复确认`——`disable`/`enable`/`resume-audit` 明确是**保留**的活命令（`workflow_state.py:469-541`），这两条 Scenario 是其唯一规格来源。仅 1 条真死（`workflow 未启用时不暴露活跃 change`，因 `discover` 删除）。

**`flow 命令与受保护路径`**：正式 3 → delta 3，但**全量替换**：丢 `flow status 展示投影`（**活**，含 stale 提示、自愈重建、「事件不完整，检查 seq N」三条语义，delta 的替代 Scenario 只覆盖了「返回投影状态」）、`受保护路径只准 CLI 写`（**活**，guard `cli_written` 规则 + `test_guard_blocks_direct_writes_to_protected_files`）。仅 `flow block / flow advance` 真死。

**`阻塞状态`**（整条 REMOVED）：含 2 条**仍活** Scenario，删 Requirement 即删规格。① `checker 派生物一致性`（投影 == replay，`check_openspec_artifacts.py:957-961` 在用）；② `guard 读投影执法`（awaiting 期间写操作 exit 2、事件日志为唯一真相、fail-closed），`tests/test_workflow_guard.py:396-537` 有 **10 条活测试**专测。**必须先把这 2 条迁入保留的 Requirement**（建议并入 `Protected artifact 变更解释` 或独立新 Requirement），否则本退役会把「awaiting 执法不弱化」从规格里抹掉却保留其实现与测试。

## D6 层 1/层 3 落地后的失效面与改法

**层 1 改点精确**：`_refresh_workflow_state`（`workflow_state.py:977-992`）尾部 6 行（构造 `handoff` dict + `_atomic_write_json(change_dir/"handoff.json", handoff)`）删除。**调用点不变**：`:836`（`_flow_status_projection` 自愈）与 `:974`（`_flow_refresh_after_event` gen-2 分支）——两者都只应写 `workflow-state.json`。
**不要动** `_flow_refresh_after_event` 的 **gen-1 分支**（`:968-972`，`_save_handoff(replay_handoff_projection(...))`）：那写的是 gen-1 的**唯一投影**，不是 #228 说的「映射写」。design.md 的表述（「不再映射写 handoff.json」）需限定为 **gen-2 映射**。

实测（本 grill 亲历）：在 change 目录跑一次 `flow status` 即产出 `handoff.json` + `workflow-state.json` 两个 untracked 文件——即 #228 层 1 的现场复现（`git status` 显示 `?? openspec/changes/.../handoff.json`）。**这也是层 1 判别性测试的最强形式**。

| 失效面 | 现状 | 改法 |
|---|---|---|
| `tests/test_workflow_protected_write_channel.py` docstring :11-14 第 3 条（「不得先跑 flow status…会凭空写出 handoff.json」） | 改后该约束**失去理由**（自愈不再写 handoff） | 改写 docstring 第 3 条为「自愈已不写 handoff.json，本约束不再必要；改断言**写入后**仍无 handoff 以 pin 住层 1」 |
| 同文件 :149/:162/:178/:192/:213 `assert not (change_dir/"handoff.json").exists()`（**调用前**冷状态） | 仍成立但**退化为恒真**，判别力归零 | **保留**该前置（无害）并**新增调用后断言** `assert not (change_dir/"handoff.json").exists()` + `assert (change_dir/"workflow-state.json").exists()`——后者是层 1 的新判别点（去掉层 1 改动 → 变红） |
| 同文件 :192/:213「老世代兼容」两用例（gen-1 仍须有 handoff.json） | 仍活，是 gen-1 行为的**唯一** pin | **不动**，作为「gen-1 不受层 1 影响」的判别性证据 |
| `tests/test_workflow_archive_write_channel.py:32` `HOLLOW_PROJECTIONS` + :125/:140/:154/:197-217 | 全部**仍成立**（归档写通道本就跳过刷新，与层 1 正交） | **不改**。:197-217 `test_archived_write_supports_gen1_change_with_only_handoff` 依赖 `_require_change_target` 的 `or handoff.json` 分支 → 见下 |
| `tests/test_openspec_artifact_checker.py:1754` 注释「flow status 会同步映射写 handoff.json」 | 仅**注释**陈述来源，断言对象是 `workflow-state.json` 的 replay 一致性（`_check_handoff_json`） | 改注释；断言不动（用例从不跑 flow status） |
| `tests/test_openspec_artifact_checker.py:148-161` `test_check_change_rejects_handoff_projection_mismatch` | 测的是 checker 的 handoff 校验（`_check_handoff_json`，gen-1 分支） | **不改**（gen-1 校验存活） |

**`_require_change_target`（:878-938）的 `or handoff.json` 分支**：实测「只有 handoff.json、无 proposal.md」的 change 在**当前仓库为 0 个**——5 个 tracked `handoff.json` 全部同时有 `proposal.md`；active change 无一有 `handoff.json`。但 `cmd_spawn` 删除**不等于**历史上没有 spawn 子 change：归档目录里可能存在，且该分支是 `test_archived_write_supports_gen1_change_with_only_handoff` 与 `test_spawn_style_child_without_proposal_still_writable` 的被测对象。**裁定：保留该分支**（零成本、保护历史 gen-1 change 可写性；删它会让两个活测试变红且无收益）。相应地把 `_require_change_target` docstring 里「`cmd_spawn` 生成的子 change」的**举例**改为「历史 spawn 子 change」，spec delta :51 的「`proposal.md` 或 `handoff.json`」措辞**保留**。

**`event_log.py` 的 `verify_handoff_projection` / `replay_handoff_projection` / `project_workflow_state`**：**都不写盘**（纯函数，实测 `verify_projection == []` 无副作用）；三者在 gen-1 路径上仍被 checker 使用（`_check_archived_projectable`、`_check_handoff_json`），**全部保留**。写盘只发生在 `workflow_state.py` 的 `_refresh_workflow_state` / `_save_handoff`，正是层 1 的唯一改点。

**层 3 `.gitignore`**：实测当前 `.gitignore:22` 只有 `.handoff/`；`git check-ignore` 对 `openspec/changes/foo/handoff.json` 与 `.../workflow-state.json` 均返回「未忽略」。需新增两条（建议 `**/handoff.json`、`**/workflow-state.json` 形式的 glob，或精确到 `openspec/changes/**/`）。**注意排除面**：`git ls-files` 显示 5 个归档 `handoff.json` 与 1 个归档 `workflow-state.json` **已被 git 跟踪**；`.gitignore` 不影响已跟踪文件，但若用宽 glob，需确认不会让未来「归档 change 的投影」被静默忽略（`docs/known-debt.md` 已记录该口径限定）。

## D9 净损失裁定（实测复核）

两个「无等价替代」断言**均成立**，且比 design.md 描述更明确：

1. **「100% 全勾」**：真正的实现是 `doc_artifact_protocol_openspec.py:123-125` 的 `ContentRequirement(..., "checkboxes_all_checked", description="All task checkboxes must be [x]")` + `:356-375` 的实测逻辑（**不是** `check_phase_done.py` 自身——design.md 归因略有偏差，但删除面包含该文件，结论不变）。对照 `check_openspec_artifacts.py:1027-1033` 的 `requires_building_review = not archived and primary != "docs" and _changed_capabilities(...) and _tasks_all_complete(change_dir)`——`_tasks_all_complete`（:982）是**触发器**：tasks 未全勾 → 整个分支不进入 → 无任何检查。故「不勾即绕开」成立。
2. **TODO 残留扫描**：`check_phase_done.py:210 _find_todo_residuals` + `:183 _load_known_debt`（对 `docs/known-debt.md` 比对），在 `:455-465` 参与 building 机械检查，只扫 `git diff --name-only origin/master -- '*.py'`（`:200`）。对照 `check_openspec_artifacts.py:92-99 SELF_ADMITTED_INCOMPLETE_PHRASES`——只扫**自认未完成短语**（`尚未完成`/`待补充`/`待调研`/`tbd`/`todo`/`待确认`）且只作用于 `Reference Implementation Research` 的特定字段（`:585-598`）。**子集关系成立**：`todo` 短语检查 ⊂ TODO 标记检查，但**覆盖面差异是结构性的**（前者只查一个 section 的散文，后者查全部改动过的 .py 源码行）。

**裁定 (b)**：显式接受消失，写入 `docs/known-debt.md` 新条目（配 `protected_artifact_explained` 事件），内容须含：失去的两项能力、各自的触发条件、与 #235 的关联、以及「退役前 = 旧机制兜底 + 新层更薄；退役后 = 只剩薄层」的定性。**反对 (a) 的理由**：`_find_todo_residuals` 依赖 `git diff origin/master`，而 checker 走 `--base-ref`（CI 传 `${{ github.event.pull_request.base.sha }}`，`.github/workflows/ci.yml:53-62`），直接搬运会在 CI 上退化为「与 master 比」的语义漂移；正确移植需要重新设计 diff 基线，属新增能力面而非退役配套。

## Open Questions

- **Q1（D8 — spec 正文补全的工作量边界）**：MODIFIED 段要求「变更后完整正文」，实测 `工作流事件日志与 handoff.json projection` 现状 87 行、delta 只有 31 行。具体场景：正式 spec 第 78-90 行的 `受保护写通道支持已归档 change` Scenario 有 6 条 `AND`（含「不触发投影刷新」「归档目录不得新增投影文件」「不因不一致而失败」），delta 版只有 3 条。若照现状归档，`openspec archive` 会把这些 `AND` 从正式规格里删掉——而 `tests/test_workflow_archive_write_channel.py` 的 4 条活测试仍会断言它们。**请确认**：是把 delta 的三条 MODIFIED 全部补成「原正文 + 本 change 的最小改动」的完整正文（我推荐这条，工作量约 120 行 diff），还是接受这些 Scenario 细节从规格消失（则须同步删除对应活测试，等于主动降低规格覆盖面）？

- **Q2（D9 — 净损失的处置方式）**：具体场景：假设本 change 合入后，某个后续 change 在 `agent/foo.py` 第 42 行留下 `# TODO: 处理边界` 且 tasks.md 全部勾选。退役前：`flow approve --phase building` 会调 `check_phase_done` 报「发现 1 处 TODO/TBD/FIXME/HACK 残留」并拒绝批准。退役后：`check_openspec_artifacts.py` 的 `SELF_ADMITTED_INCOMPLETE_PHRASES` 只扫 `Reference Implementation Research` 的 `findings` 等字段，**扫不到源码行**，PR 照常合入。**请确认**：接受这个具体退化并在 `docs/known-debt.md` 记明（我推荐），还是要求本 change 顺带把 TODO 扫描移植进 checker（则本 change 从「净删除 ~2650 行」变成「净删除 + 新增一项 CI 检查」，性质改变）？

- **Q3（D2 — 删除 `flow/` 后是否连带清理 `agent/workflow/routing.py` 的死函数）**：具体场景：删 `manager.py`/`dispatcher.py`/`__init__.py` 的导出后，`routing.py` 里 `load_global_defaults`（:76）、`merge_routing`（:154）、`get_routing_for_phase`（:184）、`build_routing_config_prompt`（:201）、`RoutingConfigError`（:72）、`_parse_routing_dict`/`_parse_phase_routing`/`_apply_degradation`/`routing_to_dict` 全部失去生产消费者，只剩 `is_workflow_enabled`（:47，被活 `workflow_state.py:65` 与 `resume_audit.py:16` 的 `load_workflow_methods` 使用）。**请确认**：是「最小删除面」（只删 design.md 列出的文件，`routing.py` 原样保留，含约 180 行死函数），还是「深挖一层」（同 change 内把 `routing.py` 裁到 `load_workflow_methods` + `is_workflow_enabled` 两个函数）？我倾向后者但需用户拍板，因为它扩大了删除面且会使 `tests/agent/workflow/test_routing.py` 整文件失效。

## User Confirmation

- **Q1**: 用户答复：选 A——把 4 条 MODIFIED 全部补成「原正文 + 本 change 最小改动」的**完整正文**（约 120 行 diff），保证**零 Scenario 丢失**。主 session 复核确认现 delta 在 MODIFIED 段净丢 10 条 Scenario（事件日志投影 13→5、Workflow 总开关 4→2），其中若干有活测试（`test_workflow_archive_write_channel.py`）仍在断言；补全后须重跑 Scenario 数核对（**不得少于**正式 spec 对应条目）；确认时间: 2026-09-22
- **Q2**: 用户答复：选 A——接受 TODO 扫描消失的退化并在 `docs/known-debt.md` 记明（写明失去哪两项、触发条件、#235 是收口入口）。保持本 change「净删除」性质，不顺带移植 checker；确认时间: 2026-09-22
- **Q3**: 用户答复：选 A（最小删除面）——`routing.py` 原样保留，本 change 不清理；死函数**记 issue #239** 单独跟踪（已开：https://github.com/Xingkai98/asterwynd/issues/239，含实测符号清单与「等本 change 合入后再做」的前置）；确认时间: 2026-09-22

## 风险

- **【高】`agent/workflow/__init__.py` 是包的 `__init__`，删 `dispatcher.py`/`role_registry.py` 会打崩活路径**。`agent/workflow/__init__.py:1` `from agent.workflow.dispatcher import ...`、`:26` `from agent.workflow.role_registry import ...`、`:2` `from agent.workflow.manager import WorkflowManager`（全在删除面）。Python 在导入**任何子模块**时先执行包的 `__init__.py`——因此 checker 的 `from agent.workflow.event_log import verify_projection`（`check_openspec_artifacts.py:959`）与 guard 的 `from agent.workflow.event_log import is_awaiting_state, project_workflow_state`（`workflow_guard.py:552`）**都会先跑 `__init__.py`**，删文件不删导出即 `ModuleNotFoundError`，直接打崩 CI 与 PreToolUse 门禁。design.md D1 删除面**未列** `__init__.py` 的导出行；tasks.md:14 只写「及 `agent/workflow/__init__.py` 的导出」，粒度不足以拦住这个陷阱。**改法**：同一步删除 `__init__.py` 第 1、2、26-31、36-38（routing 中死亡部分）、45-52（state_machine 中删除部分）诸行，并同步裁剪 `__all__`（:54-107）。实测：全仓 `from agent.workflow import ...` **0 处**，故亦可整体删除该 `__init__.py` 的 re-export 面（保留空文件或最小导出），二者皆可，但**必须显式处理**。

- **【高】spec delta 的 MODIFIED 会把仍活的行为从正式规格里静默删除**（证据见 D8 表）。具体：`受保护写通道拒绝非法目标` 与 `受保护写通道拒绝归档语境下的非法 change id` 两条 Scenario 被删，而 `tests/test_workflow_protected_write_channel.py:220+` 与 `tests/test_workflow_archive_write_channel.py:225` 仍在断言它们 → 归档后出现「有测试、无规格」的反向漂移，且下一次有人改 `_require_change_target` 时规格不再提供判据。

- **【高】`阻塞状态` 整条 REMOVED 会删掉 2 条活 Scenario**：`checker 派生物一致性`（`check_openspec_artifacts.py:957-961` 在用）与 `guard 读投影执法`（`tests/test_workflow_guard.py:396-537` 10 条活测试）。本 change 保留 guard 的 awaiting 执法实现却删除其规格来源。

- **【中】`flow block`/`flow confirm` 删除后，awaiting 进入/解除通道完全消失，但 guard 的 awaiting 硬拦截保留**。实测：`blocked_entered` 仅由 `workflow_state.py:611`（cmd_flow_block）与 `manager.py:316`（同删）写入；`blocked_resolved` 仅由 `:649`（cmd_flow_confirm）与 `manager.py:328` 写入。删除后两个事件**无任何写入者**，而 `workflow_guard.py:539-560 _awaiting_block_reason` 仍会对 `is_awaiting_state` 为真的 change 对所有写操作 exit 2 且**不可经 Bash 绕过**。实测当前 awaiting change 数为 **0**，故不会立刻自锁；但若合入前有 in-flight change 处于 awaiting（例如某个 change 正卡在 `awaiting_proposal_confirmation` 等用户确认），合入后**无法解除**——`flow confirm` 已不存在，唯一出路是手写 `workflow-events.jsonl`（受保护路径，需事件解释）。**建议**：合入前检查全仓 awaiting 状态（本次实测 0，但合入时机不同结果可能不同），并在 change 文档显式声明「awaiting 执法保留但无 CLI 解除通道」这一后果；或保留 `flow confirm` 作为纯恢复命令（最小代价消除死锁面）。

- **【中】SPAWN 悬空指针的对称问题未处理**：`cmd_spawn` 删除后，`_require_change_target` 的 `or handoff.json` 分支 docstring（`workflow_state.py:884-887`）仍以「`cmd_spawn` 生成的子 change」举例，指代一个已不存在的命令；同时 spec delta :51 保留了「`proposal.md` 或 `handoff.json`」措辞但删除了 `老世代 change 的受保护写通道保持可用` Scenario（该 Requirement 的第 86-90 行），使该分支**有实现、有测试、无规格**。

- **【中】`handoff_note.py`（103 行）是 design.md 遗漏的删除面**。实测全仓 `import handoff_note` / `from agent.workflow.handoff_note import` **0 处**（唯一提及是 `openspec/changes/archive/2026-07-14-add-workflow-automation/tasks.md:28` 的历史记录）。它属于四阶段子系统（`FALLBACK_HANDOFF_PROMPT` 引导 agent 生成 handoff note 并「append to transitions, update current state, and set next hints」），与 `Agent 间 handoff` Requirement（:304）同源。**建议加入删除面**，否则本 change 会留下一个新的一文件死代码。

- **【中】`WF_REQUIRED_PHASES` 类未用导入与 `workflow_methods.json` 的孤儿键**：`workflow_state.py:42` 导入 `WORKTREE_REQUIRED_PHASES`，其唯一使用点在 `:416`（`_cmd_discover_json`，删除面内）；`workflow_methods.json` 的 `ticket_tracker` 节唯一读者是 `_ticket_tracker_label`（`:152`，仅被 `_method_hint:176,179` 调），而 `_method_hint` 的调用点全在 discover 路径。若按 D4 删除 phase 段与 `_method_hint`，`ticket_tracker` 与 `on_ramps`/`cross_cutting` 节一并成为孤儿。tasks.md 未列这些连带项。

- **【低】`docs/benchmark-run-protocol.md:22` 的规划区间与删除后现状冲突**：该行声明 `B 轨·当前演进 12–16`，删除 b03 后 B 轨为 **11**，低于区间下界。该行属「协议目标口径」而非现状（`docs/interview-bullets/walkthrough.md:3676` 明确「协议目标口径为 82–90…是升级方向而非现状」），**不必改**，但需在 change 文档中记录该偏差，避免后续被当作不一致。
- **【低】`docs/benchmark-plan.md:22` 写「27 个本地任务」是既有漂移**（现状 34，与本 change 无关），应作为**既有**问题与本次数字更新分开记录或另开债务，**不要**在同一改动里混改。
- **【低】`tests/agent/workflow/test_manager.py` 与 `tests/test_workflow_state_cli.py` 的 gen-1 种子依赖 `WorkflowManager(...).init()`**（`test_workflow_state_cli.py:158,295,331`、`test_workflow_guard.py:32`）。删除 `manager.py` 会打断 `test_workflow_guard.py:32 _seed_active_change`（guard 的活测试种子）——该处需按 `_seed_gen1_change` 的等价字面量改写，design.md 与 tasks.md **均未列出 `test_workflow_guard.py` 的改写**，而它是活路径回归的核心测试文件。
