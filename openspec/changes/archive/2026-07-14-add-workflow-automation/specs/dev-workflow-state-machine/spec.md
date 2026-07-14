## ADDED Requirements

### Requirement: 会话启动自动状态发现

每次 agent 进入仓库的新会话中，agent SHALL 在回复用户之前运行 `python3 scripts/workflow_state.py discover` 以检查当前活跃 change 的状态。

#### Scenario: 单个 change 处于 ready_for_review

- **WHEN** discover 输出唯一一个 change 的 sub_state 为 `ready_for_review`
- **THEN** agent SHALL 运行对应 phase 的 `check_phase_done.py` 机械验证
- **AND** agent SHALL 呈现验证结果后停止，等待人工批准
- **AND** agent SHALL NOT 修改代码或推进状态，直到人工明确批准

#### Scenario: 单个 change 处于执行中

- **WHEN** discover 输出唯一一个 change 的 sub_state 不是 `ready_for_review`
- **THEN** agent SHALL 读取该 change 的 `handoff.json` 确认当前 sub_state
- **AND** agent SHALL 从当前 sub_state 继续执行，按子状态序列自动推进

#### Scenario: 无活跃 change

- **WHEN** discover 输出"无活跃 change"
- **THEN** agent SHALL 进入正常对话模式，无需追踪 phase 状态

### Requirement: Gate 机械验证

每个 phase 的 `ready_for_review` sub_state SHALL 是强制停止点。到达此状态时，agent SHALL 运行 `check_phase_done.py --phase <phase> --change <id>` 进行只读机械验证，且 SHALL NOT 在人工批准前继续推进。

#### Scenario: Gate 验证全部通过

- **WHEN** `check_phase_done.py` 返回全部通过
- **THEN** agent SHALL 列出通过项，说明"等待人工审核"
- **AND** agent SHALL 停止执行，等待用户明确输入"批准"/"通过"/"继续"

#### Scenario: Gate 验证未通过

- **WHEN** `check_phase_done.py` 返回失败项
- **THEN** agent SHALL 列出失败项，说明"需修复后再审核"
- **AND** agent SHALL 回到当前 phase 的对应 sub_state 进行修复

#### Scenario: 人工批准后推进

- **WHEN** 用户明确批准 gate
- **THEN** agent SHALL 运行 `workflow_state.py approve` 记录批准
- **AND** agent SHALL 生成 handoff note 写入 `.handoff/<change_id>/`
- **AND** agent SHALL 推进 handoff.json 到下一 phase 的起始 sub_state

### Requirement: Building Phase 工作区隔离

building phase 中的所有代码修改 SHALL 在独立 git worktree 中进行。planning、reviewing、code-review 和 closing phase SHALL 在主仓库中执行。

#### Scenario: 进入 building phase 时创建 worktree

- **WHEN** change 从 planning/reviewing gate 推进到 building phase
- **THEN** agent SHALL 创建 git worktree，分支命名为 `<change-id>/<YYYY-MM-DD>`
- **AND** agent SHALL 在 worktree 中执行所有代码修改

#### Scenario: closing 完成后清理 worktree

- **WHEN** change 完成 closing phase 并归档
- **THEN** agent SHALL 清理对应的 worktree

#### Scenario: 多个 change 共用 worktree 被禁止

- **WHEN** 存在多个活跃 change
- **THEN** 每个 change SHALL 使用独立的 worktree
- **AND** 禁止多个 change 共用一个 worktree
