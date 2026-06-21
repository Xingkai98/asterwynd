# OpenSpec 收窄点实现排查

## 背景

在为当前代码建立 OpenSpec 初版规格时，有几处规格被收窄为“当前实现如此”。本排查用于判断这些收窄点是合理限制、设计债务还是应修复的 bug。

本文只记录排查结论和建议，不修改实现。

## 结论摘要

| 项 | 判断 | 优先级 | 建议 |
| --- | --- | --- | --- |
| ReadTool 不受 WorkspacePolicy 约束 | bug / 安全缺陷 | P0 | 建 change 修复 |
| GrepTool 不受 WorkspacePolicy 约束 | bug / 安全缺陷 | P0 | 建 change 修复 |
| `assert_read_allowed` 不拦 denied patterns | 设计缺陷 | P0 | 和 Read/Grep 一起修 |
| Bash allowlist 先于 denylist 导致宽泛命令放行 | 设计缺陷 | P1 | 单独建 change 收紧 |
| MemoryManager compact 不生成摘要 | 设计债务 | P1 | 建 change 明确 AutoCompact 语义 |
| DebugHook 不捕获 memory compact 事件 | 文档/实现不一致 | P2 | 先修文档，是否扩展事件另议 |
| InspectGitDiff 未复用 `snapshot_git_diff` | 轻微设计债务 | P3 | 后续重构时处理 |
| Benchmark 失败路径 artifact 不完整 | 合理限制 + 旧文档债务 | P2 | 统一旧文档口径 |

## 详细排查

### 1. ReadTool 不受 WorkspacePolicy 约束

**当前实现**

- `agent/tools/builtin/read.py` 直接使用 `Path(path)`。
- `get_default_tools()` 和 `get_coding_tools()` 都以 `ReadTool()` 形式注册，没有注入 policy。
- 当前测试只覆盖读取普通文件、文件不存在和目录错误。

**可复现现象**

临时探针确认：

```text
read_env: TOKEN=secret
read_outside: outside-secret
```

这意味着 agent 可以通过绝对路径读取 workspace 外文件，也可以读取 `.env`。

**判断**

这是 bug / 安全缺陷。项目已有 WorkspacePolicy 和 workspace safety 能力域，Read 是 coding agent 的核心工具，不应绕过工作区边界。

**建议修复**

- 为 ReadTool 增加可注入 `WorkspacePolicy`。
- 在 `get_default_tools()` / `get_coding_tools()` 中注入同一个 policy。
- `ReadTool.execute()` 先调用 `policy.assert_read_allowed(path)`。
- 是否拒绝 `.env` 等 denied patterns，需要和 `assert_read_allowed` 的语义一起确定。
- 新增回归测试：workspace 外路径被拒绝、`.env` 读取被拒绝或按确认后的策略处理。

### 2. GrepTool 不受 WorkspacePolicy 约束

**当前实现**

- `agent/tools/builtin/grep.py` 直接使用 `Path(path)`。
- `get_default_tools()` 和 `get_coding_tools()` 都以 `GrepTool()` 形式注册，没有注入 policy。

**可复现现象**

临时探针确认：

```text
grep_env: /tmp/.../.env:1: TOKEN=secret
```

**判断**

这是 bug / 安全缺陷。Grep 是批量读取工具，风险不低于 Read。

**建议修复**

- 为 GrepTool 增加可注入 `WorkspacePolicy`。
- 搜索起点必须通过 `policy.assert_read_allowed(path)`。
- 递归搜索时应跳过 denied directories / patterns，避免扫 `.env`、`.git`、`.venv`、`node_modules` 等。
- 新增回归测试：workspace 外目录拒绝、递归搜索不泄露 denied pattern 文件。

### 3. `assert_read_allowed` 不拦 denied patterns

**当前实现**

- `WorkspacePolicy.assert_read_allowed()` 只调用 `assert_within_workspace()`。
- `assert_write_allowed()` 才调用 `is_denied()`。
- 测试 `test_workspace_policy_allows_reads_inside_root_even_for_task_files` 固化了当前读允许策略。

**判断**

这是设计缺陷。读路径和写路径的安全语义不一致，导致 `.env` 等敏感文件不能通过统一 policy 防护。

需要注意，benchmark 曾需要读取 `benchmarks/tasks` 这类任务文件；不能简单把所有 denied patterns 都套到读路径，否则可能破坏现有流程。

**建议修复**

- 拆分 policy 语义：
  - `assert_read_allowed`: workspace 内 + 默认敏感文件拒绝。
  - `assert_internal_read_allowed` 或显式参数：供 benchmark/内部流程读取任务文件。
- denied patterns 可以区分 read denied 和 write denied。
- 先写 OpenSpec change 明确读安全边界，再改测试。

### 4. Bash allowlist 先于 denylist

**当前实现**

- `assert_command_allowed()` 先执行 `_match_allowlist()`，命中后直接 return。
- 因为 allowlist 包含宽泛前缀，以下命令当前会放行：

```text
python -c "import os; os.remove('x')"
cp /etc/passwd ./passwd.copy
mv .env backup.env
```

