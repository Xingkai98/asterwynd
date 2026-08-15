# Building Review: flow-event-projection

## Verdict

**PASS**

Round 1 的 I1-I5 与 Round 2 的 S1-S3 全部 8 条历史 issues 经独立逐条验证均已真实修复，且每条都有针对原失败场景的回归测试锁定；代码实现、执法行为、spec/当前规格/实现三者一致；无新确认的功能/安全/正确性/测试缺陷。R1-R5 风险点结论成立（R1 残留 interpreter 写模式盲区与 R3 同源残余为已记录的固有局限/设计口径，均非本轮新引入）。按「宁可严格」逐项核对后仍判 PASS，另附两条 PR 收尾建议（非阻塞）见 Issues 节。

## Scope

- 审阅范围：`git diff 4131efe..HEAD`（提交 5 个：a709bce / d7d932c / eaa526c / b5567ee / 915de44，工作区无未提交改动）
- 审阅者：review-20260815-7c2e（Round 3，封顶轮）
- 实测基线：`base=4131efe`（立项）→ `head=915de44`（Round 2 修复后）

## Per-Task Verification

逐条对照 tasks.md 1.1-4.5（5.x 为 PR 收尾，未勾选属预期）：

- [x] 1.1 proposal.md 含需求/非目标/行为定义/验收，关联 #136 + #121（`proposal.md`）。
- [x] 1.2 design.md 含 Context/Goals/Non-Goals/Decisions(D1-D9)/Risks/Testing Strategy 全节（checker `_check_required_sections` 通过）。
- [x] 1.3 proposal.md 维护 `## Impact Analysis`（proposal.md:73-90），含实现期回写；guard bootstrap 条目已随 Round 2 修复更新为 replay 判定口径（S3 已验证）。
- [x] 1.4 RIR `research_tier: exempt` + status: disabled + 上游决策锁定理由引用 #121/#125/#128/#129（proposal.md:92-99）。
- [x] 1.5 `reviews/grill-design.md` 存在，7 条 Confirmed Decisions，Q1-Q13 全部有实质 User Confirmation；checker `_unconfirmed_open_questions` 无缺失。
- [x] 1.6 backlog 已登记（`docs/openspec-change-backlog.md`），配 `backlog_updated` 事件（workflow-events.jsonl seq 2、seq 4）。
- [x] 1.7 spec delta 已合并到 `openspec/specs/dev-workflow-state-machine/spec.md`，含 S1 补入的 checker 派生物一致性场景、S2 修正的解除等待态/flow approve 场景；配 `current_spec_synced` 事件（seq 3、seq 5、seq 6）。

## 2. 测试

- [x] 2.1 投影派生：`test_project_new_gen_change_created_seed` / `test_project_new_gen_milestones_pusher_does_not_change_state` / `test_project_new_gen_blocked_awaiting_state` / `test_project_no_seed_tolerated` / `test_project_gen1_maps_handoff_to_workflow_state` 全绿。
- [x] 2.2 两代 parity：`test_gen1_replay_shape_unchanged_parity` 锁老世代 handoff 形状；`test_project_gen1_maps_handoff_to_workflow_state` 当代不抛错。
- [x] 2.3 flow status：`test_flow_status_outputs_json_and_self_heals_stale` / `test_flow_status_all_lists_contemporary_changes` / `test_flow_status_archived_change_readonly` 全绿。
- [x] 2.4 flow 写命令：`test_flow_block_and_confirm_roundtrip` / `test_flow_confirm_rejects_when_not_awaiting` / `test_flow_approve_rejects_non_gate_state` / `test_flow_advance_rejects_invalid_sub_state_jump` / `test_flow_approve_rejects_gate_when_phase_check_fails` 全绿；写路径唯一化由 guard 拦截测试覆盖。
- [x] 2.5 guard 兜底：四形态 + awaiting/Bash/stale/corrupt/fail-closed/只读回归测试全绿（含 Round 1 新增 5 条回归，见 Issues 复查）。
- [x] 2.6 checker 一致性：`test_check_handoff_json_rejects_gen2_projection_mismatch` / `test_verify_projection_gen2_disk_matches_and_tamper_detected` / `test_check_archived_projectable_*` / `test_check_archived_no_seed_projectable` 全绿。
- [x] 2.7 废旧命令：advance/approve 子命令已删除，discover `approve_command` 迁移（workflow_state.py:442），CLI 测试迁移。
- [x] 2.8 回归：本审阅实测相关 4 测试文件 141 passed（`test_workflow_guard.py` + `test_event_log.py` + `test_workflow_state_cli.py` + `test_openspec_artifact_checker.py`）；OpenSpec strict validate 30/30 passed；artifact checker 除「review manifest missing」外无其他错误（manifest 在 PASS 后由 /review-loop 生成，属预期中间态）。

