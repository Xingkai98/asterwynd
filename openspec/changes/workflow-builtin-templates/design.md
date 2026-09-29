# Design: 内置模板归一：RunPattern 融合进 Workflow DSL 入口

## Context

`RunPattern` 与 `RunWorkflow` 驱动**同一个** `WorkflowScheduler`，差异只有入口形状与出口投影。四个 pattern 早在 `workflow-dsl-scheduler`（D7）就降级为 DSL 模板，`run_pattern()` 只是兼容 adapter（`agent/subagent/patterns.py:429-471`）。本 change 是**双入口收敛**，不是迁移。

已逐条读码核实的现状事实（不是转述）：

1. **入参形状**：`RunPattern(pattern, task, params)` 两个必填（`agent/tools/builtin/subagents.py:415-436`）；`RunWorkflow(spec)` 要求整张 DAG（`:834-856`）。`params` 由 Python 消费后展开进 spec——`_items(workers, "worker")` 生成 N 个 item（`patterns.py:61-62`），`max_rounds` 填进 route 的 `max_routes`（`patterns.py:211`），`worker_max_tokens`/`worker_max_time_s` 落到节点预算字段（`patterns.py:65-77`）。
2. **出口形状**：`RunPattern` → `_legacy_result()` 扁平结构（`patterns.py:376-426`）+ `result["bus"] = bus.snapshot_payload()`（`:468`）。`RunWorkflow` → `scheduler.parent_envelope()`，**显式 `payload.pop("bus", None)`**（`scheduler.py:3088-3102`），节点数硬上限 `_PARENT_NODES_LIMIT = 200`、文本字段裁到 `_PARENT_FIELD_LIMIT = 200`（`:119-121, 389-405`）。
3. **`OrcPattern` / `run_pattern` 被 spec 钉死**：`openspec/specs/multi-agent-collaboration/spec.md:70`（adapter 条款）与 `:135`（返回字段条款）。
4. **`asset_source` 的唯一写入点是 `run_pattern`**：`scheduler.asset_source` 默认 `{"kind": "dsl"}`（`scheduler.py:503`），只有 `run_pattern` 在 `run(spec)` 前覆盖为 pattern 溯源（`patterns.py:457-462`）。`SaveWorkflowAsset` 读它决定存 recipe 还是 spec（`subagents.py:905-938`）。**删 `run_pattern` 必须迁移这个写入点**，否则 #245 的「pattern 图存成 recipe 资产」静默退化成 DSL 资产。
5. **`RunWorkflow` 已在 `SPAWN_TOOL_NAMES`**（`manager.py:424-435`），合并进来的 `template` 路径仍在 `RunWorkflow` 名下，深度闸语义不变。
6. **C5 benchmark 的 `template` 臂不经工具**：`benchmarks/agent_runner.py:505-529` 直调 `compile_pattern`，本 change 不影响它。

**外部调研**（RIR 全文见 proposal.md）给出的两条硬约束：

- **没有任何参考实现让单工具按入参吐两种形状**。最接近的类比全是两个工具、各一个稳定 envelope（deepseek `workflow`/`ralph`、LangGraph prebuilt/custom、kimi `Agent`/`AgentSwarm`、codex `spawn_agent`/`spawn_agents_on_csv`、opencode `task`）。MCP 文献把「入参相关返回 schema」列为记录在案的坑，缓解办法是「显式 `required` 判别子 + 单一稳定形状」。
- **模板参数化一律留在代码/配置拥有的配方层**，占位符集封闭、启动前校验、从不 eval（kimi `{{item}}`、codex `{column}` over 声明列、deepseek ralph 固定脚本、Ema `input_schema`）。没有一个把参数化放进动态 spec，也没有一个接受带通用展开规则的模型手写模板。

## Goals / Non-Goals

**Goals**

