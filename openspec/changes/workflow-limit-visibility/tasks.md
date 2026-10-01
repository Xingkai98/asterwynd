# Tasks: 工作流闸门可见性

## 1. 立项与调研

- [ ] 1.1 关联 GitHub issue #275，写 `proposal.md`（含 Change Type / Why / What Changes / Capabilities / 验收 / RIR / Impact Analysis / Non-Goals）
- [ ] 1.2 写 `design.md`（Context / Goals-Non-Goals / Decisions / Risks / Testing Strategy / Pre-Implementation Review / Impact Analysis）
- [ ] 1.3 写 spec delta（MODIFIED 2 条 Requirement + 新增 Scenario）
- [ ] 1.4 技术侦察脚本与实测证据落 `research/`（`gap_probe.py` 确认 G1–G4 缺口；`gate_trip_probe.py` 确认 G5 撞闸非结构化）
- [ ] 1.5 补齐 `## Reference Implementation Research` 的 findings 与 design impact（`research_tier: full`）
- [ ] 1.6 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）

## 2. grill 与确认

- [ ] 2.1 用独立零记忆 subagent 按 `batch-grill-me` 逐轮追问 `design.md`，产出 `reviews/grill-design.md`
- [ ] 2.2 停轮把 `## Open Questions` 逐项（每条配具体例子）抛给用户，等待答复
- [ ] 2.3 用户答复写回 `grill-design.md` 的 `## User Confirmation` 节

## 3. 实现（测试先行）

- [ ] 3.1 先写失败测试 `tests/agent/subagent/test_workflow_limit_visibility.py`：`limits` 三段式、`node_budget` 宽/窄扇入、route `max_routes`+`used`、撞闸 `diagnostics`（含未撞闸不挂诊断）
- [ ] 3.2 `_build_dry_run_report` 增 `limits`（复用 `limits_report(spec, {})`）
- [ ] 3.3 `_build_dry_run_report` 增 `node_budget`（源 `ExecutionPlan.declared_nodes`/`.inserted_nodes`/`.nodes` + `_eff_limit("max_nodes")`）
- [ ] 3.4 route 条目增生效 `max_routes` 与 `_route_counts` 计数（同源）
- [ ] 3.5 报告增 `diagnostics`（镜像 `_envelope()` 的 `if self._diagnostics` 条件）
- [ ] 3.6 报告 `notes` 补口径说明句（clamped 恒 false 的原因；动态闸余量不适用）
- [ ] 3.7 `DeclareWorkflow` 描述补图级三闸默认值句（值，非示例）
- [ ] 3.8 扩展 `tests/agent/subagent/test_workflow_tool_discoverability.py`：描述含三闸默认值 + 长度守卫
- [ ] 3.9 不变量测试：`report["limits"] == limits_report(spec, {})` 逐字段相等（变异验证）
- [ ] 3.10 回归：`tests/agent/subagent/test_workflow_dry_run.py` 既有断言不失效

## 4. 审阅与验收

- [ ] 4.1 `/review-loop` 独立审阅至 PASS 或 3 轮封顶，报告落 `reviews/building-review.md` + manifest
- [ ] 4.2 全量 `uv run pytest -q`（对照 pristine 排除环境噪声）
- [ ] 4.3 真实 LLM 验收 N=3（主 session 跑）：L0 生效值可见、L1 展开数可见、L2 撞闸可读、L3 无新误读；证据落 `reviews/acceptance-evidence.md`
- [ ] 4.4 **benchmark smoke**（本 change 触及 `agent/tools/builtin/subagents.py`）：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-limit-visibility`

## 5. 收尾

- [ ] 5.1 把 spec delta 同步到 current spec（`openspec/specs/multi-agent-collaboration/spec.md`：MODIFIED 2 条；受保护路径，需结构化事件）
- [ ] 5.2 归档到 `openspec/changes/archive/2026-10-01-workflow-limit-visibility/`（受保护路径）
- [ ] 5.3 从 `docs/openspec-change-backlog.md` 移除（受保护路径）
- [ ] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [ ] 5.5 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
- [ ] 5.6 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描
- [ ] 5.7 发起 PR（标题关联 #275），写明验证结果
- [ ] 5.8 (post-merge) PR 合入后关 issue #275，并在 #276 留言解锁（blocked-by 解除）
