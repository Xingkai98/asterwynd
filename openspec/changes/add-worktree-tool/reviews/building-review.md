# Building Review: add-worktree-tool (Round 3)

## Reviewer

- run id: fc8263e9-38ca-4ba0-bd51-e895d7694f39（独立零记忆 subagent，PASEO_AGENT_ID）
- 时间: 2026-08-08
- 审阅范围: `git diff origin/master...HEAD`（四个提交：7e661e4 grill/文档 + 454bebe 实现 + 922bc45 R1 修复 + 9bc3573 R2 修复）
- 测试环境: 本 worktree 内 `source ~/my-agent/.venv/bin/activate` + `python3 -m pytest`

## Round 2 修复验证

- **R2-1 test.patch 格式：已修复**。`benchmarks/tasks/asterwynd-008-worktree-tools/test.patch` 首行为标准 diff 头 `diff --git a/tests/agent/tools/test_worktree_benchmark_smoke.py b/tests/agent/tools/test_worktree_benchmark_smoke.py` + `new file mode 100644`（87 行）。模拟 runner 流程：`rm` 目标文件 → `git apply --check` rc=0 → `git apply` rc=0 → `git checkout --` 恢复，工作树干净；应用结果与主套件 `tests/agent/tools/test_worktree_benchmark_smoke.py` 逐字节一致（diff 无差异）。`git ls-tree 454bebe tests/agent/tools/` 确认该文件不在 base 树中（该文件由 922bc45 引入），runner 的 reset→apply 注入路径可行。
- **R2-2 文档回写：已修复**。D3（design.md:55-58）前置校验新增"且该 worktree 必须是 EnterWorktree 工具自建的（路径位于 `.asterwynd/worktrees/` 下，`_is_tool_created_worktree` 判定）。编排层/benchmark 任务 worktree 不在该约定下，工具拒绝退出/删除（否则 agent 可删掉任务 worktree 破坏 benchmark）——review-loop R1 用户确认新增边界"；D7（design.md:81）显式声明"ExitWorktree 同样仅对工具自建 worktree 生效（D3 边界）——显式声明此边界"；`_is_tool_created_worktree` 函数 docstring（worktree.py:28-31）与 ExitWorktree 工具描述亦覆盖该边界。模块 docstring（worktree.py:8-9）仍只展开 EnterWorktree 拒绝面，属微瑕疵，非阻断。
- **R2-3 `-` 前缀声明：已修复**。`_is_valid_worktree_name` docstring（worktree.py:101-105）改为"允许 `-` 开头但分支创建会拒绝"，与实测一致（`git check-ref-format --allow-onelevel refs/heads/-leading` rc=0 通过前置校验、分支创建处下游拒绝）。
- **R2-4 add 失败路径 remove 返回值：未修复（R2 自评 [低] 非阻断，维持）**。add 失败分支（worktree.py:169-172）的 `_run_git(repo, "worktree", "remove", str(wt_path))` 返回值仍被丢弃，与 rebind 回滚路径（worktree.py:176-189，text 合并 remove stderr 并明示 worktree 保留）写法不一致。双失败（add 失败且 remove 也失败）概率极低，维持 R2 的 [低] 分级，不阻断本轮。

## Verdict

**CHANGES_REQUESTED** —— R2 的三项修复（test.patch 格式、design.md D3/D7 回写、`-` 声明修正）全部到位且经实测验证；主套件 23 测试全绿；实现代码未发现新问题。但 Round 3 实测发现 benchmark task `asterwynd-008-worktree-tools` 存在新的自洽性缺陷（New Issue 1）：task.json 的 base_commit=454bebe 与其 issue.md/test.patch 三方矛盾，任务在其声明 base 上必然失败，且失败过程实测复现了测试所防的越权删除行为。修复为 issue.md 措辞/组合微调（见 New Issue 1），机械、不影响产品代码。

## New Issues

