# Tasks: grill 用户确认门禁

## 0. 前置决策

- [x] 0.1 独立 subagent grill 本 change 设计，产出 `reviews/grill-design.md`（含 User Confirmation）
- [x] 0.2 Reference Implementation Research 实质调研（plan mode 审批 / review manifest 绑定）

## 1. checker User Confirmation 校验

- [x] 1.1 `_extract_open_questions(text) -> list[str]`：解析 `## Open Questions` 节非占位条目
- [x] 1.2 `_extract_user_confirmations(text) -> list[str]`：解析 `## User Confirmation` 节确认记录
- [x] 1.3 `_check_design_review_task` 增强：grill-design.md 存在时，若 N>0 且 tasks 全勾选且 M<N → 报错

## 2. workflow_guard 写代码 gate 增强

- [x] 2.1 `_grill_evidence_missing` 增强：grill-design.md 存在但 Open Questions 未确认（M<N）→ 仍返回 True
- [x] 2.2 提取规则与 checker 一致（两文件独立复刻）

## 3. 回归测试

- [x] 3.1 checker：Open Questions 为空通过；有确认覆盖通过；有未确认且全勾选报错；无 User Confirmation 节报错
- [x] 3.2 workflow_guard：grill-design.md 存在但未确认 → 拦截

## 4. 流程规则 + skill

- [x] 4.1 AGENTS.md 最高优先级规则：grill 后必须停轮交给用户确认，未确认不得进 building
- [x] 4.2 batch-grill-me / grilling skill：产出 User Confirmation 节 + 停轮契约

## 5. 收尾

- [x] 5.1 OpenSpec spec 同步（change-documentation MODIFIED requirement 加 user-confirmation 场景）
- [x] 5.2 全量 pytest + openspec validate + artifact checker
- [x] 5.3 benchmark smoke（process change 不强制，标注跳过）

## 6. 收尾校验（checker 要求项）

- [x] 6.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）
- [x] 6.2 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