1. 把「跑内置模板」并入 `RunWorkflow`，删除 `RunPattern` 工具——模型侧模板调用从两个必填字段起步。
2. 让父 agent 从编排入口收到的**形状不随入参变化**：一种返回形状（bounded 投影），`bus` 不进该投影。
3. 模板参数化继续留在 Python（`compile_pattern`），**不引入** spec 内模板/占位方言、不引入静态模板文件。
4. 与 #245 归一：内置模板 = 随代码走的配方，用户资产 = 随 workspace 走的配方，**共用同一条编译路径**（`compile_pattern`）与同一个 `recipe` 概念。
5. 迁移 `asset_source` 写入点，保住 #245 的 recipe 资产能力。
6. 无静默行为变更：非法入参组合结构化拒绝，未知模板名结构化拒绝。

**Non-Goals**

- **不做静态模板文件（JSON/YAML）**。`WorkflowSpec` 没有模板/参数概念，`foreach.items` 是具体元组。纯文件模板需要发明「参数占位 → 展开」的求值规则，且新增可写面，与仓库「DSL 受限可校验、不执行模型生成代码」的安全姿态相悖（`agent/subagent/workflow.py:15-16, 27-32`）。模板参数化留在 Python 或 #245 的配方层。
- **不做模型手写 prompt 模板**（kimi/codex 那种单一 `{{item}}`/`{column}` 字面替换）。本 change 的 `template` 是**服务端配方的引用**，不是模型可写的字符串——开了这个口就等于打开本 change 要避开的占位符求值面。
- **不改 `parent_envelope()` / `_envelope()` 的内容**（除「谁是它的调用方」外逐字不动）。`_envelope` 仍是权威 envelope（C2 断言依赖），`parent_envelope` 的投影规则、`nodes_omitted` 语义、`_PARENT_*` 上限全不动。
- **不改资产 schema 与 4 个资产工具的对外行为**（`workflow_assets.py` 不动）。是否把 `RunWorkflowAsset` 也并入统一入口是独立判断（见 Open Questions）。
- **不改 benchmark 三模式**、不改 `workflow_id` 生成与 per-run 结果落点、不改内置模板编译结果。
- **不改模型当轮声明 spec 的行为**（#245 的「声明路径不钳制」口径逐字不变）。

## Decisions

### D1 — 收敛形态：一个工具 `RunWorkflow`，`spec` 与 `template` 显式互斥

`RunWorkflow` 扩展为接受 **exactly one of `{spec, template}`**：

| 入参 | 类型 | 说明 |
|---|---|---|
| `spec` | object | 既有：模型手写的 DAG spec（`parse_spec_for_manager` 校验）。 |
| `template` | string | 新增：内置模板名，enum = `orchestrator-worker` / `peer-review` / `hierarchical` / `bidding`。 |
| `task` | string | `template` 路径**必填**；`spec` 路径禁用（给了即拒绝）。 |
| `params` | object | 仅 `template` 路径：`workers`/`teams`/`proposers`/`max_rounds`/`worker_max_tokens`/`worker_max_time_s`。 |
| `wait` | boolean | 既有：`true`（默认）等待终态，`false` 立即返回启动回执。 |

**schema 层约束（grill R1 实测）**：`tool_parameters` 把参数字典原样传给模型（`agent/tools/base.py:18-56` → `agent/anthropic_llm.py:750-753`），而 Anthropic API 拒绝顶层 `oneOf`/`anyOf`（RIR）。**故「exactly one of」在 schema 层不可表达，只能是运行期判别**；且 `RunWorkflow` 现有的 `"required": ["spec"]`（`subagents.py:855`）**必须摘掉**，否则 `RunWorkflow(template=…)` 在模型侧就被判缺参。模型实际看到的是「两个可选字段 + 描述文本里的显式规则」。这与 RIR「判别子应在 required 语义上无歧义」的自我要求存在张力，只能靠描述 + 运行期拒绝弥合——形态与 `pi` 的单工具多模式一致（同为全可选 + 运行期 `modeCount` 判别）。

判别规则（四种非法组合一律**结构化拒绝**，不静默取其一）：

1. `spec` 与 `template` 同时给出 → `invalid_input`（`reason` 指明二选一）。
2. 两者都不给 → `invalid_input`。
3. `template` 给出但缺 `task` → `invalid_input`。
4. `template` 名字不在 enum → 同既有 `_invalid_spec` 风格的 `invalid_input`（列出可用模板名）。
5. `spec` 路径带 `params`/`task` → `invalid_input`（避免「以为 params 生效了」的假象）。

