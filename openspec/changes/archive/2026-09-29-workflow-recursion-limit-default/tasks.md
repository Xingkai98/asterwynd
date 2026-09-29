# Tasks: workflow 图级 recursion_limit 默认值调大（25 → 100）

> 状态：**实现完成，审阅闭环 PASS（Round 2）**，进入归档收尾（3.5 / 3.6(post-merge) 未勾）。
> 设计阶段产出：proposal + design + spec delta + tasks + grill（Q1–Q6 已用户拍板 2026-09-29）。

## 0. 设计追问（实现前门禁）

- [x] 0.1 跑 `batch-grill-me`（`/grill` 等价流程：独立零记忆 subagent）审视 design.md D1–D5 与 Open Questions，产出 `reviews/grill-design.md`（≥3 条决策记录 + `## Open Questions` + `## User Confirmation`）。已产出 5 条 Confirmed Decisions + 6 条 Design Corrections + 6 条 Open Questions。
- [x] 0.2 停轮把 `## Open Questions` 逐条配具体例子交用户拍板；答复记录进 `reviews/grill-design.md` 的 `## User Confirmation`。**Q1–Q6 已全部确认（2026-09-29）**：Q1 不收敛 / Q2 维持 100 / Q3 接受指纹变化 / Q4 归属 #246（change-id `workflow-builtin-templates`）/ Q5 只做 peer-review 拓扑回归 / Q6 保留覆盖语义句。
- [x] 0.3 把 grill 结论与用户答复回写 design.md 的 `## Pre-Implementation Review`，并把 D1/D3/D5 的结论按答复定稿。已完成：D1/D3/D5 的「备选（未采纳）」均已标 **✅ 已确认（2026-09-29）**；Q1–Q6 在 Open Questions 节各有答复实质；换算比一节同时写明 superstep/轮 与 run/轮 两个比值。

## 1. 默认值改为 100（四处定义点 + docstring 同步）

- [x] 1.1 `agent/config.py`：`WorkflowLimitsConfig.recursion_limit` 字段默认值 `25` → `100`，docstring 同步说明新默认值与「结构闸后盾」的定位。
- [x] 1.2 `agent/config.py`：`_parse_workflow_limits` 的 `mapping.get("recursion_limit", 25)` → `100`；`_validate_positive_int` 的「拒绝 0 / 负值 / 非数值」语义保持不变。
- [x] 1.3 `agent/tools/builtin/subagents.py`：`_spec_bounds` 的 `getattr(limits, "recursion_limit", 25)` 兜底 → `100`（与 1.1/1.2 同值，否则 `manager.config` 缺失路径会分叉）。
- [x] 1.4 `agent/subagent/workflow.py`：`DEFAULT_RECURSION_LIMIT = 25` → `100`；同步模块 docstring 第 13 行的「三闸默认值」表述。确认 `WorkflowSpec` 字段默认（`:230`）、`parse_workflow_spec` 形参默认（`:316`）、`to_dict()` 哨兵（`:288`）自动跟随，无需单独改。
- [x] 1.5 核实「无第五处」：确认 `scheduler.py` 的「默认 25」是并发容量（`max_active + max_queued_runs`）不得改动；`web/static/workflow_graph.js` 只读运行时 `diagnostics`，不含默认值。

## 2. 测试（TDD，先红后绿）

- [x] 2.1 更新 `tests/agent/subagent/test_workflow_tools.py:235` 的默认值断言 `== 25` → `== 100`（`test_workflow_limits_default_to_documented_values`）。
- [x] 2.2 新增三路径一致性断言（锁 D2）：`AsterwyndConfig()` 直构 = 100；yaml 未写该键时 `load_config` = 100；`_spec_bounds` 在 `manager.config` 链路缺失时兜底 = 100。
- [x] 2.3 **核心回归（构造口径须实测标定，不得照抄估算）**：`run_pattern("peer-review", max_rounds=N)` + 始终回 `CRITIQUE` 的 `StaticLLM`，使 route 的 `max_routes=N` 成为唯一自然终点。
  - 先跑探针**实测标定 N**：确认该图跑满 N 轮所需 superstep 数严格落在 (25, 100) 之间。
  - 默认配置（100）→ 断言 `diagnostics.reason == "max_routes"`（证图级闸未提前触发）。
  - **对照组**：同图同 N，显式 `recursion_limit=25` → 断言 `diagnostics.reason == "recursion_limit"`（证该图确实能触发旧默认，防恒真）。
