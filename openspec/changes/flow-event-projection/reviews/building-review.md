# Building Review: flow-event-projection

## Verdict

**CHANGES_REQUESTED**

Round 1 的五条 issues（I1-I5）已全部真实修复并有回归测试锁定，代码实现与执法行为正确且经过实测。本轮新发现三条 **spec/文档对齐缺陷**（S1 当前 spec 缺 checker 派生物一致性场景、S2 解除等待态场景对 flow approve 的断言与实现不符、S3 Impact Analysis guard bootstrap 语义注释过时），按「宁可严格」判 CHANGES_REQUESTED。均为快速可修的文档/规格问题，不影响代码正确性。

## Scope

- 审阅范围：`git diff 4131efe..HEAD`（提交 4 个：a709bce / d7d932c / eaa526c / b5567ee，工作区无未提交改动）
- 审阅者：review-20260815-4f9d（Round 2）

## Per-Task Verification

逐条对照 tasks.md 1.1-4.5（5.x 为 PR 收尾，未勾选属预期）：

- [x] 1.1 proposal.md 含需求/非目标/行为定义/验收，关联 #136 + #121（`proposal.md`）。
- [x] 1.2 design.md 含 Context/Goals/Non-Goals/Decisions(D1-D9)/Risks/Testing Strategy 全节（checker `_check_required_sections` 通过）。
- [x] 1.3 proposal.md 维护 `## Impact Analysis`（proposal.md:73-90），含实现期回写。**注：其中「guard bootstrap 语义」条目已过时（见 S3）。**
- [x] 1.4 RIR `research_tier: exempt` + status: disabled + 上游决策锁定理由引用 #121/#125/#128/#129（proposal.md:92-99）。
- [x] 1.5 `reviews/grill-design.md` 存在，7 条 Confirmed Decisions，Q1-Q13 全部有实质 User Confirmation；checker `_unconfirmed_open_questions` 无缺失。
- [x] 1.6 backlog 已登记（`docs/openspec-change-backlog.md`），配 `backlog_updated` 事件（workflow-events.jsonl seq 2、seq 4）。
- [x] 1.7 spec delta 已合并到 `openspec/specs/dev-workflow-state-machine/spec.md` 大部分，但 **`checker 派生物一致性` 场景漏合并**（见 S1），配 `current_spec_synced` 事件（seq 3、seq 5）。

## 2. 测试

- [x] 2.1 投影派生：`test_project_new_gen_change_created_seed` / `test_project_new_gen_milestones_pusher_does_not_change_state` / `test_project_new_gen_blocked_awaiting_state` / `test_project_no_seed_tolerated` / `test_project_gen1_maps_handoff_to_workflow_state` 全绿。
- [x] 2.2 两代 parity：`test_gen1_replay_shape_unchanged_parity` 锁老世代 handoff 形状；`test_project_gen1_maps_handoff_to_workflow_state` 当代不抛错。
- [x] 2.3 flow status：`test_flow_status_outputs_json_and_self_heals_stale` / `test_flow_status_all_lists_contemporary_changes` / `test_flow_status_archived_change_readonly` 全绿。
- [x] 2.4 flow 写命令：`test_flow_block_and_confirm_roundtrip` / `test_flow_confirm_rejects_when_not_awaiting` / `test_flow_approve_rejects_non_gate_state` / `test_flow_advance_rejects_invalid_sub_state_jump` 全绿；写路径唯一化由 guard 拦截测试覆盖。
- [x] 2.5 guard 兜底：四形态 + awaiting/Bash/stale/corrupt/fail-closed/只读回归测试全绿（含 Round 1 新增 5 条回归，见 Issues 复查）。
- [x] 2.6 checker 一致性：`test_check_handoff_json_rejects_gen2_projection_mismatch` / `test_verify_projection_gen2_disk_matches_and_tamper_detected` / `test_check_archived_projectable_*` / `test_check_archived_no_seed_projectable` 全绿。
- [x] 2.7 废旧命令：advance/approve 子命令已删除，discover `approve_command` 迁移（workflow_state.py:442），CLI 测试迁移。
- [x] 2.8 回归：本审阅实测相关 4 测试文件 141 passed；全量 pytest 1931 passed / 7 skipped / 5 failed——5 个失败均在 `tests/agent/mcp/test_mcp_manager.py`（MCP fixture 发现环境问题，与本 change 无关，未触及任何被改模块），非本次回归。

