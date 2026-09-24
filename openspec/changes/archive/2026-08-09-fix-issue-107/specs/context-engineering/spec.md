## ADDED Requirements

### Requirement: 执行进度保留（Todo 层级保护）

注入层预算超限时，上下文系统 SHALL 将执行进度 todo 层排在 P4（技能）和 P5（规划）可变层之后才裁剪。Todo 层优先级 SHALL 为 P2（与持久记忆索引同级，非 critical、非 cacheable），即在 P4/P5 全部裁完、预算仍超限时才可被裁剪。

#### Scenario: 超预算时 todo 先于技能/规划层保留

- **GIVEN** 注入层总 token 超过预算，且存在 P4 技能层、P5 规划层和 P2 Todo 层
- **WHEN** ContextBuilder 的预算裁剪从最低优先级层尾部开始
- **THEN** P5 规划层先被裁剪，接着 P4 技能层被裁剪
- **AND** Todo 层在这些可变层裁完后仍完整保留
- **AND** cacheable 稳定前缀层（P0/P1/P2 记忆索引）不被裁剪

#### Scenario: 预算极端紧张时 todo 最后才被裁

- **GIVEN** P4/P5 可变层全部被裁剪后预算仍超限
- **WHEN** 预算裁剪继续
- **THEN** Todo 层（P2，非 cacheable）作为下一个可裁剪层从尾部被裁
- **AND** P0/P1 critical 层与 P2 记忆索引 cacheable 层仍不被裁剪
