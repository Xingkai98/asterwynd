# Proposal: 循环图的契约对模型可见（workflow-cycle-contract）

## Change Type

- primary: feature
- secondary:
  - multi-agent-collaboration

## Why

用户在 session `0a94250da7bf` 实测时，模型自行建了一张**回边环**的图，结果**图报成功、环内节点一个都没跑**，
**图和人都不知道发生了什么**（issue #219）。用户原话：**「应该让给模型的提示更准确，能够指引他创建出正确的图」**。

排查确认：这不是模型能力问题，而是**循环的契约从未被写下来**。`DeclareWorkflow` 的工具描述关于循环**只有一句**：

> "Cycles are only allowed through a route node."

而实际生效的隐式契约有四条，全部只能靠踩坑发现：

| 隐式契约 | 实现位置 | 不知道的后果 |
|---|---|---|
| `max_routes` **默认 1**，且**只能在 spec 里逐节点配**（config 层无此字段） | `workflow.py::WorkflowNode.max_routes` / `workflow.py` 的 `_parse_max_routes` 调用点 | 想多轮循环不写就 1 轮撞线 |
| 回边应当**从 route 出发**（route 出边是控制边，不参与数据门控） | `workflow.py::ExecutionPlan.is_control_edge` | 从非 route 出发的回边是**数据边**，`required` 默认 true → 门控住下游 |
| **环里必须有个节点能先跑起来**，且它不能反过来等环里的节点 | `scheduler.py::_ready_nodes` 的 `activations` 检查 + `_data_deps_satisfied` | 环内全部节点互等 → 一个都跑不起来，图静默收敛 |
| `max_routes` 是**节点级、跨轮累加、不重置** | `scheduler.py::_dispatch` 的 `_route_counts` 闸门 + `scheduler.py::_execute_route` 的计数点 | 语义与「最多循环几轮」的直觉不同 |

用户那张图同时踩了两个坑（环内 `required` 数据边互等 + 环内没有能自启动的节点），而运行期反馈
（图级 `status = completed`、节点 `blocked`、`diagnostics` 为空）**不足以让模型自己纠正**——它看不出「为什么转不出去」。

> **口径修正（grill 实测）**：归档 diagnosis 的 `#220` 最小 spec（`cycle_gate` + `body` + 回边
> `required:false`）**没有**烧到 `max_routes`——它 `route_counts=2`、`body` 全程 `blocked`、图报
> `completed`，一圈都没转完就收敛了。真正「空转到撞 `max_routes`」需要**环体是 entry** 这个前提，
> 而那是初版 proposal/design 都没写的条件。本 change 的判据不依赖区分这两种表现——它拦的是它们的
> 共同根因：**环内没有任何节点能先跑起来**。

## What Changes

**A. 提示面：把循环契约写进 `DeclareWorkflow` 描述**

补一个「循环（cycle）」小节，讲清：**环里必须有个节点先跑起来、且它不能反过来等环里的节点**、回边应从
route 出发（否则是数据边、默认门控，须写 `"required": false`）、`max_routes` 的默认值与配置位置与累加语义。
附一个**最小正确示例**与一个**最小反例**。

**B. 声明期校验：在 `DeclareWorkflow` 就拦下必然停滞的环**

判据只有一条，**静态可判定**（无需运行），在 `workflow.py` 的校验阶段（与既有 `_validate_cycles` 同层）执行：

| 判据 | 检测 | 为什么必然失败 |
|---|---|---|
| **环不能启动** | 环（SCC）内**没有任何节点可派发** | 派发规则单调且只看结构：可派发集合由「required 数据源可派发 + entry/控制语义 + best_effort 截止」唯一决定。集合为空 ⇒ 环内零节点会被派发 ⇒ 图停滞 |