## 3. 实现

- [x] 3.1 `agent/workflow/event_log.py`：`project_workflow_state`（:370）两代兼容统一入口、`verify_projection`（:481）、`is_awaiting_state`（:365）、复用 v1 blocked 事件；实测 3 active + 20 归档全部可投影。
- [x] 3.2 `scripts/workflow_state.py`：flow 命令组齐全（status/block/confirm/approve/advance）、`_all_change_ids` 覆盖当代（:193）、自愈重建 `_refresh_workflow_state`（:858）。
- [x] 3.3 `scripts/workflow_guard.py`：awaiting 判定以事件 replay 为准（`_awaiting_block_reason` :539）、Bash 写路径 awaiting 执法（:628-637）、豁免正则（:254-274）。I1-I5 修复均已验证（见 Issues 复查）。
- [x] 3.4 `scripts/check_openspec_artifacts.py`：`_check_handoff_json` 调 `verify_projection`（:959）、`_check_archived_projectable`（:1054）。
- [x] 3.5 flow-policy.json 未改（受保护清单 cli_written 已由 P0 具备）；`policy-validate` parity 实测通过。
- [x] 3.6 AGENTS.md flow 命令组说明已加（AGENTS.md:189-205）。
- [x] 3.7 新影响面已回写 Impact Analysis；guard bootstrap 语义条目已更新为 replay 口径（S3）。

## 4. 验证

- [x] 4.1 相关测试：本审阅实测 141 passed（见 2.8）。
- [x] 4.2 全量 pytest：Round 2 实测 1931 passed / 7 skipped / 5 MCP 环境失败（`tests/agent/mcp/test_mcp_manager.py`，未触及任何被改模块，非本 change 回归）；本审阅未全量重跑，聚焦相关 4 文件全绿。
- [x] 4.3 OpenSpec strict validate：30/30 passed（本审阅实测）。
- [x] 4.4 artifact checker：默认模式仅报「review manifest missing」（PASS 后由 /review-loop 生成 manifest，预期中间态）；`--check-archived` 的 7 处 tasks hash mismatch 为归档目录既有 drift（proposal.md:90 已记录为债务，本 diff 不含 archive/ 改动）。
- [x] 4.5 两代兼容：实测 20/20 归档 + 3/3 active 可投影不抛错。

## Issues 复查