危险 git 命令当前会被拒绝，是因为 allowlist 不包含 `git reset` / `git push` 前缀。

**判断**

这是设计缺陷。当前策略并不是“denylist 覆盖 allowlist”，而是“allowlist 优先短路”。宽泛命令前缀会绕过 denylist。

**建议修复**

- 改为先检查 denylist，再检查 allowlist。
- 收窄 `python`、`cp`、`mv` 等高风险前缀，或引入命令解析而不是纯前缀匹配。
- 新增回归测试覆盖 `python -c`、`cp /etc/passwd`、`mv .env` 等边界。

### 5. MemoryManager compact 不生成摘要

**当前实现**

- `MemoryManager.compact()` 只保留 system + recent messages。
- 即使构造时传入 `llm`，也不会调用 LLM 生成摘要。
- 临时探针确认 compact 后只剩 system 和 recent messages。

**判断**

这是设计债务。当前行为和“AutoCompact / 上下文压缩”的命名不完全匹配，会丢失中间上下文。它不一定是立即 bug，但会影响长任务质量。

**建议修复**

- 建 OpenSpec change 明确 compact 行为：
  - 无 LLM 时是否只裁剪。
  - 有 LLM 时是否生成摘要。
  - 摘要消息的 role、位置和内容格式。
  - tool-call 链如何保持合法。
- 先补回归测试：有 LLM 时应生成 summary；tool-call 链仍合法。

### 6. DebugHook 不捕获 memory compact 事件

**当前实现**

- `AgentLoop` 通过 `on_event("memory_compaction", ...)` 向 Web session 事件队列发送压缩事件。
- `DebugHook` 本身没有 memory compact hook 方法。
- `web/static/debug.js` 有 `memory_compaction` 渲染分支。
- `docs/architecture.md` 仍写“DebugHook 捕获压缩事件”，这是旧口径。

**判断**

这是文档/实现不一致，不一定是代码 bug。当前 Web 事件流可以看到 memory_compaction，但 DebugHook 不是捕获来源。

**建议修复**

- 先修 `docs/architecture.md` 表述。
- 如果需要统一 debug 事件来源，再建 change 扩展 Hook protocol。

### 7. InspectGitDiff 与 WorkspacePolicy.snapshot_git_diff 重复

**当前实现**

- `WorkspacePolicy.snapshot_git_diff()` 存在，但当前主要调用点不使用它。
- `InspectGitDiffTool` 自己运行 `git diff --stat`、按 path 运行 `git diff -- <path>`，并可列 untracked files。

**判断**

这是轻微设计债务，不是明显 bug。InspectGitDiff 需要更多展示能力，未复用 helper 可以接受。

**建议修复**

- 暂不优先处理。
- 后续如重构 workspace safety，可把 diff stat/path/untracked 统一收敛到 policy 或单独 GitDiff service。

### 8. Benchmark 失败路径 artifact 不完整

**当前实现**

- `result.json`、`trace.json`、`runner.log` 在 finally 写入。
- `final.diff` 只有 agent 运行并完成 diff capture 后才写入。
- `test_output.txt` 只有验证命令实际运行后才写入。
- 新 OpenSpec 已按当前实现收窄。
- `docs/benchmark-plan.md` 等旧文档仍有“每个任务都保存 final.diff/test_output.txt”的绝对表述。

**判断**

这是合理限制 + 文档债务。setup 阶段失败时没有 diff/test output 是合理的。

**建议修复**

- 统一旧文档口径，说明 artifact 按阶段生成。
- 是否创建空占位文件可以另议，但不是当前优先 bug。

## 建议拆分的后续 changes

### P0: `harden-read-grep-workspace-policy`

范围：

- ReadTool 注入并执行 WorkspacePolicy。
- GrepTool 注入并执行 WorkspacePolicy。
- 明确 read denied patterns。
- 保留内部 benchmark 读取任务文件的合法路径。

测试：

- Read 拒绝 workspace 外路径。
- Read 拒绝 `.env` 或按新策略处理敏感文件。
- Grep 拒绝 workspace 外路径。
- Grep 递归搜索不泄露 denied pattern 文件。
- MyAgentRunner 使用 coding tools 时共享同一个 workspace policy。

### P1: `tighten-bash-command-policy`

范围：

- denylist 优先于 allowlist。
- 收窄宽泛命令前缀。
- 明确允许测试命令和普通开发命令的边界。

测试：

- `git reset --hard`、`python -c destructive`、`cp /etc/passwd`、`mv .env` 被拒绝。
- `pytest`、`uv run pytest`、`git diff` 等仍允许。

### P1: `implement-memory-summary-compact`

范围：

- 明确有 LLM / 无 LLM 的 compact 行为。
- 生成 summary message。
- 保持 tool-call 链合法。

测试：

- 超预算时生成 summary。
- 无 LLM 时执行降级裁剪。
- 包含 tool result 的 recent window 不破坏 provider 消息链。

### P2: `align-observability-and-benchmark-docs`

范围：

- 修正旧文档中 DebugHook、benchmark artifact 的过时表述。
- 不改业务实现。

验证：

- OpenSpec strict validate。
- 文档链接和口径检查。

