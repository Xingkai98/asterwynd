# Proposal: 模型面出现的子 agent 文本一律 bounded（fix-issue-213-transcript-item-bound）

## Change Type

- primary: bugfix
- secondary:
  - subagents

## Why

issue #213 报告：`InspectSubagentTranscript` 工具路径只约束**条数**（`limit ≤ 200`），对**单条内容**
没有任何上限。实测（子 agent 输出 30000 字）：工具返回 **30000 字**，无截断标记。

而 HTTP 路由那条路是有界的（`web/session.py` 的 `_bounded_messages` 截到
`TRANSCRIPT_CONTENT_LIMIT = 4000`）。**同一份 `inspect_transcript` 结果，网页看是 bounded 的、
模型看到的是无界**——父 agent 的上下文会被单次工具调用撑爆，而撑爆它的量由子 agent 决定。

> **口径不一致本身就是 bug**（issue #212 同根）。`manager.py:62-63` 的注释早已把契约定死：
> 「『单条内容』在模型面与 HTTP 面是同一个概念，不该有两个数」——但那条契约只对
> `tool_calls[].arguments` 执行了，`content` 漏在同一句论证之外。

### 排查后范围比 issue 标题更大（实测确认）

| # | 出口 | 现状 | 实测 |
|---|---|---|---|
| 1 | `InspectSubagentTranscript` | `content` / `summary` 无截断 | 30000 字 → 30000 字 |
| 2 | **`GetSubagentRun`** | `to_result_dict()["summary"]` 是全文 | 30000 字 → 30000 字 |
| 3 | `RunSubagent` / `CancelSubagentRun` | 同走 `_format_run_envelope` | 同上 |
| 4 | `RunPattern` | N 个 worker × 全文拼接 | 一次调用放大 N 倍 |

**出口 2 是「取子 agent 结果」的默认方式**，很可能比 #213 本尊更常被踩到。

**讽刺之处**：`to_result_dict()` **已经**同时提供 `bounded_summary`（裁剪早就算好了），
只是模型面消费的是 `summary`（全文）那一份。这不是「少了功能」，是「算好了没用」。

### 顺带发现的确定性假话

`_bounded_summary` 截断后追加 `"\n…[truncated; full result in result_ref]"`。但 `run.workflow_id`
为空时 `_write_result_artifacts` 早退，`result_ref` 保持 `None`——**实测确认**：`bounded_summary`
说「全文在 result_ref」，而同一条记录里 `result_ref: None`，**全文根本没落盘**。

这是仓库明令禁止的「报假话」，且一旦把 `bounded_summary` 接进更多出口（本 change 要做的事），
假话会从 1 处扩散到 4 处。

## What Changes

**A. `InspectSubagentTranscript` 的两个 scope 都加单条内容上限**（#213 本尊）

`summary` 分支与 `recent_messages` 分支的单条文本一律按 `TRANSCRIPT_ITEM_LIMIT`（= 4000，与
HTTP 面同数）截断，并回流 `summary_truncated` / `content_truncated` 布尔标志。

`include_tool_results=True` 时 tool 角色消息的 content 由同一处覆盖——那才是 30000 字最可能的
真实来源（一次 Bash/Read 的整份输出）。

**B. 模型面 run envelope 改为 bounded**（出口 2/3）

`_format_run_envelope` 默认返回 bounded `summary`（复用**已有的** `bounded_summary`，
不引入新常量），全文仍可通过 `summary_ref` / `result_ref` 按需读取。
调度器的内部消费点显式要求全量——它拿 envelope 喂 `state.summary` 做下游聚合，
截断会降低聚合质量。

**C. `RunPattern` 的 worker summary 同口径 bounded**（出口 4）

**D. 修 `_bounded_summary` 的假话**

截断标记只在**确有落盘 ref** 时提它；没有落盘时只说「已截断」，不说「全文在 X」。

**E. 常量治理**

`TOOL_CALL_ARGUMENT_LIMIT` 现在实际要同时约束 `arguments` / `content` / `summary` 三处，
名字已误导。新增 `TRANSCRIPT_ITEM_LIMIT` 承载语义，旧名保留为兼容别名（churn 最小）。

**F. HTTP 面的截断标志改成取或**

生产者开始截 `content` 后，路由层的 `content_truncated` 若仍只比较本层长度，会在
「生产者截了、本层预算更宽」时报「没截断」——**谎报**。这与 #212 在 `arguments` 上修过的
是同一个 bug 的第二例，必须对称处理。

## Non-Goals

- **不减小 `run.summary` 本身**：它是全文，经 `to_result_dict` → `_format_run_envelope` →
  `scheduler` 的 `state.summary` → `_node_task_text` 传导到下游聚合。截断只能发生在**出口投影**。
  两条既有测试（`test_result_representations.py`）直接钉死这一点。
- **不承诺「响应总量有上限」**：单条消息里 `tool_calls` 的**条数**没有代码上限（provider 层面的
  隐性限制不算契约）。spec 措辞只能是「单条内容」。
