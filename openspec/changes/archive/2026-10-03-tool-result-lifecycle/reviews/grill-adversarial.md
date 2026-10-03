# 对抗验证：tool-result-lifecycle grill 结论证伪报告

## Reviewer

- run id: 独立零记忆对抗验证 subagent（本 worktree 内直接执行；自述 id `adversarial-tool-result-lifecycle`）
- 时间: 2026-10-03
- 任务: **证伪** `reviews/grill-design.md` 的 5 条新发现（Q-new1..Q-new5）+ 4 个核心推荐答案（Q1/Q4/Q3/Q7）；不复述、不背书。
- 方法: 逐条读被改代码 + 运行时实测（`/tmp/` 脚本，CPython 3.12.13 `uv run python`）+ 全仓 sweep。凡标「实测」处均为本机真实运行结果。
- **主 session 复核**: 本报告每条「实测」结论已由主 session 独立复跑核实（见文末「主 session 复核记录」）。

> 结论速览：**5 条新发现里 4 条 survives、1 条 needs-revision（Q-new2 生产触发面被夸大）**；**Q1 核心选型对但「完全等价」是过度断言（实测 `asdict` 对 str 子类会复制）**；**Q4 有 off-by-one（`-2` 与理由差一轮）**；**新发现 grill 漏了 6 条面**，其中 **Web `on_event` 全文外发是唯一的「行为回归风险点」**。

---

## 对 grill「新发现」的裁决

### Q-new1（预览必须保尾以保留分页进度）→ **survives**

`read.py:46-55` 的 `_progress_note`/`_truncated_note` 把 `[ReadProgress ...]` 追加在正文尾部；`manager.py:460-485` 的 `_extract_read_progress` 扫 tool 消息**内存正文**（`:480` `extract_text(m.content)`），不读 ref。head-only 预览会丢注记 ⇒ 续读位点丢失 ⇒ 违反 base spec「Pagination Progress Preservation」。**未找到证伪点。**

**措辞修正（更严重）**：grill 说「若 compaction 在模型回读前触发」才发作——实际 `_decorate_for_summary`（`manager.py:487-512`）**每次** compact 都从最近消息抽进度；只要被 spill 的条目是某文件进度的最后载体（last-wins，`:484`），进度即永久丢失。

### Q-new2（无回读工具时 ref 悬空）→ **needs-revision（机制真、生产触发面被夸大）**

机制正确：`expose_subagent_tools=False` 时 `_ensure_subagent_tools_registered` 整个不跑（`loop.py:204-205` 门控）。**但「哪个真实入口用默认 loop」是事实错误**——全仓**生产**构造点核验：

| 构造点 | `expose_subagent_tools` |
|---|---|
| `main.py:327`（CLI） | `True` |
| `web/session.py:1602`（Web） | `True` |
| `subagent/manager.py:1321`（子 agent） | `True` |
| `benchmarks/agent_runner.py:389`（benchmark） | `True` |

默认 `False` 只出现在**单测**。⇒ **生产无可达触发点**，定级应为**中**（非高）。「spill 与回读成对启用」仍是好防御，但删去「非 CLI 入口」这个错误场景。

### Q-new3（spec delta 与 design D3 口径不一致）→ **survives**

`specs/context-engineering/spec.md:21-26` 的 scenario 写「已消费过**且滑出近期窗口**」（窗口单向）；design D3（`design.md:67-78`）是「窗口 **∪** 单条超阈」且明说单条不受窗口保护。delta 7 条 scenario 里**无任何**单条穿透窗口的 case。**未找到证伪点。**

### Q-new4（ref 存法：不改 `Message` 结构）→ **survives**

`Message.to_dict`/`from_dict`（`message.py:162-205`）完整往返 `content`；「内嵌可解析标记」随 `messages.json`（`session.py:217`）自然持久化。Goal 明写「不改协议：`Message` 结构…不变」（`design.md:29`），加字段确实自破。**未找到证伪点。**

### Q-new5（硬顶对非工具大内容死结）→ **survives，且定级应为「高」**

`compact` 的 `_recent_with_tool_chains`（`manager.py:375-393`）无条件保留 recent，D3 只剪工具结果。大内容为**非工具项**（大 user 粘贴 / 大 assistant `arguments`）且落在 recent 内时：D7 硬顶每轮强压 → compact 只压 `middle`（`:196-205`），`middle` 空则走 `:207-221` 分支 `msgs[:] = system + recent`（**尺寸不变**、返回 `True`）→ 下轮仍超硬顶 → **每轮空转**。这与 grill 自评「高」的 arguments 缺口是**同一机制**，却给了「中」——**定级自相矛盾，统一为高**。

---

## 对核心推荐答案的裁决

### Q1（GC 测试用 `str` 子类弱引用）→ 核心 **survives**，但「完全等价」**needs-revision**

实测（CPython 3.12.13）：

- `weakref.ref("hello")` → `TypeError: cannot create weak reference to 'str' object` ✓
- `class _WeakStr(str)` 可弱引用，`w() is s` True ✓；对照 `bytes` 子类**仍不可**（选型正确）✓
- 干净作用域 + `gc.collect()` 后 `w() is None` ✓

