# Q04: 上下文管理——怎么构造、压缩、注入

## 讲稿

上下文管理是 coding agent 的核心瓶颈——context 是有限的，但 agent 需要注入仓库结构、记忆、技能、计划，同时保留对话历史。Asterwynd 用三层设计解决。

**第一层，构造（注入哪些）**。`ContextBuilder` 统一编排所有 `ContextSource`：系统提示、ASTER.md（项目约定）、记忆索引、技能索引、计划、待办。每个 source 渲染成一层，按优先级排序，最终拼成 system 块注入。

**第二层，预算分配（放不下的怎么办）**。总 token 预算有限，`_apply_budget` 从**最低优先级的可裁剪层尾部**开始截断。关键设计：**critical（P0）和 cacheable（稳定前缀 P0/P1/P2）层永不截断**——因为它们必须字节级稳定才能命中 LLM 的 Prefix Cache。可裁剪层从尾部删，删完再上移一层。

**第三层，对话历史压缩**。`MemoryManager` 在 token 超阈值时压缩历史：第一次压缩把中间段整体摘要，之后只摘要**新增**消息并合并进运行摘要；system 消息和最近消息（含 tool 链）保留。摘要以 **user 消息**注入——让 agent 把摘要当"先前对话上下文"而非约束。压缩还做了**四字段摘要**（已完成事项/待办/疑难点与决策/当前进行中）和 **L1/L2 层级压缩**——L1 是增量块摘要，L2 在累计到阈值时把多个 L1 再压成高层摘要，避免无限膨胀。

面试重点：稳定前缀缓存不是"塞进去就行"，而是靠 `build_blocks` 把 cacheable 层标记 `cache=True`，让 LLM 层在最后稳定块打 cache breakpoint。同时增量 token 计数缓存（`message._tokens`）让重复 count 是 O(1)。

## 代码走读

### 入口与调用链

```
AgentLoop._messages_with_run_context (loop.py:1300)
  → ContextBuilder.build_blocks (context/builder.py:113)
    → render_layers → _apply_budget → [TextBlock(cache=source.cacheable)]
  → MemoryManager.compact_if_needed (memory/manager.py:141) [超阈值时]
    → compact → summarizer
```

### 关键文件逐段

**`agent/context/builder.py` `class ContextBuilder`**
- `register(source)`（51 行）：注册 ContextSource。
- `render_layers`（69 行）：渲染所有 source 成层，按优先级排序。
- `build_blocks`（113 行）：把每层变成 `TextBlock`，`cacheable` 层标 `cache=True`——这是稳定前缀缓存的接线点，LLM 层据此在最后稳定块打 cache breakpoint。
- `_apply_budget`（132 行）：预算分配。从最低优先级**可裁剪**层尾部开始截断；critical 和 cacheable 层跳过（`_find_trimmable_index` 176-179 行）。这是"稳定前缀字节级稳定"的机械保证。
- `_truncate_tail`（182 行）：按 `excess_tokens * _CHARS_PER_TOKEN_ESTIMATE` 估算字符数截尾。

**`agent/context/sources.py` — ContextSource 家族**
- `SystemPromptSource`（100 行）：系统提示，critical。
- `AsterMdSource`（254 行）：项目 ASTER.md 约定，cacheable。
- `MemoryIndexSource`（278 行）：长期记忆索引（~50 token 摘要，Q06 展开）。
- `SkillIndexSource`（311 行）/ `SkillActiveSource`（327 行）：技能索引与激活技能。
- `PlanModeSource`（343 行）/ `PlanningStateSource`（365 行）/ `TodoSource`（381 行）：计划与待办。

**`agent/memory/manager.py` `class MemoryManager`**
- `_count_message_tokens`（128 行）：**token 计数缓存**——`Message._tokens` 非序列化字段，重复 count 是 O(1)；压缩/恢复创建新消息时 `_tokens=None` 首次触达重算。
- `compact_if_needed`（141 行）：超阈值触发压缩，阈值默认 `max_tokens - 15_000`（给 LLM 响应留 15K）；`compaction_gap` 防止抖震。
- `compact`（175 行）：第一次压缩整段中间摘要；之后只摘要**新增**消息合并进运行摘要；system 和最近消息（含 tool 链）保留；摘要以 **user 消息**注入。
- L1/L2 层级：`SummaryTier`（38 行）记录 tier（L1/L2）；`_l1_chunks` 累积 L1 摘要，`l2_trigger_tokens`（默认 6000）到阈值把多个 L1 压成 L2。四字段摘要（已完成/待办/疑难点/进行中）在 `agent/context/summarizer.py`。

**`agent/message.py`** — `TextBlock`、`count_tokens_for_content`、`extract_text`。

### 设计理由

- **分层注入而非单一大 prompt**：每个 source 独立渲染、独立测试、独立讲面试；按优先级 + 预算统一编排。
- **稳定前缀缓存**：`cacheable` 层字节级稳定才命中 Prefix Cache（省 token 成本），所以预算裁剪**绝不碰** cacheable 层——这是"缓存命中"和"上下文裁剪"两个目标的权衡点。
- **增量压缩**：只摘要新增消息，避免反复全量摘要（省 LLM 调用）；L1/L2 层级防无限膨胀。
- **摘要当 user 消息**：让模型把历史当"对话上下文"而非 system 约束，避免压缩后的指令被当成强约束。
- **token 计数缓存**：重复 count 是循环热点（每轮都算），缓存到消息对象上避免 O(n) 重复扫描。
