# Tasks: 开发流程自动化

## 1. 规格

- [x] 开发前使用 `grill-with-docs` 对 design.md 做设计追问（本次通过 Codex CLI 审阅等价完成）
- [x] 同步对应 current spec 到 `openspec/specs/dev-workflow-state-machine/spec.md`（本次通过 spec delta 记录新增需求）

## 2. 基础设施

- [x] 创建 `docs/adr/_TEMPLATE.md`（ADR 标准模板）
- [x] 创建 `scripts/workflow_state.py`（状态管理 CLI：discover/current/advance/approve/validate）
- [x] 创建 `scripts/check_phase_done.py`（只读相位验证：planning/building/code-review/closing）

## 2. 核心逻辑

- [x] `workflow_state.py` discover 命令：扫描 `openspec/changes/*/handoff.json`，列表展示
- [x] `workflow_state.py` advance 命令：推进 sub_state，写 transition，自动检测 trigger 类型
- [x] `workflow_state.py` approve 命令：记录人工批准到 `gate-approvals.json`
- [x] `workflow_state.py` validate 命令：校验 handoff.json schema
- [x] `check_phase_done.py` planning checker：复用 artifact checker + handoff.json 状态校验
- [x] `check_phase_done.py` building checker：pytest + TODO 扫描（known-debt 白名单）+ benchmark smoke（可选跳过）+ handoff.json 状态
- [x] `check_phase_done.py` code-review checker：review report 存在性 + CHANGES_REQUESTED 检测 + handoff.json 状态
- [x] `check_phase_done.py` closing checker：openspec validate + 归档检查 + backlog 一致性 + artifact checker + handoff.json 状态

## 3. Agent 行为集成

- [x] AGENTS.md 新增"工作流自动推进与 Gate 机制"章节：会话启动协议、Gate 停止规则、阶段内自动推进、跨阶段推进、Worktree 隔离、验证命令速查、ADR 创建规则
- [x] `agent/workflow/handoff_note.py`：FALLBACK_HANDOFF_PROMPT 加入 ADR 格式要求
- [x] `agent/workflow/role_registry.py`：五个角色 system_prompt 追加 check_phase_done.py 验证指令
- [x] `docs/requirements-process.md`：新增"架构决策记录（ADR）"章节

## 4. 测试

- [x] `tests/test_check_phase_done.py`：15 个测试覆盖 planning/building/code-review/closing
- [x] 全量 pytest 通过（新 15 + 已有 22）
- [x] `workflow_state.py discover` 手动验证通过

## 5. 文档

- [x] 本 change 的 proposal.md / design.md / tasks.md
- [ ] 更新 `docs/openspec-change-backlog.md`（归档收尾阶段完成）
