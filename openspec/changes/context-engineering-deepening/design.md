# Design: 上下文工程做深 — 结构化摘要 + 层级压缩 + Prefix Cache 优化

## Context

当前上下文管线已有 ContextBuilder（P0-P6 注入）+ MemoryManager（90% 阈值 AutoCompact）+ LLMSummarizer（四段式）。但摘要字段缺"疑难点"维度、"待办/阻塞"未拆开；tool_call 成对保留只在最近窗口，中间段摘要后未完成调用无 pending 标记；只有单层 running summary，无层级压缩；ReadTool 无 offset/进度续读；所有层拼一个 system 消息，无 cache_control 断点；深层 MD 只在根链上收集。面试表现"阈值触发 + LLM 做摘要"即被判定停留在原型。

## Goals / Non-Goals

**Goals:**

- 四字段结构化摘要（已完成/待办/疑难点与决策/当前进行中）。
- tool_call/tool_result 成对保留 + `[call#n pending]` 标记。
- 两级层级压缩（一级摘要 → 二级压缩）。
- 分页读大文件进度保留 `(file, offset, total)`。
- Prefix Cache 注入顺序（system → MD → 工具 → 记忆索引 → 用户消息）+ cache_control 断点。
- 深层 MD 按需加载 tool。

**Non-Goals:**

- 不重做 ContextBuilder 架构（P0-P6 已存在）。
- 不改动单次运行语义与 artifact 结构（向后兼容）。
- 不实现 P3 自动召回 / P6 对话历史（后续项）。

## Decisions

### Decision 1: 拆 3 个子 change 分阶段合入

**方案**：本 change 拆为 3 个子 change，各自独立合入、各自产出单点量化数据：
- ① 增量 token 计数 + ContextBuilder 缓存 + 四字段摘要 + tool_call pending 标记（不碰工具注入缝，可与 Batch 1 并行开工）。
- ② Prefix Cache 注入顺序（system → MD → 工具 → 记忆索引稳定前缀 + cache_control 断点）。
- ③ 分页读进度 `(file, offset, total)` + 深层 MD 按需加载 tool。

**备选**：一个大 change。被拒：冲突面最大（loop 注入/压缩/resume），拆开可错开合入、各自量化。

**理由**：拆分降低冲突风险，每子项产出独立面试量化点。

### Decision 2: 四字段摘要替换现有四段式

**方案**：把 LLMSummarizer 的"已完成/关键决策/进行中/阻塞与待办"改为"已完成事项/待办事项/疑难点与决策/当前进行中"，补"疑难点"维度、拆开"待办/阻塞"。模板 `_LLM_SUMMARY_USER_TEMPLATE` 同步更新。

**备选**：保留现四段。被拒：缺"疑难点"维度，无法讲"踩过的坑"。

**理由**：四字段结构与面试标准答案、业界主流对齐。

### Decision 3: 两级层级压缩

**方案**：L1 摘要（最近窗口 tool 链成对保留）→ 累积超标 → L2 压缩（只保留最高层结论）。summary 带层级元数据（tier/来源范围/生成时间）。

**备选**：单层 running summary。被拒：无法支撑超长会话。

**理由**：层级压缩是长会话 token 上界可控的关键。

### Decision 4: Prefix Cache 注入顺序 + 稳定层/可变层分层

**方案**（已按 grill 裁定 Q1/Q3/Q4/Q6 修正为 wire 顺序 + 按模式单断点）：
- 注入 wire 顺序：**system（prompt → MD → memory index）→ tools（core stable → 选中 variable tail）→ user messages**。记忆索引（P2）留在缓存 system 区域；其相对 tools 的位置由 provider wire 格式决定（system 字段先于 tools 字段），不追求字面 "tools 在 memory index 之前"。
- 稳定前缀冻结：P0/P1/P2 在 `_apply_budget` 之外以完整未截断尺寸渲染，token 预算只作用于 P4/P5；截断整块丢弃而非裁剪 P0-P2，保证稳定前缀跨迭代字节一致。
- 按模式单断点：**selector OFF（默认）** → 只放 P2 system 断点（全量 tools 数组字节稳定，P2 同时缓存 tools+system）；**selector ON** → 只在最后一个核心工具放 cache_control（变长 tail 使 P2 断点失效）。任何情况下不宣称两个缓存同时命中。
- 稳定标记机制：`TextBlock.cache: bool = False` 字段（`to_dict/from_dict` 序列化）；核心工具集 Read/Edit/Write/Bash/Glob/Grep/InspectGitDiff；`_select_tool_schemas` 在 selector 存在时调用 `set_stable_tools(core_names)`；`CachePlan(stable_system_block_count, stable_tool_count)` 经 `_call_llm` 只传给 `AnthropicLLM._build_payload`。
- anthropic_llm.py 加 cache_control（ephemeral）断点；openai_llm.py 接受并忽略 CachePlan，不发送 cache_control（OpenAI 自动缓存前缀）。cache_control 加 provider 能力门控 + 400 重试降级。

**备选**：全层拼一个 system 消息。被拒：无法利用 prefix cache，无法讲 cache 命中率。

**理由**：稳定前缀是 cache 收益的前提，需与 #77 动态选择契约共存；wire 顺序与断点策略必须按 Anthropic 渲染语义设计（tools → system → messages），否则断点失效。

## Pre-Implementation Review

已完成 `batch-grill-me` 设计追问（2026-08-02），完整裁定见 `reviews/design-grill.md`。关键裁定：

