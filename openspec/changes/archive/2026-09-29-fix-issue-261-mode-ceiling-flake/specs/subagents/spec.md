# subagents spec delta: 子 agent mode 上限按执行上下文继承

## MODIFIED Requirements

### Requirement: 子 agent mode 上限按执行上下文继承

系统 SHALL 从**当前执行上下文的上限**推导子 agent 的有效 mode，SHALL NOT 从任何跨 run 共享、会被并发构造覆盖的可变状态推导。具体地：`SubAgentManager` 的有效 mode 钳制 SHALL 读取一个由执行上下文（asyncio Task 上下文）承载的上限值；该值缺失时 SHALL 回落到一个**保守的静态下界**（会话初始 mode），SHALL NOT 回落为「不收窄」。系统 SHALL 提供一个只读访问器，使调度器与工具层能在**不读取任何共享可变字段**的前提下取得该上限。

该上限 SHALL 只对其所属执行上下文生效：一次 run 退出时对上界的恢复 SHALL NOT 写入任何**其它**执行上下文（否则会清空或改写另一个活跃 run 的上限）。

#### Scenario: 并发构造的子 loop 不改变钳制基准

- **GIVEN** 一个 manager 与一个以其构造的会话 loop（会话上限为只读）
- **WHEN** 在派发节点之前，另有一个以 `build` mode 构造的子 loop 复用了同一 manager
- **THEN** 该 manager 的钳制基准 SHALL 仍为只读
- **AND** 请求 `build` 的子 agent SHALL 被收窄为只读
- **AND** 该结果 SHALL NOT 因两个 loop 的构造顺序不同而改变

#### Scenario: 上限缺失时回落到保守的静态下界

- **GIVEN** 没有任何执行上下文上限被 set（例如调度器被直接构造并 `run()`）
- **AND** 该 manager 以 `parent_mode=read_only` 构造
- **WHEN** 请求一个 `build` 子 agent
- **THEN** 该请求 SHALL 被收窄为只读
- **AND** SHALL NOT 因上限缺失而被授予 `build`

#### Scenario: 子孙继承父节点的有效 mode

- **GIVEN** 一个以只读运行的子 agent（其自身声明的 mode 已被上限收窄）
- **WHEN** 该子 agent 的执行上下文内再派生一个声明 `build` 的子 agent
- **THEN** 后者 SHALL 以其父节点的**有效** mode（只读）为上限
- **AND** SHALL NOT 回落到该 manager 的静态下界或发起会话的 mode

#### Scenario: 提供 scheduler 可读的上限通道

- **GIVEN** 调度器只持有 `SubAgentManager`（不持有 `AgentLoop`）
- **WHEN** 调度器需要读取当前执行单元的 mode 上限
- **THEN** 系统 SHALL 提供一个只读访问器返回该上限
- **AND** 该访问器的返回值 SHALL NOT 从会被并发构造覆盖的共享可变字段推导
- **AND** 该访问器 SHALL 在该值缺失时返回保守的静态下界，SHALL NOT 返回无界值

#### Scenario: 执行上下文上限的 set 不破坏运行收尾

- **GIVEN** 一个子 agent run 在其私有执行上下文中设置了上限
- **WHEN** 该 run 被取消或以跨上下文的方式被 teardown
- **THEN** 系统 SHALL NOT 因上限的 token reset 抛出 `ValueError`
- **AND** 该 run 的终态 SHALL 与未引入上限时一致

#### Scenario: 被遗留 run 的迟后收尾不改变活跃 run 的上限

- **GIVEN** 一个子 agent run 已启动并挂起在其私有执行上下文中，且其所属事件循环已关闭（该 run 的 task 保持 pending）
- **AND** 另一个 run 正在其自己的执行上下文中以只读为上限运行
- **WHEN** 那个被遗留的 task 在**后一个 run 的上下文里**被终结（例如被垃圾回收），从而展开其嵌套的 `finally`
- **THEN** 系统 SHALL NOT 因此改写后一个（活跃）run 的上限
- **AND** 活跃 run 内请求 `build` 的子 agent SHALL 仍被收窄为该活跃 run 的上限（只读）
