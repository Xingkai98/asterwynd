# workspace-safety spec delta: 沙箱事件归属按执行上下文隔离

## MODIFIED Requirements

### Requirement: 沙箱事件入 trace

沙箱 SHALL 通过 contextvar sink 向活跃的 `TraceRecorder` 发出结构化事件（`denied`/`kill`/`oom`/`degraded`），SHALL 附带调用方 `tool_call_id` 与截断的命令，且 SHALL 与 trace 事件 schema 向后兼容（新增 `sandbox` step type；`schema_version` 不变）。

该 sink SHALL 只对其所属执行上下文生效：一次 run 退出时对 sink 的恢复 SHALL NOT 写入任何**其它**执行上下文（否则会改写或清空另一个活跃 run 的事件归属，使 sandbox 事件静默丢失或串写进别的 run 的 trace）。

#### Scenario: 命令拒绝事件

- **GIVEN** 命令被 workspace policy 或命令护栏拒绝
- **WHEN** Bash 工具拒绝该命令
- **THEN** trace 中 SHALL 记录带拒绝原因的 `sandbox` `denied` 事件

#### Scenario: 超时 kill 事件

- **GIVEN** 命令超过超时（前台或后台）
- **WHEN** 后端或后台管理器杀死进程树
- **THEN** trace 中 SHALL 记录 `sandbox` `kill` 事件

#### Scenario: 被遗留 run 的迟后收尾不改变活跃 run 的事件归属

- **GIVEN** 一个 run 已启动并挂起在其私有执行上下文中，且其所属事件循环已关闭（该 run 的 task 保持 pending）
- **AND** 另一个 run 正在其自己的执行上下文中、以自己活跃的 sink 记录 sandbox 事件
- **WHEN** 那个被遗留的 task 在**后一个 run 的上下文里**被终结（例如被垃圾回收），从而展开其嵌套的 `finally`
- **THEN** 系统 SHALL NOT 因此改写后一个（活跃）run 的 sink
- **AND** 活跃 run 之后发出的 sandbox 事件 SHALL 仍写入它**自己**的 trace
- **AND** 该事件 SHALL NOT 静默丢失，也 SHALL NOT 写入任何别的 run 的 trace
