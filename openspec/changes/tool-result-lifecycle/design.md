# Design: 工具结果生命周期 — 单一受管持有 + 全持有者释放

## Context

#278 实测：agent 常驻上下文无上界，根因是**工具结果原样驻留 `messages`**（占常驻字节 95%+），`compaction_gap` 放行增长窗口；B（`read-output-bound`）治了单条峰值但 E0 实测 RSS 同量级（1172 vs 1228MB）——**累积才是主因**。

本 change 在 #282 的实测地基上，把工具结果全文从「被多个池子持有、只增不减」改为「单一受管持有 + 随生命周期释放」。

### 已实测的机制事实（本设计的地基）

1. **三持有者、同一对象**（2026-10-03 实测，`/tmp/t282_probe/probe_ownership.py`）：同一 `result` 字符串被 `messages`（`tool_result_message(id, result)`）、`run.trace`（`record_tool_result(..., result)` → `steps[].data["observation"]`）、`tool_calls_made`（`ToolCallMade(result=result)`）三处持有，`is` 判定全为 `True`。替换 `messages` + 释放 `tool_calls_made` 后，trace 仍 `is` 原全文（`True`）。
2. **`Message.content` 是 `str | list[ContentBlock]`**（`message.py:150`，**非** 旧 design 误写的 `str`）；图片工具结果返回 `list[ContentBlock]`（base64 `ImageBlock`，`read.py`/`browser_screenshot.py`/`read_doc.py`）。
3. **`_tokens` 缓存**（`manager.py:141-143`）缓存在非序列化字段 `Message._tokens`；原地改 `content` 后不重置 → `count_tokens` 返回**旧的全量值**（实测 25001 不变），使压缩误判。**任何改 `content` 的代码 MUST 置 `_tokens=None`。**
4. **两次入库点**：`loop.py:854`（错误路径）与 `:1047`（正常路径），都是 `messages.append(tool_result_message(tool_call.id, result))`，**原样入库**；紧随其后各 `tool_calls_made.append(ToolCallMade(..., result=result))`（`:855`/`:1048`）；`trace_recorder.record_tool_result(..., result)` 在 `:997`。**三处共享同一 `result` 变量。**
5. **`_call_llm` 每轮发全量 `messages`**（`loop.py:1194`）——常驻即成本。
6. **`compact` 保留 recent window 原样**（`_recent_with_tool_chains`，`manager.py:371-389`；写回 `manager.py:309`）——**硬顶压不动 recent 内的大 tool 结果**（实测 8×20K 压后 5 条 100KB 存活）。
7. **可复用诚实模式**：`_bounded_summary`（`manager.py:53-78`）实现「超预算截断 + `[truncated; full result in result_ref]`」，要求调用方**如实传 `has_ref`**。
8. **`WorkflowStore`**（`agent/subagent/workflow_store.py`）：ref 格式 `artifact://workflow/<workflow_id>/<key>`、`save_result`、分页 `read(offset, limit)`、原子写 `_atomic_write`（tmp+`os.replace`）；但 `parse_ref` **硬编码** `artifact://workflow/` 前缀 + `path_for` 校验 `workflow_id == self.workflow_id`——**不能字面承载 agent 作用域**（须泛化）。
9. **`MemoryManager` 三处共用**：根（`main.py:296`）、子（`manager.py:1318`），都是 `MemoryManager(max_tokens=80_000)`——**改一处影响所有 agent**。
10. **`.asterwynd/` 命名空间**：sessions（`main.py:224`）、subagents（`snapshot.py:35`）、workflows（`workflow_store.py:60`）、uploads（`uploads.py:17`）。`SessionStore.remove()` 用 `shutil.rmtree`（`session.py:189`）——**artifacts/ 必须在 `sessions/<id>/` 之外**，否则清会话会连 ref 一起删。
11. **`run.trace` 全文无消费者**（除 benchmark 落盘）：`web/session.py:898` 截断读、`benchmarks/agent_runner.py:459` 只读前缀、CLI collapsed preview、`snapshot.py:77` 只数 steps；**唯一**读全文的是 `benchmarks/runner.py:661`（`trace.write_to_file`）。

## Goals / Non-Goals

### Goals

- **工具结果全文单受管持有**：`messages`/`trace`/`tool_calls_made` 三处 SHALL 有界，替换后全文**可被 GC**。
- **`messages` 无损**：被 spill 的结果可按 ref 完整回读（区别于有损摘要）。
- **不改协议**：`Message` 结构、tool-call 链合法性不变。
- **对模型/观察者可见**：spill 不静默。

### Non-Goals

