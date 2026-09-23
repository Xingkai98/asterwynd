## ADDED Requirements

### Requirement: workflow 节点失败证据只读投影

Web 服务的 workflow 节点 transcript 只读接口 SHALL 在同一个载荷中提供该 run 的**失败证据**投影（bounded），数据来源 SHALL 是该 run 的执行 trace（`run.trace.steps`）中 `status` 不为 `ok` 的 `tool_result` step 与全部 `llm_error` step；该投影 SHALL NOT 新增采集、SHALL NOT 调用 LLM、SHALL NOT 写盘或改变 workflow 执行状态。

「无失败证据」SHALL 用显式**状态枚举**区分成因，SHALL NOT 把「没有 trace」与「trace 里没有失败步骤」折叠成同一个状态——用户在后者可以放心，在前者不能。

投影 SHALL bounded：只返回**最近** `N` 条失败条目，每条的可变长文本 SHALL 不超过节点 transcript 的单条内容上限，超出 SHALL 置对应的截断标志，并 SHALL 附上失败总数与「是否被截断」两个标量，使调用方不必靠长度比较推断。

被截断或不可用时 SHALL 给出**可读的原因文案**，SHALL NOT 只给空列表或 `null`。

#### Scenario: run 完成但中途有工具失败

- **GIVEN** 某个 subagent run 已到终态 `completed`，其 trace 中存在 `status` 为 `error` 的 `tool_result` step（例如一次失败的 `Bash`）
- **WHEN** 请求该节点的 transcript
- **THEN** 载荷 SHALL 携带失败证据，状态为「有失败证据」
- **AND** 每条条目 SHALL 至少包含工具名、trace 步骤序号、`status` 与 `error_type`
- **AND** `observation` SHALL 不超过单条内容上限，超出时 SHALL 置 `observation_truncated` 为 `true`

#### Scenario: trace 存在且没有任何失败步骤

- **GIVEN** run 已到终态，其 trace 存在且 `steps` 非空，但没有任何 `status` 不为 `ok` 的 `tool_result`、也没有 `llm_error`
- **WHEN** 请求该节点的 transcript
- **THEN** 失败证据 SHALL 报告「已检查、未发现失败」，SHALL NOT 报告「无 trace」
- **AND** 条目列表 SHALL 为空，且 SHALL 带一个说清「已检查过」的原因文案

#### Scenario: run 仍在运行

- **GIVEN** run 尚未到终态（trace 按设计只在终态写入）
- **WHEN** 请求该节点的 transcript
- **THEN** 失败证据 SHALL 报告「运行中，尚无失败证据」，SHALL NOT 报告「没有失败」
- **AND** SHALL NOT 因 trace 为 `None` 而报「未记录 trace」

#### Scenario: run 到终态但从未记录 trace

- **GIVEN** run 已到终态，且 `run.trace` 为 `None`（该 run 从未开始执行，或写入 trace 的路径在 trace 缺失时写入了 `None`）
- **WHEN** 请求该节点的 transcript
- **THEN** 失败证据 SHALL 报告「未记录执行 trace」，SHALL NOT 报告「没有失败」
- **AND** 原因文案 SHALL 说明这是「没有采集到」而不是「采集到了、是空的」

#### Scenario: trace 存在但该 run 没有执行过任何步骤

- **GIVEN** run 已到终态，其 trace 存在但 `steps` 为空（run 在排队阶段被取消，取消时新建了一个空 trace）
- **WHEN** 请求该节点的 transcript
- **THEN** 失败证据 SHALL 报告「该 run 未执行任何步骤」，SHALL NOT 报告「未记录 trace」
- **AND** 该状态 SHALL 与「未记录 trace」是两个不同的取值

#### Scenario: 解析不到该节点的 run 记录

- **GIVEN** 节点对应的 run 记录已不在 session 的 runs 列表里（例如被队列上限拒绝、记录已弹出）
- **WHEN** 请求该节点的 transcript
- **THEN** 失败证据 SHALL 报告「无法解析该 run」，SHALL NOT 报告「没有失败」
- **AND** 该状态 SHALL 与「未记录执行 trace」是两个不同的取值

#### Scenario: 失败条目超过上限

- **GIVEN** 某 run 的 trace 中有多于 `N` 条失败步骤
- **WHEN** 请求该节点的 transcript
- **THEN** 返回的条目 SHALL 不超过 `N` 条
- **AND** SHALL 返回失败总数，且「被截断」标志 SHALL 为 `true`
- **AND** 返回的条目 SHALL 是**最近**的 `N` 条（按 trace 步骤序号），显示顺序 SHALL 为时间正序