**「可派发」的定义**（复刻 `scheduler.py::_ready_nodes` / `_data_deps_satisfied` / `_is_entry` /
`_execute_route` / `_fire_best_effort_deadlines`，取不动点）：节点可派发 ⟺ **常规路径**（全部
`required` 数据入边源头可派发，**且**它是 `entry`｜它没有控制入边｜存在可派发的 route 能激活它——
激活来源含 `cases[].to`/`default` 的目标）**或** **best_effort 截止路径**（`join == "best_effort"`
且声明了 `deadline_s` 的聚合，其数据上游可派发——截止到点后调度器直接放行它）。

**为什么它不会误报**：取的是真实可派发节点集的**超集**——多算一个节点只会漏报（少拒一张坏图），
少算一个才会误报（拒掉一张能跑的图）。每条真实派发路径都必须复刻进去，否则方向就反了
（首轮独立审阅正是在这里抓到两个误报：漏掉 `deadline_fired` 短路与 `cases`/`default` 激活）。

**为什么它替换了初版的「环内无产出节点」判据**：实测证明产出节点**既非必要也非充分**——环里有
**两个** `subagent` 但 `b`/`c` 互相 `required` 等待时，按初版判据通过，实跑仍双双永久 `blocked`、
图报 `completed`、`diagnostics` 为空。而且 `route` 其实**产出**非空 `summary`（`_node_output` 末行
`return state.summary or None`），`aggregate(strategy="collect")` 超预算时也会调 LLM——
「环内没有 LLM 调用」这个论据本身就不成立。

**C. 运行期诊断不再需要单独补因果**（初版 C 取消）

初版计划在 `graph_recursion_exceeded` 的 `diagnostics` 里补「为什么转不出去」。既然 B 已在声明期拦下
全部可静态判定的停滞环，且 `workflow-terminal-honesty` 已让运行期 `blocked` 节点如实报出
「入边互相等待」，本条价值不足以独立成项——留作观察项，不在本 change 实现。

## Non-Goals

