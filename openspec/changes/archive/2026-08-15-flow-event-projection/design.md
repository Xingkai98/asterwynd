# Design: 开发流程事件投影（flow-event-projection，P1）

## Context

现状事实（file:line 证据）：

- **事件基建两代分裂**（#125）：老世代事件（`initialized` + handoff.json 开头）可被 `replay_handoff_projection`（`agent/workflow/event_log.py:205`）回放；当代事件（`change_created` 开头、无 handoff.json）该函数**直接抛错**。`workflow-events.jsonl` 实为 per-change 文件（20 文件 80 事件 v1）。
- **命令现状**（`scripts/workflow_state.py`）：`advance`（:517）/`approve`（:554）已死亡（仅 artifact-event/review-manifest 底层函数可用）；`artifact-event`（:677）/`review-manifest`（:706）可用；P0 已加 `policy-*` 子命令（:775+）与 `_read_policy`/`_atomic_write_json`。
- **事件底层**：`event_log.py` 有 `_read_events`（:334）/`_append_event`（:192）/`_apply_*_event`（:237-312）/`verify_handoff_projection`（:319）。
- **受保护路径**：P0 的 `flow-policy.json` 已预留 `workflow-state.json` 条目（governance 待 #128/#129 定 → 已定为 cli_written）。
- **spec**：`openspec/specs/dev-workflow-state-machine/spec.md` 有「工作流事件日志与 handoff.json projection」（:9）、「阻塞状态」（:466）、「内容门槛阶段感知」（:553）等 requirement。
- 决策已锁定：#125（两代分裂 + 可用底层函数）、#128（投影 schema：state + milestones + source_event_seq，删 updated_at，awaiting 集）、#129（写路径唯一化、复用 v1 blocked 事件、guard 读投影 stale 兜底、checker 派生物一致性、受保护路径 cli_written、paseo 通知非执法）。

## Goals / Non-Goals

### Goals

- per-change 可读投影 `workflow-state.json`：`state + milestones + source_event_seq`，任意 change（老/新世代）可投影。
- `flow status/confirm/approve/block/advance` 命令组取代死亡命令；awaiting 态可查询、可确认、可执法。
- 等待合法化不弱化执法（红线 1）：awaiting 期间 guard 仍 exit 2，确认后才放行。
- 两代分裂修复：replay 对当代事件不抛错；归档证据格式不重写（红线）。
- 机械闭环：checker 投影==replay 一致性防自锁。

### Non-Goals

- P2 平台闸门 / P3 lark 通知 / P4 声明化引擎（各自立项）。
- 新增事件类型（复用 v1 blocked，红线 2）。
- 改 AgentLoop / ToolRegistry / benchmark。
- paseo 侧执法（paseo permission 仅通知，awaiting 执法本地化）。

## Decisions

> 所有决策已由用户于 2026-08-15 逐项确认（Q1-Q13，记录于 `reviews/grill-design.md` 的 `## User Confirmation`），并吸收独立 subagent 代码层自洽性审查的修正。Q 标注对应 grill Open Questions 的最终口径。

### D1: workflow-state.json 落点与 schema（#128 沿用 + Q1/Q6/Q7/Q13 确认）

- 路径：`openspec/changes/<change-id>/workflow-state.json`（每 change 一份，与 events 同目录）。**当代 change 落盘**；老世代归档 change **不落盘**（handoff.json 即其投影，Q13）。
- 核心字段：`state`（派生）、`milestones`（数组）、`source_event_seq`（int）；**删 `updated_at`**（当代事件无时间戳，#128）。
- **awaiting 态建模为 `blocked` phase 的 sub_state**（代码层修正 1）：`blocked.awaiting_proposal_confirmation` / `blocked.awaiting_human_review` / `blocked.awaiting_user_confirmation`；普通 `blocked`（非 awaiting）sub_state 为 null。spec delta 同步修正「blocked/done 时 sub_state 可为 null」为「awaiting 态可承载 sub_state，普通 blocked 仍为 null」。
- **`awaiting_proposal_confirmation` 激活**（Q4 确认）：proposal（含调研结论）完成后写 `blocked_entered` 进入该态，用户 `flow confirm` 后才允许进入开发。
- `review_blocked` 不入 awaiting 集。
- 权威形状 = `state + milestones + source_event_seq`；老世代 replay 时从 handoff 形状**映射输出**该形状（Q7）。
- 派生 any-of + 容忍异构：不要求首事件 change_created（Q8 确认 change_created 作 seed）。

