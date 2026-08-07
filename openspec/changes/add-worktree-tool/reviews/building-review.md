# Building Review: add-worktree-tool (Round 4, final)

## Reviewer

- run id: fc8263e9-38ca-4ba0-bd51-e895d7694f39（独立零记忆 subagent，PASEO_AGENT_ID）
- 时间: 2026-08-08
- 审阅范围: `git diff origin/master...HEAD`（五个提交：7e661e4 grill/文档 + 454bebe 实现 + 922bc45 R1 修复 + 9bc3573 R2 修复 + 43ffd4a R3 修复）
- 测试环境: 本 worktree 内 `source ~/my-agent/.venv/bin/activate` + `python3 -m pytest`；benchmark 闭环用临时 clone 检出 base 实测（用后已删除）

## Round 3 修复验证

- **R3-1 benchmark task base_commit 矛盾：已修复**。task.json 保持 base_commit=454bebe，issue.md 已改为实现型任务（"Fix ExitWorktree to only exit tool-created worktrees"），明确描述越权边界缺陷（454bebe 上 ExitWorktree 可切出/删除任意 linked worktree 含编排层任务 worktree），不再有"无需改动"声称。三项闭环全部实测通过：
  - `git apply --check` test.patch 于 454bebe 检出上 rc=0（`git ls-tree 454bebe tests/agent/tools/` 确认 smoke 文件不存在于 base，new-file patch 适用），实际 apply 成功；
  - base + test.patch 测试红：`1 failed, 2 passed`，失败断言正是 `exit_res.error_type == "not_in_worktree"` 实际为 None（ToolResult `{"workspace": ..., "removed": true}`）——base 上越权删除行为被复现，issue.md 描述与 base 状态一致（边界未实现、测试红是期望）；
  - base + test.patch + gold.patch 测试绿：`3 passed`。
  - gold.patch 与 `git diff 454bebe 922bc45 -- agent/tools/builtin/worktree.py` 逐字节一致（`diff` 命令确认），即 R1 的 worktree.py 修复 diff：核心为越权修复（`_is_tool_created_worktree` 辅助函数 + ExitWorktree 前置校验，worktree.py:24-33/246-250），另含同轮 R1 修复（name 前置校验、超时映射 124、add 失败清理兜底）——宽于 issue.md 最小需求但均属有效输入路径行为不变的无害改动，且 smoke 测试只依赖边界修复，agent 最小解法即可通过。
- **R3-2 add 失败分支 remove 返回值：已修复**。worktree.py:169-177：`cleanup = _run_git(repo, "worktree", "remove", str(wt_path))` 检查 `cleanup.returncode != 0`，清理失败返回 `"Error: worktree 创建失败且清理未完成，worktree 可能残留: ...; 清理: ..."`（error_type `worktree_create_failed`），与 rebind 回滚路径（worktree.py:186-194）写法对齐。新增回归测试 `test_enter_worktree_add_failure_cleanup_checked`（monkeypatch `_run_git` 使 add 与 remove 均失败）断言 error_type、text 含"清理未完成"、policy root 不变；主套件 24 测试全绿（21 + 3 smoke）。

## Verdict

**PASS** —— Round 3 两项修复全部到位并经实测验证：benchmark task 闭环（base 红 → gold 绿）为标准 SWE-bench 验证形态，R1/R2/R3 三轮遗留的 benchmark 交付物问题终获解决；R2-4 残留的 remove 返回值问题已修复并有回归测试。实现代码未发现新问题，测试全绿。无残留中等以上问题。

## New Issues

- [低] **spec delta 未覆盖 R1 越权边界场景**：`openspec/changes/add-worktree-tool/specs/tool-system/spec.md` 自立项后未更新，场景仅覆盖创建/退出/删除/拒绝路径，缺"编排层/非工具自建 worktree 内 ExitWorktree 被拒且状态不变"场景（该边界由 design.md D3/D7 与 issue.md 覆盖）。非阻断：spec 同步（任务 1.7）属收尾步骤尚未执行，建议同步时补该场景。
- [低] **gold.patch 宽于 issue.md 需求**：issue.md 要求"EnterWorktree behavior must stay unchanged"，gold.patch 含 R1 的 name 校验与 add 失败清理兜底（仅影响非法 name 与失败路径，有效输入行为不变），与最小修复不一致但不影响任务可解性与评测。属 SWE-bench 常见 gold 噪声，不阻断。
- [流程] **review manifest 尚未生成**：`reviews/building-review-manifest.json` 缺失为 verdict 前预期状态；本报告 PASS 后须由 /review-loop 生成绑定本报告的 manifest 才能过 CI 门禁（artifact checker 当前唯一报错即此）。

## Test Results

```
$ python3 -m pytest tests/agent/tools/test_worktree_tools.py tests/agent/tools/test_worktree_benchmark_smoke.py -q
24 passed in 1.64s
```

（test_worktree_tools.py 21 个 + test_worktree_benchmark_smoke.py 3 个；MCP 相关测试因环境缺 uv 未跑，已知 baseline。）

专项实测（临时 clone 检出 454bebe，用后已删除）：
- **454bebe 检出**：`git apply --check` test.patch rc=0（smoke 文件不在 base 树，new-file patch 适用）；apply 后 pytest → `1 failed, 2 passed`，失败断言 `exit_res.error_type == "not_in_worktree"` 实际为 None（ToolResult `{"workspace": "...", "removed": true}`）——越权删除行为复现，与 issue.md 描述一致。
- **同检出 + gold.patch**：`git apply --check` rc=0、apply 后 pytest → `3 passed`。红→绿闭环成立，标准 benchmark 验证形态。
- **gold.patch 溯源**：与 `git diff 454bebe 922bc45 -- agent/tools/builtin/worktree.py` 逐字节一致（R1 worktree.py 修复 diff）。
- **HEAD 上 test.patch 与主套件一致性**：`git apply --check --reverse` rc=0，smoke 文件与 test.patch 逐字节一致。
- **artifact checker**：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 仅报 review manifest 缺失（预期，待 /review-loop 生成）；grill 证据、文档完整性等其余门禁全过。
- **文档一致性**：tasks.md 实现/测试任务全部 `[x]`（2.5 含 benchmark task 沉淀，已实测闭环），未勾选项均为 PR 收尾步骤（1.7 spec 同步、5.x 归档）；proposal.md 含 Impact Analysis 与 Reference Implementation Research（status: enabled，本地参考仓库不可用事实已记录）；grill-design.md 8 项 Open Questions 全部有用户确认记录（2026-08-07）；design.md D2/D3 已回写 R1 边界。

## 结论

Round 3 的两项阻断/遗留问题均已修复并验证充分：benchmark task `asterwynd-008-worktree-tools` 已从"在声明 base 上必失败的矛盾交付物"转为标准实现型任务（base 红 → gold 绿闭环实测通过，issue.md 与 base 状态一致）；add 失败分支 remove 兜底已检查返回值并有回归测试。主套件 24 测试全绿，实现代码无新问题，产品代码与主套件自 R2 起未再改动（R3 仅改 worktree.py 的 add 失败分支并补测试）。文档（proposal/design/tasks/spec delta/grill 确认）一致完备，剩余两项 [低] 与 [流程] 项均不阻断。**最终 verdict：PASS**。收尾动作：/review-loop 生成 review manifest 后即可进入归档收尾（spec 同步时建议补边界场景）。
