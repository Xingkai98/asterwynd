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
- **不改资产 schema、不改变资产工具有效输入的语义**（`workflow_assets.py` 不动）。是否把 `RunWorkflowAsset` 也并入统一入口是独立判断（见 Open Questions）。**R2/R3 订正**：本条原标题「不改 4 个资产工具的**对外行为**」与 Q3 的「收紧资产路径」**字面冲突**（实现者只读标题会以为不能动资产路径校验），已改为现标题。准确口径是「不改资产 **schema**、不改变**有效键的语义**」——把模板封闭键校验同步到 `RunWorkflowAsset` 的 pattern 分支（拒绝该模板无效的键）**不算违反本条**：它只拒绝本就无效的输入，不改变任何有效输入的行为。**不违反 #245**（#245 无「资产工具对外行为不变」承诺，且 `#245` design.md:45 逐字把模板归一划给 #246）。该收紧的最终取舍见 Open Questions Q3（已确认收紧）。
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
> 最小补偿改法（若拍板补）：让 `_node_refs()`（或 `GetWorkflow(detail='nodes')`）对 `kind=="foreach"` 节点读 `state.item_runs`，吐 `item_refs: [{index, subagent_id, run_id, result_ref?}]`——纯读投影，`item_runs` 已是权威身份源（`web/session.py:1207,1213` 同款用法已存在）。**这是本 change 实现前必须拍板项**（Open Questions Q1）：补则 task 5.6 的断言可落地；不补则 task 5.6 必须显式缩水并记录损失，SHALL NOT 静默降级成「只断言 `root_result_ref`」。
>
> **⚠️ R2 实测再订正（三条硬约束，实现必遵，见 `reviews/grill-design.md` 第二轮 Confirmed Decisions）**：
> 1. **只承诺成功项的 ref**。`result_ref` 只在成功路径 `_complete_run` → `_write_result_artifacts` 写（`manager.py:1326-1388`）；`_mark_failed`/`_mark_cancelled`/`_mark_budget_exceeded` **都不落盘**。实测：失败项 `result_ref=None`、取消项 `None`、`worker_max_tokens` 超限项 `None`。故 `item_refs` 里 `result_ref` **仅对成功项出现**，失败项给有界 `reason` + 状态——与 legacy `_worker_entry`（只在 `truncated and ref` 时注入，`patterns.py:365-372`）**同口径**，不是净回归。spec delta 已按此改写（初稿「每个展开项…可达」是过度承诺）。
> 2. **跳过未派发的空槽**。`item_runs` 槽在派发前是默认 `_ItemRunSlot()`（`subagent_id=None`/`run_id=None`）。实测（`max_total_runs=2` / 6 项 foreach）容器被预算 drain 拦下时 6 个槽全空（`fan: status=blocked item_states=['pending']*6`）。投影须跳过空槽。
> 3. **自带界**。计数键无上界（`patterns.py:81` 是 `max(1, int(...))`，实测 `params={"workers": 100000}` → 10 万 item）。成功项数被 `max_runs`（默认 300）间接界定，但设计文本必须显式声明该界，并附 `items_total`/`item_refs_omitted`——否则把「只读出口」重新撑成随规模线性的数组，正是投影纪律要消灭的形态。
>
> **「更小改法」（在 `parent_envelope()._bounded_node` 里直接带 per-item 投影）——R2 明确否决**：它同时违反本 change 的 Non-Goal（`parent_envelope`/`_envelope` 逐字不动，见 §Non-Goals）与投影纪律（`_bounded_node` 明写「丢弃随图规模线性增长的数组」，`scheduler.py:389-405`）。选 `GetWorkflow(detail='nodes')` 那个出口是对的——它本就允许逐节点 `result_ref`（`subagents.py:775-781`）。
>
> **⚠️ R3 实测再订正（字段定义与语义，实现前必钉）**：
> 1. **`items_total` / `item_refs_omitted` 定义钉死**：`items_total = len(state.item_runs)`（= 本轮展开项数，含空槽），`item_refs_omitted = items_total - len(item_refs)`（**涵盖空槽 + 超固定上限两类**）。R3 实测：预算 drain 用例 6 槽全空 → `items_total=6`、`item_refs=[]`、`omitted=6`（全部来自空槽）。**不钉死会让测试写不出唯一期望值**（spec delta 初稿把 omitted 只绑「超上限」，与空槽来源冲突）。
> 2. **只反映最后一轮**：`_execute_foreach` 每次进入都把 `state.item_runs` 整体重置（`scheduler.py:1890-1896`，与 `state.items`/`item_states` 同批归零）。R3 实测带 route 回边的容器 `fan.runs=2`（跨轮累计）但 `len(item_runs)=2`（仅最后一轮）。这是**既有正确语义**（否则会吐同一 index 的陈旧 run），但实现/测试须知道「`item_refs` 长度对 `runs`（跨轮累计）对不上是正常的」。
> 3. **固定上限取既有常数**：`item_refs` 长度上限**复用 `_PARENT_NODES_LIMIT` = 200**（不新增常数）——模板路径因 `max_items`=20 实际到不了 200，纯 DSL foreach 路径可到 `max_runs`≈300，超 200 的进 `item_refs_omitted`。

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

