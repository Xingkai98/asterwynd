# multi-agent-collaboration spec delta: DryRunWorkflow

## ADDED Requirements

### Requirement: 工作流可零成本模拟执行以暴露数据投递语义

系统 SHALL 提供一个只读工具 `DryRunWorkflow`，接受与 `DeclareWorkflow` 相同的 `spec` 参数，对给定 spec 执行**模拟**，并返回数据投递报告。

模拟 SHALL NOT 调用真实 LLM（真实 provider 的调用次数 SHALL 为 0），SHALL NOT 向 workspace 写入任何文件，SHALL NOT 把模拟的 workflow 注册进 `SubAgentManager` 的 workflow 注册表，SHALL NOT 触达任何图事件 sink。这些隔离性质 SHALL 由测试机械锁定，SHALL NOT 仅靠实现约定。

模拟 SHALL 复用既有的调度执行路径（门控、reducer、route 匹配、foreach 展开、循环计数），SHALL NOT 另起一套与真实执行可能漂移的模拟逻辑。

模拟 SHALL NOT 让「语义压缩型」的聚合行为污染报告：聚合节点在报告中呈现的产出 SHALL 是**上游文本的有界投影**，SHALL NOT 是模拟替身（fake LLM）对压缩请求的回应。报告 SHALL 说明该产出是投影而非真实运行时的语义压缩结果。

模拟 SHALL 让每一次替身模型调用都可归因到某个节点；SHALL NOT 出现无法归属到任何节点的调用记录。

报告 SHALL 至少包含：

- 每个节点的 `id` / `kind` / 终态 `status` / 被执行的 `runs` 次数 / 产出 `produced`。节点集合 SHALL 基于实际执行计划（含系统自动插入的汇合层），SHALL NOT 只列出模型声明的节点；执行计划中由系统自动插入的节点 SHALL 可被识别（与声明节点区分）；
- route 节点：判定输入 `input_seen`（SHALL 与调度器实际用于匹配的文本同源）、命中的标签 `matched`、实际走到的后继 `walked_to`、是否走了 `default`；判定输入的**来源节点** SHALL 可识别（SHALL NOT 只给文本而不给归属）；
- 每个节点的 `received`——该节点实际收到的任务文本（SHALL 反映上游投递与 foreach 项注入的净效果）。对被 foreach 展开的节点，`received` SHALL 按**展开项**分别可见，SHALL NOT 让多个项的输入坍缩为单一值；
- 每条边的 `from` / `to` / `channel`，以及该边是否为控制边（route 出边）；
- 一个显式标记该结果为模拟的字段。

报告中的文本字段 SHALL 有界（按可配置上界截断），SHALL NOT 把不带截断的聚合槽全文返回。

#### Scenario: 模拟不产生任何副作用

- **GIVEN** 一个真实 workspace 与一个真实的 `SubAgentManager`
- **WHEN** 对一张合法 spec 调用 `DryRunWorkflow`
- **THEN** 该 workspace SHALL NOT 新增任何文件
- **AND** 该 manager 的 workflow 注册表 SHALL 保持为空
- **AND** 该 manager 的真实 LLM SHALL 一次都没有被调用

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

### Requirement: 模拟结果 SHALL 声明其可信边界

`DryRunWorkflow` 的模拟结果 SHALL 让调用方能够区分「可信的结论」与「不可信的结论」，SHALL NOT 仅凭一个看起来完整的产出字段让调用方误以为图已被真实执行。

工具的 `description` SHALL 以**可判定的断言**说明该工具不调用模型、不写入任何内容；结果体 SHALL 包含一个固定字段显式标记结果为模拟。结果体 SHALL NOT 包含任何可被后续工具（`StartWorkflow` / `GetWorkflow` / `RunWorkflow`）消费的 workflow 标识符。

#### Scenario: 结果体携带模拟标记且无可消费标识符

- **GIVEN** 一次 `DryRunWorkflow` 调用
- **WHEN** 检查其返回体
- **THEN** 返回体 SHALL 含一个显式的模拟标记字段
- **AND** 返回体 SHALL NOT 含 `workflow_id`

#### Scenario: 描述含断言式的无副作用声明

- **GIVEN** 模型读取 `DryRunWorkflow` 的工具描述
- **WHEN** 它考虑是否该调用
- **THEN** 描述 SHALL 明确该调用不产生模型调用与写盘

### Requirement: 工作流模拟可通过脚本指定节点产出以推演分支

`DryRunWorkflow` SHALL 接受一个可选的 `script` 参数，允许调用方按节点指定该节点的模拟产出，从而推演「若该节点输出为 X，图会往哪里走」。

未在 `script` 中指定的节点 SHALL 使用默认行为——回显其收到的任务文本并标注该产出为模拟占位，SHALL NOT 编造一个看似真实的业务产出。

`script` 的键 SHALL 是节点 id；工具 SHALL 说明该参数对不产生 run 的节点（route / collect 聚合）不生效。

#### Scenario: 脚本注入改变 route 走向

- **GIVEN** 一张含 route 的图，其 route 的一个 case 匹配标签 `GAPS`
- **WHEN** 调用方提供 `script` 使 route 的上游节点产出 `GAPS`
- **THEN** 报告 SHALL 显示 route 命中该 case
- **AND** 报告 SHALL 显示 route 走到该 case 指向的后继
- **AND** 未提供 `script` 时同一张图 SHALL 显示 route 走了 `default`

#### Scenario: 未注入的节点产出被标注为占位

- **GIVEN** 一次未对某节点提供 `script` 的模拟
- **WHEN** 检查该节点的 `produced`
- **THEN** 该值 SHALL 可被识别为模拟占位
- **AND** SHALL NOT 被呈现为真实模型产出
