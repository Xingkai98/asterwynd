# Tasks: 设计追问工具从 grill-with-docs 切换为 batch-grill-me

## 1. 文档同步

- [x] 1.1 `AGENTS.md`：设计追问规则、自然语言路由表、worktree 阶段方法表
- [x] 1.2 `docs/requirements-process.md`、`docs/agents/domain.md`、`openspec/project.md`、`openspec/templates/tasks.md`
- [x] 1.3 6 个 wayfinder change（tool-governance-deepening 等）的 design.md / tasks.md 引用
- [x] 1.4 3 个流程规格：`openspec/specs/change-documentation/spec.md`、`dev-workflow-state-machine/spec.md`、`subagents/spec.md`

## 2. 机械检查同步

- [x] 2.1 `scripts/check_openspec_artifacts.py`：`_has_design_review_task` 接受 `batch-grill` 子串 + 错误文案
- [x] 2.2 `scripts/workflow_methods.json`：planning exploring 方法映射为 `/batch-grill-me`
- [x] 2.3 测试断言文案同步（`test_openspec_artifact_checker.py`）

## 3. 验证

- [x] 3.1 `test_openspec_artifact_checker.py` + `test_check_phase_done.py` 通过（60 passed）
- [x] 3.2 `openspec validate --all --strict` 通过
- [ ] 3.3 artifact checker 通过（需本 change 的 workflow-events.jsonl 解释受保护 spec 修改）

## 4. 收尾

- [ ] 4.1 当前规格同步：把 spec delta 合并到 `openspec/specs/change-documentation/spec.md`
- [ ] 4.2 全量 pytest 无新增失败（9 个既有环境失败已挂 issue #82）
- [ ] 4.3 提交本次变更
