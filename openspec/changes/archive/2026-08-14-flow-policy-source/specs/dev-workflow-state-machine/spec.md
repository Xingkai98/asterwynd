# dev-workflow-state-machine 规格 delta

## ADDED Requirements

### Requirement: 开发流程策略单一源

系统 SHALL 将受保护路径治理规则收敛到单一策略文件 `scripts/flow-policy.json`，作为 guard（PreToolUse hook）与 CI artifact checker 的共同规则来源。该文件 SHALL 以 JSON 承载受保护路径规则表，每条规则 SHALL 声明 `match_type(exact|prefix|contains)`、`governance(guard_only|event_explained|manifest_verified|cli_written)` 与可空 `event_types`。系统 SHALL 禁止 agent 直接改写该策略文件（governance=cli_written），仅允许人类直改或 `policy-*` CLI 子命令更新。

#### Scenario: guard 与 checker 同源加载受保护路径规则

- **WHEN** guard 或 checker 需要判断某路径是否受保护
- **THEN** 系统 SHALL 从 `scripts/flow-policy.json` 读取规则表，而不再使用各自硬编码的独立清单
- **AND** guard 与 checker 对同一路径 SHALL 得出一致的受保护判定

#### Scenario: 策略文件缺失或损坏时 guard fail-closed

- **GIVEN** `scripts/flow-policy.json` 缺失、损坏或非法
- **WHEN** guard 拦截代码写操作
- **THEN** guard SHALL fail-closed（exit 2），不得静默放行
- **AND** guard SHALL 在错误信息中指明策略文件问题与恢复方向

#### Scenario: 策略文件规则与 guard 内嵌默认表保持一致

- **WHEN** 运行 parity 测试
- **THEN** 磁盘上的 `flow-policy.json` 规则表 SHALL 与 guard 源码内嵌的默认规则表一致
- **AND** checker 的受保护路径规则集 SHALL 是策略表 `event_explained` 子集

### Requirement: guard 写操作门禁顺序与路径归一化

guard 对 Bash 命令 SHALL 在 is_write 判定之前先扫描受保护路径；对 Write/Edit 的 `file_path` SHALL 先做路径归一化（normpath / 剥离 `./`、解析 `..`）再按 match_type 匹配。已知绕过形态（`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./` 变体）SHALL 被拦截。

#### Scenario: Bash 命令绕过受保护路径被拦截

- **GIVEN** Bash 命令尝试改写受保护 artifact 但未命中既有写模式（如 `cat <<EOF`、`python3 -c "Path(...).write_text(...)"`）
- **WHEN** 命令文本包含受保护路径片段
- **THEN** guard SHALL 拦截（exit 2），不受 is_write 判定前置影响

#### Scenario: 归一化变体写入受保护路径被拦截

- **GIVEN** Write/Edit 或 Bash 使用 `docs/./known-debt.md` 等归一化变体路径
- **WHEN** 目标指向受保护 artifact
- **THEN** guard SHALL 在路径归一化后拦截（exit 2）

### Requirement: 内容门槛阶段感知

CI artifact checker 对 `Reference Implementation Research` 字段的检查 SHALL 区分结构门槛与内容门槛：change 处于 proposal 阶段时 SHALL 只要求 section 存在且非空；tasks 全部勾选（实现完成）时 SHALL 额外检查「自认未完成」短语级模式，命中 SHALL 报错（exit 2）并指明命中短语与字段。

#### Scenario: 实现完成的 change 含自认未完成占位

- **GIVEN** 一个 change 的 tasks 全部勾选
- **WHEN** 其 Reference Implementation Research 字段包含「尚未完成」「待补充」等自认未完成短语
- **THEN** checker SHALL exit 2
- **AND** 错误信息 SHALL 指明命中短语与所在字段

#### Scenario: proposal 阶段含占位不触发内容门槛

- **GIVEN** 一个 change 处于 proposal 阶段（tasks 未全勾）
- **WHEN** 其 Reference Implementation Research 字段含占位文本
- **THEN** checker SHALL 只按结构门槛检查（section 存在 + 非空），不触发内容门槛报错

### Requirement: 阶段执行者 agent schema 定义

`scripts/flow-policy.json` SHALL 支持可选的 `phases.<phase>.agent = {provider, model}` 与顶层 `review.agent` 声明，用于表达每阶段与审阅节点的执行者选择。本 requirement 只定义 schema 并做结构校验，不实现按阶段 spawn 执行者（后续阶段实现）。

#### Scenario: 合法 agent schema 通过校验

- **GIVEN** `flow-policy.json` 声明 `phases.building.agent` 或 `review.agent`，字段为合法 provider/model 字符串
- **WHEN** 运行 artifact checker
- **THEN** checker SHALL 通过 schema 校验

#### Scenario: 非法 agent schema 被拒绝

- **GIVEN** `flow-policy.json` 声明未知 phase 键、非字符串 provider/model 或额外未知字段
- **WHEN** 运行 artifact checker
- **THEN** checker SHALL 报错并指明非法字段

## MODIFIED Requirements

### Modified: Protected artifact 变更解释

受保护路径清单的来源从 checker 硬编码 `PROTECTED_PATH_RULES` 改为 `scripts/flow-policy.json` 中 `governance == event_explained` 的规则子集。checker SHALL 从策略文件加载受保护路径与事件类型映射，保持「受保护 artifact 变更需 workflow-events.jsonl 结构化解释事件」的既有执法语义不变。
