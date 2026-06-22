## ADDED Requirements

### Requirement: code intelligence 扫描遵守 workspace safety

Code intelligence 扫描 SHALL 只访问 workspace 内且 read policy 允许的路径，并复用现有 ignore rules 降低噪音。

#### Scenario: 扫描包含 denied path 的 workspace

- **GIVEN** workspace 中包含 `.env`、`.git` 或其他 denied path
- **WHEN** 生成 repo map 或符号索引
- **THEN** 系统 SHALL 跳过这些路径
- **AND** SHALL NOT 返回 denied path 内容
