# Bullet 4: ContextBuilder 上下文系统 — 代码走读

> 简历原文：实现 ContextBuilder 统一编排 8 个上下文源，稳定前缀分层注入、字节级不变命中 LLM Prefix Cache，搭配 AutoCompact L1/L2 层级压缩与 tool-call pending 标记防止工具链断裂

---

## 整体架构

上下文系统的代码分布在 6 个文件中，以 `ContextBuilder`（`builder.py`）为编排枢纽，`ContextSource`（`sources.py`）为内容工厂，通过 `AgentLoop._make_default_context_builder()` 一次性注册所有源，每次 LLM 调用前注入。

```
每次 LLM 调用前 (_messages_with_run_context):
┌─────────────────────────────────────────────────────────┐
│            ContextBuilder.build_blocks(ctx)              │
│                                                         │
│  ① 按 priority 排序（0=最高, 6=最低）                      │
│  ② Phase 1: 渲染每个源（static源走缓存，dynamic源每轮重渲染）│
│  ③ Phase 2: 按 budget 截断（最低优先级 tail-first）         │
│  ④ 输出 TextBlock 列表（cacheable 层带 cache=True flag）    │
└──────────────┬──────────────────────────────────────────┘
               │
   ┌─── text block 列表注入为一条 system Message ───┐
   │                                                │
   ▼                                                ▼
 AnthropicLLM._apply_cache_plan()         MemoryManager.compact_if_needed()
 把 cache_control 断点打在                 AutoCompact L1/L2 层级压缩
 最后一个 cacheable block 上              + tool-call pending 标记保护
```

---

## 1. ContextBuilder 统一编排 8 个上下文源

### 注册点

**文件**：`agent/loop.py:1339-1355`

`AgentLoop._make_default_context_builder()` 是唯一的注册入口，创建 `ContextBuilder` 并逐个注册 8 个 `ContextSource`：

```python
def _make_default_context_builder(self) -> ContextBuilder:
    builder = ContextBuilder(total_budget=self._injection_budget)
    builder.register(SystemPromptSource())                                    # ① P0
    builder.register(AsterMdSource())                                         # ② P1
    builder.register(MemoryIndexSource(persistent_memory=self.persistent_memory))  # ③ P2
    builder.register(TodoSource(todo_renderer=self._todo_context))            # ④ P2
    builder.register(SkillIndexSource(skill_runtime=self.skill_runtime))      # ⑤ P4
    builder.register(SkillActiveSource(skill_runtime=self.skill_runtime))     # ⑥ P4
    builder.register(PlanModeSource())                                        # ⑦ P5
    builder.register(PlanningStateSource(planning_manager=self._planning))    # ⑧ P5
    return builder
```

**代码级计数**：恰好 8 次 `builder.register()` 调用（line 1343-1354），无其他注册路径。

### 8 个源的完整属性对照表

**文件**：`agent/context/sources.py`（全部 8 个源的定义）+ `agent/context/protocol.py`（`ContextSource` Protocol 定义）

| # | 源 | Priority | Budget | critical | static | cacheable | 类 (sources.py) |
|---|-----|----------|--------|----------|--------|-----------|-----------------|
| ① | SystemPrompt | 0 (P0) | 1500 | True | True | True | `:100-114` |
| ② | AsterMd | 1 (P1) | 3000 | True | True | True | `:254-275` |
| ③ | MemoryIndex | 2 (P2) | 2000 | False | False | True | `:278-308` |
| ④ | Todo | 2 (P2) | 1000 | False | False | False | `:381-399` |
| ⑤ | SkillIndex | 4 (P4) | 2500 | False | False | False | `:311-324` |
| ⑥ | SkillActive | 4 (P4) | 2500 | False | False | False | `:327-340` |
| ⑦ | PlanMode | 5 (P5) | 2500 | False | False | False | `:343-362` |
| ⑧ | PlanningState | 5 (P5) | 1500 | False | False | False | `:365-378` |

**关键属性释义**（Protocol 定义在 `protocol.py:24-43`）：