**grill 漏掉的坑（实测坐实）**：`dataclasses.asdict` 与 `copy.deepcopy` 对 **str 子类实例会复制**，对**普通 str 返回同一对象**：

```
asdict PLAIN str is same object: True
asdict SUBCLASS str is same object: False  (type: _WeakStr)
deepcopy PLAIN str is same object: True
deepcopy SUBCLASS str is same object: False
```

后果：
1. **`run.trace = trace.to_dict()`（`manager.py:1349` 等）持的是子类的 COPY**，不是原对象 ⇒ **只断言弱引用回 None 的测试会「假通过」**——即便 trace 的序列化副本仍是全文，原对象被 messages+tcm 释放后弱引用也回 None。测试**必须显式断言内存态 `trace.steps[*].data["observation"]`（`record_tool_result` 直接存对象，实测 `is` 同对象）已 bounded**，不能只靠弱引用。
2. 生产用**普通 str**（`asdict` 返回同对象，grill 事实 1 对），但测试用子类时这个共享在序列化路径上**不复存在**——`_WeakStr` 使测试与生产的引用拓扑分歧，grill 的「完全等价」是过度断言。

⇒ `_WeakStr` 仍是可用主手段（解决 `weakref.ref(str)` 不可用），但测试须断言**内存字段**、对 `run.trace`（序列化件）单独断言。

### Q4（「已消费一轮」=`added_iteration <= current_iteration - 2`）→ **needs-revision（off-by-one）**

`-2` 与它自己的理由**差一轮**。执行序：结果在 iteration k 的 `:1047`/`:854` 入库（`self._iteration = k`，`:723`）；剪枝在**同轮末尾** `:1056`（此时 `_call_llm` 已发过一次）；第 k+1 轮 `_call_llm`（`:743`）又发一次 ⇒ 到 k+1 末尾**已消费一遍**。按 grill 自己的口径（「k+1 末尾起可剪」+「至少一次 `_call_llm` 发出」），正确式 = `added_iteration <= current_iteration - 1`。代码 `-2` 会到 k+2 才剪（**被消费两遍**）——不是正确性 bug（更保守），但**与 D3 降峰目标冲突**（大结果多常驻一轮）。**须二者取一：改 `-1`（匹配理由）或改理由为「至少两次」。**

**覆盖性**：grill 只举正常路径。**错误路径 `:854`** 同样是 append，若「记 `added_iteration`」只在 `:1047` 实现，错误路径结果将无标记。⇒ 推荐答案**必须显式点名「`:854` 与 `:1047` 两个 append 点都要记」**。并行 tool call（同轮同 `added_iteration`）天然覆盖 ✓。

### Q3/Q7（trace 是否持图片/大内容）→ **部分 survives**

- 「trace 不持图片 base64」**成立**：`_sanitize_observation`（`trace_recorder.py:131-143`）对 `list` 转 `[image: path]`。
- 「图片持有者只有 messages + tool_calls_made，二者同对象」**成立**（实测 `is` True）。
- **但 Q3 的 arguments 缺口被 grill 自己低估**：grill 只列两处（assistant `tool_calls[].arguments` + `ToolCallMade.arguments`），**漏了第三处——trace 的 `tool_call` step**（`loop.py:993` → `trace_recorder.py:100-101` 原样存完整 parsed arguments）。`redact_value` 只脱敏密钥、不截断长度。⇒ bounded 须把 trace 步也纳入。

### Q7（图片策略）→ **survives**

`count_tokens_for_content` 对 `ImageBlock` 固定 1000/张（`message.py:97-98`），`MAX_IMAGE_SIZE=20MB`（`read.py:18`）。token 硬顶对图片失效成立。`_read_image`（`read.py:242-248`）返回 `[TextBlock, ImageBlock]` 且 `file_path` 存在 ⇒「消费一轮后换成 `[image: path]`、必要时按路径回读」可行。未找到证伪点。

---

## grill 漏掉的（全仓 sweep 新发现）

1. **Web `on_event("tool_result")` 把全文推给前端，且是「Expand 看全文」的数据源**（最严重，本 change 唯一的行为回归风险点）。`loop.py:1029-1037` 的 event payload `"result": extract_text(result) ...` 是**全文**；经 `web/session.py:1779-1780` 入队、送 WebSocket；前端 **`web/static/chat.js:932` `const fullResult = data.result || ''`**，`:963-970` 的 Expand 按钮 `body.textContent = expanded ? fullResult : display.preview`。后果：
   - 这是 `result` 的一个**全文消费者**，推翻「工具结果全文没有消费者」的**总框定**（D2 对 **trace/tcm** 无消费者的具体结论仍对）。
   - 若 D1 把 `result` 换成 bounded 后再发 on_event，**Web UI 的 Expand-to-full 会静默退化成只显示预览**——一个未测试的可见行为回归。**必须在 design 显式决定 on_event 用原文还是 bounded。**
   - 附带：`web/session.py:1771` 的 `queue` 是**无界** `asyncio.Queue()`，大结果消费前瞬态驻留（非长期，低危）。
