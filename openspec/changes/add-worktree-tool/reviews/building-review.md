# Building Review: add-worktree-tool (Round 2)

## Reviewer

- run id: ba39bffa-27bb-4aa9-b159-15f82003c53b（独立零记忆 subagent）
- 时间: 2026-08-08
- 审阅范围: `git diff origin/master...HEAD`（三个提交：7e661e4 grill/文档整合 + 454bebe 实现 + 922bc45 R1 修复）
- 测试环境: 本 worktree 内 `source ~/my-agent/.venv/bin/activate` + `python3 -m pytest`

## Round 1 修复验证

- **R1-1 [中] ExitWorktree 越权边界：已修复**。
  `_is_tool_created_worktree`（`agent/tools/builtin/worktree.py:24-33`）实现正确：`path.resolve().relative_to((repo / WORKTREE_SUBDIR).resolve())`，两侧均 resolve 归一化，`..`/符号链接场景一致；ExitWorktree 内检查位置在"是否在 worktree"判定之后、任何状态变更之前（worktree.py:237-241），编排层/benchmark worktree 返回 `not_in_worktree` 且 policy root 与 worktree 均不变。验证：单测 `test_exit_worktree_rejects_non_tool_created`（test_worktree_tools.py:209-221，断言 policy root 未切回、worktree 未被删）+ registry 层 smoke `test_rejected_in_orchestration_worktree`（test_worktree_benchmark_smoke.py:60-81）。工具描述（worktree.py:200-204）已声明"仅对 EnterWorktree 工具自建的 worktree 生效"。
- **R1-2 [中] 任务 2.5 证据：已修复（主套件证据充分），但沉淀的 benchmark task 存在可运行性缺陷（见 New Issue 1）**。`benchmarks/tasks/asterwynd-008-worktree-tools/` 四文件齐全；task.json 经 `benchmarks/task_schema.load_task` 加载通过（字段与 001/005 等既有任务一致）；test.patch 与主套件 `tests/agent/tools/test_worktree_benchmark_smoke.py` **逐字节一致**（diff 无差异），主套件实际运行 3 个 smoke 测试全绿（断言强度足够：注册/schema/权限元数据/编排层双工具拒绝 + 状态不变）。
- **R1-3 [低-中] D2 兜底：已修复**。add 失败后显式执行 `_run_git(repo, "worktree", "remove", str(wt_path))` 兜底再返回 `worktree_create_failed`（worktree.py:165-172）；rebind 失败且 remove 回滚失败时返回部分成功 text（明确"worktree 保留"+ 回滚 stderr，worktree.py:176-189）。残留：add 失败路径的 remove 返回值未检查（见 New Issue 4）。
- **R1-4 [低] name 前置校验：已修复（`-` 开头子项声明不实，见 New Issue 3）**。`_is_valid_worktree_name`（worktree.py:99-110）在 mkdir 副作用（worktree.py:161-162）之前执行（worktree.py:155），cwd 参数正确传入 `_run_git(repo, ...)`；空名/`.`/`..`/含 `/`/空格/`.lock`/`..` 全部前置拒绝（实测 `git check-ref-format --allow-onelevel refs/heads/<name>`：`a b`/`..`/`.`/`a.lock`/`a..b` rc=1）。路径穿越（`..`/`/`）已无目录副作用窗口。
- **R1-5 [低] git 超时：已修复**。`_run_git` 捕获 `subprocess.TimeoutExpired` 映射 returncode=124 + stderr 超时说明（worktree.py:43-58），超时值 10s→30s；124 为非零，落入 add 失败路径 → `worktree_create_failed`。MCP 相关测试因缺 uv 失败为既有 baseline。
- **R1-6 [低] 测试缺口：已修复（清单三项齐备）**。`test_enter_worktree_invalid_name_rejected`（test_worktree_tools.py:196-205，5 种非法名逐一断言无残留 worktree）、`test_enter_worktree_detached_head`（test_worktree_tools.py:225-234，detached 时以 HEAD 为 base 成功创建）、`test_exit_worktree_rejects_non_tool_created`（test_worktree_tools.py:209-221）。R1 报告 Issue 6 的其余两项（ExitWorktree 切回后 remove 失败部分成功、read_only/plan 模式 DENY）仍无测试，属低危残留。

## Verdict

**CHANGES_REQUESTED** —— R1 的 6 项问题均已实质修复且核心语义验证充分（23 个测试全绿），但任务 2.5 沉淀的 benchmark task 交付物有缺陷：`test.patch` 是纯文件内容而非 unified diff，benchmark harness（`benchmarks/runner.py:733` 的 `git apply`）在 base commit 454bebe 上应用失败（实测 exit 128 "No valid patches in input"），该 task 无法经 benchmark 运行器执行。修复范围单一（重新生成 patch 格式并验证 `git apply --check`），其余为低危建议项。

## New Issues

