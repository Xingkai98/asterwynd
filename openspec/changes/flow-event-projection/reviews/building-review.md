# Building Review: flow-event-projection

## Verdict

**CHANGES_REQUESTED**

## Scope

- 审阅范围：`git diff 4131efe..HEAD`（提交 3 个：a709bce / d7d932c / eaa526c + 工作区，工作区无未提交改动）
- 审阅者：review-20260815-a7f3

## Per-Task Verification

逐条对照 tasks.md 1.1-4.5（5.x 为 PR 收尾，未勾选属预期）：

- [x] 1.1 proposal.md 含需求/非目标/行为定义/验收，关联 #136 + #121（`openspec/changes/flow-event-projection/proposal.md`）。
- [x] 1.2 design.md 含 Context/Goals/Non-Goals/Decisions(D1-D9)/Risks/Testing Strategy（design.md 全节齐全，checker `_check_required_sections` 通过）。
- [x] 1.3 proposal.md 维护 `## Impact Analysis`（proposal.md:73-90），含实现期回写的新影响面。
- [x] 1.4 `## Reference Implementation Research` status: disabled + research_tier: exempt + 上游决策锁定理由（proposal.md:92-99），tasks 全勾内容门槛下 exempt 证据校验通过（reason 引用 #121/#125/#128/#129）。
- [x] 1.5 `reviews/grill-design.md` 存在，≥3 Confirmed Decisions（7 条），Q1-Q13 全部有 `## User Confirmation` 实质确认记录；checker `_unconfirmed_open_questions` 无缺失。
- [x] 1.6 backlog 条目已更新（`docs/openspec-change-backlog.md`），配 `backlog_updated` 事件（workflow-events.jsonl seq 2、seq 4）。
- [x] 1.7 spec delta 已合并到 `openspec/specs/dev-workflow-state-machine/spec.md`，配 `current_spec_synced` 事件（seq 3）；当前规格未把未实现能力写成已实现（两代投影/awaiting 建模/flow 命令均实现）。

## 2. 测试

- [x] 2.1 投影派生：老世代（`test_gen1_maps_handoff_to_workflow_state`）、当代（`test_project_new_gen_change_created_seed`）、awaiting 建模（`test_project_new_gen_blocked_awaiting_state`）、容忍异构（`test_project_no_seed_tolerated`）、milestones 推进器（`test_project_new_gen_milestones_pusher_does_not_change_state`）均覆盖。
- [x] 2.2 两代 parity：`test_gen1_replay_shape_unchanged_parity` 锁老世代 handoff 形状不变；当代不抛错由 2.1 系列覆盖。
- [x] 2.3 `flow status`：JSON 输出 + stale 自愈重建（`test_flow_status_outputs_json_and_self_heals_stale`）、`--all` 覆盖当代（`test_flow_status_all_lists_contemporary_changes`）、归档只读不落盘（`test_flow_status_archived_change_readonly`）。
- [x] 2.4 flow 写命令：block/confirm roundtrip（`test_flow_block_and_confirm_roundtrip`）、confirm 非 awaiting 拒绝（`test_flow_confirm_rejects_when_not_awaiting`）、approve 非 gate 拒绝（`test_flow_approve_rejects_non_gate_state`）、advance 非法跳转拒绝（`test_flow_advance_rejects_invalid_sub_state_jump`）、写路径唯一化由 guard 拦截测试（test_workflow_guard.py）覆盖。
- [x] 2.5 guard 兜底：投影正常/缺失/损坏/stale 四形态（`test_guard_blocks_write_when_projection_*`、`test_guard_allows_write_when_not_awaiting`）、awaiting 未确认 exit 2、fail-closed、chain hijack（`test_guard_blocks_flow_chain_hijack`）。**注：测试未覆盖「Bash 写代码文件在 awaiting 期被拦」与「stale 且投影显示非 awaiting」两分支（见 Issues 1/2）。**
- [x] 2.6 checker 一致性：磁盘投影==replay 通过 + 人为篡改检出（`test_check_handoff_json_rejects_gen2_projection_mismatch`、`test_verify_projection_gen2_disk_matches_and_tamper_detected`）、归档只验可投影（`test_check_archived_projectable_*`、`test_check_archived_no_seed_projectable`）。
- [x] 2.7 废旧命令：`advance`/`approve` 子命令已删除（workflow_state.py parser 无该两项），discover `approve_command` 改指 `flow approve`（workflow_state.py:442），4 个 CLI 测试迁移。
- [x] 2.8 回归：本审阅实测相关四测试文件 136 passed；全量 pytest 1928 断言由实现者声明（tree-sitter 环境失败为 pre-existing）。

