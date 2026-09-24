# Tasks: add-worktree-tool

## 1. 规格

- [x] 1.1 更新受影响 capability 的 spec delta（tool-system）。
- [x] 1.2 明确本 change 的范围、非目标和验收标准。
- [x] 1.3 开发前使用 `batch-grill-me` 或等价设计追问审视 `design.md`，逐项确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案；不得把 agent 自己的推荐答案当作用户确认。重点收敛：会话 cwd 切换承载点、WorkspacePolicy 重绑定 API、worktree 目录约定、权限元数据、失败回滚边界、错误码枚举。
- [x] 1.4 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [x] 1.5 维护 `## Reference Implementation Research`；记录最终调研状态、发现和设计影响。
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。
- [x] 1.7 当前规格同步：把 tool-system spec delta 合并到 `openspec/specs/tool-system/spec.md`，确认未实现能力没有被写成已实现，并配 workflow-events.jsonl 解释事件。**（PR #113 复验补做）** 原归档收尾提交 `be1828c` 声称已合并 delta 并删除 delta 文件，但主规格实际未写入、事件日志缺 `seq 2`（`backlog_updated` → `change_archived` 跳号）、归档目录缺 `specs/`——三者是同一次遗漏的三个症状。本次补齐：`openspec/specs/tool-system/spec.md` 新增 Requirement「Worktree 隔离工具」+ 7 个 Scenario（与归档 delta 逐条一致），delta 文件回填归档目录，事件日志补 `current_spec_synced`。

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

## 审阅修复记录（review-loop R5，基线复验轮）

PR #113 合并 master 后在今天基线上重新审阅，发现 R1/R3 修复自身引入的缺陷：

- **R5-1 [高] EnterWorktree 失败兜底会删除已存在的 worktree（数据丢失）**：`worktree add` 失败后无条件 `worktree remove`，而同名分支已存在（最常见路径：`keep=true` 保留后重入）时该路径上本就有用户的合法 worktree，`remove` 返回 0 → 已有 worktree 连同内容被静默删除。修复：引入 `_registered_worktree_paths`，失败后只清「本次 add 新增的注册」（`after - before`）；路径被占用时改为返回「已被占用、未改动它」的准确文案。测试：`test_enter_worktree_existing_worktree_not_deleted`、`test_enter_worktree_dirty_existing_worktree_not_deleted`（变异验证：还原破坏性 remove → 两条立即变红）。
- **R5-2 [中] 失败文案与事实相反**：dirty 同名 worktree 实际完好保留，文案却说「清理未完成、worktree 可能残留」，误导 agent 做补救动作。修复：区分「被占用（未改动）」与「真残留（已清理/清理失败）」三类文案。
- **R5-3 [低] `base_branch` 未校验（参数注入）**：`base_branch="--force"` 会被 git 当选项吞掉，base 静默失效按 HEAD 创建。修复：`git worktree add ... -- <path> <base>` 加 `--` 隔离位置参数；测试 `test_enter_worktree_base_branch_option_injection_rejected`。
- **R5-4 [低] 测试缺口**：原 `test_enter_worktree_branch_conflict` 只造「分支存在但无对应 worktree」，恰好绕开 R5-1 路径。已按 R5-1 补两条回归。
- **R5-5 [低] spec 滞后于实现**：R1 追加的「ExitWorktree 仅对工具自建 worktree 生效」边界有实现（`_is_tool_created_worktree`）和测试，但 7 个 Scenario 未覆盖。修复：delta 与主规格同步补 `#### Scenario: 拒绝退出非本工具创建的 worktree`（现 8 个 Scenario，两侧 `diff` IDENTICAL）。
- **R5-6 [低] benchmark 交付物固化缺陷**：`gold.patch` 是 R1 diff，含同一条破坏性 remove。修复：随实现重新生成 `gold.patch`（= base→当前实现），并实测复现 base 红 → gold 绿闭环。

## 审阅修复记录（review-loop R6–R9，收尾轮）

- **R6 [低] 残留判定 fail-open**：`_registered_worktree_paths` 枚举失败返回空集，差集会把「此前无 worktree」读成现实，`worktree list` 自身失败时会误删别人的 worktree。修复：返回 `None`（未知），调用侧任一为空即不清理（fail-closed）+ 对应文案。
- **R7 [低] fail-closed 回归测试保护强度不足**：测试把被测 helper 也 monkeypatch 掉，绕过其返回契约——只改 helper 的 `return None` → `return set()` 时全绿（变异存活），而该变异正是数据丢失路径。修复：新增 `test_registered_worktree_paths_none_when_list_fails` 直接锁 helper 契约。
- **R8 [低] R7 的修法丢了调用侧覆盖**：重写后的用例让每次 `worktree list` 都失败（对称失败），恰好落在畸形实现仍安全的情形；实测「只让 before 快照失败」（非对称）会执行 remove。修复：新增 `test_enter_worktree_cleanup_fail_closed_on_asymmetric_list_failure`；相关用例现场改用**已提交**内容，避免未跟踪文件被 git 拒删而削弱判别力。
- **R9（最终确认）PASS**：变异 B/C/D 均被测试抓住（分别为 `2 failed` / `1 failed` / `4 failed`）；独立复现同一数据丢失场景在 HEAD 下 `SAFE`、在变异 B/C 下 `UNSAFE`；生产代码未改动，R9 报告无剩余 Open Questions。
- **收敛说明（用户指令）**：审阅目的为验证而非无限加固。R8 报告已明确「`head` 的生产代码本身在所有可构造路径上都是安全的」「安全性等价，属可选打磨，不阻塞」；本 PR 已从 R5 修到 R9、超出「3 轮封顶」约定，按指令以 R9 PASS 收敛，不再开新一轮审阅。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试。
- [x] 4.2 运行全量测试（1823 通过，5 个 MCP baseline 失败）。
- [x] 4.3 运行 OpenSpec strict validate。
- [x] 4.4 运行项目 OpenSpec artifact checker。
- [x] 4.5 确认 baseline CI 命令可本地通过：`uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.6 至少一个 benchmark smoke 通过（`asterwynd-008-worktree-tools` 纳入主套件实际运行）。

## 5. PR 收尾

- [x] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。（已于 `be1828c` 完成：归档到 `openspec/changes/archive/2026-08-08-add-worktree-tool/`；PR #113 复验补回了本次遗漏的 `specs/` 子目录。）
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。（已于 `be1828c` 完成：未实现队列 5 号条目移除，第十批标记已归档。PR #113 合并 master 时该清理被保留。）
- [x] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。（复验确认：proposal.md / design.md 零命中。）
- [x] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。（复验确认：`research_tier: full` / `status: enabled`，reason/findings/design impact 齐全；`.dev/reference-repos.txt` 仅作为「不可用」事实记录，未写成项目依赖。）
- [x] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。（PR #113 复验实跑通过，结果记录在 `reviews/building-review.md`。）
- [ ] 5.6 (post-merge) PR 合入时，给关联 GitHub issue（标题【feature】）添加完成说明 comment 并关闭。
