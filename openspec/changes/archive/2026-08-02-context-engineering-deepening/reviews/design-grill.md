# Design Grill: context-engineering-deepening（issue #74）

> 状态：**已记录，agent 推荐答案待用户确认**。本 review 是进入 building 前的 `batch-grill-me` 设计追问产物。用户不可实时作答；以下每项均给出 agent 推荐答案，实施前需用户确认；确认前这些结论不视为用户决定。设计基线仍以 `design.md` 的 Decisions 1-4 为准，本文件记录其实现细节的裁定与修正。

## 审阅方式

- 方法：`batch-grill-me` 设计树逐轮追问（一轮问整个 frontier）。
- 事实收集：5 个 Explore subagent 并行通读 `agent/context/`、`agent/memory/`、LLM 层、工具层、loop/trace，产出带 `file:line` 的代码现状地图。
- 对抗审阅：Workflow 4 视角审阅面板（spec 对齐 / cache 语义 / 边界与回归 / 测试策略），合成最终结论。
- 总 verdict：**CHANGES_REQUESTED**（方案需按本文件修正后进入实现）。

## 设计树

```
context-engineering-deepening (issue #74)
├── Decision 1: 拆 3 子 change 分阶段合入 ── 确认 ✓
├── Decision 2: 四字段摘要替换现四段式 ── 确认 ✓（需同步改测试）
├── Decision 3: 两级层级压缩 ── ⚠️ 原 tasks 无 L2 任务 → 补进子 change ①
├── Decision 4: Prefix Cache 注入顺序 + 稳定层/可变层 ── ⚠️ 需按 wire 顺序改写
├── 子 change ①
│   ├── 1.1 增量 token 计数 ── ⚠️ id()-keyed cache 不安全 → 改 Message._tokens
│   ├── 1.2 ContextBuilder 静态源缓存 ── ⚠️ P2 非静态 → 排除或 content-hash 键
│   ├── 1.3 四字段摘要模板 ── 确认 ✓（改 summarize+merge 模板）
│   ├── 1.4 tool_call 成对 + pending 标记 ── ⚠️ 绑定 tool_call_id，manager 预扫
│   └── 1.5 L2 层级压缩 + tier 元数据 ── 新增任务（原 tasks 缺失）
├── 子 change ②
│   ├── 2.1 注入顺序 ── ⚠️ 按 wire 顺序重述（system→tools→messages）
│   ├── 2.2 工具 schema 确定性排序 ── 确认 ✓（注册序稳定；selector 时 stable 前置）
│   ├── 2.3 cache_control 断点 ── ⚠️ 按模式单断点；provider 兼容 fallback
│   ├── 2.4 openai_llm 对齐 ── 确认 ✓（不发送 cache_control，接受并忽略 CachePlan）
│   └── 2.5 稳定层/可变层 wiring ── ⚠️ set_stable_tools 从未被调用 → 补 wiring + 测试
└── 子 change ③
    ├── 3.1 ReadTool offset/分页 ── ⚠️ 仅显式 offset 时输出注记；定死格式
    ├── 3.2 压缩前进度写入摘要 ── ⚠️ 扫 tool-result 内容取 (file,offset,total)
    ├── 3.3 深层 MD 按需加载 tool ── ⚠️ 命名 ReadDoc（PascalCase）+ 工厂注册
    └── 3.4 单元测试 ── 确认 ✓
```

## 逐项裁定

### Q1（spec 顺序字面不可达）：注入顺序 "system → MD → 工具 → 记忆索引 → 用户消息"

- **事实**：Anthropic payload 顶层字段顺序是 `system` → `tools` → `messages`（`anthropic_llm.py:138-141`）；MemoryIndex 是 P2 system block（`sources.py:274-300`）。字面顺序 "工具在记忆索引之前" 在 wire 上不可实现，除非把 P2 移出 system（会破坏其可缓存性）。MODIFIED stable-prefix layering 要求与 P2 留在缓存 system 区域兼容。
- **推荐答案**：保留 P2 在缓存 system 区域。把 spec 的 ADDED scenario Then 子句改为 wire 顺序：**system（prompt → MD → memory index）→ tools（core stable → 选中 variable tail）→ user messages**，并注明记忆索引相对工具的位置由 provider wire 格式决定（system 字段先于 tools 字段）。此解释写入 proposal/design 和 spec-sync 步骤。
- **需用户确认**：是。

### Q2（L2 层级压缩无任务覆盖）：原 tasks.md 三个子 change 均无 L2 任务

