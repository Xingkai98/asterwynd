## MODIFIED Requirements

### Requirement: 父 run 通过显式运行时接口管理子 session

父 AgentLoop SHALL 通过显式运行时接口创建、启动、查询、等待、取消和检查子 session / 子 run，而不是通过自动消息注入或伪造 tool result 把子结果并入父 messages。

这些接口返回给**模型面**的 run envelope SHALL bounded：`summary` 字段 SHALL 不超过该 run 的摘要预算，
SHALL NOT 默认返回子 agent 的全文输出。全文 SHALL 通过 envelope 里的显式引用（`result_ref` /
`summary_ref`）按需读取。

bounded 化 SHALL 只发生在**出口投影**：run 记录本身 SHALL 保留全文（下游聚合依赖它）。
调度器等内部消费方 SHALL 能显式取得全量 summary，SHALL NOT 因出口 bounded 而丢失聚合输入。

截断发生时返回体 SHALL 说明这一点（截断标记 / 可导航的引用），SHALL NOT 出现「声称全文在某个引用、
而该引用不存在」的表述。

#### Scenario: 父 run 查询子 run 结果

- **GIVEN** 一个已存在的子 session 和其最近一次子 run
- **WHEN** 父 agent 调用 `GetSubagentRun`
- **THEN** 系统 SHALL 返回结构化结果
- **AND** SHALL NOT 直接修改父 run 的 messages transcript

#### Scenario: 超长子 agent 输出在模型面被 bounded

- **GIVEN** 子 run 输出了远超摘要预算的文本（例如 30,000 字）
- **WHEN** 父 agent 调用 `GetSubagentRun`
- **THEN** 返回的 `summary` SHALL 不超过摘要预算
- **AND** 返回体 SHALL 提供可取回全文的引用
- **AND** run 记录本身的 `summary` SHALL 仍为全文（受影响的是出口投影，不是记录）

#### Scenario: 截断标记不指向不存在的引用

- **GIVEN** 一个没有 workflow 身份、因而全文未落盘的子 run，其输出超过摘要预算
- **WHEN** 该 run 的结果经模型面出口返回
- **THEN** 截断相关的文本 SHALL NOT 声称全文可从某个引用取得
- **AND** SHALL 仍然如实表达「内容已被截断」

#### Scenario: 调度器内部消费仍取全量

- **GIVEN** 一个 workflow 节点由子 run 的结果驱动，其输出超过摘要预算
- **WHEN** 调度器读取该 run 的结果用于下游聚合
- **THEN** 调度器 SHALL 取得**全量** summary
- **AND** SHALL NOT 使用被出口投影截断后的版本
