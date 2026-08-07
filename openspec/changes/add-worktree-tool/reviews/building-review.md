# Building Review: add-worktree-tool

## Reviewer

- run id: 4b4d1f2f-6d1e-4c18-8db3-2d1b5d5a5e21（独立零记忆 subagent）
- 时间: 2026-08-07
- 审阅范围: `git diff origin/master...HEAD`（两个提交：7e661e4 grill/设计文档整合 + 454bebe 实现；8 个文件，+688/-61）
- 测试环境: 本 worktree 内 `source ~/my-agent/.venv/bin/activate` + `python3 -m pytest`

## Verdict

**CHANGES_REQUESTED** —— 核心语义（创建/退出/重绑定/deny/回滚）实现正确且测试充分，但存在一处设计声明与实际行为不符的缺口（ExitWorktree 在编排层 worktree 内可执行并会把 policy root 切回主 checkout 甚至删除编排层 worktree），且任务 2.5 标注 [x] 但承诺的"专用验证脚本"和 benchmark smoke 无任何证据。

## Tasks Verification

逐条对照 tasks.md 的 [x] 项（1.7 / 3.7 / 4.x / 5.x 未勾选，属 PR 收尾工作，本次审阅覆盖实现部分）：

- **1.1** ✓ `openspec/changes/add-worktree-tool/specs/tool-system/spec.md` 存在 7 个场景的 delta（创建进入/非 git 拒绝/嵌套拒绝/退出保留/退出删除/删除被拒/不在 worktree 报错）。
- **1.2** ✓ proposal.md 明确范围、非目标与验收（已同步"keep=false 不删分支"、"dangerous=False + MEDIUM"、smoke 形态）。
- **1.3** ✓ `reviews/grill-design.md` 有 8 条 Confirmed Decisions（含实测证据）+ 8 条 User Confirmation（全部有实质答复与日期），无占位文本。
- **1.4** ✓ proposal.md Impact Analysis 每行均已收敛为明确结论（无 unknown/TBD）。
- **1.5** ✓ proposal.md `## Reference Implementation Research` status=enabled，记录了 `.dev/reference-repos.txt` 不可用事实（已核实 `.dev/` 不存在）与替代依据（Claude Code 公开行为），findings/design impact 已按用户确认更新。
- **1.6** ✓ design.md `## Pre-Implementation Review` 记录已解决/已否决/已确认边界/剩余风险。
- **2.1** ✓ 单测覆盖 schema、错误路径、keep 语义、分支名派生（`tests/agent/tools/test_worktree_tools.py`）。
- **2.2** ✓ 真实 git 仓库集成全流程：`test_enter_worktree_creates_and_rebinds` / `test_file_tool_boundary_rebound_into_worktree` / `test_exit_worktree_keep_*`。
- **2.3** ✓ 负向路径齐全：非 git 仓库（:156）、嵌套拒绝（:169）、dirty 删除被拒且状态不变（untracked :254 + tracked 修改 :272）、失败回滚 policy root 不变（:196）。
- **2.4** ✓（部分）registry 层测试断言 enter/exit 后 policy root 正确（:322）；无独立 AgentLoop 全循环测试，但设计即"不做 os.chdir、由 policy root 驱动"，registry 层断言覆盖了实际状态承载点。
- **2.5** ✗ **无证据**：tasks 声称"Q7 形态注册+schema+被拒路径由专用验证脚本覆盖"且"benchmark smoke 与 master baseline 一致无回归"——全仓搜索无任何"专用验证脚本"（scripts/、benchmarks/ 无 EnterWorktree/ExitWorktree 引用）；benchmark smoke 也未运行（4.6 未勾选佐证）。注册与嵌套被拒路径由单测覆盖，但 smoke 与脚本承诺无产出物。
- **3.1** ✓ `agent/tools/builtin/worktree.py:100-144` EnterWorktree 创建+切换+回滚。
- **3.2** ✓ `worktree.py:167-219` ExitWorktree keep/remove，顺序（预检→切出→删除）正确。
- **3.3** ✓ 重绑定（worktree.py:146-147）、权限元数据（base.py 默认 dangerous=False + WORKSPACE_WRITE/MEDIUM，`test_permission_metadata` 钉住）、`agent/workspace_policy.py:46` 新增 `.asterwynd/worktrees/**`。
- **3.4** ✓ 注册进 `agent/tools/factory.py` 两个工具集（:331-334、:444-448）并更新 `KNOWN_BUILTIN_TOOL_NAMES`（:108-112）；但 get_all_schemas() 暴露无直接测试（见 Issue 6）。
- **3.5 / 3.6** ✓ proposal/design 同 change 内回写（Impact Analysis 与 Reference Implementation Research 均已更新）。

## Issues

- **[中] ExitWorktree 在编排层 worktree（benchmark runner / building 强制 worktree）内可执行，与 D7"工具仅对主 checkout 会话有效"的声明不符**。
  `worktree.py:178-184` 前置校验只检查 `_toplevel(repo) != main`——该条件在编排层 worktree 内**满足**（git worktree list 首条目是主 checkout，当前 cwd 是 linked worktree）。后果：benchmark agent 位于任务 worktree 时（`benchmarks/agent_runner.py:298` 经 `build_coding_tool_registry` 注册了 ExitWorktree，policy root = 任务 worktree），调用 ExitWorktree 会把 policy root 重绑定到源仓库主 checkout（keep=true 即生效，文件工具边界随之打开对源仓库的访问）；keep=false 且 worktree 干净时会**删除 benchmark 的任务 worktree**（runner.py:473-476 创建于 task_output/.worktree），直接破坏 benchmark 基础设施。workflow building worktree 场景下同样可切回主 checkout（workflow_guard 写门禁是部分 backstop，但 policy root 重绑定本身已破坏编排层假设）。D7/proposal 的"恒被拒"声明只对 EnterWorktree 成立。需决策：限制 ExitWorktree 仅对工具自建 worktree 生效（如校验当前路径位于 `main/.asterwynd/worktrees/` 下），或显式修改声明与文档。