## 3. 实现

- [x] 3.1 `agent/workflow/event_log.py`：`project_workflow_state` 两代兼容统一入口（:370）、`verify_projection`（:474）、复用 v1 blocked 事件类型、不新增类型。实测 20 个归档 + 4 个 active change 全部可投影。
- [x] 3.2 `scripts/workflow_state.py`：flow 命令组齐全（status/block/confirm/approve/advance）、`_all_change_ids` 覆盖当代（:193）、废旧命令删除、discover 迁移。
- [x] 3.3 `scripts/workflow_guard.py`：awaiting gate + fail-closed + 豁免正则扩展 `flow (status|confirm|approve|block|advance)`（:267-271）。**实现存在下述 Issue 1/2/3，见 Issues。**
- [x] 3.4 `scripts/check_openspec_artifacts.py`：`_check_handoff_json` 调 `verify_projection`（:959）、`--check-archived` 调 `_check_archived_projectable`（:1435）。
- [x] 3.5 flow-policy.json 无需改：`workflow-state.json`（:71-74）+ `workflow-events.jsonl`（:46-49）已在受保护清单 cli_written；guard 默认表同步（workflow_guard.py:79,84）；`policy-validate` parity 一致（实测通过）。
- [x] 3.6 AGENTS.md 已加 flow 命令组说明（AGENTS.md:189-205）。
- [x] 3.7 新影响面已回写 Impact Analysis（gen-2 同步写 handoff、guard bootstrap 语义、--check-archived 既有 drift）。

## 4. 验证

- [x] 4.1 相关测试：本审阅实测 136 passed。
- [x] 4.2 全量 pytest：实现者声明 1928 passed, 7 skipped（1 个 pre-existing tree-sitter 环境失败）。
- [x] 4.3 OpenSpec strict validate：实现者声明 30/30。
- [x] 4.4 artifact checker：实测默认模式 `passed`（exit 0）。`--check-archived` 报 7 处 review manifest tasks hash mismatch，为既有 drift（归档目录不在本 diff 内，proposal.md:90 已记录为债务），非本 change 引入。
- [x] 4.5 两代兼容人工验证：实测 20/20 归档 + 4/4 active 可投影不抛错。

## Issues