**为什么是一个工具而不是两个**：两个 Asterwynd 工具确实驱动同一个 `WorkflowScheduler`，工具重叠指导倾向合并（RIR）；且合并正是本 change 的收益来源（工具集少一个名字、少一份工具描述、模型少一次「该用哪个」的判断）。**为什么用显式互斥而不是别名**：`pi` 的单工具多模式（`packages/coding-agent/examples/extensions/subagent/index.ts:443-509` 按出现的参数判别、非法组合拒绝）是可直接照抄的形态；MCP 文献要求判别子显式且在 `required` 语义上无歧义——本 change 用「exactly one of」把歧义消灭在入参校验里。

**替代方案与否决理由**：
- **保留两个工具、只统一返回形状** —— 部分否决。这能达到「一种形状」，但保留了两份入参校验、两份工具描述，且不解决「模型要判断该用哪个」的成本；issue #246 的诉求正是双入口收敛（「spawn 工具集从 10 个减到 9 个」）。**代价**：合并后单工具 schema 更大，模型要读懂「二选一」——用 enum + 描述里的显式规则缓解。
- **`template` 同时接受资产名**（把 `RunWorkflowAsset` 也并进来）——否决为**本 change 范围外**，列入 Open Questions。理由：资产路径有独立的加载信任边界（闸值钳制、`mode` 收窄诊断、`overrides` 覆盖面子集，#245 D3），并入会让 `RunWorkflow` 的 schema 与行为分支显著变复杂，且可能破坏 #245 的「模型当轮声明路径行为逐字不变」不变量。**归一在本 change 落在「共用编译路径 + 共用 recipe 概念」这一层**（D4）。

### D2 — 返回形状：统一为 `parent_envelope()` 一处，`bus` 不进父上下文

`RunWorkflow` 无论走 `spec` 还是 `template`，父 agent 收到的都是 `scheduler.parent_envelope()`。**`bus` 键不出现在该投影里。**

- **依据一（内部自洽）**：`parent_envelope` 的 docstring 逐字写着「bus 是非权威广播通道（D4）：它不属于权威 envelope，也不该出现在父上下文里」，并已 `payload.pop("bus", None)`（`scheduler.py:3102`）。`_legacy_result` 注入 bus（`patterns.py:468`）是与该教义**不一致**的异常侧——收敛按 pop 一侧解决，消除这个自相矛盾。
- **依据二（外部一致）**：deepseek 父只拿到 `{id, createdAt, mode, label}`（`projection-types.ts:9-19`）；kimi 中间推理刻意不进父历史（`docs/en/customization/agents.md`）；opencode/pi 只返回子 agent 最后文本。Anthropic 把 message-bus 列为难调试的 cloud-scale 形态、不作默认结果面（RIR 第二层）。
- **`bus` 并未消失**：run **内部**仍可用 `PublishBusMessage`/`ReadBus`（`subagents.py:250-364`，`ReadBus` 仍受 `BUS_MESSAGE_LIMIT`/`BUS_SNAPSHOT_LIMIT` 界），`_envelope()` 仍为权威口径保留 `bus`。变的只是「父 agent 的**结果**里不再带它」。

**信息损失与补偿路径（必须正面写清，这是本 change 最贵的一处）**：`workers[]` / `selected` / `selector` / 顶层 `summary` 这四个 pattern 专属字段消失，取而代之的是：

- `nodes[]`：每个模板节点一条 bounded 摘要（`{id, kind, status, runs, subagent_id, items, summary≤200, reason≤200}`）。
- `root_result_ref`：workflow 级落盘根的 ref（C3 D3），读全文用 `ReadWorkflowResult`。
- `GetWorkflow(detail='nodes')`：逐节点 `result_ref`，按需读。