- **[中] Task 2.5 标注 [x] 但证据缺失**：承诺的"专用验证脚本"在 diff 与全仓中不存在；"benchmark smoke 与 master baseline 一致"无运行记录（4.6 未勾选）。应补跑 smoke 或修改任务描述，不能以未验证状态勾选。

- **[低-中] EnterWorktree add 失败路径未执行 design D2 要求的显式 verify**：design.md D2 写"工具显式 verify `git worktree list` 中无该 worktree"；实现（`worktree.py:126-132`）仅依赖 git 自清理（branch 冲突场景 grill 实测成立），回滚 `git worktree remove` 的返回值也未检查（`worktree.py:137`）。磁盘满、git 被杀、超时等非 branch-conflict 失败可残留 `.git/worktrees/<name>` 注册，后续同名调用报"已存在"且无清理入口。偏离已确认设计，建议按 D2 补 verify（list 中有残留时尝试 remove/prune）。

- **[低] name 未在目录副作用前校验**：`worktree.py:122-125` 先 `mkdir(parents=True)` 再交给 git 校验 refname。含 `..` 的 name（如 `../../../../tmp/x/y`）git 因无效 refname 拒绝，但 mkdir 副作用已发生（可越过仓库边界在 /tmp 等可写路径创建目录）。分支名合法性由 git check-ref-format 兜底（注入安全，arg list 调用无 shell 注入），但建议 add 前先 `git check-ref-format --branch <name>` 校验，消除目录副作用窗口。

- **[低] `_run_git` 10s 硬超时 + 非结构化错误路径**：`git worktree add` 是完整 checkout，大仓库可超 10s。TimeoutExpired（`subprocess.TimeoutExpired` 非 `TimeoutError`，`agent/observability.py:93-97` 映射为 None）不落入 5 个新错误码（D6"所有错误路径返回结构化 ToolResult"字面违背），且消息含 "timed out" 命中 RetryHook 重试模式（`agent/hooks/builtin/retry.py`），4 次尝试 + 退避约 40s；被杀的 git 可能留下半注册状态。mkdir OSError 同理走通用 `[Error: ...]`（error_type=None）。建议：超时/OSError 捕获并映射 `worktree_create_failed`，超时后执行 prune 清理。

- **[低] 测试缺口**：(1) ExitWorktree 部分成功路径（切回后 remove 失败，`worktree.py:203-212`）无测试，可 monkeypatch `_run_git` 覆盖；(2) `get_all_schemas()` 暴露（task 3.4 验收）无测试；(3) read_only/plan 模式 DENY（registry 层）无测试；(4) 特殊字符/路径穿越 name（`..`、空格、`/`）无测试；(5) detached HEAD 默认 base 无测试。

- **[低] CommandGuard workspace 快照过期（已知限制，但"实现时确认"未回写）**：`agent/tools/builtin/bash.py:52` 构造时 `CommandGuard(workspace=policy.workspace_root)`，重绑定后 `command_guard.py:228` 绝对路径判定基于旧 root，worktree 内绝对路径命令会被误拒（guardrail 非边界，已文档化于 design.md D4）。但 design.md Risks 节仍写"实现时确认 `_check_argv` 相对路径分支"——实现后未回写确认结论，收尾时应更新。

## Test Results

```
$ python3 -m pytest tests/agent/tools/test_worktree_tools.py -q
17 passed in 1.44s
$ python3 -m pytest tests/agent/tools/test_factory.py tests/agent/tools/test_registry.py tests/agent/tools/test_write_tool_policy.py -q
26 passed in 0.92s
```

（提交信息写"16 测试全绿"，实际 17 个；MCP 相关测试因环境缺 uv 未跑，已知 baseline。）

## 结论

实现质量总体良好：政策根重绑定语义正确且被 loop（`agent/loop.py:1302` BuildContext 动态读取）与文件工具（Read/Grep 调用时读 policy）真实跟随；deny pattern `.asterwynd/worktrees/**` 经 `is_denied` 实现验证确实拦截主模式文件工具（`workspace_policy.py:232-241`，fnmatch `**` 匹配 rel 全路径）；dirty 预检（`status --porcelain` 覆盖 tracked+untracked）与状态不变语义实现一致并有测试；失败回滚（add 后 rebind 抛异常 → remove）正确；权限元数据与用户确认一致（base.py 默认即 dangerous=False + WORKSPACE_WRITE/MEDIUM）；5 个错误码风格一致；`.asterwynd/` 已在 .gitignore（无 git status 污染）。

阻止合入的两项：1) ExitWorktree 在编排层/benchmark worktree 内可执行并重绑定/删除编排层 worktree，与 D7 声明矛盾，需决策或修复；2) 任务 2.5 无证据勾选。另有三项建议修复（D2 verify 未实现、name 预校验、10s 超时结构化错误）。修复并补对应回归测试后，change 可进入 spec 同步与收尾（1.7/3.7/4.x/5.x 仍待完成）。