| 属性 | 含义 |
|------|------|
| `priority` | 注入顺序 & 截断优先级（0=最高，数字越大越先被裁） |
| `critical` | 永不参与截断（即使超出预算） |
| `static` | 渲染输入不可变（同 cwd/mode/user_system_prompt 下输出字节级不变），可跨迭代缓存 |
| `cacheable` | 稳定前缀层：不参与预算截断 + 打 TextBlock.cache flag，参与 cache_control 断点 |

### Priority 分层模型

```
P0 (最高)     SystemPrompt         ← critical + static + cacheable
P1           AsterMd              ← critical + static + cacheable
P2           MemoryIndex, Todo    ← MemoryIndex cacheable（非 static），Todo 无保护
P3           (未使用)
P4           SkillIndex, SkillActive
P5 (最低)     PlanMode, PlanningState
P6           (未使用)
```

### ContextBuilder 核心实现

**文件**：`agent/context/builder.py:27-204`

核心类 `ContextBuilder`，维护 `_sources: list[ContextSource]` 和 `_static_cache: dict[tuple, str]`。

**注入入口**（`loop.py:1300-1327` `_messages_with_run_context`）：

```python
# loop.py:1303-1313
ctx = BuildContext(
    cwd=cwd,
    mode=self.runtime_state.current_mode,
    context_window=self._context_window,
    total_budget=self._injection_budget,      # min(20K, 20% of context_window)
    user_system_prompt=self._user_system_prompt,
)
blocks = await self.context_builder.build_blocks(ctx)
```

注入预算公式（`loop.py:1335-1337`）：

```python
@property
def _injection_budget(self) -> int:
    """Injection-layer budget: min(20K, 20% of context window)."""
    return min(20_000, int(self._context_window * 0.20))
```

默认 context_window 为 100K（`loop.py:1330-1332`），所以默认注入预算为 `min(20000, 20000) = 20000` tokens。

---

## 2. 稳定前缀分层注入

### 稳定前缀的定义

稳定前缀由具备 `cacheable=True` 属性的源构成。从属性对照表可知：**P0（SystemPrompt）+ P1（AsterMd）+ P2 中的 MemoryIndexSource** 三个 cacheable 层构成稳定前缀。

- P0 和 P1 同时具备 `static=True`：同 cwd/mode/user_system_prompt 下输出**字节级不变**（`builder.py:42-45`）
- P2 MemoryIndex 具备 `cacheable=True` 但 `static=False`：保留在前缀中不受截断，但每轮重渲染以获取最新记忆摘要

### 优先级排序与分层注入

`render_layers()`（`builder.py:69-107`）是核心渲染方法：

```python
# ① 按 priority 排序（0 → 6）
sorted_sources = sorted(self._sources, key=lambda s: s.priority)  # :81

# ② Phase 1: 逐个渲染；static 源命中缓存则跳过渲染
for source in sorted_sources:
    key = self._static_cache_key(source, context)  # :86
    if key is not None and key in self._static_cache:
        content = self._static_cache[key]           # 缓存命中，字节级不变
    else:
        content = await source.render(context)      # :91
        if key is not None:
            self._static_cache[key] = content       # :99 存入缓存

# ③ Phase 2: 预算截断
return self._apply_budget(rendered)                 # :107
```

### Static 缓存机制

`_static_cache_key`（`builder.py:63-67`）决定一个源是否走缓存：

```python
@staticmethod
def _static_cache_key(source: ContextSource, context: BuildContext) -> tuple | None:
    if not getattr(source, "static", False):
        return None          # 非 static 源，返回 None（不走缓存）
    return (source.name, context.cwd, context.mode, context.user_system_prompt)
```

**仅 P0 和 P1 走缓存**。缓存 key 由 `(name, cwd, mode, user_system_prompt)` 组成；只要这四个值不变，P0 和 P1 的输出就是字节级不变的。

MemoryIndexSource 虽不是 `static`，但注释已说明设计原因（`sources.py:289-290`）：