**已知的具体落差**（须在 Open Questions 让用户拍板，不藏在设计里）：
- `completed`/`failed` 的**语义变了**。`_legacy_result` 数的是**终态节点**（peer-review 的 producer 跑两轮仍算一条 worker，`patterns.py:386`）；envelope 的 `completed`/`failed` 数的是 **run**（`scheduler.py:3005-3019`）。实测对照：peer-review legacy `completed=2` / envelope `completed=4`；bidding legacy `3` / envelope `4`（同一 `spec_hash`）。
- **bidding 的 `selected` 不再抽取**。selector 在投影里是一条 `{id: "selector", kind: "subagent", ...}` 的节点摘要（≤200 字）；长 justification 会被截断，全文经 `result_ref` 读回。

> **⚠️ 实测订正（grill R1，见 `reviews/grill-design.md` 的 Confirmed Decisions）——本设计初稿的「per-worker 明细经 `GetWorkflow(detail='nodes')` 读回」是错的，必须按本条实现或拍板补通道。**
>
> 实测（探针 `/tmp/probe_refs2.py`、`/tmp/probe_itemrefs.py`）：foreach 类模板（orchestrator-worker / hierarchical / bidding 的 proposers，即四个模板里的三个）的 **per-worker `result_ref` 在统一出口下不可达**：
> - `_bounded_node` 丢弃 `subagent_ids`/`item_runs`（`scheduler.py:384-405`），父投影里 foreach 节点只有 `{id, kind, status, runs, subagent_id: None, items, summary≤200, reason≤200}`。
> - `GetWorkflow(detail='nodes')` 的 ref 来自 `_node_refs()`（`subagents.py:792-803`），它只读 `state.subagent_id`/`state.run_id`——foreach 容器节点这两个字段恒为 `None`（身份在 `state.item_runs`）。实测 `_node_refs` 对 orchestrator-worker / hierarchical 返回 `{}`，对 bidding 只返回 selector，对 peer-review 返回 producer/reviewer。
> - `root_result_ref` 只落终态节点的最后一条 summary（实测内容不含各 worker 正文）。
>
> 而**今天** legacy 出口的每个 worker 条目**确实**带 `result_ref`（`_worker_entry` 截断时注入，`patterns.py:365-372`，实测 workers=3 时三条各自可 `ReadWorkflowResult`）。所以删 `_legacy_result` 是**净损失**一条能力，不是「多一跳」。
>
> 最小补偿改法（若拍板补）：让 `_node_refs()`（或 `GetWorkflow(detail='nodes')`）对 `kind=="foreach"` 节点读 `state.item_runs`，吐 `item_refs: [{index, subagent_id, run_id, result_ref}]`——纯读投影，`item_runs` 已是权威身份源（`web/session.py` 同款用法已存在）。**这是本 change 实现前必须拍板项**（Open Questions Q1）：补则 task 5.6 的断言可落地；不补则 task 5.6 必须显式缩水并记录损失，SHALL NOT 静默降级成「只断言 `root_result_ref`」。

**替代方案与否决理由**：
- **按入参返回两种形状**（template → legacy，spec → envelope）——否决。这是 RIR 明确警告的形态：调用方无法在不知道入参的情况下解析返回体；MCP/function-calling 文献把它列为记录在案的坑。本 change 的核心诉求正是消除这个认知负担，不能用一个新版本重建它。
- **保留一个 pattern 专属的 `workers` 摘要字段塞进 envelope**——否决（本 change 范围内）。它会破坏 `parent_envelope`「节点只保留 bounded 摘要」的投影纪律（新增一个随展开数线性的字段），且是 D4 明确排除的 bus 之外的又一处不对称；若确需 per-worker 明细，正确形态是 `GetWorkflow` 的一个新 `detail` 模式，而非塞进结果体（列入 Open Questions）。

### D3 — 模板参数化留在 Python：`template` 是配方引用，不是 `WorkflowSpec` 的字段

`template` 路径的处理是：`compile_pattern(template, task=task, params=params)` → `WorkflowSpec` → 与 `spec` 路径**汇合**到同一个 `parse_spec_for_manager` / 校验 / 调度路径。