### D2: 两代兼容的 replay 修复（#125 + Q8/Q7 确认）

- `replay_handoff_projection` 改为**统一投影入口**：当代事件（change_created 开头）→ `_apply_*_event` 链 + seed 派生 + milestones 推进器；老世代（initialized + handoff.json）→ 既有 `_apply_transition_event` 兼容路径（不抛错）。
- **seed 派生**：首事件 `change_created` 作派生起点，初始投影等价 `init_handoff_json` 的 `planning.exploring`（Q8）。
- **milestones 推进器**：`grill_completed` / `design_reviewed` / `design_review_completed` / `building_review_completed` / `known_debt_updated` 五类事件只更新 `milestones` 数组、不改 state（Q8）；其余非状态类型归 `NON_STATE_EVENT_TYPES` 跳过。
- 修复不改变 v1 事件文件内容（归档证据不可重写）。
- 归档「可投影」（代码层修正 2）= 结构合法（schema/seq 连续）+ 所有 event_type 可识别（在 `_apply_*` 或 NON_STATE 或 milestones 集），**不要求 seed 事件**；无 seed 的 gen-1 归档按结构合法即可投影，不抛错。

### D3: flow 命令组（#129 + Q1/Q2/Q10 确认）

- 子命令集 = `flow status` / `flow confirm` / `flow approve` / `flow block` / `flow advance`（代码层修正 3/8：advance 是删除旧 advance 后的推进路径）。
- `flow status [--change <id>|--all]`：**唯一/默认输出 JSON**（state/milestones/source_event_seq/last_seq/stale），不做文本表格、不做双格式（Q1）。
- `flow confirm --change <id>`：写 `blocked_resolved`（复用 v1 blocked 事件类型）；payload 从当前投影 awaiting 态推导，兼容无 blocked_entered 前置记录的 change（Q9，代码层修正 7）。
- `flow approve --change <id> [--phase]`：阶段通过（写对应 transition 事件）。
- `flow block --change <id> --awaiting <type>`：写 `blocked_entered` 进入指定 awaiting 态（写路径唯一化，D4）。
- `flow advance --change <id> --to <sub_state>`：sub_state 推进，写 `transition_applied`。
- 废旧 `advance`/`approve`：**直接删除**，不留兼容 stub（Q2）；`discover --format json` 的 `approve_command` 改为指向 `flow approve`，4 个 CLI 测试同步迁移。

### D4: 写路径唯一化（#129 红线 2 + Q4/Q12 确认）

- `blocked_entered` 只由进入 awaiting 的完成命令与 `flow block` 写：**P1 至少 proposal 完成命令写 `awaiting_proposal_confirmation` 的 blocked_entered**（Q4/Q12 激活）；进入其他 awaiting 态的完成命令写路径可留 P2。
- `blocked_resolved` 只由 `flow confirm` 写（building-review S2：`flow approve` 是阶段 gate 通过，写 `transition_applied`，不写 blocked_resolved）。
- 不新增事件类型（v1 blocked 类型复用，`append_blocked_event`/`append_unblocked_event` 沿用）。

### D5: guard 读投影 + stale 自愈重建（#129 + Q3 确认 + building-review 修复）

