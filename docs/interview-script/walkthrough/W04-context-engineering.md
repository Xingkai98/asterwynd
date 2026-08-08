# W04 · ContextBuilder 上下文工程

**对应简历 bullet 4**：*"实现 ContextBuilder 统一编排 8 个上下文源，稳定前缀分层注入、字节级不变命中 LLM Prefix Cache，搭配 AutoCompact L1/L2 层级压缩与 tool-call pending 标记防止工具链断裂"*

## 代码入口

```
agent/context/
├── protocol.py     ← ContextSource Protocol（priority/name/budget/critical）
├── builder.py      ← ContextBuilder（渲染、预算裁剪、TextBlock 生成）
├── sources.py      ← 8 个具体源
└── summarizer.py   ← LLMSummarizer / TruncationSummarizer（L1/L2）

接线：loop.py:1339 _make_default_context_builder() ← 8 源注册点
调用点：loop.py:624 _messages_with_run_context() → build_blocks()
压缩：loop.py:941 compact_if_needed → memory/manager.py compact()
```

## 核心逻辑

### 8 个上下文源（P0-P5）

| 层 | 源 | priority | critical | cacheable | static |
|----|----|----|----|----|----|
| P0 | SystemPromptSource | 0 | ✅ | ✅ | ✅ |
| P1 | AsterMdSource（ASTER.md 项目指令） | 1 | ✅ | ✅ | ✅ |
| P2 | MemoryIndexSource（持久记忆摘要） | 2 | ❌ | ✅ | ❌（每轮重渲染） |
| P4 | SkillIndexSource | 4 | ❌ | ❌ | — |
| P4 | SkillActiveSource | 4 | ❌ | ❌ | — |
| P5 | PlanModeSource | 5 | ❌ | ❌ | — |
| P5 | PlanningStateSource | 5 | ❌ | ❌ | — |
| P5 | TodoSource | 5 | ❌ | ❌ | — |

**三个关键区分**：
- **critical** = 永不裁剪（P0/P1）
- **cacheable** = 稳定前缀层，参与 cache_control 断点，**也不参与预算裁剪**（P0/P1/P2）
- **static** = 渲染输入不可变，可缓存输出（P0/P1）；P2 MemoryIndex 故意**非 static**（SaveMemory 会改写索引，缓存会返回陈旧内容，sources.py:288-290 注释明确此权衡）

### 稳定前缀分层注入（builder.py:113-126）

`build_blocks()` 把每层渲染成独立 `TextBlock`，cacheable 层带 `cache=True` → Anthropic 在最后一个稳定块放 cache_control 断点。**"字节级不变"** = P0/P1/P2 每轮字节相同 → 缓存命中。

- **预算裁剪**（builder.py:132-165）：从最低优先级尾部裁，critical 和 cacheable 永不裁。注入预算 = `min(20_000, context_window × 20%)`（loop.py:1335-1337）。
- **静态缓存**（builder.py:45）：static 源按 `(name, cwd, mode, user_system_prompt)` 缓存渲染输出。

### AutoCompact L1/L2 层级压缩（memory/manager.py:267-297）

```
每次 compact 产出一个 L1 四段式摘要（已完成/待办/疑难点/进行中）
  → 累积到 _l1_chunks
  → 当累积 ≥ 2 块 且 累积 tokens ≥ l2_trigger_tokens (6K)
  → 触发 L2 压缩：把（旧 L2 base + 累积 L1）再压成顶层结论
  → 重置 L1 累积，tier 轨迹保留（_tiers）
```

- **增量累积**（manager.py:280）：`_l1_accumulated_tokens` 避免每次重编码所有 chunk。
- **L2 带旧 base**（manager.py:285）："顶层结论永不丢失先前上下文"。
- 每轮压缩只处理**新增消息**（manager.py:198），然后 merge 进 running summary。
- 摘要作为 **user 消息**注入（manager.py:301-305）——"agent 当它是先前对话上下文，而非系统约束"。
- 阈值默认 `max_tokens − 15K`，`compaction_gap=5` 防抖动。
- **无 LLM 降级**：TruncationSummarizer（截断 500 字符 + 丢弃旧消息）。

### tool-call pending 标记（manager.py:409-454）

- 压缩前 `_annotate_pending_calls`：**某 tool_call 没有对应 tool result → 标记 `[call#<i>: <tool_call_id> pending]`**。
- 为什么：压缩会把中间 tool result 压掉，assistant 的 tool_call 若结果丢失消息链非法。pending 标记让 LLM 知道"这个调用还没结果"。
- 同时保留 **Read 分页进度** `[ReadProgress file=...; offset=...; total=...]`（manager.py:456-472）。

### 工具链保护另一层（manager.py:371-403）

`_recent_with_tool_chains`：recent 窗口不是简单最后 N 条，而是**把落在窗口外但属于窗口内 tool result 的 assistant 消息回溯进来**（while 扩展循环）。保证压缩后最近工具链完整。

## 简历核实

| 简历 | 核实 | 结论 |
|------|------|------|
| "8 个上下文源" | _make_default_context_builder 正好 8 个 | ✅ |
| "稳定前缀分层注入、字节级不变命中 Prefix Cache" | builder.py cacheable + static cache + cache_control | ✅ |
| "AutoCompact L1/L2 层级压缩" | manager.py L1/L2 tier + l2_trigger_tokens | ✅ |
| "tool-call pending 标记防止工具链断裂" | _annotate_pending_calls | ✅ |

## 面试加分点

1. **"压缩摘要作为 user 消息而非 system"**——认知深度细节。
2. **Read 分页进度保留**——大文件续读场景。
3. **L2 带旧 base 压缩**——"顶层结论不丢上下文"的设计取舍。