## 3. 实现

- [x] 3.1 `event_log.py`：`project_workflow_state`（:370）两代兼容统一入口、`verify_projection`（:481）、`is_awaiting_state`（:365）、复用 v1 blocked 事件。实测 3 active + 20 归档全部可投影。
- [x] 3.2 `workflow_state.py`：flow 命令组齐全（status/block/confirm/approve/advance）、`_all_change_ids` 覆盖当代（:193）、自愈重建 `_refresh_workflow_state`（:858）。
- [x] 3.3 `workflow_guard.py`：awaiting 判定改为事件 replay（`_awaiting_block_reason` :539）、Bash 写路径 awaiting 执法（:628-637）、豁免正则（:254-274）。Round 1 的三条实现缺陷均已修复（见 Issues 复查）。
- [x] 3.4 `check_openspec_artifacts.py`：`_check_handoff_json` 调 `verify_projection`（:959）、`_check_archived_projectable`（:1054）。
- [x] 3.5 flow-policy.json 未改（受保护清单 cli_written 已由 P0 具备）；`policy-validate` parity 实测通过。
- [x] 3.6 AGENTS.md flow 命令组说明已加（AGENTS.md:189-205）。
- [x] 3.7 新影响面已回写 Impact Analysis。**注：「guard bootstrap 语义」条目描述的是修复前 fail-closed 行为，未随 Round 1 修复更新（见 S3）。**

## 4. 验证

- [x] 4.1 相关测试：本审阅实测 141 passed。
- [x] 4.2 全量 pytest：1931 passed / 7 skipped / 5 MCP 环境失败（非本 change，见 2.8）。
- [x] 4.3 OpenSpec strict validate：30/30 passed（实测）。
- [x] 4.4 artifact checker：默认模式报「review manifest missing」——当前处于审阅闭环中（Round 1 的 building-review.md 已存在但 manifest 未生成），manifest 在 PASS 后由 /review-loop 生成，属预期中间态，非缺陷。`--check-archived` 另报 7 处 tasks hash mismatch，为归档目录既有 drift（proposal.md:90 已记录为债务，本 diff 不含 archive/ 改动）。
- [x] 4.5 两代兼容：实测 20/20 归档 + 3/3 active 可投影不抛错。

## Round 1 Issues 复查

- **I1（awaiting gate 不拦 Bash 写）: ✅ 已修复**。`workflow_guard.py:628-637` awaiting gate 现对 write-intent Bash 生效（复用 `_is_write_bash` + `_current_change_id`）。实测：awaiting 期间 `echo code > agent/foo.py`、`cat <<EOF > agent/foo.py`、`python3 -c "open('agent/foo.py','w')..."`、`tee`、`printf >` 均 exit 2；回归测试 `test_guard_blocks_bash_write_when_awaiting`（test_workflow_guard.py:501）+ `test_guard_allows_bash_read_when_awaiting`。残余面：`node -e "fs.writeFileSync(...)"` 不命中写模式 → exit 0（见 R1，属字符串模式写检测固有局限，不属本轮判死项）。
- **I2（stale 且显示非 awaiting 时放行）: ✅ 已修复**。`_awaiting_block_reason`（workflow_guard.py:539-560）改用 `project_workflow_state` 事件 replay 判定 awaiting（事件是唯一真相），不再读磁盘投影状态。实测：磁盘 state=planning.exploring + source_event_seq=1（stale）+ 事件已 blocked_entered → Write 与 Bash 均 exit 2；回归测试 `test_guard_blocks_write_when_events_awaiting_but_disk_stale_non_awaiting`（test_workflow_guard.py:438）+ `test_guard_blocks_write_when_awaiting_despite_stale_projection`。
- **I3（缺投影误伤非 awaiting change）: ✅ 已修复**。`_awaiting_block_reason` 仅当 replay 判定 awaiting 时拦截；无投影 + 非 awaiting（gen-0 `backlog_updated` 开头）→ 放行；无投影 + awaiting → 仍拦；仅事件损坏（无法 replay）fail-closed。实测：gen-0 无投影 Write 代码 exit 0；gen-2 无投影且非 awaiting exit 0；gen-2 无投影且 awaiting exit 2；事件坏 JSON/缺 seq → exit 2 报「事件不完整，检查 seq N」。回归测试 `test_guard_allows_write_for_non_awaiting_change_without_projection`（test_workflow_guard.py:471）+ `test_guard_blocks_write_when_awaiting_despite_missing_projection`。
- **I4（awaiting 集合两处复制）: ✅ 已修复**。`_AWAITING_SUB_STATES` 已从 guard 删除；guard 从 `agent.workflow.event_log` 导入 `is_awaiting_state`（workflow_guard.py:552），集合单源定义于 event_log.py:51-55（`AWAITING_SUB_STATES`），workflow_state.py:46/576/1205 亦导入同源。实测 grep 无第二处集合定义。
- **I5（blocked.<任意> 绕过 awaiting 集）: ✅ 已修复**。`_apply_blocked_to_state`（event_log.py:455-468）拒绝 `blocked.<非 awaiting> sub_state`（raise「blocked sub_state must be an awaiting type or null」）。实测 `blocked.weird_blocked` 投影抛 StateMachineError；回归测试 `test_project_rejects_blocked_non_awaiting_sub_state`（test_event_log.py:257）。