```
非 static：SaveMemory/RecallMemory 会话内会改写 MEMORY.md，缓存会返回陈旧索引。
builder 对无 static 属性的源每轮重渲染。
```

### 预算截断策略

`_apply_budget`（`builder.py:133-166`）采用最低优先级 tail-first 截断：

```python
# 规则（:138-142）:
# ① 永不截断 critical 或 cacheable 源
# ② 从最低优先级的可截断层尾部开始截
# ③ 如果整层被移除，向上找下一层

def _find_trimmable_index(layers):
    for i in range(len(layers) - 1, -1, -1):     # 从末尾向头部扫描
        source = layers[i][0]
        if not source.critical and not getattr(source, "cacheable", False):
            return i                               # 找到最低优先级的可截断层
    return None                                    # 全是受保护层，停止截断
```

**截断级联顺序**：P5（PlanMode/PlanningState）→ P4（SkillIndex/SkillActive）→ P2（TodoSource）。P0、P1 和 MemoryIndexSource（P2 cacheable）永不参与截断。

### build_blocks：生成带 cache flag 的 TextBlock 列表

`build_blocks`（`builder.py:114-127`）是实际注入入口：

```python
async def build_blocks(self, context: BuildContext) -> list:
    layers = await self.render_layers(context)
    return [
        TextBlock(text=content, cache=bool(getattr(source, "cacheable", False)))
        for source, content in layers
    ]
```

`TextBlock.cache` 字段定义在 `agent/message.py:22`：

```python
class TextBlock:
    text: str = ""
    cache: bool = False  # 稳定前缀标记（Anthropic cache_control 断点用）
```

### 层间分隔符

`_join_layers`（`builder.py:197-204`）用 `"\n\n---\n\n"` 连接各层，保证每层视觉上有明确边界。

---

## 3. 字节级不变命中 LLM Prefix Cache

### 整体机制：从 cacheable flag 到 cache_control 断点

```
ContextBuilder.build_blocks()
  → TextBlock.cache=True（cacheable 层）
     → 注入 system Message 的 content 为 list[TextBlock]
        → _compute_cache_plan()
           → 扫描所有 system block，找最后一个 cache=True 的 index
              → CachePlan(stable_system_block_count=N)
                 → AnthropicLLM._apply_cache_plan()
                    → system[N-1] 打上 cache_control: {"type": "ephemeral"}
```

### _compute_cache_plan — 断点计算

**文件**：`agent/loop.py:1103-1148`

```python
def _compute_cache_plan(self, messages, tools=None) -> CachePlan:
    # 扫描所有 system 消息中的 block，找最后一个 cache=True 的 block index
    stable_system_breakpoint = 0
    block_index = 0
    for m in messages:
        if m.role != "system":
            continue
        if isinstance(m.content, list):
            for b in m.content:
                if isinstance(b, TextBlock) and b.cache:   # :1127
                    stable_system_breakpoint = block_index + 1  # 1-based
                block_index += 1
        else:
            block_index += 1

    # Selector OFF（默认）：断点打在最后一个 cacheable system block
    selector = getattr(self.tool_registry, "_selector", None)
    if selector is None:
        return CachePlan(stable_system_block_count=stable_system_breakpoint,
                         stable_tool_count=0)                # :1135-1138

    # Selector ON：断点打在最后一个核心稳定工具上
    ...
    return CachePlan(stable_system_block_count=0,
                     stable_tool_count=stable_tool_count)
```

**默认（Selector OFF）**：断点只打在最后一个 cacheable system block。Anthropic API 缓存该 block **及之前所有内容**（system blocks + 所有 tools），最大程度覆盖。

**Selector ON**：变层 tools 破坏前缀不变性，断点改打在最后一个核心稳定工具上。

### AnthropicLLM._apply_cache_plan — 实际打断点

**文件**：`agent/anthropic_llm.py:167-194`

