# multi-agent-collaboration spec delta: Workflow 结果聚合

## ADDED Requirements

### Requirement: result_ref 落盘 artifact

系统 SHALL 将 workflow 节点的完整结果/transcript 落盘到 workflow store，`result_ref` SHALL 指向文件路径；内存 SHALL 只持 bounded summary。`SubagentRunRecord` 的返回 SHALL 增 `summary_ref`/`transcript_ref`/`artifact_refs`。

#### Scenario: 完整结果落盘、内存只持摘要

- **GIVEN** 一个 workflow 节点完成并产出完整 transcript
- **WHEN** 该节点结果被记录
- **THEN** 系统 SHALL 将完整结果落盘
- **AND** 内存中 SHALL 只持 bounded summary + result_ref

### Requirement: 树状分层汇聚

系统 SHALL 支持树状汇聚：模型显式声明 aggregate 树（leaf→shard→domain→root）；调度器 SHALL 在「单 aggregate 直接上游 >10」或「总叶子数 >10」时自动插入分层 aggregate。每层输出 SHALL 遵守 token 预算（leaf 300 / shard 800 / domain 1500 / root 3000，可配置）。

#### Scenario: 上百个叶子不撑爆父上下文

- **GIVEN** 一个含 100 个叶子节点的 workflow
- **WHEN** 汇聚执行
- **THEN** 系统 SHALL 分层汇聚
- **AND** 父 agent 上下文 SHALL NOT 被 100 个完整结果注入

### Requirement: 父 agent 永远 bounded envelope

父 agent SHALL 只接收 bounded envelope（workflow_id/status/completed/failed/pending/root_result_ref），SHALL NOT 默认接收子级详细结果；子级结果 SHALL 通过显式 inspect（GetWorkflow detail 参数 / InspectSubagentTranscript）按需读取。

#### Scenario: 父 agent 收 bounded envelope

- **GIVEN** 一个 workflow 完成
- **WHEN** 父 agent 获取结果
- **THEN** 系统 SHALL 返回 bounded envelope
- **AND** SHALL NOT 默认展开子级详细结果

### Requirement: bus 降级为非权威

MessageBus SHALL 只承担低延迟广播/非关键提示；权威状态、依赖完成、结果完整性、重试、重放 SHALL 进 workflow store/事件日志。bus 丢消息 SHALL NOT 影响 workflow 完成与结果正确性。

#### Scenario: bus 丢消息不影响结果

- **GIVEN** 协作中的子 agent 通过 bus 广播一条非关键提示
- **WHEN** 该消息因队列满被丢弃
- **THEN** workflow SHALL 仍正常完成
- **AND** 结果正确性 SHALL NOT 受影响
