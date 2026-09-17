# Tasks: workflow 四维预算默认无上限

## 0. 设计追问（实现前门禁）

- [x] 0.1 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D6，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认，答复记录进 `## User Confirmation`）。
- [x] 0.2 把 grill 结论与用户答复回写 design.md 的 `## Pre-Implementation Review`，并把 D4（CLI 入参）的最终结论从「待拍板」改为明确结论。

## 1. 默认值改为「不限」

- [x] 1.1 `agent/config.py`：`WorkflowBudgetConfig` 四字段默认值改为 0（`0 = 不限`，沿用 C4 Q11 哨兵），docstring 同步说明「默认不设上限，显式配置才设限」。
- [x] 1.2 `agent/config.py`：`_parse_workflow_budget` 四处 `mapping.get(key, <默认>)` 默认值同步改为 0（含 docstring 口径更新）；显式 `null` / 负值 / 非数值的拒绝语义保持不变。
- [x] 1.3 `agent/subagent/workflow_budget.py`：`WorkflowBudget.__init__` 四处 `getattr(..., <兜底>)` 兜底值改为 0，docstring 同步。
- [x] 1.4 CLI 入参：用户已拍板**不改**（grill Q1 / design D4），不加 `--workflow-budget-*`，本项无需代码改动。
- [x] 1.5 段落级 `null` 收紧（grill Q2 / design D7）：`subagents` / `subagents.workflow` / `subagents.workflow.budget` 三级，键存在但值为 `null` 时抛 `ConfigError`（键缺失仍走默认=不限）；替换现有 `mapping.get(key, {})` 的静默 `{}` 兜底。

## 2. 测试（TDD，先红后绿）

- [x] 2.1 更新断言旧默认值的既有测试：`tests/agent/subagent/test_workflow_budget_config.py`（默认值 / 部分配置保留默认 / 缺段默认）、`tests/agent/subagent/test_workflow_budget.py`（`test_defaults_come_from_config`、`test_dimensions_snapshot_shape`）、`tests/benchmark/test_workflow_replay.py`（`budget_config` 断言）。
- [x] 2.2 改写 `test_max_total_runs_default_matches_structural_max_runs`：默认不再与 C2 对齐，改为断言「预算默认不限（0）+ C2 `max_runs` 仍兜底」的新语义，不删除该语义覆盖。
- [x] 2.3 新增回归（**构造口径经 grill 确认，必须照此写否则是假保护**）：`_chain_spec(8)` + `StaticLLM(usage=Usage(50_000, 0))`（8 run 累计 400k token，真越过旧默认 200k）→ 默认配置下 `status == "completed"`、`budget.exceeded is False`；**同图对照组**：显式 `max_total_tokens=200000` 时 `status == "budget_exceeded"` 且 `completed < 8`。runs / wall_time 维度不作默认路径回归面（前者被 C2 `max_runs` 等值顶掉，后者单测不可达）。
- [x] 2.4 新增/保持：显式配置上限仍触发 `budget_exceeded` + drain + 根节点终态；显式 `0` 仍表示不限；显式 `null` / 负值仍被拒。
- [x] 2.5 兼容回归：C2 `max_runs` / `max_nodes` 在预算不限时仍兜底；`max_items=0` 展开容量退化为 C2 两闸最小值。
- [x] 2.6 段落级 null 测试（grill Q2）：三级段落（`subagents` / `subagents.workflow` / `subagents.workflow.budget`）各写一个 `null` → 参数化断言 `ConfigError`；同时断言「键缺失」仍正常加载为默认（不限）。

## 3. 收尾

- [x] 3.0 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过（本 change 触及 agent-runtime / subagent 面，按门禁要求跑）。
- [ ] 3.1 同步 current spec：把 spec delta 合入 `openspec/specs/multi-agent-collaboration/spec.md` 的「workflow 级四维度总预算」Requirement。
- [ ] 3.2 文档影响：复核 `asterwynd.example.yaml`、`README.md` / `README_EN.md`、`docs/`（关键词 `workflow budget` / `max_total_` / 预算默认）是否需要同步；README 改动必须同 PR 同步 `README_EN.md`。
- [ ] 3.3 跑 `/review-loop workflow-budget-unbounded-default` 独立审阅闭环，产出 `reviews/building-review.md`（PASS）+ review manifest。
- [ ] 3.4 `uv run pytest -q` 全绿；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 通过。
- [ ] 3.5 归档：change 移入 `openspec/changes/archive/2026-09-17-workflow-budget-unbounded-default/`，从 `docs/openspec-change-backlog.md` 移除，写 `current_spec_synced` / `change_archived` / `backlog_updated` 结构化事件。
