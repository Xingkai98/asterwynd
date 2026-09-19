# Proposal: 循环图的契约对模型可见（workflow-cycle-contract）

## Change Type

- primary: feature
- secondary:
  - multi-agent-collaboration

## Why

用户在 session `0a94250da7bf` 实测时，模型自行建了一张**回边环**的图，结果空转到撞 `max_routes`，**图和人都不知道发生了什么**（issue #219）。用户原话：**「应该让给模型的提示更准确，能够指引他创建出正确的图」**。

排查确认：这不是模型能力问题，而是**循环的契约从未被写下来**。`DeclareWorkflow` 的工具描述关于循环**只有一句**：

> "Cycles are only allowed through a route node."

而实际生效的隐式契约有四条，全部只能靠踩坑发现：

| 隐式契约 | 实现位置 | 不知道的后果 |
|---|---|---|
| `max_routes` **默认 1**，且**只能在 spec 里逐节点配**（config 层无此字段） | `workflow.py:145` / `:501` | 想多轮循环不写就 1 轮撞线 |
| 回边应当**从 route 出发**（route 出边是控制边，不参与数据门控） | `workflow.py:243-245` | 从非 route 出发的回边是**数据边**，`required` 默认 true → **双向等待死锁** |
| 循环体里**必须有个「会变」的节点**（subagent / llm-aggregate） | 环内无产出节点 → 每轮读同一份空串 | **空转环**，永远转不出去 |
| `max_routes` 是**节点级、跨轮累加、不重置** | `scheduler.py:1615` | 语义与「最多循环几轮」的直觉不同 |

用户那张图**同时踩了两个坑**（回边是数据边 + 环内无产出节点），而运行期反馈（`max_routes exceeded`）**不足以让模型自己纠正**——它看不出「为什么转不出去」。

## What Changes

**A. 提示面：把循环契约写进 `DeclareWorkflow` 描述**

补一个「循环（cycle）」小节，讲清：`max_routes` 的默认值与配置位置、回边应从 route 出发（否则是数据边会门控）、环内必须有产生产出的节点、`max_routes` 的累加语义。附一个最小正确示例与一个反例。

**B. 声明期校验：在 `DeclareWorkflow` 就拦下必然失败的环**

两条判据都能**静态判定**（无需运行），在 `workflow.py` 的校验阶段（与既有 `_validate_cycles` 同层）执行：

| 判据 | 检测 | 为什么必然失败 |
|---|---|---|
| **空转环** | 环（SCC）内**没有任何产出节点**（`subagent` 或 `aggregate(strategy="llm")`） | 环内没有任何东西会变化 → 每轮读到同样的输入 → 退出条件永不成立，只能烧到 `max_routes` |
| **回边死锁** | `route` 节点有**来自同环内**的 `required` 数据入边 | route 等该上游终态、该上游等 route 的激活 → **双向等待**，一个节点都跑不起来 |

**为什么这两条没有误报**：

- 空转环：纯逻辑环即使靠 `max_routes` 停下，也只是把同一份计算重复 N 次——没有合法用途
- 回边死锁：`required` 的语义是「必须等上游终态」，而环内上游的启动又依赖 route 的激活，二者互等是**定义上的**死锁；官方 `peer-review` pattern 的回边是**控制边**（`gate`(route) → `producer`），天然不受影响

**C. 运行期诊断补一句可操作的因果**（可选，随 A/B 一起）

`graph_recursion_exceeded` 且 `reason == "max_routes"` 时，`diagnostics` 补一句**为什么转不出去**（环内无产出 / 回边死锁），而不只是「超过上限 N」。这是 A/B 的兜底——声明期拦不住的（例如模型绕过校验的路径），运行期还能自己纠正。

## Non-Goals