- [x] 2.4 spec 级回归：对应 spec delta 的「默认配置不掐断迭代式任务」与「显式更小的 recursion_limit 仍精确生效」两条 Scenario，各写一条断言（后者可用既有 `recursion_limit: 7` 配置路径）。
- [x] 2.5 序列化面（锁 D3）：未声明 `recursion_limit` 的 spec，其 `to_dict()` 不含该键且 `spec_hash` 与改前逐字相同；显式 `recursion_limit=25` 的 spec 在新默认下含该键。
- [x] 2.6 兼容回归保持绿：既有触发类测试（`test_scheduler.py` / `test_terminal_honesty.py` / `test_dynamic_foreach.py` / `test_aggregation_runtime.py` / `test_workflow_graph_events.py` / `test_workflow_graph_snapshot.py`）与钳制类测试（`test_workflow_asset_limits.py`）全部不红。

## 3. 收尾

- [x] 3.0 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过（本 change 触及 agent-runtime / subagent 面）。
- [x] 3.1 同步 current spec：把 spec delta 合入 `openspec/specs/multi-agent-collaboration/spec.md:124` 的「reducer 声明与图级递归上限」Requirement（受保护路径，需 `current_spec_synced` 结构化事件）。
- [x] 3.2 文档影响：复核 `README.md` / `README_EN.md` / `asterwynd.example.yaml` / `docs/` 是否记载该默认值（已扫描，预期无命中；README 若改必须同 PR 同步 `README_EN.md`）；`docs/openspec-change-backlog.md` 的历史 C2 条目按「不改历史」保留。
- [x] 3.3 跑 `/review-loop workflow-recursion-limit-default` 独立审阅闭环，产出 `reviews/building-review.md`（PASS）+ review manifest。
- [x] 3.4 `uv run pytest -q` 全绿；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py` 通过。
- [x] 3.5 归档：change 移入 `openspec/changes/archive/YYYY-MM-DD-workflow-recursion-limit-default/`，从 `docs/openspec-change-backlog.md` 移除，写 `current_spec_synced` / `change_archived` / `backlog_updated` 结构化事件。
- [ ] 3.6 （post-merge）PR 合入后给 issue #262 加完成说明 comment 并关闭。

## 4. 审阅闭环修复（Round 1 → Round 2）

- [x] 4.1 **（审阅 Issue 1，medium）** 把实现类任务 1.1–2.6 与已完成收尾任务 3.0–3.4 勾上——归档点完成度门禁对无 `(post-merge)` 标记的未勾任务判红。
- [x] 4.2 **（审阅 Issue 2 + Issue 3，medium + low）** 提交审阅期间的工作区改动：`test_declared_above_config_is_not_raised` 名实不符（构造的 spec 未声明该键，实际测的是「未声明→取配置值」路径），改为 `test_declared_above_config_is_kept_at_parse_but_clamped_at_read`——显式声明 `recursion_limit=500`，两段断言（解析保留 500 + `_eff_limit` 钳到 7）。
- [x] 4.3 **（审阅 Issue 4，low）** 订正 `agent/subagent/patterns.py:238` 的生产注释量纲错误：「peer-review 一轮约 1.9 superstep」→「约 3 superstep（实测 `superstep = 3N + 2`）」并注明「≈1.9」是 run/轮口径。该行属 pre-existing，但本 change 主题正是该换算比。
- [x] 4.4 **（审阅 Issue 5，low）** 在 `proposal.md` 的 `## What Changes` 记录附带效果：`compile_pattern` 对 `max_rounds` 的编译期接受域随同一常量由 `≤25` 放宽到 `≤100`（收益方向）。
- [x] 4.5 修复后重跑全量验证（pytest / openspec validate / artifact checker）并再审（Round 2），直至 PASS。
