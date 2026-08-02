# Proposal: 流程精简 — 保留 subagent 审阅闭环，停用 workflow 状态机仪式

## Change Type

primary: process
secondary:
  - change-documentation

## 需求

1. 停用 PR #67 引入的 workflow 四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止），开发流程精简为「OpenSpec 主干 + 强制独立 subagent 审阅闭环」。
2. 新增 `/review-loop` 命令封装审阅闭环：spawn 独立零记忆 subagent 审阅 → 判 verdict → CHANGES_REQUESTED 则修复+回归测试 → 再审直到 PASS 或 3 轮封顶 → 生成 review manifest。
3. `check_openspec_artifacts.py` 对「非 docs + 有 spec delta + tasks 全勾选」的 change 强制 building-review.md + manifest 存在且 PASS——缺审阅直接报错（PR 前机械门禁）。
4. 审阅证据存放于 `openspec/changes/<id>/reviews/`，随 change 进 PR，CI 可机械校验。
5. `workflow_guard.py` 停用 phase gate check（active change/worktree/required files），保留受保护文件始终拦截。

## 背景

#77/#76/#78 三个 change 开发复盘发现：OpenSpec 流程（proposal → batch-grill-me → worktree → TDD → spec sync → PR）推进很顺，够用。唯一实质缺口是实现完成后没有独立 subagent 审阅（reviewing_impl 没触发，代码只经过自测）。PR #67 引入的状态机仪式过重：phase/sub_state 推进、handoff.json、gate 停止——价值不大且 agent 容易漏走。但状态机里「独立 subagent 审阅 + 机械检查」是有价值的。

结论：精简 PR #67——保留「subagent 审阅闭环」，停用「状态机仪式」。开发流程 = OpenSpec 主干 + 强制 subagent 审阅。

## 变更范围

- `AGENTS.md`：重写「工作流自动推进与 Gate 机制」→「开发流程：OpenSpec 主干 + 强制审阅闭环」。
- `.claude/commands/review-loop.md`：新增审阅闭环命令（本地，不入库）。
- `scripts/check_openspec_artifacts.py`：`_check_review_manifests` 加强制门禁。
- `scripts/workflow_guard.py`：停用 phase gate check，保留受保护文件保护，清理死代码。
- `scripts/workflow_hook.example.json`：移除 session start discover hook。
- `agent/workflow/review_manifest.py`：审阅证据路径迁移到 `openspec/changes/<id>/reviews/`。
- `scripts/check_phase_done.py`：`_check_review_report` 同步新路径。

## 验收标准

1. 开发流程 = OpenSpec 主干 + 强制 subagent 审阅闭环（审到通过或 3 轮）。
2. `check_openspec_artifacts.py` 能机械检查 `reviews/building-review.md` + manifest，缺审阅直接报错。
3. 审阅证据随 change 进 PR（`openspec/changes/<id>/reviews/`），CI 可校验。
4. `AGENTS.md` 反映新流程（无状态机仪式，有审阅闭环）。
5. 全量 pytest + openspec validate + artifact checker 通过。

## Impact Analysis

- `AGENTS.md`：流程文档重写。
- `scripts/check_openspec_artifacts.py`：强制门禁逻辑。
- `scripts/workflow_guard.py`：写操作门禁行为变化（受保护文件仍拦截，phase gate 停用）。
- `scripts/check_phase_done.py`：review report 路径。
- `agent/workflow/review_manifest.py`：审阅证据路径。
- 测试：`test_openspec_artifact_checker.py`、`test_workflow_guard.py`、`test_check_phase_done.py`、`test_workflow_state_cli.py`、`test_review_manifest.py`。

## Reference Implementation Research

- status: disabled
- reason: 本 change 是流程/工具链精简，不涉及 coding-agent 能力实现对比；审阅闭环的设计基于 #77/#76/#78 开发复盘（本仓库自己的经验），无需外部参考。
