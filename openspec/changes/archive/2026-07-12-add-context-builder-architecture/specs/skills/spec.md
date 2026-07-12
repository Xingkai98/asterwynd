## ADDED Requirements

### Requirement: Skill 上下文作为 ContextSource

Skill index 和 active skill context SHALL 通过 ContextSource adapter 注入运行上下文。

#### Scenario: 已激活 skill

- **GIVEN** 当前运行已有 active skill
- **WHEN** ContextBuilder 构建上下文
- **THEN** skill adapter SHALL 渲染 active skill 指令
- **AND** 构建报告 SHALL 记录该来源
