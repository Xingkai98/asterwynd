# web-ui spec delta: 纯门控边的独立状态

## MODIFIED Requirements

### Requirement: 节点与边状态高亮

前端 SHALL 按状态高亮节点（pending 灰 / started 蓝 / completed 绿 / failed 红 / cancelled 深灰 / blocked 黄 / budget_exceeded 橙 / skipped 冷灰蓝）。边 SHALL 按状态高亮（inactive / ready / active / passed / blocked / **satisfied**）。route 控制边 SHALL 单列表达（`kind: "control"`），SHALL 只高亮 `targets` 中实际选中的出口。

**边 `satisfied`（依赖已满足但产出未被消费）**：scheduler SHALL 对「`required` 边 + 未被下游消费 + 源 `completed` + 目标已越过 `pending`」判定为 `satisfied`，SHALL NOT 落 `inactive` 兜底。该档表达「这条边确实门控了下游派发，但上游产出没有流过去」——纯顺序依赖（如 foreach 用字面 `items` 而不读 source 产出）SHALL NOT 显示为「没有参与」。`passed` 的语义 SHALL NOT 改变（仍是「上游产出被下游读取」）。

`satisfied` SHALL 与 `inactive`、`passed` 在**非颜色维度**上可分辨（明度差或线宽差），SHALL NOT 仅靠色相区分。

#### Scenario: 节点状态高亮

- **GIVEN** 一个 workflow 有 completed、started、pending 三种状态的节点
- **WHEN** 前端渲染快照
- **THEN** 三种节点 SHALL 分别显示绿色、蓝色、灰色
- **AND** SHALL 直观区分运行状态

#### Scenario: route 分支高亮

- **GIVEN** 一个 route 节点命中某条分支
- **WHEN** 前端渲染快照
- **THEN** SHALL 只高亮该 route 选中的出口控制边
- **AND** 未选中的分支 SHALL 保持 inactive

#### Scenario: 纯门控边不显示为死线

- **GIVEN** 一条 `required` 数据边，其源节点 `completed`、目标节点已因该依赖被放行并越过 `pending`，但目标**没有读取**源的产出（例如 foreach 使用字面 `items`）
- **WHEN** 渲染该边
- **THEN** 该边 SHALL 判定为 `satisfied`，SHALL NOT 判定为 `inactive`
- **AND** SHALL 与「数据被读取」的 `passed` 边在视觉上可分辨

#### Scenario: 未被消费且无门控作用的边仍是 inactive

- **GIVEN** 一条 `required: false` 的边，下游未读取其产出
- **WHEN** 渲染该边
- **THEN** 该边 SHALL 保持 `inactive`（该边从未门控派发，未消费就是真的无关）

#### Scenario: 等待消费仍是 ready

- **GIVEN** 一条 `required` 边，其源 `completed` 但目标仍为 `pending`
- **WHEN** 渲染该边
- **THEN** 该边 SHALL 判定为 `ready`（等待下游消费的**进行中**态），SHALL NOT 判定为 `satisfied`

### Requirement: workflow 图图例

Workflow 视图 SHALL 提供常驻可折叠的图例（legend），说明节点类型（`S` subagent / `F` foreach / `R` route / `A` aggregate）、节点状态八档、边状态**六档**与 channel 线型语义。图例 SHALL 在桌面（>720px）默认展开、在手机（≤720px）默认折叠。图例每条目 SHALL 包含人话解释（而非仅状态词）。图例内容 SHALL 与状态词表（颜色/线型/代号/状态名）同源生成。

#### Scenario: 手机端图例可折叠且可见

- **GIVEN** 一个 ≤720px 视口的移动端打开 Workflow 视图
- **WHEN** 图渲染完成
- **THEN** SHALL 显示一行折叠态图例入口（`图例 ▾`）
- **AND** 点击后 SHALL 展开显示节点类型、状态、边状态的完整图例

#### Scenario: 图例与状态词表同源

- **GIVEN** 状态词表（`NODE_COLORS`/`NODE_LABELS`/`EDGE_STYLES`/`KIND_GLYPHS`）发生变化
- **WHEN** 重建图例内容
- **THEN** 图例条目 SHALL 自动反映新词表，SHALL NOT 出现图例与图不一致

#### Scenario: 图例覆盖六档边状态

- **GIVEN** 边状态词表为六档（inactive / ready / active / passed / blocked / satisfied）
- **WHEN** 构建图例内容
- **THEN** 图例 SHALL 含全部六档，SHALL NOT 遗漏 `satisfied`
- **AND** 每档 SHALL 带人话解释（`satisfied` 的解释 SHALL 说明「依赖已满足但产出未被读取」）