- [中] **benchmark task base_commit 与 issue.md 自相矛盾，任务在其声明 base 上必失败**：`benchmarks/tasks/asterwynd-008-worktree-tools/task.json` base_commit=454bebe，而 test.patch 断言的"编排层 worktree 内 ExitWorktree 返回 `not_in_worktree`"边界是 922bc45（R1 修复）才落地的行为，454bebe 的 ExitWorktree 仅检查 `_toplevel != main`。实测（临时 worktree 检出 454bebe + `git apply` test.patch + pytest）：`test_rejected_in_orchestration_worktree` 失败（1 failed, 2 passed），ExitWorktree(keep=false) 实际切回 policy root 并删除编排层 worktree（ToolResult `{"workspace": ..., "removed": true}`、error_type=None）——正是该测试要防的行为。issue.md 明示 "no code changes required / The implementation already exists; confirm the tests pass against the current checkout"，与 base 实际状态冲突：忠实执行指示的 agent 零改动必然失败（对比 001：base cc06ee8 无 test_registry.py 与实现，issue.md 为实现型框架，测试后注入属标准 SWE-bench 模式）。修复选项：a) 保留 base 454bebe + test.patch，把 issue.md 措辞改为"实现缺失的边界行为使提供测试通过"（item 3 已给出完整边界规格，与 001 模式对齐）；b) 不可简单把 base_commit 改为 922bc45——该提交树上 smoke 文件已存在，new-file patch `git apply` 报 `error: tests/agent/tools/test_worktree_benchmark_smoke.py: already exists in working directory`（实测 rc=1）；c) 弱化 test.patch 至 454bebe 行为（丢失边界断言，不推荐）。修复后须在所选 base 上重跑 smoke 验证。
- [低] **add 失败路径 remove 返回值未检查（R2-4 残留）**：worktree.py:169-172，R2 自评 [低] 非阻断，本轮维持；建议后续与 rebind 回滚路径对齐（text 合并 remove stderr）。
- [流程] **review manifest 仍未生成**：`reviews/building-review-manifest.json` 缺失为 verdict 前预期状态；本轮修复后再审通过后，须由 /review-loop 生成绑定本报告的 manifest 才能过 CI 门禁。

## Test Results

```
$ python3 -m pytest tests/agent/tools/test_worktree_tools.py tests/agent/tools/test_worktree_benchmark_smoke.py -q
23 passed in 1.62s
```

（test_worktree_tools.py 20 个 + test_worktree_benchmark_smoke.py 3 个；MCP 相关测试因环境缺 uv 未跑，已知 baseline。）

专项实测（临时 worktree 检出，用后已删除）：
- **454bebe 检出 + test.patch**：`git apply` rc=0；`pytest tests/agent/tools/test_worktree_benchmark_smoke.py` → `1 failed, 2 passed`，失败断言 `exit_res.error_type == "not_in_worktree"` 实际为 None（ToolResult `{"workspace": "...", "removed": true}`）——越权删除行为被复现（New Issue 1 证据）。
- **922bc45 检出**：同一 smoke 测试 `3 passed`（边界行为在该提交起成立）。
- **922bc45 上 `git apply` test.patch** → rc=1 `already exists in working directory`（排除"仅改 base_commit"的修复路径）。
- **模拟 runner 流程（HEAD 上 rm + apply --check + apply + restore）**：全过，应用结果与主套件逐字节一致。
- 001 task 对照：base cc06ee8 树中无 test_registry.py（new-file patch 适用），issue.md 为实现型任务框架——008 的偏离点仅在 base_commit 选择与 issue.md"无需改动"声称。

## 结论

R2 三项修复全部到位且验证充分：test.patch 已是标准 a/b 相对路径 diff，模拟 runner 的 reset→apply 流程通过，应用结果与主套件一致；design.md D3/D7 已回写 ExitWorktree 仅限工具自建边界；`-` 前缀声明与实测行为一致。主套件 23 测试全绿，实现代码无新问题。主套件保留 smoke 测试与 test.patch 重复沿用 001 同模式（SWE-bench 式测试注入，runner reset 后应用），可接受。

但 benchmark 交付物仍有实质缺陷：base_commit=454bebe 与 test.patch/issue.md 三方不一致，任务在其声明 base 上必失败，且实测复现测试所防的越权删除——任务 2.5 的"沉淀 benchmark task"仍未达到可运行标准（R1/R2 同为该交付物阻断，本轮为其第三种形态）。修复为 issue.md 措辞或 base/patch 组合微调（见 New Issue 1），机械且不影响产品代码；修复后应做最终确认，PASS 后由 /review-loop 生成 review manifest。
