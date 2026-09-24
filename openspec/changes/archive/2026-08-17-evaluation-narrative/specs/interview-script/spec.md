# interview-script 规格（delta）

## ADDED Requirements

### Requirement: 面试叙事与评测现状对齐

面试叙事文档 SHALL 将评测现状口径（任务数、测试数、工具数）与升级方向分层表述：现状数字 SHALL 与当前实现一致（任务 schema 扩展后本地任务数、测试函数数、内置工具数）；升级方向（场景×难度分层任务集、pass^k/cost@pass/fault_owner 等）SHALL 标注「设计已定、实现中」，不得把未实现写成已实现。

#### Scenario: 现状口径分层

- **GIVEN** 面试叙事文档涉及评测数字
- **WHEN** 表述评测能力
- **THEN** 现状数字 SHALL 与当前实现一致
- **AND** 升级方向 SHALL 标注「设计已定、实现中」