```python
def _apply_cache_plan(self, payload: dict) -> None:
    plan = getattr(self, "cache_plan", None)
    self.cache_plan = None   # 消费一次（防 stale plan 泄漏到其他 chat 调用）
    if plan is None:
        return

    if plan.stable_system_block_count > 0:
        system = payload.get("system")
        idx = min(plan.stable_system_block_count, len(system)) - 1  # 0-based
        if idx >= 0 and isinstance(system[idx], dict):
            system[idx] = {**system[idx],
                           "cache_control": {"type": "ephemeral"}}    # :188
```

在 system block 的最后一个子块上打 `cache_control: {"type": "ephemeral"}`。

### 字节级不变的前提条件

要保证 prefix cache 命中，缓存区间的内容必须字节级一致：

| 条件 | 机制 | 代码 |
|------|------|------|
| P0/P1 源：同 cwd/mode/user_system_prompt 下输出不变 | `static=True` + 缓存 key 排除变化因素 | `builder.py:63-67` |
| cacheable 层不参与预算截断 | `cacheable=True` → `_find_trimmable_index` 跳过 | `builder.py:178` |
| budget 不变 | 截断位置稳定，不会锯齿状变化 | `loop.py:1337` |
| 工具 schema 不变（Selector OFF） | 全量 tool schema 无变化 | `loop.py:1001` |

### 仅 Anthropic 路径生效

**文件**：`loop.py:1084-1101`

```python
def _apply_cache_plan(self, messages, tools=None) -> None:
    if not getattr(self.llm, "supports_cache_control", False):
        return   # OpenAI 走服务端 auto-caching，不需要手动打断点
    plan = self._compute_cache_plan(messages, tools)
    self.llm.cache_plan = plan
```

`supports_cache_control = True` 只在 `AnthropicLLM`（`anthropic_llm.py:36`）上声明。OpenAI 端通过服务端 auto-caching 实现类似效果，不需要手动打点。

### 400 降级保护

**文件**：`anthropic_llm.py:74-86`

某些 Anthropic 兼容端点（如 DeepSeek-anthropic）会拒收 `cache_control` 字段并返回 400。AnthropicLLM 在非流式路径中自动检测并重试：

```python
if self._payload_has_cache_control(payload):
    logger.info("400 with cache_control — retrying without it")
    payload = self._strip_cache_control(payload)   # 深拷贝并去掉所有 cache_control
    return await self._chat_nonstream(payload)      # 重试
```

流式路径同样有对应的 400 降级逻辑（`anthropic_llm.py:239-261`）。

---

## 4. AutoCompact L1/L2 层级压缩

### 触发时机

**文件**：`agent/loop.py:939-959`

每次迭代的 Phase 3 末尾，工具执行结果回填后触发：

```python
# loop.py:941
compacted = await self.memory.compact_if_needed(messages, iteration=self._iteration)
```

### compact_if_needed — 触发条件

**文件**：`agent/memory/manager.py:141-173`

```python
async def compact_if_needed(self, messages, iteration=0) -> bool:
    msgs = messages if messages is not None else self.messages
    total = self.count_tokens(msgs)

    # 阈值：compact_trigger_tokens 如果配置了就用它，
    # 否则 = max_tokens - 15_000（保留 15K 给 LLM 回复）                # :155
    threshold = (self.compact_trigger_tokens if self.compact_trigger_tokens is not None
                 else max(1, self.max_tokens - 15_000))

    if total >= threshold:
        # 间隔检查：至少隔 compaction_gap=5 轮才能再次压缩，防止抖动       # :157
        if iteration - self._last_compaction_iteration >= self._compaction_gap:
            await self.compact(msgs)
            self._last_compaction_iteration = iteration
            return True
```

**两项触发条件**（必须同时满足）：
1. 总 token >= 阈值（默认 `max_tokens - 15000`，即 100K 下为 85K）
2. 距上次压缩 >= 5 次迭代

### compact — 核心压缩流程

**文件**：`agent/memory/manager.py:175-307`

```
① 分离 system 消息（保留）
② 计算 recent window：_recent_with_tool_chains (10 条消息 + 保护工具链)
③ 确定 middle segment：非 system 中超出 recent window 的部分
④ _decorate_for_summary：pending 标记 + 分页进度注入
⑤ summarizer.summarize(annotated_middle, budget=middle_tokens*0.30)
⑥ 合并 running_summary（首次直接赋值，后续 merge）
⑦ L1 记账 → 检查是否触发 L2
⑧ 用 [system] + [summary_msg(user)] + [recent] 替换 messages
```

