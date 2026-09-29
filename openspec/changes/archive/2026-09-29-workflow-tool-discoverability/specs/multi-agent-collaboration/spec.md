# multi-agent-collaboration spec delta: Workflow 工具面可发现性

## MODIFIED Requirements

### Requirement: DeclareWorkflow 描述暴露循环契约

`DeclareWorkflow` 的工具描述 SHALL 说明有限循环的契约，SHALL 至少覆盖：

- **环里必须有个节点先跑起来，且它不能反过来等环里的节点**，否则环内所有节点互等、一个都跑不起来（声明期会被拒绝）
- 回边应从 `route` 出发（`route` 出边是控制边，不参与门控）；从其它节点出发的回边是数据边、默认门控，须显式声明 `"required": false`
- `max_routes` 的默认值为 `1`，且只能在节点上逐节点声明
- `max_routes` 的计数是节点级、跨轮累加、不因新一轮循环而重置

描述 SHALL 附**最小正确示例与反例**，SHALL NOT 仅罗列规则。

描述 SHALL 同时覆盖以下**工具面可发现性**条款，SHALL NOT 让模型只能靠试错或读源码常量才能得知：

- **`cases` 的匹配语义**：匹配是**行首前缀匹配**（对上游每一行的、去前导空白的行首做 `startswith`），SHALL NOT 被描述为子串包含；多 case SHALL 按**声明顺序 first-match-wins**；因此描述 SHALL 明确要求**具体/更长的模式排在宽泛模式之前**，并 SHALL 给出该排序的正例与反例。
- **`when` 的两种形态**：字面标签（大小写无关）与 `$ref:<node_id>:<slot>` 动态条件源（取槽值首个非空行作期望标签），并 SHALL 说明槽缺失时走 `default`。
- **门控与传输渠道的正交性**：一条边是否门控下游 SHALL 由**发起节点的 kind** 决定（`route` 出边是控制边、不门控；其它节点出边是数据边、默认门控），SHALL NOT 被描述为与边的 `channel` 取值相关。`channel` 描述数据以何种形式传给下游，其合法值 SHALL 在 schema 中枚举（见「Workflow spec schema 的封闭取值从单一来源派生」）。
- **按节点 kind 的字段适用性**：描述 SHALL 说明哪些字段属于哪种 kind（至少覆盖 `join`/`strategy`/`deadline_s` 属 `aggregate`，`cases`/`default`/`max_routes` 属 `route`，`items`/`source`/`source_field`/`max_items` 属 `foreach`），SHALL NOT 只靠示例里的节点 id 隐式暗示。

描述 SHALL NOT 出现**任何非法枚举值**（尤其是会让 `DeclareWorkflow` 直接拒绝的 `channel` 取值）；描述里出现的每个示例 SHALL 是可成功声明的。

#### Scenario: 描述含循环契约

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它需要构造一个有限循环
- **THEN** 描述 SHALL 能回答「环里的节点要满足什么条件才转得起来」「回边从哪出发」「`max_routes` 默认几、在哪配、怎么计数」
- **AND** 描述 SHALL 给出一个能启用的最小正例与一个会被拒绝的最小反例

#### Scenario: 描述含 cases 匹配语义

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它需要写一个「评审不通过就回边重做」的 `route` 节点，上游文本可能是 `GAPS` 或 `GAPS: none`
- **THEN** 描述 SHALL 说明匹配是行首前缀匹配、按声明顺序 first-match-wins
- **AND** 描述 SHALL 给出「具体模式排在宽泛模式之前」的正例（`"GAPS: none"` 在 `"GAPS"` 之前）与反例（宽泛在前会让 `"GAPS"` 永久命中、每轮都回边直至 `max_routes` 超限）

#### Scenario: 描述不把门控与 channel 混为一谈

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它想知道「怎样让一条回边不参与门控」
- **THEN** 描述 SHALL 回答「由发起节点是 `route` 决定」，SHALL NOT 回答「把 `channel` 写成某个值」
- **AND** 描述中的示例 SHALL NOT 使用任何不属于 `channel` 合法枚举的取值

#### Scenario: 描述暴露按 kind 的字段适用性

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它需要给一个 `aggregate` 节点声明汇合语义
- **THEN** 描述 SHALL 让模型知道存在 `join` 字段且该字段属于 `aggregate`
- **AND** 模型 SHALL NOT 需要从相邻字段（如 `reducer` 的取值）猜测该字段的合法值

## ADDED Requirements

### Requirement: Workflow spec schema 的封闭取值从单一来源派生

`DeclareWorkflow` 与 `RunWorkflow` 的 `spec` 参数 SHALL 以**嵌套 JSON Schema**（`properties` / `items` / `enum`）暴露 workflow DSL 的结构，SHALL NOT 只声明为无结构的 `{"type": "object"}`。至少以下封闭取值集合 SHALL 以 `enum` 出现在 schema 中：节点 `kind`、边的 `channel`、边的 `reducer`、`aggregate` 的 `strategy`、`aggregate` 的 `join`、节点的 `mode`。

这些 `enum` SHALL **从 `agent/subagent/workflow.py` 的源码常量派生**，SHALL NOT 在工具层手写第二份字面量。可派生集合 SHALL 包含至少一个模块级常量出口（`mode` 的合法值 SHALL 从既有内联元组提升为模块常量，供校验与 schema 共用）。

系统 SHALL 提供测试，断言 schema 中每个 `enum` 与其源码常量**逐字相等**（元素与顺序），使「schema 与常量一致」成为机械可验的性质，SHALL NOT 依赖人工同步。

#### Scenario: schema 暴露枚举

- **GIVEN** 模型在调用前读取 `DeclareWorkflow` 的 `spec` 参数 schema
- **WHEN** 它需要给一条边写 `channel`
- **THEN** schema SHALL 在动笔前就让它看到 `result_ref` / `summary` / `artifact` / `bus` 四个合法值
- **AND** SHALL NOT 出现任何非法的 `channel` 取值（如 `control`）

#### Scenario: 枚举与源码常量一致性可机械校验

- **GIVEN** 一个把 `CHANNELS` 常量临时改成不同元组的变异
- **WHEN** 运行 schema 一致性测试
- **THEN** 测试 SHALL 失败
- **AND** 未变异时该测试 SHALL 通过

#### Scenario: 两条声明入口的 spec schema 一致

- **GIVEN** `DeclareWorkflow` 与 `RunWorkflow` 都接受 `spec` 参数
- **WHEN** 比较两者的 `spec` schema
- **THEN** 它们的嵌套结构与 enum 集合 SHALL 一致（同一份派生结果）