- **不修运行期行为**：#217 / #218 / #220 已由 `workflow-terminal-honesty` 修复（图级终态四档 / 因由如实 / 回边不清空发起者）。本 change 只改**声明期**与**提示面**。
- **不改 `max_routes` 的语义**（节点级、跨轮累加、不重置）：只**讲清楚**它，不改它。
- **不做「自动修复」**（例如自动把回边改成 `required: false`）：静默改用户声明的图比报错更危险——模型应显式写对它。
- **不做一般性可终止性证明**（不可判定）：只做「环能不能启动」这一个可判定特例。
- **不覆盖 `foreach` 的 `source` 环**：既有的 `_validate_foreach_source_cycles` 已处理。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/subagent/workflow.py` | 新增声明期可启动性校验（复用既有 `_strongly_connected_components` Tarjan）+ `WorkflowCycleError` | **中**（拒绝路径：会让此前能声明的图报错） |
| `agent/tools/builtin/subagents.py` | `DeclareWorkflow` 描述补循环小节 + `_invalid_spec` 对本类错误给指向性 hint | 低（文案 + 分支） |
| `tests/agent/subagent/test_terminal_honesty.py` | 改为绕过声明期校验、直接构造 `WorkflowSpec`（保住运行期诊断覆盖） | 低 |

**契约影响（对外）**

- **声明期新增拒绝路径**：此前能通过 `DeclareWorkflow` 的「永远跑不起来」的环会**变成声明期报错**。
  这是**有意的**（那些图必然停滞），但属行为变更，已在 spec 写明。用户已就「拒绝 vs 警告」拍板选**拒绝**，
  并要求**报错信息必须足以让模型自己改对**（`_invalid_spec` 返回体里没有 `workflow_id`，`reason` + `hint`
  是唯一信息来源）。
- 官方 4 个 pattern（`orchestrator-worker` / `peer-review` / `hierarchical` / `bidding`）**必须全部仍能声明通过**
  ——需测试锁定。**初版 D2 判据会拒绝 `peer-review`**（实测：`reviewer→gate` 是 required 数据边且与 route
  同 SCC），这正是判据重写的直接原因。

**测试影响**

- 新增：环不能启动被拒（含 #219 形态与「环内有 subagent 但互等」形态）/ 能启动的环通过 / 官方 4 pattern 全部仍通过 /
  报错三要素 / best_effort 环与 route 无声明边激活**不得误拒**（首轮审阅的 blocker+major）
- 改造：`test_terminal_honesty.py` 的 `_deadlock_spec()` 用例绕过声明期校验
- 回归：`tests/agent/subagent/`（重点 `test_workflow_*.py`、`test_pattern_*.py`、DSL 声明与校验相关）
- **变异验证**：每条新校验都要能被「改坏实现」杀死。**初版规划的「`data_incoming` → `incoming`」是恒等变换
  （实测对 `peer-review` 结果完全相同），已换成「删掉 `required` 判断」等有区分度的变异**

**文档影响**

- `openspec/specs/multi-agent-collaboration/spec.md`（ADDED：循环图形的声明期校验 + 描述暴露循环契约）
- `docs/openspec-change-backlog.md`（登记 + 完成后移除）
- 关键词扫描 `docs/`、`AGENTS.md`、`CONTEXT.md` 中涉及 workflow DSL / 循环的段落

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 新增**声明期拒绝路径**（对外行为变更）+ 提示面契约，属 spec 可见改动；「循环必须有可启动条件」是工作流引擎的经典静态检查，业界有明确先例可对标。

- research questions:
  1. 业界工作流引擎是否在**声明期**静态检查循环的可终止性？
  2. 它们如何表达「这个循环转不出去」？
  3. 提示面如何让 LLM 一次写对循环？

- findings:
  - **Airflow**：DAG 是**声明期**强约束——有环直接拒绝（`AirflowDagCycleException`），根本不允许循环；要重复只能用 `max_active_runs`/回填等外层机制。**不适用**本项目的「有限循环」需求（本项目的 route 回边是**有意支持**的），但它印证了「拓扑错误应在声明期拦」这一方向。
  - **Argo Workflows**：`dag` 模板**声明期拒绝环**；但它提供 `template` 递归 + `when` 条件实现循环，且**限制并发递归深度**（`MaxRecursionDepth`）。其文档明确警告无界递归，属**运行期**护栏而非声明期可终止性证明。
  - **Temporal**：用**代码**写工作流（`while` 循环天然可读），因此不做「循环可终止性」静态检查——语言的 `while` 已经表达了意图。它对本项目的启示是**提示面**：Temporal 的教程一律用「循环体内必须推进某个状态」的写法示范，即**契约靠示例传达**。
  - **LangGraph**：显式建图的循环需要用户自己保证退出条件，但它在**文档与示例**里把「循环体的状态必须更新」讲成硬要求（否则 `recursion_limit` 兜底），与本项目 `max_routes` 的角色一致。
  - 本地参考仓库不可用（工作区无 `.dev/reference-repos.txt`），findings 全部来自业界调研（官方文档/源码/issue）。

- design impact:
  - **没有任何一家在声明期做「循环可终止性」的形式化证明**——因为一般情形不可判定。但本项目的情形**有可判定的特例**：环内没有任何节点能先跑起来 ⇒ 状态空间不推进会一轮。**只做这个特例**（可判定、实测零误报），不做一般性证明。
  - **提示面靠「正确示例 + 反例」而不是靠规则罗列**（Temporal / LangGraph 的共同做法）：工具描述里给一段最小的**能启动**循环 + 一段反例（环内全在互等），比列 4 条规则更易被模型遵守。
  - **拒绝而非警告**：Argo / Airflow 对拓扑错误都是**拒绝**不是警告。用户已就此拍板选拒绝（grill Q3），并要求拒绝时必须给出可操作的修法。
  - **判据的重写来自独立 grill 的实测反证**：初版「环内无产出节点」被实测证伪（漏报 + 论据不成立），改为复刻调度器派发语义的不动点（过近似，覆盖常规派发与 best_effort 截止两条路径）；初版「route 有同环内 required 数据入边」会误杀官方 `peer-review`，其诊断价值并入不动点判据的报错文案。