**汇总消息的角色**：压缩后的 running summary 以 **user 角色**（不是 system）注入（`:302`），这样模型把它当作"之前的对话上下文"而非"系统约束"。

### L1 层：增量压缩

每次压缩产出一个 L1 summary chunk，记录在 `_l1_chunks` 列表中。`_l1_accumulated_tokens` 增量累加，避免每次重新编码（`:280`）。

```python
# manager.py:274-280
self._l1_chunks.append(new_summary)
self._l1_chunk_ranges.append(middle_range)
self._tiers.append(SummaryTier(
    tier="L1", content=new_summary, source_range=middle_range, generated_at=now,
))
self._l1_accumulated_tokens += _count_tokens(new_summary)
```

### L2 层：高阶压缩

**触发条件**（`manager.py:282`）：

```python
# 两个条件必须同时满足
if len(self._l1_chunks) >= 2 and accumulated >= self.l2_trigger_tokens:
    #                                             ↑ 默认 6000 (:83)
```

即：至少 2 个 L1 chunk **且** L1 累积 token >= 6000。

**L2 压缩逻辑**（`:282-297`）：

```python
# 压缩输入 = 已有 L2 基础 + 所有 L1 chunks
compress_input = ([self._l2_summary] if self._l2_summary else []) + self._l1_chunks

# 预算 = L1 累积 token 的 30%
l2 = await self._compress_to_l2(compress_input, budget=int(accumulated * 0.30))
if l2:
    self._running_summary = l2      # 替换 running summary
    self._l2_summary = l2           # 保存 L2 基础（下次压缩时带上）
    self._tiers.append(SummaryTier(tier="L2", content=l2, ...))
    self._l1_chunks = []            # 清空 L1 缓存
    self._l1_chunk_ranges = []
    self._l1_accumulated_tokens = 0
```

**关键设计**：每次 L2 压缩都带上之前的 L2 基础（`:285`），确保顶层结论永不丢失之前的上下文。

### L2 压缩实现 — LLMSummarizer.compress

**文件**：`agent/context/summarizer.py:215-244`

```python
async def compress(self, tier_summaries: list[str], budget: int = 0) -> str | None:
    body = "\n\n".join(
        f"## L1 Summary {i}\n{text}" for i, text in enumerate(tier_summaries, 1)
    )
    response = await self._llm.chat(
        messages=[
            Message(role="system", content=_LLM_L2_COMPRESS_SYSTEM_PROMPT),
            Message(role="user", content=body + budget_hint),
        ],
        tools=None,
    )
    return (response.content or "").strip() or None
```

L2 的 system prompt（`summarizer.py:98-107`）明确指示：