- **不截 `run_id`**：它是调用方传入的回显参数，不是放大路径。
- **不动 `ReadWorkflowResult`**：它已有 bounded 口径（分页 + `total_chars`/`truncated`）。
- **不动 `GetWorkflow`**：走 `parent_envelope()`，节点文本已裁到 `_PARENT_FIELD_LIMIT`。
- **不动 message bus——但必须说清楚：它当前是****无界**的，不是「已有 bounded 口径」**。
  实测（本 change 排查期独立复现）：`ReadBus` 的单条消息可原样返回 30,000 字；
  `RunPattern` 返回体里的 `result["bus"]`（`bus.snapshot_payload()`）100 条 × 1600 字
  → **172,703 字符**全部进模型上下文。这两处返回的都是**子 agent 撰写的内容**，
  落在本 change 的动机范围内，**只是不在本 change 的交付边界内**：
  按 codex 建议的范围划分，bus 属独立的 PR2（与本 change 的 4 个结果出口不同路径、
  不同数据结构），另立 issue **#224** 跟踪。本 change 的标题承诺因此收敛为
  「**结果出口**的模型面文本一律 bounded」，不说「所有模型面出口」。
  （初版此条写「bus 已有各自的 bounded 口径」——**那是假话**，已按审阅 R1 Issue 2 更正。）
- **不在工具侧加第二道截断**：生产者已兜底，双份截断会产生「谁的标志为准」的新问题。
- **不修 `web/session.py` 的 `payload["status"]` 覆盖问题**：与 bounded 无关的既有瑕疵，另记。

## Capabilities

### Modified Capabilities

- `subagents`：「子 transcript inspect 默认受限」补「单条内容上限与 HTTP 出口同值，两面 SHALL NOT
  分叉」——原 Requirement 只写「限制返回范围」+「最近 N 条」，字面只覆盖条数。
- `agent-runtime`：「父 run 通过显式运行时接口管理子 session」补「返回的 run envelope SHALL bounded；
  全文 SHALL 通过 ref 按需读取」——原 Requirement 只定了「返回结构化结果」，未定 bounded 义务。

## Dependencies

- 无新依赖。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/subagent/manager.py` | 常量治理 + `_clip`/`_bounded_content` + inspect 两分支截断 + `_format_run_envelope` 默认 bounded + 修 `_bounded_summary` 假话 | **中**（默认值翻转：改的是「工具面拿到什么」的对外行为） |
| `agent/subagent/scheduler.py` | 内部消费点显式要全量 summary（1 处） | 低 |
| `agent/subagent/patterns.py` | worker summary 走 bounded | 低 |
| `web/session.py` | 截断标志取或 + 注释同步 | 低 |
| `agent/tools/builtin/subagents.py` | 工具描述校正（明说单条有上限、全文走 ref） | 低 |

**契约影响（对外）**

- **模型面返回变短**：4 个出口的单条文本从「全文」变为 bounded。这是**有意的**（现状是父 agent
  上下文可被子 agent 撑爆），但属可观测行为变更，已在 spec 写明。
- **`bounded_summary` 的文本可能变化**（修假话）：当 `result_ref` 不存在时，截断标记不再声称
  「全文在 result_ref」。既有测试若断言了该字样需同步。
- **`run.summary` 不变**（全文），`summary_ref` / `result_ref` 指向全文——按需读取的路径保持完整。

**测试影响**

- 新增：4 个出口各有界 + 标志正确 + ref 可取全文 + 假话修复 + 路由取或
- 改造：`tests/web_tests/test_workflow_node_transcript.py:624` 的「两个 4000 相等」断言升级为三处同值
- 回归：`tests/agent/subagent/`（重点 `test_result_representations.py`、`test_workflow_result_refs.py`）、
  `tests/web_tests/`
- **变异验证**：`_bounded_content` 改回 identity / 取或改成只看本层 / envelope 传回 full
  → 对应测试必须变红
- **参数选择教训**：既有测试写过「输入必须真的超过上限」的注释——新测试用 issue 里的 30000 字，
  不用 5000，否则「返回 ≤4000」恒真

**文档影响**

- `docs/agent-internals.md` 的 inspect 示例已过时（只列 3 键、无截断说明）
- 关键词扫描 `docs/`、`README.md`、`CONTEXT.md`、`docs/architecture.md`

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 属 bugfix（无新增能力面），根因与修法已由 issue #213 给出（复用同一套 `content_limit`
  口径），且上游决策已锁定——同根的 issue #212（PR #214）已在同一仓库确立了「生产者无条件截断 +
  标志随文本回流」的契约与实现范式（`agent/subagent/manager.py` 的 `_bounded_arguments`，
  含 `openspec/changes/archive/` 中 workflow-result-aggregation 对 `bounded_summary` 的三表示决策）。
  本 change 是把该既有契约执行到漏掉的那一维，无待定设计项。
