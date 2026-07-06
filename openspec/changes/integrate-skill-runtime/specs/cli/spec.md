## ADDED Requirements

### Requirement: CLI exposes skill status commands

CLI interactive mode SHALL expose slash commands for observing and reloading skills after the slash command framework exists.

#### Scenario: List skills

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/skills`
- **THEN** CLI SHALL 输出当前已加载 skills
- **AND** 输出每个 skill 的名称、来源和 always 标记

#### Scenario: Reload skills

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/skills reload`
- **THEN** CLI SHALL 重新加载 configured skill roots
- **AND** 输出加载数量和诊断摘要
- **AND** 后续 run SHALL 使用刷新后的 skill set

#### Scenario: Skill command requires slash command framework

- **GIVEN** slash command framework 尚未实现
- **WHEN** 本 change 准备进入实现
- **THEN** implementation SHALL wait for or include the command registry dependency resolution
