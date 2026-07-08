## MODIFIED Requirements

### Requirement: Bash 支持后台执行

`Bash` 工具 SHALL 新增 `run_in_background` 参数（默认 `False`）。当 `run_in_background=True` 时，Bash SHALL 异步启动子进程并立即返回 task_id。后台命令 SHALL 仍然经过 workspace safety 的 allowlist/denylist 检查。

#### Scenario: 后台命令通过安全检查

- **GIVEN** agent 调用 Bash 且 run_in_background=True
- **WHEN** 命令为 `pytest -q tests/`
- **AND** 命令通过 allowlist 检查
- **THEN** 命令 SHALL 在后台启动
- **AND** SHALL 返回 task_id

#### Scenario: 后台命令被拒绝

- **GIVEN** agent 调用 Bash 且 run_in_background=True
- **WHEN** 命令为 `rm -rf /`（被 denylist 拒绝）
- **THEN** 系统 SHALL 返回权限错误
- **AND** SHALL NOT 启动任何进程

#### Scenario: 前台执行保持不变

- **GIVEN** agent 调用 Bash 且 run_in_background=False（默认）
- **WHEN** 命令执行
- **THEN** 行为 SHALL 与改动前完全一致（同步阻塞等待结果）
