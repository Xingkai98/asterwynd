# tool-system 规格 delta

## ADDED Requirements

### Requirement: Worktree 隔离工具

系统 SHALL 提供 EnterWorktree 和 ExitWorktree 工具，允许 agent 在运行时创建、进入和退出 git worktree 隔离工作区；进入 worktree 后，文件工具的工作区边界 SHALL 切换到该 worktree。

#### Scenario: 创建并进入 worktree

- **GIVEN** agent 当前不在任何 worktree 中，且当前工作区是 git 仓库
- **WHEN** 调用 EnterWorktree 并指定 name
- **THEN** 系统 SHALL 创建基于当前仓库的 git worktree
- **AND** 将 agent 工作目录切换到该 worktree
- **AND** 返回 worktree 路径和分支名

#### Scenario: 非 git 仓库拒绝创建

- **GIVEN** 当前工作区不是 git 仓库
- **WHEN** 调用 EnterWorktree
- **THEN** 系统 SHALL 返回结构化错误
- **AND** 工作目录保持不变

#### Scenario: 嵌套 worktree 拒绝创建

- **GIVEN** agent 已位于某个 worktree 中
- **WHEN** 再次调用 EnterWorktree
- **THEN** 系统 SHALL 返回结构化错误
- **AND** 保持当前 worktree 不变

#### Scenario: 退出并保留 worktree

- **GIVEN** agent 已进入 worktree
- **WHEN** 调用 ExitWorktree 且 keep 为 true
- **THEN** 系统 SHALL 将工作目录切回主工作区
- **AND** 保留该 worktree 和分支

#### Scenario: 退出并删除 worktree

- **GIVEN** agent 已进入 worktree 且 worktree 内无未提交改动
- **WHEN** 调用 ExitWorktree 且 keep 为 false
- **THEN** 系统 SHALL 将工作目录切回主工作区
- **AND** 删除该 worktree

#### Scenario: 删除含未提交改动的 worktree 被拒

- **GIVEN** agent 已进入 worktree 且 worktree 内存在未提交改动
- **WHEN** 调用 ExitWorktree 且 keep 为 false
- **THEN** 系统 SHALL 返回结构化错误
- **AND** 保持当前 worktree 与工作目录不变

#### Scenario: 退出时不在 worktree 中返回错误

- **GIVEN** agent 当前不在任何 worktree 中
- **WHEN** 调用 ExitWorktree
- **THEN** 系统 SHALL 返回结构化错误
