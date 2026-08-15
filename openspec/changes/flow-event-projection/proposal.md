# Proposal: 开发流程事件投影（flow-event-projection，P1）

关联跟踪 issue：[#136](https://github.com/Xingkai98/asterwynd/issues/136)（【feature】flow-event-projection：开发流程事件投影（workflow-state.json，P1））。父 map：[#121](https://github.com/Xingkai98/asterwynd/issues/121)（开发流程可安装化，P1 事件投影）。

## Change Type

- primary: process
- secondary: []

## 需求

1. **workflow-state.json 投影**（每 change 一份）：`state + milestones + source_event_seq` 核心字段；删 `updated_at`（当代事件无时间戳，沿用 #128 决策）；3 个 awaiting 态对应三人机节点——`awaiting_proposal_confirmation` 留槽位暂不派生、调研节点归 `working`、`review_blocked` 不入 awaiting 集（#128）；派生规则 any-of + 容忍异构，不要求首事件为 `change_created`（#128）。
2. **flow 命令**：`flow status`（展示投影与等待态）、`flow confirm`（阻塞解除，写 `blocked_resolved`）、`flow approve`（阶段通过，写对应事件）；废旧 `advance`/`approve` 子命令（#129）。
3. **写路径唯一化**：`blocked_entered` 由进入 awaiting 的完成命令写、`blocked_resolved` 由 `flow confirm/approve` 写；**复用 v1 blocked 事件类型**（不新增类型，防 v1 replay 崩，红线 2，#129）。
4. **guard 读投影 + last_seq 新鲜度**：guard 读 `workflow-state.json` 判断等待态，`last_seq` 与事件文件不一致（stale）时回退正则兜底（#129）。
5. **checker 派生物一致性**：投影 == replay 校验防自锁；`verify` 扩展覆盖新世代事件（#129）。
6. **受保护路径**：`workflow-state.json` 与 `workflow-events.jsonl` 入受保护清单（governance=cli_written，只准 CLI 写；flow-policy.json 已预留 `workflow-state.json` 条目，见 P0 归档版）。
7. **事件基建两代分裂修复**（#125）：`replay_handoff_projection`（`agent/workflow/event_log.py:205`）对当代事件（`change_created` 开头、无 handoff.json）直接抛错——P1 统一/兼容处理，保证任意 change 可投影。
8. **paseo permission 仅通知非执法**：进入 awaiting 时建 pending permission 请求做通知（#126），awaiting 执法本地化（guard/checker 是权威，paseo 通知不承担执法）。

## 背景

- #121 P1 是「事件投影」：把 per-change 的 `workflow-events.jsonl`（20 文件 80 事件 v1，per-change 文件，#125）投影为可读的 `workflow-state.json`，让人机节点（调研/方案设计/开发）的等待态可查询、可执法。
- 决策已锁定：#125（事件溯源/投影现状盘点——两代分裂：老世代 initialized+handoff.json 可回放、当代 change_created 开头无 handoff.json 直接抛错；advance/approve 已死亡，仅 artifact-event/review-manifest 底层函数可用）+ #128（投影 schema）+ #129（等待态执法）。
- P0（flow-policy-source）已合入：`flow-policy.json` 单一策略源、`policy-*` 子命令、guard 同源加载 fail-closed、内容门槛。P1 在其上新增投影与 flow 命令。
- 现状代码：`scripts/workflow_state.py` 现有 `advance`/`approve`（:517/:554，已死亡）、`artifact-event`/`review-manifest`（:677/:706，可用底层）、`policy-*`（:775+）；`agent/workflow/event_log.py` 有 `_read_events`/`_append_event`/`replay_handoff_projection`/`_apply_*_event`/`verify_handoff_projection`。

## 非目标

- **不做 P2 平台闸门**（GitHub required checks / approve=1 / required_conversation_resolution）。
- **不做 P3 编排通知**（lark 卡片与降级链；paseo pending permission 通知形态已由 #126/#129 定，但 lark 通道细节不做）。
- **不做 P4 声明化引擎**（statechart 等价 pin + 演示，验收线 #124 已定，触发点随 P0-P2 推进）。
- **不改归档证据格式**（红线：versioned reader 兼容，不重写 v1 事件）。
- **不新增事件类型**（复用 v1 blocked 事件，红线 2）。
- **不改 AgentLoop/ToolRegistry**（本 change 只动 workflow 治理面）。

## 用户故事

- 用户在手机上查看 change 进度 → `flow status` 输出该 change 的投影状态（working / awaiting_* / done），不再需要人肉读 events jsonl。
- agent 完成 proposal 阶段进入方案设计确认 → 完成命令写 `blocked_entered`（awaiting_proposal_confirmation）→ 用户在手机上看到等待态 → 用户确认后 `flow confirm` 写 `blocked_resolved` → agent 恢复开发。
- guard 判断某 change 处于 awaiting 且用户未确认 → 写操作 exit 2（awaiting 执法不弱化，红线 1）；投影 stale 时回退正则兜底。
- checker 对 tasks 全勾的 change 校验「投影 == replay」→ 自锁（投影逻辑与事件应用逻辑不一致）时 fail，防 checker 自己放行。
- 老 change（handoff.json 时代）与新 change（当代事件）都能 `flow status`，不抛错。

## 行为定义

### workflow-state.json 投影（每 change 一份）

- 路径：`openspec/changes/<change-id>/workflow-state.json`（受保护，governance=cli_written）。
- 核心字段：`state`（working / awaiting_* / done 等派生态）、`milestones`（阶段里程碑数组）、`source_event_seq`（投影来源的最大事件 seq）。
- awaiting 态集合（#128）：`awaiting_proposal_confirmation`（留槽位暂不派生）、`awaiting_human_review`、`awaiting_user_confirmation`（grill-confirmation-gate 对应）；`review_blocked` 不入 awaiting 集。
- 派生规则：any-of（任一路径可达即成立）+ 容忍异构（不要求首事件 change_created）；老世代（initialized + handoff.json）与当代（change_created）均可投影。

### flow 命令（scripts/workflow_state.py）

- `flow status [--change <id>|--all]`：展示投影状态、awaiting 态、milestones、last_seq 与事件文件一致性。
- `flow confirm --change <id>`：写 `blocked_resolved` 事件（复用 v1 blocked 事件类型）。
- `flow approve --change <id> [--phase <phase>]`：阶段通过事件（对应阶段 transition）。
- 废旧 `advance`/`approve` 子命令（保留兼容提示或删除，grill 定）。

### guard 读投影（scripts/workflow_guard.py）

- 读 `workflow-state.json` 判断 awaiting 态；`last_seq` 与 `workflow-events.jsonl` 不一致（stale）时回退现有正则兜底（不因投影缺失/损坏放行，fail-closed）。

### checker 派生物一致性（scripts/check_openspec_artifacts.py）

- tasks 全勾的 change：校验「磁盘投影 == 从事件 replay 的投影」（一致性，防自锁）；`verify` 覆盖新世代事件。

### 受保护路径与更新通道

- `workflow-state.json` + `workflow-events.jsonl` 入 `flow-policy.json` 受保护清单（governance=cli_written），只准 `flow`/`policy-*` CLI 写。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 开发流程治理 | `scripts/workflow_state.py`（flow status/confirm/approve/block/advance + 投影生成 + 自愈重建）、`scripts/workflow_guard.py`（读投影判断 awaiting + stale/corrupt fail-closed + `_is_privileged_cli` 豁免正则扩展 flow）、`scripts/check_openspec_artifacts.py`（投影==replay 一致性 + verify_projection 扩展 + 归档可投影检查） |
| 事件溯源 | `agent/workflow/event_log.py`：`project_workflow_state` 统一投影入口（两代兼容，change_created seed + milestones 推进器 + 容忍无 seed）；`verify_handoff_projection` 扩为 `verify_projection`；复用 v1 blocked 事件，不新增类型 |
| 受保护 artifact | `workflow-state.json` + `workflow-events.jsonl` 已在 flow-policy.json 受保护清单（governance=cli_written，P0 已预留条目）；**任务 3.5 无需改策略表**（改动会破坏 parity 测试）；`workflow-state.json` 入库 git 跟踪 |
| CLI | `flow` 命令组（status/confirm/approve/block/advance）；废旧 `advance`/`approve` 子命令删除，discover 的 `approve_command` 改指 `flow approve`；gen-2 change 的 `flow status` 同步映射写 handoff.json（老枚举/工具兼容） |
| Specs | `openspec/specs/dev-workflow-state-machine/spec.md`（两代投影 + awaiting 态建模为 blocked.awaiting_* + flow 命令 + guard 读投影执法 + verify_projection） |
| Tests | 投影派生测试、两代 parity 测试、stale 兜底测试、派生物一致性测试、归档可投影测试、flow 命令集成测试、废旧命令迁移 |
| Docs | AGENTS.md（flow 命令说明）、change 自身文档（design/grill） |
| 明确不受影响 | AgentLoop、工具系统、Web/TUI、benchmark、`flow-policy.json` 既有规则表（不改）、hook 部署机制、归档事件文件内容（不重写 v1 证据） |

### 实现期发现并回写的新影响面

- **gen-2 change 同步写 handoff.json**（代码层修正 6）：`flow` 命令写 `workflow-state.json` 时同步映射写最小 handoff.json，避免 `_load_handoff`/discover 等老枚举工具漏掉当代 change。checker 的 `_check_handoff_json` 已改用 `verify_projection`（gen-2 校验 workflow-state.json，不校验 synced handoff 与 replay 的 handoff 形状）。
- **guard bootstrap 语义**：当代 change 有 events 但无 workflow-state.json 时，guard fail-closed 拦写并提示先跑 `flow status`（投影是 awaiting 判定的前提）。
- **`--check-archived` 既有 drift**：归档 change 的 review manifest tasks hash 与当前 tasks.md 存在 pre-existing drift（7 处），非本 change 引入，另作债务处理。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 本 change 归「上游决策锁定」豁免——决策集全部来自 #121 已关闭决策票（#125 事件溯源现状盘点、#128 投影 schema、#129 等待态执法）与 #121 架构评审（红线 2 复用 v1 blocked 事件、versioned reader 兼容），无待定设计项；业界调研已在 #121 架构评审完成（重型 workflow 引擎 Temporal/Argo 评审否决、编排工具等待/blocked 建模调研 #126、Herdr/Orca 桌面端调研），本 change 是仓库内部流程改造，不引入新能力面。本地参考仓库不可用（`.dev/reference-repos.txt` 不存在，已确认）。
- research questions: 无（决策已锁定）
- findings: 无新增
- design impact: 无
