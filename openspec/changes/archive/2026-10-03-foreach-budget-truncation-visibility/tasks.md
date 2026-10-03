# Tasks: foreach 预算截断可见性

## 1. 立项与调研

- [x] 1.1 关联 GitHub issue #286，写 `proposal.md`
- [x] 1.2 写 `design.md`（D1 两出口 / D2 复用+成因字段 / D3 扩展共享 helper / D4 零噪声 / D5 与 #279 不冲突 / D6 成因粒度）
- [x] 1.3 写 spec delta（multi-agent-collaboration ADDED 1「foreach 预算截断可见」+ MODIFIED 1「foreach 静态截断可见」）
- [x] 1.4 补齐 `## Reference Implementation Research`（`research_tier: light`）
- [x] 1.5 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，结构化事件已记）
- [x] 1.6 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过

## 2. grill 与对抗（实现前强制）

- [x] 2.1 独立零记忆 subagent 按 `batch-grill-me` 追问 `design.md`，产出 `reviews/grill-design.md`（Confirmed Decisions + Open Questions + 风险表）
- [x] 2.2 独立零记忆对抗 subagent 证伪 grill 结论，产出 `reviews/grill-adversarial.md`；主 session 逐条复核
- [x] 2.3 停轮把 Open Questions（每条配具体例子）抛给用户
- [x] 2.4 用户答复写回 `## User Confirmation`（Q1–Qn）
- [x] 2.5 按结论回写 design/proposal/spec delta（成因字段名 / 出口范围 / 成因粒度等）

## 3. 实现（测试先行）

- [x] 3.1 先写失败测试：T1（dry-run 三元+成因）、T2（运行期后写可见）、T3（成因判别）、T4（零噪声）、T5（静态路径不退化）
- [x] 3.2 扩展 `_foreach_visibility_fields`（`subagents.py:1122`）：去 `max_items > 0` 前置，`declared > expanded` 时按 `max_items` 值发 `items_omitted_cause`
- [x] 3.3 dry-run foreach 条目（`subagents.py:1687`）与运行期后写（`_attach_foreach_visibility`，`:1159`）共用扩展后的 helper
- [x] 3.4 确认 `_resolve_items`（`scheduler.py:2675`）已记 `items_declared`（预算路径切片前）——无需改；成因粒度粗 `"budget"` 无需回传绑定维度
- [x] 3.5 成因字段名避开既有 `reason` 键（D2）；运行期字段**后写**绕过 `_bounded_node`（D3）；**新增** `RunWorkflow` 信封出口（OQ2=(b)，`_drive_scheduler` 后写）
- [x] 3.6 回归：`test_foreach_truncation_visibility.py`（25 条，含 7 新）+ `test_dynamic_foreach.py` + 全量（唯一 2 处失败为预存在环境问题，与本 change 无关）

## 4. 审阅与验收

- [x] 4.1 `/review-loop` 独立审阅至 PASS 或 3 轮封顶（report + manifest）
- [x] 4.2 全量 `uv run pytest -q`
- [x] 4.3 验收 T1–T5（新测试全绿）
- [x] 4.4 benchmark smoke（`benchmark-gate` PASS，success_rate=1.0000）

## 5. 收尾

- [x] 5.1 spec delta 同步到 current spec（`openspec/specs/multi-agent-collaboration/spec.md`；受保护路径，结构化事件已记）
- [ ] 5.2 归档到 `openspec/changes/archive/2026-10-03-foreach-budget-truncation-visibility/`（受保护路径）
- [ ] 5.3 从 `docs/openspec-change-backlog.md` 移除（受保护路径；标记已归档）
- [ ] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [ ] 5.5 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`（+ `--check-archived`）
- [ ] 5.6 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描
- [ ] 5.7 (post-merge) 发起 PR（关联 #286）、写明验证结果并合入；由主 session 执行，worktree 不 push
- [ ] 5.8 (post-merge) PR 合入后给 #286 加完成说明并关闭
