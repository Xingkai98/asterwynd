## MODIFIED Requirements

### Requirement: 子 transcript inspect 默认受限

系统 SHALL 通过专用 inspect 接口提供子 transcript 摘要或最近消息读取，但 SHALL 默认限制返回范围。

「限制返回范围」SHALL 同时覆盖**条数**与**单条内容长度**两个维度：任一条返回文本（消息 `content`、
摘要 `summary`、工具调用 `arguments`）SHALL 不超过一个固定上限，且该上限 SHALL 与 HTTP 出口
（workflow 节点 transcript 只读接口）的对应上限**同值**——同一份 inspect 结果在模型面与 HTTP 面
SHALL NOT 分叉。

被截断的字段 SHALL 伴随一个**布尔**截断标志（`content_truncated` / `summary_truncated` /
`arguments_truncated`），SHALL NOT 依赖调用方用长度比较自行推断。标志 SHALL 表达「本条是否发生过
截断」这一事实，跨层组合时 SHALL 取或（上游截过而下游预算更宽时 SHALL NOT 报未截断）。

全文 SHALL 通过显式引用（result_ref / summary_ref / ReadWorkflowResult）按需读取，SHALL NOT 要求
模型面出口默认返回全文。

#### Scenario: 查看最近消息

- **GIVEN** 父 agent 需要检查某个子 run 最近的执行情况
- **WHEN** 调用 `InspectSubagentTranscript`
- **THEN** 系统 SHALL 返回摘要或最近 `N` 条消息
- **AND** SHALL NOT 默认返回整份子 transcript

#### Scenario: 超长单条内容在模型面被截断

- **GIVEN** 子 run 的某条消息 content 远超单条上限（例如 30,000 字）
- **WHEN** 父 agent 调用 `InspectSubagentTranscript` 读取最近消息
- **THEN** 返回的该条 `content` SHALL 不超过单条上限
- **AND** 该条 SHALL 携带 `content_truncated` 为 `true`

#### Scenario: 超长摘要同样受限

- **GIVEN** 子 run 的 summary 远超单条上限
- **WHEN** 调用 `InspectSubagentTranscript` 且 `scope` 为 `summary`
- **THEN** 返回的 `summary` SHALL 不超过单条上限
- **AND** SHALL 携带 `summary_truncated` 为 `true`

#### Scenario: 工具结果消息与普通消息同口径

- **GIVEN** 子 run 含一条超长的 tool 角色消息（工具结果全文）
- **WHEN** 调用方显式请求包含工具结果（`include_tool_results=true`）
- **THEN** 该条 `content` SHALL 与普通消息**适用同一个单条上限**
- **AND** SHALL 携带 `content_truncated` 为 `true`

#### Scenario: 模型面与 HTTP 面同值

- **GIVEN** 同一份 inspect 结果分别经模型面工具与 HTTP 路由出口返回
- **WHEN** 比较两侧对同一字段的上限
- **THEN** 两个上限 SHALL 相等
- **AND** 该相等关系 SHALL 有测试机械锁定（SHALL NOT 只靠注释约定）
