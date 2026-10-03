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

- [ ] 3.1 先写失败测试：T1/T2（声明期 warnings）、T3（dry-run 三字段）、T4（运行期）、T5（不截断不报）、T6（max_items=0 不报）、T7（与 ref 界不混）、source 驱动声明期不报
- [ ] 3.2 声明期 `_foreach_truncation_warnings(spec)` helper（字面 items 截断 → 可行动警告），在 `DeclareWorkflow` 与 `RunWorkflow(spec=)` 调用
- [ ] 3.3 dry-run foreach 条目补 `items_total`/`items_omitted`（与 `items_expanded` 三元）
- [ ] 3.4 运行期 `GetWorkflow` foreach 节点暴露静态截断信号
- [ ] 3.5 `_resolve_items` 记录声明/展开数供运行期读
- [ ] 3.6 字段名与 `item_refs_omitted` 的 `items_total` 划清（D2）
- [ ] 3.7 回归：workflow declare/dry-run/run 既有测试 + 全量

## 4. 审阅与验收

- [ ] 4.1 `/review-loop` 独立审阅至 PASS 或 3 轮封顶（report + manifest）
- [ ] 4.2 全量 `uv run pytest -q`（对照排除环境噪声）
- [ ] 4.3 验收 T1–T8
- [ ] 4.4 benchmark smoke（触及 `agent/tools/`）

## 5. 收尾

- [ ] 5.1 spec delta 同步到 `openspec/specs/multi-agent-collaboration/spec.md`（受保护路径，需结构化事件）
- [ ] 5.2 归档到 `openspec/changes/archive/2026-10-0X-foreach-truncation-visibility/`（受保护路径）
- [ ] 5.3 从 `docs/openspec-change-backlog.md` 移除（受保护路径）
- [ ] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [ ] 5.5 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
- [ ] 5.6 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描
- [ ] 5.7 (post-merge) 发起 PR（关联 #279）、写明验证结果并合入
- [ ] 5.8 (post-merge) PR 合入后给 #279 加完成说明并关闭