- **Q1 顺序解释**：spec 字面顺序 "system → MD → 工具 → 记忆索引 → 用户消息" 在 Anthropic wire（tools → system → messages）上不可达；保留 P2 于缓存 system 区域，spec Then 子句改为 wire 顺序（已同步 spec delta）。
- **Q2 L2 压缩**：L1→L2 + tier 元数据补进子 change ①（原 tasks 缺失），保持压缩比量化主张。
- **Q3 断点策略**：按模式单断点（selector OFF → P2 system 断点；ON → 末核心工具断点），不宣称双断点。
- **Q4 稳定前缀**：P0/P1/P2 冻结于预算 pass 之外，保证跨迭代字节一致。
- **Q5 P2 缓存**：P2 排除静态源缓存（或 content-hash 键），防 SaveMemory 中途改写陈旧。
- **Q6 稳定标记**：`TextBlock.cache` 字段 + `CachePlan` 传 Anthropic，核心工具集 Read/Edit/Write/Bash/Glob/Grep/InspectGitDiff。
- **Q7 token 计数**：改用 Message 非序列化 `_tokens` 字段，规避 id() 复用危险。
- **Q8 pending 标记**：绑定 `tool_call_id`（`[call#<i>: <id> pending]`），MemoryManager 预扫标注，模板加成对保留指令。
- **Q12 builder 返回类型**：`build()` 保持 str；新增 `build_blocks()`/`render_layers()` API 供 loop 使用。

## Reference Implementation Research

- status: enabled
- reason: 上下文工程是 Claude Code（Dream 机制/占位符）、MemGPT 等成熟系统的核心能力，需参考其四字段摘要、层级压缩、Prefix Cache 注入顺序、按需加载实现。
- research questions:
  - Claude Code 的四字段摘要结构与层级压缩触发条件？
  - Prefix Cache（cache_control）注入顺序与断点策略？
  - 分页读大文件进度保留实现？
- findings:
  - **Anthropic prompt caching 渲染顺序是 tools → system → messages**；断点标记缓存段终点，段内任一字节变化使该段失效。因此"双断点（P2 + 末核心工具）同时命中"仅在 tools 数组字节稳定时成立 → 采用按模式单断点策略（Q3 裁定）。缓存段最小长度按模型而异（Sonnet 4 = 1024 tokens，Opus/Haiku 4.5+ = 4096），核心工具集 schema 长度需实测，不足则接受工具段 miss。
  - **Claude Code 占位符/Dream 机制**：以占位符保留未完成调用、延迟到可完成时再解析，对应本 change 的 `[call#n pending]` 标记；实现上绑定 `tool_call_id` 可跨摘要/合并存活。
  - **MemGPT 层级记忆**：L1 工作记忆 + L2 长期压缩，按累积量触发二次压缩；对应本 change L1→L2 压缩 + tier 元数据。
  - **分页进度保留**：Read 工具返回 `(file, offset, total)` 进度注记，压缩时扫描 tool-result 内容提取最后一条，写入摘要"当前进行中"区。
- design impact:
  - 与 #77 约定工具注入缝「稳定层/可变层」分层：selector 存在时 `set_stable_tools(core_names)`（原实现从未被调用，需 wiring + 测试）。
  - 与 #78 约定压缩/缓存事件 schema：`memory_compaction` 事件补充 before/after tokens、压缩层级；新增 cache 断点事件（延迟到 #78 事件 schema 稳定后对齐）。
  - `build()` 公共契约保持不变，新增 `build_blocks()` API，避免破坏既有消费点。
  - 静态源缓存键：P0/P1 用 `(name, cwd, mode, user_system_prompt)`；P2 排除或 content-hash 键。

## Risks / Trade-offs

- **[压缩信息丢失] → 四字段摘要保留关键状态，pending 标记防链断；压缩前后对比量化验证。**
- **[Prefix Cache 与 #77 动态 Top-K 张力] → 先约定「稳定层/可变层」分层策略，动态选择只变 tail。**
- **[cache_control provider 差异] → 定义跨 provider 测量方法（Anthropic cache_control vs OpenAI 自动缓存）。**
- **[拆分 3 子 change 顺序耦合] → ① 不碰注入缝可与 Batch 1 并行；②③ 依赖 #77 注入契约。**
- **[分页进度兼容性] → ReadTool 缺省行为不变（path+limit），新增 offset 为可选参数。**

## Testing Strategy

- 单元测试：四字段摘要、pending 标记、L1/L2 压缩、分页进度、cache 分层。
- 集成测试：注入顺序、压缩触发、resume 时 pending 链。
- 回归测试：既有 context/memory/loop 测试不回归。
- benchmark 层级：压缩率/token 节省量化（复用 PR #80 statistics）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/context/summarizer.py` | 四字段模板 + pending + L2 |
| `agent/memory/manager.py` | 层级摘要状态 + 未完成 tool call |
| `agent/context/builder.py` | cache 感知分层 |
| `agent/context/sources.py` | source 排序与断点 |
| `agent/tools/builtin/read.py` | 分页进度 |
| `agent/tools/registry.py` | 工具描述排序 |
| `agent/anthropic_llm.py` | cache_control 断点 |
| `agent/openai_llm.py` | provider 对齐 |
| `agent/loop.py` | 注入顺序、resume pending、压缩触发 |
| `agent/trace_recorder.py` | 压缩/缓存事件 |
| `benchmarks/` | 压缩率量化 |