- guard 判断 awaiting **以事件日志 replay 结果为准**（事件是唯一真相，building-review Issue 2/3 修复）：`_awaiting_block_reason` 调 `project_workflow_state` 得到权威状态；投影缺失/损坏/stale 不影响判定——awaiting 仍 exit 2（不因投影问题放行）、非 awaiting 放行（不额外误拦 gen-0 在途 change）。
- **写操作全覆盖**（building-review Issue 1 修复）：awaiting 期间 Write/Edit 与 write-intent Bash（重定向/heredoc 等）均 exit 2，红线 1 不可经 Bash 绕过；`flow`/`policy-*` 特权 CLI 豁免（确认/解除通道）。
- guard **只读不写盘**（hook 无副作用，代码层修正 4）。
- **自愈重建**（Q3）：`flow` 命令在投影缺失/损坏/stale 时先用事件 replay 自动重建，重建成功即写新鲜投影；仅事件不完整导致重建失败才报错。
- **事件损坏**（缺 seq / JSON 语法坏 / 末尾截断）→ guard fail-closed exit 2 报「事件不完整，检查 seq N」；`flow status` 同口径报错，不猜测不跳过。
- guard 内嵌默认行为保持：awaiting 且未确认 → exit 2（执法不弱化，红线 1）。

### D6: checker 派生物一致性（#129 + Q5/Q11 确认）

- tasks 全勾的 change：校验磁盘投影 == 从事件 replay 的投影；不一致 → exit 2（防自锁）。磁盘投影与 replay 重建走独立实现路径，避免同源恒真。
- **不扩展 `--check-archived`**（Q5）：归档 change 只验证**可投影**（结构合法 + 类型可识别，见 D2），不抛错、不要求磁盘投影。
- `verify_handoff_projection` 扩为 **`verify_projection`**（两代通用：可投影 + 一致性），checker 调它（Q11）。

### D7: 受保护路径与更新通道

- `workflow-state.json` + `workflow-events.jsonl` 已由 P0 入 `flow-policy.json` 受保护清单（governance=cli_written，`scripts/flow-policy.json:46-49,70-74` + guard 默认表 `scripts/workflow_guard.py:79,84`）——**任务 3.5 无需改策略表**，只记录该事实，勿破坏 parity 测试。
- guard `_is_privileged_cli` 豁免正则扩展 `flow` + 子命令白名单 `(status|confirm|approve|block|advance)`（Q10，代码层修正 8）；复合/重定向判断保持（防 hijack）。
- `workflow-state.json` **入库 git 跟踪**（代码层修正 5），保证 CI checker 投影==replay 可执行。

### D8: paseo 通知非执法（#126/#129）

- 进入 awaiting 时建 pending permission 请求（通知形态），awaiting 执法由 guard/checker 本地承担；paseo 通知不承担执法。

### D9: 本 change 自身 RIR

- `research_tier: exempt` + `status: disabled`，上游决策锁定（#125/#128/#129 已关闭 + #121 架构评审），与 P0/industry-research-gate 归档口径一致。

## Pre-Implementation Review

独立 subagent design grilling 已完成（`reviews/grill-design.md`，7 条 Confirmed Decisions + 13 条 Open Questions + 5 条 Risks，issue #95 机械强制）；用户于 2026-08-15 对 Q1-Q13 逐项确认，已记录于 `## User Confirmation`（grill-confirmation-gate 通过）。另完成一次独立零记忆 subagent 代码层自洽性审查（对照 event_log.py / workflow_state.py / workflow_guard.py / check_openspec_artifacts.py / flow-policy.json + 全部归档事件日志），9 条修正已并入上方 Decisions。

## Open Questions（已确认，2026-08-15）

> Q1-Q13 已由用户逐项确认并记录于 `reviews/grill-design.md` 的 `## User Confirmation`。最终口径见 Decisions 节对应条目。

