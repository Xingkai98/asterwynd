# dev-workflow-state-machine 规格 delta

## ADDED Requirements

### Requirement: 审阅闭环的终止条件为收敛，而非轮数上限

实现后的 `/review-loop` 与设计阶段的审阅闭环 SHALL 以**收敛**为终止条件，SHALL NOT 设固定轮数上限。收敛 SHALL 定义为：一次审阅下来**没有出现新的可证伪项**，且此前列出的**所有「必须修改项」都已落库**。闭环出现 `BLOCKED`、或在仍不断出现新的可证伪项（无法收敛）时，SHALL 停下来报告**阻塞**，SHALL NOT 以「已达到某个轮数」作为停止理由。

#### Scenario: 没有轮数上限

- **WHEN** 一个 change 的审阅闭环连续多轮都判 `CHANGES_REQUESTED`，但每一轮都有可修复的新问题
- **THEN** 闭环 SHALL 继续（审 → 改 → 再审）
- **AND** SHALL NOT 因轮数达到任何阈值而停止

#### Scenario: 收敛即停

- **WHEN** 一次审阅下来没有新的可证伪项，且此前列出的所有必须修改项都已落库
- **THEN** 闭环 SHALL 以 `PASS` 结束
- **AND** 停止理由 SHALL 是「已收敛」，SHALL NOT 写成「已跑满轮数」

#### Scenario: 无法收敛时报告阻塞

- **WHEN** 闭环出现 `BLOCKED`，或反复修复仍不断出现新的可证伪项
- **THEN** 闭环 SHALL 停下来报告阻塞
- **AND** SHALL NOT 把「已跑满 N 轮」写成停止理由
