# multi-agent-collaboration spec delta: workflow 节点 mode 上限语义

## ADDED Requirements

### Requirement: workflow 节点 mode 有效值受会话上限钳制

系统 SHALL 让 workflow 节点的**有效** mode 等于 `min(节点声明 mode, 当前执行单元的会话上限)`，SHALL NOT 因节点在 workflow 中显式声明而放宽当前会话的能力面。会话上限 SHALL 在一个**保守**的静态下界之上取得，SHALL NOT 由跨 run 共享、会被并发构造覆盖的可变状态推导。

节点自身的收窄 SHALL 在节点**被派发时**就已生效，SHALL NOT 晚于其自身 mode 的确定。节点有效 mode SHALL 作为该节点子孙的上限传播——子孙上限 SHALL 逐层收紧为父节点的**有效** mode，SHALL NOT 一律回落到发起会话的 mode；该继承 SHALL 跨越 workflow 边界的嵌套（父节点内启动新图）同样成立。

#### Scenario: 只读会话中的 build 节点被收窄

- **GIVEN** 会话上限为只读，某个节点声明 `mode: "build"`
- **WHEN** 该节点被派发
- **THEN** 该节点 SHALL 以只读运行
- **AND** 该收窄 SHALL 发生在该节点自身 mode 确定之时（派发阶段），SHALL NOT 晚于它

#### Scenario: build 节点不被前面的只读节点降级

- **GIVEN** 会话上限为写，一张图中先有一个 `read_only` 节点、后有一个 `build` 节点
- **WHEN** 两个节点先后被派发
- **THEN** `read_only` 节点 SHALL 以只读运行
- **AND** `build` 节点 SHALL 以写运行
- **AND** SHALL NOT 因前一个节点的存在而被降级

#### Scenario: 并发节点互不覆盖上限

- **GIVEN** 同一张图里并行存在一个声明 `read_only` 的节点与一个声明 `build` 的节点
- **WHEN** 两者各自被派发
- **THEN** 各自 SHALL 得到各自正确的有效 mode
- **AND** 该结果 SHALL NOT 因两个节点的构造顺序不同而互相覆盖

#### Scenario: 节点自身的收窄随上下文传播到子孙

- **GIVEN** 会话上限为写，其下一个节点声明 `read_only`（故其有效 mode 为只读）
- **WHEN** 该节点的执行上下文内再派生子 agent（含它内启动的另一张图）
- **THEN** 子孙的上限 SHALL 等于该节点的**有效** mode（只读）
- **AND** SHALL NOT 回落到发起会话的 mode（写）

#### Scenario: 会话上限在 run 起点快照

- **GIVEN** 一个 run 以其起点的会话 mode 确定了整轮上限
- **WHEN** 该 run 运行途中会话切换了 mode
- **THEN** 本次 run 已确定的上限 SHALL NOT 改变
- **AND** 该会话**下一次** run SHALL 按当时的会话 mode 重新确定上限

#### Scenario: 顺序运行的两张图互不污染

- **GIVEN** 同一会话（用户从未切换 mode）顺序运行图 1 与图 2，图 1 含一个声明 `read_only` 的节点，图 2 的节点声明 `build`
- **WHEN** 图 2 被派发
- **THEN** 图 2 的 `build` 节点 SHALL 按发起会话的上限确定其有效 mode
- **AND** SHALL NOT 被图 1 运行时的任何中间状态降级