- [中] **benchmark task 的 test.patch 非 patch 格式，harness 无法应用**：`benchmarks/tasks/asterwynd-008-worktree-tools/test.patch` 是待测文件的纯内容（首行 `# tests/agent/tools/test_worktree_benchmark_smoke.py`），而既有任务（001/005 等）的 test.patch 均为 `diff --git` 格式。实测：在 base commit 454bebe 检出上 `git apply --check test.patch` → `error: No valid patches in input (allow with "--allow-empty")`，exit 128；runner 的 `_apply_test_patch`（benchmarks/runner.py:733-741）对非零返回值直接 raise RuntimeError，未来任何 `run_all` 批量 benchmark 运行都会在该任务上失败。修复：用 `git diff`（新文件相对空索引）重新生成 test.patch 并在 454bebe 上 `git apply --check` 验证；或如认定该任务仅供主套件运行，需修改 tasks 2.5/4.6 描述避免"沉淀 benchmark task"的误导。gold.patch 为 0 字节（runner 不参与打分，swebench_convert.py:152 注释"reference only"），可接受。
- [低] **design.md 未回写 ExitWorktree 新边界**：R1-1 修复（仅工具自建 worktree 可退出/删除，用户确认）只记录在 tasks.md 审阅修复记录（tasks.md:33）和代码注释/工具描述，design.md D7（design.md:78-81）与 Risks 节（design.md:109）仍只写"编排层 worktree 内 EnterWorktree 恒被拒"，未提 ExitWorktree 的 `not_in_worktree` 边界；模块 docstring（worktree.py:8-9）同样只述 EnterWorktree。spec delta（specs/tool-system/spec.md）7 个场景与新行为不冲突（新行为映射既有 `not_in_worktree` 错误），无需改 spec。收尾前应把边界写回 design.md 与 docstring。
- [低] **`_is_valid_worktree_name` 对 `-` 开头名的"前置校验"声明不实**：tasks.md:36 称 check-ref-format 禁止"`-` 开头"，但实测 `git check-ref-format --allow-onelevel refs/heads/-leading` 返回 rc=0（`-` 规则只作用于 refname 整体而非成分），`_is_valid_worktree_name` 对 `-leading` 返回 True。实际由 `git worktree add -b -leading` 在分支创建处拒绝（`name[0]=='-'`），端到端行为仍正确（测试通过、无 worktree 残留），但前置校验被绕过，留下空目录 `.asterwynd/worktrees/-leading/` 副作用（在 `.asterwynd/` 内且被 gitignore，无害）。可在 check-ref-format 之外显式加 `name.startswith("-")` 拒绝，或修正 tasks.md 描述。
- [低] **add 失败路径的 remove 兜底返回值未检查**（worktree.py:168）：设计 D2 字面要求"显式 verify `git worktree list` 中无该 worktree"，实现改为无条件 remove 且不检查结果；若 remove 也失败（超时/被杀），残留注册与 text 中仅有原始 add 错误。双失败概率极低，建议后续在 text 中合并 remove 失败信息（与 rebind 回滚路径 worktree.py:176-189 的写法一致）。
- [流程] **artifact checker 当前报错**：`scripts/check_openspec_artifacts.py` 报 `review manifest missing: openspec/changes/add-worktree-tool/reviews/building-review-manifest.json`。这是本轮 verdict 之前的预期状态；R2 修复后若审阅 PASS，必须由 /review-loop 生成绑定 R2 报告的 manifest，CI 门禁才可通过。

## Test Results

```
$ python3 -m pytest tests/agent/tools/test_worktree_tools.py tests/agent/tools/test_worktree_benchmark_smoke.py -q
23 passed in 1.80s
```

（test_worktree_tools.py 20 个 + test_worktree_benchmark_smoke.py 3 个；MCP 相关测试因环境缺 uv 未跑，已知 baseline。）

专项实测：
- `git apply --check`（454bebe 检出上应用新 test.patch）→ `error: No valid patches in input`，exit 128（确认 New Issue 1）。
- `git check-ref-format --allow-onelevel refs/heads/<name>` 探测：`-leading` rc=0（绕过前置校验），`a b`/`..`/`.`/`a.lock`/`a..b` rc=1（正常拒绝），`HEAD`/`@` rc=0（由 git 下游拒绝，无害）。
- `load_task('benchmarks/tasks/asterwynd-008-worktree-tools')` 加载通过。
- 全量 pytest 未重跑（4.2 勾选声称 1823 通过，本次按指示只跑相关套件）。

## 结论

R1 全部 6 项问题均得到实质修复，核心实现质量保持良好：ExitWorktree 越权边界修复正确且被单测+registry 层 smoke 双层验证（状态不变断言到位）；name 前置校验消除了路径穿越与目录副作用窗口；add 失败 remove 兜底与回滚部分成功 text 落位；超时映射 124 落入结构化错误码；R1-6 清单三项测试齐备。`_is_tool_created_worktree` 的路径约定边界（手动建在 `.asterwynd/worktrees/` 下的 worktree 会被视为工具自建）是用户确认过的设计取舍，非新缺陷。

阻止合入的一项：benchmark task `asterwynd-008-worktree-tools` 的 test.patch 非 unified diff，harness `git apply` 失败，2.5 的"沉淀 benchmark task"交付物不可运行。修复方式机械（重新生成 patch 并在 base commit 验证 `git apply --check`），另建议同提交回写 design.md D7/模块 docstring 的 ExitWorktree 边界。修复后应进入 Round 3 审阅；PASS 后须生成 review manifest 才能过 CI 门禁（1.7/5.x 收尾任务仍待完成）。