不属于该模板的键 → 结构化拒绝，`reason` 列出该模板的可用键。

**校验落点（R2 实测）**：落在 **`compile_pattern` 这一唯一 choke point**，三个生产调用方共用——`RunWorkflowAsset` 的 pattern 分支（`subagents.py:1201`）、benchmark `_run_template_pattern`（`agent_runner.py:516`，**不传 params**）、以及本 change 的统一入口。既有测试全部只用模板自身的键，在此校验**零破坏**。`RunWorkflowAsset` 因此**自动享受**同一校验。

**Q3 归属澄清（R2 实测订正）**：「资产工具对外行为不变」这条 Non-Goal 是**本 change（#246）自己**的设计约束（`design.md` §Non-Goals、`proposal.md` §Non-Goals），**不是 #245 的承诺**——#245 的 Non-Goals 无此项，且它**显式把内置模板归一划给 #246**（归档 design 原文：「**不做内置模板归一。** 内置 4 个 pattern 走代码内注册表（`PATTERNS`）……那是 #246 的范畴」）。故把按模板封闭的键校验同步到 `RunWorkflowAsset` **不违反 #245**，只需在本 change 内把该 Non-Goal 措辞修订为「仅拒绝对该模板无效的键，不改变有效键的语义」。实测资产路径今天确实放行跨模板键（caller `params={"workers": 7}` 打到 peer-review 资产 → 起图正常、`workers` 被静默忽略）——这正是本条要消灭的假象。是否接受收紧见 Open Questions Q3。

**必须同时做值级校验（R2 新增，Q5）**：设计初稿只写了「未知键」一维，漏了「值非法」维。实测：`params={"workers": "abc"}` 在 `_template_*` 抛**未捕获** `ValueError`（`int("abc")`）、`{"workers": None}`/`{"teams": [1,2]}` 抛 `TypeError`，经 `execute_with_retry` 折成模型可见的**裸 `[Error: invalid literal for int()…]`**（非结构化、不可重试、无自足 reason），与 D1 规则 #5 的口径冲突。故校验须含值类型：计数键要求「可安全 `int()` 且为正整数」、`worker_max_*` 要求数值；非法值 → `invalid_input`。**clamp 保留**（`0/-5 → 下界`是既有语义，实测 `workers:0 → 1`，不宜改）——只把「无法转成数」这类从裸异常改成结构化拒绝。是否接受见 Open Questions Q5。

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

## Open Questions（Q1–Q6 ✅ 已确认 2026-09-29；**Q7 ⏳ 待确认，阻塞实现**）

> 完整版（含逐条具体例子与推荐）见 `reviews/grill-design.md` 的三轮 `## Open Questions`；用户答复记录于同文件的 `## User Confirmation`。**Q1–Q6 已拍板；R3 新增的 Q7 尚未拍板，grill-confirmation-gate 在 Q7 确认前仍拦截代码写。**

