# Proposal: 纯门控边的独立状态（workflow-gate-only-edge-status）

关联跟踪 issue：[#207](https://github.com/Xingkai98/asterwynd/issues/207)。

## Change Type

- primary: feature
- secondary:
  - web-ui

## Why

用户在 #197 实测（真 LLM 跑 workflow + 手机端看图）时发现：`scan→fan` 这条边**跑完后显示为灰色**，看起来像条死线。

排查确认**不是渲染 bug，是边语义的系统性缺口**：

| 边 | 执行顺序 | 数据流 | 现显示 |
|---|---|---|---|
| `scan→fan` | ✅ 门控了 fan 启动 | ❌ fan 用**字面 items**，没读 scan 产出 | 灰 |
| `scan→fragile` | ✅ 门控了 fragile 启动 | ✅ 读了 scan 产出 | 绿 |

两条边在「执行顺序」维度上**完全一样**（都是 `required` 依赖，`_data_deps_satisfied` 都要求上游终态才放行下游），颜色却不同——因为颜色量的是「数据有没有被消费」。

根因：边五档的 `inactive`（**兜底档**）现在同时承载两种完全不同的语义：

1. 边没意义 / 从未参与 → 灰 ✅ 对
2. 边**起了作用**（门控了下游派发），只是上游产出未被下游读取 → 灰 ❌ **误导**

而 `passed` 需要「数据边被下游消费过」（`_consumed_edges` 记账），纯门控边永远命中不了它，最终落兜底 `inactive`。

**这不是 #197 引入的**（五档边语义是 #190 的决策），但任何「只起门控作用、不传数据」的边都会中招——例如「A 先建目录、B 才写文件」这类只有顺序意义的依赖，跑完都显示为灰，用户会问「这条线到底算不算数」。

## What Changes

新增**第 6 档边状态 `satisfied`**（依赖已满足但产出未被消费）：

- **判据**：`required` 边 + 未被消费 + 源 `completed` + 目标**已越过 pending**（即目标确实被这条依赖放行过）。
- **语义**：这条边**起了门控作用**，但上游产出没有流过去——所以它既不是「死线」（`inactive`），也不是「数据流」（`passed`）。
- **视觉**：**淡绿 + 细实线**——与 `passed`（深绿、粗）同色系以示「都是起作用的边」，靠明度与粗细区分「有数据流 / 只有顺序」；与 `inactive`（暗灰、最细）明确拉开。
- **图例**：自动跟随（图例内容从 `EDGE_STYLES`/`EDGE_STATUS_TEXT` 同源生成），新增一行人话「依赖已满足，但产出未被下游读取」。

**明确的 Non-Goal**：**不改** `passed` 的语义。`passed` 仍然是「上游产出被下游读走」——C5 的冗余度指标（`_consumed_run_ids`/`useful_runs`/`redundancy`）依赖这个信号，把绿色改成「依赖已满足」会丢掉「产出有没有被用」这一层观测（这是被否的方案 B）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `web-ui`: 边状态从**五档**（inactive / ready / active / passed / blocked）扩展为**六档**（+ `satisfied`），图例与边渲染同步。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 常规功能增强（在已有的边状态词表上补一档 + 视觉区分），属「成熟模式的局部应用」——依赖图里区分「依赖已满足」与「数据已流动」是工作流引擎的常见表达，非架构级改造，也没引入新框架/新协议。
- findings:
  - **业界对本问题的处理**（#197 的调研已覆盖 Airflow / Argo / Temporal / Prefect / Dagster / n8n / Tekton / Step Functions 八家）：与本 change 最相关的是 **Argo Workflows 的 `depends` 语义**——它把「依赖满足与否」与「是否真的传了数据」分开表达；以及 **Airflow 的 trigger rule 日志**（`dependency 'Trigger Rule' PASSED: False, upstream_states=...`），它明确区分「依赖检查通过」与「任务是否真的执行」。本仓库的 `required` 边正是「依赖检查」这一层，而 `_consumed_edges` 是「数据是否真的被读走」那一层——两者本就是不同事实，理应有不同的视觉档位。
  - **为什么不用「边捆绑」等图形学方案**：#197 已明确排除（本场景同对节点重叠边只有 2–4 条，捆绑只会把信息藏得更深）。本 change 是**语义层**的补档，不是几何层。
  - **不采纳的替代**：把 `passed` 语义改成「依赖已满足」（会丢 C5 冗余度信号）；只改图例文案（治标不治本，用户仍得先看文档才知道灰线可能是有意义的）。
- design impact: 见 design.md 的 D1（判据与优先级）、D2（视觉编码）、D3（与 C5 指标的隔离）。

## Impact Analysis

- **能力域**: `web-ui`（边状态词表 + 图例 + 边渲染）。
- **代码**:
  - `agent/subagent/scheduler.py` 的 `_edge_status()`：优先级链加一档（不改既有档的判据）；
  - `web/static/workflow_graph.js` 的 `EDGE_STYLES` + `EDGE_STATUS_TEXT`：各加一项（图例自动跟随）；
  - **不改** `_consumed_edges`/`_mark_consumed`/`_consumed_run_ids`（C5 口径零漂移）。
- **测试**: 后端 `_edge_status` 的档位单测（新增 `satisfied` + 既有五档回归）；前端纯函数单测（`EDGE_STYLES` 覆盖六档、图例覆盖六档、`satisfied` 与 `inactive`/`passed` 视觉可分辨）。
- **文档**: `docs/openspec-change-backlog.md`（登记 change）；issue #207 跟踪；收尾同步 `openspec/specs/web-ui/spec.md`（两处「五档」→「六档」）。
- **流程（process）**: 独立 change，走 OpenSpec 全套（propose → grill → 独立 worktree TDD → review-loop → archive）；分支 `<change-id>/2026-09-18`。
- **风险面**: 边状态是 spec 里明文列举的词表（`openspec/specs/web-ui/spec.md` 两处），改动必须同步 spec delta，否则 spec 与实现漂移；另需确认前端既有测试里对「五档」的精确断言会红（有意为之）。