- `WorkflowSpec` **不加**任何模板/占位字段。`foreach.items` 仍是具体元组。
- **不新增可写面**：没有模板文件、没有占位符插值、没有表达式求值。`params` 的键按**每个模板各自的封闭子集**校验（见下）。
- 安全姿态：`agent/subagent/workflow.py:15-16` 的模块纪律（不执行模型生成代码、只做结构与语义校验）**不动**；本 change 不引入任何新的求值面。

**`params` 校验必须按模板封闭，不能只做全局封闭键集（grill R1 订正）**：实测 `compile_pattern` 今天对未知键**静默忽略**——`compile_pattern("peer-review", params={"workers": 7})` 的 `spec_hash` 与空参**逐字节相同**（`658b47f0aa7d5495`）。若只定义「全局封闭键集」（六个键的并集），`peer-review + workers:7` 会被放行而毫无效果，正是 D1 规则 #5 要消灭的「以为 params 生效了」假象在 template 路径复现。故每个模板自身的键子集：

| 模板 | 接受的 params 键 |
|---|---|
| `orchestrator-worker` | `workers` / `worker_max_tokens` / `worker_max_time_s` |
| `hierarchical` | `teams` / `worker_max_tokens` / `worker_max_time_s` |
| `bidding` | `proposers` / `worker_max_tokens` / `worker_max_time_s` |
| `peer-review` | `max_rounds` / `worker_max_tokens` / `worker_max_time_s` |

不属于该模板的键 → 结构化拒绝，`reason` 列出该模板的可用键。**这是行为变更**：`RunWorkflowAsset` 的 pattern 分支今天会把 recipe 默认 params 与调用方 params 合并后直接编译（`subagents.py:1198-1199`），历史上允许「多传无关键」；收紧后若某资产 recipe 存着跨模板键会被拒。是否让 `RunWorkflowAsset` 同步享受该收紧（会触碰「资产工具对外行为不变」这条 Non-Goal），见 Open Questions Q3。

**依据**：RIR 显示所有参考实现都把参数化放在代码/配置层，占位符集封闭且启动前校验；Asterwynd 的 `compile_pattern` 已经是这个容器，#245 的 `ALLOWED_OVERRIDE_FIELDS` 封闭子集已示范同一门槛（零新方言、直接赋值、覆盖后重校验）。

### D4 — 与 #245 归一：共用一条编译路径与 `recipe` 概念

两个 `recipe` 来源，**同一个编译入口**：

| 来源 | 载体 | 编译 |
|---|---|---|
| 内置模板（随代码走） | `template` 入参（enum） | `compile_pattern(template, task, params)` |
| 用户资产（随 workspace 走） | `WorkflowAsset(source="pattern")` 的 `recipe={pattern, params, task}` | **同一个** `compile_pattern(recipe.pattern, task=recipe.task, params=merged)` |

落一个共享 helper（拟定 `_compile_recipe(pattern, task, params) -> WorkflowSpec`，实现期定名），被 `RunWorkflowTool` 的 template 分支与 `RunWorkflowAssetTool` 的 pattern 分支共同调用；「recipe 名不在注册表 → 结构化拒绝」的措辞也共用。这样「归一」不是文档口号，而是**一条代码路径**。

**`asset_source` 迁移（本 change 的连带必做项）**：`scheduler.asset_source` 的写入点从 `run_pattern` 迁到 `RunWorkflowTool` 的 template 分支（`{"kind": "pattern", "pattern": template, "params": params, "task": task}`）。**spec 分支不写**（保持默认 `{"kind": "dsl"}`）。回归测试须钉住：「`RunWorkflow(template=...)` 跑完后 `SaveWorkflowAsset` 存出的是 `source="pattern"` 的 recipe 资产」——这是 #245 能力不静默退化的证据。

### D5 — 删除面与保留面（精确清单，供实现逐条对照）

**删除**（`agent/subagent/patterns.py`）：

- `run_pattern()`（`:429-471`）
- `_legacy_result()`（`:376-426`）
- `_workers_from_node()`（`:314-330`）
- `_worker_entry()`（`:333-373`）
- `_AGGREGATE_NODE_IDS`（`:246-252`）
- 模块 docstring 中逐字描述 `run_pattern` 返回形状的段落（`:11-22`）须改写