- **不修运行期行为**：#217 / #218 / #220 已由 `workflow-terminal-honesty` 修复（图级终态四档 / 因由如实 / 回边不清空发起者）。本 change 只改**声明期**与**提示面**。
- **不改 `max_routes` 的语义**（节点级、跨轮累加、不重置）：只**讲清楚**它，不改它。
- **不做「自动修复」**（例如自动把回边改成 `required: false`）：静默改用户声明的图比报错更危险——模型应显式写对它。
- **不覆盖 `foreach` 的 `source` 环**：既有的 `_validate_foreach_source_cycles` 已处理。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/subagent/workflow.py` | 新增两条声明期校验（复用既有 `_strongly_connected_components` Tarjan） | **中**（拒绝路径：会让此前能声明的图报错） |
| `agent/tools/builtin/subagents.py` | `DeclareWorkflow` 描述补循环小节 | 低（纯文案） |
| `agent/subagent/scheduler.py` | （可选 C）`diagnostics` 补因果 | 低 |

**契约影响（对外）**

- **声明期新增拒绝路径**：此前能通过 `DeclareWorkflow` 的「空转环 / 回边死锁」图会**变成声明期报错**。这是**有意的**（那些图必然失败），但属行为变更，需在 spec 里写明。
- 官方 4 个 pattern（`orchestrator-worker` / `peer-review` / `hierarchical` / `bidding`）**必须全部仍能声明通过**——`peer-review` 的回边是控制边，不受影响；需测试锁定。

**测试影响**

- 新增：空转环被拒 / 回边死锁被拒 / 官方 4 pattern 全部仍通过
- 回归：`tests/agent/subagent/`（重点 `test_workflow_*.py`、DSL 声明与校验相关）
- **变异验证**：每条新校验都要能被「改坏实现」杀死

**文档影响**

- `openspec/specs/multi-agent-collaboration/spec.md`（ADDED：循环图形的声明期校验）
- `docs/openspec-change-backlog.md`（登记 + 完成后移除）
- 关键词扫描 `docs/`、`AGENTS.md`、`CONTEXT.md` 中涉及 workflow DSL / 循环的段落

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 新增**声明期拒绝路径**（对外行为变更）+ 提示面契约，属 spec 可见改动；「循环必需可终止条件」是工作流引擎的经典静态检查，业界有明确先例可对标。

- research questions:
  1. 业界工作流引擎是否在**声明期**静态检查循环的可终止性？
  2. 它们如何表达「这个循环转不出去」？
  3. 提示面如何让 LLM 一次写对循环？

- findings:
  - **Airflow**：DAG 是**声明期**强约束——有环直接拒绝（`AirflowDagCycleException`），根本不允许循环；要重复只能用 `max_active_runs`/回填等外层机制。**不适用**本项目的「有限循环」需求（本项目的 route 回边是**有意支持**的），但它印证了「拓扑错误应在声明期拦」这一方向。
  - **Argo Workflows**：`dag` 模板**声明期拒绝环**；但它提供 `template` 递归 + `when` 条件实现循环，且**限制并发递归深度**（`MaxRecursionDepth`）。其文档明确警告无界递归，属**运行期**护栏而非声明期可终止性证明。
  - **Temporal**：用**代码**写工作流（`while` 循环天然可读），因此不做「循环可终止性」静态检查——语言的 `while` 已经表达了意图。它对本项目的启示是**提示面**：Temporal 的教程一律用「循环体内必须推进某个状态」的写法示范，即**契约靠示例传达**。
  - **LangGraph**：显式建图的循环需要用户自己保证退出条件，但它在**文档与示例**里把「循环体的状态必须更新」讲成硬要求（否则 `recursion_limit` 兜底），与本项目 `max_routes` 的角色一致。

- design impact:
  - **没有任何一家在声明期做「循环可终止性」的形式化证明**——因为一般情形不可判定。但本项目的情形**有可判定的特例**：环内无产出节点 → 状态空间不变化 → 必然不可终止。**只做这个特例**（可判定、无误报），不做一般性证明。
  - **提示面靠「正确示例 + 反例」而不是靠规则罗列**（TemporalLangGraph 的共同做法）：工具描述里给一段最小的可终止循环（subagent 在环内）+ 一段反例（全是 aggregate），比列 4 条规则更易被模型遵守。
  - **拒绝而非警告**：Argo/Airflow 对拓扑错误都是**拒绝**不是警告。本 change 的两条判据无误报，故同样选择拒绝——但这一点**列为 grill Open Question**，因为它是唯一的对外行为变更。
  - 本地参考仓库不可用（工作区无 `.dev/reference-repos.txt`），findings 全部来自业界调研（官方文档/源码/issue）。
