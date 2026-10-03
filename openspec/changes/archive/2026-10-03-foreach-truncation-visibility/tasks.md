# Tasks: foreach 截断可见性

## 1. 立项与调研

- [ ] 1.1 关联 GitHub issue #279，写 `proposal.md`
- [ ] 1.2 写 `design.md`（D1 三出口 / D2 字段名 / D3 声明期边界 / D4 与 ref 界划清 / D5 措辞）
- [ ] 1.3 写 spec delta（multi-agent-collaboration ADDED 1「foreach 静态截断可见」）
- [ ] 1.4 补齐 `## Reference Implementation Research`（`research_tier: light`）
- [ ] 1.5 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）
- [ ] 1.6 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过

## 2. grill 与对抗（实现前强制）

- [ ] 2.1 独立零记忆 subagent 按 `batch-grill-me` 追问 `design.md`，产出 `reviews/grill-design.md`
- [ ] 2.2 独立零记忆对抗 subagent 证伪 grill 结论，产出 `reviews/grill-adversarial.md`；主 session 逐条复核
- [ ] 2.3 停轮把 Open Questions（每条配具体例子）抛给用户
- [ ] 2.4 用户答复写回 `## User Confirmation`
- [ ] 2.5 按结论回写 design/proposal/spec delta

## 3. 实现（测试先行）

- [x] 3.1 先写失败测试：T1/T2（声明期 warnings）、T3（dry-run 三字段）、T4（运行期）、T5（不截断不报）、T6（max_items=0 不报）、T7（与 ref 界不混）、source 驱动声明期不报
- [x] 3.2 声明期 `_foreach_truncation_warnings(spec)` helper（字面 items 截断 → 可行动警告），在 `DeclareWorkflow` 与 `RunWorkflow(spec=)` 调用
- [x] 3.3 dry-run foreach 条目补 `items_declared`/`items_omitted`（与 `items_expanded` 三元；source 驱动标模拟）
- [x] 3.4 运行期 `GetWorkflow` foreach 节点暴露静态截断信号（**后写**绕过 `_bounded_node`）
- [x] 3.4b **Q4（已纳入）**：空集合 / source 无产出 ⇒ dry-run 与运行期**显式**标「集合为空/无产出」，区别于正常展开 0 项
- [x] 3.4c **Q5**：dry-run 对 source 驱动的 `items_declared` 标「模拟、不可信」；**M1** 选 **(b)**——声明期新 warning **不切片**，docstring 如实写「上界 = foreach 节点数（受 `max_nodes` 间接约束），不漏项」，不引用 dry-run 才有的 `warnings_omitted`（理由：声明期警告是对声明的忠实反映，切片反而可能漏掉某个节点）；测试 `test_declare_emits_one_warning_per_truncated_node` 锁 3 节点 ⇒ 3 条
- [x] 3.5 `_resolve_items` 记录声明/展开数供运行期读
- [x] 3.6 字段名用扁平 `items_declared`/`items_omitted`、**绝不复用** `items_total`（D2）；运行期字段**后写**绕过 `_bounded_node`（D3）
- [x] 3.7 回归：workflow declare/dry-run/run 既有测试 + 全量

## 4. 审阅与验收

- [x] 4.1 `/review-loop` 独立审阅至 PASS 或 3 轮封顶（report + manifest）——**1 轮 PASS**（3 条低严重度观察，其中 low-1 已改 `2b17f6e`）；`reviews/building-review.md`
- [x] 4.2 全量 `uv run pytest -q`——`3972 passed, 2 failed, 9 skipped`（2 失败 = `test_persistent.py::TestFindScopeRoot::*` 的 `/tmp/.git` 残留目录环境噪声，与 change 无关）
- [x] 4.3 验收 T1–T9（新测试 `tests/agent/subagent/test_foreach_truncation_visibility.py` 18/18）
- [x] 4.4 benchmark smoke（触及 `agent/tools/`）——`72 tasks`（5 passed / 38 unsupported / 29 failed，`--agent fake` 预期分布），无 crash

## 5. 收尾

- [ ] 5.1 spec delta 同步到 current spec（`openspec/specs/multi-agent-collaboration/spec.md`；受保护路径，需结构化事件）
- [ ] 5.2 归档到 `openspec/changes/archive/2026-10-0X-foreach-truncation-visibility/`（受保护路径）
- [ ] 5.3 从 `docs/openspec-change-backlog.md` 移除（受保护路径）
- [ ] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [ ] 5.5 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
- [x] 5.6 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描（`max_items`/`foreach`/`items_expanded` **0 命中**——内部 DSL 报告面，无面向用户文档描述它，**无需改**）
- [ ] 5.7 (post-merge) 发起 PR（关联 #279）、写明验证结果并合入
- [ ] 5.8 (post-merge) PR 合入后给 #279 加完成说明并关闭
