# Proposal: 声明化流程引擎（declarative-flow-engine，P4）

关联跟踪 issue：[#141](https://github.com/Xingkai98/asterwynd/issues/141)（【feature】declarative-flow-engine：P4 声明化引擎（statechart.yaml + 薄引擎 + parity 等价 pin））。父 map：[#121](https://github.com/Xingkai98/asterwynd/issues/121)（开发流程可安装化，P4 声明化引擎）。

## Change Type

- primary: process
- secondary: []

## 需求

1. **statechart.yaml 声明流程状态机**：把流程状态机（phase / sub_state / awaiting / transition 的转移逻辑）从 Python 硬编码声明化为 `statechart.yaml`，语义对齐 `dev-workflow-state-machine` 规格（五阶段、awaiting 三态、blocked 建模）。
2. **薄引擎消费 statechart**：stdlib-only 薄引擎加载 `statechart.yaml`，提供与现有 Python 常量（`agent/workflow/event_log.py` 的 `_apply_*_event`、`scripts/workflow_state.py` 的 flow 命令）**等价的**状态派生与转移。
3. **parity 等价 pin**：引擎输出与现有 Python 行为**等价锁定**（parity 测试 golden 断言），引擎坏了有旧逻辑兜底，验证价值后再替换。
4. **演示改规则不改 Python**：新增 `awaiting_design_confirmation` 态——**只改 statechart.yaml + 加 transition**，不改 Python，跑 parity 测试证明等价。
5. **方案 A 分工（statechart 与 workflow_methods）**：statechart.yaml 管「状态怎么流转」（state + transition）；`workflow_methods.json` 保留「每个状态用什么方法执行」（skill/command/agent）。把 `workflow_methods.json` 里已有的流程结构抽到 statechart.yaml，职责不重叠。

## 背景

- #121 P4 是「声明化引擎」：让开发流程状态机变成「改规则不改 Python」的声明化形态。这是 P0-P4 里最有架构价值的一项，也是 #121 路线的终点。
- #124 已定验收线：`statechart.yaml` + 薄引擎与现有 Python 常量 parity 等价 pin 住 + 演示一次真实规则变更不改 Python。触发点已到：P0（flow-policy-source #131）→ P1（flow-event-projection #136）→ P2（platform-gate #138）全部完成，P3（orchestration-notification #140）砍掉（飞书通知对单人仓 + 手机 paseo 鸡肋）。
- 现状：流程状态机硬编码在 Python——`agent/workflow/event_log.py` 的 `_apply_*_event`（blocked/transition 事件应用逻辑）、`scripts/workflow_state.py` 的 `flow block/confirm/status`（:12-15）、`scripts/workflow_methods.json`（可插拔方法映射，含部分流程结构）。
- 用户范围决策（2026-08-16）：只声明流程状态机（不做 guard/checker 规则声明化——已由 flow-policy.json 驱动）；parity 并存（不替换现有 Python，验证价值后再替换）；方案 A 分工；演示加 `awaiting_design_confirmation` 态。

## 非目标

- **不做 guard 执法规则 / checker 检查的声明化**（已由 flow-policy.json 驱动，P0；再声明化是重复劳动）。
- **不替换现有 Python 状态机**（parity 并存，验证价值后再替换；引擎坏了有旧逻辑兜底）。
- **不引入 XState / SCXML / 外部依赖**（stdlib-only 薄引擎；借鉴 XState 的 `states/on/transition` 模型，自写 Python 实现）。
- **不做可安装产物**（#124：P0-P4 只做内部改造，可安装化留后续 effort）。
- **不改 paseo / AgentLoop / ToolRegistry**。
- **不扩展等待态集合**（awaiting 三态保持；演示新增的 `awaiting_design_confirmation` 是验证 parity 的演示规则，不是产品化新态）。

## 用户故事

- 用户想加一个新的 awaiting 态（如 `awaiting_design_confirmation`）→ **只改 statechart.yaml**（加一个 state + 一条 transition），Python 一行不改，flow 命令/投影/执法自动跟随。
- 用户想调整某个阶段转移（如 design 完成后自动进入 awaiting）→ 只改 statechart.yaml 的 `on` 表。
- 用户跑 parity 测试 → 证明引擎输出与现有 Python 等价（golden 断言），引擎与旧逻辑行为一致。
- 用户想换某个阶段的执行 skill → 改 `workflow_methods.json`（不改 statechart、不改 Python）——两个文件各管一个维度，职责不重叠。

## 行为定义

### statechart.yaml（声明流程状态机）

- schema（对齐 XState `states/on/transition` 模型 + dev-workflow-state-machine 语义）：
  - `id`、`initial`（初始 phase.sub_state，如 `planning.exploring`）
  - `states`：每个状态（`<phase>.<sub_state>`，如 `planning.awaiting_proposal_confirmation`、`blocked.awaiting_user_confirmation`）
  - `on`：每个状态的转移表（`<event>: <target_state>`，如 `proposal_done: planning.awaiting_proposal_confirmation`、`user_confirmed: planning.building_ready`）
  - 挂载到 `workflow_methods.json` 的现有流程结构之上（方案 A）
- 语义对齐现有 Python 常量：awaiting 三态建模为 blocked 子态、`review_blocked` 不入 awaiting 集、派生 any-of + 容忍异构。

### 薄引擎（stdlib-only）

- 消费 `statechart.yaml`，提供：
  - `apply_transition(state, event) -> state`：按 on 表转移，等价现有 `_apply_*_event`
  - `derive_state(events) -> state`：事件序列派生，等价现有投影派生
  - `validate()`：statechart 合法性（状态/转移引用完整性、initial 存在）
- 落点：`flow/` 目录（#124 可拆缝契约，引擎边界收进 `flow/`，拆仓时平移）。
- stdlib-only（argparse/json/yaml 不引入——若需要 YAML 解析，用 JSON 或最小解析器，grill 定）。

### parity 等价 pin

- parity 测试：同一事件序列，**引擎结果 == 现有 Python 结果**（golden 断言），覆盖：初始派生、awaiting 进入/解除、transition 应用、归档可投影。
- 引擎与现有 Python **并存**（不替换）；parity 测试锁一致，引擎坏了有旧逻辑兜底。

### 演示（改规则不改 Python）

- 新增 `awaiting_design_confirmation` 态（演示规则）：statechart.yaml 加一个 state + transition；Python 不改；parity 测试证明引擎正确派生新态，旧 Python 逻辑不变（新态对旧逻辑透明——旧逻辑不认识该态时按 NON_STATE/容忍处理，grill 定）。

### 方案 A 分工

- `statechart.yaml`：状态转移（新增）
- `workflow_methods.json`：执行方法（保留，含 skill/command/agent 映射；把已有的流程结构抽到 statechart）
- `flow-policy.json`：执法规则（不变，P0）
- `platform-gate.json`：平台配置（不变，P2）

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 引擎边界 | 新增 `flow/` 目录（statechart.yaml + 薄引擎 + schema 校验），#124 可拆缝契约落点 |
| 配置架构 | 新增 `statechart.yaml`（流程状态机）；`workflow_methods.json` 流程部分抽到 statechart（方案 A），保留执行方法部分 |
| workflow 命令 | `scripts/workflow_state.py` 的 flow 命令可**改用引擎**（parity 对照，不替换旧逻辑）或保持（grill 定）；现有 Python 状态机不改 |
| Specs | `openspec/specs/dev-workflow-state-machine/spec.md` delta（statechart 声明化 requirement） |
| Tests | parity 测试（引擎==Python golden）、statechart 合法性测试、演示规则测试 |
| Docs | AGENTS.md（配置架构说明：4 个配置文件各管什么）、change 自身文档 |
| 明确不受影响 | guard 执法（flow-policy.json 驱动）、platform-gate 配置、AgentLoop、benchmark、paseo |

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 本 change 走 grill（非平凡 process change，有 spec delta 与引擎交付），按判据命中「走 grill 的非平凡 change」→ full 必调研。调研对象为 statechart 声明化引擎模式与配置驱动流程引擎实践。
- research questions:
  1. statechart 声明化引擎的成熟模型（XState / SCXML）——状态机怎么声明、转移怎么表达、与硬编码 reducer 的差异？
  2. 配置驱动流程引擎（GitHub Actions yaml / BPMN / 重型 workflow 引擎）的取舍——本仓库为何用轻量薄引擎而非重型框架？
  3. parity / golden 双轨迁移模式——新旧实现等价锁定的业界做法？
- findings:
  1. **XState（statechart 声明化标杆）**：XState 是"state machines and statecharts for the modern web"的 JS 库，`createMachine()` 用**纯配置对象**（`id`/`initial`/`states`/`on`）声明行为，`createActor()` 运行，`actor.send({type})` 驱动事件。关键对比（作者 David Khourshid 在 StackOverflow 的对比）：**reducer（Redux）式的隐式逻辑无法序列化声明式**（"the implicit logic/behavior represented in reducers can't be serialized declaratively"）；而 statechart 是"reducer with rules"，声明合法转移 + 每个转移/进入/退出时的动作，**可序列化 JSON、行为可移植可配置**。XState 遵循 W3C SCXML 规范。本仓库不引入 JS 依赖，**借鉴其 `states/on/transition` 模型**，用 Python 薄引擎实现（stdlib-only，align guard 自包含约束）。
  2. **配置驱动流程引擎取舍**：#121 架构评审已否决重型 workflow 引擎（Temporal/Argo/Camunda——引入复杂运行时、违背 hook 自包含约束）；GitHub Actions yaml / BPMN 是成熟的"配置驱动流程"先例，P4 是**轻量 self-contained 版**（statechart.yaml + 薄引擎，不引入外部框架），符合「引擎与 guard 薄壳分离」的可拆缝结构（#124）。
  3. **parity / golden 双轨迁移**：本仓库 P1 已有成熟先例——`flow-event-projection` 用「老世代 replay 结果与修复前一致（golden 断言）+ 当代事件不抛错」的 parity 测试锁两代兼容（`agent/workflow/event_log.py`）。P4 的 parity 是同一模式：**引擎输出 == 现有 Python 常量**（golden 断言），验证价值后再替换。业界 characterization/golden test 也是新旧行为等价锁定的标准做法。
- design impact: 上述 3 点直接决定 P4 设计——借鉴 XState 的 `states/on/transition` 声明模型写 `statechart.yaml` + Python 薄引擎（不引依赖）；不引入重型框架（#121 评审红线）；parity 测试沿用 P1 的 golden 断言模式锁「引擎==Python」；引擎收进 `flow/` 目录（#124 可拆缝契约）。
- 本地参考仓库不可用：`.dev/reference-repos.txt` 不存在（已确认），无本地参考仓库可对比；业界实践调研以 XState/SCXML 文献 + 本仓库 P1 parity 先例为准。
