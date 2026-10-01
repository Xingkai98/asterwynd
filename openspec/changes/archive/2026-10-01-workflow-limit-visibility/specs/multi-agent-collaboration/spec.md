# multi-agent-collaboration spec delta: 工作流闸门可见性

## MODIFIED Requirements

### Requirement: 工作流可零成本模拟执行以暴露数据投递语义

系统 SHALL 提供一个只读工具 `DryRunWorkflow`，接受与 `DeclareWorkflow` 相同的 `spec` 参数，对给定 spec 执行**模拟**，并返回数据投递报告。

模拟 SHALL NOT 调用真实 LLM（真实 provider 的调用次数 SHALL 为 0），SHALL NOT 向**调用方的 workspace** 写入任何文件，SHALL NOT 把模拟的 workflow 注册进调用方 `SubAgentManager` 的 workflow 注册表，SHALL NOT 触达调用方的图事件 sink。这些隔离性质 SHALL 由测试机械锁定，SHALL NOT 仅靠实现约定。

**口径说明（避免误读）**：隔离要求是「不污染调用方的 workspace 与状态」。模拟**允许**在一次性临时目录里写中间 artifact，但这些 SHALL 随模拟结束清理，且 SHALL NOT 指向调用方的 workspace 根。（依据：写入口有两个——manager 的 `_write_result_artifacts` 与 scheduler 的 `_store`——两者都以 `workspace_policy.workspace_root` 为路径根，所以「一次性 workspace_root」是隔离的**独立充分条件**。）

模拟 SHALL 复用既有的调度执行路径（门控、reducer、route 匹配、foreach 展开、循环计数），SHALL NOT 另起一套与真实执行可能漂移的模拟逻辑。

模拟 SHALL NOT 让「语义压缩型」的聚合行为污染报告：聚合节点在报告中呈现的产出 SHALL 是**上游文本的有界投影**，SHALL NOT 是模拟替身（fake LLM）对压缩请求的回应。报告 SHALL 说明该产出是投影而非真实运行时的语义压缩结果。

模拟 SHALL 让每一次替身模型调用都可归因到某个节点；SHALL NOT 出现无法归属到任何节点的调用记录。

报告 SHALL 至少包含：

- 每个节点的 `id` / `kind` / 终态 `status` / 被执行的 `runs` 次数 / 产出 `produced`。节点集合 SHALL 基于实际执行计划（含系统自动插入的汇合层），SHALL NOT 只列出模型声明的节点；执行计划中由系统自动插入的节点 SHALL 可被识别（与声明节点区分）；
- 对**非正常结束**的节点（失败 / 被取消 / 被跳过），报告 SHALL 给出可解释的原因，SHALL NOT 只给一个 `status` 值让调用方无从判断「是图的问题还是模拟本身的问题」；
- route 节点：判定输入 `input_seen`（SHALL 与调度器实际用于匹配的文本同源）、命中的标签 `matched`、实际走到的后继 `walked_to`、是否走了 `default`；判定输入的**来源节点** SHALL 可识别（SHALL NOT 只给文本而不给归属）；
- 每个节点的 `received`——该节点实际收到的任务文本（SHALL 反映上游投递与 foreach 项注入的净效果）。对被 foreach 展开的节点，`received` SHALL 按**展开项**分别可见，SHALL NOT 让多个项的输入坍缩为单一值；
- 每条边的 `from` / `to` / `channel`，以及该边是否为控制边（route 出边）；
- 一个显式标记该结果为模拟的字段。

报告中的文本字段 SHALL 有界（按可配置上界截断，缺省上界 SHALL 为一个明确的正整数常量），SHALL NOT 把不带截断的聚合槽全文返回。被截断处 SHALL 带一个**可与调度器既有 bounded 标记区分**的标记——既有标记承诺「有 `result_ref` 可读全文」，而模拟结果没有任何可读的 ref。

对聚合节点的槽值，报告 SHALL 以独立字段提供（单独截断），SHALL NOT 与节点的 `received` / `produced` 混为一层；未被任何 route 实际读取的聚合槽 SHALL NOT 展开。