## Issues

- **[中等] S1：当前 spec 漏合并「checker 派生物一致性」场景（spec 同步不完整，task 1.7 未完全达成）**。change delta（`openspec/changes/flow-event-projection/specs/dev-workflow-state-machine/spec.md:63-67`）在「### Modified: 阻塞状态」下新增 `#### Scenario: checker 派生物一致性`（tasks 全勾 change 校验磁盘投影 == replay，不一致 exit 2），但当前 spec（`openspec/specs/dev-workflow-state-machine/spec.md` 阻塞状态 requirement，:486-512）只有进入等待态/解除等待态/guard 读投影执法三个场景，**缺失该场景**（grep「派生物/防自锁/replay 重建」当前 spec 无命中）。实现已正确落地（checker `_check_handoff_json` → `verify_projection`，实测篡改检出），delta 也写了，但当前规格未记录这条 checker 一致性要求。失败场景：归档合入后，当前 spec 无法机械反映「checker 投影==replay」这条核心约束，后续 change 的 spec 增量无从引用。建议：在 `openspec/specs/dev-workflow-state-machine/spec.md` 阻塞状态 requirement 补入该场景（与 delta 一致）。
- **[中等] S2：spec「解除等待态」场景对 flow approve 的断言与实现不符**。当前 spec（spec.md:501）与 delta（delta:51）均写「**THEN** `flow confirm` / `flow approve` SHALL 追加 `blocked_resolved` 事件」，但实现 `cmd_flow_approve`（workflow_state.py:651-712）要求当前态为 `phase.ready_for_review`（GATE），运行 `check_phase_done` 后写的是 `transition_applied`（append_transition_event，:706），**从不写 blocked_resolved**；对 blocked/awaiting 态直接报「期望 gate ...，实际 blocked.awaiting_*」。design D3 亦定义 approve 为「阶段通过（写对应 transition 事件）」。即 spec/design 将 approve 描述为 awaiting 解除写者，实现却只做阶段 gate 推进。失败场景：实现者按 spec 对 `blocked.awaiting_human_review` 的 change 运行 `flow approve` 解除等待，命令失败且 spec 与行为矛盾。建议：修正 spec 与 delta 文本为「`flow confirm` SHALL 写 `blocked_resolved`；`flow approve` SHALL 写 `transition_applied`（阶段 gate 通过）」。
- **[轻微] S3：Impact Analysis「guard bootstrap 语义」注释过时（描述修复前行为）**。proposal.md:87-88 写「当代 change 有 events 但无 workflow-state.json 时，guard fail-closed 拦写并提示先跑 flow status（投影是 awaiting 判定的前提）」——这正是 Round 1 I3 修复前行为。修复后 guard 以事件 replay 判定 awaiting：无投影 + 非 awaiting 放行、awaiting 仍拦、仅事件损坏 fail-closed（workflow_guard.py:539-560），投影已不是判定前提。该注释未随修复更新，与现实现矛盾。失败场景：后续维护者读 Impact Analysis 得到过时语义，误以为缺投影会误拦。建议：将该条改写为 replay 判定口径（或删除）。

## Risk Point Findings