- **事实**：proposal/design Decision 3 声明两级压缩，spec requirement 3 要求 tier 元数据（tier/source range/generation time）；`MemoryManager._running_summary` 是单层 str。
- **推荐答案**：在子 change ① 内实现 L1→L2 + tier 元数据：`_running_summary` 改为层级结构（L1 列表 + 可选 L2 结论），L2 触发条件（累积 L1 token/数量超阈值），L2 压缩复用 `merge()` 并加 "只保留最高层结论" 提示。保持 90%→20-30% 压缩比量化主张。
- **需用户确认**：是。

### Q3（双断点不可兼得）：P2 system 断点 + 末核心工具断点

- **事实**：Anthropic 渲染顺序 tools → system → messages，P2 断点缓存的是 tools+system 整体。selector 开启时 variable tail 每轮变化且位于 P2 段内 → P2 每轮 miss。
- **推荐答案**：按模式单断点策略：
  - **selector OFF（默认）**：只放 P2 system 断点，去掉工具断点（全量 tools 数组字节稳定，P2 同时缓存 tools+system）。
  - **selector ON**：只在最后一个核心工具放 cache_control，省略 P2 断点（变长 tail 会使 P2 失效）。
  - 任何情况下不宣称两个缓存同时命中。写入 design.md Decision 4 和 task 2.3。
- **需用户确认**：是。

### Q4（稳定前缀字节一致性被预算截断破坏）

- **事实**：`_apply_budget` 按最低优先级先截断非 critical 层（`builder.py:85-119`）；P2 MemoryIndex `critical=False`（`sources.py:282`），预算压力下 P2 尾部会被裁 → 每轮字节不同 → 缓存 miss。
- **推荐答案**：冻结 P0/P1/P2 于预算 pass 之外：以完整未截断尺寸渲染缓存 P0/P1/P2（约 6.5K token 预算），token 预算只作用于 P4/P5；截断时整块丢弃而非裁剪 P0-P2；`_join_layers` 分隔符不得泄漏进冻结前缀。加回归测试：P0-P2 跨轮跨预算字节一致。
- **需用户确认**：是（保守方案）。

### Q5（P2 静态源缓存陈旧）

- **事实**：`PersistentMemory.save()` 中途会重写 MEMORY.md（`persistent.py:99-130`）；`sources.py:277` 注释声称 P2 "static per session" 是错的。
- **推荐答案**：把 P2 排除出静态源缓存（按动态源处理），或缓存键加入 `load_index()` content-hash / PersistentMemory 写版本号。P0/P1 不可变，其 `(name, cwd, mode, user_system_prompt)` 键有效。加测试：`build → save memory → build again` 新索引出现。
- **需用户确认**：是。

### Q6（稳定标记机制未定）

- **推荐答案**：`TextBlock` 增加 `cache: bool = False` 字段（`to_dict/from_dict` 序列化，resume 可往返）；ContextBuilder 输出 P0-P5 各自独立 TextBlock，P0/P1/P2 标 `cache=True`；`_build_payload` 通过 `CachePlan(stable_system_block_count, stable_tool_count)` 在最后一个稳定 system block / 最后一个核心工具上加 `{"type":"cache_control"}`。核心工具集：Read/Edit/Write/Bash/Glob/Grep/InspectGitDiff。`_select_tool_schemas` 在 selector 存在时调用 `set_stable_tools(core_names)`。
- **需用户确认**：是。

### Q7（token 计数缓存安全）

- **事实**：`id(msg)`-keyed 缓存有 id 复用陈旧命中危险；Message 是可变 dataclass。
- **推荐答案**：token 计数存为 Message 上的非序列化字段 `_tokens: int | None = None`（惰性计算，`to_dict` 不序列化）；`compact()`/`clear()`/resume 重载时对新建消息重算。加测试：二次计数全命中、新增消息计一次、compact 后重算、id 复用不返回陈旧值。
- **需用户确认**：是。

### Q8（pending 标记语义）

- **推荐答案**：绑定 `tool_call_id`：`[call#<i>: <tool_call_id> pending]`（i 为该 assistant 消息内 1-based 序号）。标注在 MemoryManager 预扫中完成（`summarize()` 调用前），LLM 与 Truncation 降级路径均可见。模板加显式成对保留指令：`preserve each tool_call as call#n: name(args) -> result`。
- **需用户确认**：是。

### Q9（ReadTool 分页注记）

