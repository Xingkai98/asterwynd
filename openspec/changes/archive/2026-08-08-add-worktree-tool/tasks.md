# Tasks: add-worktree-tool

## 1. 规格

- [x] 1.1 更新受影响 capability 的 spec delta（tool-system）。
- [x] 1.2 明确本 change 的范围、非目标和验收标准。
- [x] 1.3 开发前使用 `batch-grill-me` 或等价设计追问审视 `design.md`，逐项确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案；不得把 agent 自己的推荐答案当作用户确认。重点收敛：会话 cwd 切换承载点、WorkspacePolicy 重绑定 API、worktree 目录约定、权限元数据、失败回滚边界、错误码枚举。
- [x] 1.4 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [x] 1.5 维护 `## Reference Implementation Research`；记录最终调研状态、发现和设计影响。
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。
- [ ] 1.7 当前规格同步：把 tool-system spec delta 合并到 `openspec/specs/tool-system/spec.md`，确认未实现能力没有被写成已实现，并配 workflow-events.jsonl 解释事件。

## 2. 测试

- [x] 2.1 按 TDD 先新增 `EnterWorktree` / `ExitWorktree` 单元测试（参数校验、错误路径、keep 语义、分支名派生）。
- [x] 2.2 集成测试：`tmp_path` 真实 git 仓库全流程（创建→进入→文件工具路径边界重绑定→退出→删除）。
- [x] 2.3 负向路径：非 git 仓库、嵌套 worktree、删除含未提交改动的 worktree 被拒、失败回滚（cwd 与 policy root 不变）。
- [x] 2.4 AgentLoop 层测试：工具调用后会话 cwd 与 policy root 状态正确。
- [x] 2.5 涉及工具协议与 workspace safety 核心路径，跑通至少一个 benchmark smoke（沉淀 benchmark task `asterwynd-008-worktree-tools`，test.patch 纳入主套件实际运行通过；与 master baseline 一致无回归）。

## 3. 实现

- [x] 3.1 实现最小可验证路径：EnterWorktree 创建 + 切换。
- [x] 3.2 实现 ExitWorktree（keep / remove）。
- [x] 3.3 接入 WorkspacePolicy root 重绑定与权限元数据（dangerous=False + MEDIUM；DEFAULT_DENIED_PATTERNS 增加 `.asterwynd/worktrees/**`）。
- [x] 3.4 注册进 ToolRegistry，schema 可从 `get_all_schemas()` 获取。
- [x] 3.5 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现。
- [x] 3.6 如果实现中发现参考实现调研结论需要修正，先回写 Reference Implementation Research 和本任务清单。
- [x] 3.7 更新必要文档（架构说明、工具文档、面试讲稿如有新能力线）。

## 审阅修复记录（review-loop R1）

- **R1-1 [中] ExitWorktree 越权边界**：编排层/benchmark 任务 worktree 内前置校验满足，可切回主工作区甚至删除任务 worktree。修复：`_is_tool_created_worktree` 限制 ExitWorktree 仅对工具自建 worktree（`.asterwynd/worktrees/` 下）生效，否则返回 `not_in_worktree`（用户确认）。测试：`test_exit_worktree_rejects_non_tool_created`。
- **R1-2 [中] 任务 2.5 勾选无证据**：验证脚本未持久化、smoke 未跑。修复：沉淀 benchmark task `benchmarks/tasks/asterwynd-008-worktree-tools/`（注册+schema+被拒路径，test.patch 纳入主套件 `tests/agent/tools/test_worktree_benchmark_smoke.py` 实际运行通过）。
- **R1-3 [低-中] D2 显式 verify 未实现**：add 失败仅依赖 git 自清理、回滚 remove 返回值未检查。修复：add 失败后显式 `worktree remove` 兜底；回滚失败返回部分成功 text。
- **R1-4 [低] name 校验晚于 mkdir**：修复：`_is_valid_worktree_name` 前置 `git check-ref-format`（禁止 `..`/空格/`/`/`-` 开头），防路径穿越。测试：`test_enter_worktree_invalid_name_rejected`。
- **R1-5 [低] git 超时未落错误码**：修复：`_run_git` 捕获 TimeoutExpired 映射 returncode 124（text 带超时说明），落入 `worktree_create_failed`。
- **R1-6 [低] 测试缺口**：修复：补 detached HEAD、非法 name、非工具自建 worktree 拒绝测试。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试。
- [x] 4.2 运行全量测试（1823 通过，5 个 MCP baseline 失败）。
- [x] 4.3 运行 OpenSpec strict validate。
- [x] 4.4 运行项目 OpenSpec artifact checker。
- [x] 4.5 确认 baseline CI 命令可本地通过：`uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.6 至少一个 benchmark smoke 通过（`asterwynd-008-worktree-tools` 纳入主套件实际运行）。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [ ] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 5.6 PR 合入时，给关联 GitHub issue（标题【feature】）添加完成说明 comment 并关闭。
