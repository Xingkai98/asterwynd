# Proposal: workflow 节点 mode 钳制基准修正（fix-issue-255-mode-ceiling）

关联跟踪 issue：[#255](https://github.com/Xingkai98/asterwynd/issues/255)（【bug】workflow 节点 mode 钳制基准错误：共享 provider 被子 agent 构造覆盖，导致 fail-open 与静默降级）。

## Change Type

- primary: bugfix
- secondary: []

## Why

Workflow DSL 的节点可以声明 `mode`（`build` / `read_only` / `plan`，`agent/subagent/workflow.py:_parse_node`），设计意图是「节点的**有效** mode 不得超过当前会话的 mode」，由 `SubAgentManager._clamp_mode`（`agent/subagent/manager.py:1588`）按权限等级取小实现。

**钳制的形状是对的，输入是错的。** `_clamp_mode` 读的 `self.parent_mode_provider` 是 manager 上的**共享实例字段**（`manager.py:454`），其唯一写入点是 `AgentLoop.__init__` 里的 `configure_runtime(...)`（`agent/loop.py:153-155`）。子 agent 的 loop 复用同一个 manager（`manager.py:1303`，`subagent_manager=self`），于是**每构造一个子 agent loop 都会无条件覆盖这个字段**。「当前会话允许的能力面」因此退化成「**最后被构造的那个 loop 的 mode**」，而它与发起运行的那次会话无关。

后果分三类（本 change 立项阶段以独立探针实测复现，见 `diagnosis.md`）：

- **fail-open（安全方向）**：BUILD 会话跑过一张图后，用户把会话切到 `read_only`（`runtime_state.set_mode` 只改会话自身状态，**不重新调** `configure_runtime`）→ provider 停在 BUILD → 声明 `mode: build` 的节点被授予 **BUILD**。只读会话被授予写权限。
- **静默降级（正确性方向）**：BUILD 会话顺序跑两张图，前一张含只读节点 → 后一张的 `build` 节点被降级为 `read_only`。用户**从未切换过模式**，且没有任何 diagnostics。
- **并发结构性错误**：同一张图并行展开 `A(build)` / `B(read_only)`，两个节点读同一个标量；构造序 `('A','B')` → `READ_ONLY`、`('B','A')` → `BUILD`。**不可能同时正确。**

测试盲区：`rg 'parent_mode_provider|_clamp_mode' tests/` **零命中**——该钳制从未被测试覆盖。既有 `test_create_subagent_*` 系列走的是 `parent_mode=` 构造参数（静态、不被覆盖），绕过了出问题的那条路径。

**为什么现在做**：本 change 是 `workflow-asset-persistence`（issue #245）的**前置阻塞项**。#245 的资产功能以「保留显式 mode」为卖点，并承诺「运行前列出将以什么 mode 运行的节点」——在基准错误的前提下，那个批准面列的是**错的基准**，等于给出不可信的批准面。用户已确认执行顺序 **#255 → #245 → #246**。

## What Changes

- **新增会话 mode 上限通道**：在 `agent/subagent/context.py` 增加一个 `ContextVar`（与既有 `workflow_id` / `node_id` / `graph_distance` / `bus` 同机制），承载「当前执行上下文的 mode 上限」。这是 #245 Q11 明确要求由 #255 提供的、**scheduler 可读的会话 mode 通道**。
- **`_clamp_mode` 改读执行上下文**：钳制基准从共享 `parent_mode_provider` 改为该 `ContextVar`（无值时回落既有静态 `parent_mode` 构造参数，保持既有行为与兜底保守性）。
- **会话上限在会话 run 起点快照**：会话 loop 在自己的 run 起点把上限快照为当时的会话 mode；运行途中切换会话 mode 不影响本次 run 已确定的上限（快照语义）。
- **节点有效 mode 在派发点确定并随上下文传播**：调度器在派发点 `_launch_run` 把上限收紧为 `min(节点声明 mode, 当前上限)`（`set` + `finally reset`，与既有 4 个身份 contextvar 并列），使**节点自身**被正确钳制，且其**子孙**经既有 `copy_context()` 继承该节点的**有效** mode（逐层收紧）。
- **退役共享 `parent_mode_provider`**：删除该字段、`configure_runtime` 的对应形参、以及 `AgentLoop.__init__` 里的 `lambda`，消除「共享可变标量被并发覆盖」这一根因面。
- **新增回归测试**：覆盖 fail-open、静默降级、并发（含构造序反转）、嵌套继承、快照、跨图污染六个方向，每项配「合法路径必须成功」的对照用例（防「无差别压低」的假修复）。

## Capabilities

### New Capabilities

（无新增能力域。）

### Modified Capabilities

- `subagents`: 新增 Requirement「子 agent mode 上限按执行上下文继承」。子 agent 的有效 mode SHALL 由**当前执行上下文的上限**（而非任何跨 run 共享、会被并发构造覆盖的可变状态）推导；同一路径 SHALL 在并发节点与跨 mode 切换下保持一致。
- `multi-agent-collaboration`: 新增 Requirement「workflow 节点 mode 上限语义」。节点有效 mode SHALL 为 `min(节点声明 mode, 当前会话上限)`；会话上限 SHALL 在 run 起点快照（运行途中切换不影响本次 run）；嵌套派发 SHALL 逐层收紧到父节点的**有效** mode；并发节点 SHALL 互不覆盖；系统 SHALL 提供一个 scheduler 可读的会话上限通道。

## Impact

### 影响的能力域

`subagents`（子 agent mode 钳制基准）与 `multi-agent-collaboration`（workflow 节点 mode 上限语义）。

### 影响的代码

- `agent/subagent/context.py`：新增 mode 上限 `ContextVar` 及其 get/set/reset 访问器。
- `agent/subagent/manager.py`：`_clamp_mode` 改读上下文上限；删除 `parent_mode_provider` 字段与 `configure_runtime` 对应形参；`_parent_mode` 回落静态 `parent_mode`。
- `agent/loop.py`：删除 `__init__` 里写 `parent_mode_provider` 的 `lambda`；在会话/子 run 的 run 起点设置上限（快照）。
- `agent/subagent/scheduler.py`：`_launch_run` 在既有 4 个身份 contextvar 旁 set/finally-reset mode 上限。

### 影响的 API / 依赖

- 内部 API：`SubAgentManager.__init__` 的 `parent_mode_provider` 形参与 `configure_runtime` 的对应形参被移除（仓库内调用点仅 `agent/loop.py`，无外部调用方）。
- 契约（对外）：`current_mode_ceiling()` 成为 #245 消费的「会话 mode 通道」。**#245 依赖它做整轮上限快照**；若本 change 只换机制而不提供该通道，#245 会静默读不到值并退化回 fail-open。
- 无新增第三方依赖，无配置 schema 变化。

### 影响的测试

- 新增 `tests/agent/subagent/` 下的 mode 上限回归用例（六个方向 + 对照）；补 `_clamp_mode` 的既有零覆盖。
- 既有 `test_create_subagent_*`（走 `parent_mode=` 静态路径）行为不变，作为回归基线。

### 影响的文档

- 本 change 的 OpenSpec 文档、`docs/openspec-change-backlog.md`。
- 与 #245 的 spec delta 存在**口径重叠**（#245 已把 mode 上限语义写进其 `multi-agent-collaboration` delta）；需在实现前统一归属，见 `design.md` 的 Open Questions。

### 影响的系统 / 运维

无。纯进程内行为修正，无迁移、无数据格式变化。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 本 change 虽属 bugfix，但**引入了新的能力面**（会话 mode 上限通道 `current_mode_ceiling()`，被 #245 显式消费）并改动了跨模块、安全相关的能力面传播机制（`manager` / `loop` / `scheduler` / `context` 四处），命中分流表 `full` 的「架构级改造 / 走 grill 的非平凡 change」。故不按 `exempt` 的「bugfix 无新增能力面」豁免，也不按 `light` 的「成熟模式局部应用」处理，做完整调研。
- research questions:
  - Q1：业界 coding agent 如何把「权限/mode 上限」传播给派生的子 agent？是共享可变状态、显式参数，还是执行上下文（contextvar/thread-local）？
  - Q2：并发派发的兄弟节点若各自带不同权限档，主流实现如何保证互不污染？
  - Q3：会话级上限在「一次 run 中途被用户切换」时，应快照还是实时读取？
  - Q4：本仓库内是否已有可复用的正确先例，而不是引入第二套机制？
- findings:
  - **本仓库内先例（最高优先级依据）**：`workflow_id` / `node_id` / `graph_distance` / `bus` 四项**已在同一派发点** `_launch_run`（`scheduler.py:2112-2141`）用 contextvar set / finally-reset 传播，`create_subagent` 与身份字段消费它们；`context.py` 文件注释显式写明理由「asyncio 的每个 Task 各持一份 context 副本，其它节点的 run 看不到这里的 set」。即仓库早已认识到「共享标量在并发节点下不成立」并给出了正确方案，唯独 `mode` 还留在共享标量上。**本 change 的正确做法是把 mode 并入既有机制，而非新造一套。**
  - **业界同类实现（参考仓库 `codex` / `opencode` / `pi`，路径见 `design.md`）**：未发现与「把可变 mode 标量共享给子 agent 并按构造顺序覆写」同构的缺陷形态。Codex 的 `codex-rs/linux-sandbox` 与 `codex-rs/core` 对子进程采用**进程级沙箱**（`sandbox_mode` / `SandboxPolicy` 在 spawn 时解析为独立策略，子进程不共享父进程的可变权限标量），因此不存在「兄弟并发覆盖同一标量」的结构性缺陷。这从反方向印证：**能力面边界应当随执行单元（进程 / Task / 上下文）绑定，而不是挂在会被并发复用的共享对象上。**
  - **快照 vs 实时（Q3）**：参考实现未提供与本仓库「一次 run 内允许切换会话 mode」等价的实时语义先例；其权限档在进程启动时即解析固定，天然等价于**快照**语义。这支持本 change 选择「run 起点快照」而非实时读取——它与业界「一次执行单元的能力边界自始至终一致」的直觉一致。
  - 注意：本机 `.dev/reference-repos.txt` **不存在**（该文件按仓库约定不提交），调研改用 `/home/shared/agent-study/reference-repos` 下的参考仓库（`codex` / `opencode` / `pi` / `deepseek-harness` / `kimi-code` / `zcode`）；路径可用，未构成调研阻断。
- design impact: 调研结论直接决定了三个设计选择——(1) **不引入新机制**，把 mode 并入既有 contextvar 身份通道（Q1/Q4）；(2) 节点上限在**派发点**确定并随 `copy_context()` 传播，使并发兄弟天然隔离（Q2）；(3) 采用 **run 起点快照** 而非实时读取（Q3）。同时调研未发现「共享 provider」方案的任何正向依据，支持彻底退役该字段而非打补丁。

## Impact Analysis

- **能力域**：`subagents`（ADDED 1 条 Requirement）、`multi-agent-collaboration`（ADDED 1 条 Requirement）。无 REMOVED / RENAMED。
- **代码**：`agent/subagent/context.py`、`agent/subagent/manager.py`、`agent/loop.py`、`agent/subagent/scheduler.py` 四处；无新增模块、无新增依赖。
- **数据 / 配置**：无 schema 变化，无迁移；不写盘、不改资产格式。
- **对外行为**：修正 fail-open（只读会话不再被授予写权限）与静默降级（build 节点不再被前面的只读节点降级）；新增 `current_mode_ceiling()` 只读通道供 #245 消费。
- **测试**：补齐 `_clamp_mode` 的零覆盖，六个方向 + 对照用例。
- **文档**：本 change 文档 + backlog 同步；#245 的 spec delta 存在口径重叠，归属需用户拍板（见 design Open Questions）。
- **风险面**：删除 `parent_mode_provider` 会移除一条「动态 provider」能力；仓库内唯一写入点（`agent/loop.py:153`）随本 change 一起删除，无外部调用方，`unknown`：无。
