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
- `flow status/confirm/approve` 命令组取代死亡命令；awaiting 态可查询、可确认、可执法。
- 等待合法化不弱化执法（红线 1）：awaiting 期间 guard 仍 exit 2，确认后才放行。
- 两代分裂修复：replay 对当代事件不抛错；归档证据格式不重写（红线）。
- 机械闭环：checker 投影==replay 一致性防自锁。

### Non-Goals

- P2 平台闸门 / P3 lark 通知 / P4 声明化引擎（各自立项）。
- 新增事件类型（复用 v1 blocked，红线 2）。
- 改 AgentLoop / ToolRegistry / benchmark。
- paseo 侧执法（paseo permission 仅通知，awaiting 执法本地化）。

## Decisions

### D1: workflow-state.json 落点与 schema（#128 沿用）

- 路径：`openspec/changes/<change-id>/workflow-state.json`（每 change 一份，与 events 同目录）。
- 核心字段：`state`（派生）、`milestones`（数组）、`source_event_seq`（int）；**删 `updated_at`**（当代事件无时间戳，#128）。
- awaiting 集：`awaiting_proposal_confirmation`（留槽位暂不派生）、`awaiting_human_review`、`awaiting_user_confirmation`；`review_blocked` 不入 awaiting 集。
- 派生 any-of + 容忍异构：不要求首事件 change_created（老世代 initialized 开头同样可派生）。

### D2: 两代兼容的 replay 修复（#125）

- `replay_handoff_projection` 改为**统一投影入口**：当代事件（change_created 开头）走 `_apply_*_event` 链；老世代（initialized + handoff.json）走既有 `_apply_transition_event` 兼容路径（不抛错）。
- 修复不改变 v1 事件文件内容（归档证据不可重写）。

### D3: flow 命令组（#129）

- `flow status [--change <id>|--all]`：读投影输出 state/milestones/last_seq + 与事件文件一致性（stale 提示）。
- `flow confirm --change <id>`：写 `blocked_resolved`（复用 v1 blocked 事件类型）。
- `flow approve --change <id> [--phase]`：阶段通过（写对应 transition 事件）。
- 废旧 `advance`/`approve`：删除或保留兼容提示（Open Question Q2，grill 定）。

### D4: 写路径唯一化（#129 红线 2）

- `blocked_entered` 只由进入 awaiting 的完成命令写（如 proposal 完成 → awaiting_proposal_confirmation）。
- `blocked_resolved` 只由 `flow confirm/approve` 写。
- 不新增事件类型（v1 blocked 类型复用，`append_blocked_event`/`append_unblocked_event` 沿用）。

### D5: guard 读投影 + stale 兜底（#129）

- guard 读 `workflow-state.json` 判断 awaiting 态；`source_event_seq != len(events)`（stale）或投影缺失/损坏 → **回退现有正则兜底**（fail-closed，不因投影问题放行）。
- guard 内嵌默认行为保持：awaiting 且未确认 → exit 2（执法不弱化，红线 1）。

### D6: checker 派生物一致性（#129）

- tasks 全勾的 change：校验磁盘投影 == 从事件 replay 的投影；不一致 → exit 2（防自锁）。
- `verify`（`verify_handoff_projection` 扩展）覆盖新世代事件。

### D7: 受保护路径与更新通道

- `workflow-state.json` + `workflow-events.jsonl` 入 `flow-policy.json` 受保护清单（governance=cli_written），只准 `flow`/`policy-*` CLI 写；人类直改 + CLI 为合法通道（P0 决策模型沿用）。

### D8: paseo 通知非执法（#126/#129）

- 进入 awaiting 时建 pending permission 请求（通知形态），awaiting 执法由 guard/checker 本地承担；paseo 通知不承担执法。

### D9: 本 change 自身 RIR

- `research_tier: exempt` + `status: disabled`，上游决策锁定（#125/#128/#129 已关闭 + #121 架构评审），与 P0/industry-research-gate 归档口径一致。

## Pre-Implementation Review

开发前需完成独立 subagent design grilling（`reviews/grill-design.md`，issue #95 机械强制），并停轮获得用户对 `## Open Questions` 的确认（grill-confirmation-gate，记录于 `## User Confirmation`）。本 change 的三个决策票（#125/#128/#129）已在 wayfinding 阶段完成 grilling 并确认，此处 grilling 聚焦 P1 合并实现细节（投影派生边界、命令形态、guard 兜底、checker 一致性实现）。

## Open Questions

- **Q1**：`flow status` 的输出形态——纯文本表格（手机可读）还是 JSON + 文本双格式？（现有 discover 是双格式，flow status 是否对齐）
- **Q2**：废旧 `advance`/`approve` 的处理——直接删除（干净，但要检查调用方）还是保留兼容提示（渐进迁移）？
- **Q3**：guard stale 兜底的精确语义——投影缺失/损坏/stale 时回退正则兜底，但"awaiting 且已确认"如何与正则兜底对齐（正则兜底能否识别 blocked_resolved）？
- **Q4**：`awaiting_proposal_confirmation` 留槽位暂不派生的边界——本 P1 是否完全不产出该态，还是保留派生逻辑但守卫禁用？
- **Q5**：checker 派生物一致性对**归档 change**是否生效（`--check-archived` 是否扩展）？
- **Q6**：投影生成时机——每次 CLI 调用时即时 replay（无落盘，纯派生）还是落盘 `workflow-state.json` 缓存 + stale 校验（#129 说落盘 + last_seq）？落盘时机的写入者是谁？

## Risks / Trade-offs

- **两代兼容回归（高）**：replay 修复可能影响老世代投影（handoff.json 路径）——parity 测试锁「老世代 replay 结果不变」+ 新世代不抛错。
- **guard 兜底误判（中）**：stale 时正则兜底与投影判定可能不一致（awaiting 判定差异）——兜底语义 fail-closed（宁可多拦不放行），parity 测试覆盖。
- **命令删除破坏调用方（中）**：advance/approve 若被脚本/文档引用，删除会破坏——先查调用方（rg），保留兼容提示或同步更新文档。
- **checker 自锁（低）**：投影实现与 replay 实现同一套代码，一致性检查可能恒真——用独立实现（磁盘投影 vs replay 重建）对比，避免同源恒真。
- **受保护路径误拦（低）**：workflow-state.json 入受保护清单后，非 CLI 写被拦——guard 豁免 `flow`/`policy-*` CLI 通道（P0 已建立的豁免模式）。

## Testing Strategy

- **投影派生测试**：老世代（initialized+handoff.json）/ 当代（change_created 开头）各自投影正确；awaiting 态派生（awaiting_human_review / awaiting_user_confirmation / review_blocked 不入 awaiting）；容忍异构（无 change_created 首事件）。
- **flow 命令集成测试**：status 输出；confirm 写 blocked_resolved；approve 写 transition；写路径唯一化（非法写者被拦）。
- **guard 兜底测试**：投影正常 / 缺失 / 损坏 / stale 四种形态的行为；awaiting 未确认 exit 2；已确认放行。
- **checker 一致性测试**：磁盘投影 == replay 通过；人为篡改投影 → exit 2；归档 change 行为（随 Q5 定）。
- **两代 parity 测试**：老世代 replay 结果与修复前一致（golden 文件或特性断言）。
- **回归**：现有 guard/checker/policy 测试全绿；全量 pytest；OpenSpec strict validate；artifact checker。