- **I1（awaiting gate 不拦 Bash 写）: ✅ 已修复**。`workflow_guard.py:628-637` awaiting gate 现对 write-intent Bash 生效（复用 `_is_write_bash` + `_current_change_id`）。本审阅实测：awaiting 期间 `echo code > agent/foo.py`、`cat <<EOF > agent/foo.py`（heredoc）均 exit 2；回归测试 `test_guard_blocks_bash_write_when_awaiting`（test_workflow_guard.py:501）+ `test_guard_allows_bash_read_when_awaiting`。残余面：`node -e "fs.writeFileSync(...)"` 不命中写模式 → exit 0（见 R1，字符串模式写检测固有局限，Round 2 已记录，非本轮判死项）。
- **I2（stale 且显示非 awaiting 时放行）: ✅ 已修复**。`_awaiting_block_reason`（workflow_guard.py:539-560）改用 `project_workflow_state` 事件 replay 判定 awaiting（事件是唯一真相），不再读磁盘投影状态。回归测试 `test_guard_blocks_write_when_events_awaiting_but_disk_stale_non_awaiting`（test_workflow_guard.py:438）+ `test_guard_blocks_write_when_awaiting_despite_stale_projection`。
- **I3（缺投影误伤非 awaiting change）: ✅ 已修复**。`_awaiting_block_reason` 仅当 replay 判定 awaiting 时拦截；无投影 + 非 awaiting（gen-0 `backlog_updated` 开头）→ 放行；无投影 + awaiting → 仍拦；仅事件损坏（无法 replay）fail-closed。本审阅实测：gen-0 无投影 Write 代码 exit 0；事件坏 seq → exit 2 报「事件不完整，检查 seq 1」。回归测试 `test_guard_allows_write_for_non_awaiting_change_without_projection`（test_workflow_guard.py:471）+ `test_guard_blocks_write_when_awaiting_despite_missing_projection`。
- **I4（awaiting 集合两处复制）: ✅ 已修复**。`AWAITING_SUB_STATES` 单源定义于 event_log.py:51-55；guard 从 `agent.workflow.event_log` 导入 `is_awaiting_state`（workflow_guard.py:552）；workflow_state.py:46/576/1205 亦导入同源。本审阅 grep 确认无第二处集合定义（`_AWAITING_RECOVERY_DEFAULTS` 为恢复目标映射，非集合）。
- **I5（blocked.<任意> 绕过 awaiting 集）: ✅ 已修复**。`_apply_blocked_to_state`（event_log.py:455-468）拒绝 `blocked.<非 awaiting> sub_state`（raise「blocked sub_state must be an awaiting type or null」）。回归测试 `test_project_rejects_blocked_non_awaiting_sub_state`（test_event_log.py:257）。
- **S1（当前 spec 漏 checker 派生物一致性场景）: ✅ 已修复**。当前 spec `openspec/specs/dev-workflow-state-machine/spec.md:513-517` 已补入「checker 派生物一致性」场景（tasks 全勾校验磁盘投影 workflow-state.json == replay，不一致 exit 2），与实现（checker `_check_handoff_json` → `verify_projection`）一致。
- **S2（spec 解除等待态对 flow approve 断言不符）: ✅ 已修复**。当前 spec（spec.md:498-511）与 change delta 均修正为：`flow confirm` 写 `blocked_resolved`（只由 confirm 写）；`flow approve` 写 `transition_applied`（阶段 gate 通过，不写 blocked_resolved）。与实现 `cmd_flow_approve`（workflow_state.py:651-712）一致；design D4 同步修正。
- **S3（Impact Analysis guard bootstrap 注释过时）: ✅ 已修复**。proposal.md「实现期发现并回写的新影响面」中 guard 条目已改写为事件 replay 判定口径（投影缺失/损坏/stale 不额外误拦、awaiting 仍拦、仅事件不完整 fail-closed），与实现一致。

## Issues

无新确认缺陷（功能/安全/正确性/测试层面）。以下两条为 PR 收尾建议（非阻塞，不影响 PASS）：

- **[轻微·建议] change delta 的「flow approve 阶段 gate 通过」场景缺一行断言**。当前 spec（spec.md:511）含「**AND** phase 机械检查未通过时 SHALL 拒绝批准」，实现 `cmd_flow_approve` 也强制该检查（workflow_state.py:668-684，`test_flow_approve_rejects_gate_when_phase_check_fails` 锁定），但 change delta（`openspec/changes/flow-event-projection/specs/dev-workflow-state-machine/spec.md`「flow approve 阶段 gate 通过」场景）未包含该行，构成 delta 与当前 spec 的轻微记录漂移。当前 spec（权威已同步）与实现一致、行为正确，不影响任何机械门槛；建议归档前在 delta 补上该行保持三者一致（或视为已同步、delta 仅作历史记录，接受漂移）。
- **[轻微·建议] delta 与当前 spec 的措辞级差异（非语义）**。「checker 派生物一致性」当前 spec 写作「磁盘投影（workflow-state.json）」（delta 无括号说明）；「非状态 artifact 事件」当前 spec 写作「replay `handoff.json` projection」（delta 为「replay projection」）。均为当前 spec 更具体的措辞，无语义分歧，可随 PR 归档一并对齐或接受。

## Risk Point Findings