**删除**（`agent/tools/builtin/subagents.py`）：`RunPatternTool`（`:415-451`）；`agent/loop.py` 的注册（`:62, 398`）；`manager.py` 的 `SPAWN_TOOL_NAMES` 条目（`:427`）。

**保留**（模板本体，被三处共用）：`compile_pattern`、`PATTERNS`、`OrcPattern` 及四个子类、`_template_orchestrator_worker` / `_template_peer_review` / `_template_hierarchical` / `_template_bidding`、`_items`、`_worker_budget`、`_AGGREGATE_INSTRUCTION`。

> **注意 1**：`_workers_from_node` / `_worker_entry` 目前**同时**服务于 `_legacy_result` 与 `test_workflow_node_transcript.py` 的「出口 4」断言。删除前须确认该测试的断言改为走 envelope 的 `nodes[]` + ref，而非直接删测试——出口 4（worker 条目 bounded + `result_ref` 补偿）是 issue #213 的回归保护，其**语义**必须在新出口上继续被钉住（见 Testing Strategy）。**但**该语义的迁移依赖 Q1 拍板补 ref 通道，否则迁移不可能（见 D2 的实测订正）。
>
> **注意 2（grill R1 补，实现必踩）**：`_worker_entry` 还被 `tests/web_tests/test_workflow_node_transcript.py:942-946` **直接 import 调用**（`test_worker_entry_without_workflow_identity_does_not_lie`）。删 `_worker_entry` 会让该测试在**收集期 ImportError**；D5/tasks 5.6 初稿只点了「出口 4 经 `run_pattern`」那条（`:894-932`），漏了这条直调测试，须一并删除或改写。
>
> **注意 3（grill R1 补）**：`agent/subagent/bus.py:3` 与 `agent/subagent/context.py:11` 的模块 docstring 也写「bus is created by `RunPattern`」，与 `bus.py` 的 `snapshot_payload()` docstring 共三处措辞须一并订正（tasks 5.8 的 `rg` 会兜住）。
>
> **注意 4（grill R1 补）**：`benchmarks/agent_runner.py:518` 的注释引用 `RunPatternTool`（「与 `RunPatternTool` 同路」），tasks 5.8 的扫描范围已含 `benchmarks/`，会被抓住；该文件**逻辑不受影响**（C5 template 臂直调 `compile_pattern`）。

### D6 — `wait=False` 的回执形状是正交的第二形状，但带显式判别子

`RunWorkflow(wait=False)` 当前返回 `{status: "running", workflow_id, spec_hash, nodes: []}`（`subagents.py:871-881`）。这是**启动回执**，不是**结果**，与终态结果语义不同。

- **不视为「入参相关形状」违例**：它有显式判别子（`status == "running"` vs 终态 `status ∈ {completed, completed_with_failures, stalled, failed, cancelled, budget_exceeded, graph_recursion_exceeded}`），且 `wait` 是**显式声明的入参**而非隐式推断。符合 RIR 的「显式、诚实判别子」门槛。
- **本 change 不动它**，但须在 `RunWorkflow` 描述里写明「`wait=false` 返回回执而非结果」，避免模型把回执当结果解析。

## Pre-Implementation Review

> 本 change 为非平凡 change（改工具面 + 改 spec 契约 + 改父 agent 结果投影），实现前须按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D6，逐项确认实现细节、依赖、风险、测试策略与文档影响，产出结构化决策记录到 `reviews/grill-design.md`，并经停轮确认（grill-confirmation-gate）。本节为占位声明，实际 review 记录以 `reviews/grill-design.md` 为准。

## Risks / Trade-offs

