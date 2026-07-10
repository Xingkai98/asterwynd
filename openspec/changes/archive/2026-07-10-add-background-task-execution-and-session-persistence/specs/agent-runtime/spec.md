## ADDED Requirements

### Requirement: 后台任务执行

系统 SHALL 支持通过 `Bash` 工具的 `run_in_background=True` 参数启动后台命令。启动后台命令后 SHALL 返回 task_id。`BackgroundTaskManager` SHALL 维护所有活跃后台任务的状态，并在任务完成时通过 AgentLoop 自动注入结果。

#### Scenario: 启动后台任务

- **GIVEN** agent 调用 Bash 且 run_in_background=True
- **WHEN** 命令为 `pytest -q tests/`
- **THEN** 系统 SHALL 返回 `"Task started: <task_id>"`
- **AND** 命令 SHALL 在后台异步执行

#### Scenario: 后台任务完成后注入结果

- **GIVEN** 有一个活跃的后台任务正在执行
- **WHEN** 任务完成（exit_code=0）
- **THEN** AgentLoop SHALL 在下一次迭代开始时将该任务的输出作为 tool result 注入消息
- **AND** 该 task_id SHALL 从活跃列表移至历史

#### Scenario: AgentLoop 退出时清理后台任务

- **GIVEN** AgentLoop 退出时仍有一个运行中的后台任务
- **WHEN** AgentLoop.run() 返回
- **THEN** BackgroundTaskManager SHALL 发送 SIGTERM 给所有活跃进程
- **AND** 等待 5 秒后发送 SIGKILL

### Requirement: 会话持久化

系统 SHALL 支持将会话状态序列化到 `.asterwynd/sessions/<session_id>/` 目录。持久化内容 SHALL 包含消息历史、mode、todo 列表、技能激活状态。CLI SHALL 提供 `--resume` 参数恢复会话。

#### Scenario: 会话自动保存

- **GIVEN** AgentLoop 在一次迭代后仍有活跃迭代
- **AND** config.session.auto_save 为 True
- **WHEN** 当前迭代结束
- **THEN** 系统 SHALL 将会话快照写入 `.asterwynd/sessions/<session_id>/`

#### Scenario: 会话恢复

- **GIVEN** 存在一个有效的 session 快照
- **WHEN** 用户通过 `--resume <session_id>` 启动
- **THEN** 系统 SHALL 加载消息历史和 mode
- **AND** 注入 `## Session Resumed` 系统消息
- **AND** 正常进入交互循环

#### Scenario: 损坏的会话文件

- **GIVEN** session 文件的 JSON 格式损坏或不兼容
- **WHEN** 用户尝试 --resume
- **THEN** 系统 SHALL 返回明确错误而非静默失败

#### Scenario: 不存在的 session

- **GIVEN** session_id 对应的目录不存在
- **WHEN** 用户尝试 --resume
- **THEN** 系统 SHALL 返回 "Session <id> not found"

### Requirement: TaskOutput 和 TaskStop 工具

系统 SHALL 提供 `TaskOutput` 和 `TaskStop` 工具用于后台任务的控制。

#### Scenario: 阻塞等待任务完成

- **GIVEN** 后台任务 5 秒后完成
- **WHEN** agent 调用 TaskOutput(task_id, block=True)
- **THEN** TaskOutput SHALL 阻塞等待直到任务完成
- **AND** 返回 exit_code、stdout、stderr

#### Scenario: 非阻塞查询

- **GIVEN** 后台任务仍在运行
- **WHEN** agent 调用 TaskOutput(task_id, block=False)
- **THEN** TaskOutput SHALL 立即返回
- **AND** status SHALL 为 "running"

#### Scenario: 终止任务

- **GIVEN** 后台任务仍在运行
- **WHEN** agent 调用 TaskStop(task_id)
- **THEN** 进程 SHALL 被终止
- **AND** TaskStop SHALL 返回最终输出