2. **trace 的 `tool_call` step 持 arguments 全文**（`loop.py:993`）；**`record_edit(summary=result)`**（`:1008`）与 **`record_iteration(assistant_preview=response.content)`**（`:756-758`）在「preview」名下存**全文**（`assistant_preview` 实为 `response.content` 全文，命名与语义不符）。
3. **根 CLI / Web run 根本没有 trace**（`main.py` 与 `web/session.py` 都不创建、不传 `trace_recorder`；`trace_recorder` 只由 `benchmarks/agent_runner.py:424` 与子 agent `manager.py:1178` 传入）。⇒ **「三持有者」在根 CLI/Web run 上实际只有两持有者**（messages + tool_calls_made）；三持有者形态只存在于 benchmark 与子 agent。#278 复现器若是单 agent 直跑（可能走 CLI），常驻只有两处——不推翻 change（两处也要治），但 grill/design 的「三持有者」总框定对主复现场景**过度**。
4. **后台注入 `:737` 的 64KB user 消息 D3 剪不到**（`background.py:13` `MAX_OUTPUT_BYTES=64*1024`；`:737` 以 `role=user` 注入、无 `tool_call_id`）——与 Q-new5 同类的**残余边界**，须在 design 明写。
5. **`_workflows`/`NodeState.slots` 持全文且从不清理**（`scheduler.py:1841/1869` 存全文、`manager.py:518` 无清理）——但 design Non-Goals **已明确 defer**，故非 grill 漏项，属**已声明边界**。仅提示：`memory-context` spec「常驻上下文 SHALL 有界」的措辞勿被读成**全局**有界。
6. **证据索引路径漂移**：grill 表写 `agent/web/session.py:898`，实为 **`web/session.py:898`**（无 `agent/` 前缀）。

---

## 严重度复核

| 项 | grill 定级 | 对抗复核 | 依据 |
|---|---|---|---|
| Q-new2 悬空 ref | **高** | **中** | 4 生产入口全 `True`，默认 False 只在单测 |
| Q-new5 非工具内容空转 | **中** | **高** | 与自评「高」的 arguments 缺口同机制；D7 每轮强压无解 |
| arguments 无界 | 高 | 高（**低估覆盖**） | 漏了 trace `tool_call` step（`:993`）第四持有者 |
| Web `on_event` 全文外发 | **未列** | **中-高** | `loop.py:1029-1037`；影响 D2 总框定 + Web Expand 回归 |
| 图片绕过硬顶 | 高 | 高（成立） | 1000 token vs MB base64 |
| `_tokens` 缓存 | 高 | 高（成立） | 唯一写点 `manager.py:142` |
| 其余 | 中/低 | 大致成立 | — |

---

## 总体

**可据此拍板（顶住攻击）**：三持有者同对象（普通 str）、`str` 子类可弱引用、trace 图片 sanitize、spec delta 缺穿透场景、`parse_ref` 硬编码、`SessionStore.remove` rmtree、`_tokens` 唯一写点、`full_trace` inert。

**需修正后拍板**：
- **Q4 的 `-2`**：改 `-1`（或改理由）；**显式写「`:854`+`:1047` 都记 `added_iteration`」**。
- **Q1 的「完全等价」**：改「内存态等价；序列化路径对子类复制，测试须断言内存字段」。
- **Q-new2 定级**：高→中，删「非 CLI 入口」错误。
- **Q-new5 + arguments 缺口**：统一为高。
- **补 D2 真消费者清单**：把 **Web `on_event` 全文外发**写进「全文消费者」核对表，并决定 on_event 用原文还是 bounded（**唯一行为回归风险点**，design 完全没提）。
- **「三持有者」措辞**：根 CLI/Web run 实为两持有者，注明 trace 持有者仅在 benchmark/子 agent 存在。

**被证伪**：Q-new2 的「非 CLI 入口会触发」（生产无此入口）；grill 隐含的「工具结果全文没有消费者」（Web `on_event` 是；但 D2 对 trace/tcm 的具体结论仍对）。

**需用户/主 session 拍板**：(1) Q4 取 `-1` 还是 `-2`；(2) Web `on_event` 外发用原文还是 bounded；(3) `_workflows` slots 与 Q-new5 是否写死为残余边界。

---

## 主 session 复核记录（逐条独立实测）

| 对抗结论 | 主 session 复核 | 结果 |
|---|---|---|
| Web chat.js Expand 用 `data.result` 全文 | 读 `web/static/chat.js:932,963-970` | ✅ 确认 |
| `asdict`/`deepcopy` 对 str 子类复制、普通 str 同对象 | 跑 `/tmp/t282_adv1.py` | ✅ 确认（plain True / sub False） |
| `weakref.ref(str)` TypeError、子类 OK | 同上 | ✅ 确认 |
| 根 main.py/web 无 trace_recorder | grep 两文件 + benchmark/子 agent | ✅ 确认 |
| trace `tool_call` step 持全文 arguments | 读 `loop.py:993` + `trace_recorder.py:100` | ✅ 确认 |
| `record_iteration(assistant_preview=response.content)` | 读 `loop.py:756-757` | ✅ 确认 |
