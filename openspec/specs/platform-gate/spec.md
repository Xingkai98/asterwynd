# platform-gate 规格

## Purpose

定义合入平台闸门的能力边界：CI required checks、conversation resolution、review 时机与平台配置即代码。当前仓库尚未实现平台闸门配置脚本（`platform_gate.py` / `platform-gate.json` 均不存在），平台配置由 GitHub 手动管理。

## Requirements

### Requirement: platform-gate 当前为预留能力域

系统 SHALL NOT 声称已经提供平台闸门配置脚本、`--apply`/`--verify` 命令或分支保护目标状态声明。

#### Scenario: 当前平台配置

- **GIVEN** 用户使用当前仓库
- **WHEN** 查看平台配置工具
- **THEN** 系统 SHALL 只提供现有 CI workflow（`validate` / `benchmark-gate`）与 GitHub branch protection 现状
- **AND** 不提供 `platform_gate.py` 或 `platform-gate.json`

### Requirement: 未来平台闸门必须复用 GitHub branch protection 语义

未来平台闸门实现 SHALL 复用 GitHub branch protection REST API 语义（required_status_checks / required_conversation_resolution / required_pull_request_reviews / enforce_admins），并遵守「PR 作者不能 approve 自己的 PR」的平台限制，不得另起一套不兼容的合入门禁协议。

#### Scenario: 准备实现平台闸门

- **GIVEN** 需求提出合入平台闸门
- **WHEN** 创建 OpenSpec change
- **THEN** change SHALL 描述与 GitHub API、CI workflow、AGENTS.md 合入门禁的共享边界