- 不改默认数值（`compaction_gap` / `max_tokens`）。
- 不做有损工具结果压缩（属 compaction）。
- 不引入第二套 ref 格式。
- 不处理 `_workflows` scheduler slots / 跨图壳清理（里程碑 A 的另一半，另立 change）。

## Decisions

### D0 — 验收主指标是 **GC 不变量**，不是 RSS

本 change 的**机械可验**判据是：spill/bounded 后，原工具结果全文**不再被任何池子强引用**——用 `weakref.ref(big)`（断言回 `None`）或 `gc.get_referrers`（断言无三持有容器）锁。

**为什么不是 RSS**：RSS 受解释器内存池、并发邻居、采样时机影响（#278 实测本机是共享 cgroup）；把 RSS 当唯一判据会让「机制做对了但 RSS 降幅不显著」误判为失败。**GC 不变量是机制正确性的直接证明**，RSS（E0）作对照观测。

> **待 grill 确认**：GC 不变量的测试如何避免 flaky（`gc.get_referrers` 会看到测试自身的引用；`weakref` 对 str **不可用**——str 不支持弱引用，须换用容器对象或 `gc` 可达性）。这是**实现难点**，见 Risks。

### D1 — 统一工具结果入库通道（`loop.py`）

三处写入（`messages` / `tool_calls_made` / `trace`）**经同一判定点**：算一次「是否需要 bounded/落地」的决策，应用到三处，保证一致（`_tokens` 重置、标记、度量维度统一）。

**不改变写入顺序/结构**：仍 `messages.append(tool_result_message(id, content))`、`tool_calls_made.append(ToolCallMade(...))`、`record_tool_result(...)`，只是 `content` 由通道决定（全文 / 预览）。

> **待 grill 确认**：通道放在 `loop.py` 内部helper，还是 `MemoryManager` 的方法？trace/tool_calls_made 的 bounded 逻辑与 `messages` 剪枝是否同一处？

### D2 — 三持有者**分离**处理：`messages` 需 ref，`trace`/`tool_calls_made` 只需 bounded

**决定性区别**：
- `messages` 的全文**有消费者**（模型当轮/按需推理）→ 需 **spill + ref**（可无损回读）。
- `trace`/`tool_calls_made` 的全文**无模型面消费者**（D11）→ 只需 **bounded**（预览 + 诚实标记），**不落 ref**。

**为什么不给 trace 也落 ref**：没有消费者按 ref 回读（web/CLI/benchmark 全读截断/前缀），落 ref 只是徒增磁盘与复杂度；benchmark 若要事后全文，那属**另一需求**（可让 benchmark 显式开启 full trace，见 D8）。

> **待 grill 确认**：`ToolCallMade` 的 bounded 会不会影响 benchmark 对工具结果的判定（实测 `agent_runner.py:459` 只 `startswith("[Error")`——bounded 预览仍保留前缀，安全；但需核实 benchmark 是否有别的全文消费）。**这是与 A 方案最大的形态差异，须重点攻。**

### D3 — `messages` spill 时机与判据：**「已消费一轮」∩（滑出窗口 ∪ 单条超阈）**

一个工具结果被剪的条件（**同时**满足）：

1. **已被模型消费过至少一轮**（对抗验证关键修正）：剪枝点在结果产生轮的**末尾**（`loop.py:1047` → `:1056`），模型要到**下一轮 `_call_llm`** 才消费。故**产生当轮不剪**（否则「巨型新鲜结果立即剪」会伤害任务完成、撞 A5）——**记录本轮新增结果，下一轮起才允许剪**。
2. **且**满足其一：
   - **滑出近期窗口**（`recent_window`，默认 10 条——**注意是消息条数非轮数**，一条 assistant+tool 对占 2 条，故 window=10 实际覆盖约 5 轮；措辞在 spec/代码须钉死「条」）；
   - **单条超阈**（token 或**字节**，见 D6）。

**为什么窗口 ∪ 单条，且单条要能独立触发**：只靠窗口 → 单条 200KB 在窗口内每轮全量重发，峰值不降；只靠单条 → 正常结果也剪、伤任务。取或，且**单条判据不受窗口保护**（大结果即使新鲜也要剪）——**但受「已消费一轮」保护**（修正后不会在模型用之前抽走）。

> **待 grill 确认**：单条阈取值（A 推荐 `max_tokens×0.25`）+ 窗口「已消费一轮」的具体实现（`loop.py` 记录本轮新增 set；或给 `Message` 打「产生轮次」标记）。**这是本 change 最核心的待定项。**

### D4 — agent 通用 ref 存储：复用 `WorkflowStore` 实现，**泛化作用域**；身份**按 agent 类型分**