- **[中等] awaiting gate 不拦截 Bash 写操作，红线 1 可经 Bash 绕过**：`scripts/workflow_guard.py:648` — awaiting gate 包在 `if file_path and not _is_change_doc_write(file_path):` 内，Bash 的 tool_input 无 `file_path` 字段，awaiting gate 对 Bash 永不触发。实测：change 处于 `blocked.awaiting_proposal_confirmation` 时，Write 工具写 `agent/foo.py` → exit 2；但 Bash `echo code > agent/foo.py` → exit 0（放行）。spec（`openspec/specs/dev-workflow-state-machine/spec.md`「guard 读投影执法」场景）要求「写操作 SHALL exit 2」。失败场景：awaiting 期间 agent 用 Bash 重定向/heredoc 继续写实现代码，awaiting 执法形同虚设。建议：awaiting gate 对 write-intent Bash 命令同样生效（复用 `_is_write_bash` + `_current_change_id`），或明确把「写操作」收窄为 Write/Edit 并在 spec 同步口径。
- **[中等] stale 投影且显示非 awaiting 时 guard 放行，违反「stale → fail-closed」**：`scripts/workflow_guard.py:553-554` — `if not (state.get("phase") == "blocked" and state.get("sub_state") in _AWAITING_SUB_STATES): return None` 在 stale 判定（:565）之前返回，导致投影 stale（`source_event_seq != len(events)`）且磁盘状态非 awaiting 时 guard 直接放行。实测：事件日志含 `blocked_entered`（seq 2，实际 awaiting），磁盘投影 state=planning.exploring + source_event_seq=1（stale）→ Write 放行（exit 0）。spec 要求「投影缺失、损坏或 source_event_seq 与事件文件不一致（stale）时，guard SHALL fail-closed（exit 2…），不因投影问题放行」。失败场景：事件与投影失同步且投影显示非 awaiting（如 confirm 后事件被追加）时，实际 awaiting 的 change 写操作不被拦截。建议：把 stale 检查移到 awaiting-state 检查之前，任何 stale 投影一律 fail-closed。
- **[中等] 缺投影时对所有「有 events 无 workflow-state.json」的 change fail-closed，误伤在途非 awaiting change**：`scripts/workflow_guard.py:545-548` — 有 `workflow-events.jsonl` 但无 `workflow-state.json` → 一律 `projection_missing` exit 2，不区分 change 是否真的 awaiting。实测：非 awaiting 的 gen-0 change（仅 `backlog_updated` 事件、无投影）→ Write 代码文件 exit 2「投影不可用/过期…请先运行 flow status」。仓库现有 active change `add-worktree-tool`、`update-design-review-method` 均为无投影的 gen-0 change，本 change 合入后这两个在途 change 的所有代码写操作将被 guard 阻塞，直到手动跑 `flow status` 生成投影。spec 原文虽支持缺投影 fail-closed，但设计 Q3 明确「不额外误拦」；该行为对非 awaiting change 构成实际误拦。失败场景：另一个并行 change 的 agent 在自身 worktree 内第一次写代码即被拦，需先运行 flow status 才能继续。建议：缺投影时先用事件 replay 判断是否真的 awaiting（或仅对事件显示 awaiting 的 change fail-closed），非 awaiting 放行或仅提示；或至少在错误信息中给出自动修复命令并确认对存量在途 change 的影响面。
- **[轻微] awaiting 态集合两处复制**：`agent/workflow/event_log.py:51-55` `AWAITING_SUB_STATES` 与 `scripts/workflow_guard.py:538` `_AWAITING_SUB_STATES` 是两份独立元组。guard 未从 event_log 导入（hook 自包含设计），未来 awaiting 集变更时两处易漂移导致 guard 与投影判定不一致。建议：guard 从 event_log 导入或加 parity 测试锁定两集合相等。
- **[轻微] `blocked` 的 sub_state 不经状态机校验，任意 `blocked.<anything>` 事件可通过 replay**：`agent/workflow/state_machine.py:42-44` `_validate_sub_state` 对 blocked/done 直接返回 None，`validate_transition` 对 `blocked.*` 不校验 sub_state。因此 `_apply_blocked_to_state`（event_log.py:455）接受 `blocked.foo` 这类非 awaiting sub_state，投影为普通 blocked 态，guard 因不在 awaiting 集而不拦截。虽受「events 仅 CLI 写」缓解（`flow block` 用 `--awaiting choices` 限定），但作为事件溯源层健壮性缺口建议在投影层拒绝未知 blocked sub_state 或显式忽略。

## Risk Point Findings

