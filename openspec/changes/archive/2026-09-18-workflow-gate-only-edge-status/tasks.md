# Tasks: 纯门控边的独立状态

## 0. 设计追问（实现前门禁）

- [x] 0.1 跑 `batch-grill-me`（或等价独立零记忆 subagent 设计追问）审视 design.md D1–D4，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。

## 1. 后端：`_edge_status` 加档

- [x] 1.1 `agent/subagent/scheduler.py::_edge_status` 在 `ready` 之后、兜底 `inactive` 之前加 `satisfied`：判据 `source/target 非 None`（防御）`and edge.required and source.status == "completed" and target.status != "pending" and target.status != "skipped"`（**Q1 用户拍板 B：排除 skipped**）；更新 docstring 的优先级表（五档 → 六档）。
- [x] 1.2 **（Q2 用户拍板 (b)）** `_source_collection` 读出上游产出的返回点旁加 `_consumed_edges.add((<被读节点 id>, node.id))`——与 #197 在 `_route_verdict` 的修法同构（旁加，`_mark_consumed` 本体不动）。
- [x] 1.3 回归确认：`_mark_consumed`/`_consumed_run_ids` 本体不动；`useful_runs`/`redundancy` 逐位不变（C5 口径零漂移）。

## 2. 后端测试

- [x] 2.1 新增「foreach 用字面 items → `scan→fan` 判 `satisfied`」（**实跑**复现 issue 场景）。
- [x] 2.2 新增「`required=False` 的未消费边仍 `inactive`」。
- [x] 2.3 新增「目标仍 `pending` → `ready`（不是 `satisfied`）」。
- [x] 2.5 新增「**目标 `skipped` → `inactive`**（不是 `satisfied`）」（Q1 判据的回归）。
- [x] 2.6 新增「**动态 foreach（`source:`）读上游 → 该边判 `passed`**」（Q2 记账修复的回归，实跑断言 `_consumed_edges` 非空）。
- [x] 2.4 更新 `EDGE_STATUS_TIERS` frozenset 加 `satisfied`；既有五档判据回归全绿。

## 3. 前端：词表 + 图例

- [x] 3.1 `web/static/workflow_graph.js` 的 `EDGE_STYLES` 加 `satisfied: { color: '#86efac', opacity: 0.55, width: 1.6, dash: [] }`。
- [x] 3.2 `EDGE_STATUS_TEXT` 加 `satisfied: '依赖已满足，但产出未被下游读取'`（图例内容由此自动跟随，无需改图例代码）。
- [x] 3.3 前端纯函数单测：`EDGE_STYLES`/图例覆盖六档；`satisfied` 与 `inactive`、`passed` 在明度或线宽上可分辨（灰度第二重编码）。
- [x] 3.4 **更新那条会红的既有前端断言**（grill 实测点名）：`tests/web_tests/test_workflow_graph_js.py:94-96` 的 `assert set(styles) == {五档}` 加 `satisfied`（改名 / 改断言为六档）。（图例那条是动态断言、会自动跟随，**不会**红。）

## 4. 测试与收尾

- [x] 4.1 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过。
- [x] 4.2 同步 current spec：把 spec delta（MODIFIED 两条 Requirement：边五档 → 六档）合入 `openspec/specs/web-ui/spec.md`，并写受保护路径的结构化解释事件。
- [x] 4.3 文档影响检查：`docs/openspec-change-backlog.md`（登记/归档时清理）、相关入口文档。
- [x] 4.4 独立审阅闭环（`/review-loop`）PASS + review manifest。
- [x] 4.5 归档 change 到 `openspec/changes/archive/<date>-workflow-gate-only-edge-status/`，清 backlog，建 PR。
