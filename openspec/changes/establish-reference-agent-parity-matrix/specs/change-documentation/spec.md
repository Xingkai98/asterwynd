## ADDED Requirements

### Requirement: 维护 Reference Agent 对标矩阵

项目 SHALL 维护一份 reference-agent parity artifact，用于记录主流 coding agent 能力与 Asterwynd 能力、证据和后续 OpenSpec change 之间的映射关系。

#### Scenario: 记录对标能力项

- **GIVEN** 维护者新增或更新一个对标能力项
- **WHEN** 该能力项进入 reference-agent parity artifact
- **THEN** 条目 SHALL 记录参考对象、来源链接、参考能力描述、Asterwynd 状态、Asterwynd 证据、缺口优先级、后续 change 和核对日期
- **AND** Asterwynd 状态 SHALL 使用 `supported`、`equivalent`、`partial`、`gap` 或 `out_of_scope`

#### Scenario: 标记已有或等价能力

- **GIVEN** 某个对标能力项被标记为 `supported` 或 `equivalent`
- **WHEN** 维护者检查该条目
- **THEN** 条目 SHALL 链接到规格、代码、测试、benchmark、trace 或运行证据中的至少一种
- **AND** 不得只凭自然语言断言声称已支持

#### Scenario: 标记能力缺口

- **GIVEN** 某个对标能力项被标记为 `gap` 或重要 `partial`
- **WHEN** 该能力符合 Asterwynd 当前项目定位
- **THEN** 条目 SHALL 链接到已有 OpenSpec change 或记录待新增 change
- **AND** 不得在对标矩阵中直接替代需求、设计和测试策略

### Requirement: Reference Agent 分层

项目 SHALL 在对标矩阵中区分主对标对象、产品能力参照和专项参照，避免把所有参考项目视为同等实现目标。

#### Scenario: 使用 Codex CLI 作为主对标

- **GIVEN** 对标能力来自 Codex CLI
- **WHEN** 该能力属于本地 coding agent 核心路径
- **THEN** 条目 SHOULD 标记 Codex CLI 为 `primary_reference`

#### Scenario: 使用辅参照

- **GIVEN** 对标能力来自 Claude Code、Aider 或 OpenCode
- **WHEN** 该能力用于判断产品边界或专项能力
- **THEN** 条目 SHALL 标记其参考角色
- **AND** SHALL 说明该能力是否需要 Asterwynd 等价覆盖