- **R1（guard 读投影 fail-closed 被绕过）**：**部分成立，有两条确认绕过面**。(1) awaiting gate 仅对 Write/Edit（file_path）生效，Bash 写代码文件可绕过（见 Issue 1）；(2) 投影 stale 且磁盘显示非 awaiting 时 guard 放行，不满足「不因投影问题放行」（见 Issue 2）。`_current_change_id()` 推导失败（非分支名 + 多 active）时门禁不触发，属设计既有约定（与 grill gate 一致，AGENTS.md 分支纪律是前提）。guard 只读不写盘成立（`_awaiting_block_reason` 仅读文件、调 `_read_events`，无任何写路径）。
- **R2（flow 豁免正则 hijack 防护）**：**充分**。`_is_privileged_cli`（workflow_guard.py:254-274）对 `&&`/`||`/`;`/`|`/反引号/`$()`/换行/`>` 重定向 fail-closed 拒绝豁免；子命令白名单 `(status|confirm|approve|block|advance)` 已含 advance。实测：`flow status && echo x > docs/known-debt.md` → exit 2；`flow status ... > workflow-state.json` → exit 2；`flow status ... foo`（多余参数）→ guard 放行但 argparse 在 CLI 层拒绝，无实际危害。`flow block/confirm/approve/advance` 写受保护路径走合法通道被豁免，符合设计。
- **R3（投影==replay 同源恒真）**：**不恒真，防篡改有效**。`verify_projection`（event_log.py:474-501）比较「磁盘 workflow-state.json 字面 JSON」与「从事件即时 replay 重建的投影」，两者非同一调用；人为篡改磁盘 state 字段 → mismatch 检出（实测 + `test_verify_projection_gen2_disk_matches_and_tamper_detected`）。残余同源面：磁盘投影由同一 `project_workflow_state` 写入，若投影函数本身有 bug 且磁盘由同版本写入，则磁盘==replay 恒等、checker 无法自锁发现——设计 D6 声称「独立实现路径」未完全落实，但功能目标（检出 stale/篡改/版本漂移）达成，属轻微设计口径偏差。
- **R4（awaiting 建模 blocked.sub_state 的 replay 兼容）**：**正确**。`_apply_unblocked_to_state`（event_log.py:464-471）不依赖 blockers 数组，直接取 `transition.to` 恢复，无 blocked_entered 前置记录不抛错（Q9，实测 + `test_project_new_gen_unblock_without_blocker_record`）。`flow confirm` 的恢复目标从最近 `blocked_entered` 的 transition.from 推导，缺省回退 `_AWAITING_RECOVERY_DEFAULTS`。老世代 handoff replay（`replay_handoff_projection`）未改动，parity 测试锁定。`validate_transition` 对 `blocked.*`→任意态放行（state_machine.py:138-139），符合「blocked → 恢复目标」语义。唯一缺憾是 blocked sub_state 不做 awaiting 集校验（见 Issue 5，轻微）。
- **R5（--check-archived 归档可投影校验）**：**符合设计，不误判通过为结构层面**。`_check_archived_projectable`（checker:1054-1068）调用 `project_workflow_state`，只校验「结构合法（seq 连续）+ 类型可识别」，不要求 seed。实测 20/20 归档可投影不抛错；gen-0（无 seed）可投影（`test_check_archived_no_seed_projectable`）；未知事件类型报「不可投影」（`test_check_archived_projectable_rejects_unknown_event`）。「可投影但状态语义错误」的日志（如非法 transition）会被 `_validate_transition_dict` 拒绝或按设计放行（状态语义非归档门槛范围），符合 Q5「只验可投影」。

## Other Notes

- `--check-archived` 的 7 处「tasks hash mismatch」为归档 review manifest 与 tasks.md 的 pre-existing drift（proposal.md:90 已记录为债务，非本 change 引入，本 diff 不含 archive/ 改动）。
- 全量 pytest 未在本审阅重跑（实现者声明 1928 passed）；本审阅实测相关 4 文件 136 passed、artifact checker 默认模式 passed、`policy-validate` parity passed。
