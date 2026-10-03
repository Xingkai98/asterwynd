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
- **不治「非工具大内容」**（超大 user 粘贴 / 超大 `tool_calls[].arguments` 在 recent 内 / 后台注入输出）——**另立 [#283](https://github.com/Xingkai98/asterwynd/issues/283)**，见 D7 残余边界。

## Decisions

### D0 — 验收主指标是 **GC 不变量**，不是 RSS（测试形态已由对抗验证定）

本 change 的**机械可验**判据是：spill/bounded 后，原工具结果全文**不再被任何池子强引用**。

**为什么不是 RSS**：RSS 受解释器内存池、并发邻居、采样时机影响（#278 实测本机是共享 cgroup）；把 RSS 当唯一判据会让「机制做对了但 RSS 降幅不显著」误判为失败。**GC 不变量是机制正确性的直接证明**，RSS（E0）作对照观测。

**测试形态（经对抗验证实测敲定）**：
- **主手段 = `str` 子类弱引用**：`weakref.ref(str)` 抛 `TypeError`，但 **`class _WeakStr(str)` 的子类可弱引用**（实测；且 `bytes` 子类仍不可，选型正确）。因它是 `str`，生产代码的所有 `isinstance(x, str)`/`startswith`/`extract_text` 路径**行为等价**，无需 mock 管线。测试让 fake 工具返回唯一的大 `_WeakStr`，持 `weakref.ref`。
- **硬约束（对抗验证实测，务必遵守）**：`dataclasses.asdict` 与 `copy.deepcopy` 对 **`str` 子类实例会复制**（返回新对象），对**普通 `str` 返回同一对象**。而 `run.trace = trace.to_dict()`（`subagent/manager.py:1349` 等）走 `asdict` ⇒ 测试用 `_WeakStr` 时，**`run.trace` 持的是副本、不是原对象**。⇒ **只断言「弱引用回 None」的测试会「假通过」**（原对象被 messages+tcm 释放后弱引用回 None，但 trace 副本可能仍是全文）。**测试 MUST 显式断言内存态 `trace.steps[*].data["observation"]`（`record_tool_result` 直接存对象、`is` 同对象）与 `tool_calls_made[*].result` 均已 bounded**，不能只靠弱引用。
- **兜底**：`gc.get_referrers` 断言无三持有容器——仅对**大且唯一（非 interned）**串可靠，须与 `_WeakStr` 合用。

**生产事实校正**：生产用普通 `str`，`asdict` 返回同对象 ⇒ 生产 trace 与 messages/tcm 确实共享同一对象（事实 1 成立）；`_WeakStr` 造成的引用拓扑分歧**只存在于测试**，故测试须按上条断言内存字段。

### D1 — 工具结果有界化**两段式**（判定纯函数 + loop 侧注入 store/scope）

**不塞一处**（对抗验证修正：`MemoryManager` 是构造期建的，拿不到 workspace_root，scope id（子 agent 的 `run_id`）只在 `run()` 期才知道）：

1. **bounded 逻辑** = 纯函数（新模块 `agent/memory/tool_result_policy.py`，如 `bound_result(result, *, token_budget, byte_budget) -> (preview, released_bytes)`）：无状态、可单测，由 `loop.py` 在三处写入点调用。
2. **`messages` 剪枝** = `MemoryManager.prune_tool_results(...)`：只负责「判哪些消息该剪（D3 判据）+ `_tokens=None` 重置」，**不碰 I/O**。
3. **ref 落盘与 scope** = 由 `loop.py` 在 `run()` 期构造并注入（loop 持 `self._artifact_store`，scope = 根 `session_id` / 子 `run_id`）；`prune_tool_results` 通过注入的回调入 `save(ref, text)`。

**不改变写入顺序/结构**：仍 `messages.append(tool_result_message(id, content))`、`tool_calls_made.append(ToolCallMade(...))`、`record_tool_result(...)`，只是 `content` 由通道决定（全文 / 预览）。

### D2 — 持有者**分离**处理：`messages` 需 ref，`trace`/`tool_calls_made` 只需 bounded

**决定性区别**：
- `messages` 的全文**有消费者**（模型当轮/按需推理）→ 需 **spill + ref**（可无损回读）。
- `trace`/`tool_calls_made` 的全文**无模型面消费者** → 只需 **bounded**（预览 + 诚实标记），**不落 ref**。

**为什么不给 trace 也落 ref**：没有消费者按 ref 回读（web/CLI/benchmark 全读截断/前缀），落 ref 只是徒增磁盘与复杂度；benchmark 若要事后全文，那属**另一需求**（可让 benchmark 显式开启 full trace，见 D8）。

**全文消费者核对表（对抗验证补齐——原 design 只列了 trace/tcm，不完整）**：

| 消费者 | 读什么 | 结论 |
|---|---|---|
| `web/session.py:898` | `text[:text_limit]`（截断） | 非全文 |
| `benchmarks/agent_runner.py:459` | `.startswith("[Error")` | 非全文 |
| `main.py:656` `_print_tool_call_summaries` | collapsed → preview | 非全文 |
| `subagent/snapshot.py:79` / `scheduler.py:2315` | 计数 / `status` | 非全文 |
| `benchmarks/runner.py:661` | 全文落 `trace.json` | **全文**（事后账本）→ D8 开关 |
| **`web/session.py:1779` ← `loop.py:1029-1037` `on_event("tool_result")`** | **`"result": <全文>` → WebSocket → `web/static/chat.js:932/963` Expand 按钮** | **全文（前端 Expand 数据源）** → **D12（行为回归风险点）** |

**持有者拓扑校正（对抗验证）**：**根 CLI / Web run 根本不创建/传 `trace_recorder`**（`main.py`、`web/session.py` 都不传；`trace_recorder` 只由 `benchmarks/agent_runner.py:424` 与子 agent `subagent/manager.py:1178` 传入）。⇒ **「三持有者」只存在于 benchmark 与子 agent run**；根 CLI/Web run 只有**两持有者**（`messages` + `tool_calls_made`）。这不推翻本 change（两处也要治），但「单做任一处=白做」的论证在根 CLI/Web 场景是「单做 messages 白做（tcm 还持）」。design/spec 措辞**不得**断言所有 run 都有三持有者。

**已核实**：`ToolCallMade` 的 bounded 不影响 benchmark 判定——`agent_runner.py:459` 只 `startswith("[Error"/"[Permission denied")`，bounded 预览仍保留前缀（安全）。

### D3 — `messages` spill 时机与判据：**「已消费一轮」∩（滑出窗口 ∪ 单条超阈）**

一个工具结果被剪的条件（**同时**满足）：

1. **已被模型消费过至少一轮**（对抗验证关键修正）：剪枝点在结果产生轮的**末尾**（`loop.py:1047` → `:1056`），模型要到**下一轮 `_call_llm`** 才消费。故**产生当轮不剪**（否则「巨型新鲜结果立即剪」会伤害任务完成、撞 A5）——**记录每个结果入库的 iteration，下一轮起才允许剪**。
2. **且**满足其一：
   - **滑出近期窗口**（`recent_window`，默认 10 条——**注意是消息条数非轮数**，一条 assistant+tool 对占 2 条，故 window=10 实际覆盖约 5 轮；措辞在 spec/代码须钉死「条」）；
   - **单条超阈**（token 或**字节**，见 D6）。

**「已消费一轮」的实现（用户 2026-10-03 拍板 = `-1`）**：
- **`added_iteration <= current_iteration - 1`**：匹配「至少一次 `_call_llm` 已发出」——结果在 iteration k 入库、同轮末尾 `_call_llm` 已发一次、k+1 轮再发一次，故 k+1 末尾即可剪。**这是本 change 采用的常量**（大结果少驻留一轮、贴合降峰目标）。
- ~~`-2`（被消费两遍才剪）~~：更保守但与降峰目标冲突，**不采用**。
- **两 append 点（`:854` 错误路径 + `:1047` 正常路径）都必须记 `added_iteration`**——只在正常路径记会让错误路径结果无标记（被立即剪或永不剪）。并行 tool call 同轮同 `added_iteration`，天然覆盖。

**为什么窗口 ∪ 单条，且单条要能独立触发**：只靠窗口 → 单条 200KB 在窗口内每轮全量重发，峰值不降；只靠单条 → 正常结果也剪、伤任务。取或，且**单条判据不受窗口保护**（大结果即使新鲜也要剪）——**但受「已消费一轮」保护**（修正后不会在模型用之前抽走）。

**单条阈取值（已定）**：`token > max(TOOL_RESULT_SPILL_MIN_TOKENS, max_tokens × 0.25)` **或** `bytes > 128KB`（与 B 的 Read 默认字节界同值），双判据**取先到**；写成常量（可配置）。

### D4 — agent 通用 ref 存储：复用 `WorkflowStore` 实现，**泛化作用域**；身份**按 agent 类型分**

新增 agent 通用 ref 落点，**复用 `WorkflowStore` 的 ref 格式族 / 原子写 / 分页读**，置于 `.asterwynd/artifacts/`（**在 `sessions/<id>/` 之外**，避免 `SessionStore.remove()` 的 `rmtree` 误删）。

**身份寻址（对抗验证修正）**：
- **根 agent 用 `session_id`**（resume 时 `session_id` 不变、`run_id` 新起——按 `run_id` 会悬空）；
- **子 agent 用 `run_id`**（对抗验证：`subagent_id` 是 `uuid4().hex[:8]` 进程内标识、不落盘；durable 身份是 `run_id`，checkpoint 落盘 `session_id=run.run_id`，`resume_subagent(subagent_id, run_id)` 靠 `run_id` 取）。

**生命周期**：会话/子 agent 归档或删除时随其目录清理；**run 结束不删**（保 resume 可回读）。**当前 `_sessions` 不清理**（里程碑 A），故本 change 的清理路径须**显式实现**（不依赖里程碑 A）。

**已定**：ref 前缀 `artifact://agent/<scope_id>/<key>`（与既有 `artifact://workflow/<workflow_id>/<key>` 并列）；**新增共享 `ArtifactRef.parse(ref) -> (kind, scope_id, key)`**，`WorkflowStore.parse_ref` 委托之；**在工具层按前缀路由**（`artifact://workflow/`→`manager.workflow_store(wid)`，`artifact://agent/`→agent store），不改 workflow 语义。清理触发点 = `SessionStore.remove(session_id)` 内**显式追加** rm `.asterwynd/artifacts/<session_id>`；子 agent 同理由**显式实现**（当前无此路径，否则退化为永不清理）。

### D5 — 回读工具：**泛化 `ReadWorkflowResult`**，不新增

`ReadWorkflowResult` 按 ref 前缀分派（`artifact://workflow/...` 与 agent ref 都读），**工具名/schema 保持不变**（兼容）。**不新增工具**（#248：工具越多越选错）。

**必须落实**（对抗验证点名）：
- **注册路径**：该工具现由 `loop.py:_ensure_subagent_tools_registered` 构造、**依赖 `subagent_manager`**；须确认**根 agent 与深度到限的子 agent**都注册可用（`expose_subagent_tools=False` 的入口会整套不注册）。
- **改工具 description**：现为 workflow 专用文案，泛化后须改写，否则模型仍以为只读 workflow。

**已定**：**泛化（不新增工具）**——工具按 ref 前缀分派；构造依赖改为**一个解析器**（由 `workspace_root` + ref 路由组成），不再只依赖 `manager.workflow_store`。**注册路径已核实**：根 agent（`main.py:327` `expose_subagent_tools=True`）与深度到限子 agent（`manager.py:1321`，`SPAWN_TOOL_NAMES` 不含 `ReadWorkflowResult`）**都可用**；`expose_subagent_tools=False` 的入口（仅单测）整套不注册 ⇒ 由 D8 的「spill 与回读成对启用」兜底。

### D6 — 度量维度：**token 与字节双维度**，图片纳入字节

**对抗验证核心修正**：图片 `ImageBlock` 在 token 账本上是**固定 1000/张**（`message.py:89-99`），但正文 base64 可达 **MB 级**（`MAX_IMAGE_SIZE=20MB`）——**token 硬顶对图片失效**。

- 单条阈（D3）与硬顶（D7）SHALL 同时约束 **token 估算** 与 **常驻字节**；
- 图片结果（`list[ContentBlock]`）SHALL 至少按**字节**（`len(url)`）纳入判定——**SHALL NOT 因 token 计 1000 就放行 MB 级 base64 常驻**；

**图片持有者校正（对抗验证）**：`trace` 经 `_sanitize_observation`（`trace_recorder.py:131-143`）把图片转成 `[image: path]` 文本 ⇒ **trace 不是图片持有者**；图片的持有者是 `messages` + `tool_calls_made`（二者同对象，实测 `is` 为 True）。

**图片 spill 策略（对抗验证推荐，四管）**：
1. 字节维度对 `ImageBlock` 计 `len(url)`，纳入单条阈与硬顶；
2. 图片「预览」复用 trace 既有形态 `[image: <file_path>]`——消费一轮后把 `ImageBlock` 换成该 TextBlock，**字节立即释放，模型必要时可 `Read` 该路径取回像素**（`file_path` 在）；
3. `file_path is None`（粘贴图）时，把 base64 落 ref store、标 `[image: <ref>]`（字节有界、诚实标注）；
4. **`MAX_IMAGE_SIZE`（`read.py:18`，20MB/张）与「常驻有界」自相矛盾，须收敛到与常驻预算相容的值**（本 change 至少记此矛盾为待办/或直接收紧）。

### D6b — 覆盖缺口：`arguments` 与 trace 的「非 result」大内容（对抗验证新增）

「工具结果」不止 `result`。以下三处**未被原 design 覆盖**，均持全文：
- **`tool_calls_made[*].arguments`**（`result.py:17-20`）与 **`messages` 里 assistant 的 `tool_calls[].arguments`**（`message.py:172-176` + `_recent_with_tool_chains` 原样保留 assistant）——一次 `Write` 带 300KB 正文时，`result` 只有状态串，**300KB 在 `arguments` 里**；
- **trace 的 `tool_call` step**（`loop.py:993` → `trace_recorder.py:100-101` 原样存完整 parsed arguments；`redact_value` 只脱敏密钥、不截断长度）；
- **trace 的 `record_edit(summary=result)`**（`loop.py:1008`）与 **`record_iteration(assistant_preview=response.content)`**（`loop.py:756`，`assistant_preview` 名义是 preview、实为 `response.content` 全文）。

⇒ **bounded 判据 SHALL 覆盖 `result` 与 `arguments` 两者**；`messages` 侧 assistant `arguments` 至少**计入字节预算**（否则 `Write` 型大参数绕过白名单）。

**已定**：采用上述**四管策略**（A 的「图片不参与 spill」已被对抗验证否决——那会让硬顶对图片密集 run 失效）。**`MAX_IMAGE_SIZE`（20MB/张）与「常驻有界」的矛盾**：本 change**先记为单位债务**（`docs/known-debt.md` 或 #283 一并评估），不在本 change 收紧默认值（避免扩大改动面）。

### D7 — 压缩硬顶：超硬限**无视 gap 强制压**

`compaction_gap` 仅防抖，SHALL NOT 让上下文无界。`compact_if_needed`：超硬上限（独立常量/可配置）时**无视 gap** 强制 `compact`。

**次序**：**先剪枝（D3）→ 再判硬顶 → 超了才强压**（剪完可能已达标，无需压）。

**与 D3 的交互（对抗验证的死结，定级=高）**：`compact` 的 `_recent_with_tool_chains` **原样保留 recent window 内的大内容**（事实 6）——若大内容卡在 recent 内，硬顶会**每轮空转**（`compact` 只压 `middle`，`middle` 空则 `msgs[:] = system + recent`，尺寸不变、返回 `True`，下轮再压）。**D3 的单条阈解的是 `result`（工具结果）**；但**非工具大内容**（大 user 粘贴 / 大 assistant `arguments` 在 recent 内）**D3 剪不到**（对抗验证 Q-new5）——这是**残余边界**：

- **最小要求**：design 明写此残余边界，**不得**宣称「硬顶 = 常驻有界」在**非工具**主导的 run 上成立；
- **可选加强（用户 2026-10-03 拍板：不在本 change，另立 [#283](https://github.com/Xingkai98/asterwynd/issues/283)）**：超硬顶**且剪无可剪**时允许 compact **收缩/驱逐 recent window 本身**（或对 recent 内超大非工具消息做有损截断）。理由：触及 compaction 的 recent-keep 不变量、风险面独立。

**同类残余边界（对抗验证）**：后台任务完成输出以 `role=user` 注入（`loop.py:737`，`MAX_OUTPUT_BYTES=64KB`，`background.py:13`）——无 `tool_call_id`，D3 不剪，多后台任务会累积多条 ~64KB user 消息至下次 compact。

**决策（用户 2026-10-03）**：以上**非工具大内容**的残余边界**本 change 只如实记录、不治**，**另立 [#283](https://github.com/Xingkai98/asterwynd/issues/283) 跟进**（候选方向：超硬顶且剪无可剪时收缩/驱逐 recent window，或对 recent 内超大非工具消息做有损截断）。理由：改动触及 compaction 的「recent window 原样保留」不变量（`memory-context` spec 的「compact 必须保留系统消息和近期上下文」），可能丢模型仍需要的数据，风险面独立于 #282。**本 change 不得宣称「一切内容有界」，只保证「工具结果主导」的上下文有界。**

### D8 — 诚实标记：ref 不存在就不谎称可回读

沿用 `_bounded_summary`（`agent/subagent/manager.py:53-80`）的 `has_ref` 纪律：只有**确实落盘成功**才写「full result in result_ref」；否则写「已截断、全文不可回读」（`[truncated]`）。`trace`/`tool_calls_made` 的 bounded 无 ref，标记 SHALL 如实为「已截断」（不指向 ref）。

**与 spill 成对启用（对抗验证 Q-new2，定级=中）**：**溢出前门控「回读工具是否已注册」**（`tool_registry.get_tool("ReadWorkflowResult")`）——不可回读时**不 spill**（或 spill 但如实标 `[truncated]`、不指向 ref），否则违反 spec「SHALL NOT 声称存在可读的 ref」。**注意**：生产 4 个入口（CLI/Web/子 agent/benchmark）**都**传 `expose_subagent_tools=True`，默认 `False` 只在单测 ⇒ 生产可达性低，防御性设计即可。

### D9 — spill 可观测（不静默），沿用 #275/#279 纪律

spill/bounded 的**发生次数与字节数** SHALL 可观测，经既有 trace/event 通道暴露。业界对照：Anthropic context editing 响应带 `cleared_tool_uses`/`cleared_input_tokens`。**落地形态（对抗验证推荐）**：新增 trace step 类型 `record("tool_result_spill", spilled_messages=N, bounded_ledger=M, released_bytes=B)`（对齐既有 `record_compaction`，`trace_recorder.py:164-180`），并在 `loop.py` 同步发 `on_event("tool_result_spill", ...)`（对齐 `memory_compaction` 的 `:1058-1066`）；**不改 `RunResult` 协议**；计数区分「messages 无损 spill（有 ref）」与「账本有损 bounded（无 ref）」。

### D10 — `_tokens` 缓存失效（实现红线）

任何替换 `messages[i].content` 的代码 **MUST** 置 `messages[i]._tokens=None`（事实 3），并加回归测试（改 content 后 `count_tokens` 重算）。

### D11 — `trace`/`tool_calls_made` bounded 的消费者核实（前置）

**实现前 MUST 逐点核实**无消费者依赖 `trace` observation / `ToolCallMade.result` 的**全文**（结论见 D2 核对表：仅 `benchmarks/runner.py:661` 落盘与 **Web on_event（D12）**）。若 benchmark 需要全文，方案 = **benchmark 显式开启 full trace**（`TraceRecorder.full_trace` 字段现保留但 inert，可复活为开关），而**非**默认常驻全文。

### D12 — Web Expand 改为**按需回读**（形态 (c)，用户 2026-10-03 拍板）

`loop.py:1029-1037` 的 `on_event("tool_result", {"result": <全文>})` 经 `web/session.py:1779` 入队 → WebSocket → 前端 **`web/static/chat.js:932` `const fullResult = data.result`**，`:963-970` 的 **Expand 按钮**就靠这份全文。

**决策：默认只发预览，Expand 时按需向服务器取全文**（(c) 懒加载）。

**寻址键 = `(session_id, tool_call_id)`，不按 ref**（关键实现约束）：
- 事件发在**结果产生的那一刻**（`loop.py:1029`），而 ref 要到**轮末剪枝**才写盘 ⇒ **事件里拿不到 ref**；且 `tool_result` 事件 payload **现在不带 `tool_call_id`**。
- 故：事件 payload **增加 `tool_call_id`**（小、稳定，非大内容）；新增只读端点 `GET /api/sessions/{session_id}/tool-result/{tool_call_id}`：在 `session.messages`（`web/session.py:1272`）找 `role=tool` 且 `tool_call_id` 匹配的消息 → **若 content 是全文直接返回；若已 spill（预览 + 内嵌 ref 标记，Q-new4）则解析 ref、从 artifacts store 读全文返回**；消息已被 compaction 驱逐/找不到 → 返回 missing（前端显示「全文不可用」）。
- **这解耦了 ref 时机**：端点用 `tool_call_id` 定位消息，再决定读 content 还是读 ref。

**前端（`web/static/chat.js`）**：Expand 时若未加载则 `fetch` 一次并缓存到该条；**Collapse 时清除缓存**——释放浏览器内存（修既有闭包 `const` 永不释放的问题，`:932`）。

**服务端瞬时读**：端点读盘 → 发回 → 丢引用，**不进 `messages`**，不重新引入常驻。

**spec 影响**：`web-ui` 的 Requirement「Chat 视图按 display metadata 展示工具结果」（`openspec/specs/web-ui/spec.md:117`，"长结果 SHALL 默认展示 preview 并允许展开全文"）需 **MODIFY**——展开改为「按需从服务端取回全文」。

**不受影响**：CLI 的 `on_event`（`main.py:613-624`）不处理 `tool_result`，打印走 `result.tool_calls_made`（另一条路）；子 agent 无 `on_event`（Web 里的工具结果都是根级）。

**新攻击面**：多一个 Web 端点——SHALL 只读、SHALL 复用 workspace/session 校验、只在 session 存在时返回。附带（非本 change）：`web/session.py:1771` 的 `queue` 是**无界** `asyncio.Queue()`，大结果消费前瞬态驻留（低危）。

## Risks / Trade-offs

| 风险 | 严重度 | 缓解 |
|---|---|---|
| **大 `tool arguments` 无界**（`Write`/`Edit` 正文住在 `tool_calls[].arguments` + `ToolCallMade.arguments` + trace `tool_call` step，剪 `result` 不触及） | **高** | D6b：bounded 覆盖 `arguments`；messages 侧至少计入字节预算 |
| **Web Expand 按需回读的新端点**（新攻击面 / 找不到全文时的降级） | **中** | D12：只读端点 + session/workspace 校验 + 找不到返回 missing + 回归测试 |
| **硬顶对非工具大内容空转**（大 user 粘贴 / 大 assistant 参数 / 后台注入在 recent 内） | **高** | D7：明写残余边界，或允许收缩 recent |
| **改 `loop.py` 入库通道破坏 tool-call 链合法性** | 高 | 剪枝只替换 content 文本，不删消息、不改 `tool_call_id`；专门链合法性回归测试 |
| **GC 不变量测试假通过**（`asdict` 对 str 子类复制） | **高** | D0：断言**内存字段**，不只靠弱引用 |
| **图片绕过 token 硬顶** | 高 | D6 双维度（token + 字节）+ 四管策略 |
| **`_tokens` 缓存使剪枝白剪 / 反复误触发压缩** | 高 | D10 显式重置 + 回归测试 |
| **无回读工具时溢出 → 悬空 ref** | 中 | D8：spill 与回读工具注册成对启用 |
| **预览剪掉 `[ReadProgress]` 尾注 → 破坏分页进度保留** | **中-高** | 预览 = 头 + **保留尾部注记**（`_READ_PROGRESS_RE`，`manager.py:23-25`） |
| **spec/design 口径漂移**（单条穿透窗口：delta 只写窗口） | 中 | 向 delta 增补「窗口内超大单条消费一轮后仍被替换」scenario |
| **ref 存法自破「Message 结构不变」** | 中 | 内容内嵌可解析标记，不加 `Message` 字段 |
| **ref 文件泄漏 / 跨会话污染** | 中 | 复用 `WorkflowStore` 路径校验；artifacts/ 与 sessions/ 隔离；**清理须显式实现**（`_sessions` 永不清理） |
| **子 agent ref 身份洞** | 中 | D4 按 agent 类型分（根 session_id / 子 run_id） |
| **`MemoryManager` 三处共用** | 中 | 根/子一致回归（`main.py:297`、`subagent/manager.py:1318`、`loop.py:156` 默认） |
| **trace bounded 影响 benchmark 全文分析** | 中 | benchmark 显式 `full_trace=True`（已验证 inert 可复活） |
| **字节维度每轮重算 `len(encode)` 的 O(n) 开销** | 低-中 | 字节数在入库时与 `_tokens` 一同缓存 |
| **spill 开销**（落盘 + 回读） | 低-中 | 仅超阈值触发，小结果零开销；A5「不退化」 |
| **`benchmarks/agent_runner.py:459` 对 `list` 结果调 `.startswith` 会崩**（既存缺陷，非本 change 引入） | 低 | D11 前置核实记录；bounded 后可顺带修（先 `extract_text`） |

## Testing Strategy

- **新增** `tests/agent/memory/test_tool_result_lifecycle.py`（或并入既有）：
  - **GC 不变量**（A0）：三处替换后全文不可达；
  - **`messages`**：陈旧被替换为预览 + ref；**当轮/未消费完结果不被替换**；
  - **`trace`/`tool_calls_made`**：超阈 bounded（保 `status`/`name`/`arguments`）；
  - **按 ref 无损回读**（逐字节）；**无 ref 不谎称**（`has_ref`）；
  - **tool-call 链在剪枝后合法**；
  - **`_tokens` 缓存失效**（改 content 后重算）；
  - **硬顶**：超硬限 + 未到 gap → 仍压缩；**单条阈穿透 recent window**（大结果即使新鲜也剪，但受「已消费一轮」保护）。
  - **新增（图片 D6）**：`list[ContentBlock]` 结果的字节维度纳入；图片消费一轮后转 `[image: path]`。
  - **新增（D6b）**：`arguments` bounded（含 trace `tool_call` step）；`messages` assistant `arguments` 计入字节预算。
  - **新增（D8）**：**预览保尾**——spill 后预览仍能匹配 `_READ_PROGRESS_RE`（跨模块契约）。
  - **新增（D12）**：Web `on_event("tool_result")` 的 payload 决策（原文/bounded）有对应断言（防 Expand 静默回归）。
  - **新增（Q-new5/后台）**：残余边界测试——大 user 粘贴 / 后台注入不被 D3 剪（锁定「已知不覆盖」，避免误以为已覆盖）。
- **新增（端到端）**：#278 复现器缩比版（单 agent 直读，RSS 峰值对照 E0）。
- **回归**：`agent-runtime` tool-call 链；`memory-context` 压缩；`context-engineering` Read/分页；全量 `uv run pytest -q`。

## Pre-Implementation Review

grill 阶段填写（`reviews/grill-design.md`）。**grill 结论已走独立对抗验证（`reviews/grill-adversarial.md`），其修正已折进本 design（D0/D1/D2/D3/D6/D6b/D7/D8/D9/D12）。**

## Impact Analysis（design 视角的补充）

见 `proposal.md` 的 `## Impact Analysis`。补充：

1. **`loop.py` 是最敏感改动面**——它构造 `messages`，直接关系 `agent-runtime` 的「tool-call 消息链合法」；实现须先加链合法性回归。
2. **`MemoryManager` 三处共用**——根/子 agent 行为须一致，测试须覆盖两处。**`MemoryManager` 构造期无 workspace_root** ⇒ D1 的 store/scope 由 loop 在 run 期注入。
3. **ref 存储泛化**——须确认 `.asterwynd/artifacts/` 的 workspace_policy 允许写（`workspace_policy.py` 的 allowlist；`WorkflowStore` 走自身原子写、不经 policy）。
4. **各持有者的 bounded 是独立改动点**（`messages` / `trace_recorder` / `result.py` / `on_event`），须分别测试，但共享 D1 的判定通道。**持有者拓扑因 run 类型而异**（根 CLI/Web = 2 持有者，benchmark/子 agent = 3）。