报告 SHALL 额外暴露**结构闸（structural gates）**的可见性，使调用方在预演拓扑的同时能判断离闸距离，SHALL NOT 只给一个跑通/跑不通的结论：

- 报告 SHALL 含一个**结构闸生效值**字段，覆盖 `recursion_limit` / `max_nodes` / `max_runs`，每项 SHALL 以 `declared` / `applied` / `clamped` 三段式给出，且 SHALL 与系统其余对外报限制值的出口**同源同形**（SHALL NOT 在报告层基于 spec 重算）；
- 报告 SHALL 含一个**节点预算**字段，以 `declared`（声明节点数）/ `graph_nodes`（**已落地**执行计划的图节点数，含系统自动插入层、**不含** foreach 展开项）/ `expanded_nodes`（**闸门等价投影**：闸门 `max_nodes` 若把这张图展开完会数到的计费规模）/ `auto_inserted`（**已落地**的系统自动插入节点数）/ `limit`（`max_nodes` 的生效值）/ `headroom`（`limit - expanded_nodes`，可为负）给出，SHALL 让调用方不必自行清点即可看出自动插层与 foreach 展开把计费规模放大了多少。`expanded_nodes` SHALL 与闸门据以判定 `max_nodes` 超限的计费口径同源，SHALL NOT 只数图节点（后者会漏掉 foreach 展开项、在撞闸图上给出**正**余量）。`graph_nodes` 与 `auto_inserted` 反映**已落地**的计划，`expanded_nodes` 反映**展开完成后**的投影，两者基线不同——当闸门在自动插层处拒绝（该层从未落地）时 `expanded_nodes` 可大于 `graph_nodes + Σ foreach 展开项`，差额即被拒的自动层；报告 SHALL 让调用方以 `headroom` 为准判断余量，SHALL NOT 要求其用 `graph_nodes` 反推 `expanded_nodes`；
- 报告 SHALL NOT 出现「`expanded_nodes` 恒等于 `graph_nodes + Σ foreach 展开项`」这类无条件等式陈述，因为它在「自动插层即撞闸」路径上不成立；若给出该关系，SHALL 附带成立条件（无被拒自动层时）；
- route 节点的条目 SHALL 含该节点的生效 `max_routes`，以及**闸门实际使用的**累计计数（SHALL 与调度器据以判定 `max_routes` 超限的计数同源，SHALL NOT 用另一个口径的计数）；
- 当模拟因**结构闸**中止时，报告 SHALL 附**结构化诊断**（至少含闸名与生效上限），其字段形状与挂载方式 SHALL 与真实运行中**模型可见的**诊断出口一致，SHALL NOT 把闸门原因只留在散文式的告警文本里。

结构闸的生效值字段 SHALL NOT 仅呈现声明值而隐藏钳制事实；当生效值与声明值不同时，两个值 SHALL 都可见。模拟路径若不施加配置级的钳制（即无 ceiling），报告 SHALL 如实呈现 `applied` 等于 `declared`，SHALL NOT 凭空捏造一个 `clamped` 为真的结论。报告 SHALL NOT 以「节点预算」的展开数暗示**动态闸**（`max_runs` / `recursion_limit`）的余量——那两项的消耗取决于运行期轮数，静态展开数不构成其上界。

诊断字段的挂载 SHALL 与真实运行模型可见出口同形：SHALL 在未命中任何结构闸时仍存在（为空对象），SHALL NOT 以「字段为空」为由省略该字段。报告 SHALL 让调用方能区分「诊断非空」与「撞了结构闸」——诊断可能携带与结构闸无关的记录，故调用方 SHALL 能据诊断内的闸名判定是否撞闸。

#### Scenario: 模拟不产生任何副作用

- **GIVEN** 一个真实 workspace 与一个真实的 `SubAgentManager`
- **WHEN** 对一张合法 spec 调用 `DryRunWorkflow`
- **THEN** 该 workspace SHALL NOT 新增任何文件
- **AND** 该 manager 的 workflow 注册表 SHALL 保持为空
- **AND** 该 manager 的真实 LLM SHALL 一次都没有被调用

#### Scenario: 失败节点带可解释原因

