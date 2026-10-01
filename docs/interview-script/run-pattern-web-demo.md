# 在 Web 上实测多 Agent 编排模板（RunWorkflow template）

> 面试讲到多 Agent 时，"我真在 web 上跑过 4 种内置模板"比纯讲代码更有说服力。
> 本指南基于源码核实：web 会话 `expose_subagent_tools=True`（`web/session.py`），
> 模板入口是 `RunWorkflow` 的 `template` 入参（`agent/tools/builtin/subagents.py`）。
>
> **变化说明**：内建模板原由独立工具 `RunPattern` 驱动；该工具已退役，模板并入统一
> Workflow 入口 `RunWorkflow`（`template=…` + `task` + `params`），与手写 spec
> （`RunWorkflow(spec=…)`）共存于同一工具、同一返回形状。

## 0. 前置

```bash
cd ~/code/asterwynd
cp .env.example .env   # 填 API key（OpenAI 或 Anthropic）
uv sync --extra dev
```

## 1. 启动（bypass 模式：命令免审批，试起来最顺）

```bash
uv run asterwynd web --port 8000 --mode bypass
```

浏览器打开 `http://localhost:8000`。

> 为什么 bypass？BYPASS profile `auto_approve_max_risk=HIGH`，Bash 等高风险工具自动放行不弹审批框（tool_permissions.py）。子 agent 想跑命令时不会被单槽审批卡住。
> 注意：BYPASS 会跳过审批，仅限本地安全环境试用。

## 2. 用自然语言驱动模板

`RunWorkflow` 的模板入参：

```
template: "orchestrator-worker" | "peer-review" | "hierarchical" | "bidding"
task:     给参与子 agent 的目标（template 路径必填）
params:   workers/teams/proposers 数量、max_rounds、worker_max_tokens、worker_max_time_s
```

> 也可以直接给整张拓扑：`RunWorkflow(spec=…)`。两者**二选一**，工具会结构化拒绝混用。

### ① orchestrator-worker（扇出并行）

> 用 orchestrator-worker 模板，开 3 个 worker，让他们各自分析这个项目里有哪些测试没有覆盖到，汇总给我

### ② peer-review（迭代批判）

> 用 peer-review 模板，让 producer 写一份 README 的改进方案，reviewer 审到通过为止，max_rounds 3

### ③ hierarchical（嵌套 manager）

> 用 hierarchical 模板，开 2 个 manager 子团队，分别审查 agent/loop.py 和 agent/memory/ 的代码质量，manager 可以自己再派 worker

### ④ bidding（独立方案 + 评选）

> 用 bidding 模板，3 个 proposer 各自给一个方案：怎么优化这个项目的测试运行速度，再让 selector 选最好的

## 3. 界面上看什么

- **流式输出**：子 agent 输出、Workflow 运行态图逐字显示。
- **有界信封**：模板跑完返回的是**有界投影**（`parent_envelope()`），字段要点：
  - `status`：`completed` / `completed_with_failures` / `failed` / `cancelled` / `budget_exceeded` / `graph_recursion_exceeded` 等。
  - `nodes[]`：每个节点的有界摘要（`{id, kind, status, runs, items, summary, reason}`）。
  - `completed` / `failed`：**数的是 run，不是 subagent**（一个节点跑两轮算两条）。
  - `root_result_ref` / `GetWorkflow(detail='nodes')`：按 ref 读回全文；foreach 节点还有 `item_refs`（每个展开项的成功项 ref）。
  - **不再有** pattern 专属扁平字段（旧 `RunPattern` 的 `workers` / `selected` / `selector` / `summary` / `bus`）。

## 4. 如果 agent 不主动用模板

- 直接点名："调用 RunWorkflow，template=peer-review，task=...，params={max_rounds: 3}"
- 确认工具可见：问它"你有哪些子 agent 工具？"——正常情况下 `RunWorkflow` / `StartWorkflow` / `DeclareWorkflow` / `GetWorkflow` / `CancelWorkflow` / `DryRunWorkflow` 与资产工具（`ListWorkflowAssets` / `GetWorkflowAsset` / `SaveWorkflowAsset` / `RunWorkflowAsset`）都在（`RunPattern` 已退役）。其中 `DryRunWorkflow` 是零 token 模拟执行（不调模型、不写盘），用来在声明前预演拓扑与数据流。

## 5. 常见坑

- **护栏**：并发上限、嵌套深度上限（`manager.py`），超了报错——这是设计好的保护。
- **`max_rounds` 是期望轮数**：实际轮数受图级 `recursion_limit` 约束，可能显著少于声明值；被截断时 `graph_recursion_exceeded` 的诊断会给出 `declared_max_rounds` / `rounds_actually_run` / `limit_source`，据此调整而不是只看"超了递归上限"。
- **fan-out 计数有上界**：`workers`/`teams`/`proposers` 超过 foreach 节点的 `max_items`（默认 20）会被结构化拒绝——既防静默截断，也防编译期造出上万个 item 对象。
- **bidding 的 selector 只看紧凑摘要**：想让 selector 看完整方案，让 proposer 把方案写文件、selector 读 artifact。
- **单槽审批**：若不用 bypass，一次只能一个 pending 审批，别同时等两个。
- **BYPASS 仅本地试用**：真实安全实践请回 build 模式 + 审批。

## 6. 面试讲法参考

试完可以这样说："我在 web 上实测过 4 种内置模板。orchestrator-worker 是并行扇出最快；peer-review 会迭代到 APPROVED 为止，能看到 producer 被 critique 回喂后的改进；bidding 里我故意让 proposer 把方案写文件，因为 selector 只看摘要、读 artifact 拿全文——这是 drop-oldest 会丢投标的设计取舍。预算 kill 我也触发过：给 worker 设 max_tokens 超限，能看到它先写检查点再标记 budget_exceeded，是可恢复的。"