新增 agent 通用 ref 落点，**复用 `WorkflowStore` 的 ref 格式族 / 原子写 / 分页读**，置于 `.asterwynd/artifacts/`（**在 `sessions/<id>/` 之外**，避免 `SessionStore.remove()` 的 `rmtree` 误删）。

**身份寻址（对抗验证修正）**：
- **根 agent 用 `session_id`**（resume 时 `session_id` 不变、`run_id` 新起——按 `run_id` 会悬空）；
- **子 agent 用 `run_id`**（对抗验证：`subagent_id` 是 `uuid4().hex[:8]` 进程内标识、不落盘；durable 身份是 `run_id`，checkpoint 落盘 `session_id=run.run_id`，`resume_subagent(subagent_id, run_id)` 靠 `run_id` 取）。

**生命周期**：会话/子 agent 归档或删除时随其目录清理；**run 结束不删**（保 resume 可回读）。**当前 `_sessions` 不清理**（里程碑 A），故本 change 的清理路径须**显式实现**（不依赖里程碑 A）。

> **待 grill 确认**：ref 前缀命名（`artifact://agent/...` 还是统一）；`parse_ref` 泛化方式（工具层前缀路由 vs store 层参数化）；清理触发点。

### D5 — 回读工具：**泛化 `ReadWorkflowResult`**，不新增

`ReadWorkflowResult` 按 ref 前缀分派（`artifact://workflow/...` 与 agent ref 都读），**工具名/schema 保持不变**（兼容）。**不新增工具**（#248：工具越多越选错）。

**必须落实**（对抗验证点名）：
- **注册路径**：该工具现由 `loop.py:_ensure_subagent_tools_registered` 构造、**依赖 `subagent_manager`**；须确认**根 agent 与深度到限的子 agent**都注册可用（`expose_subagent_tools=False` 的入口会整套不注册）。
- **改工具 description**：现为 workflow 专用文案，泛化后须改写，否则模型仍以为只读 workflow。

> **待 grill 确认**：泛化 vs 并列的边界；根 agent 无 `subagent_manager` 时回读工具的构造来源。

### D6 — 度量维度：**token 与字节双维度**，图片纳入字节

**对抗验证核心修正**：图片 `ImageBlock` 在 token 账本上是**固定 1000/张**（`message.py:89-99`），但正文 base64 可达 **MB 级**（`MAX_IMAGE_SIZE=20MB`）——**token 硬顶对图片失效**。故：

- 单条阈（D3）与硬顶（D7）SHALL 同时约束 **token 估算** 与 **常驻字节**；
- 图片结果（`list[ContentBlock]`）SHALL 至少按**字节**纳入判定——**SHALL NOT 因 token 计 1000 就放行 MB 级 base64 常驻**；
- 图片 spill 策略：图片无法「预览 + 文本 ref 无损回读」（base64 落盘再回读 = 放大）——**待 grill 定**（选项：图片不参与文本 spill 但计入字节预算触发压缩；或图片超阈时转「路径引用」——但图片已有 `file_path`，见 `trace_recorder._sanitize_observation` 已用 `[image: ref]`）。

> **待 grill 确认**：图片结果的具体策略（A 的「图片不参与 spill」已被对抗验证否决——那会让硬顶对图片密集 run 失效）。**这是 grill 必攻项。**

### D7 — 压缩硬顶：超硬限**无视 gap 强制压**

`compaction_gap` 仅防抖，SHALL NOT 让上下文无界。`compact_if_needed`：超硬上限（独立常量/可配置）时**无视 gap** 强制 `compact`。

**次序**：**先剪枝（D3）→ 再判硬顶 → 超了才强压**（剪完可能已达标，无需压）。

**与 D3 的交互（对抗验证的死结）**：`compact` 的 `_recent_with_tool_chains` **原样保留 recent window 内的大 tool 结果**（事实 6）——若大结果卡在 recent 内，硬顶会**每轮空转**。**解法 = D3 的单条阈**：超阈的大结果被剪，硬顶才有东西可压。

### D8 — 诚实标记：ref 不存在就不谎称可回读

沿用 `_bounded_summary` 的 `has_ref` 纪律：只有**确实落盘成功**才写「full result in result_ref」；否则写「已截断、全文不可回读」（`[truncated]`）。`trace`/`tool_calls_made` 的 bounded 无 ref，标记 SHALL 如实为「已截断」（不指向 ref）。

### D9 — spill 可观测（不静默），沿用 #275/#279 纪律