- **GIVEN** 一张模拟中某节点未正常结束的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告 SHALL 给出该节点异常结束的原因
- **AND** SHALL NOT 让调用方把「一个失败节点让 route 走了 default」误读为「这张图的 route 本来就该走 default」

#### Scenario: 聚合节点的产出不被模拟替身污染

- **GIVEN** 一张含 `collect` 聚合节点、且上游文本拼接后超出该节点预算的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告中该聚合节点的产出 SHALL 是上游文本的有界投影
- **AND** SHALL NOT 是模拟替身模型的回应文本

#### Scenario: 判定输入可归属到来源节点

- **GIVEN** 一张 `A → B → gate(route)` 的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告 SHALL 能指出 gate 的判定输入来自哪个节点
- **AND** SHALL NOT 只给出文本片段而需调用方自行比对推断

#### Scenario: 报告如实暴露 route 的判定输入

- **GIVEN** 一张形如 `A → B → gate(route)` 的图，其中 `A` 与 `B` 都是 subagent 节点
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告中 gate 的 `input_seen` SHALL 等于 `B` 自身产出的文本
- **AND** SHALL NOT 等于 `A` 的产出

#### Scenario: 报告暴露系统自动插入的汇合层

- **GIVEN** 一张扇入宽度足够大、会触发系统自动插入汇合层的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告中 SHALL 出现这些自动插入的节点
- **AND** SHALL 能把它们与模型声明的节点区分开
- **AND** SHALL NOT 让调用方以为「只有我声明的节点会跑」

#### Scenario: 报告区分 foreach 各展开项

- **GIVEN** 一个 foreach 节点展开出 3 个项，每个项的任务文本各不相同
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告中该节点的 `received` SHALL 让 3 个项各自的输入分别可见
- **AND** SHALL NOT 只保留其中一项

#### Scenario: 报告暴露被重派发节点在回边上收到的文本

- **GIVEN** 一张含 route 回边的循环图，其中回边指向循环体的起始节点
- **WHEN** 该循环执行多轮
- **THEN** 报告中该起始节点在每一轮的 `received` SHALL 分别可见
- **AND** 报告 SHALL 让调用方能看出回边是否向它投递了新的上游文本

#### Scenario: 有界性

- **GIVEN** 一张会产生超长节点产出的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告中的每个文本字段 SHALL 被截断到配置上界
- **AND** 截断 SHALL 有可见标记，SHALL NOT 静默丢弃

#### Scenario: 报告暴露结构闸的生效值

- **GIVEN** 一张未显式声明结构闸的 spec，其生效闸值来自当前配置
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告 SHALL 含一个覆盖 `recursion_limit` / `max_nodes` / `max_runs` 的生效值字段
- **AND** 每一项 SHALL 含 `declared` / `applied` / `clamped` 三个子字段
- **AND** 这些值 SHALL 与系统其余出口报出的同一 spec 的生效值一致

#### Scenario: 报告暴露自动插层与 foreach 展开造成的计费放大

- **GIVEN** 一张声明节点数为 N、含 foreach 节点（展开出若干项）、且扇入宽度可能触发系统自动插入汇合层的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告的节点预算字段 SHALL 给出 `declared` / `graph_nodes` / `expanded_nodes` / `auto_inserted` / `limit` 各值
- **AND** `expanded_nodes` SHALL 等于 `graph_nodes` 加该图所有 foreach 节点的展开项数之和（此时自动层已落地）
- **AND** 当展开项数大于 0 时 `expanded_nodes` SHALL 严格大于 `graph_nodes`
- **AND** 调用方 SHALL NOT 需要自行清点节点才能得出「闸门实际会计费多少」

#### Scenario: 自动插层即撞闸时基线不同仍如实

- **GIVEN** 一张在**自动插入汇合层**这一步就超出 `max_nodes` 的图（该自动层从未落地）
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** `graph_nodes` 与 `auto_inserted` SHALL 反映**已落地**的计划（不含被拒层）
- **AND** `expanded_nodes` SHALL 反映展开完成后的计费投影（含被拒层）
- **AND** `expanded_nodes` SHALL NOT 被要求等于 `graph_nodes + Σ foreach 展开项`
- **AND** `headroom` SHALL 为负，调用方据此判定已超限