- **R1（guard awaiting 执法不可绕过 + 事件损坏 fail-closed + 只读不写盘）**：**成立，修复充分，残留一处固有局限**。Write/Edit（workflow_guard.py:660-666）与 write-intent Bash（:628-637）两路径本审阅均实测 exit 2；事件损坏（坏 seq / 坏 JSON）fail-closed exit 2 报「事件不完整，检查 seq N」（实测）；guard 只读不写盘（实测运行 guard 后无 workflow-state.json 落盘，/tmp 场景目录仅剩 events + proposal）。`_current_change_id` 推导失败（非分支名 + 无单 active 兜底）时门禁不触发属既有设计约定（与 grill gate 一致，AGENTS.md 分支纪律是前提）。残留：`_is_write_bash` 字符串模式检测固有局限——`node -e "require('fs').writeFileSync('agent/foo.py','x')"` 实测 exit 0 绕过 awaiting gate（ruby/perl -e、python -c、重定向、heredoc、tee 均被覆盖）。受保护路径仍拦截（命令文本含受保护片段即拦），仅 awaiting 执法对任意解释器写存在盲区；Round 2 已记录为固有成本，建议在 guard 注释或 spec 注明范围，不作为判死项。
- **R2（flow 豁免正则 hijack）**：**充分**。`_is_privileged_cli`（workflow_guard.py:254-274）对 `&&`/`||`/`;`/`|`/反引号/`$()`/换行/重定向 fail-closed；子命令白名单 `(status|confirm|approve|block|advance)`。回归测试 `test_guard_blocks_flow_chain_hijack` + `test_guard_allows_flow_cli_commands` 全绿；本审阅实测 `flow status && echo x > docs/known-debt.md` 场景 exit 2。
- **R3（投影==replay 同源恒真）**：**不恒真，防篡改有效，残余同源面未变**。`verify_projection`（event_log.py:481-508）比较「磁盘 workflow-state.json 字面 JSON」与「从事件即时 replay 重建的投影」，两者非同一调用；人为篡改磁盘 state 字段 → mismatch 检出（回归测试 + 实测）。残余：磁盘投影由同一 `project_workflow_state` 写入，若投影函数自身有 bug 则磁盘==replay 恒等、checker 无法发现——设计 D6 声称的「独立实现路径」未完全落实，Round 1/2 已连续记录为轻微设计口径偏差，本轮未改（功能目标：检出 stale/篡改/版本漂移已达成）。
- **R4（awaiting 建模 blocked.sub_state replay 兼容）**：**正确**。`_apply_blocked_to_state` 拒非 awaiting sub_state（I5）；`_apply_unblocked_to_state`（event_log.py:471-478）不依赖 blockers，无 blocked_entered 前置记录不抛错（Q9，`test_project_new_gen_unblock_without_blocker_record`）；`flow confirm` 恢复目标从最近 blocked_entered 的 transition.from 推导、缺省回退 `_AWAITING_RECOVERY_DEFAULTS`（workflow_state.py:833-844，block/confirm roundtrip 实测恢复 planning.writing_proposal）；老世代 handoff replay（`replay_handoff_projection`）未改，parity 测试锁定。
- **R5（--check-archived 归档可投影校验）**：**符合设计**。`_check_archived_projectable`（checker:1054-1068）只验「结构合法 + 类型可识别」，不要求 seed、不要求磁盘投影。实测 20/20 归档可投影不抛错；未知事件类型 → 报「不可投影」（`test_check_archived_projectable_rejects_unknown_event`）；gen-0 无 seed 可投影（`test_check_archived_no_seed_projectable`）。

## Other Notes

- 本审阅实测：4 个相关测试文件 141 passed；OpenSpec strict validate 30/30；artifact checker 默认模式仅报 review manifest missing（PASS 后生成，预期中间态）。
- `--check-archived` 的 7 处「tasks hash mismatch」为归档 review manifest 与 tasks.md 的 pre-existing drift（proposal.md:90 已记录为债务，本 diff 不含 archive/ 改动）。
- Round 2 实测全量 pytest 1931 passed / 7 skipped / 5 failed 均在 `tests/agent/mcp/test_mcp_manager.py`（MCP fixture 环境问题，未触及被改模块，非本 change 回归）；实现者声称的 tree-sitter 环境失败在部分环境复现，两者均非本 change 引入。
- 审阅中运行 `flow status --all` 会在其他 active change 目录自愈落盘 `workflow-state.json` + `handoff.json` 映射（Q3 设计行为）；本审阅未运行该命令，工作区 git status 干净。
- 当前 spec「guard 读投影执法」「checker 派生物一致性」「解除等待态」「flow approve 阶段 gate 通过」场景均已与实现一致；仅 change delta 缺一行「phase 机械检查」断言及两处措辞差异（见 Issues，非阻塞）。