- **R1（guard awaiting 执法不可绕过）**：**成立，修复充分，残留一处固有局限**。Write/Edit（workflow_guard.py:660-666）与 write-intent Bash（:628-637）两路径均实测 exit 2；事件损坏（坏 JSON / 缺 seq / 截断）fail-closed exit 2 报「事件不完整，检查 seq N」（实测）；guard 只读不写盘（实测运行 guard 后无 workflow-state.json 落盘）；`_current_change_id` 推导失败（非分支名 + 多 active）门禁不触发属既有设计约定（与 grill gate 一致）。残留：`_is_write_bash` 字符串模式检测固有局限——`node -e "require('fs').writeFileSync('agent/foo.py','x')"` 实测 exit 0 绕过 awaiting gate（ruby/perl -e、python -c、重定向、heredoc、tee 均被覆盖）。受保护路径仍拦截（命令文本含受保护片段即拦），仅 awaiting 执法对任意解释器写存在盲区；属模式检测固有成本，建议在 guard 注释或 spec 注明范围，不作为本轮判死项。
- **R2（flow 豁免正则 hijack）**：**充分**。`_is_privileged_cli`（workflow_guard.py:254-274）对 `&&`/`;`/`|`/反引号/`$()`/换行/重定向 fail-closed；子命令白名单 `(status|confirm|approve|block|advance)`。实测：`flow status && echo > docs/known-debt.md`、`; echo`、反引号、换行拼接均 exit 2；`flow status | tee docs/known-debt.md`、`| grep x > docs/known-debt.md` 均 exit 2；`flow status | cat`（纯只读管道，无写意图）exit 0 属正确放行；`flow confirm/block/advance` 合法豁免 exit 0。
- **R3（投影==replay 同源恒真）**：**不恒真，防篡改有效，残余同源面未变**。`verify_projection`（event_log.py:481-508）比较「磁盘 workflow-state.json 字面 JSON」与「事件即时 replay 重建」两条路径；人为篡改 → mismatch 检出（实测 + `test_verify_projection_gen2_disk_matches_and_tamper_detected`）。残余：磁盘投影由同一 `project_workflow_state` 写入，投影函数自身 bug 时磁盘==replay 恒等，D6 声称的「独立实现路径」未完全落实——Round 1 已记录为轻微设计口径偏差，本轮未改。
- **R4（awaiting 建模 blocked.sub_state replay 兼容）**：**正确**。`_apply_blocked_to_state` 拒非 awaiting sub_state（I5）；`_apply_unblocked_to_state`（event_log.py:471-478）不依赖 blockers，无 blocked_entered 前置记录不抛错（Q9，`test_project_new_gen_unblock_without_blocker_record`）；`flow confirm` 恢复目标从最近 blocked_entered 的 transition.from 推导、缺省回退 `_AWAITING_RECOVERY_DEFAULTS`（workflow_state.py:833-844）；老世代 handoff replay（`replay_handoff_projection`）未改，parity 测试锁定。
- **R5（--check-archived 归档可投影校验）**：**符合设计**。`_check_archived_projectable`（checker:1054-1068）只验「结构合法 + 类型可识别」，不要求 seed、不要求磁盘投影。实测 20/20 归档可投影不抛错；未知事件类型 → 报「不可投影」（`test_check_archived_projectable_rejects_unknown_event`）；gen-0 无 seed 可投影（`test_check_archived_no_seed_projectable`）。

## Other Notes

- 全量 pytest 中 `tests/agent/mcp/test_mcp_manager.py` 5 个失败为 MCP fixture 发现的环境问题，未触及任何被改模块（event_log/workflow_state/workflow_guard/checker），与本次 change 无关；实现者声称的「1 个 pre-existing tree-sitter 环境失败」在本审阅环境未复现（本环境改为 MCP 失败），两者均非本 change 回归。
- `--check-archived` 的 7 处「tasks hash mismatch」为归档 review manifest 与 tasks.md 的 pre-existing drift（proposal.md:90 已记录为债务，本 diff 不含 archive/ 改动）。
- 审阅中运行 `flow status --all` 会在其他 active change 目录（add-worktree-tool / update-design-review-method）自愈落盘 `workflow-state.json` + `handoff.json` 映射（Q3 设计行为）；审阅者已清理这些由审阅命令产生的 untracked 文件，恢复工作区原状。
- 当前 spec 中「guard 读投影执法」场景已随 Round 1 修复正确同步（Write/Edit 与 write-intent Bash、replay 判定、事件不完整 fail-closed），与实现一致；仅上述 S1/S2 两条 spec 文本残留不一致。