```
只保留最高层次结论、关键决策、仍待处理的 pending 项。
每个文件路径、函数名、工具名、未解决问题、关键决策必须保留。
Keep `[call#<i>: <tool_call_id> pending]` markers verbatim.
```

### 两种 Summarizer

| 类型 | 触发条件 | 行为 |
|------|----------|------|
| `LLMSummarizer` | `MemoryManager.llm` 不为 None（默认启用） | LLM 生成四段式结构化摘要 |
| `TruncationSummarizer` | `MemoryManager.llm` 为 None | 截断策略：工具输出截断到 500 字符，旧消息丢弃 |

`MemoryManager._get_summarizer()`（`manager.py:107-116`）按 llm 是否存在做懒初始化：

```python
def _get_summarizer(self):
    if self._summarizer is not None:
        return self._summarizer
    if self.llm is not None:
        self._summarizer = LLMSummarizer(self.llm)      # 默认路径
    else:
        self._summarizer = TruncationSummarizer()        # 无 LLM 降级
    return self._summarizer
```

### 四段式摘要结构

**文件**：`summarizer.py:74-96`

```markdown
## 已完成事项
## 待办事项
## 疑难点与决策
## 当前进行中
```

该结构在 agent 恢复上下文时提供清晰的信息分层。

---

## 5. tool-call pending 标记防止工具链断裂

### 工具链保护 — _recent_with_tool_chains

**文件**：`agent/memory/manager.py:371-403`

在计算 recent window 时，不仅保留最后 `recent_window=10` 条消息，还向前扩展以确保每个 tool_result 对应的 assistant tool_call 消息不丢失：

```python
def _recent_with_tool_chains(self, messages):
    start = max(0, len(messages) - self.recent_window)  # 最后 10 条
    while start > 0:
        expanded = False
        for index in range(start, len(messages)):
            message = messages[index]
            if message.role != "tool" or not message.tool_call_id:
                continue
            # 找到这个 tool_result 对应的 assistant 消息
            assistant_index = self._find_tool_call_assistant(
                messages, message.tool_call_id, before=index)
            # 如果 assistant 消息在 window 之外 → 扩展 window 包含它
            if assistant_index is not None and assistant_index < start:
                start = assistant_index
                expanded = True
                break
        if not expanded:
            break
    return messages[start:]
```

例如：如果最后 10 条里有 3 个 tool result 但它们的 assistant 消息在第 12 条之前，则 window 自动扩展到包含那些 assistant 消息，保证 `[assistant tool_call] → [tool result]` 链完整。

### _annotate_pending_calls — 挂起标记

**文件**：`agent/memory/manager.py:409-454`

在压缩 middle segment 之前，对**尚未收到 tool_result 的工具调用**打上 pending 标记：

```python
def _annotate_pending_calls(self, messages, recent):
    # 收集所有已有结果的 tool_call_id（middle + recent 全量扫描）
    result_ids: set[str] = set()
    for m in (*messages, *recent):
        if m.role == "tool" and m.tool_call_id:
            result_ids.add(m.tool_call_id)

    annotated: list["Message"] = []
    for m in messages:
        if m.role != "assistant" or not m.tool_calls:
            annotated.append(m)
            continue
        # 找到所有没有结果的 tool_call
        pending = [
            (i, tc)
            for i, tc in enumerate(m.tool_calls, 1)
            if getattr(tc, "id", None) and tc.id not in result_ids
        ]
        if not pending:
            annotated.append(m)
            continue
        # 追加 pending 标记
        markers = " ".join(
            f"[call#{i}: {tc.id} pending]" for i, tc in pending
        )
        content = f"{content}\n\n{markers}" if content else markers
        annotated.append(Message(role=m.role, content=content, ...))
    return annotated
```

**标记格式**：`[call#1: toolu_abc123 pending] [call#2: toolu_def456 pending]`

其中 `#1`、`#2` 是 1-based 位置编号（`enumerate(m.tool_calls, 1)`），`toolu_abc123` 是工具调用 ID。

### _decorate_for_summary — 组合注入

**文件**：`agent/memory/manager.py:474-499`

```python
def _decorate_for_summary(self, middle, recent):
    annotated = self._annotate_pending_calls(middle, recent)        # ① pending 标记
    progress = self._extract_read_progress([*middle, *recent])       # ② 分页进度
    if progress:
        hint = Message(role="user", content=(
            "当前分页读取进度（大文件续读用，请在「当前进行中」中保留...:\n"
            + "\n".join(f"- {path}: offset={offset}, total={total}"
                        for path, offset, total in progress)
        ))
        annotated = [*annotated, hint]                               # ③ 追加进度 hint
    return annotated
```

这个装饰是在**传给 summarizer 之前**完成的，所以 LLM 做摘要时能看到：哪些工具调用还没完成、大文件读到了哪个位置。

### LLM Summarizer 中 pending 标记的保留

**文件**：`summarizer.py:54-62`（system prompt）

```
Preserve each tool call as a `call#n: name(args) -> result` line and keep
`[call#<i>: <tool_call_id> pending]` markers verbatim.
```

**文件**：`summarizer.py:91`（user prompt）

```
incomplete calls (no result yet) stay as `[call#<i>: <tool_call_id> pending]`.
```

L2 压缩的 system prompt（`summarizer.py:104`）同样要求：

```
keep `[call#<i>: <tool_call_id> pending]` markers verbatim.
```

**三层保障链**：
1. `_recent_with_tool_chains` — 保证工具链消息不会被 recent window 切断
2. `_annotate_pending_calls` — 在压缩前把未完成的工具调用显式标记为 pending
3. Summarizer prompt — 要求 LLM 在摘要中逐字保留 pending 标记

### ReadProgress 分页进度保留

`_extract_read_progress`（`manager.py:456-472`）从 tool result 中提取 `[ReadProgress file="..."; offset=...; total=...]` 注记，以 per-file last-winner 策略保留最后一次读到的 (file, offset, total)。这些信息通过 `_decorate_for_summary` 注入摘要 prompt，确保压缩后 agent 仍知道大文件读到了哪里（避免从头重新读取）。

---

## 默认配置速查

| 参数 | 默认值 | 位置 |
|------|--------|------|
| ContextBuilder 注入预算 | `min(20000, context_window * 0.2)` | `loop.py:1337` |
| context_window 默认 | 100000 (100K) | `loop.py:1330-1332` |
| MemoryManager.max_tokens | 100000 | `manager.py:77` |
| recent_window | 10 条消息 | `manager.py:78` |
| compaction_gap | 5 轮迭代 | `manager.py:81` |
| compact_trigger_tokens | `max_tokens - 15000` (即 85K) | `manager.py:155` |
| l2_trigger_tokens | 6000 | `manager.py:83` |
| L2 触发 L1 chunk 数 | >= 2 | `manager.py:282` |
| L1/L2 压缩预算 | middle_tokens * 0.30 | `manager.py:237, :286` |
| Static cache key | `(name, cwd, mode, user_system_prompt)` | `builder.py:67` |
| MAX_ASTER_SIZE_BYTES | 32768 (32KB) | `sources.py:121` |
| TruncationSummarizer 工具输出截断 | 500 字符 | `summarizer.py:21` |
| 层间分隔符 | `"\n\n---\n\n"` | `builder.py:204` |
| cache_control 类型 | `"ephemeral"` | `anthropic_llm.py:188` |

**无"默认关闭"的功能**：ContextBuilder 在 `AgentLoop.__init__` 中始终创建（`loop.py:156-159`），AutoCompact 始终由 `compact_if_needed` 调用（`loop.py:941`），cache_control 断点对所有 `supports_cache_control=True` 的 LLM 生效。整个上下文系统没有通过配置开关控制的功能。

---

## 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/context/builder.py` | ContextBuilder：优先级排序 + 静态缓存 + 预算截断 + 层连接 |
| `agent/context/sources.py` | 全部 8 个 ContextSource 实现 + ASTER.md 收集/渲染 |
| `agent/context/protocol.py` | ContextSource Protocol + BuildContext 数据类 |
| `agent/context/summarizer.py` | Summarizer Protocol + LLMSummarizer（四段式 + L2）+ TruncationSummarizer |
| `agent/memory/manager.py` | MemoryManager：AutoCompact + L1/L2 层级记账 + tool-call pending + ReadProgress 保护 |
| `agent/loop.py:1339-1355` | `_make_default_context_builder()` — 8 源注册点 |
| `agent/loop.py:1300-1327` | `_messages_with_run_context()` — context 注入到 messages |
| `agent/loop.py:1084-1148` | `_apply_cache_plan()` + `_compute_cache_plan()` — cache_control 断点计算 |
| `agent/anthropic_llm.py:167-194` | `AnthropicLLM._apply_cache_plan()` — cache_control 断点实际注入 |
| `agent/anthropic_llm.py:36` | `supports_cache_control = True` |
| `agent/message.py:18-22` | `TextBlock` — `cache: bool` 字段定义 |
| `agent/llm.py:20-31` | `CachePlan` — `stable_system_block_count` + `stable_tool_count` |
