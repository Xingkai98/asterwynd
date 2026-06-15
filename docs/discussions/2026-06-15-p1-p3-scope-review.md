# P1 开发方案讨论纪要

**日期**: 2026-06-15
**参与**: 用户、Claude
**背景**: 基于 coding-agent-roadmap.md 和 benchmark-plan.md，逐项审查 P1-P3 交付物可行性，最终合并为单一 P1

---

## 决策总表

| # | 决策项 | 原方案 | 最终决定 | 依据 |
|---|--------|--------|---------|------|
| 1 | 开发阶段 | P1/P2/P3 三阶段 | **合并为单一 P1**，砍掉 RunTestsTool/PatchTool 后体量不大 | — |
| 2 | RunTestsTool | 新建专用测试工具 | **砍掉**，增强 BashTool 输出结构化 JSON | 7 个参照仓库均无专用测试工具 |
| 3 | PatchTool | 新建差异补丁工具 | **砍掉**，只保留 Edit 精确替换 | Claude Code/nanobot/pi-mono 只用 Edit；LLM 生成 patch 错误率高 |
| 4 | ListFilesTool + FindTool | P2 交付物 | **保留**，两个独立工具 | 4/7 仓库有文件列表工具 |
| 5 | Glob 命名 | 叫 GlobTool | **改为 FindTool** | 更直观，跟 Unix find 一致 |
| 6 | ListFiles/Find 忽略规则 | 复用 WorkspacePolicy denied | **独立定义**，默认忽略 `.git`/`node_modules` 等，`.env` 可追加 `MYAGENT_IGNORE_PATTERNS` | denied 是安全边界，ignore 是降噪 |
| 7 | BashTool 结构化输出 | 改 Tool 接口 | **不改接口**，execute() 返回 JSON 字符串 | 零破坏性，参照 hermes-agent |
| 8 | Trace 截断 | 默认截断 500 字符，--full-trace 全量 | **不截断**，全量保留，去掉 --full-trace flag | 开销可忽略，排查价值高 |
| 9 | 编码 prompt | 通用系统提示 | benchmark prompt 加"完成前跑验证命令" | — |
| 10 | 模式架构 | CLI coding mode 单独子命令 | `myagent main` + `myagent web` + `myagent benchmark` 三个入口 | 默认即编码代理 |
| 11 | 打包发布 | pyproject.toml 无 entry point | 加 `[project.scripts]`，`uv tool install` 全局安装 | — |
| 12 | 审批模式 | P3 交付物 | **先不做** | — |
| 13 | Bash 黑白名单 | 仅硬编码黑名单 | 对标 hermes/nanobot，正则黑名单 + 白名单，`.env` 可追加 | 安全底线不依赖配置 |
| 14 | 基准任务 | 合成任务 | 从历史 commit 选取，详细设计待实现时做 | 更真实 |

## 参照仓库结论

审查了 `/home/shared/agent-study/repos/` 下全部 7 个仓库：

| 仓库 | Shell | RunTests | Patch | FileList | 命令过滤 |
|------|------|----------|-------|----------|---------|
| claude-code | BashTool | 无 | 无（仅 Edit） | GlobTool | 黑白名单（最强） |
| codex | shell_command | 无 | apply_patch | FsReadDirectory | OS 级沙箱 |
| hermes-agent | terminal_tool | 无 | V4A parser | api.listFiles | 48 条正则黑名单 |
| nanobot | exec | 无 | ApplyPatchTool（JSON） | ListDir + FindFiles | 正则黑白名单 |
| openclaw | exec/bash | 无 | apply-patch | 无 | 无 |
| opencode | BashTool | 无 | apply_patch | 无 | 无 |
| pi-mono | bash | 无 | 无（仅 Edit） | ls + find | 无 |

**统一结论**: 没有仓库建 RunTestsTool，全用 Bash/Shell 跑测试。

## P1 交付物（8 项）

1. **BashTool 结构化输出** — execute() 返回 JSON 字符串 `{"exit_code": int, "stdout": str, "stderr": str, "duration_ms": float, "timed_out": bool}`（对标 codex），不改 Tool 接口
2. **BashTool 黑白名单** — 正则黑名单 + 白名单，`MYAGENT_COMMAND_ALLOWLIST` / `MYAGENT_COMMAND_DENYLIST` 环境变量追加
3. **编码 prompt** — `benchmarks/prompt.py` 加"完成前跑验证命令"
4. **ListFilesTool** — 列出目录，独立忽略规则，`MYAGENT_IGNORE_PATTERNS` 可追加
5. **FindTool** — 按 glob 模式递归搜索文件
6. **打包发布** — `pyproject.toml` 加 `[project.scripts]`，`uv tool install` 全局安装
7. **Trace 全量** — 去掉截断和 --full-trace flag
8. **回归测试** — 跟进上述所有变更

## 变更文件

- `docs/coding-agent-roadmap.md`
- `docs/benchmark-plan.md`
- `docs/discussions/2026-06-15-p1-p3-scope-review.md`（本文件）
