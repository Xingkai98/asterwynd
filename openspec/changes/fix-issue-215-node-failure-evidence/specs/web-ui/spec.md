## ADDED Requirements

### Requirement: workflow 节点失败证据只读投影

Web 服务的 workflow 节点 transcript 只读接口 SHALL 在同一个载荷中以键名 `failure_evidence` 提供该 run 的**失败证据**投影（bounded）——`candidates` 容器形态下该键 SHALL 挂在**每个候选**上而不是容器顶层（容器没有单一的 run，见下方该 Scenario），数据来源 SHALL 是该 run 的执行 trace（`run.trace.steps`）中 `status` 不为 `ok` 的 `tool_result` step 与全部 `llm_error` step；该投影 SHALL NOT 新增采集、SHALL NOT 调用 LLM、SHALL NOT 写盘或改变 workflow 执行状态。

`failure_evidence` SHALL 含 `state`（节点级状态枚举）、`total`（**真实失败总数**，不是返回条数）、`truncated`（布尔，`total` 是否大于返回条数）、`message`（可读原因文案）与 `items`（条目列表）。

`state` 的取值集合 SHALL 为且仅为：`present`、`clean`、`running`、`empty_trace`、`no_trace`、`unavailable`、`not_applicable`。该枚举 SHALL NOT 把「没有 trace」与「trace 里没有失败步骤」折叠成同一个取值——用户在后者可以放心，在前者不能；`not_applicable`（结构上不可能产生 run）SHALL NOT 与 `unavailable`（本该有 run 但取不到）折叠。

`items` 的每条 SHALL 含 `type`（`tool_result` 或 `llm_error`）、`step`（trace 步骤序号）、`status`、`error_type`、`tool_name`（`llm_error` 条目为 `null`）、`text_truncated`（布尔），并按条目类型二选一携带文本：`tool_result` 条目 SHALL 用 `observation`，`llm_error` 条目 SHALL 用 `message`。`llm_error` 的 trace step 不携带 `status` 字段，其条目 `status` SHALL 由投影固定为 `"error"`。

投影 SHALL bounded：`items` 只含**最近** `N` 条失败条目（按 trace 步骤序号），且每条的可变长文本 SHALL 不超过节点 transcript 的单条内容上限（`content_limit`），超出 SHALL 置 `text_truncated` 为 `true` 并把文本截到该上限。「是否被截断」SHALL 由 `truncated` 标量给出，使调用方不必靠长度比较推断。

被截断或不可用时 SHALL 给出**可读的原因文案**（`message`），SHALL NOT 只给空列表或 `null`。

该投影 SHALL NOT 改变前端取数时机：前端 SHALL 保持「切到『对话』tab 才请求该载荷」的懒加载行为。

#### Scenario: run 完成但中途有工具失败

- **GIVEN** 某个 subagent run 已到终态 `completed`，其 trace 中存在 `status` 为 `error` 的 `tool_result` step（例如一次失败的 `Bash`）
- **WHEN** 请求该节点的 transcript
- **THEN** 载荷 SHALL 携带 `failure_evidence`，其 `state` SHALL 为 `present`
- **AND** 每条条目 SHALL 至少包含 `tool_name`、`step`、`status` 与 `error_type`
- **AND** 条目的变长文本 SHALL 不超过单条内容上限，超出时 SHALL 置 `text_truncated` 为 `true`

#### Scenario: trace 存在且没有任何失败步骤

- **GIVEN** run 已到终态，其 trace 存在且 `steps` 非空，但没有任何 `status` 不为 `ok` 的 `tool_result`、也没有 `llm_error`
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `clean`（「已检查、未发现失败」），SHALL NOT 为 `no_trace`
- **AND** `items` SHALL 为空，且 SHALL 带一个说清「已检查过」的 `message`

#### Scenario: run 仍在运行

- **GIVEN** run 尚未到终态（trace 按设计只在终态写入）
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `running`（「运行中，尚无失败证据」），SHALL NOT 为 `clean`
- **AND** SHALL NOT 因 trace 为 `None` 而报 `no_trace`

#### Scenario: run 到终态但从未记录 trace

- **GIVEN** run 已到终态，且 `run.trace` 为 `None`
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `no_trace`（「未记录执行 trace」），SHALL NOT 为 `clean`
- **AND** `message` SHALL 说明这是「没有采集到」而不是「采集到了、是空的」

#### Scenario: trace 存在但该 run 没有执行过任何步骤

- **GIVEN** run 已到终态，其 trace 存在但 `steps` 为空（run 在排队阶段被取消、或取消路径新建了空 trace）
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `empty_trace`（「该 run 未执行任何步骤」），SHALL NOT 为 `no_trace`、SHALL NOT 为 `clean`
- **AND** 该取值 SHALL 与 `no_trace` 是两个不同的取值

#### Scenario: 解析不到该节点的 run 记录

- **GIVEN** 节点本该有 run，但对应 run 记录已不在 session 的 runs 列表里（例如被队列上限拒绝而弹出），或节点尚未派发
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `unavailable`（「无法解析该 run」），SHALL NOT 为 `clean`
- **AND** 该取值 SHALL 与 `no_trace` 是两个不同的取值

#### Scenario: 结构上不可能产生 run 的节点

- **GIVEN** 该节点是 route 节点，或是 `aggregate(strategy="collect")` 纯逻辑聚合节点
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `not_applicable`，SHALL NOT 为 `unavailable`
- **AND** `message` SHALL 说明该节点类型不产生 run

#### Scenario: 失败条目超过上限

- **GIVEN** 某 run 的 trace 中有多于 `N` 条失败步骤
- **WHEN** 请求该节点的 transcript
- **THEN** `items` 的条数 SHALL 不超过 `N`
- **AND** `total` SHALL 为**真实失败总数**（大于返回条数），且 `truncated` SHALL 为 `true`
- **AND** 返回的条目 SHALL 是**最近**的 `N` 条（按 trace 步骤序号），显示顺序 SHALL 为时间正序

#### Scenario: 候选集形态只带轻量证据

- **GIVEN** 某个 foreach 容器节点展开出多个候选，每个候选各自有 run
- **WHEN** 请求该容器节点的 transcript
- **THEN** 每个候选 SHALL 各自携带 `failure_evidence`，且其为**轻量**形态：`state` / `total` / `truncated` 齐全，`items` SHALL 至多 1 条最新失败条目且该条文本 SHALL 不超过 400 字符
- **AND** 候选项下钻（指名 `subagent_id`）时，载荷顶层的 `failure_evidence` SHALL 为**完整**形态（最近 `N` 条 × 单条内容上限），SHALL NOT 被轻量上限约束
