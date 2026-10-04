# web-ui spec delta: 节点 transcript 的终态补取与手动刷新

> **为什么 MODIFIED 块要带既有 Scenario**：OpenSpec 对 MODIFIED requirement 是**整块替换**
> （`buildUpdatedSpec`），只写新 Scenario 会静默删掉该 requirement 原有但未复述的 Scenario。
> 因此本块**逐字保留**原有 4 条 Scenario 的正文（读取单 subagent / foreach 候选集 / 不产生 run
> 降级 / 对话内容的刷新与暂停），只改「刷新与暂停」这一条的措辞并新增两条。

## MODIFIED Requirements

### Requirement: workflow 节点 transcript 只读接口

Web 服务 SHALL 提供只读接口 `GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript`，复用 `SubAgentManager.inspect_transcript()`，按节点的**对话形态**返回三态之一：`single`（1 个对应 subagent：`subagent` / `aggregate(strategy="llm")` / 自动插层聚合）、`candidates`（foreach 容器，N 个展开项）、`none`（`route` / `aggregate(strategy="collect")` / 从未派发的节点——这些节点不产生 run）。接口 SHALL bounded（条数上限 + 单条内容截断 + 候选集分页上限），SHALL 默认排除工具结果。接口 SHALL NOT 调用 LLM、写盘或改变 workflow 执行状态。

`candidates` 的候选集 SHALL 以 index 空间（`item_states`）为索引源且保持完整，SHALL NOT 依赖可能稀疏的 `subagent_ids`；每条候选 SHALL 含 `index`/`subagent_id`/`run_id`/`status`/`task`/`reason`/`summary`。三个形态 SHALL 返回 scheduler 侧 `reason` 的**全文**（附 `reason_truncated` 布尔标志——前端比长度会把恰好等于上限的 reason 误判成已截断）。

#### Scenario: 读取单 subagent 节点的 transcript

- **GIVEN** 一个已执行、恰好对应 1 个 subagent 的节点（普通节点 / LLM 聚合 / 自动插层聚合）
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "single"` 与该节点的 messages（bounded）与 `truncated` 标志
- **AND** SHALL NOT 触发任何 LLM 调用或状态变更

#### Scenario: foreach 容器返回候选集

- **GIVEN** 一个 foreach 容器节点（N 个展开项各自独立 subagent，且 N>1）
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "candidates"` 与至多 `limit` 条候选（每条含 `index`/`subagent_id`/`run_id`/`status`/`task`/`reason`/`summary`），附 `total`/`has_more`
- **AND** 用户点某一项后 SHALL 能按该项的 `subagent_id` 取到该项自己的 transcript，SHALL NOT 混入同容器其它项的 messages
- **AND** 被取消/失败的展开项 SHALL 仍出现在候选集里

#### Scenario: 不产生 run 的节点优雅降级

- **GIVEN** 一个 `route` 节点、一个 `strategy="collect"` 的聚合节点，或一个从未派发的 `pending`/`blocked` 节点
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "none"` 与结构化说明（route 附命中标签与选中出口、collect 附合并产出、未派发节点说明未执行）
- **AND** SHALL NOT 编造 transcript

前端 SHALL 在切到「对话」tab 时才请求（懒加载），SHALL 按**定死的刷新节律**按需重取：节点在运行中时按节律周期重取，用户暂停后 SHALL NOT 自动重取（**暂停优先于补取**：暂停期间连终态补取也 SHALL NOT 发生）。**节点到达终态后 SHALL NOT 再周期性重取**，但**若最后一次取数发生在该节点到达终态之前，SHALL 补取一次**（终态补取）——否则运行期抓到的那一帧会被永久缓存，「跑完后对话停在半途」且该 run 的失败证据一并不可见。补取判据 SHALL 基于「取数时记录的节点状态」而不是「是否曾经取过数」，且补取后 SHALL NOT 再次触发（终态帧只补一次）；取数时状态**未记录**时按「非终态」处理（允许一次补取，且同样自收敛）。对话区 SHALL 提供**暂停/继续实时更新**与**手动刷新**两个动作；手动刷新 SHALL 绕过缓存重新取数、SHALL NOT 改变暂停状态、也 SHALL NOT 影响其它节点的缓存。transcript 的渲染 SHALL 按行聚簇做 UI 虚拟化（SHALL NOT 按行建 DOM）。

#### Scenario: 对话内容的刷新与暂停

- **GIVEN** 一个仍在运行的节点，用户已切到该节点的「对话」tab
- **WHEN** 达到刷新节律
- **THEN** SHALL 重取该节点的 transcript
- **AND** 用户点「暂停实时更新」后 SHALL NOT 再自动重取

#### Scenario: 运行中取过数、随后节点到终态

- **GIVEN** 用户在节点仍在运行时切到「对话」tab（此时已取数一次，载荷是运行中的快照）
- **WHEN** 该节点到达终态（快照状态变为终态）
- **THEN** 前端 SHALL **补取一次** transcript，使用户看到完整对话与终态失败证据
- **AND** 补取后 SHALL NOT 再周期性重取（终态帧只补一次：再来一张终态快照也 SHALL NOT 再发请求）
- **AND** 若最后一次取数本身已发生在终态之后，则 SHALL NOT 补取

#### Scenario: 暂停期间到达终态

- **GIVEN** 用户已点「暂停实时更新」，且手上这一帧取自运行期
- **WHEN** 该节点到达终态（抽屉可能因快照重绘）
- **THEN** 前端 SHALL NOT 自动取数（暂停优先于终态补取），面板保持用户正在读的那一帧
- **AND** 用户随后点「继续实时更新」或「刷新」时，SHALL 立即取到终态帧（「继续」= 现在就跟上，SHALL NOT 让用户再等一个刷新节律）

#### Scenario: 手动刷新绕过缓存

- **GIVEN** 某节点的「对话」tab 已渲染（缓存中存在一帧载荷）
- **WHEN** 用户点该区的「刷新」动作
- **THEN** 前端 SHALL 忽略缓存重新取数并按新载荷重绘
- **AND** 该动作 SHALL NOT 改变暂停状态，也 SHALL NOT 影响其它节点的缓存
