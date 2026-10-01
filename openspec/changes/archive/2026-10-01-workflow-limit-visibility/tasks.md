# Tasks: 工作流闸门可见性

## 1. 立项与调研

- [x] 1.1 关联 GitHub issue #275，写 `proposal.md`（含 Change Type / Why / What Changes / Capabilities / 验收 / RIR / Impact Analysis / Non-Goals）
- [x] 1.2 写 `design.md`（Context / Goals-Non-Goals / Decisions / Risks / Testing Strategy / Pre-Implementation Review / Impact Analysis）
- [x] 1.3 写 spec delta（MODIFIED 2 条 Requirement + 新增 Scenario）
- [x] 1.4 技术侦察脚本与实测证据落 `research/`（`gap_probe.py` 确认 G1–G4 缺口；`gate_trip_probe.py` 确认 G5 撞闸非结构化；`node_budget_probe.py` 钉死 max_nodes 计费口径与撞闸图假余量）
- [x] 1.5 补齐 `## Reference Implementation Research` 的 findings 与 design impact（`research_tier: full`）
- [x] 1.6 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）

## 2. grill 与确认

- [x] 2.1 用独立零记忆 subagent 按 `batch-grill-me` 逐轮追问 `design.md`，产出 `reviews/grill-design.md`
- [x] 2.2 停轮把 `## Open Questions` 逐项（每条配具体例子）抛给用户，等待答复
- [x] 2.3 用户答复写回 `grill-design.md` 的 `## User Confirmation` 节
- [x] 2.4 按 grill 实测订正回写 design/proposal/spec delta（D2 计费口径、D3 route runs 恒 0、D4 无条件挂载、D6 调用级同源锁、L0 可判定性）

## 3. 实现（测试先行）

- [x] 3.1 先写失败测试 `tests/agent/subagent/test_workflow_limit_visibility.py`：`limits` 三段式、`node_budget`（含撞闸图 `headroom < 0`）、route `max_routes`+`gate_count`、`diagnostics` 无条件挂载（未撞闸为 `{}`）
- [x] 3.2 `_build_dry_run_report` 增 `limits`（复用 `limits_report(spec, {})`）
- [x] 3.3 scheduler 增「投影展开值」记录（`_check_foreach_budget` 内、超限判定**前**记入新只读字段；不改判定逻辑）
- [x] 3.4 `_build_dry_run_report` 增 `node_budget`（`graph_nodes = len(plan.nodes)`；`expanded_nodes` 取 3.3 的投影记录；`auto_inserted = len(plan.inserted_nodes)`；`headroom = limit - expanded_nodes`）
- [x] 3.5 route 条目增生效 `max_routes` 与 `gate_count`（取 `scheduler._route_counts`，同源）
- [x] 3.6 报告增 `diagnostics`（**无条件**挂载，镜像 `parent_envelope`；未撞闸为 `{}`）
- [x] 3.7 报告 `notes` 补口径说明句（`clamped` 恒 false 的原因；`expanded_nodes` vs `graph_nodes` 的差别；route `runs` 恒 0 与 `gate_count`；`diagnostics` 非空 ≠ 撞闸）
- [x] 3.8 `DeclareWorkflow` 描述补图级三闸**模块默认值**句（值，非示例；含「以报告生效值为准」）
- [x] 3.9 扩展 `tests/agent/subagent/test_workflow_tool_discoverability.py`：描述含三闸名 + 数值（宽松匹配，不绑定运行时配置）+ 长度守卫
- [x] 3.10 **调用级同源锁**（非值相等）：monkeypatch `limits_report`/`_eff_limit` 返回哨兵，断言报告字段反映哨兵；`expanded_nodes` 断言取自闸门投影记录
- [x] 3.11 scheduler 侧测试：撞闸图 `投影展开值 == len(plan.nodes) + Σ items`，且既有 `max_nodes` 拒绝行为逐字不变
- [x] 3.12 回归：`tests/agent/subagent/test_workflow_dry_run.py` 既有断言不失效

## 4. 审阅与验收

- [x] 4.1 `/review-loop` 独立审阅至 PASS 或 3 轮封顶，报告落 `reviews/building-review.md` + manifest
- [x] 4.2 全量 `uv run pytest -q`（对照 pristine 排除环境噪声）
- [x] 4.3 真实 LLM 验收 N=3（主 session 跑）：L0 生效值可见、L1 展开数可见、L2 撞闸可读、L3 无新误读；证据落 `reviews/acceptance-evidence.md`
- [x] 4.4 **benchmark smoke**（本 change 触及 `agent/tools/builtin/subagents.py`）：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-limit-visibility` → **`Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29`**，与 pristine baseline（stash 改动后同命令）**逐项相同**，本 change 未引入 benchmark 退化。

## 5. 收尾

- [x] 5.1 把 spec delta 同步到 current spec（`openspec/specs/multi-agent-collaboration/spec.md`：MODIFIED 2 条；受保护路径，需结构化事件）
- [x] 5.2 归档到 `openspec/changes/archive/2026-10-01-workflow-limit-visibility/`（受保护路径）
- [x] 5.3 从 `docs/openspec-change-backlog.md` 移除（受保护路径）
- [x] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 5.5 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
- [x] 5.6 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描
- [x] 5.7 发起 PR（标题关联 #275），写明验证结果
- [ ] 5.8 (post-merge) PR 合入后关 issue #275，并在 #276 留言解锁（blocked-by 解除）

## 6. 审阅修复（review-loop Round 1）

- [x] 6.1 Issue 1（MEDIUM）：`notes` + spec delta 限定「`expanded_nodes == graph_nodes + Σitems`」的成立条件（自动插层撞闸路径上不成立），新增 Scenario 与回归测试 `test_node_budget_baseline_differs_when_auto_layer_is_rejected`
- [x] 6.2 Issue 2（LOW）：route `gate_count` 补调用级哨兵锁 `test_gate_count_reads_the_scheduler_route_counter`（变异验证变红）
- [x] 6.3 Issue 3（LOW）：收尾阶段在 PR 描述附 benchmark smoke 原始命令与对比摘要
