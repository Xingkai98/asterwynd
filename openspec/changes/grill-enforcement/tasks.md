# Tasks: 流程强制 — batch-grill-me 独立执行 + 写代码前门禁

## 0. 本 change 先 grill（独立 subagent 设计追问）

- [x] 0.1 独立 subagent grill 本 design.md，产出 `reviews/grill-design.md`（run id: grill-subagent-independent-design-review）
- [x] 0.2 grill 发现 2 处硬伤 + 5 处必须修改，已整合进 design.md（Decision 5-10）

## 1. 独立 grill 命令

- [x] 1.1 `.claude/commands/grill.md`：spawn 零记忆 subagent grill design.md，产出结构化决策记录到 `reviews/grill-design.md`
- [x] 1.2 结构：`## Confirmed Decisions`（每条 `- **决策**: ...；理由: ...；来源: <run id>`，至少 3 条）+ `## Open Questions`（可为空）
- [x] 1.3 与 /review-loop 对称：grill 在开发前、review 在开发后

## 2. 写代码前门禁（workflow_guard）

- [x] 2.1 change 映射机制：分支名 `<change-id>/<date>` 推导为主，单 active change 兜底，都不成立则门禁不触发
- [x] 2.2 grill 证据检查：写操作时检查 `reviews/grill-design.md` 存在且含 `## Confirmed Decisions`
- [x] 2.3 豁免清单：`openspec/changes/<id>/{proposal,design,tasks}.md`、`<id>/specs/**`、`<id>/reviews/**` 不拦截；代码目录（agent/tests/scripts）不豁免
- [x] 2.4 缺失 → exit 2 阻止写操作，提示运行 /grill
- [x] 2.5 单元测试：有/无 grill 证据、分支映射、豁免清单

## 3. checker 结构化验证

- [x] 3.1 `_check_design_review_task`：验证 `reviews/grill-design.md` 存在 + `## Confirmed Decisions` 非空且 ≥3 条
- [x] 3.2 触发条件收窄：非 docs + 有 spec delta + tasks 全勾选（与 building-review 对齐，存量不误伤）
- [x] 3.3 与 update-design-review-method 兼容：结构化验证优先，字面检查兜底
- [x] 3.4 单元测试：结构化证据通过 / 缺失报错 / 字面字样不通过 / 存量未全勾选不触发

## 4. 文档

- [x] 4.1 `AGENTS.md`：把「必须 batch-grill-me」描述为写代码前机械门禁 + 分支纪律
- [x] 4.2 `openspec/specs/change-documentation/spec.md`：更新设计追问 requirement（先建 spec delta，见 5.1）

## 5. spec delta

- [x] 5.1 建 `specs/change-documentation/spec.md` delta：设计追问 requirement 从"字面检查"升级为"结构化证据 + 门禁"
- [x] 5.2 同步当前规格 `openspec/specs/change-documentation/spec.md` + workflow-events 事件

## 6. 收尾

- [ ] 6.1 实现完成后走 /review-loop 审阅闭环
- [ ] 6.2 全量 pytest + openspec validate + artifact checker
- [ ] 6.3 归档 + backlog 清理
