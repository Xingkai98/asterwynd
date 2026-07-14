# conversation-delivery-workflow 规格

## Purpose

定义从探索性对话、需求确认、设计、开发、自动审查、人工 gate 到 closing 的端到端交付工作流控制面边界。

## Requirements

### Requirement: 能力域边界

对探索性对话、需求确认、设计、开发、自动审查、人工 gate 和 closing 之间端到端交付流程的新增规格，SHALL 归属到 `conversation-delivery-workflow` capability。当前运行时行为仍以已归档 specs 和 active changes 为准。

#### Scenario: 新增端到端交付流程规格

- **WHEN** change 定义跨越闲聊、需求、设计、开发、审查和 closing 的流程要求
- **THEN** 该 change SHALL 在 `conversation-delivery-workflow` 下维护对应 spec delta