1. ✅ **已确认（2026-09-29）：per-worker 通道「补」。** 用户答复：落 `GetWorkflow(detail='nodes')`，形状 `item_refs: [{index, subagent_id, run_id, result_ref?}]` + `items_total`/`item_refs_omitted`；跳过未派发的空槽；**只有成功项有 `result_ref`**（失败/取消/预算超限恒为 `None`），spec delta 措辞须与 legacy `_worker_entry` 同口径，**不得暗示失败项可读全文**。
2. ✅ **已确认（2026-09-29）：接受 run 口径，不改名。** 用户答复：`completed`/`failed` 数的是 run 不是 subagent；不改名（改名要连 `_envelope` 一起动、约 20 处断言，性价比不抵）。**必须在工具描述里写明**「completed/failed 数的是 run，不是 subagent」。主 session 补充：实测 `parent_envelope()` 是 `_envelope()` 的派生（`scheduler.py:3100` 起手 `self._envelope(status=…)` 再 pop + bounded），「只改父投影」结构上不可行，故撤回改名提议。
3. ✅ **已确认（2026-09-29）：按模板封闭键校验 + 同步收紧资产路径。** 用户答复：校验落 `compile_pattern`（唯一 choke point）；同步修订本 change 自设的 Non-Goal 措辞（**不违反 #245**，见下方 Non-Goals 的 R2 订正）。
4. ✅ **已确认（2026-09-29）：接受 `wait=false` 回执为「正交第二形状」。** 用户答复：工具描述硬写「回执非结果」（`status:"running"` 与终态集合不相交，`wait` 是显式入参）。
5. ✅ **已确认（2026-09-29）：做值级校验。** 用户答复：非法值（非整数 / null / 不可转数）→ `invalid_input` 结构化拒绝，列出可用键与取值约束；**clamp 保留**（`workers=0/-5 → 下界`是既有语义，不动）。
6. ✅ **已确认（2026-09-29）：`workers` 上界归位——不造第二套上界，复用既有 `max_items`，但须把「静默截断」改为显式报告。** 用户答复（主 session 取证后新增的约束）：`params` 计数键无上界（实测 `workers=100000` 造 10 万 spec items）；要求明确它在 Q3/Q5 校验设计里的归位，并与既有三闸（`max_items`/`max_nodes`/`max_runs`）的关系写清，**不得造第二套互不知情的上界**。
   **实测结论（本 session 探针 `/tmp/probe_maxitems.py`）**：**该上界已经存在**——`WorkflowNode.max_items` 默认 **20**，`_resolve_items` 在执行期做 `items[:max_items]` 静态截断（`scheduler.py:2611-2614`），模板不设 `max_items`（`patterns.py` 零命中）故一律吃默认 20。实测：`workers=100000`→`state.items=20`、`workers=50`→`20`、`workers=20`→`20`、`workers=5`→`5`（均 `status=completed`）。**即 `workers=100000` 的真实效果是「静默只跑 20 个」**——与 Q3/Q5 要消灭的「以为 params 生效了」是**同一类假象，只是发生在值层**。
   **归位决定**：**不新增上界**（三闸已是唯一权威：`max_items` 截断展开项数、`max_nodes` 计展开节点、`max_runs` 计 run）。校验层**拒绝**「计数键 > 既有 `max_items`」的输入并报 `invalid_input`（`reason` 写明该模板的位次上限来自 `max_items`），使「只跑 20 个」不再静默；**`max_items` 本身不改**（既有语义，且它是三闸之一，改它会波及非模板路径）。`workers=100000` 因此在**校验期**被拒，不会走到执行期截断——避免「校验过了但展开被三闸截断」的双重语义。**唯一权威边界仍是三闸**，校验只是把「超出既有边界」从静默变显式。

7. ⏳ **待确认（2026-09-29 R3 新增，阻塞「Q6 闭环」判定）——`max_rounds` 的静默截断是否同样归位？** R3 实测：`max_rounds` 落到 route 的 `max_routes`，受 `recursion_limit`=25 约束（不吃 `max_items`）。`peer-review` 在永不批准时 `max_rounds=3/20/25/100000` **全部**停在 `graph_recursion_exceeded`、`steps=25`、`producer.runs=9`——即 `max_rounds=100000` 的真实效果是「静默只跑约 9 轮」，与 Q6 要消灭的 `workers=100000` **同类**，但逃出了「计数键 > max_items」规则。两条朴素修法都不好（跳过 → 假象存续；套 `max_items=20` → 误拒合法的 `max_rounds=25`）。
   **R3 推荐**：按模板分别取界——`workers`/`teams`/`proposers` 对 `max_items`（20），**`max_rounds` 对 `recursion_limit`（25）**（两个界都是既有闸，不造第二套上界）；超界一律 `invalid_input` 并在 `reason` 写明界的来源。若用户认为 `max_rounds` 的静默截断可接受，则须在 design/spec **显式声明**「`max_rounds` 不在本校验范围内、超 `recursion_limit` 由既有闸处理」——不能留白。**此项拍板前，Q6 不得判定为完整闭环，实现不得开工。**