spill/bounded 的**发生次数与字节数** SHALL 可观测（计数 + 量级，如「N 条结果被 spill、共释放 M 字节」），经既有 trace/event 通道暴露。业界对照：Anthropic context editing 响应带 `cleared_tool_uses`/`cleared_input_tokens`。

> **待 grill 确认**：可观测落点（trace step 类型？run result 字段？）；是否复用 `memory_compaction` step 的形态。

### D10 — `_tokens` 缓存失效（实现红线）

任何替换 `messages[i].content` 的代码 **MUST** 置 `messages[i]._tokens=None`（事实 3），并加回归测试（改 content 后 `count_tokens` 重算）。

### D11 — `trace`/`tool_calls_made` bounded 的消费者核实（前置）

**实现前 MUST 逐点核实**无消费者依赖 `trace` observation / `ToolCallMade.result` 的**全文**（预期结论：仅 `benchmarks/runner.py:661` 落盘，属「事后账本」）。若 benchmark 需要全文，方案 = **benchmark 显式开启 full trace**（`TraceRecorder.full_trace` 字段现保留但 inert，可复活为开关），而**非**默认常驻全文。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **改 `loop.py` 入库通道破坏 tool-call 链合法性** | 剪枝只替换 content 文本，不删消息、不改 `tool_call_id`；专门链合法性回归测试。 |
| **GC 不变量测试难写/易 flaky**（str 不支持 weakref） | 用容器对象包裹 + `gc` 可达性断言；测试隔离（关闭其它引用）。**grill 定测试形态。** |
| **模型当轮拿不到刚读的内容** | D3「已消费一轮」+ 新鲜保留；测试锁定「当轮结果未剪」。 |
| **图片绕过 token 硬顶** | D6 双维度（token + 字节）；图片按字节纳入。 |
| **`_tokens` 缓存使剪枝白剪** | D10 显式重置 + 回归测试。 |
| **trace/tool_calls_made bounded 影响 benchmark** | D11 前置核实；必要时 benchmark 显式开 full trace。 |
| **ref 文件泄漏 / 跨会话污染** | 复用 `WorkflowStore` 路径校验（段级拒绝 `..`）；artifacts/ 与 sessions/ 隔离避免 rmtree 误删；生命周期随会话。 |
| **子 agent ref 身份洞** | D4 按 agent 类型分（根 session_id / 子 run_id）。 |
| **`MemoryManager` 影响所有 agent** | 三处共用；改动须全量回归。 |
| **spill 开销**（落盘 + 回读） | 仅超阈值触发，小结果零开销；A5「不退化」。 |

## Testing Strategy

- **新增** `tests/agent/memory/test_tool_result_lifecycle.py`（或并入既有）：
  - **GC 不变量**（A0）：三处替换后全文不可达；
  - **`messages`**：陈旧被替换为预览 + ref；**当轮/未消费完结果不被替换**；
  - **`trace`/`tool_calls_made`**：超阈 bounded（保 `status`/`name`/`arguments`）；
  - **按 ref 无损回读**（逐字节）；**无 ref 不谎称**（`has_ref`）；
  - **tool-call 链在剪枝后合法**；
  - **`_tokens` 缓存失效**（改 content 后重算）；
  - **硬顶**：超硬限 + 未到 gap → 仍压缩；**单条阈穿透 recent window**（大结果即使新鲜也剪，但受「已消费一轮」保护）。
- **新增（图片 D6）**：`list[ContentBlock]` 结果的字节维度纳入。
- **新增（端到端）**：#278 复现器缩比版（单 agent 直读，RSS 峰值对照 E0）。
- **回归**：`agent-runtime` tool-call 链；`memory-context` 压缩；`context-engineering` Read/分页；全量 `uv run pytest -q`。

## Pre-Implementation Review

grill 阶段填写（`reviews/grill-design.md`）。**按流程纪律：grill 结论须先走独立对抗验证（`reviews/grill-adversarial.md`）再拍板。**

## Impact Analysis（design 视角的补充）

见 `proposal.md` 的 `## Impact Analysis`。补充：

1. **`loop.py` 是最敏感改动面**——它构造 `messages`，直接关系 `agent-runtime` 的「tool-call 消息链合法」；实现须先加链合法性回归。
2. **`MemoryManager` 三处共用**——根/子 agent 行为须一致，测试须覆盖两处。
3. **ref 存储泛化**——须确认 `.asterwynd/artifacts/` 的 workspace_policy 允许写（`workspace_policy.py` 的 allowlist；`WorkflowStore` 走自身原子写、不经 policy）。
4. **三持有者的 bounded 是三个独立改动点**（`messages` / `trace_recorder` / `result.py`），须分别测试，但共享 D1 的判定通道。