- **风险：`completed`/`failed` 语义切换会造成静默误读。** 旧 `RunPattern` 的 `completed` 是节点口径、envelope 是 run 口径。**缓解**：`RunWorkflow` 描述里写清 envelope 的口径；如用户拍板要保留节点口径，正确落点是 `GetWorkflow` 的新 `detail` 模式而非改 envelope（Open Question）。
- **风险：per-worker 明细从内联变为按需读，多一跳。** **缓解**：`root_result_ref` 恒在投影里；`GetWorkflow(detail='nodes')` 提供逐节点 ref；这是 C3 既定的「父 agent 永远 bounded」纪律，pattern 路径是最后一个未对齐的例外。
- **风险：`asset_source` 写入点迁移漏做，静默退化 #245 能力。** **缓解**：D4 写明 + 回归测试钉住「template 图存出 recipe 资产」。
- **风险：合并后单工具 schema 变大，模型误用（例如 spec 路径带 params）。** **缓解**：D1 的五条互斥规则 + 结构化拒绝 + enum；`pi` 的单工具多模式已证明该形态可用。
- **Trade-off**：删除 `RunPattern` 是对模型面工具的**破坏性变更**（工具名消失）。这是 issue #246 的既定诉求（「spawn 工具集减一」），且 `RunWorkflow` 的 template 路径完全覆盖其能力面。
- **Trade-off**：`bus` 从 `RunPattern` 返回体消失，是可见行为变更（现有测试依赖）。接受——它对齐 D4 与外部一致实践，且 `bus` 在 run 内仍可达。

## Testing Strategy

- **入参互斥**（D1）：四条非法组合各一条测试（同时给 / 都不给 / 缺 task / 未知模板名）+ spec 路径带 params 拒绝。
- **模板路径等价性**（D3/D4）：`RunWorkflow(template="peer-review", task=..., params={"max_rounds": 2})` 编译出的 spec 与 `compile_pattern(...)` 逐字一致（`spec_hash` 相等）；且与「同一 spec 走 `RunWorkflow(spec=...)`」产生同一形状的返回体（键集相等）。
- **返回形状统一**（D2）：父投影键集在 `spec` 与 `template` 两条路径上相等；投影**不含** `bus`；`nodes[]` 每节点文本 ≤ `_PARENT_FIELD_LIMIT`；`nodes_total`/`nodes_omitted` 仍正确。
- **出口 4 语义迁移**（D5）：把 `test_workflow_node_transcript.py` 的「worker 条目 bounded + `result_ref` 补偿」断言改挂到新出口（`GetWorkflow(detail='nodes')` 的 `result_ref` 或 envelope 的 `root_result_ref`），**不删断言语义**——这是 issue #213 的回归保护。
- **#245 能力回归**（D4）：`RunWorkflow(template=...)` → `SaveWorkflowAsset` 存出 `source="pattern"` 的 recipe 资产；用不同 `params` 重跑展开项数变化。
- **深度闸**（D5）：深度到限的子 agent 工具集不含 `RunWorkflow`（且不再有 `RunPattern`）。
- **既有行为不变**：`StartWorkflow`/`DeclareWorkflow`/`GetWorkflow`/`CancelWorkflow`/4 个资产工具行为逐字不变；`_envelope`/`parent_envelope` 内容逐字不变（回归 `test_bounded_envelope.py` 的键集与界断言）。
- **删净检查**：全仓 `rg 'run_pattern|RunPattern|_legacy_result'` 零命中（除本 change 的 change 文档与 archive 历史）。
- 全量 `uv run pytest -q` 绿 + `openspec validate --all --strict` + artifact checker。

## Open Questions

> 完整版（含逐条具体例子与推荐）见 `reviews/grill-design.md` 的 `## Open Questions`；用户答复回填同文件的 `## User Confirmation`。本 change 在停轮确认（grill-confirmation-gate）前不得写实现代码。

1. **per-worker 明细损失**：统一出口下 foreach 类模板（三个模板）的 per-worker `result_ref` 不可达（实测）。是接受损失，还是补 `_node_refs` 的 `item_runs` 投影？
2. **`completed`/`failed` 口径**：从节点口径翻成 run 口径（实测 peer-review 2→4）。是否接受「run 口径 + 工具描述写明」？
3. **`params` 校验按模板封闭**：是否接受「跨模板键结构化拒绝」这一行为变更，以及 `RunWorkflowAsset` 的合并路径是否同步收紧？
4. **`wait=false` 回执**：与终态 `parent_envelope()` 形状完全不同，是否确认为可接受的「正交第二形状」？
