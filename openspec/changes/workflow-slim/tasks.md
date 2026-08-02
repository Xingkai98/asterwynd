# Tasks: 流程精简 — 保留 subagent 审阅闭环，停用 workflow 状态机仪式

## 1. 审阅闭环命令

- [x] 1.1 `.claude/commands/review-loop.md`：spawn 零记忆 subagent 审阅 → 判 verdict → CHANGES_REQUESTED 修复 → 再审直到 PASS 或 3 轮 → 生成 manifest
- [x] 1.2 审阅维度沿用 workflow_methods.json `building.reviewing_impl`（任务逐项/正确性/Spec 对齐/冗余度/测试/安全/可维护/CI）

## 2. 机械强制门禁

- [x] 2.1 `check_openspec_artifacts.py`：`_check_review_manifests` 对非 docs + spec delta + tasks 全勾选的 change 强制 building-review.md + manifest 存在且 PASS
- [x] 2.2 `_tasks_all_complete` helper：tasks.md 全部 `[x]` 才算实现完成（部分实现不触发）
- [x] 2.3 回归测试：feature 全勾选强制 / 部分实现不强制 / 缺 manifest 报错 / docs 不强制

## 3. 停用状态机仪式

- [x] 3.1 `workflow_guard.py`：移除 phase gate check，普通写放行，受保护文件始终拦截
- [x] 3.2 `workflow_guard.py`：清理死代码（_discover_active_change/_check_gate/_track_agent_call 等），修复 sys.path
- [x] 3.3 `workflow_hook.example.json` / settings.json：移除 session start discover hook
- [x] 3.4 测试更新：guard 测试反映新行为（受保护拦截 / 普通写放行 / 无 _agent-calls 跟踪）

## 4. 审阅证据路径迁移（方案 A）

- [x] 4.1 `review_manifest.py`：`review_report_path`/`review_manifest_path` 迁移到 `openspec/changes/<id>/reviews/`
- [x] 4.2 `check_openspec_artifacts.py`：`_check_review_manifests` 读 change 目录 reviews/
- [x] 4.3 `check_phase_done.py`：`_check_review_report` 同步新路径
- [x] 4.4 测试同步：5 个测试文件路径更新
- [x] 4.5 端到端验证：证据随 change 进 PR → CI 通过；证据只在 `.handoff` → 报缺审阅

## 5. 文档

- [x] 5.1 `AGENTS.md`：重写「工作流自动推进与 Gate 机制」→「开发流程：OpenSpec 主干 + 强制审阅闭环」
- [x] 5.2 `AGENTS.md`：机械门禁描述补 tasks 全勾选条件

## 6. 收尾

- [x] 6.1 本 change 自身走审阅闭环（`/review-loop` 验证流程自身），3 轮通过
- [x] 6.2 全量 pytest（1204 passed，6 个 issue #82 环境问题）+ openspec validate + artifact checker
- [x] 6.3 spec delta 同步 + 归档
- [x] 6.4 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）— issue #90 讨论即设计追问，决策见 design.md Pre-Implementation Review
- [x] 6.5 当前规格同步：把 spec delta 合并到 `openspec/specs/dev-workflow-state-machine/spec.md`