- **推荐答案**：仅当显式传入 `offset` 时输出单行机器可解析注记 `\n\n[ReadProgress file="<rel>"; offset=<n>; total=<m>]`；现有 path+limit 行为字节兼容（`test_read_file == "hello world"` 保持通过）。offset 0-based 作用于 `splitlines()`；offset>total → 空内容+注记；offset 无 limit → 读到 EOF；图片文件忽略 offset。
- **需用户确认**：是。

### Q10（ReadDoc 工具契约）

- **推荐答案**：命名 `ReadDoc`（PascalCase）；`.md` only，限制在 docs/ 树（或显式 allowlist），32K 字节上限（复用 `MAX_ASTER_SIZE_BYTES` 模式），workspace-policy 走 `assert_read_allowed`；加入 `KNOWN_BUILTIN_TOOL_NAMES` 与两个工具工厂列表。
- **需用户确认**：是。

### Q11（benchmark 量化契约）

- **事实**：tasks 4.4/8.2 要求 cache 命中率/压缩比量化，但 `--agent fake` smoke 不产生真实 cache 指标，Usage 只有 input/output tokens。
- **推荐答案**：在 tasks.md 明确指标契约：(a) 真实 API benchmark 解析 `cache_creation/cache_read_input_tokens` 进 Usage+report；或 (b) 代理指标——稳定前缀字节一致率 + cache_control 断点计数（pytest benchmark task 测量）+ 压缩比（compact 前后 middle token 数）。注明 tiktoken 对 Claude 低估 ~15-20%。
- **需用户确认**：是。

### Q12（ContextBuilder 返回类型兼容）

- **事实**：`build()` 返回 str，被大量测试断言消费（`test_builder.py`、`test_sources.py`、`test_loop.py`）。
- **推荐答案**：**保持 `build()` 返回 joined str**；新增独立 `build_blocks()/render_layers()` API 返回 `list[TextBlock]`，loop 走新 API。不静默破坏公共契约。
- **需用户确认**：是（保守方案）。

## 已确认（无需改动）

- Decision 1（拆 3 子 change）正确。
- Decision 2（四字段模板替换）正确，仅测试需同步更新。
- Provider 隔离正确：OpenAI 自动缓存前缀，绝不能收到 cache_control；`openai_llm.chat` 接受并忽略 CachePlan。需回归测试断言 OpenAI payload 无 cache_control。
- 消息层变动安全：活动轮次与 compaction running-summary user 消息位于 system/tools 断点之后，只使 Messages 层缓存失效。
- pending 检测边界安全：`_recent_with_tool_chains` 会把结果在 recent 窗口的 assistant 调用回扩进 recent，middle 中不存在"结果在 recent"的悬空调用；middle+recent 扫描是 defense-in-depth。真正 pending 只出现在异常/抢占中断，回归测试应模拟"异常中断的对话"而非解析错误。
- ReadDoc workspace 安全复用 `assert_read_allowed`（路径穿越/符号链接处理）正确，无需改权限 profile。

## 需要落进 change 文档的修正

1. `specs/context-engineering/spec.md`：ADDED Prefix Cache Ordering scenario 的 Then 子句改为 wire 顺序，注明 P2 相对工具位置由 provider 决定。
2. `design.md`：Decision 4 重述为 wire 顺序 + 按模式单断点策略；Pre-Implementation Review 填本文件结论；Reference Implementation Research 补 findings。
3. `tasks.md`：子 change ① 增加 L2 压缩任务；4.4 注明 benchmark 指标契约；补 resume pending 链 e2e 测试任务。

## 测试策略（经审阅面板强化）

- 单元：四字段模板（prompt 断言 4 个新标题、旧标题缺失）、pending 标注（fake summarizer 记录 prompt 断言 `[call#i: id pending]`）、增量计数（counting fake encoder：二次计数零次调用、新消息计一次、compact 后重算、id 复用）、静态源缓存（同 ctx 两次 build P0/P1 字节一致；save memory 后 P2 失效）、ReadDoc、Read offset、build_blocks。
- 集成（AgentLoop）：稳定前缀跨迭代字节一致；`cache_control` 只在最后一个稳定 system block / 末核心工具；`set_stable_tools` 被 loop 以核心工具集调用；resume 后 pending 链存活。
- 回归：`test_summarizer.py` 旧标题断言更新；`test_builder.py`/`test_sources.py`/`test_loop.py` 字符串消费点确认不破（`build()` 保持 str）。
- benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`（coding-agent core change 要求）。

## 证据

- Workflow run `wf_09df918b-aec`（5 agents，510K tokens），findings 完整清单见 session transcript；本文件为裁剪后的最终裁定。
- 代码事实 `file:line` 已嵌入各裁定条目。
