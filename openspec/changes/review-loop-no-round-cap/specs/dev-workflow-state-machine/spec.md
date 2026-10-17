# dev-workflow-state-machine 规格 delta

## ADDED Requirements

### Requirement: 审阅闭环的终止条件为收敛，而非轮数上限

实现后的 `/review-loop` 与设计阶段的审阅闭环 SHALL 以**收敛**为终止条件，SHALL NOT 设固定轮数上限。收敛 SHALL 定义为：一次审阅下来**没有出现新的可证伪项**，且此前列出的**所有「必须修改项」都已落库**。「必须修改项」SHALL 等同于审阅 verdict 规则里的**中等及以上严重度问题**——风格偏好与低价值建议 SHALL NOT 阻断 `PASS`、SHALL NOT 延长闭环。若**最近两轮里开放的「必须修改项」数没有下降**（新增与关闭相抵、闭环在原地打转），该闭环 SHALL 判为**无法收敛**并停下来报告阻塞。`BLOCKED` 的语义 SHALL 为「闭环无法自行推进到 `PASS`」，其**成因** SHALL 在报告里写明，至少区分「阻塞性缺陷」与「无法收敛」两种；任何终态的成因 SHALL NOT 写作「已达到某个轮数」。

#### Scenario: 没有轮数上限

- **WHEN** 一个 change 的审阅闭环连续多轮都判 `CHANGES_REQUESTED`，但每一轮都有可修复的新问题、且开放的必须修改项数在下降
- **THEN** 闭环 SHALL 继续（审 → 改 → 再审）
- **AND** SHALL NOT 因轮数达到任何阈值而停止

#### Scenario: 风格建议不阻断收敛

- **WHEN** 某一轮审阅只提出风格偏好或低价值建议（不属于中等及以上严重度问题）
- **THEN** 该轮 SHALL 判 `PASS`；这些建议 SHALL NOT 被记为「必须修改项」
- **AND** 闭环 SHALL NOT 因它们延长

#### Scenario: 收敛即停

- **WHEN** 一次审阅下来没有新的可证伪项，且此前列出的所有必须修改项都已落库
- **THEN** 闭环 SHALL 以 `PASS` 结束
- **AND** 停止理由 SHALL 是「已收敛」，SHALL NOT 写成「已跑满轮数」

#### Scenario: 原地打转判为无法收敛

- **WHEN** 最近两轮里开放的「必须修改项」数没有下降（闭环在原地打转）
- **THEN** 闭环 SHALL 判为**无法收敛**并停下来报告阻塞
- **AND** 报告 SHALL 注明成因是「无法收敛」

#### Scenario: 无法收敛时报告阻塞

- **WHEN** 闭环出现 `BLOCKED`，或反复修复仍不断出现新的可证伪项且开放项数不降
- **THEN** 闭环 SHALL 停下来报告阻塞
- **AND** 报告 SHALL 写明 `BLOCKED` 的成因（阻塞性缺陷 / 无法收敛）
- **AND** SHALL NOT 把「已跑满 N 轮」写成停止理由