#### Scenario: 撞闸图上节点预算不报正余量

- **GIVEN** 一张因 `max_nodes` 超限而中止的图（其 `expanded_nodes` 超过生效上限）
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告暴露的 `expanded_nodes` SHALL 反映**展开完成后的**计费规模（含被闸门拒绝的那次展开）
- **AND** `limit - expanded_nodes` SHALL NOT 为正
- **AND** SHALL NOT 让一张已经撞闸的图显示出「还有余量」

#### Scenario: 报告暴露 route 的生效 max_routes 与已用计数

- **GIVEN** 一张含 `route` 节点的图，该节点被求值并按闸门计数累计
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 该 route 的报告条目 SHALL 给出生效 `max_routes`
- **AND** SHALL 给出闸门实际使用的累计计数（与调度器判定 `max_routes` 超限所用的计数同源）

#### Scenario: 因结构闸中止时报告带结构化诊断

- **GIVEN** 一张在模拟中因 `max_nodes` 超限而中止的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告 SHALL 附一个结构化诊断，含闸名与生效上限
- **AND** 该诊断的形状 SHALL 与真实运行中模型可见的诊断出口一致
- **AND** SHALL NOT 仅以散文式告警文本呈现闸门原因

#### Scenario: 未撞闸时诊断字段仍与真实出口同形

- **GIVEN** 一张在模拟中跑到完成的图
- **WHEN** 调用 `DryRunWorkflow`
- **THEN** 报告的诊断字段 SHALL 存在（与真实运行模型可见出口同形）
- **AND** 未命中任何结构闸时该字段 SHALL 为空对象
- **AND** SHALL NOT 因「字段为空」而省略它（否则与真实出口分叉）

### Requirement: DeclareWorkflow 描述暴露循环契约

`DeclareWorkflow` 的工具描述 SHALL 说明有限循环的契约（原有条款不变，见当前 spec），并 SHALL 在描述中指向**可零成本预演拓扑与数据流**的手段——即当模型不确定一张图会如何路由、文本如何流动时，描述 SHALL 让它知道存在 `DryRunWorkflow` 可以在不调用模型、不产生副作用的前提下先行验证。

该指针 SHALL 简短（一句话量级），SHALL NOT 挤压既有的循环契约条款；`DryRunWorkflow` 自身的用法与边界说明 SHALL 由 `DryRunWorkflow` 自己的描述承担，SHALL NOT 重复写进 `DeclareWorkflow` 的描述。

描述 SHALL 披露**图级结构闸的默认值**（`recursion_limit` / `max_nodes` / `max_runs`），使模型在声明一张大图之前就能据此规划规模，SHALL NOT 让模型只能通过撞闸才发现闸门存在。该披露 SHALL 以**事实性的数值**呈现，SHALL NOT 用可被照抄的**示例**呈现（示例是模型学错的地方；默认值是域的一部分）。

该披露 SHALL 把数值表述为**模块默认值**（而非「你当前会话的生效值」），并 SHALL 说明部署可用配置覆盖、资产在更小配置下加载时会被钳制、**以工具报告出的生效值为准**——因为描述是静态文本而生效值随配置变化，把静态数值说成「当前默认」会与运行期报告分叉。披露 SHALL 明确限定为「图级」（graph-level），SHALL NOT 与路由节点级的 `max_routes` 默认值混淆。

描述披露 SHALL NOT 使描述超出既有的长度守卫上界。

#### Scenario: 声明入口引导到零成本预演

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它不确定自己将要声明的图会如何路由
- **THEN** 描述 SHALL 让它知道有 `DryRunWorkflow` 可用来先行验证
- **AND** 描述 SHALL NOT 因此丢失既有的循环契约条款（环可启动性 / 回边方向 / `max_routes` 语义）

#### Scenario: 声明入口披露图级闸默认值

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它准备声明一张节点数较多、可能触及图级上限的图
- **THEN** 描述 SHALL 给出 `recursion_limit` / `max_nodes` / `max_runs` 的默认值
- **AND** 描述 SHALL 说明这些值可在 spec 内覆盖
- **AND** 描述长度 SHALL 仍不超过既有长度守卫上界