- **Q1**（已确认）：`flow status` 唯一/默认输出 JSON，不做文本表格、不做双格式 → D3。
- **Q2**（已确认）：废旧 advance/approve 直接删除，迁移到 flow 命令 → D3。
- **Q3**（已确认）：投影缺失/损坏/stale 时 flow 先自动 replay 重建；事件损坏 fail-closed 报「事件不完整，检查 seq N」→ D5。
- **Q4**（已确认）：awaiting_proposal_confirmation 激活，proposal 完成后写 blocked_entered → D1/D4。
- **Q5**（已确认）：checker 不扩展 --check-archived，归档只验可投影 → D6。
- **Q6**（已确认）：投影落盘 workflow-state.json，写入者=flow 命令（status/confirm/approve/重建时刷新）→ D1/D3。
- **Q7**（已确认）：workflow-state 形状权威，老世代 handoff 映射输出 → D1/D2。
- **Q8**（已确认）：change_created 作 seed；5 类里程碑事件归 milestones 推进器；其余 NON_STATE → D2。
- **Q9**（已确认）：flow confirm payload 从当前投影 awaiting 态推导 → D3。
- **Q10**（已确认）：guard 豁免正则白名单 flow 子命令（含 advance）→ D7。
- **Q11**（已确认）：verify_handoff_projection → verify_projection → D6。
- **Q12**（已确认）：P1 提供 blocked_entered 写路径（至少 proposal 完成命令）→ D4。
- **Q13**（已确认）：老世代不落盘 workflow-state.json，stale 只对当代 → D1。

## Risks / Trade-offs

- **两代兼容回归（高）**：replay 修复可能影响老世代投影（handoff.json 路径）——parity 测试锁「老世代 replay 结果不变」+ 新世代不抛错。
- **guard 兜底误判（中）**：stale 时正则兜底与投影判定可能不一致（awaiting 判定差异）——兜底语义 fail-closed（宁可多拦不放行），parity 测试覆盖。
- **命令删除破坏调用方（中）**：advance/approve 若被脚本/文档引用，删除会破坏——先查调用方（rg），保留兼容提示或同步更新文档。
- **checker 自锁（低）**：投影实现与 replay 实现同一套代码，一致性检查可能恒真——用独立实现（磁盘投影 vs replay 重建）对比，避免同源恒真。
- **受保护路径误拦（低）**：workflow-state.json 入受保护清单后，非 CLI 写被拦——guard 豁免 `flow`/`policy-*` CLI 通道（P0 已建立的豁免模式）。

## Testing Strategy

- **投影派生测试**：老世代（initialized+handoff.json）/ 当代（change_created 开头）各自投影正确；change_created seed 派生（初始等价 planning.exploring）；awaiting 态建模为 blocked.awaiting_*（awaiting_proposal_confirmation 激活、awaiting_human_review / awaiting_user_confirmation 枚举、review_blocked 不入 awaiting）；milestones 推进器（5 类事件只改 milestones 不改 state）；容忍异构（无 change_created 首事件）。
- **flow 命令集成测试**：status JSON 输出（state/milestones/source_event_seq/stale）；confirm 写 blocked_resolved（payload 从投影推导，无 blockers 记录不抛错）；approve 写 transition；block 写 blocked_entered；advance 写 transition_applied；写路径唯一化（非法写者被 guard 拦）。
- **guard 兜底测试**：投影正常 / 缺失 / 损坏 / stale 四种形态的行为；缺失/stale/corrupt → exit 2 提示先跑 flow status 重建；事件损坏报「事件不完整，检查 seq N」；awaiting 未确认 exit 2；已确认放行；fail-closed（不因投影问题放行）；guard 只读不写盘。
- **checker 一致性测试**：磁盘投影 == replay 通过；人为篡改投影 → exit 2；归档 change 只验可投影（结构合法 + 类型可识别，无 seed 不抛错）。
- **verify_projection 测试**：老世代（handoff.json == replay）与当代（可投影 + 一致性）通用。
- **两代 parity 测试**：老世代 replay 结果与修复前一致（golden 文件或特性断言）。
- **回归**：现有 guard/checker/policy 测试全绿（含 4 个 advance/approve CLI 测试迁移）；全量 pytest；OpenSpec strict validate；artifact checker。
