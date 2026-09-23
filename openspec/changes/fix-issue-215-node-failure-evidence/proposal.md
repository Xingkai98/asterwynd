# Proposal: workflow 节点失败证据投影（fix-issue-215-node-failure-evidence）

关联跟踪 issue：[#215](https://github.com/Xingkai98/asterwynd/issues/215)（M3.6 `trace_digest` 虚假完成：归档 tasks 标 `[x]` 但全仓零实现）。

## Change Type

- primary: feature
- secondary: []

## Why

归档 change `enhance-workflow-graph-ux` 的 M3.6（G9 `trace_digest`）标了 `[x]`，但**全仓零实现**：`openspec/specs/` 无对应 requirement，active 代码无 `trace_digest` / 失败证据投影，唯一命中在归档 change 自己的文档里。归档审阅 R1 诚实标注「未逐行核实」、R2 只复审 R1 的阻断项，**没有回头补 M3.6 的核实** → 任务被当成做完（issue #215 的机制缺口描述）。

issue 的「事实勘误」comment 要求开工第一步先**重估**：原 issue 写的重估前提是「#213 落地后 transcript 已能回答『为什么报错』，本条可关闭」。**#213 已由 PR #225 合入归档，本次重估已完成，结论如下。**

### 重估结论：不重叠，但范围应收窄

**#213 修的是「单条内容无上限」（长度维度），本条要的是「哪个工具失败了、为什么」（投影维度）——正交，不重叠。**

实证（当前 master `1a7df92`）：

1. **数据齐备但无人投影**。`run.trace.steps` 里已有 `tool_result`（带 `status` / `error_type`，`agent/trace_recorder.py:129`）与 `llm_error`（带 `error_type` / `message`，`:226`）。全仓**唯一**读取 `run.trace` 的地方是 `agent/subagent/snapshot.py:77`，且只数 `llm_iteration` 步数——**没有任何用户面出口投影失败步骤**。
2. **Web 出口拿不到工具结果**。`/nodes/{node_id}/transcript` 路由（`web/server.py:195-202`）签名里**没有** `include_tool_results` 参数，`build_node_transcript_payload` 的默认 `False` 一路传到 `inspect_transcript`，把所有 `role == "tool"` 消息过滤掉；前端（`web/static/workflow_transcript.js:55-70`）也没传这个参数。用户最多看到 `🔧 Bash` 这一行工具调用，**永远看不到它的失败 observation**。
3. **`run.reason` 覆盖不到「中途失败」**。`reason` 只在**整个 run 失败**时才有文本（`_mark_failed` / `_mark_budget_exceeded`）。而工具失败**不会**让 run 失败——`agent/loop.py:895-935` 把工具错误包成 tool 消息继续跑。
4. **`failed` 分支实际是死代码**。`agent/subagent/manager.py:1324` 判 `result.stop_reason is not StopReason.ERROR`，但 `StopReason.ERROR` 全仓**零赋值点**（只有 `agent/result.py:14` 的定义 + `tests/agent/test_result.py:18` 的断言），`loop.py` 只产出 `END_TURN` / `MAX_ITERATIONS`。run 只能经异常路径 `_mark_failed` 变 `failed`。

**净效果**：一个 `completed` 的节点可以内部有多次工具失败，而 UI 上**零信号**——状态绿、`reason` 空、transcript 里工具结果被过滤。这正是归档 change 总目标里「如果报错了，为什么报错」没被回答的那一半。

**收窄结论**：不做通用 `trace_digest`（那是「运行内事件流」#202 的领域，需要新的暴露口径与容量设计），只做归档 design.md:410 坑 (b) 点名的那一件事——**节点详情里的 bounded 失败证据区，并区分「无 trace」与「trace 里无失败」**。坑 (a)（trace 只在终态写入，运行中看不到）本次不试图解决，而是**如实投影成 `running` 状态**，不再假装。

## 需求

1. **失败证据投影进节点 transcript 载荷**。`build_node_transcript_payload` 的返回多一个 `failure_evidence` 键，数据源是该 run 的 `run.trace.steps`：`status != "ok"` 的 `tool_result` + 全部 `llm_error`。
2. **区分成因，不折叠**。「无失败证据」SHALL 用显式状态枚举表达，**SHALL NOT** 把「没有 trace」与「trace 里没有失败步骤」显示成同一件事。归档 design.md:410 点名的 `trace is None` 三种成因必须各有独立取值。
3. **bounded**。只取**最近** N 条失败条目，单条 `observation` 不超过节点 transcript 的单条内容上限（复用既有 `TRANSCRIPT_CONTENT_LIMIT` 口径），带截断标志、失败总数与「是否被截断」标量。
4. **前端落点**：详情抽屉「任务」tab 里加「失败证据」区，位于既有 `drawer-why` 之后。
5. **不动受保护归档路径**。归档 change 的 M3.6 标注保持原样，本 change 的文档里做对照说明（用户已确认走「选项 1：补实现收窄版」）。

## Non-Goals

- **不做通用 `trace_digest` / 全量 trace 摘要**（含 `llm_iteration` 等正常步骤的投影）。归 #202（运行内事件流）。
- **不做运行中实时失败可见性**。`run.trace` 按设计只在终态写入，本条只如实投影 `running` 状态；真正的「此刻在干什么」需要事件流，归 #202。
- **不改 `run.trace` 的写入时机或结构**。四个终态落点（`manager.py:1334/1410/1425/1444`）一行不动，本次是纯读取侧投影。
- **不给 HTTP 路由加 `include_tool_results` 开关**。那是另一条产品决策（要不要在 UI 里放全量工具结果），本条只投影**失败**子集。
- **不修 `StopReason.ERROR` 死分支**。该发现记录在案，但修它属于 run 状态机语义（会改变 `completed`/`failed` 的判据），不在本条范围。
- **不追溯修改归档 change 的 tasks.md / spec**（受保护路径）。
- 不改 `_envelope` / `parent_envelope` 结构契约。

## Impact Analysis

### 受影响文件（预期）

| 文件 | 改动性质 |
|---|---|
| `web/session.py` | 新增 `failure_evidence` 投影函数 + 常量；`build_node_transcript_payload` 三态各分支挂载 |
| `web/static/workflow.js` | 详情抽屉「任务」tab 新增「失败证据」区渲染 |
| `openspec/specs/web-ui/spec.md` | 同步 ADDED requirement（收尾阶段） |
| `tests/web_tests/test_workflow_node_transcript.py` | 新增失败证据回归测试 |

### 契约影响

- **加性**：transcript 载荷新增一个键，既有键语义不变。既有测试 `test_workflow_node_transcript.py` 不因新增键而红（需验证无严格相等断言）。
- **`_envelope` / `parent_envelope` 逐字节不变**（本次不碰 scheduler 投影）。
- **模型面不受影响**：`InspectSubagentTranscript` 工具一行不动。

### 风险

- **`run.trace` 体积**：`to_dict()` 序列化**全部** steps，含每次 `tool_call` 的完整 arguments 与每次 `tool_result` 的 observation。投影必须**只遍历不复制**，且对取出的条目做单条截断，否则会把大 trace 灌进 HTTP 响应。需在测试里用大 trace 验证响应体积有界。
- **`observation` 可能不是字符串**：`record_tool_result` 对 list 型 observation 先经 `_sanitize_observation` 转字符串，但 `llm_error` 的 `message` 与 `tool_result` 的 `observation` 都可能为空。投影需容忍缺失字段。
- **节点→run 的解析**：`queue_full` 的 run 会被 `session.runs.pop()`（`manager.py:1033-1034`），无法解析——这是状态枚举里必须有的一个取值，不能当成「无失败」。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 属「诊断能力」新增（引入新的只读投影面 + 新 spec requirement），且设计空间开放——状态枚举怎么分、
  证据不可得时怎么表达、bounded 取什么形状，都有多个可行解，故走 full 档完整调研而非沿用既有权衡。调研对象
  为业界 agent 可观测性框架（OTel GenAI 语义约定 / LangSmith / LangFuse / W&B Weave / OpenAI Agents SDK /
  OpenInference）的**当前公开文档与规范原文**；结论逐条落在 `design.md` 的「业界调研结论」节（F1–F4），
  并直接驱动了 D1（状态枚举）、D3（字段命名）两个决策。
- research questions:
  1. 成熟的 agent 可观测性工具（LangSmith / LangFuse / W&B Weave）如何在 UI 与 API 里投影**中间工具失败**——失败的是子 span，父 run 仍是成功态时怎么显示？
  2. OpenTelemetry GenAI 语义约定里，工具调用的错误有没有标准字段（`error.type` / span status）？「span 已结束但没有错误」与「span 未采集」在标准里怎么区分？
  3. 业界有没有既有「bounded 失败摘要」的字段命名与上限约定（last-N-errors / error digest）？状态枚举该怎么命名才不产生歧义？
- findings:
  - **F1「完成但有隐藏的中间失败」是业界默认，非本仓库特有 bug**：LangFuse 的失败 observation 不填 `level`
    时停在 `DEFAULT`，文档自述「与成功的调用无法区分」；LangSmith 的子 `tool` run 可以是 `error` 而根 run
    仍 `success`（状态不向上冒泡），且默认按 Root run 过滤；OTel 规范**明确要求**「被重试或已处理的错误
    SHOULD NOT 记在 span 上」——标准本身就在建议丢掉这类证据
    ([Recording errors](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/))。
  - **F2 OTel 的 `Unset` 重载正是坑 (b)**：`Unset` 同时表示「跑完了没事」与「没评估/没记录」；
    这个重载是真实故障源（[OpenLit#300](https://github.com/openlit/openlit/issues/300)）。OTel 没能区分，
    本 change 有条件区分——印证显式枚举的必要性。
  - **F3 命名与「证据不可得」的处理**：OTel 的 `error.type`（低基数，MCP 约定工具失败用 `tool_error`）、
    OpenInference 的 `exception.escaped`（异常被吸收 vs 逃出）、OpenAI Agents SDK 在敏感数据关闭时用占位
    文本**替代而非省略**错误——三条都指向「沿用既有键名 + 负向态给可读原因」。
  - **F4 bounded 摘要形状**：业界通行「结构化截断 + 显式省略标记 + 报告省略数量」；LangFuse 拒绝按 level
    过滤 trace 的理由是跨存储 join 昂贵，说明 join 该在写入时做——但本 change 数据源在内存，不适用。
  - **本地参考仓库不可用**：本工作区 `.dev/reference-repos.txt` 不存在（无本地参考仓库）。findings 全部
    来自业界调研（权威框架官方文档 + OTel 规范原文），已在 design.md「业界调研结论」节逐条附引用。
- design impact:
  - **状态枚举六值**（`present` / `clean` / `running` / `empty_trace` / `no_trace` / `unavailable`），
    每个负向态对应一条**实测确认过**的代码路径；`clean` 是**正向声明**（走完 trace 且零失败才给），
    直接落实 F2 的「`ok` 不能是默认值」。
  - **字段名不造第二套词表**（F3）：条目沿用 trace step 的既有键 `status` / `error_type`；节点级用 `state`
    而非 `status`，避开 LangFuse 那种「同一个词指两件事」的语义碰撞。
  - **bounded 三元组**（F4）：最近 N 条 + **真实总数** + 截断标志；负向态一律配可读原因文案，不返回空列表。
