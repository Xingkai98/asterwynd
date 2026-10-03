# Proposal: 工具结果生命周期 — 单一受管持有 + 全持有者释放

关联跟踪 issue：[#282](https://github.com/Xingkai98/asterwynd/issues/282)（主）。父 issue：[#280](https://github.com/Xingkai98/asterwynd/issues/280)。诊断来源：[#278](https://github.com/Xingkai98/asterwynd/issues/278)（已关闭）。

**本 change 是原 `agent-context-bound`（A）的归宿**：A 的核心（`messages` 工具结果 spill/ref）折叠进本 change，A 不再单独立项。A 的 proposal/design/grill/对抗验证（`agent-context-bound/2026-10-02` 分支）是本 change 的设计输入，其 design 已按对抗验证修正。

## Change Type

- primary: feature
- secondary:
  - agent-runtime
  - context
  - observability

## Why

### 问题：工具结果全文被**多个池子**持有，且从不释放

#278 复现了 4GB cgroup OOM，定位到根因：`compaction_gap=5` 放行单 agent 常驻上下文无界增长（实测单 run 冲到 **1078 万 tokens** ≈ 43MB 文本），**常驻字节 95%+ 是工具结果**；5 个并发子 agent 各涨各的 → 尖峰叠加 → OOM。B（`read-output-bound`，PR #281 已合入）治了「单条 Read 过大」的**源头**，但实测 B 后 RSS 峰值 1172MB vs 基线 1228MB（同量级）——**证明 OOM 是「跨轮累积驻留」，不是「单条峰值」**。

### 决定性实测（2026-10-03，本 change 的地基）

**同一个工具结果字符串被三处持有、是同一个对象**：

| 持有者 | 位置 | 实测 `is` 同一对象 |
|---|---|---|
| `messages` | `tool` 消息的 `content`（`loop.py:854`/`:1047`） | ✅ |
| `run.trace` | `run.trace.steps[].data["observation"]`（`manager.py:1349`/`:1425`/`:1440`/`:1459`） | ✅ |
| `tool_calls_made` | `ToolCallMade.result`（`loop.py:855`/`:1048`，随 `RunResult` 返回） | ✅ |

实测（`/tmp/t282_probe/probe_ownership.py`）：把 `messages` 的 content 换成预览、并释放 `tool_calls_made` 后，`run.trace` 的 observation **仍 `is` 原全文**（`trace observation 仍是全文: True`）——**全文不回 GC、RSS 不降**。

⇒ **单做任一处 = 白做**（这正是 A 单独做无效的原因）。**三者是同一批内存的三个引用，必须一起治。**

### 量级实测

`/tmp/t282_probe/probe_memory.py`（N=30 × ~192KB 工具结果，三处持有）：

| 场景 | tracemalloc cur | peak |
|---|---|---|
| 三处持全文（基线） | **5569 KB** | 5753 KB |
| 三处有界 | **83 KB** | 450 KB |
| 降幅 | **-98.5%** | -92.2% |

（5569KB ≈ 30×192KB，印证三处共享**同一对象**——不是三份拷贝。）

### 关键事实：`trace`/`tool_calls_made` 的全文**没有消费者**

模型面与人类面的出路都已 bounded（实测逐点核实）：

- `web/session.py:898` 只读 `text[:text_limit]`（截断）；
- `benchmarks/agent_runner.py:459` 只读 `result.startswith("[Error")`；
- `agent/main.py:_print_tool_call_summaries` 对超大结果本就打 collapsed preview（`tool_result_display.py`）；
- `agent/subagent/snapshot.py:77` 只数 `llm_iteration` steps；
- `TraceRecorder.full_trace` 字段注释已是 `retained for serialization compat only`。

**唯一读 trace observation 全文的是 `benchmarks/runner.py:661`（`trace.write_to_file` 落盘 `trace.json` 供事后分析）**——即 trace 的全文是「留作事后分析的账本」，不是模型运行所需。

⇒ **`trace`/`tool_calls_made` 不需要 ref（没人按 ref 回读全文），只需 bounded**；**只有 `messages` 需要 spill + ref**（模型当轮/需要时要用全文）。这比 A 的方案更简洁：**ref 基建只服务 `messages` 一个池子**。

## What Changes

1. **统一工具结果入库通道**（`loop.py`）：三处持有者的写入经**同一判定点**，保证同一 `result` 在三处被一致地有界化（`_tokens` 重置、标记、字节/ token 度量统一）。
2. **`messages` 工具结果 spill（有损驻留、无损可回读）**：**新鲜**结果保留全文（模型当轮要用），**已消费一轮且**（滑出近期窗口**或**单条超阈）后替换为「有界预览 + `result_ref`」；模型可按 ref **确定性无损回读**。
3. **`trace` 的工具结果 bounded**：`record_tool_result` 的 observation 超过阈值时存**有界预览 + 诚实标记**（无消费者按 ref 回读，故不落 ref）；保留 `status`/`error_type`/`tool_name` 等分析字段不变。
4. **`tool_calls_made` 的工具结果 bounded**：`ToolCallMade.result` 超过阈值时存有界预览（保留 `name`/`arguments`）。
5. **agent 通用 ref 存储**：把「可回读 ref」从 workflow 作用域**提升为 agent 通用**（根 agent 与子 agent 都可用），**复用 `WorkflowStore` 的 ref 格式族 / 原子写 / 分页读实现**，置于 `.asterwynd/` 新命名空间。身份寻址：**根 agent 用 `session_id`、子 agent 用 `run_id`**（对抗验证：`subagent_id` 不持久、`run_id` 才跨 resume 稳定）。
6. **通用回读工具**：**泛化 `ReadWorkflowResult`**（按 ref 前缀分派 `artifact://workflow/...` 与 agent ref），**不新增工具**（#248：工具越多越选错）；工具名/schema 保持兼容。
7. **压缩硬顶（兜底）**：`MemoryManager.compact_if_needed` 在上下文超过**硬上限**时**无视 `compaction_gap` 强制执行**——`gap` 是防抖，SHALL NOT 成为无界增长的许可证。
8. **spill 可观测（不静默）**：spill/bounded 的发生与量 SHALL 可观测（计数 + 字节），沿用 #275/#279「截断必须显式可见」纪律。
9. **Web 工具结果展开改为按需回读**：`tool_result` 事件默认只发预览 + `tool_call_id`（**不发全文**）；Web Expand 时按标识向服务端**按需取回全文**（收起释放浏览器缓存）。这把「全文外发」从「无条件推给浏览器」变为「用户想看才取」。

**不变**：`compaction_gap`/`max_tokens` 等**默认数值**（调参另议）；workflow DSL 语义；`WorkflowStore` 既有 ref 格式与 `ReadWorkflowResult` 行为（只增不改）；**图片路径**（见 Non-Goals）；**CLI 工具结果打印**（走 `tool_calls_made`，不受 Web 事件影响）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `context-engineering`：
  - **ADDED** 新 Requirement「工具结果全文的单受管持有与释放」——任何持有工具结果全文的池子（`messages`/`trace`/`tool_calls_made`）SHALL 有界；替换/释放 SHALL 使全文**可被 GC**（SHALL NOT「换引用、原文仍被另一池子持有」）；`messages` 的替换 SHALL 可**按 ref 无损回读**且对模型可见；SHALL NOT 破坏 tool-call 链合法性。
- `memory-context`：
  - **MODIFIED** 既有 Requirement「超过 90% token 阈值时触发压缩」——压缩 SHALL 在上下文超过硬上限时**无视 `compaction_gap` 强制执行**，使常驻上下文有界。
- `web-ui`：
  - **MODIFIED** 既有 Requirement「Chat 视图按 display metadata 展示工具结果」——全文 SHALL NOT 随 `tool_result` 事件无条件下发；展开改为按 `tool_call_id` **按需向服务端取回全文**（收起释放缓存；取不回时如实标「全文不可用」）。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

| # | 指标 | 主/辅 |
|---|---|---|
| **A0** | **GC 不变量**：`messages` spill + `trace`/`tool_calls_made` bounded 后，原工具结果全文**弱引用验证不可达**（`weakref` 回 None / `gc` 无强引用）——机械可验，不依赖 RSS | **主指标** |
| **A1** | `messages`：陈旧结果被替换为预览 + ref；**当轮/未消费完的新鲜结果不被替换** | **主指标** |
| **A2** | `trace`/`tool_calls_made`：超出阈值时**不再持全文**（bounded 预览）+ 诚实标记；`status`/`name`/`arguments` 等分析字段不变 | **主指标** |
| A3 | 被 spill 的 `messages` 结果可按 ref **逐字节无损回读**；根 agent 与子 agent 均可用 | 辅 |
| A4 | ref 不存在时**不谎称可回读**（沿用 `_bounded_summary` 的 `has_ref` 纪律） | 辅 |
| A5 | **不退化**：既有测试全绿；tool-call 链在 spill 后仍合法；小任务不因 spill 显著变慢 | 辅 |
| A6 | 硬顶：构造超硬上限上下文 + 未到 gap → 断言**仍压缩** | 辅 |
| **E0** | **端到端对照**：#278 复现器缩比版（单 agent 直读）下 asterwynd RSS 峰值**对比基线**——**如实记录**（B 后基线 1172MB） | 对照 |

**通过门槛**：A0 + A1 + A2 成立（三处确实有界且可 GC），A3–A6 可验证。**E0 作对照观测**（RSS 受环境与邻居影响，不作为唯一判据——A0 的 GC 不变量是更硬的机械判据，见 design D0）。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 命中 `full` 判据「架构级改造」「对标业界产品」「走 grill 的非平凡 change」。本 change 触及 `MemoryManager`/`loop.py` 的**工具结果入库契约**（改 `messages` 内容、引入新持久化命名空间与回读工具），且需业界依据的**形态与时机**决策。
- research questions:
  - **RQ1**：业界 agent 框架怎么处理「工具结果过大 / 过多」——剪除、落盘 + 回读、还是只靠摘要？
  - **RQ2**：剪除的**时机与判据**是什么？（触发条件、保留多少、值得不值得）
  - **RQ3**：「无损落盘 + 按需回读」与「有损摘要压缩」如何**分层协作**？
  - **RQ4**：剪除/替换对模型**如何可见**（避免静默丢信息）？
- findings:
  1. **RQ1/RQ3 结论：业界主流是「剪除先于摘要」，两个独立来源一致。** ① `deepseek-harness` `docs/agent-lifecycle.md:85`：*"optional **tool-result pruning runs before summary selection**"*；② **Anthropic context editing**（`clear_tool_uses_20250919`，beta header `context-management-2025-06-27`）：*"clearing still ... clearing edit comes **before** the compaction edit"*——**prune（清除）与 compaction（摘要）是两个分离的编辑**，pruning 在前。⇒ 本 change 的 D3（spill 排在 `compact_if_needed` 前）有两个独立业界先例。
  2. **RQ2 结论：Anthropic 的参数直接映射本 change 的判据形态。** `trigger`（默认 100K input tokens 或 tool_uses 数）、`keep`（默认保留最近 **3** tool use/result 对）、`exclude_tools`（memory/skill 等工具不清）、`clear_at_least`（最小清除量——**清得不够就不清**，避免不值得地打断 prompt cache）。⇒ 支撑本 change「触发阈 + 保留最近 + 值得才清 + 白名单」的判据（D3）。
  3. **RQ1 的**本 change 相对业界是**更强（更保守）的形态**。Anthropic 的 `clear_tool_uses` 是**不可回读的移除**（"cleared content is removed, not replaced"）；本 change 的 `messages` spill 是**替换为预览 + ref，可无损回读**——即「prune 的无损版」。这正是本 change 需要**自建 ref 基建**（复用 `WorkflowStore` 实现，D4）的原因，也是它的**创新点**（本地 6 仓库与 Anthropic 均无「可回读剪除」同款，见 finding 5）。
  4. **RQ4 结论：Anthropic 提供剪除的可观测统计。** 响应带 `cleared_tool_uses` / `cleared_input_tokens`，token-count 端点同时返回 `original_input_tokens` 与后编辑的 `input_tokens`。⇒ 本 change 的 **A5（spill 可观测）** 有业界对照：剪除必须**可计数、可观察**，不静默。项目内先例：`_bounded_summary`（`manager.py:53-78`）的 `has_ref` 诚实纪律 + `[truncated; full result in result_ref]`。
  5. **本地 6 仓库**（`/home/shared/agent-study/reference-repos/`，本次以 `deepseek-harness` 为主证）：「无损落盘 + 按需回读」**无同款**——最接近的是分页/截断（`pi`/`kimi-code`/`opencode` 的各类 limit）与 codex 的压缩并发限（`MAX_CONCURRENT_COMPRESSION_JOBS=2`），均**不解决常驻**。⇒ 本 change 的 spill/ref 形态是创新点，须自证边界（见 design D3/D4）。**WebSearch 已用于取 Anthropic context editing 一手文档**（`platform.claude.com/docs/en/build-with-claude/context-editing`）。
- design impact: 见 design **D0**（GC 不变量作验收——比 RSS 硬）、**D1/D2**（三持有者分离处理：messages 需 ref、trace/tcm 不需）、**D3**（剪除先于压缩，两先例）、**D4**（ref 基建复用 + 身份寻址修正）、**D7**（spill 可观测，Anthropic 对照）。**调研对设计的主要影响**：finding 1 把「剪除先于压缩」从单先例升为双先例；finding 3 明确本 change 比业界更强（可回读）故须自建 ref；finding 4 新增「spill 可观测」为验收项。

## Impact Analysis

- **能力域**: `context-engineering`（工具结果生命周期）+ `memory-context`（压缩行为）。
- **代码**:
  - `agent/loop.py` — 两次 `messages.append(tool_result_message(...))`（`:854`/`:1047`）+ 两次 `ToolCallMade(result=result)`（`:855`/`:1048`）+ `trace_recorder.record_tool_result(..., result)`（`:997`）**统一经一个工具结果入库通道**（统一判定/截断/`_tokens` 重置）。**本 change 最敏感改动面**（改 `messages` 内容，关系 tool-call 链合法性）。
  - `agent/memory/manager.py` — 新增 `messages` 剪枝步骤（在 `compact_if_needed` 前）；`compact_if_needed` 加硬顶；`_count_message_tokens` 的 `_tokens` 缓存须在 `content` 变更后失效。
  - `agent/trace_recorder.py` — `record_tool_result` 对超阈 observation 存 bounded 预览 + 诚实标记（`record`/`to_dict` 结构不变）。
  - `agent/result.py` / `agent/loop.py` — `ToolCallMade.result` 超阈 bounded。
  - **新增** agent 通用 ref 存储（复用 `WorkflowStore` 的 ref 格式/原子写/分页读，置于 `.asterwynd/artifacts/`）。
  - `agent/tools/builtin/subagents.py` — 泛化 `ReadWorkflowResult` 按 ref 前缀分派（工具名/schema 不变），并**改写工具 description**（现为 workflow 专用文案）。
  - `agent/subagent/manager.py` — `_write_result_artifacts`/`_bounded_summary` 既有模式复用；确认 ref 身份（根 `session_id` / 子 `run_id`）与注册路径（根 / 深度到限子 agent 均可用）。
  - **Web（D12，形态 c）**：`agent/loop.py` 的 `tool_result` 事件 payload 去全文、增 `tool_call_id`；`web/session.py` / `web/server.py` 新增只读端点 `GET /api/sessions/{id}/tool-result/{tool_call_id}`（`session.messages` 定位 → 全文直返 / 已 spill 解析 ref 读回 / 找不到返 missing）；`web/static/chat.js` 的 Expand 改 fetch 懒加载 + Collapse 释放缓存。
- **测试**:
  - **必须新增**：**GC 不变量**（A0，`weakref`/`gc` 断言三处不再持全文；**断言内存字段**）；`messages` 陈旧被替换 / 新鲜保留 / **穿透窗口** / **预览保尾**；`trace`/`tool_calls_made`/`arguments` 超阈 bounded；按 ref 逐字节无损回读；无 ref 不谎称（`has_ref`）；tool-call 链在剪枝后合法；硬顶无视 gap 生效；`_tokens` 缓存失效；图片字节维度；残余边界（后台注入不被剪）。
  - **必须新增（Web）**：`tool_result` 事件不含全文；展开端点按 `tool_call_id` 返回全文（含已 spill 走 ref 的路径）；消息被驱逐时返回 missing。
  - **必须新增（端到端）**：#278 复现器缩比版（单 agent 直读，RSS 峰值对照基线）。
  - **必须回归**：`agent-runtime` tool-call 链测试；`memory-context` 既有压缩测试；`context-engineering` Read/分页测试；`web-ui` 工具结果事件/展开测试；全量 `uv run pytest -q`。
- **文档**:
  - `openspec/specs/context-engineering/spec.md` + `openspec/specs/memory-context/spec.md` + `openspec/specs/web-ui/spec.md`（current spec 同步，受保护路径）。
  - `docs/openspec-change-backlog.md`（受保护路径）。
  - `README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描。
- **流程（process）**: 触及受保护路径，需结构化事件 + grill + building review；实现须独立 worktree、`tool-result-lifecycle/2026-10-03` 分支。**change type = feature → 实现前必须走 `batch-grill-me` + 停轮确认 Open Questions**；**grill 结论须先走独立对抗验证**（`reviews/grill-adversarial.md`）。
- **与既有 change / issue 的边界**:
  - **#278**（诊断，已关）：本 change 是其修复的完整版；**#280** 是父 issue。
  - **B（`read-output-bound`，PR #281 已合入）**：治单条峰值（源头），本 change 治累积驻留（生命周期）。**B 的 E0 数据（1172MB 同量级）正是本 change 必须做的实测依据。**
  - **A（`agent-context-bound`）**：**本 change 是其归宿**；A 的 `messages` spill + ref 基建 = 本 change 需求 2/5/6；A 的**压缩硬顶** = 本 change 需求 7。A 不再单独立项。
  - **`_workflows` slots + 跨图壳清理（#278 里程碑 A 的另一半）**：**Non-Goal**（见下）——不同机制、增长慢（+2MB/图）、改动面独立（scheduler + `GetWorkflow` 读路径），另立 change。
  - **#279**（`max_items` 静默截断）：独立缺陷，不合并（但本 change 遵循同一「不静默」纪律）。
  - **#276**（上限数值重估）：参数 vs 机制，独立。
- **代价权衡**: spill 增一次「落盘 + 必要时回读」开销——只在**结果足够大**时触发（阈值），小结果零开销；`trace`/`tool_calls_made` 的 bounded 是**纯收益**（无消费者的全文本就不必存）。收益：常驻内存从「线性膨胀」变为「有界」。
- **可回滚性**: 改动集中在入库通道 + `MemoryManager` + `trace_recorder` + `result` + 新增 store/tool；回滚 = revert，无数据迁移（ref 文件随会话目录，可重新生成）。

## Non-Goals（摘要）

- **不改** `compaction_gap` / `max_tokens` 等默认数值（调参另议）。
- **不改** workflow DSL 语义。
- **不做**「有损压缩工具结果」（那是 compaction 的活；`messages` spill 是无损的）。
- **不引入**第二套与 `WorkflowStore` 漂移的 ref 格式（复用其实现）。
- **不处理 `_workflows` scheduler slots + 跨图壳清理**（`_sessions`/`_workflows` 字典「已结束图壳」的释放）——**这是 #278 里程碑 A 的另一半，另立 change**。理由：不同机制（图节点产出 vs 单 run 工具结果）、增长慢（+2MB/图，非 OOM 紧急项）、改动面独立（需改 `GetWorkflow` 活读路径为终态快照读）。
- **不治「非工具大内容」**（超大 user 粘贴 / 超大 `tool_calls[].arguments` 在 recent 内 / 后台注入输出）——**另立 [#283](https://github.com/Xingkai98/asterwynd/issues/283)**（决策见 design D7 残余边界）。理由：改动触及 compaction 的 recent-keep 不变量、风险面独立。**本 change 不得宣称「一切内容有界」，只保证「工具结果主导」的上下文有界。**
- **图片结果（`list[ContentBlock]` 含 base64）的 spill 策略由 design D6 定义**：至少 SHALL 使其**不绕过字节维度**（对抗验证实测：图片 token 估 1000/张、实际 base64 可达数十 MB）。
