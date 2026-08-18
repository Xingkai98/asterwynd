# Bullet 代码走读合集（1-7）

> 七条简历 bullet 的代码级走读合集。每条包含核心模块拆解、关键代码位置（文件:行号）与设计取舍，全部经合并 master 后的当前代码核实。
> 简历原文见 [resume-bullets.md](./resume-bullets.md)。面试讲稿见 [interview-prep.md](./interview-prep.md)。

- **Bullet 1** · AgentLoop 核心循环
- **Bullet 2** · 动态工具编排
- **Bullet 3** · 多 Agent 编排模式
- **Bullet 4** · ContextBuilder 上下文系统
- **Bullet 5** · 长期记忆系统
- **Bullet 6** · 3 层纵深防御安全体系
- **Bullet 7** · 全链路可观测体系与 Benchmark 评测闭环


---

## Bullet 1: AgentLoop 核心循环 — 代码走读

> 简历原文：实现可扩展 AgentLoop 核心循环（message-driven + 快照断点续传），以 7 切面 Hook 协议解耦迭代/LLM 调用/工具执行/错误处理/完成阶段，同构适配 OpenAI / Anthropic 双 Provider，集成 38 个内置工具

---

### 1. 核心循环 — message-driven 迭代引擎

**文件**：`agent/loop.py`

主类 `AgentLoop`（line 112），入口 `run()` → `_run()`（line 544）。核心是一个 for 循环：

```python
for iteration in range(start_iteration, self.max_iterations):  # loop.py:610
```

单次迭代的完整流程：

```
① _select_tool_schemas()  — 从 38 工具中 Top-K 选 schema 注入 LLM    (:627)
② _messages_with_run_context() — 拼接 context block (ContextBuilder)   (:629)
③ hooks.before_iteration()     — Hook 切面                            (:630)
④ _call_llm()                  — 调 LLM，返回 LLMResponse              (:631)
⑤ hooks.after_llm_call()      — Hook 切面                             (:636)
⑥ 无 tool_call → 判断是否 max_tokens 截断                               (:678-683)
   - 截断 → 续接消息 "Please continue..."，下一轮继续
   - 非截断 → end_turn，结束
⑦ 有 tool_call → 追加 assistant 消息到 messages                        (:715)
⑧ Phase 1：解析 arguments + 权限审批 + 模式策略判定                     (:719-855)
⑨ Phase 2: _execute_tool_calls() 并行/串行执行                          (:858)
⑩ Phase 3: 结果回填 messages + hook after_tool_execute                  (:861-951)
⑪ memory.compact_if_needed() 上下文压缩                                (:952)
```

"message-driven" 的含义：所有状态在 `messages: list[Message]` 中流转，没有外部状态机。messages 数组就是 Agent 的"记忆"。

#### Phase 1: JSON 解析 + 权限审批（:719-855）

```python
for delta in response.tool_calls:
    try:
        arguments = self._parse_arguments(delta.arguments)  # json.loads
    except ValueError:
        # JSON 解析失败 → 不重试，直接作为 error 回传 messages
        # 让模型在下一轮看到错误后自己修正
        result = f"[Error: {e}]"
        messages.append(tool_result_message(tool_call.id, result))
        continue

    # 未知工具 → pre_denied
    tool = self.tool_registry.get_tool(tool_call.name)  # KeyError → pre_denied

    # 模式策略判定 → 是否需要审批
    decision = self.tool_registry.mode_policy.decide_tool(tool)

    if decision.requires_approval:
        approval_response = await self.approval_handler.request_approval(...)
        if 被拒: pre_denied_result = "[Approval denied: ...]"
        if 不可用: pre_denied_result = "[Approval unavailable: ...]"
```

**关键**：JSON 解析失败**不重试**，直接作为 error 回传让模型自我修正。这与工具执行重试是不同的机制。

#### 工具执行重试：RetryHook（`agent/hooks/builtin/retry.py`）

```python
class RetryHook:
    max_retries = 3      # 最多重试 3 次
    base_delay = 1.0     # 指数退避：1s → 2s → 4s

    async def execute_with_retry(self, tool_call, execute_fn):
        for attempt in range(self.max_retries + 1):  # 1 原始 + 3 重试
            try:
                return await execute_fn(tool_call)
            except Exception as e:
                if not _is_retryable(str(e)):  # 非可重试错误，直接返回
                    return ToolResult(text=f"[Error: {e}]")
                # 可重试：timeout / connection / rate limit / 429 / 503
                await asyncio.sleep(self.base_delay * (2 ** attempt))
```

**注意**：RetryHook 只在非 Bash 工具上生效（Bash 可能有副作用，异常直接转 error，不重试）。

#### Phase 2: 并行/串行分组逻辑（:1225-1295）

```python
# 贪心分组：连续的可并行工具 → 同一组，不可并行的 → 单独一组
for item in items:
    is_parallel = (
        tool.parallelizable      # 工具声明可并行
        and not pre_denied       # 没被预拒绝
        and not requires_approval  # 不需要人工审批
    )
    if is_parallel:
        current_group.append(item)   # 加入当前并行组
    else:
        flush current_group          # 先执行当前并行组
        groups.append([item])        # 该工具单独串行组

# 执行：多元素组 → asyncio.gather 并行；单元素组 → 串行
for group in groups:
    if len(group) > 1:
        await asyncio.gather(*[_run_one(item) for item in group])
    else:
        serial execution
```

举例：`[Read, Edit, Bash, Grep]`，Read/Grep parallelizable，Edit/Bash 不可并行 → 分组为 `[[Read], [Edit], [Bash], [Grep]]`。

---

### 2. 快照断点续传

#### 数据结构：SessionSnapshot（`agent/session.py:16`）

```python
@dataclass
class SessionSnapshot:
    messages: list[Message]       # 完整对话历史 ← 核心
    mode: AgentMode               # 当前模式
    todos: list[PlanItem]         # 待办事项
    active_skills: list[str]      # 激活的 skills
    run_id: str
    iteration: int
    user_system_prompt: str
    runtime_fingerprint: dict     # 运行时指纹（跨环境续传告警）
    # 子 agent 扩展：
    objective: str
    blockers: list[str]
    next_steps: list[str]
    bus_summary: str              # 编排消息总线摘要
```

#### 持久化：SessionStore（`:88`）

```python
class SessionStore:
    def save(self, snapshot):
        # 1. SHA-256 去重：内容无变化则跳过写入
        if self._last_hash[snapshot.session_id] == new_hash:
            return False
        # 2. 原子写入：先写 tmp 文件，再 rename（防止写入中断损坏）
        self._write(snapshot.session_id, snapshot_dict, snapshot.messages)
```

**保存触发**：`run()` 的 `finally` 块（`:530-534`）→ 无论成功/异常/中断，保底落盘。

#### 恢复路径（`loop.py:561-588`）

```python
if resume_snapshot is not None:
    # ① 保留当前 system 消息不变
    # ② 恢复 mode / todos / skills / user_system_prompt
    # ③ 重建 messages:
    #    messages = 当前 system + 快照对话 + "[Session resumed. ...]" + 新用户输入
    # ④ 从头迭代
```

#### 恢复是 transcript 级，非 call-stack 级

如果中断时恰好在工具执行中（assistant tool_call 消息已写入但 tool_result 未写回），续传后：
- 对话历史中 tool_call 缺少对应的 tool_result（消息链不完整）
- **没有代码逻辑自动重新执行未完成的 tool_call**
- 模型会在下一轮看到不完整的工具链，自然地做出反应（"上次工具没结果，需要重新执行"）
- `subagent/manager.py:256-258` 注释明确：**"resume is transcript-level, not stack-level"**

---

### 3. 7 切面 Hook 协议

**协议定义**（`agent/hooks/manager.py:14-27`）：

```python
class Hook(Protocol):
    async def on_run_started(self, run_config) -> None: ...           # ①
    async def before_iteration(self, iteration, messages) -> None: ... # ②
    async def after_llm_call(self, response) -> None: ...             # ③
    async def before_tool_execute(self, tool_call) -> None: ...       # ④
    async def after_tool_execute(self, tool_call, result, error_type) -> None: ... # ⑤
    async def on_error(self, error) -> None: ...                      # ⑥
    async def on_completion(self, result) -> None: ...                # ⑦
```

**接线位置**（`loop.py`）：

| Hook | 接线点 | 说明 |
|------|--------|------|
| `on_run_started` | `:601` | 仅在非 resume 路径触发 |
| `before_iteration` | `:630` | 每轮迭代前，传入 contextualized messages |
| `after_llm_call` | `:636` | LLM 返回后，可读 response.usage |
| `before_tool_execute` | `:1192` | 工具执行前 |
| `after_tool_execute` | `:1222` | 工具执行后，带 error_type |
| `on_error` | `:725, :1202, :1206` | JSON 解析失败 / Bash 超时 / 其他异常 |
| `on_completion` | `:686, :984` | end_turn 和 max_iterations 两个出口 |

**内置 Hook**（`agent/hooks/builtin/`）：

| Hook | 功能 |
|------|------|
| `LoggingHook` | 日志记录 |
| `TracingHook` | trace 打点 |
| `RetryHook` | 工具调用重试（max 3 次，指数退避） |
| `TokenBudgetHook` | token 预算监控 |

`HookManager`（`:29`）遍历所有 hook 独立执行，互不影响。

---

### 4. OpenAI / Anthropic 双 Provider

#### 统一接口（`agent/llm.py:35`）

```python
class LLM(Protocol):
    async def chat(messages: list[Message], tools: list[dict] | None, model: str) -> LLMResponse: ...
```

#### 两个实现

| 实现 | 文件 | API | 特点 |
|------|------|-----|------|
| `OpenAILLM` | `openai_llm.py:15` | Chat Completions | auto-caching，不打 cache_control |
| `AnthropicLLM` | `anthropic_llm.py:26` | Messages API | `supports_cache_control = True` |

#### 关键差异：Cache Plan

- `AnthropicLLM.supports_cache_control = True` — 只有 Anthropic 路径打 `cache_control: {"type": "ephemeral"}` 断点
- `_apply_cache_plan()`（`loop.py:1097`）在每次 LLM 调用前检查 `supports_cache_control`，决定是否打断点
- OpenAI 走服务端 auto-caching，不需要手动放断点

#### AnthropicLLM 三层降级（`:56-97`）

1. 正常调用
2. 400 + cache_control → **去掉 cache_control 重试**（DeepSeek-anthropic 等兼容端点可能拒绝）
3. 400 + vision → **去掉图像重试**

#### Provider 分发（`agent/main.py:build_llm()`）

```python
if provider == "anthropic":
    return AnthropicLLM(...)
else:
    return OpenAILLM(...)  # 默认
```

---

### 5. 38 个内置工具

**权威清单**：`KNOWN_BUILTIN_TOOL_NAMES`（`agent/tools/factory.py:71-110`）= 恰好 38 个。

| 类别 | 工具 | 数量 |
|------|------|------|
| 文件读写 | Read, Write, Edit, Bash, Grep, Find, ListFiles, InspectGitDiff | 8 |
| Web 获取 | WebFetch, WebSearch, WebNavigate, WebGetContent, WebScreenshot, WebScroll, WebListTabs, WebSwitchTab, WebCloseTab | 9 |
| LSP 代码理解 | LspDefinition, LspReferences, LspHover, LspDocumentSymbols, LspWorkspaceSymbols, LspDiagnostics | 6 |
| 代码智能 | RepoMap, SymbolSearch | 2 |
| 长期记忆 | SaveMemory, RecallMemory, SearchMemory, ResolveMemoryConflict, MemoryGitBackend | 5 |
| 计划/任务 | ExitPlanMode, UpdatePlan, TaskOutput, TaskStop, TodoWrite | 5 |
| 其他 | AskUserQuestion, ReadDoc, ActivateSkill | 3 |

**注意**：38 是 `KNOWN_BUILTIN_TOOL_NAMES` 的数量。实际运行时还有 10 个子 agent 工具（CreateSubagent, RunSubagent, ListSubagents 等）按需动态注册 + MCP 工具动态注入，所以运行时全量可以到 40+，但核心内置集合是 38。

---

### 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/loop.py` | AgentLoop 主类、迭代循环、工具执行全流程 |
| `agent/session.py` | SessionSnapshot + SessionStore 断点续传 |
| `agent/hooks/manager.py` | Hook Protocol + HookManager |
| `agent/hooks/builtin/retry.py` | RetryHook 工具重试 |
| `agent/llm.py` | LLM Protocol + BaseLLM + LLMResponse |
| `agent/openai_llm.py` | OpenAILLM 实现 |
| `agent/anthropic_llm.py` | AnthropicLLM 实现 + cache_control + 三层降级 |
| `agent/tools/factory.py` | KNOWN_BUILTIN_TOOL_NAMES (38 个) |

---

## Bullet 2: 动态工具编排 — 代码走读

> 简历原文：实现动态工具编排：BM25 粗筛 + 向量精排两阶段按对话上下文 Top-K 注入工具 schema，核心工具稳定层常驻且不占 Top-K 预算、配合 cache_control 断点保 LLM Prefix Cache 命中，工具语义去重 + 质量评分驱动软降级

---

### 整体架构

4 个机制都在 `agent/tools/governance/` 目录，由 `ToolRegistry`（`registry.py`）统一编排。调用入口在 `agent/loop.py:999` `_select_tool_schemas()`，每次迭代前触发。

```
每次迭代前 (_select_tool_schemas):
┌──────────────┐
│ 38 个工具全量  │
└──────┬───────┘
       │ 分离
  ┌────┴────┐
  │ 稳定层 7 │────────────── 始终注入，排最前，不参与任何筛选
  └─────────┘
       │ 其余 ~30
  ┌────┴────┐
  │ 质量过滤  │────────── 低分工具从变层候选剔除（软降级）
  └────┬────┘
       │
  ┌────┴────┐
  │ BM25粗筛 │────────── 取 top 50（当前 ~30 工具，实际未筛选，仅排序）
  └────┬────┘
       │
  ┌────┴────┐
  │向量精排  │────────── cosine → top 5
  └────┬────┘
       │
  稳定层(7) + 变层(5) = 最终注入 LLM 的 ~12 个 tool schema
       │
  ┌────┴────┐
  │cache断点 │────────── 打在最后一个稳定工具上（Anthropic 专属）
  └─────────┘
```

**重要前提**：整个动态选择 + 质量评分功能**默认关闭**（`config.py:89,104`：`enabled: bool = False`）。开启方式是 `asterwynd.yaml` 中 `tools.selection.enabled: true` 和 `tools.quality.enabled: true`。关闭时走 `get_all_schemas()` 全量注入。

---

### 机制 1: BM25 粗筛 + 向量精排两阶段检索

**文件**：`agent/tools/governance/selector.py`

核心类 `ToolSelector`（line 22）：

```python
class ToolSelector:
    def __init__(self, embedder, top_k=5, coarse_k=50, latency_budget_ms=50.0):
        ...
```

#### 调用触发

`agent/loop.py:1008-1029`，每次迭代构造 query：

```python
# query = 最新一条 user 消息 + 最多 3 个最近的工具调用名
query = "用户问题 recently used: Read, Edit, Bash"
return self.tool_registry.select_schemas(query, k=5)
```

#### 两阶段流程（`_select_impl`, line 81）

```
Stage 1: BM25 粗筛
  对所有非稳定工具 description 做 BM25 打分（k=1.5, b=0.75）
  → 取 top coarse_k=50

Stage 2: 向量精排
  对 query 做 embedding → 与候选工具向量 cosine 比较
  → 取 top top_k=5
```

**当前局限性**：38 工具 - 7 稳定层 = ~30 候选，`coarse_k=50` 意味着 BM25 阶段不做筛选，仅排序。这是**前瞻性设计**——为工具数量增长到 100+（大量 MCP 工具接入）预留的。

#### Embedding 后端

**文件**：`agent/embedding/provider.py`

默认 `NGramEmbedding`（line 42）：**字符 n-gram MD5 哈希向量**（256 维），零外部依赖。**不是神经网络的语义 embedding**。

通过 `EmbeddingProvider` Protocol（line 26）可插拔换成 sentence-transformers 等真实模型，不需要改任何 governance 代码：

```python
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> Vector: ...
    def cosine(self, a: Vector, b: Vector) -> float: ...
```

---

### 机制 2: 核心工具稳定层 + Prefix Cache

#### 稳定工具集

**文件**：`agent/loop.py:85-87`

```python
CORE_STABLE_TOOL_NAMES = (
    "Read", "Edit", "Write", "Bash", "Glob", "Grep", "InspectGitDiff",
)
```

这 7 个工具被视为"任何 coding 任务都需要的核心工具"，schema 字节级确定。

#### 在 ToolSelector 中的行为

`selector.py:86, :104-108`：

```python
# ① 稳定层永远排最前，按注册顺序固定
stable_names = [n for n in self._names if n in self._stable]

# ② 不参与 BM25 排序（从候选池排除）
# ③ 变层 Top-K 追加在稳定层后，不占 top_k 配额
tail = [name for name, _ in ranked[: self._top_k]]
return stable_names + tail
```

不管什么任务，Read/Edit/Write/Bash/Glob/Grep/InspectGitDiff 永远在工具列表最前面且位置不变。

#### cache_control 断点

**文件**：`agent/loop.py:1116-1163` + `agent/anthropic_llm.py:167-194`

| Selector 状态 | 断点策略 | 缓存范围 |
|:---|:---|:---|
| **OFF**（默认） | 最后一个 cacheable system block | system + tools 整体缓存 |
| **ON** | **最后一个核心稳定工具** | system + 稳定工具前缀缓存，变层不缓存 |

```python
# loop.py:1146-1163
selector = getattr(self.tool_registry, "_selector", None)
if selector is None:
    return CachePlan(stable_system_block_count=N, stable_tool_count=0)
else:
    # selector ON：稳定工具是连续前缀 → 在最后一个稳定工具上打断点
    stable_tool_count = 0
    for tool in tools:
        if tool.name in stable_names:
            stable_tool_count += 1
        else:
            break  # 遇到第一个非稳定工具立即停止
    return CachePlan(stable_system_block_count=0, stable_tool_count=stable_tool_count)
```

**重要**：`cache_control` 断点**仅 Anthropic 路径生效**（`loop.py:1108`）：

```python
if not getattr(self.llm, "supports_cache_control", False):
    return  # OpenAI 服务端 auto-caching，不需要手动打断点
```

Anthropic 的 `_apply_cache_plan`（`:167-194`）把 `cache_control: {"type": "ephemeral"}` 打到对应 block，一轮对话中稳定前缀不变时，KV cache 不重复计算。

---

### 机制 3: 工具语义去重

**文件**：`agent/tools/governance/dedup.py`

核心类 `SemanticDeduper`（line 20）：

```python
class SemanticDeduper:
    def add(self, tool_name, description):
        vector = self._embedder.embed(description)
        for other in self._descriptions:
            sim = self._embedder.cosine(vector, self._vectors[other])
            if sim > self._threshold:  # 默认 0.7
                self._duplicate_of[tool_name] = other  # 标记为重复
                break
```

注册期触发（`registry.py:81-83`）：每个新工具注册时与已注册工具两两 cosine 比较，超过阈值 → 标记 `duplicate_of`。

**这是软标记，不是硬约束**：被标记的工具依然可以注册、调用、出现在 schema 中。标记存为旁路元数据，不注入官方 tool schema。

**注意**：`difference_explanation()`（line 48-61，给模型注入差异说明的软提示）目前**没有任何运行时路径调用**。去重检测是真实做的，但"给模型看差异说明"这条没接线。

---

### 机制 4: 质量评分驱动软降级

**文件**：`agent/tools/governance/quality.py`

核心类 `ToolQualityStore`（line 18）：

#### 评分公式

```python
score = 0.5 × success_rate + 0.3 × duration_factor + 0.2 × approval_rate

# duration_factor = 1.0 - avg_duration / 30000  （越快分越高）
# approval_rate：无审批信号时权重重归一为 0.5×成功 + 0.3×耗时
```

滑动窗口 50 个调用，最少 5 个样本才产出评分。

#### 降级行为

`registry.py:114`：

```python
if self._is_quality_degraded(name) and not self._selector.is_stable(name):
    continue  # 从变层候选排除
```

- 阈值 < 0.4 → 软降级
- 稳定层工具**不受降级影响**
- 权限模型**不动**（`get_all_schemas()` 仍可见，模型仍可手动调用）
- 不是禁用，是软移除变层候选

#### 公式的已知问题

经代码走读 + 业界调研发现三个问题（已提 issue #120）：

| 问题 | 说明 |
|------|------|
| `duration_factor` 不应作为质量信号 | "快=好"不成立（`git clone` 比 `ls` 慢不代表质量差）。业界无人用耗时做质量评分 |
| `approval_rate` 是策略偏好，不应混入质量 | 审批率高只说明人允许用了。审批是安全控制面，应是独立信号 |
| 缺少核心信号 | 业界标准：Tool Selection Accuracy（选对工具了吗）、Invalid Tool Rate（幻觉出新工具）、Error Type Classification（区分错误类型） |

**不影响简历表述**——"质量评分驱动软降级"属实，公式最优性是后续优化方向。

---

### 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/tools/governance/selector.py` | ToolSelector：BM25 + embedding 两阶段选择 |
| `agent/tools/governance/dedup.py` | SemanticDeduper：注册期语义去重 |
| `agent/tools/governance/quality.py` | ToolQualityStore：滑动窗口质量评分 + 软降级 |
| `agent/tools/registry.py` | ToolRegistry：统一编排 governance 组件 |
| `agent/embedding/provider.py` | EmbeddingProvider Protocol + NGramEmbedding 默认实现 |
| `agent/config.py` | ToolSelectionConfig / QualityConfig（默认关闭） |
| `agent/loop.py:85-87` | CORE_STABLE_TOOL_NAMES |
| `agent/loop.py:999-1029` | _select_tool_schemas() 注入点 |
| `agent/loop.py:1097-1163` | _apply_cache_plan / _compute_cache_plan |
| `agent/anthropic_llm.py:167-194` | AnthropicLLM._apply_cache_plan 实际打断点 |

---

## Bullet 3: 多 Agent 编排模式 — 代码走读

> 简历原文：内置 4 种多 Agent 编排模式（orchestrator-worker / peer-review / hierarchical / bidding）+ 子 agent 消息总线、token/时间双维度预算硬 kill 与快照恢复

---

### 整体架构

多 Agent 能力域由 4 个模块构成，全部在 `agent/subagent/` 目录：

```
agent/subagent/
├── patterns.py       ← 4 种编排模式 + PATTERNS 注册表 + run_pattern 入口
├── bus.py            ← MessageBus：语义摘要交换 + 三层 token 预算
├── budget.py         ← BudgetTracker/Hook：token/时间双维度硬 kill
├── snapshot.py       ← SubagentSnapshotStore：快照持久化 + 恢复
├── manager.py        ← SubAgentManager：子 agent 全生命周期管理
├── context.py        ← ContextVar：spawn_depth / bus 上下文传递
├── protocol.py       ← ParentChannel：父子 agent 结果回传通道
└── parent_channel_hook.py ← ParentChannelHook：结果注入父 agent 消息

agent/tools/builtin/
└── subagents.py      ← 10 个 LLM 可见子 agent 工具
```

控制平面完全复用 `SubAgentManager`，不引入单独的 orchestration control plane（见 spec `scenario: orchestration-state-persists-without-dev-workflow-coupling`）。编排由 LLM 通过 `RunPattern` 工具（`subagents.py:320-354`）触发，模式内部执行确定性骨架（spawn N → wait → collect）。

---

### 1. 4 种多 Agent 编排模式

**文件**：`agent/subagent/patterns.py`

#### 1.0 注册表：确认恰好 4 种模式

```python
# patterns.py:203-208
PATTERNS: dict[str, type[OrcPattern]] = {
    "orchestrator-worker": OrchestratorWorkerPattern,
    "peer-review": PeerReviewPattern,
    "hierarchical": HierarchicalPattern,
    "bidding": BiddingPattern,
}
```

`RunPattern` 工具（`subagents.py:328-329`）的 `pattern` 参数 `enum` 恰含此 4 个值，与 `PATTERNS` 一一对应。调用路径：

```
LLM 调 RunPattern 工具
  → RunPatternTool.execute()                  (:347-354)
    → run_pattern(manager, pattern, task, params) (:211-235)
      → 创建 MessageBus + set_bus contextvar    (:227-228)
      → PATTERNS[pattern](...).run()            (:230-231)
      → 结果附 bus.snapshot_payload()           (:232)
      → reset_bus                               (:235)
```

#### 1.1 Orchestrator-Worker（`:100-111`）

**模式**：coordinator（即调用 agent）fan-out 到 N 个 parallel worker，所有 worker 执行相同 task，互不通信，最后 aggregate。

```python
class OrchestratorWorkerPattern(OrcPattern):
    name = "orchestrator-worker"

    async def run(self) -> dict:
        worker_count = max(1, int(self.params.get("workers", 3)))       # :104
        worker_ids = [
            self._spawn(f"worker-{i}", "parallel worker")
            for i in range(worker_count)
        ]                                                              # :105-107
        results = await asyncio.gather(
            *[self._run_worker(wid, self.task) for wid in worker_ids]  # :108-110
        )
        return self._aggregate(list(results))
```

**关键参数**（`:104`）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `workers` | 3 | 并行 worker 数，`max(1, ...)` 保底至少 1 个 |
| `worker_max_tokens` | None | 透传给 `_run_worker`（`:69`），覆盖每个 worker 的 token 预算 |
| `worker_max_time_s` | None | 透传给 `_run_worker`（`:70`），覆盖每个 worker 的时间预算 |

Worker 之间不通信（设计注释 line 12: "Workers do not talk to each other."）。

#### 1.2 Peer-Review（`:114-149`）

**模式**：一个 producer 产出 proposal，一个 reviewer 评审；送代至 reviewer 回复 APPROVED 或达到 max_rounds。

```python
class PeerReviewPattern(OrcPattern):
    name = "peer-review"
    max_rounds = max(1, int(self.params.get("max_rounds", 3)))   # :118
```

**送代流程**（`:124-144`）：

```
for round in range(max_rounds):
    ① producer 执行 self.task
    ② 如果 producer 失败（status != "completed"）→ 立即返回
    ③ reviewer 收到："Review the following proposal. Reply with exactly one line
       starting with APPROVED if it is acceptable, or CRITIQUE followed by
       the specific issues if it needs revision.\n\nPROPOSAL:\n<summary>"
    ④ reviewer 回复以 "APPROVED" 开头 → 返回 producer + reviewer 的 aggregate
    ⑤ 否则：self.task 追加 "Address the reviewer's critique:\n<review>"，
       下一轮 producer 重新执行
```

**max_rounds 耗尽未批准**（`:147-149`）：返回最后一次真实的 producer + reviewer 结果（不丢信息）。

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_rounds` | 3 | 最多送代轮次 |

#### 1.3 Hierarchical（`:152-164`）

**模式**：N 个 manager 子 agent 各自执行 task，每个 manager 可以继续 spawn 自己的 worker（嵌套 spawn）。

```python
class HierarchicalPattern(OrcPattern):
    name = "hierarchical"
    team_count = max(1, int(self.params.get("teams", 2)))       # :156
```

嵌套 spawn 能力由 decision D4 启用（`manager.py:130-131, :143-155` 中的 `max_concurrent_runs` / `max_depth` guardrails 为此而设）。Manager 子 agent（subagent）在 loop 中通过 `CreateSubagent` + `RunSubagent` 工具递归创建孙子 agent，形成树状工作组。

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `teams` | 2 | 并行 manager 数 |

**嵌套深度上限**（`:722-726`）：`max_depth` 默认 3，即 root → child → grandchild 最深 3 层。`hierarchical` 模式中 manager 子 agent 本身占用一层 depth，所以在其下最多再 deep 2 层。

#### 1.4 Bidding（`:167-200`）

**模式**：N 个 proposer 独立产出方案 → 一个 selector 子 agent 读取 compact summary，选出最佳 proposal。

```python
class BiddingPattern(OrcPattern):
    name = "bidding"
    proposer_count = max(2, int(self.params.get("proposers", 3)))  # :171
```

**与 bus 的关系**（`:179-180` 注释）：

> "Selector input = compact proposal summaries (not the bus — drop-oldest could lose a key bid)"

bidding 的 proposal 传递**故意不走 MessageBus**，而是直接拼接到 selector 的 task prompt 中。原因是 bus 的 `drop-oldest` 丢旧策略可能丢弃关键 bid（bus 为限制爆炸设计，牺牲完整性保预算）。

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `proposers` | 3 | 独立 proposer 数，`max(2, ...)` 确保至少 2 个 |
| `worker_max_tokens` | None | 透传 token 预算 |
| `worker_max_time_s` | None | 透传时间预算 |

#### 1.5 共性基础设施

**基类 `OrcPattern`**（`:38-97`）：所有模式继承，提供：

| 方法 | 行号 | 功能 |
|------|------|------|
| `_spawn(name, description)` | `:59-62` | 调 `manager.create_subagent()` 创建子 agent session，返回 `subagent_id` |
| `_run_worker(subagent_id, task)` | `:64-71` | 调 `manager.run_subagent(wait=True)` 阻塞等待子 agent 完成 |
| `_aggregate(results)` | `:73-97` | 按统一格式汇总：`pattern / task / completed / failed / workers / summary` |

**统一 envelope 格式**（`:90-97`）：

```python
{
    "pattern": self.name,           # 模式名
    "task": self.task,              # 原始任务
    "completed": N,                 # 成功 worker 数
    "failed": N,                    # 失败 worker 数
    "workers": [...],               # 每个 worker 的 {subagent_id, status, summary, reason, usage}
    "summary": "\n".join(parts),    # 文本摘要
}
```

bidding 模式额外附 `"selected"` + `"selector"` 字段（`:194-199`）。

**并行执行**：所有模式的 worker 通过 `asyncio.gather` 并行执行（`:108, :161, :176`），而非串行。这是 "spawn N → wait → collect" 的确定性骨架。

---

### 2. 子 Agent 消息总线

**文件**：`agent/subagent/bus.py`

#### 2.1 设计定位

每个编排 run 创建一个 `MessageBus` 实例（`run_pattern()` 中 `:227`），通过 contextvar `_bus`（`context.py:25`）对所有 worker 可见。bus 只存活于 run 期间，不跨 run 持久化。交换的是**语义摘要**，从来不是原始 transcript。

#### 2.2 三层 Token 预算（`:12-16` 注释 + 代码实现）

##### Layer 1: Bounded Queue — 容量约束（`:53-64, :78`）

```python
class MessageBus:
    def __init__(self, *, max_messages: int = 100, ...):  # :57
        self.max_messages = max_messages
        self._messages: deque[BusMessage] = deque()

    def publish(self, ...):
        if len(self._messages) >= self.max_messages:       # :78
            self._messages.popleft()  # drop-oldest         # :79
```

- **默认上限**：100 条消息
- **溢出策略**：drop-oldest（丢弃最旧消息）
- **TTL 可选**（`:59`）：`ttl_s: float | None = None`，在 `read()` 中检查过期（`:112`），默认关闭

##### Layer 2: Publish-Side Summarization — 发布端压缩（`subagents.py:208-237`）

```python
# subagents.py:208
max_tokens = kwargs.get("max_tokens", 400)    # 默认每条约 400 token
summary = content
token_count = estimate_tokens(content)         # ~4 chars/token
if token_count > max_tokens:
    summary = await self._summarize(content, max_tokens)   # LLM 摘要
```

`_summarize()` 调 `LLMSummarizer` 做真正的摘要（`:222-237`），LLM 不可用时退化到 `content[:max_tokens * 4]` 截断。

##### Layer 3: Consume-Side Token Window — 消费端窗口（`bus.py:92-125`）

```python
def read(self, *, max_tokens: int | None = None, ...):
    budget = max_tokens if max_tokens is not None else self.max_read_tokens  # :105
    # 默认 max_read_tokens = 2000                                             # :58
    for msg in reversed(self._messages):  # 从最新开始                        # :109
        if used + msg.token_count > budget:
            if not collected:
                collected.append(msg)       # 单条超预算也保留最新一条         # :117-118
            break
        collected.append(msg)
        used += msg.token_count
    collected.reverse()  # 返回时 oldest-first                              # :124
```

**核心语义**（LangGraph `trim_messages` 风格）：
- 从最新消息开始往前累加，直到 token 预算耗尽
- 单条消息即使超过整个窗口，也保留最新一条（消费者不盲目于最新状态）
- 支持 `topics` 过滤、`limit` 截断、`ttl_s` 过期检查

#### 2.3 Bus 生命周期与上下文传递

```python
# patterns.py:227-235
async def run_pattern(...):
    bus = MessageBus()
    token = set_bus(bus)          # 注入 contextvar
    try:
        instance = PATTERNS[pattern](...)
        result = await instance.run()
        result["bus"] = bus.snapshot_payload()  # 快照 payload 附在结果
        return result
    finally:
        reset_bus(token)           # 清理 contextvar
```

**snapshot_payload**（`:135-139`）：包含 messages 列表 + `max_read_tokens`。这个 payload 可以被 recovery 路径注入到续传上下文（`snapshot.py:46-73` 中 `bus_summary` 字段）。

#### 2.4 LLM 可见工具

| 工具 | 文件:行号 | 功能 |
|------|-----------|------|
| `PublishBusMessage` | `subagents.py:181-237` | 发布摘要到 bus（sender/topic/content/max_tokens） |
| `ReadBus` | `subagents.py:240-280` | 消费 bus 摘要（topics/max_tokens/limit 过滤） |

这两个工具是子 agent 通过 bus 协作的唯一接口。所有消息经过 `PublishBusMessage` 的统一摘要压缩才进入 bus。

#### 2.5 数据结构

```python
# bus.py:33-40
@dataclass
class BusMessage:
    message_id: str           # uuid4().hex[:8]
    sender: str               # 发送者标识
    topic: str                # 主题标签
    summary: str              # 语义摘要内容
    token_count: int          # 估算 token 数（~4 chars/token）
    timestamp: float          # time.time()
```

---

### 3. Token/时间双维度预算硬 Kill

**文件**：`agent/subagent/budget.py` + `agent/subagent/manager.py`

#### 3.1 BudgetTracker — 预算累加器（`budget.py:43-66`）

```python
class BudgetTracker:
    def __init__(self, max_tokens: int | None = None, max_time_s: float | None = None):
        self.max_tokens = max_tokens       # 可为 None（不限）
        self.max_time_s = max_time_s       # 可为 None（不限）
        self.tokens = 0                     # 累加计数器
        self.started_at = time.time()

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.tokens += input_tokens + output_tokens    # :57-58

    def token_overrun(self) -> bool:       # :60-61
        return self.max_tokens is not None and self.tokens > self.max_tokens

    def time_overrun(self) -> bool:        # :63-66
        if self.max_time_s is None:
            return False
        return time.time() - self.started_at > self.max_time_s
```

**每次 LLM 调用后累加**（`:86-94`）：`BudgetHook.after_llm_call()` 读取 `response.usage.input_tokens + output_tokens` 并累加到 tracker。

**配置来源**（`config.py:246-258`）：

```python
@dataclass(frozen=True)
class SubagentsConfig:
    max_concurrent_runs: int = 4
    max_depth: int = 3
    default_max_tokens: int | None = None       # 默认无 token 限制
    default_max_time_s: float | None = None     # 默认无时间限制
```

**预算默认关闭**：`default_max_tokens` 和 `default_max_time_s` 默认都是 `None`。需要用户在 `asterwynd.yaml` 中配置 `subagents.budget.max_tokens` / `subagents.budget.max_time_s` 或在 `RunSubagent` 调用时显式传参，预算限制才生效。

#### 3.2 两条 Kill 路径

设计中严格区分两类超限场景及其触发路径（`budget.py:5-15` 注释）：

##### 路径 1: Token 超限 — Hook 内检测（`budget.py:86-94`）

```
AgentLoop 每次 LLM 调用后:
  BudgetHook.after_llm_call(response)
    → tracker.add(input_tokens, output_tokens)           # :88
    → if tracker.token_overrun():                        # :89
        raise BudgetExceededError("token", used, limit)  # :90-94

_execute_run (manager.py:457-461):
  except BudgetExceededError as exc:
    self._write_checkpoint(session, run)                  # 快照
    self._mark_budget_exceeded(session, run, exc.dimension, ...)
```

Token 超限在 LLM 调用边界（`after_llm_call` hook）被捕到。不需要外部 cancel —— `BudgetExceededError` 直接 unwinds loop，manager 在 exception handler 中写 checkpoint + 标记 `budget_exceeded`。

##### 路径 2: 时间超限 — Monitor 协程硬杀（`manager.py:645-666`）

```
run_subagent → _launch_run:
  if run.max_time_s is not None:                           # :352
    asyncio.create_task(self._monitor_run_timeout(session, run))

_monitor_run_timeout:
  await asyncio.sleep(run.max_time_s)                      # :656
  task = self._active_tasks.get(run.run_id)
  run._budget_kill_reason = "time"                         # :660  ← 先标记
  self._write_checkpoint(session, run)                     # :661  ← 先快照
  task.cancel()                                            # :662  ← 再取消

_execute_run (manager.py:462-471):
  except asyncio.CancelledError:
    if run._budget_kill_reason is not None:
      self._mark_budget_exceeded(session, run, run._budget_kill_reason, ...)
    else:
      self._mark_cancelled(session, run, trace)             # 普通取消
```

时间超限使用独立协程 `asyncio.sleep(run.max_time_s)` 后 cancel 跑趟 task。关键顺序是 **先标记 `_budget_kill_reason` + 先写 checkpoint，再 cancel**，这样被取消后 handler 能区分 "预算杀" vs "普通取消"（`:464`），终止状态正确标记为 `budget_exceeded` 而非 `cancelled`。

时间超限处理的是"tool 卡死"场景（如 hung Bash），此时 hook 永远不触发，只能用外部协程硬杀。

#### 3.3 双路径的共同行为

1. **都先写 checkpoint 再杀**（`:458, :463, :473`），保证预算 kill 后的 run 总是可恢复的
2. **都标记 `status = "budget_exceeded"`**（`manager.py:602`），reason 格式 `"budget exceeded (token)"` / `"budget exceeded (time)"`
3. **都回填 token 使用量**（`:609-610`）：即使未正常完成，`run.usage` 也记录实际消耗的 token，用于 benchmark 成本归因

#### 3.4 BudgetHook 的注册（`:527-528`）

```python
# manager.py:527-528
if budget is not None:
    hooks.hooks.append(BudgetHook(budget))
```

`BudgetHook` 是 per-run 实例化（`:442-446`），每个 run 独立一个 `BudgetTracker`，不共享跨 run 状态。必须实现所有 7 个 Hook 方法（`:80-111`），因为 `HookManager` 按属性名分发，缺方法会抛 `AttributeError`。

---

### 4. 快照恢复

**文件**：`agent/subagent/snapshot.py` + `agent/subagent/manager.py`

#### 4.1 存储后端

```python
# snapshot.py:27-35
class SubagentSnapshotStore:
    def __init__(self, root: str | Path):
        self._store = SessionStore(str(root))       # 复用主 session 的 SessionStore

    @classmethod
    def for_workspace(cls, workspace_root):
        return cls(Path(workspace_root) / ".asterwynd" / "subagents")
```

**关键设计**：
- 复用 `SessionStore`（`snapshot.py:31`），继承其 `schema_version` 兼容、SHA-256 去重、`tmp+replace` 原子写入机制
- 存储路径 `:35`：`<workspace_root>/.asterwynd/subagents/<run_id>/`
- key 为**完整 `run_id`**（非 8 字符 `subagent_id`），不可能与其他 run 碰撞（`:13` 注释）

#### 4.2 快照结构

```python
# snapshot.py:46-73
def snapshot_for_run(self, session, run, bus_summary=""):
    return SessionSnapshot(
        schema_version="1.0",
        session_id=run.run_id,         # ← key 是 run_id
        messages=list(session.messages),  # 完整 transcript
        mode=session.mode,
        todos=[],                      # 子 agent 快照无待办
        active_skills=[],
        run_id=run.run_id,
        iteration=_iteration_from_run(run),  # 从 trace 计算已执行步数
        objective=run.task,
        blockers=[],
        next_steps=[],
        bus_summary=bus_summary,        # 编排 bus 摘要（compact_summary()）
    )
```

`bus_summary` 字段（`:72`）：快照时把活跃 bus 的 `compact_summary()` 折叠进快照，续传后 agent 能看到之前的协作上下文。

#### 4.3 Checkpoint 写入时机（`manager.py:621-643`）

```python
def _write_checkpoint(self, session, run):
    # 在以下 4 个位置调用：
    store = self._snapshot_store()
    bus_summary = ""
    bus = current_bus()
    if bus is not None:
        bus_summary = bus.compact_summary()        # 折叠 bus 摘要
    store.save(store.snapshot_for_run(session, run, bus_summary))
```

| 触发场景 | 行号 | 说明 |
|----------|------|------|
| `BudgetExceededError`（token 超限） | `:458` | in-loop 检测到 token 超限 |
| `asyncio.CancelledError`（超时 kill + 人工 cancel） | `:463` | 时间超限 monitor 杀 / 用户取消 |
| 其他异常 | `:473` | 任何未处理异常 |
| 时间超限 monitor 中 | `:661` | monitor kill 前的额外保护 |

#### 4.4 恢复路径（`manager.py:242-296`）

```python
async def resume_subagent(self, *, subagent_id, task, run_id, ...):
    snapshot = self._snapshot_store().load(run_id)   # 加载快照
    if snapshot is None:
        raise KeyError(f"no checkpoint found for run {run_id}")
    # 重置 session transcript 为 system + continue prompt
    session.messages = [
        system_message("你是一个受限的子 agent。...")
    ]
    # _launch_run 传入 resume_snapshot
    await self._launch_run(session, run, resume_snapshot=snapshot)
```

**恢复是 transcript 级，非 call-stack 级**（`:256-258` 注释）：

```
"Resume is transcript-level, not stack-level (issue 79, decision D2)"
```

这意味着：
- 快照恢复后，AgentLoop 接收 `resume_snapshot`（`manager.py:454`）：传入 `loop.run()` 的 `resume_snapshot` 参数
- AgentLoop 的 resume 路径（`loop.py:557-584`）从快照重建 transcript，附加续传标记
- **未完成的 tool_call**：对话历史中 assistant tool_call 消息存在但 tool_result 缺失 → 模型看到不完整的工具链 → 自然地重新发起工具调用
- **不存在代码级别的工具栈恢复**：不尝试重新执行未完成的 tool_call

#### 4.5 LLM 可见的 Resume 工具

```python
# subagents.py:283-317
class ResumeSubagentTool(Tool):
    name = "ResumeSubagent"
    # params: subagent_id, run_id, task, wait, timeout_s, max_tokens, max_time_s
```

主 agent 可以通过此工具主动 resume 任何有 checkpoint 的已中断 run。

---

### 5. 并发与深度护栏

**文件**：`agent/subagent/manager.py`

#### 5.1 护栏参数

```python
# manager.py:146-155
self.max_concurrent_runs = max_concurrent_runs or getattr(guardrails, "max_concurrent_runs", 4)
self.max_depth = max_depth or getattr(guardrails, "max_depth", 3)
```

默认值来自 `SubagentsConfig`（`config.py:255-256`）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_concurrent_runs` | 4 | 最大并行子 agent 数 |
| `max_depth` | 3 | 最大嵌套深度（root = 0） |

#### 5.2 拦截时机（`:714-732`）

```python
def _check_guardrails(self):     # Pure pre-spawn guard
    depth = current_spawn_depth() + 1
    if depth > self.max_depth:
        raise RuntimeError(f"depth {depth} > max_depth {self.max_depth}")
    active = len(self._active_tasks)
    if active >= self.max_concurrent_runs:
        raise RuntimeError(f"{active} active runs >= max_concurrent_runs {self.max_concurrent_runs}")
```

在 `run_subagent` 的 `:222` 调用，创建 run record 之前，所以被拒的 spawn 不留痕迹。

---

### 6. 子 Agent 工具清单

**文件**：`agent/tools/builtin/subagents.py`

共 10 个 LLM 可见工具，全部权限 `SUBAGENT_CONTROL_PERMISSION`：

| # | 工具 | 行号 | 功能 |
|---|------|------|------|
| 1 | `CreateSubagent` | `:14-40` | 创建子 agent session（name / description / mode） |
| 2 | `RunSubagent` | `:43-71` | 启动子 agent 执行 task（wait / timeout_s） |
| 3 | `ListSubagents` | `:74-87` | 列出当前可见子 agent |
| 4 | `GetSubagentRun` | `:90-118` | 查询子 agent run 状态/结果 |
| 5 | `CancelSubagentRun` | `:120-145` | 取消活跃子 agent run |
| 6 | `InspectSubagentTranscript` | `:148-178` | 查看子 agent transcript（summary / recent_messages） |
| 7 | `PublishBusMessage` | `:181-237` | 发布摘要到消息总线 |
| 8 | `ReadBus` | `:240-280` | 消费消息总线摘要 |
| 9 | `ResumeSubagent` | `:283-317` | 从 checkpoint 恢复中断的 run |
| 10 | `RunPattern` | `:320-354` | 运行编排模式（4 种枚举 pattern） |

---

### 7. 事实核查汇总

对简历表述的每个事实点进行代码级确认：

| 简历事实 | 代码确认 |
|----------|----------|
| "内置 4 种多 Agent 编排模式" | `patterns.py:203-208` — `PATTERNS` dict 恰好 4 个 key |
| "orchestrator-worker" | `patterns.py:100-111` — `OrchestratorWorkerPattern`，默认 3 worker 并行 |
| "peer-review" | `patterns.py:114-149` — `PeerReviewPattern`，最多 3 轮送代 |
| "hierarchical" | `patterns.py:152-164` — `HierarchicalPattern`，默认 2 个 manager，可嵌套 spawn（D4） |
| "bidding" | `patterns.py:167-200` — `BiddingPattern`，默认 3 proposer + 1 selector |
| "子 agent 消息总线" | `bus.py:53-139` — `MessageBus`，三层 token 预算，三层语义：bounded queue / publish summarization / consume token window |
| "token/时间双维度" | `budget.py:46-66` — `BudgetTracker` 同时跟踪 `max_tokens` 和 `max_time_s` |
| "硬 kill" | `budget.py:86-94` token overrun → `BudgetExceededError`，`manager.py:645-666` time overrun → `task.cancel()` |
| "快照恢复" | `snapshot.py:27-73` — `SubagentSnapshotStore`，`manager.py:242-296` — `resume_subagent` |

**标注"默认关闭"或"需配置启用"：**

| 功能 | 默认状态 | 说明 |
|------|----------|------|
| Token 预算限制 | **关闭** | `config.py:257` — `default_max_tokens: int \| None = None` |
| 时间预算限制 | **关闭** | `config.py:258` — `default_max_time_s: float \| None = None` |
| 消息总线 | **按 run 创建** | 仅 `run_pattern()` 内部创建（`patterns.py:227`），直接调子 agent 工具的 run 不创建 bus |
| Checkpoint 快照 | **中断时自动** | 异常/取消/预算杀路径自动写，正常完成不写 |

---

### 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/subagent/patterns.py` | 4 种编排模式（OrcPattern 基类 + 4 子类 + PATTERNS + run_pattern 入口） |
| `agent/subagent/bus.py` | MessageBus：三层 token 预算（bounded queue / publish summarization / consume window） |
| `agent/subagent/budget.py` | BudgetTracker + BudgetHook + BudgetExceededError：双维度预算硬 kill |
| `agent/subagent/snapshot.py` | SubagentSnapshotStore：快照持久化 + SessionStore 复用 |
| `agent/subagent/manager.py` | SubAgentManager：全生命周期（create / run / resume / cancel / transcript）+ guardrails |
| `agent/subagent/context.py` | ContextVar：spawn_depth + bus 上下文传递 |
| `agent/subagent/protocol.py` | ParentChannel：父子 agent 结果回传 |
| `agent/subagent/parent_channel_hook.py` | ParentChannelHook：结果注入父 agent 消息 |
| `agent/tools/builtin/subagents.py` | 10 个 LLM 可见子 agent 工具（含 RunPattern / ResumeSubagent / PublishBusMessage / ReadBus） |
| `agent/config.py:246-258` | SubagentsConfig：max_concurrent_runs=4 / max_depth=3 / budget defaults=None |
| `openspec/specs/multi-agent-collaboration/spec.md` | 多 Agent 协作能力域规格（6 requirements） |

---

## Bullet 4: ContextBuilder 上下文系统 — 代码走读

> 简历原文：实现 ContextBuilder 统一编排 8 个上下文源，稳定前缀分层注入、字节级不变命中 LLM Prefix Cache，搭配 AutoCompact L1/L2 层级压缩与 tool-call pending 标记防止工具链断裂

---

### 整体架构

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

### 1. ContextBuilder 统一编排 8 个上下文源

#### 注册点

**文件**：`agent/loop.py:1352-1367`

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

**代码级计数**：恰好 8 次 `builder.register()` 调用（line 1356-1367），无其他注册路径。

#### 8 个源的完整属性对照表

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

#### Priority 分层模型

```
P0 (最高)     SystemPrompt         ← critical + static + cacheable
P1           AsterMd              ← critical + static + cacheable
P2           MemoryIndex, Todo    ← MemoryIndex cacheable（非 static），Todo 无保护
P3           (未使用)
P4           SkillIndex, SkillActive
P5 (最低)     PlanMode, PlanningState
P6           (未使用)
```

#### ContextBuilder 核心实现

**文件**：`agent/context/builder.py:27-204`

核心类 `ContextBuilder`，维护 `_sources: list[ContextSource]` 和 `_static_cache: dict[tuple, str]`。

**注入入口**（`loop.py:1313-1340` `_messages_with_run_context`）：

```python
# loop.py:1316-1326
ctx = BuildContext(
    cwd=cwd,
    mode=self.runtime_state.current_mode,
    context_window=self._context_window,
    total_budget=self._injection_budget,      # min(20K, 20% of context_window)
    user_system_prompt=self._user_system_prompt,
)
blocks = await self.context_builder.build_blocks(ctx)
```

注入预算公式（`loop.py:1348-1350`）：

```python
@property
def _injection_budget(self) -> int:
    """Injection-layer budget: min(20K, 20% of context window)."""
    return min(20_000, int(self._context_window * 0.20))
```

默认 context_window 为 100K（`loop.py:1343-1345`，`_context_window` property fallback 到 100000），所以默认注入预算为 `min(20000, 20000) = 20000` tokens。

---

### 2. 稳定前缀分层注入

#### 稳定前缀的定义

稳定前缀由具备 `cacheable=True` 属性的源构成。从属性对照表可知：**P0（SystemPrompt）+ P1（AsterMd）+ P2 中的 MemoryIndexSource** 三个 cacheable 层构成稳定前缀。

- P0 和 P1 同时具备 `static=True`：同 cwd/mode/user_system_prompt 下输出**字节级不变**（`builder.py:42-45`）
- P2 MemoryIndex 具备 `cacheable=True` 但 `static=False`：保留在前缀中不受截断，但每轮重渲染以获取最新记忆摘要

#### 优先级排序与分层注入

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

#### Static 缓存机制

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

#### 预算截断策略

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

#### build_blocks：生成带 cache flag 的 TextBlock 列表

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

#### 层间分隔符

`_join_layers`（`builder.py:197-204`）用 `"\n\n---\n\n"` 连接各层，保证每层视觉上有明确边界。

---

### 3. 字节级不变命中 LLM Prefix Cache

#### 整体机制：从 cacheable flag 到 cache_control 断点

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

#### _compute_cache_plan — 断点计算

**文件**：`agent/loop.py:1116-1163`

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
                if isinstance(b, TextBlock) and b.cache:   # :1140
                    stable_system_breakpoint = block_index + 1  # 1-based
                block_index += 1
        else:
            block_index += 1

    # Selector OFF（默认）：断点打在最后一个 cacheable system block
    selector = getattr(self.tool_registry, "_selector", None)
    if selector is None:
        return CachePlan(stable_system_block_count=stable_system_breakpoint,
                         stable_tool_count=0)                # :1148-1151

    # Selector ON：断点打在最后一个核心稳定工具上
    ...
    return CachePlan(stable_system_block_count=0,
                     stable_tool_count=stable_tool_count)
```

**默认（Selector OFF）**：断点只打在最后一个 cacheable system block。Anthropic API 缓存该 block **及之前所有内容**（system blocks + 所有 tools），最大程度覆盖。

**Selector ON**：变层 tools 破坏前缀不变性，断点改打在最后一个核心稳定工具上。

#### AnthropicLLM._apply_cache_plan — 实际打断点

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

#### 字节级不变的前提条件

要保证 prefix cache 命中，缓存区间的内容必须字节级一致：

| 条件 | 机制 | 代码 |
|------|------|------|
| P0/P1 源：同 cwd/mode/user_system_prompt 下输出不变 | `static=True` + 缓存 key 排除变化因素 | `builder.py:63-67` |
| cacheable 层不参与预算截断 | `cacheable=True` → `_find_trimmable_index` 跳过 | `builder.py:178` |
| budget 不变 | 截断位置稳定，不会锯齿状变化 | `loop.py:1350` |
| 工具 schema 不变（Selector OFF） | 全量 tool schema 无变化 | `loop.py:1013` |

#### 仅 Anthropic 路径生效

**文件**：`loop.py:1097-1115`

```python
def _apply_cache_plan(self, messages, tools=None) -> None:
    if not getattr(self.llm, "supports_cache_control", False):
        return   # OpenAI 走服务端 auto-caching，不需要手动打断点
    plan = self._compute_cache_plan(messages, tools)
    self.llm.cache_plan = plan
```

`supports_cache_control = True` 只在 `AnthropicLLM`（`anthropic_llm.py:36`）上声明。OpenAI 端通过服务端 auto-caching 实现类似效果，不需要手动打点。

#### 400 降级保护

**文件**：`anthropic_llm.py:75-86`

某些 Anthropic 兼容端点（如 DeepSeek-anthropic）会拒收 `cache_control` 字段并返回 400。AnthropicLLM 在非流式路径中自动检测并重试：

```python
if self._payload_has_cache_control(payload):
    logger.info("400 with cache_control — retrying without it")
    payload = self._strip_cache_control(payload)   # 深拷贝并去掉所有 cache_control
    return await self._chat_nonstream(payload)      # 重试
```

400 降级逻辑统一在 `chat()`（`anthropic_llm.py:56-97`）中处理，同时覆盖流式与非流式两条路径（try/except 同时包住 `_chat_stream` 与 `_chat_nonstream`）。

---

### 4. AutoCompact L1/L2 层级压缩

#### 触发时机

**文件**：`agent/loop.py:952-972`

每次迭代的 Phase 3 末尾，工具执行结果回填后触发：

```python
# loop.py:952
compacted = await self.memory.compact_if_needed(messages, iteration=self._iteration)
```

#### compact_if_needed — 触发条件

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

#### compact — 核心压缩流程

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

#### L1 层：增量压缩

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

#### L2 层：高阶压缩

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

#### L2 压缩实现 — LLMSummarizer.compress

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

#### 两种 Summarizer

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

#### 四段式摘要结构

**文件**：`summarizer.py:74-96`

```markdown
## 已完成事项
## 待办事项
## 疑难点与决策
## 当前进行中
```

该结构在 agent 恢复上下文时提供清晰的信息分层。

---

### 5. tool-call pending 标记防止工具链断裂

#### 工具链保护 — _recent_with_tool_chains

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

#### _annotate_pending_calls — 挂起标记

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

#### _decorate_for_summary — 组合注入

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

#### LLM Summarizer 中 pending 标记的保留

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

#### ReadProgress 分页进度保留

`_extract_read_progress`（`manager.py:456-472`）从 tool result 中提取 `[ReadProgress file="..."; offset=...; total=...]` 注记，以 per-file last-winner 策略保留最后一次读到的 (file, offset, total)。这些信息通过 `_decorate_for_summary` 注入摘要 prompt，确保压缩后 agent 仍知道大文件读到了哪里（避免从头重新读取）。

---

### 默认配置速查

| 参数 | 默认值 | 位置 |
|------|--------|------|
| ContextBuilder 注入预算 | `min(20000, context_window * 0.2)` | `loop.py:1350` |
| context_window 默认 | 100000 (100K) | `loop.py:1343-1345` |
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

**无"默认关闭"的功能**：ContextBuilder 在 `AgentLoop.__init__` 中始终创建（`loop.py:157-159`），AutoCompact 始终由 `compact_if_needed` 调用（`loop.py:952`），cache_control 断点对所有 `supports_cache_control=True` 的 LLM 生效。整个上下文系统没有通过配置开关控制的功能。

---

### 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/context/builder.py` | ContextBuilder：优先级排序 + 静态缓存 + 预算截断 + 层连接 |
| `agent/context/sources.py` | 全部 8 个 ContextSource 实现 + ASTER.md 收集/渲染 |
| `agent/context/protocol.py` | ContextSource Protocol + BuildContext 数据类 |
| `agent/context/summarizer.py` | Summarizer Protocol + LLMSummarizer（四段式 + L2）+ TruncationSummarizer |
| `agent/memory/manager.py` | MemoryManager：AutoCompact + L1/L2 层级记账 + tool-call pending + ReadProgress 保护 |
| `agent/loop.py:1352-1367` | `_make_default_context_builder()` — 8 源注册点 |
| `agent/loop.py:1313-1340` | `_messages_with_run_context()` — context 注入到 messages |
| `agent/loop.py:1097-1163` | `_apply_cache_plan()` + `_compute_cache_plan()` — cache_control 断点计算 |
| `agent/anthropic_llm.py:167-194` | `AnthropicLLM._apply_cache_plan()` — cache_control 断点实际注入 |
| `agent/anthropic_llm.py:36` | `supports_cache_control = True` |
| `agent/message.py:18-22` | `TextBlock` — `cache: bool` 字段定义 |
| `agent/llm.py:20-31` | `CachePlan` — `stable_system_block_count` + `stable_tool_count` |

---

## Bullet 5: 长期记忆系统 — 代码走读

> 简历原文：构建长期记忆系统，LLM 写时四分支去重（supplement/update/conflict + new 兜底），importance × recency 联合时效衰减（30 天半衰期）、超期未访问自动归档且可恢复，git commit-before-write + revert 机制保障数据可逆，对比 mem0 路线后自主设计并沉淀 ADR

---

### 整体架构

长期记忆系统由 4 个核心模块组成，存储在 `agent/memory/` 目录下：

```
用户记忆文件 → ~/.asterwynd/projects/<sha256[:16]>/memory/
               ├── MEMORY.md         ← 人类可读索引
               ├── <name>.md         ← 每条记忆一个 Markdown 文件（YAML frontmatter）
               ├── changelog.md      ← 审计日志
               ├── archive/          ← 归档目录（超期/手动）
               └── .git/             ← 独立 git 仓库（懒初始化，不在项目仓库内）
```

数据模型（`agent/memory/model.py`）：

```python
@dataclass
class MemoryEntry:
    name: str
    description: str
    body: str
    type: str = "project"           # user / feedback / project / reference
    importance: int = 3             # 1-5
    created_at: datetime | None
    last_accessed_at: datetime | None  # decay 的时间锚点
    scope: str                       # 项目 root path，隔离不同项目
    archived: bool = False
    conflict_with: list[str]         # 写时去重标记的矛盾记忆名列表
```

4 种记忆类型（`persistent.py:37`）：`_VALID_TYPES = frozenset({"user", "feedback", "project", "reference"})`。

工具暴露（`agent/tools/builtin/memory.py`）：`SaveMemory`、`RecallMemory`、`SearchMemory`、`ResolveMemoryConflict`、`MemoryGitBackend`，共 5 个（`factory.py:97-101`，`KNOWN_BUILTIN_TOOL_NAMES` 中确认）。

---

### 1. LLM 写时四分支去重（supplement / update / conflict + new 兜底）

#### 1.1 四分支定义

**文件**：`agent/memory/dedup.py:24`

```python
_ACTIONS = frozenset({"new", "supplement", "update", "conflict"})
```

恰好 4 个分支，语义由 LLM 判决系统提示词定义（`:41-54`）：

| 分支 | 语义 | 写入行为 |
|------|------|---------|
| `new` | 与任何已有记忆都不重叠 | 新建文件 |
| `supplement` | 对已有记忆补充细节，不矛盾 | 追加 body（`旧body \n\n 新body`） |
| `update` | 新内容取代旧内容 | 替换 body |
| `conflict` | 内容矛盾，两方都应保留 | 新建文件 + 双向标记 `conflict_with` |

#### 1.2 去重流水线

**调用入口**：`agent/tools/builtin/memory.py:74-102`（`SaveMemoryTool.execute()`）

```
① 构造 incoming_text = "name: description\nbody"                          (:85)
② persistent.recall_similar(incoming_text, top_k=5) — 向量召回 Top-K     (:86)
③ MemoryDedupJudge.judge(incoming, candidates) — LLM 判决                 (:87)
④ persistent.apply_judgment(...) — 按判决结果执行写入                      (:88-95)
```

**步骤 2 向量召回**（`persistent.py:763-770`）：

```python
def recall_similar(self, query, top_k=5, embedder=None):
    """Write-dedup candidate recall: top-k similar active memories."""
    return self.search(query, top_k=top_k, embedder=embedder)
```

使用 `NGramEmbedding`（字符 n-gram MD5 哈希，2048 维，零外部依赖）做余弦相似度检索。

**步骤 3 LLM 判决**（`dedup.py:84-119`）：

```python
class MemoryDedupJudge:
    def __init__(self, llm=None, model=None, recall_threshold=0.5):
```

- `recall_threshold = 0.5`（`dedup.py:78`）：候选相似度 < 0.5 的直接短路为 `new`，零 LLM 成本（`:93-95`）
- `llm=None` 时（无 LLM 可调）→ 全部返回 `new`，不阻塞写入（`:90-91`）
- LLM 调用失败 → fallback `new`，记录 `llm_call_failed`（`:115-117`）
- JSON 解析失败 → fallback `new`，记录 `parse_failed`（`:141-150`）
- 未知 action → fallback `new`，记录 `invalid_action`（`:148-150`）

**new 的多层兜底**：无 LLM / 无候选 / 相似度低于阈值 / LLM 报错 / 解析失败 / 未知 action / 目标不存在 / 目标已归档 — 所有路径最终 fallback 到 `self.save()`（`persistent.py:618`）。

#### 1.3 四分支写入实现

**文件**：`agent/memory/persistent.py:548-618`（`apply_judgment()`）

```python
def apply_judgment(self, type, name, description, body, judgment, importance=None):
    action = getattr(judgment, "action", "new")
    target = getattr(judgment, "target_name", None)
```

| 分支 | 实现位置 | 写入逻辑 |
|------|---------|---------|
| `supplement` | `:571-583` | `entry.body = f"{entry.body}\n\n{body.strip()}"` — 尾部追加 |
| `update` | `:585-598` | `entry.body = body.strip()` — 整体替换 |
| `conflict` | `:600-616` | 新建 `name` 条目 + 双向 `conflict_with` 列表追加 |
| `new`（兜底） | `:618` | 直接 `self.save()` — 新建文件 |

**LLM 提供的 target 名前验证**（`:567-569`）：

```python
if target is not None and _validate_name(str(target)) is not None:
    return self.save(type, name, description, body, importance=importance)
```

防止 LLM 幻觉出非法文件名（如 `../etc/passwd`）→ 直接 fallback 到 `new`。

**target 不存在或已归档时的兜底**（`:573-574, :587-588`）：supplement/update 的目标如果已消失或归档 → 退化为 `new`。

#### 1.4 去重判断默认可关闭

**文件**：`agent/tools/builtin/memory.py:84`

```python
if self._judge is not None:
    # 有 judge → 走四分支
else:
    # 无 judge → 直接 save，无去重
    return memory.save(type, name, description, body, importance=importance)
```

`MemoryDedupJudge` 由 `SaveMemoryTool` 构造函数的 `judge` 参数传入（`:62`）。不传 `judge` 时，所有写入跳过 LLM 判决，直接覆盖保存。工具注册在 `factory.py` 中，`judge` 是否传入取决于配置。

---

### 2. importance × recency 联合时效衰减（30 天半衰期）

#### 2.1 参数定义

**文件**：`agent/memory/persistent.py:40-54`

```python
DEFAULT_IMPORTANCE = 3      # line 40
IMPORTANCE_MIN = 1          # line 41
IMPORTANCE_MAX = 5          # line 42
ARCHIVE_AFTER_DAYS = 30     # line 43
RECENCY_HALFLIFE_DAYS = 30  # line 44  ← 半衰期 30 天
MAX_SUMMARY_TOKENS = 50     # line 45
DEDUP_RECALL_THRESHOLD = 0.5 # line 46
DECAY_THRESHOLD: float | None = 1.5      # line 51 — 衰减分数门限
DECAY_INTERVAL_SECONDS = 3600            # line 54 — 衰减检查节流间隔（1 小时）
```

所有参数均可通过 `PersistentMemory.__init__` 的构造参数覆盖（`:168-178`），实现按实例定制。

#### 2.2 衰减公式

**文件**：`agent/memory/persistent.py:212-223`（`decay_score()`）

```python
def decay_score(self, entry: MemoryEntry, now=None) -> float:
    """Importance × recency joint score (Decision 3).

    recency = 0.5 ^ (days_since_last_access / recency_halflife_days).
    """
    now = now or self._now()
    last = entry.last_accessed_at or entry.created_at or now
    days = max(0.0, (now - last).total_seconds() / 86400.0)
    recency = 0.5 ** (days / self._recency_halflife_days)
    return entry.importance * recency
```

**公式解读**：

```
decay_score = importance × 0.5^(days / 30)
```

- `importance` 范围 1-5，默认 3
- `days` = 距上次访问的天数（**小数天**，`:221` 用 `total_seconds() / 86400.0`，不是整天数）
- `recency` 在 30 天时恰好 = 0.5（半衰期），60 天时 = 0.25，以此类推

**时间锚点**：`last_accessed_at or created_at or now`（`:220`）——优先用最后访问时间，其次创建时间，最后当前时间。

**访问即刷新**：`persistent.py:840-846`（`_touch()`）

```python
def _touch(self, name):
    """Update last_accessed_at on retrieval so decay reflects real access."""
    entry = self._load_entry_by_name(name)
    if entry is None or entry.archived:
        return
    entry.last_accessed_at = self._now()
    self._write_entry(entry)
```

每次 `recall()` / `search()` 命中某条记忆，`_touch()` 更新其 `last_accessed_at`，实时刷新衰减时钟。

#### 2.3 衰减分数计算举例

| importance | 距上次访问 | days/30 | recency (0.5^(d/30)) | decay_score |
|:---|:---|:---|:---|:---|
| 5 | 30 天 | 1.0 | 0.5 | 2.5 |
| 3 | 30 天 | 1.0 | 0.5 | 1.5 |
| 1 | 30 天 | 1.0 | 0.5 | 0.5 |
| 5 | 60 天 | 2.0 | 0.25 | 1.25 |
| 3 | 60 天 | 2.0 | 0.25 | 0.75 |
| 1 | 60 天 | 2.0 | 0.25 | 0.25 |

可见：高 importance（5）的记忆 60 天不访问后 score=1.25 仍高于默认门限 1.5？不对，1.25 < 1.5，所以会被归档。而 importance=5 在 30 天时 score=2.5 远高于 1.5，不会被归档。这就是 `importance × recency` 联合衰减的效果——**重要记忆即使不访问也能存活更久**。

---

### 3. 超期未访问自动归档且可恢复

#### 3.1 归档条件（双门 AND 逻辑）

**文件**：`agent/memory/persistent.py:225-246`（`run_decay()`）

```python
def run_decay(self, now=None) -> int:
    """Archive active memories that have aged out.
    ...
    """
    now = now or self._now()
    archived = 0
    for entry in self.load_entries():
        last = entry.last_accessed_at or entry.created_at or now
        days = (now - last).total_seconds() / 86400.0
        if days <= self._archive_after_days:       # Gate 1: 30 天
            continue
        if self._decay_threshold is not None and self.decay_score(entry, now) >= self._decay_threshold:
            continue                                # Gate 2: score >= 1.5 则保护
        self.archive(entry.name, reason="decay: not retrieved within archive_after_days")
        archived += 1
    return archived
```

归档条件 = **超期（> 30 天未访问）AND 衰减分数低于门限（< 1.5）**。两个条件同时满足才归档。

**门限可关闭**：`decay_threshold=None` 时（构造参数可设为 None），Gate 2 失效 → 纯时间归档（> 30 天即归档）。

#### 3.2 归档节流

**文件**：`agent/memory/persistent.py:248-261`（`_run_decay_if_due()`）

```python
def _run_decay_if_due(self, now=None) -> int:
    """Throttled decay trigger, called from every read entry point."""
    now = now or self._now()
    if self._last_decay_run is not None:
        elapsed = (now - self._last_decay_run).total_seconds()
        if elapsed < self._decay_interval_seconds:
            return 0
    self._last_decay_run = now
    return self.run_decay(now)
```

- `DECAY_INTERVAL_SECONDS = 3600`（`:54`）：最多每 1 小时运行一次衰减扫描
- 触发点：每次 `load_index()` / `load_summary()` / `recall()` / `search()` 调用都会检查（`:273, 312, 702, 738`），但节流保证不会在繁忙 session 中每个读路径都全量扫描

#### 3.3 归档实现

**文件**：`agent/memory/persistent.py:776-795`（`archive()`）

```python
def archive(self, name, reason=None):
    entry = self._load_entry_by_name(name)
    if entry is None:
        return f"Error: memory '{name}' not found."
    if entry.archived:
        return f"Memory '{name}' already archived."
    archive_dir = self.memory_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    src = self._entry_path(name)
    dst = archive_dir / f"{name}.md"
    entry.archived = True
    self._write_entry_to(entry, dst)    # 写入 archive/ 目录
    src.unlink()                         # 删除原位置文件
    self._remove_from_index(name)        # 从 MEMORY.md 移除索引行
    self._append_changelog("archive", name, reason or "archived")
    return f"Memory '{name}' archived."
```

归档 = 移动文件到 `archive/` 子目录 + 更新 frontmatter 中 `archived: true` + 从 MEMORY.md 索引移除 + 记录 changelog。**内容不删除，只是换位置**。

#### 3.4 恢复

**文件**：`agent/memory/persistent.py:797-812`（`restore()`）

```python
def restore(self, name):
    """Move an archived memory back into the active store."""
    entry = self._load_entry_by_name(name, include_archived=True)
    if entry is None or not entry.archived:
        return f"Error: memory '{name}' not found in archive."
    src = self._entry_path(name, archived=True)
    dst = self._entry_path(name)
    entry.archived = False
    self._write_entry_to(entry, dst)     # 写回 memory/ 目录
    src.unlink()                          # 删除 archive/ 中文件
    self._update_index(name, entry.description, existed=False)
    self._append_changelog("restore", name, "restored from archive")
    return f"Memory '{name}' restored."
```

恢复是归档的逆操作：`archived` 标记改回 `false`，文件从 `archive/` 移回上级目录，索引行重建，changelog 追加。**注意**：`restore()` 目前**没有暴露为独立工具**（`memory.py` 中无 `RestoreMemoryTool`），仅内部 API 可用。agent 可通过 `MemoryGitBackendTool` 的 `revert` action 间接恢复被归档之前的内容，但无法直接将 `archive/` 中的条目移回 active。

**归档触发机制**（`persistent.py` 中的三个归档入口）：

| 入口 | 触发者 | 位置 |
|------|--------|------|
| 自动衰减 | `_run_decay_if_due()`（每次读路径节流触发） | `:273, 312, 702, 738` |
| 手动归档 | 直接调用 `archive()` | `:776` |
| 冲突解决归档 | `resolve_conflict(archive=True)` — 归档败者 | `:654` |

---

### 4. git commit-before-write + revert 机制保障数据可逆

#### 4.1 核心设计：懒初始化 + 内联 identity

**文件**：`agent/memory/persistent.py:407-431`（`_ensure_git()`）

```python
def _ensure_git(self) -> bool:
    """Lazily initialize the memory git repo.
    No side effect in __init__: the repo is created only on the first
    destructive write, so invalid-name paths never create a memory dir.
    """
    if shutil.which("git") is None:
        return False
    if not self.memory_dir.exists():
        return False
    # git init -q
```

关键点：
- **懒初始化**：不在 `PersistentMemory.__init__` 里 `git init`，只在首次破坏性写时触发（`:408-412` 注释说明）
- **内联 identity**（`:22-23`）：`_GIT_USER_NAME = "Asterwynd Memory"`、`_GIT_USER_EMAIL = "memory@asterwynd.local"` — 不依赖全局/仓库级 git config（CI 环境无 git config 也能 commit）
- **内联方式**（`:26-33`）：`_run_git()` 每次调用都带 `-c user.name=... -c user.email=...`

#### 4.2 commit-before-write 流程

**文件**：`agent/memory/persistent.py:433-465`（`_git_commit()`）

```python
def _git_commit(self, action, name, reason):
    """commit-before-write: snapshot current memory dir before a destructive write.
    - git 不可用 → RuntimeError（中止写入）
    - git init 失败 → RuntimeError（中止写入）
    - git add 失败 → RuntimeError（中止写入）
    - nothing-to-commit（fresh repo / 无旧状态）→ 安全返回，继续写入
    - git commit 失败 → RuntimeError（中止写入）
    """
    if shutil.which("git") is None:
        raise RuntimeError("Memory reversibility: git is not available; aborting write...")
    if not self._ensure_git():
        raise RuntimeError("Memory reversibility: failed to initialize git repo; aborting write.")
    add = _run_git(self.memory_dir, "add", "-A")
    if add.returncode != 0:
        raise RuntimeError(f"Memory reversibility: git add failed: {add.stderr}")
    # No staged changes → nothing to commit (fresh repo / no prior state).
    quiet = _run_git(self.memory_dir, "diff", "--cached", "--quiet")
    if quiet.returncode == 0:
        return
    msg = f"{action} {name} → {reason}"
    commit = _run_git(self.memory_dir, "commit", "-q", "-m", msg)
    if commit.returncode != 0:
        raise RuntimeError(f"Memory reversibility: git commit failed, aborting write...")
```

**写保护语义**：commit 失败 → `RuntimeError` → 调用方不执行写入。宁可写失败，不丢旧内容。

**nothing-to-commit 特殊处理**（`:456-458`）：fresh repo（第一次写入前）无旧状态需要快照，直接安全通过。

#### 4.3 所有触发 commit-before-write 的写入路径

| 操作 | 触发位置 | commit message |
|------|---------|---------------|
| `save()` 覆盖已有条目 | `persistent.py:523` | `update <name> → save-overwrite` |
| `apply_judgment()` supplement | `persistent.py:576` | `supplement <target> → <reason>` |
| `apply_judgment()` update | `persistent.py:590` | `update <target> → <reason>` |
| `apply_judgment()` conflict | `persistent.py:604` | `conflict <name> → <reason>` |
| `resolve_conflict()` | `persistent.py:649` | `resolve <name_a> <-> <name_b> → <reason>` |

**注意**：新建条目（`new` 分支）不触发 commit-before-write —— 因为没有旧内容需要快照。

#### 4.4 Revert 机制（两阶段 commit）

**文件**：`agent/memory/git_backend.py:69-102`（`MemoryGitBackend.revert()`）

```python
def revert(self, name, commit):
    """Two-step commit (design Decision 3):
      1. snapshot current state (undo credential)
      2. checkout old body + rebuild index + append changelog,
         then commit the revert result.
    """
    # Step 1: snapshot the current (to-be-overwritten) state.
    self._memory._git_commit("revert", name, f"before revert to {commit}")

    # Apply the revert: checkout old body.
    proc = self._git("checkout", commit, "--", f"{name}.md")

    # Rebuild the index line from the reverted frontmatter
    entry = self._memory._load_entry_by_name(name)
    if entry is not None:
        self._memory._update_index(name, entry.description, existed=True)
    # Append change log entry (audit history is preserved, not rolled back).
    self._memory._append_changelog("revert", name, commit)

    # Step 2: commit the revert result
    self._memory._git_commit("revert", name, f"revert to {commit}")
```

**两阶段 commit 的设计意图**（ADR 对应 grill Q9 / design Decision 3）：
- **Step 1**（`:84`）：先 commit 当前状态作为 undo 凭证（"被覆盖前的最后状态"）
- **Step 2**（`:100`）：checkout 旧内容 + 重建 MEMORY.md 索引行（保证正文与索引一致）+ changelog 保留审计（不随正文回退），再 commit

结果：`git log -- <name>.md` 显示完整版本历史，包括 revert 前后的每一个快照。

#### 4.5 Git 三件套：history / diff / revert

**文件**：`agent/memory/git_backend.py:27-102`

| 操作 | 方法 | 底层命令 | 位置 |
|------|------|---------|------|
| 查看版本历史 | `history(name)` | `git log --format=%h %s -- <name>.md` | `:44-55` |
| 比较两个版本 | `diff(name, commit_a, commit_b)` | `git diff commit_a commit_b -- <name>.md` | `:57-67` |
| 回退到指定版本 | `revert(name, commit)` | `git checkout commit -- <name>.md` + index rebuild + commit | `:69-102` |

工具暴露：`MemoryGitBackendTool`（`memory.py:275-342`），支持 `action` 参数取值 `"history"` / `"diff"` / `"revert"`。

---

### 5. 对比 mem0 路线 + ADR 沉淀

#### 5.1 ADR 概览

**文件**：`docs/adr/ADR-0002-long-term-memory-reversibility.md`

- **Status**: accepted
- **Date**: 2026-08-03
- **Deciders**: issue #99 长期记忆可逆性设计评审

#### 5.2 三条备选方案对比

| 方案 | 描述 | 拒绝原因 |
|------|------|---------|
| **mem0 V3：ADD-only + 读时 ranker** | 删除写时 LLM diff，只做 MD5 精确去重；矛盾/近重复并列存储，读时用语义+BM25+实体+时间多信号排序 | 需要重写 read 路径 + 引入多信号打分引擎，远超 #99 范围；Asterwynd 当前只有 NGramEmbedding，弱 ranker 下 ADD-only 会让矛盾记忆无序浮出（ADR:33, Alternative 1） |
| **侧车 revisions 目录** | update/supplement 前把旧 body 写入 `memory_dir/revisions/<name>/<ts>.md` | "自己发明的残缺版 git"：无 diff/log/restore、版本清理与原子性要自己造；git 已提供全部能力且业界有 Letta Context Repositories 背书（ADR:41, Alternative 2） |
| **单文件 .bak / changelog 内联** | 每个记忆一个 `.bak` 文件，或 changelog 内嵌旧内容 | 误判链覆盖中间版本；changelog 内联破坏行格式与 grep 可审计性（ADR:42, Alternative 3） |

#### 5.3 最终决策（7 条）

**ADR Decision 1-7**（`:28-34`）：

1. `memory_dir` 初始化为独立 git 仓库，懒初始化（仅首次破坏性写前 `git init`）
2. **commit-before-write**：每次破坏性写前 `git add -A` + `git commit`，失败则中止写入
3. **commit message 承载结构化审计**：`<action> <name> -> <reason>` 与 changelog 行对齐
4. **新增 `resolve_conflict` API + 工具**：清除 `conflict_with` 标记 + 可选归档败者
5. **恢复能力**：基于 git 原生 `log`/`diff`/`checkout`，对外暴露 `MemoryGitBackend`
6. **不做 mem0 ADD-only**：Asterwynd read 路径只有 NGramEmbedding，无多信号 ranker（ADR 将此列为 revisit condition）

#### 5.4 业界调研引证

ADR 引用了三个业界参考（`:18-22`）：

- **mem0 V3**：因"写时 reconciliation 判错会静默删除/污染记忆"，**删除了第二遍 LLM diff 调用**，转向 single-pass ADD-only
- **Letta / MemGPT**：Context Repositories 用 git 管理记忆，每次改动自动版本化
- **Zep / Graphiti**：时序知识图谱，事实带 `valid_from`/`valid_to`，变更走"失效而非删除"

#### 5.5 已知债务（ADR Consequences）

- **并发丢更新**：git 解决误判恢复，但不解决并发写（read-modify-write 无 flock），登记为已知债（`:49`）
- **git 依赖**：依赖系统 `git` 可用，不可用时中止写入（`:54`）
- **commit 频率**：每次破坏性写一条 commit，可接受（`:56`）
- **conflict_with 累积**：需 `resolve_conflict` 主动解除（`:55`）

---

### 6. 其他支撑机制

#### 6.1 MEMORY.md 索引

**文件**：`agent/memory/persistent.py:34-35, 266-301, 860-875, 904-938`

- 格式：`- [name](name.md) — description` 每一行对应一条记忆
- 大小限制：`MAX_INDEX_LINES = 200`，`MAX_INDEX_BYTES = 25_000`（`:34-35`）
- 超限截断 + 警告提示（`:295-300`）
- 作为 system message 注入到 Agent 上下文（`load_index()`, `:267-301`）

#### 6.2 ~50 token 全局摘要

**文件**：`agent/memory/summary.py` + `persistent.py:303-315`

- `load_summary()` 调用 `build_summary()`（`summary.py:15`）
- 按 `importance` 降序 + `last_accessed_at` 升序排列（同 importance 下越早访问的越靠前）
- 截断到 `max_tokens=50`（`persistent.py:45`）
- 超出预算时追加 `... (use SearchMemory for details)` 提示

#### 6.3 changelog 审计日志

**文件**：`agent/memory/persistent.py:848-854`（`_append_changelog()`）

```python
def _append_changelog(self, action, name, reason):
    changelog = self.memory_dir / "changelog.md"
    ts = self._now().isoformat(timespec="seconds")
    line = f"- [{ts}] {action} {name} → {reason}\n"
    with changelog.open("a", encoding="utf-8") as fh:
        fh.write(line)
```

格式：`- [<ISO timestamp>] <action> <name> -> <reason>`，与 git commit message 对齐，提供双重审计。

#### 6.4 名称校验

**文件**：`agent/memory/persistent.py:36, 112-116`

```python
_VALID_NAME_RE = re.compile(r"^[a-z0-9-]+$")

def _validate_name(name):
    if not name or not _VALID_NAME_RE.match(name):
        return f"Invalid memory name '{name}': must be kebab-case ..."
```

所有公开 API（`save`/`archive`/`restore`/`resolve_conflict`/`revert`）在路径构造前都经过 `_validate_name()` 检查，防止路径遍历。

#### 6.5 Git Worktree 感知的作用域

**文件**：`agent/memory/persistent.py:62-109`（`_find_scope_root()` + `_git_common_dir()`）

```python
def _find_scope_root(path):
    """Resolve the project scope root for a checkout.
    The scope root is the canonical repository root shared across git
    worktrees (Decision 5 / R1-Q10).
    """
    # walks up from path, resolves .git file → commondir → main worktree root
```

同一个 git 仓库的所有 worktree 共享一份 memory 存储（scope root = 主 worktree 的 repo root），不会因 worktree 切换而产生多份记忆。

---

### 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/memory/persistent.py` | PersistentMemory 主类：save、apply_judgment、decay_score、run_decay、archive、restore、_git_commit、resolve_conflict |
| `agent/memory/dedup.py` | MemoryDedupJudge：LLM 四分支判决（new/supplement/update/conflict） |
| `agent/memory/git_backend.py` | MemoryGitBackend：history / diff / revert（两阶段 commit） |
| `agent/memory/model.py` | MemoryEntry / MemoryHit 数据模型 |
| `agent/memory/summary.py` | build_summary：~50 token 重要性排序全局摘要 |
| `agent/tools/builtin/memory.py` | 5 个工具：SaveMemory / RecallMemory / SearchMemory / ResolveMemoryConflict / MemoryGitBackend |
| `docs/adr/ADR-0002-long-term-memory-reversibility.md` | ADR：mem0 对比、备选方案、最终决策、revisit conditions |
| `agent/tools/factory.py:71-110` | KNOWN_BUILTIN_TOOL_NAMES（确认 5 个 memory 工具在内置 38 中） |

---

## Bullet 6: 3 层纵深防御安全体系 — 代码走读

> 简历原文：实现 3 层纵深防御安全体系：工作区路径边界 + 敏感文件 deny 与 mode 权限 fail-closed → CommandGuard 语义级命令检查覆盖绕过变体 → 进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端，配合细粒度工具权限、受控只读浏览器（URL 白名单 + 只读工具集）和人工审批链路

---

### 整体架构

安全体系的 3 层纵深防御，按执行链路从前到后排列：

```
用户指令
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 1: 工作区路径边界 + 敏感文件 deny + mode 权限 fail-closed │
│   WorkspacePolicy  (路径边界 + deny 模式 + 命令黑名单)         │
│   ModePolicy + PermissionProfile  (权限决策 fail-closed)       │
└──────────────────────────┬───────────────────────────────┘
                           │ 通过
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2: CommandGuard 语义级命令检查（覆盖绕过变体）           │
│   正则黑名单扩展 + argv 语义检查 + 高危句式检测                │
│   被 CommandGuard 文档自身定性为 "guardrail, not boundary"     │
└──────────────────────────┬───────────────────────────────┘
                           │ 通过
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 3: 进程沙箱 / Docker 容器隔离（真正的执行边界）          │
│   ProcessBackend + cgroup v2 (CPU/memory 限制 + OOM 检测)    │
│   DockerBackend (网络隔离 + 文件系统隔离 + 资源限制)            │
└──────────────────────────────────────────────────────────┘
```

**旁路防线**（与执行链路正交）：

| 防线 | 文件 | 说明 |
|------|------|------|
| 细粒度工具权限 | `tool_permissions.py` + `run_config.py` | 8 种 Capability + 3 级 Risk + 4 种 Mode |
| 受控只读浏览器 | `browser/policy.py` + `browser/service.py` | URL 白名单 + 默认关闭 + 7 个浏览器工具 |
| 人工审批链路 | `approval.py` + `loop.py:780-853` | 审批请求/响应 + 敏感数据脱敏 |

---

### 第 1 层：工作区路径边界 + 敏感文件 deny + mode 权限 fail-closed

#### 1.1 WorkspacePolicy — 路径边界

**文件**：`agent/workspace_policy.py`

核心类 `WorkspacePolicy`（line 140），构造时接受 3 个参数：

```python
def __init__(
    self,
    workspace_root: str | Path | None = None,
    denied_patterns: tuple[str, ...] | list[str] | None = None,
    command_denylist: tuple[str, ...] | list[str] | None = None,
):  # :141-145
```

**路径边界**：`is_within_workspace()`（`:164-168`）检查 path 是否在 `workspace_root` 或 `additional_roots` 内。`assert_within_workspace()`（`:207-211`）若越界则直接抛出 `PermissionError`。

**多根目录支持**：`add_root()`（`:170-190`）允许注册额外工作区根目录，但有 3 层防护：
1. 禁止重复注册已在主 workspace 内的目录（`:173`）
2. 禁止添加主 workspace 的祖先目录，防止开放主 workspace 外的所有文件（`:174-175`）
3. 禁止添加系统敏感目录（`/etc`, `/proc`, `/sys`, `/dev`, `/root`, `/boot`）（`:176-178`）

```python
_DENY_ROOTS = {Path(p) for p in ("/etc", "/proc", "/sys", "/dev", "/root", "/boot")}  # :137
```

#### 1.2 敏感文件 deny 模式

**文件**：`agent/workspace_policy.py:9-45`

`DEFAULT_DENIED_PATTERNS` 定义了 **35 条** 默认拒绝的 glob 模式，按类别分：

| 类别 | 模式 | 数量 |
|------|------|------|
| Git 仓库 | `.git`, `.git/**` | 2 |
| 环境变量文件 | `.env`, `.env.*`, `**/.env`, `**/.env.*` | 4 |
| 私钥/Cert | `*.pem`, `*.key`, `*.p12`, `*.pfx` | 4 |
| SSH 密钥 | `id_rsa`, `id_ed25519`, `id_ecdsa`, `**/id_rsa`, `**/id_ed25519`, `**/id_ecdsa` | 6 |
| Python 缓存 | `__pycache__`, `__pycache__/**`, `**/__pycache__/**`, `*.pyc` | 4 |
| Node 依赖 | `node_modules`, `node_modules/**`, `**/node_modules/**` | 3 |
| Python 虚拟环境 | `.venv`, `.venv/**`, `venv`, `venv/**` | 4 |
| 类型/Lint 缓存 | `.mypy_cache`, `.mypy_cache/**`, `.pytest_cache`, `.pytest_cache/**`, `.ruff_cache`, `.ruff_cache/**` | 6 |
| Benchmark 产物 | `benchmarks/runs`, `benchmarks/runs/**` | 2 |

> 每个 `**` 变体单独计数，合计 35 条 glob pattern（9 大类）。benchmark runs 中的 `.env` / `.maestro-ci` 等也会被独立 `.env.*` pattern 覆盖。

`is_denied()`（`:222-239`）执行两层匹配：
1. 对 workspace 内的路径，取相对路径 + 每一级目录名 + 绝对路径名作为候选，逐一 fnmatch 比较（`:231-238`）
2. 对 additional_roots 下的路径，用 basename 匹配（`:225-229`）

`assert_read_allowed()`（`:241-245`）和 `assert_write_allowed()`（`:247-251`）在 is_within_workspace 和 is_denied 两道检查都通过后才放行，拒绝时抛出 `PermissionError`。

#### 1.3 命令白名单 + 黑名单

**文件**：`agent/workspace_policy.py:47-134`

`_match_allowlist()`（`:47-72`）定义了 **46 个** 安全命令前缀，按类别：

| 类别 | 前缀 | 数量 |
|------|------|------|
| 版本控制（只读） | `git status`, `git log`, `git diff`, `git show`, `git branch`, `git stash list`, `git stash show` | 7 |
| 测试和构建 | `pytest`, `python -m pytest`, `python3 -m pytest`, `uv run pytest`, `uv run python -m pytest`, `uv run python3 -m pytest`, `uv`, `pip`, `npm test`, `npm run`, `npx`, `yarn`, `cargo`, `make` | 14 |
| 文件查看 | `cat`, `head`, `tail`, `wc`, `sort`, `uniq`, `ls`, `tree`, `find`, `fd`, `rg`, `grep` | 12 |
| 基本工具 | `echo`, `pwd`, `which`, `env`, `df`, `du`, `ps` | 7 |
| 文件操作（低风险） | `mkdir`, `touch` | 2 |
| 包管理 | `pip install`, `pip list`, `pip show`, `pip freeze` | 4 |

> 设计为 **默认关闭**：`_match_allowlist()` 只在 `assert_command_allowed()` 的 denylist 未命中时调用（`:258-259`），作为"黑名单未命中 + 白名单通过 = 放行"的最后一道正面检查。代码注释说明这是一个"软 guardrail，不是硬边界"——真正边界在 sandbox backend。

`DEFAULT_DENYLIST`（`:74-134`）定义了 **59 个** 危险命令正则模式，覆盖：

| 危险类别 | 代表模式 | 数量 |
|------|------|------|
| 递归删除根目录 | `rm -rf /`, `rm -r[f] /`, `rm --recursive /`, `del /[fF] /`, `rmdir /[sS] /` | 5 |
| 格式化/擦除磁盘 | `format`, `mkfs.`, `dd if=`, `dd of=/dev/`, `> /dev/sd[a-z]` | 5 |
| 系统关停 | `shutdown`, `reboot`, `halt`, `poweroff`, `init [06]` | 5 |
| 服务管理破坏 | `systemctl (stop|restart|disable)`, `service ... (stop|restart)` | 2 |
| 进程终止 | `kill -9`, `killall`, `pkill` | 3 |
| Fork bomb | `:(){ :|:& };:` pattern | 1 |
| 任意代码执行 | `perl -e`, `ruby -e`, `php -r`, `python[3] -c`, `python[3] -<<` | 5 |
| 管道到 Shell | `curl\|sh`, `wget\|sh`, `curl\|bash` | 3 |
| 批量文件删除 | `find ... -exec rm`, `find ... -delete`, `xargs rm` | 3 |
| 危险 Git 操作 | `git reset --hard`, `git push --force`, `git branch -D` | 3 |
| 权限修改 | `chmod 777 /`, `chmod -R 777`, `chown -R root` | 3 |
| 写入系统目录 | `> /etc/`, `> /proc/`, `> /sys/`, `tee /etc/`, `tee /proc/`, `sed -i ... /etc\|proc\|sys/` | 6 |
| 移动/复制系统文件 | `cp (etc\|proc\|sys\|.env\|.git/)`, `mv (etc\|proc\|sys\|.env\|.git/)` | 2 |
| 权限提升 | `sudo`, `su -` | 2 |
| 网络/文件系统 | `mount`, `umount`, `iptables`, `nft` | 4 |
| 容器/编排破坏 | `docker rm`, `docker system prune`, `kubectl delete` | 3 |
| SQL 破坏 | `DROP TABLE|DATABASE`, `DELETE FROM ... ;` (无 WHERE) | 2 |
| 命令替换 | `$(...)`, `` `cmd` `` | 2 |

> 第 59 个正则（`` `[^`]*` ``）匹配反引号命令替换。注意第 101 行与第 103 行的 `curl.*\|\s*(ba)?sh` 是重复模式。

#### 1.4 mode 权限 fail-closed

**文件**：`agent/tool_permissions.py:179-185` + `agent/run_config.py`

`fail_closed` 是一个内置 `PermissionProfile`：

```python
"fail_closed": PermissionProfile(
    name="fail_closed",
    allowed_capabilities=frozenset(),       # 不放行任何 Capability
    auto_approve_max_risk=ToolRiskLevel.LOW,       # 自动放行 LOW
    approval_required_max_risk=ToolRiskLevel.LOW,  # 审批仅覆盖 LOW
),  # :179-185
```

**fail-closed 含义**：
- `allowed_capabilities=frozenset()` -- 空集合，任何需要 Capability 的工具都会被 DENY。只有无 Capability 要求的工具（如果有的话）才能存活。
- `approval_required_max_risk=ToolRiskLevel.LOW` -- 审批阈值仅到 LOW，MEDIUM 和 HIGH 都直接 DENY。
- 当 mode 没有配置对应 profile 时，`ModePolicy.permission_profile` 属性（`run_config.py:173-182`）**默认返回 `fail_closed`**，即"配置缺失则拒绝一切"。

```python
@property
def permission_profile(self) -> PermissionProfile:
    profile = self.permission_profiles_by_mode.get(
        self.mode,
        BUILTIN_PERMISSION_PROFILES["fail_closed"],  # 默认 fail_closed
    )
    return merge_denied_tools(profile, self.deny_tools_by_mode.get(self.mode, ()))
```

**4 种 Agent Mode**（`run_config.py:18-23`）：

| Mode | Profile | 行为 |
|------|---------|------|
| `BUILD` | `build_default` | 全部 Capability，LOW+MEDIUM 自动放行，HIGH 需审批 |
| `READ_ONLY` | `read_only_default` | 仅 WORKSPACE_READ + NETWORK_READ + AGENT_STATE，LOW 自动放行，MEDIUM 需审批 |
| `PLAN` | `plan_default` | 同上（WORKSPACE_READ + NETWORK_READ + AGENT_STATE），MEDIUM 自动放行 + 审批 |
| `BYPASS` | `bypass_default` | 全部 Capability 全部自动放行（含 HIGH），不产生审批 |

**权限决策链**（`run_config.py:97-171` `decide_tool()`），按优先级：

```
① mode 限制 → tool.allowed_modes 不含当前 mode → DENY
② mode deny_tools 配置 → tool 被显式拒绝 → DENY
③ profile denied_tools → tool 被显式拒绝 → DENY
④ Capability 不在 profile.allowed_capabilities → DENY
⑤ risk <= auto_approve_max_risk → ALLOW
⑥ risk <= approval_required_max_risk → REQUIRE_APPROVAL
⑦ 都不满足 → DENY
```

---

### 第 2 层：CommandGuard 语义级命令检查覆盖绕过变体

**文件**：`agent/tools/command_guard.py`

该文件在设计上被文档自身明确定性（`:2-8`）：

> "This is a **guardrail, not a boundary** (per industry consensus: Claude Code's 2025 CVEs demonstrated that regex command validation is fundamentally bypassable). The real boundary is the execution backend (ProcessBackend / DockerBackend)."

#### 2.1 调用链

CommandGuard 在 `BashTool.execute()` 中调用（`agent/tools/builtin/bash.py:73-79`）：

```python
if self._guard.check(cmd) is CommandVerdict.DENY:
    reason = f"command_guard:{self._guard.last_reason or 'denied'}"
    emit_sandbox_event("denied", reason=reason, command=cmd, tool="Bash")
    return ToolResult(text="Error: Command denied by sandbox command guard", error_type="permission_denied")
```

执行顺序：**WorkspacePolicy.assert_command_allowed() 先于 CommandGuard.check()**（bash.py:68-72），WorkspacePolicy 的 blacklist/allowlist 是第一道防线，CommandGuard 是第二道。再之后才是 sandbox backend 执行。

#### 2.2 轻量级命令分词器

`tokenize_command()`（`:68-113`）是一个**非完整 Bash 解析器**——支持单/双引号、管道、重定向、分号的 token 分割，但不解析 heredoc、进程替换 `<(cmd)`、brace expansion 等复杂语法。设计目标是足够的 argv 级精度，用于后续语义检查。

#### 2.3 扩展黑名单——绕过变体覆盖

`_EXTRA_DENYLIST`（`:32-60`）定义了 **18 个** 额外正则模式，专门覆盖基础 denylist（`workspace_policy.py` 的 `DEFAULT_DENYLIST` 42 个）未能捕获的绕过变体：

| 绕过类别 | 原始变体能被绕过的原因 | 扩展覆盖 | 行号 |
|------|------|------|------|
| `rm` flag 重排 | `rm -fr /` vs `rm -rf /`（原只匹配 `rm -rf`） | `rm -[a-z]*f[a-z]*r[a-z]*` + `rm` with `--` | `:33-35` |
| `chmod` 八进制/符号变体 | 原只匹配 `chmod 777 /` | 0?[0-7]{3,4} (前导零), 符号模式 `[a-z+=]+` 组合 | `:37-38` |
| `kill` 信号名变体 | 原只匹配 `kill -9` | `kill -(SIGKILL\|KILL\|9)\s+\d+` | `:40` |
| 任意代码执行 | 原缺 `node -e`, `deno eval`, `awk ... system()` | 新增 node/deno/awk 模式 | `:42-44` |
| base64 管道到 shell | 原 `curl\|sh` 没覆盖 base64 | `base64 -d \| (ba)?sh` | `:46` |
| mv/cp 目标落在保护路径 | 原只匹配 "移动文件到 /etc" 不精确 | 完整保护路径 + 隐藏文件后缀 | `:48` |
| nc 数据外泄 | 原缺 | `nc` + `/dev/tcp/` 反向 shell | `:50-51` |
| fork bomb | 原缺 | `:(){ :` pattern | `:53` |
| `$IFS` 变量空格绕过 | `rm$IFS/` 等价于 `rm /` | `\$IFS` literal | `:55` |
| 反斜杠逃逸命令名 | `r\m` 在某些 shell 中等价于 `rm` | `\\[a-z]\s` | `:57` |
| 资源耗尽 | 原缺 | `yes > /dev/null` (无限写 null) | `:59` |

#### 2.4 argv 语义检查

`_check_argv()`（`:190-211`）对 7 个危险命令做逐 token 语义级检查：

| 命令 | 检查方法 | 逻辑 | 行号 |
|------|------|------|------|
| `rm` | `_check_rm()` | 仅当 `-r` + `-f` 同时存在时检查目标是否命中 `_DENY_PATHS` 或 workspace 外路径。`$IFS` 变体归一化后再判断 | `:213-231` |
| `mv` / `cp` | `_check_mv_cp()` | 目标以 `_DENY_PATHS` 前缀开头 → DENY | `:233-242` |
| `chmod` | `_check_chmod()` | 目标以 `_DENY_PATHS` 前缀开头 → DENY。0777/777/a+rwx/a=rwx 在 `/` 或 `/tmp` → DENY | `:244-257` |
| `timeout` | `_check_timeout()` | 超时值 0 < t <= 600 秒；然后**递归检查被包装的命令**（`timeout 5 rm -rf /` 不能绕过） | `:269-287` |
| `curl` / `wget` | `_check_curl_wget()` | `@<protected-path>` 数据外泄参数 → DENY | `:259-267` |

**`rm` 的特殊处理**（`:139`）：denylist 中的 `rm` 模式被排除（因为 `rm -rf /` 正则会匹配任何包含 `/` 的 workspace 内路径导致误杀），rm 的判断完全交给 argv 语义检查。

#### 2.5 高危句式检测

两个独立的高危句式检测方法，不依赖 denylist：

**`_has_pipe_to_shell()`**（`:166-176`）：检测 `| sh` / `| bash` 以及 `/usr/bin/env sh -c` 链路。支持 6 种 shell（`":27": _SHELL_INTERPRETERS = {"sh", "bash", "zsh", "ksh", "dash", "fish"}`）。

**`_has_protected_redirect()`**（`:178-186`）：对 tokenized 命令流检测 `>` / `>>` 后接 `_DENY_PATHS`（`/etc`, `/proc`, `/sys`, `/dev`, `/root`, `/boot`, `/var`——共 7 个，`:25`）。

#### 2.6 默认放行设计

`check()`（`:128-162`）的核心逻辑：

```
① rm 以外 → 扩展 denylist 正则扫描 → 命中 → DENY
② 管道到 shell / 重定向到保护路径 → DENY
③ 7 个危险命令 → argv 语义检查 → DENY
④ 未命中 → ALLOW（默认放行）
```

**default-allow 设计**：未知命令默认通过（`:162`），不阻塞合法工作流。防御重心落在**已知危险模式**和**argv 级精确判断**上。

---

### 第 3 层：进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端

#### 3.1 可插拔后端抽象

**文件**：`agent/tools/sandbox/base.py`

`ExecutionBackend` Protocol（`:122-156`）定义统一接口：

```python
class ExecutionBackend(Protocol):
    def is_available(self) -> bool: ...
    async def run(self, command: str, *, timeout: float | None = None, cwd: Path | None = None) -> SandboxResult: ...
    async def run_background(self, command: str, *, cwd: Path | None = None) -> BackgroundProcessHandle: ...
```

`SandboxResult`（`:99-107`）携带 7 个字段（`:99-118` 含 `__str__`/`to_json` 方法）：`exit_code`, `stdout`, `stderr`, `duration_ms`, `timed_out`, `oom_killed`, `degraded`。后三个字段是安全关注点。

#### 3.2 后端工厂

**文件**：`agent/tools/sandbox/factory.py`

双后端注册表（`:15-18`）：

```python
_BACKENDS: dict[str, type[ExecutionBackend]] = {
    "process": ProcessBackend,
    "docker": DockerBackend,
}
```

`build_execution_backend()`（`:27-38`）根据 `name` 反射构造，自动过滤各后端接收的 kwargs：

| 后端 | 接收参数 |
|------|------|
| `process` | `timeout`, `memory_mb`, `cpus` |
| `docker` | `image`, `memory_mb`, `cpus`, `timeout` |

#### 3.3 ProcessBackend + cgroup v2 资源限制

**文件**：`agent/tools/sandbox/process_backend.py`

##### 3.3.1 进程沙箱——进程组隔离

`run()`（`:154-238`）使用 `asyncio.create_subprocess_shell(command, start_new_session=True)`（`:166-173`）创建独立**进程组**（pgid == pid）。超时终止时调用 `_kill_process_tree()`（`:40-54`）：

```python
os.killpg(proc.pid, signal.SIGKILL)  # 杀整个进程组，不留孤儿
```

这确保 `sh -c "sleep 60"` 超时后 shell 和 sleep 都被回收，不会持有管道不释放。

##### 3.3.2 cgroup v2 资源限制

**文件**：`agent/tools/sandbox/cgroup.py`

设计文档注释声明（`:3-10`，引用 design.md Decision 5）：
- 每个 `run()` 创建自己的临时子 cgroup（`asterwynd-{pid}-{counter}`），并发 run 之间不共享 memory budget，不会互相 OOM kill
- `memory.max` + `memory.swap.max=0`（hard no-swap cap），防止 malloc bomb 通过 swap 绕过 OOM killer
- `cpu.max` 配额：`quota = max(1000, round(cpus * 100000))`，period 固定 100ms（`:242-245`）
- cpuset 初始化从父 cgroup 继承（`:248-254`），避免空 cpuset 导致 pid attach 失败（cgroup v2 known gotcha）

**degrade-first 策略**（`:108-130`）：

```python
def _setup_cgroup(self) -> tuple[CgroupController | None, bool]:
    needs_limits = self.memory_mb is not None or self.cpus is not None
    if not needs_limits:
        return None, False                            # 没配置限制 → 跳过
    if not self._cgroup_available():
        self._emit_degraded_once()                    # cgroup 不可用 → degraded
        return None, True
    try:
        controller = self._controller_factory()
        controller.create()
        return controller, False
    except Exception:
        self._emit_degraded_once()                    # 创建失败 → degraded
        return None, True
```

- `_cgroup_available()` 首次调用时 probe：通过 `CgroupV2Controller.is_supported()` 尝试在 `/sys/fs/cgroup` 下创建 + 删除测试 cgroup（`:110-126`），probe 结果缓存。
- 降级时 `degraded` 事件**每 ProcessBackend 实例最多 emit 一次**（`:132-135`），避免日志风暴。
- 每个 `run()` 的 `SandboxResult.degraded` 仍会准确标记该次执行的降级状态（`:118-131`）。

**OOM 检测**（`cgroup.py:256-264`）：`oom_killed()` 比较 `memory.events` 中 `oom_kill` 计数器的**累积值 vs 创建时基线**（counter 永不递减），因此能精确判断是否有进程被 OOM 杀死。

**pid 复用防护**（`cgroup.py:197-212`）：`cleanup()` 在发出 `cgroup.kill` 前验证 `_pid_starttime()`（读取 `/proc/{pid}/stat` 中的 starttime 字段——`:66-85`）与创建时记录的基线一致，避免 pid 被复用后误杀无关进程。

##### 3.3.3 注意：cgroup 需要配置启用

`memory_mb` / `cpus` 在 `SandboxConfig`（`config.py:235-236`）中**默认 `None`**，即默认不启用资源限制。需要通过 `asterwynd.yaml` 的 `sandbox.memory_mb` 和 `sandbox.cpus` 配置才会生效：

```yaml
sandbox:
  memory_mb: 512    # 需显式配置
  cpus: 1.0         # 需显式配置
```

#### 3.4 DockerBackend — 容器隔离

**文件**：`agent/tools/sandbox/docker_backend.py`

DockerBackend 提供真正的容器级安全边界：

| 隔离维度 | 机制 | Docker flag | 代码行 |
|------|------|------|------|
| 网络 | 无网络，不能外泄数据或访问外部 | `--network none` | `:103` |
| 文件系统 | 仅挂载 workspace 目录 | `-v <workspace>:/workspace -w /workspace` | `:115` |
| 资源 | CPU/内存限制（同 cgroup，需要 Docker daemon 启用 cgroup v2 domain controller） | `--memory` / `--cpus` | `:110-113` |
| 生命周期 | 运行后自动删除容器 | `--rm` | `:102` |
| 超时 | `docker kill` 杀掉超时容器 | asyncio.wait_for + proc.kill + rm orphan | `:143-169` |

**资源限制默认关闭**（`:80`）：`memory_mb: int | None = None`, `cpus: float | None = None`。注释说明原因（`:77-79`）："Some hosts (incl. this dev environment) do not configure cgroup v2 domain controllers, causing docker run to fail."

**sg docker 适配**（`:32-64`）：`_needs_sg()` 检测 `docker info` 能否直接连接 daemon；如果不能，通过 `sg docker -c "<command>"` 方式包装——适配宿主机 supplementary group 不包含 `docker` 的场景。

**超时孤儿容器清理**（`:185-202`）：通过 `--cidfile` 机制记录容器 ID，超时后 `docker rm -f` 清理因 `docker client` 被 SIGKILL 而残留 daemon 中的容器。

#### 3.5 双后端切换

**文件**：`agent/config.py:224-237`

```python
class SandboxConfig:
    backend: str = "process"        # "process" 或 "docker"
    image: str = "alpine:latest"    # docker 后端用的镜像
    memory_mb: int | None = None    # 可选，需 cgroup v2
    cpus: float | None = None       # 可选，需 cgroup v2
    timeout_seconds: float = 30.0
```

默认为 `process` 后端。切换到 docker 需在 `asterwynd.yaml` 中配置 `sandbox.backend: docker`。

**后端不可用时的 fail-fast**（`factory.py:48-68`）：`build_sandbox_from_config()` 在构建后端后检查 `is_available()`，Docker 不可用时 **抛出 RuntimeError 而不是静默退回 ProcessBackend**——静默降级会丢失用户期望的容器隔离。

#### 3.6 Sandbox 事件可观测

**文件**：`agent/sandbox_events.py`

所有 sandbox 组件通过 `emit_sandbox_event()`（`:64-81`）发送 4 类结构化事件到 trace 层：

| 事件 | 含义 | 触发位置 |
|------|------|------|
| `denied` | 命令被 workspace policy 或 command guard 拒绝 | `bash.py:70,75` |
| `kill` | 超时后被 kill | `process_backend.py:203`, `docker_backend.py:157` |
| `oom` | OOM killer 介入 | `process_backend.py:186,210` |
| `degraded` | cgroup 不可用，降级为无限制 | `process_backend.py:135` |

事件经 `contextvars.ContextVar` 传递到每次 run 的 trace recorder（`:37-38`），支持并行+后台执行的 trace 关联（通过 `tool_call_id` contextvar）。

---

### 防线 A：细粒度工具权限

**文件**：`agent/tool_permissions.py` + `agent/run_config.py`

#### A.1 权限模型

**8 种 ToolCapability**（`:7-15`）：

```python
class ToolCapability(str, Enum):
    WORKSPACE_READ = "workspace_read"
    WORKSPACE_WRITE = "workspace_write"
    COMMAND_EXECUTE = "command_execute"
    NETWORK_READ = "network_read"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    AGENT_STATE = "agent_state"
    SUBAGENT_CONTROL = "subagent_control"
    BROWSER_CONTROL = "browser_control"
```

**3 级 ToolRiskLevel**（`:18-21`）：`LOW`, `MEDIUM`, `HIGH`。

**4 种 ToolOrigin**（`:24-29`）：`BUILTIN`, `MCP`, `PLUGIN`, `SUBAGENT`, `BROWSER`。

**预定义权限常量**（`:109-141`）为各常见能力组合绑定了风险等级：

| 常量 | Capability | Risk |
|------|------|------|
| `WORKSPACE_READ_PERMISSION` | WORKSPACE_READ | LOW |
| `WORKSPACE_WRITE_PERMISSION` | WORKSPACE_WRITE | MEDIUM |
| `COMMAND_EXECUTE_PERMISSION` | COMMAND_EXECUTE | HIGH |
| `NETWORK_READ_PERMISSION` | NETWORK_READ | LOW |
| `AGENT_STATE_PERMISSION` | AGENT_STATE | MEDIUM |
| `SUBAGENT_CONTROL_PERMISSION` | SUBAGENT_CONTROL | MEDIUM |
| `BROWSER_READ_PERMISSION` | BROWSER_CONTROL | MEDIUM |

#### A.2 只读能力集

**文件**：`agent/tool_permissions.py:98-102`

```python
READ_ONLY_CAPABILITIES = frozenset({
    ToolCapability.WORKSPACE_READ,
    ToolCapability.NETWORK_READ,
    ToolCapability.AGENT_STATE,
})
```

**3 种 Capability**，不含 WORKSPACE_WRITE、COMMAND_EXECUTE、EXTERNAL_SIDE_EFFECT。READ_ONLY / PLAN mode 共用此集。

#### A.3 6 个内置 PermissionProfile

**文件**：`agent/tool_permissions.py:144-185`

| Profile | allowed_capabilities | auto_approve | approval_required |
|------|------|------|------|
| `build_default` | 全部 8 种 | MEDIUM | HIGH |
| `build_legacy_auto_high_risk` | 全部 8 种 | HIGH | HIGH |
| `bypass_default` | 全部 8 种 | HIGH | HIGH |
| `read_only_default` | 3 种（只读） | LOW | MEDIUM |
| `plan_default` | 3 种（只读） | MEDIUM | MEDIUM |
| `fail_closed` | 0 种（空） | LOW | LOW |

---

### 防线 B：受控只读浏览器

#### B.1 浏览器工具默认关闭

**文件**：`agent/config.py:67-79`

```python
class BrowserConfig:
    enabled: bool = False                    # 默认关闭
    url_allowlist: tuple[str, ...] = ()      # 空白名单 = 拒绝所有
    idle_timeout: int = 300
    navigation_timeout: int = 30
    read_timeout: int = 15
    screenshot_timeout: int = 10
```

浏览器工具只在 `enabled=True` 且 playwright 已安装时才注册（`factory.py:357-358`），否则不暴露给 Agent。

#### B.2 URL 白名单

**文件**：`agent/browser/policy.py`

`BrowserPolicy.is_url_allowed()`（`:38-61`）实现 3 层检查：

```
① 空白名单 → 拒绝所有 URL                             (:46-47)
② 非 http/https scheme → 拒绝                         (:53-54)
③ http:// 只能由白名单中显式 http 条目放行               (:57-58)
④ https:// 匹配 bare domain 或 https 条目               (:61)
```

**域名匹配**（`_host_matches()`, `:98-111`）：

| 白名单模式 | 匹配 | 不匹配 |
|------|------|------|
| `docs.python.org` | `docs.python.org` | `sub.docs.python.org` |
| `*.example.com` | `sub.example.com` | `example.com`（缺少前导 `.`） |

#### B.3 只读工具集

**文件**：`agent/tools/builtin/browser_tools.py:14-22`

`BROWSER_TOOL_CLASSES` 包含 **7 个**工具：

| 工具 | 类 | 能力 |
|------|------|------|
| WebNavigate | `BrowserNavigateTool` | 导航到 URL（受 is_url_allowed 约束） |
| WebGetContent | `BrowserGetContentTool` | 读取页面文本 |
| WebScreenshot | `BrowserScreenshotTool` | 截取页面截图 |
| WebScroll | `BrowserScrollTool` | 滚动页面 |
| WebListTabs | `BrowserListTabsTool` | 列出标签页 |
| WebSwitchTab | `BrowserSwitchTabTool` | 切换标签页 |
| WebCloseTab | `BrowserCloseTabTool` | 关闭标签页 |

全部 7 个工具共享 `BROWSER_READ_PERMISSION`（`ToolCapability.BROWSER_CONTROL`, `ToolRiskLevel.MEDIUM`）——MEDIUM 风险在 read_only mode 下需要审批。

**没有写入/提交/下载工具**：浏览器工具集中不包含表单填写、文件上传、数据提交等能力。所有导航操作在 `BrowserSession.navigate()` 处被 `assert_url_allowed()` 拦截（`session.py:32`），超时不抛异常而是返回 error 字典（`:39-51`）。

#### B.4 浏览器架构安全性

**惰性启动**（`service.py:53`）：浏览器仅在首次工具调用时才启动，不预启动；Playwright 导入也延迟到启动时（`:58-65`），避免在只做代码分析的 session 中引入不必要的浏览器运行时。

**产物隔离**（`policy.py:115-117`）：浏览器产物目录仅限于 `<workspace_root>/.asterwynd/browser-artifacts/`，由 `WorkspacePolicy.assert_write_allowed()` 守卫。

---

### 防线 C：人工审批链路

**文件**：`agent/approval.py`

#### C.1 审批请求/响应模型

`ApprovalRequest`（`:34-68`）携带完整决策上下文：

```python
@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str       # UUID
    tool_call_id: str
    tool_name: str
    mode: str              # BUILD / READ_ONLY / PLAN / BYPASS
    capability: list[str]  # 工具所需 Capability 列表
    risk: str              # LOW / MEDIUM / HIGH
    origin: str            # BUILTIN / MCP / PLUGIN / SUBAGENT / BROWSER
    reason: str            # 审批原因（来自 PermissionDecision）
    profile_name: str      # 当前生效的 profile 名
    redacted_args: dict    # 已脱敏的参数
    args_summary: str      # 参数摘要（限 2000 字符）
```

`ApprovalResponse`（`:71-79`）三种状态：`APPROVED`, `DENIED`, `UNAVAILABLE`。

#### C.2 Fail-Closed 审批处理器

**文件**：`agent/approval.py:87-93`

```python
class FailClosedApprovalHandler:
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        return ApprovalResponse(
            approval_id=request.approval_id,
            status=ApprovalDecisionStatus.UNAVAILABLE,  # 永远 UNAVAILABLE
            reason="approval is unavailable in this runtime",
        )
```

`UNAVAILABLE` 在 AgentLoop 的处理中（`loop.py:831-853`）等价于**拒绝**：`pre_denied_error_type = "approval_unavailable"`，工具不执行。这是在非交互式环境（如 benchmark / CI / 无 TTY）下的 fail-closed 行为。

#### C.3 CLI 交互式审批

**文件**：`agent/approval.py:96-120`

```python
class CliApprovalHandler:
    def __init__(self, *, interactive: bool):
        self.interactive = interactive

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        if not self.interactive or not sys.stdin.isatty():
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.UNAVAILABLE,  # 非交互 → fail-closed
            )
        print(_render_cli_prompt(request), file=sys.stderr)
        answer = input("Approve? [y/N] ").strip().lower()
        if answer in {"y", "yes"}: ...
```

**默认答案 `N`**（`:109`）：用户输入回车不做明确选择时，行为等同拒绝。

#### C.4 敏感数据脱敏

**文件**：`agent/approval.py:15-23, :160-189`

审批请求展示前自动脱敏 3 层：

| 层级 | 机制 | 代码位置 |
|------|------|------|
| Key 名检测 | 参数 key 含 `key\|token\|secret\|password\|credential\|authorization\|api_key` → 整个 value 替换为 `[redacted]` | `:15-18` + `:165-167` |
| 字符串模式 | `Authorization: Bearer ...` / `sk-...` / `api_key=...` → 匹配部分替换为 `[redacted]` | `:19-23` + `:176-178` |
| 参数长度限制 | JSON 序列化超过 2000 字符时截断 | `:25` + `:152-157` |

#### C.5 审批在 AgentLoop 中的接线

**文件**：`agent/loop.py:780-853`

审批决策仅在 `PermissionDecision.type == REQUIRE_APPROVAL` 时触发（`:788`）。审批被拒/不可用时工具不执行，`pre_denied_result` 注入 messages 供模型观察（`:833-853`）。审批成功（`approval_granted=True`）则工具正常进入 Phase 2 执行（`:858`）。

---

### 关键文件索引

| 文件 | 内容 | 防御层 |
|------|------|------|
| `agent/workspace_policy.py` | WorkspacePolicy: 路径边界 + deny 模式 + 命令黑白名单 | Layer 1 |
| `agent/tool_permissions.py` | ToolCapability (8) / ToolRiskLevel (3) / PermissionProfile (6) / 预定义权限 | 防线 A |
| `agent/run_config.py` | AgentMode (4) / ModePolicy / fail_closed 默认 / 权限决策链 | Layer 1 + 防线 A |
| `agent/tools/command_guard.py` | CommandGuard: tokenizer + 扩展黑名单 (18) + argv 语义检查 (7 命令) + 高危句式 | Layer 2 |
| `agent/tools/sandbox/base.py` | ExecutionBackend Protocol + SandboxResult + BackgroundProcessHandle | Layer 3 |
| `agent/tools/sandbox/process_backend.py` | ProcessBackend: 进程组隔离 + cgroup v2 集成 + degrade-first | Layer 3 |
| `agent/tools/sandbox/cgroup.py` | CgroupV2Controller: memory.max + swap.max + cpu.max + cpuset + cleanup pid-reuse guard | Layer 3 |
| `agent/tools/sandbox/docker_backend.py` | DockerBackend: --network none + -v mount + --rm + orphan cleanup | Layer 3 |
| `agent/tools/sandbox/factory.py` | build_execution_backend: process/docker 双后端工厂 + fail-fast | Layer 3 |
| `agent/sandbox_events.py` | SandboxEventSink: denied/kill/oom/degraded 事件 + contextvars | Layer 3 (可观测) |
| `agent/config.py` | SandboxConfig / BrowserConfig / PermissionsConfig / ToolsConfig | 配置入口 |
| `agent/tools/builtin/bash.py` | BashTool: 三层检查调用链（policy → guard → sandbox） | 接线点 |
| `agent/browser/policy.py` | BrowserPolicy: URL 白名单 + host_matches（精确 / 通配符） | 防线 B |
| `agent/browser/service.py` | BrowserService: 惰性启动 + 标签页生命周期 | 防线 B |
| `agent/browser/session.py` | BrowserSession: 策略约束的页面操作 + 超时容错 | 防线 B |
| `agent/tools/builtin/browser_tools.py` | BROWSER_TOOL_CLASSES: 7 个只读浏览器工具 | 防线 B |
| `agent/approval.py` | ApprovalRequest/Response + FailClosedApprovalHandler + CliApprovalHandler + 脱敏 | 防线 C |
| `agent/loop.py:780-853` | Phase 1 审批接线：审批请求 → 响应 → 预拒绝结果回填 | 防线 C |

---

## Bullet 7: 全链路可观测体系与 Benchmark 评测闭环 — 代码走读

> 简历原文：建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；72 个 coding 任务（34 本地 = 22 A 轨回归基线 + 12 B 轨当前演进 + 38 SWE-bench Verified 子集）在 git worktree / Docker 隔离执行，pass@1/pass^k/成本（cache-aware）与 fault_owner 归因统计，场景×难度分层覆盖矩阵，支持跨 Agent 配对比较与 CI 回归门禁

---

### 1. TraceRecorder — 全链轨迹记录

**文件**：`agent/trace_recorder.py`

#### 1.1 数据结构

`TraceRecorder`（line 23）是所有运行时事件的结构化记录器。每个事件被编码为一个 `TraceStep`（line 16）：

```python
@dataclass
class TraceStep:
    step: int                       # 自增序号
    type: str                       # 事件类型（18 种，见下文）
    data: dict[str, Any]            # 事件载荷
    timestamp: float                # 挂钟时间戳 (line 20)
```

时间戳打在 `TraceStep` 层，而非 data 载荷内部（line 52-61 注释说明），保持事件数据清洁且向后兼容。`schema_version` 固定为 `"1.1"`（line 242）。

#### 1.2 run identity 体系

构造函数参数（line 24-38）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务标识（benchmark 场景下由 runner 注入） |
| `full_trace` | bool | 全量追踪开关，**默认 `False`**（line 27，保留为序列化兼容用途） |
| `mode` | str | 运行模式，默认 `"build"`（line 28） |
| `session_id` | str \| None | 会话标识，**默认 `None`**（line 29，由外部注入） |
| `run_id` | str \| None | 运行标识，**默认 `None`**（line 30，由外部注入） |

`set_run_identity()`（line 40-48）允许运行时补充注入 `session_id` / `run_id`。

#### 1.3 事件类型清单（共 18 种）

所有记录事件通过 `record(step_type, **data)` 统一入口（line 51-61），具体事件类型包装为命名方法：

| 事件类型 | 方法 | 行号 | 说明 |
|----------|------|------|------|
| `run_started` | `record_run_started()` | 63 | 运行开始，携带 mode / session_id / run_id |
| `mode_changed` | `record_mode_changed()` | 73 | 模式切换（如 build → plan） |
| `llm_iteration` | `record_iteration()` | 79 | 每次 LLM 调用：iteration 序号、preview、tool_calls、输入/输出 token、model、finish_reason |
| `tool_call` | `record_tool_call()` | 100 | 工具调用发起（tool_name + arguments） |
| `tool_result` | `record_tool_result()` | 103 | 工具调用结果（tool_name, status, duration_ms, observation, error_type） |
| `sandbox` | `record_sandbox_event()` | 145 | 沙箱事件（denied/kill/oom/degraded） |
| `approval_request` | `record_approval_request()` | 155 | 权限审批请求 |
| `approval_response` | `record_approval_response()` | 158 | 权限审批响应 |
| `edit` | `record_edit()` | 161 | 文件编辑操作（path, status, summary） |
| `memory_compaction` | `record_compaction()` | 164 | 上下文压缩统计（before/after messages + tokens + tiers） |
| `parallel_execution_start` | `record_parallel_execution()` | 182 | 并行工具执行组 |
| `diff` | `record_diff()` | 185 | diff 快照（path + summary） |
| `test` | `record_test()` | 188 | 测试执行记录（command, exit_code, duration_ms, output） |
| `planning_state_updated` | `record_planning_state()` | 203 | 计划状态快照更新 |
| `plan_document` | `record_plan_document()` | 206 | 计划文档事件（事件类型 + document dict） |
| `llm_error` | `record_llm_error()` | 220 | 结构化 LLM 调用失败（error_type + message） |
| `completion` | `record_completion()` | 228 | 运行完成（status, content, duration_seconds） |
| `benchmark_preflight` | `record()` 内联调用 | runner.py:330-335 | Benchmark 预检（docker 环境探测） |

#### 1.4 序列化与持久化

- `to_dict()`（line 236）：产出完整 trace dict，含 task_id、mode、duration_seconds、steps 数组
- `to_json()`（line 251）：JSON 字符串，`ensure_ascii=False`
- `write_to_file(path)`（line 254）：`errors="replace"` 写出文件

#### 1.5 SandboxSink 适配器

`TraceRecorderSandboxSink`（line 258-269）将沙箱事件桥接到 TraceRecorder 的 `record_sandbox_event`，非阻塞追加。

#### 1.6 集成点

在 `benchmarks/runner.py` 中，每个 task 启动时创建独立的 `TraceRecorder` 实例（line 296-301）：

```python
trace = TraceRecorder(
    task_id=loaded.task.id,
    mode=self.run_config.mode.value,
    run_id=agent_run_id,
)
```

runner 通过 `trace.record_diff()`（line 368）、`trace.record_test()`（line 504）、`trace.record_completion()`（line 335, 399, 469, 553, 560）打点，最终 `trace.write_to_file()` 写入 `trace.json`（line 575），存放在每个 task 的输出目录 `tasks/<task_id>/trace.json`（`TaskArtifacts`，line 286-288）。

---

### 2. CostLedger — 三层成本归因 + cache-aware 定价

**文件**：`agent/cost_tracker.py`

#### 2.1 模型定价表（cache-aware 四档）

`MODEL_PRICES`（line 15-33）包含 17 个模型的四档价格（USD / 1M tokens，fresh input / cache read / cache write / output 的顺序）：

| 模型 | Input ($/1M) | Cache Read | Cache Write | Output ($/1M) |
|------|-------------|-----------|-------------|---------------|
| gpt-4o | 2.50 | 0.25 | 3.125 | 10.00 |
| gpt-4o-mini | 0.15 | 0.015 | 0.1875 | 0.60 |
| gpt-5 | 3.75 | 0.375 | 4.6875 | 15.00 |
| claude-sonnet-4 / -4-6 / -5 | 3.00 | 0.30 | 3.75 | 15.00 |
| claude-opus-4 | 15.00 | 1.50 | 18.75 | 75.00 |
| claude-opus-4-6 / -4-7 / -4-8 / -5 | 5.00 | 0.50 | 6.25 | 25.00 |
| claude-fable-5 | 10.00 | 1.00 | 12.50 | 50.00 |
| claude-haiku-3.5 | 0.80 | 0.08 | 1.00 | 4.00 |
| claude-haiku-4-5 | 1.00 | 0.10 | 1.25 | 5.00 |
| deepseek-chat | 0.27 | 0.027 | 0.3375 | 1.10 |
| deepseek-reasoner | 0.55 | 0.055 | 0.6875 | 2.19 |
| deepseek-v4-flash | 0.0 | 0.0 | 0.0 | 0.0（自托管近零成本档） |

**关键升级（评测升级）**：定价从两档（input/output）升级为 **cache-aware 四档**。cache read = 0.1× fresh input，cache write = 1.25× fresh input（Anthropic prompt-caching 经济模型，5 分钟 TTL），注释见 line 9-12。`PRICING_TABLE_VERSION = "2026-08-17"`（line 13）随报告披露。未知模型 fallback 用表内平均价估算（`_AVG_INPUT_PRICE` / `_AVG_OUTPUT_PRICE`，line 37-38），永不为 0 静默少计。

**注意**：定价是写死在代码中的常量表。如需支持新模型或价格变动，需修改源码。这不是运行时可配置的。

#### 2.2 按前缀匹配的成本计算

- `compute_cost(model, input_tokens, output_tokens)`（line 58-63）：两档（无 cache）成本，按 `MODEL_PRICES` 的 key 长度降序做 `startswith` 前缀匹配，避免短前缀误命中（如 `gpt-4o` 匹配 `gpt-4o-mini` 之前）。CostLedger 的 `record()` 走这条路径。
- `compute_cost_cached(model, input_tokens, cache_read_tokens, cache_write_tokens, output_tokens)`（line 66-100）：**四档 cache-aware** 成本，返回 `CostEstimate(cost, known)`；unknown 模型用表内平均价估算并记 `known=False`。
- `cache_hit_rate(cache_read_tokens, fresh_input_tokens)`（line 103-112）：cache 命中率 = cache_read / (cache_read + fresh)，cache-write 是一次性写成本不算命中。
- `format_cost(cost)`（line 115-120）：小额成本显示 6 位小数。

#### 2.3 CostLedger 三层归因（"三层"的出处）

`CostLedger` 类（line 123-227）是成本的财务记账，与 trace（过程记录）解耦。

- **`record()`**（line 141-164）：记录单次 LLM 调用的成本，入参携带三个归因维度：
  - `session_id`：按会话归因
  - `phase`：按运行阶段归因（building / review / planning / bypass，由 `observability.py:PHASE_BY_MODE` 映射）
  - `tool_name`：按工具归因（可为 None）
- **`bill()`**（line 168-187）：返回三个维度的聚合结果，这就是简历中"**三层成本归因**"的来源：

```python
return {
    "by_session": by_session,   # 第一层：按 session
    "by_phase": by_phase,       # 第二层：按 phase
    "by_tool": by_tool,         # 第三层：按 tool
}
```

每层的每个 bucket 包含 `tokens`（总 token 数）和 `cost`（累计费用）两个字段。

#### 2.4 持久化

- **`flush(path)`**（line 189-206）：将新增条目追加为 JSONL 文件，使用 `_flushed_count` 游标防止重复写入。同一个 Ledger 实例可被父 agent 和子 agent 共享，各自在 run end 时 flush。
- **`load(path)`**（line 208-226）：从 JSONL 恢复条目。加载后 `_flushed_count` 已推进，后续 flush 只写新条目。

**注意**：`CostLedger` 的持久化是**显式**的——调用方决定何时 flush（通常是 run 结束）。没有自动 flush 机制。

#### 2.5 与 TraceRecorder 的关联

TraceRecorder 的 `record_iteration()` 携带 `input_tokens` / `output_tokens` / `model` 字段（line 84-87），但 TraceRecorder 本身不计算成本。CostLedger 是独立的财务记录，二者通过 AgentLoop 的 Hook 层协同——`TracingHook` 打 trace 点，`TokenBudgetHook` / 调用方同步记入 Ledger。

**benchmark 侧的关联**（评测升级）：`agent/loop.py` 的 token 计数器在评测升级后记录 `cache_read` / `cache_creation`（loop.py:553-558, 640-645），`TaskResult` / `RunMetadata` 也新增了 `cache_read_tokens` / `cache_write_tokens` 字段（`benchmarks/models.py:83-84`），供 `$/resolved-task` 用 `compute_cost_cached` 精确核算。

---

### 3. ErrorClassifier — 错误类型自动打标

**文件**：`agent/observability.py`

#### 3.1 错误分类体系

`ErrorCategory` 枚举（line 20-27）定义了 5 个结构化错误类别：

| 类别 | 值 | 说明 |
|------|-----|------|
| PERMISSION_DENIED | `"permission_denied"` | 权限拒绝 |
| NETWORK_TIMEOUT | `"network_timeout"` | 网络超时/限流 |
| MODEL_ERROR | `"model_error"` | 模型侧错误 |
| PARAMETER_ERROR | `"parameter_error"` | 参数/工具错误 |
| UNKNOWN | `"unknown"` | 兜底未知 |

#### 3.2 三级分类优先级

`ErrorClassifier.classify()`（line 106-133）采用确定性三级优先级：

**优先级 1: 结构化 `error_type` 字段**（line 114-117）

`_ERROR_TYPE_TO_CATEGORY` 字典（line 45-65）包含 **17 条映射**：

| error_type | 类别 |
|------------|------|
| `permission_denied` / `permission` / `approval_required` / `approval_denied` / `approval_unavailable` | PERMISSION_DENIED |
| `timeout` / `network_timeout` / `network_error` / `rate_limit` | NETWORK_TIMEOUT |
| `parse_error` / `parameter_error` / `invalid_argument` / `unknown_tool` | PARAMETER_ERROR |
| `model_error` | MODEL_ERROR |
| `mcp_error` / `resource_exhausted` / `unavailable` | UNKNOWN |

**优先级 2: `finish_reason` 字段**（line 119-123）

- `max_tokens` / `length` / `content_filter` → MODEL_ERROR
- `error` → PARAMETER_ERROR

**优先级 3: 文本 fallback**（line 125-132）

仅在无结构化信号命中时使用。`_TEXT_PATTERNS`（line 66-71）包含权限与超时两个 pattern 组；`[error:` 或 `error:` 前缀 → PARAMETER_ERROR（line 131-132）。

#### 3.3 Alert 级别

`_ALERT_LEVEL`（line 72-78）按类别定义了告警策略：

| 类别 | Alert 级别 |
|------|-----------|
| PERMISSION_DENIED | `"immediate"` |
| NETWORK_TIMEOUT | `"warn"` |
| MODEL_ERROR | `"warn"` |
| PARAMETER_ERROR | `"record"` |
| UNKNOWN | `"record"` |

`ErrorClassifier.alert_level()` 静态方法（line 136-138）返回对应告警级别。

#### 3.4 异常 → error_type 映射

`exception_error_type()`（line 86-97）：从 Python 异常对象提取结构化 error_type：
- `asyncio.TimeoutError` → `"timeout"`
- `ConnectionError` / `TimeoutError` → `"network_error"`
- 其他 → `None`（交由文本 fallback 路径分类）

#### 3.5 Mode → Phase 映射

`PHASE_BY_MODE`（line 31-44）将 AgentMode 映射为运行时 phase 标签，供 CostLedger 的 phase 维度使用：

| Mode | Phase |
|------|-------|
| `build` | `"building"` |
| `read_only` | `"review"` |
| `plan` | `"planning"` |
| `bypass` | `"bypass"` |

**与 dev-workflow 四阶段的区别**：文档注释（line 10-12）明确说明这套 phase 映射是**运行时**标签，不等同于 dev-workflow 的 wayfinding/planning/building/closing 四阶段。

#### 3.6 语义错误的处理边界

文档注释（line 5-7）明确声明：**语义错误（hallucination）不在此处自动分类**，需要 LLM judge 判定，与 benchmark judge 决策保持一致。这符合可观测性最佳实践（OpenTelemetry GenAI / Langfuse）。

---

### 4. Benchmark Runner — git worktree 隔离执行

**文件**：`benchmarks/runner.py`

#### 4.1 任务执行环境隔离

`BenchmarkRunner`（line 76）核心设计：每个 task 在独立工作区执行。

- 本地任务：通过 `_create_worktree()`（line 580）用 `git worktree add --detach <commit>` 创建**隔离 worktree**
- 外部 repo 任务（SWE-bench）：通过 `_clone_external_repo()`（line 592）clone 到 `tasks/<task_id>/.external_repo`
- `keep_worktrees` 参数（line 86）控制是否保留 worktree：**默认 `False`**（用完即清理）
- `clone_cache_dir` 参数（line 87-109）支持共享 bare clone 缓存加速外部 repo clone

#### 4.2 并行控制

`parallel` 参数（line 85，**默认 `1`**，即串行）通过 `asyncio.Semaphore` 控制并发（line 204）。所有 task 通过 `asyncio.gather` 并行调度，信号量限制并发数。

#### 4.3 本地任务流程（非 Docker 任务）

`run_task()` 方法（line 276-575）的本地路径：

1. 创建 worktree（`_create_worktree` line 580）
2. 隐藏 agent 不可见的 task 文件（`_hide_agent_invisible_task_files` line 739）：将 `benchmarks/tasks/` 目录移动到 `.hidden/`，防止 agent 作弊
3. 运行 agent
4. 恢复隐藏文件（`_restore_agent_invisible_task_files` line 751）
5. 写出 diff（`trace.record_diff()` line 368）
6. 应用 test.patch（如有）（`_apply_test_patch` line 785）
7. 执行测试命令（`trace.record_test()` line 504），记录 exit_code
8. 判定结果：exit_code==0 → `passed`/`passed_with_warnings`；否则 `failed`（`trace.record_completion(status)` line 553）

#### 4.4 Docker 任务流程（SWE-bench）

1. Docker preflight 探测（`_probe_docker()` line 159，判定 line 330-336）：如果 Docker 不可用 → `unsupported`
2. Clone 外部 repo + 安装依赖（`_install_repo_deps()` line 649）
3. 运行 agent
4. 通过 `VerifierAdapter` 协议调用 SWE-bench 官方 `swebench.harness.run_evaluation`（在 `adapters.py:SwebenchAdapter.verify()` 中，line 76-155）
5. 判定结果：`resolved==True` → `passed`；否则 `failed`（adapters.py:147-155）

#### 4.5 Worktree 清理

不论成功或失败，`finally` 块保证 worktree 被清理（`git worktree remove --force` + `rmtree` fallback）。

#### 4.6 Clone 重试

`_git_clone_with_retry()`（line 621）：3 次重试，指数退避（60s → 120s → 240s），总计 4 次尝试。

#### 4.7 本地 httpbin 启动

对 requests repo 的任务，runner 启动本地 httpbin 服务器（`_start_local_httpbin()` line 852），避免依赖远程 httpbin.org（可能返回 503）。

---

### 5. 任务 Schema 与套件级能力覆盖矩阵（评测升级）

**文件**：`benchmarks/task_schema.py` + `benchmarks/task_set.py`

#### 5.1 任务级双标签：scenario × difficulty

`task_schema.py` 定义任务规格的标准化校验（`TaskSpec.from_dict` line 37-72，`validate()` line 74-104）：

| 字段 | 枚举 | 代码位置 |
|------|------|---------|
| `scenario` | bug-fix / feature-dev / refactor / debug / integration（5 枚举） | `SCENARIOS` line 8，`TaskSpec.scenario` line 27 |
| `difficulty` | easy / medium / hard（3 档） | `DIFFICULTIES` line 9，`TaskSpec.difficulty` line 26 |
| `track` | A / B / verified（任务集三来源） | `TRACKS` line 11，`TaskSpec.track` line 28 |

任务 schema 是**单一事实源**：每个 `task.json` 用 `scenario`（代码改动类型，主组织轴）+ `difficulty`（归一化难度）做双标签，`track` 标记任务来源轨。非法枚举在加载时直接抛错（line 83-90）。

当前任务集分布（已核实）：本地任务 scenario 覆盖 bug-fix 6 / feature-dev 20 / refactor 3 / debug 3 / integration 2，difficulty easy 9 / medium 17 / hard 8。

#### 5.2 套件级能力覆盖矩阵（OpenHands 式）

**关键设计决策（D2）**：能力分层从"逐任务打 category 标签"升级为**套件级覆盖矩阵**——`task_set.py` 声明 7 个能力列，任务在 manifest 中登记覆盖哪些列：

```python
# task_set.py:20-28
CAPABILITIES = [
    "tool-usage", "context-planning", "multi-step-solving",
    "error-recovery", "safety-boundary", "long-term-memory", "long-context",
]
# task_set.py:31 — 场景 5 枚举规范顺序
SCENARIO_ORDER = ("bug-fix", "feature-dev", "refactor", "debug", "integration")
```

`Manifest.validate_coverage()`（task_set.py:82-135）机械校验：

- 每个能力列至少有一个**本地 A/B 任务**登记（`_LOCAL_TRACKS = {None, "A", "B"}`，line 34——verified 子集不计入矩阵，避免 bug-fix 偏置撑满场景列）
- 每个场景列（5 枚举）至少有一个本地 A/B 任务
- **按轨能力覆盖**（`REQUIRED_TRACK_COVERAGE` line 39-43）：`context-planning` / `long-term-memory` / `long-context` 三列必须分别有 **B 轨**任务登记——这是 spec delta 的机械强制

manifest 存储于 `benchmarks/tasks/manifest.json`：`coverage` 段登记 34 个本地任务的能力列覆盖，`verified` 段单独披露 Verified 子集摘要（count / by_repo / by_difficulty，`update_manifest_verified` 由 build-subset 管线维护）。

---

### 6. Benchmark Statistics — bootstrap + pass@k + pass^k + 成本 + 归因

**文件**：`benchmarks/statistics.py`

#### 6.1 Bootstrap 置信区间

`bootstrap_ci()`（line 107-131）实现标准 percentile-method bootstrap：

```python
def bootstrap_ci(
    values: Sequence[float],
    seed: int = 0,           # 固定种子，结果可复现
    n_resamples: int = 2000, # 重采样次数
    ci: float = 0.95,        # 置信水平，默认 95%
) -> tuple[float, float]:
```

实现细节：
- 使用 `random.Random(seed)` 固定种子确保可复现（line 121）
- 每次重采样从原样本中有放回抽取 n 个值计算均值（line 123-126）
- 对 2000 个 bootstrap 均值排序（line 127）
- percentile method：取 2.5% 和 97.5% 分位点（line 128-131）

#### 6.2 Pass@k 与 Pass^k（能力上限 vs 可靠性）

**`pass_at_k()`**（line 145-161）实现 Chen et al. 2021 的组合估计器：

> `pass@k = 1 - C(n - c, k) / C(n, k)`

其中 n = 总轮数，c = 通过轮数，k = 子集大小。用于评估"跑 k 次至少一次通过"的概率（**能力上限**）。`_comb(n, k)`（line 134-142）精确整数二项式系数计算，避免浮点误差。

**`pass_k_success_rate()`**（line 188-218）是评测升级新增的任务级 **pass^k** 聚合（**可靠性**）：

```python
def pass_k_success_rate(
    task_rounds: Sequence[Sequence[bool]],
    min_valid_rounds: int = 3,
) -> PassKSummary:
```

- 每个任务在所有**有效轮**（invalid rounds 已剔除）全部通过才算 pass
- 有效轮数 < `min_valid_rounds=3` 的任务从分子分母中排除（样本太小无统计意义）
- 返回 `PassKSummary(rate, passed_tasks, valid_tasks, excluded_tasks, min_valid_rounds)`

**指标语义（报告页 line 218-223 明确声明）**：
- **pass@1** = 有效轮经验通过率（用户实际获得）
- **pass@k** = k 次任一成功（能力上限，组合估计）
- **pass^k** = 全部有效轮成功（可靠性）

**无效轮次不进分母**（`is_valid_round()` line 60-71 + `INVALID_ROUND_REASONS` line 55-57）：`unsupported` 状态 + `docker_unavailable` / `task_family_unsupported` / `approval_unavailable` 三类 reason 的轮次既不算通过也不算失败。

#### 6.3 $/resolved-task（cache-aware）

`cost_per_resolved()`（line 229-254）是评测升级新增的成本-精度指标：

```python
def cost_per_resolved(results: Sequence[TaskResult]) -> tuple[float | None, float, int]:
```

- **分子**：全部 run 的 LLM token 总成本（**含失败 run**，cache-aware 用 `compute_cost_cached` 四档定价核算）
- **分母**：resolved 数（`passed` + `passed_with_warnings`）
- **口径声明**：仅 LLM token 计费，不含沙箱 / CI / 计算成本

#### 6.4 fault_owner 失败归因交叉表

`FAULT_OWNERS`（line 46）= `("agent", "task", "environment", "unknown")`，与 reason 正交的失败归因维度。

`fault_owner_cross()`（line 257-280）产出 **reason × fault_owner 交叉表**：只统计 `failed` / `error` 结果（`unsupported` 不算失败），无效/未标注的 fault_owner fallback 到 `unknown`。

#### 6.5 配对比较（跨 Agent 对比的统计核心）

`paired_comparison()`（line 401-439）+ `mcnemar_exact()`（line 379-398）实现配对统计：

| 统计量 | 实现 | 代码位置 |
|--------|------|---------|
| per-task delta | 共享任务集上 A 的 pass@1 − B 的 pass@1 | `_pass1_by_task` line 320-333 |
| 差异 CI | **配对 bootstrap**（同一任务索引同时读两侧 run，保持配对性） | `_paired_delta_ci` line 351-376 |
| win-rate | A 胜 / B 胜 / 平 的任务数 | line 419-421 |
| McNemar | 在 pass^k 布尔上做 exact-binomial 检验 | `mcnemar_exact` line 379-398 |

**配对 vs 独立**（line 363-366 注释）：独立重采样会得到 Var(A)+Var(B)（高估方差、低估显著性），配对重采样得到 Var(A−B)，这才是"同一批任务换 agent"的正确推断。

#### 6.6 辅助统计

| 函数 | 行号 | 说明 |
|------|------|------|
| `mean_std()` | 94 | 返回 (mean, sample stdev)，空输入返回 (0.0, 0.0) |
| `layer_pass_rate()` | 164 | 按 capability layer 计算通过率均值 |
| `valid_round_count()` | 85 | 有效轮数 N（per-task CI 小样本声明用） |
| `process_efficiency()` | 446 | time-to-first-successful-edit / exploration fraction（D10） |
| `swebench_versions()` | 496 | dataset/swebench 包版本（污染披露元组，D11） |
| `cohen_kappa()` | 283 | 标注一致性（fault_owner 校准预留） |

#### 6.7 Capability Layers

`LAYERS`（`benchmarks/models.py` line 11-16）定义四个能力分层：

```
execution → tool-usage → context-planning → multi-step-solving
```

`resolve_layer()`（line 20-28）将 task 的 `category` 映射到 layer，未知 category 回退到默认层 `"execution"`。`BenchmarkReason` 枚举（line 31-42）定义 **11 类失败 reason**：setup_error / tool_error / edit_validation / test_failure / test_timeout / max_iterations / no_change / out_of_scope_change / model_failure / docker_unavailable / docker_runtime_error。

---

### 7. Benchmark Report — 评估报告生成

**文件**：`benchmarks/report.py`

#### 7.1 Markdown 报告

`render_report()`（line 172-190）产出包含以下段落的 Markdown 报告：

| 章节 | 内容 | 对应代码行 |
|------|------|-----------|
| 指标语义 | pass@1 / pass@k / pass^k 定义 + 无效轮次声明 | 218-223 |
| By Capability Layer | 按 layer 聚合：Tasks / Rounds / Pass Rate / 95% CI（bootstrap）/ **Pass^k** | 227-255 |
| By Task | 逐任务：Pass@k / Passes / **Pass^k** / Mean±Std / 95% CI / p50 / p95 / p99 / Input / Output Tokens | 258-299 |
| Token Cost | Input/Output Tokens / Est. Cost（调用 `compute_cost`） | 302-312 |
| Failure Attribution | 按 reason 分类失败的 (task, round) look-back 样本 | 315-332 |
| C3 Disclosure | 披露段（报告元组 / 污染注记 / 反作弊 / 交叉表 / 成本 / f2p·p2p / 采样 / 小样本 / 过程效率 / 覆盖矩阵 / Verified） | 334-346 |

**评测升级确认**：
- **Pass^k 列**：layer 表（line 240-254）和 task 表（line 276-283）都新增 Pass^k。task 级 pass^k 需 ≥3 有效轮才显示 yes/no，否则显示 `—`。
- **预算截断轮处理**（line 206-210）：`truncated: true` 的轮次保留其真实完成的 task 结果计入 pass@1，但从 pass^k 分母剔除（Q4 确认）。
- 无效轮（unsupported / approval-unavailable / docker-unavailable）不计入任何 pass-rate 分母（`_valid_results` line 84-90）。

#### 7.2 HTML 报告

`render_html()`（line 351-518）产出自包含 HTML 页面，内容与 Markdown 等价，带 CSS 样式 + 披露段（line 470-481）。

#### 7.3 失败归因

`failure_attribution()`（line 151-169）只统计 `failed` / `error` 状态且 reason 不为 None 的结果，按 reason 分桶，返回 `{reason: [(task_id, round_index), ...]}`，与 `fault_owner_cross` 的失败集一致（`unsupported` 不算失败）。

---

### 8. Benchmark Gate — CI 回归门禁

**文件**：`benchmarks/gate.py`

#### 8.1 门禁语义

`compare()`（line 117-165）比较当前 run 的 metrics 与 baseline JSON：

| 指标 | 阈值 | 说明 |
|------|------|------|
| success_rate | 绝对下降不超过 **5pp**（0.05） | 严格 `>` 比较，含 epsilon 防浮点精度 |
| p95_latency_s | 相对增长不超过 **5%**，且绝对增长不超过 **1.0s** | `max(baseline * 1.05, baseline + 1.0)`，解决 sub-second baseline 的相对波动无意义问题 |

#### 8.2 p95 延迟的特殊处理

- p95 仅对 **passed** 任务计算，避免 failed/crashed 任务（duration=0.0）拉低延迟掩盖回归
- `check_p95=False` 跳过 p95 检查，用于 gate-smoke 等确定性近零 IO 任务集
- `ABS_P95_FLOOR_S = 1.0`（line 32）：当 baseline p95 < 1s 时，用绝对 floor 代替相对 fraction

#### 8.3 Baseline 管理

| 函数 | 行号 | 说明 |
|------|------|------|
| `compute_run_metrics()` | 54 | 从 TaskResult 列表计算 success_rate / p95 等指标 |
| `load_baseline()` | 168 | 加载并校验 schema_version + metrics shape |
| `write_baseline()` | 193 | 写出 baseline JSON |
| `build_baseline()` | 200 | 组装 baseline dict（含 git_sha 追溯） |

baseline 路径默认 `benchmarks/baseline.json`，schema_version 固定为 `1`。

#### 8.4 实际 baseline 内容

`benchmarks/baseline.json` 当前使用 `agent="fake"`（即 fake agent 记录），这是合理的——fake agent 产出的 baseline 作为门禁的绝对值参考。

---

### 9. Cross-Agent Comparison — 配对比较 + 多 run 对比

**文件**：`benchmarks/compare.py`

#### 9.1 功能

`compare.py` 是一个独立的 CLI 脚本，比较多个 benchmark run 的结果：

```
python benchmarks/compare.py <run-dir-1> <run-dir-2> ...
```

#### 9.2 对比维度

`build_summary()`（line 105-203）产出的 Markdown 对比报告包含：

| 章节 | 内容 |
|------|------|
| Task-level table | 逐任务逐 agent 的 status + duration |
| Summary | 按 agent 按 status（passed/passed_with_warnings/unsupported/failed/error）的计数分布 |
| Latency Percentiles | 每个 agent 的 p50/p95/p99/max |
| Cost Estimate | 每个 agent 的 Input/Output Tokens + Est. Cost |
| Run Metadata | 报告元组（agent/model/harness） |

#### 9.3 配对比较段（评测升级新增）

当且仅当输入为**恰好两个** run 时，`build_paired_report()`（line 234-280）追加 `## Paired Comparison` 段，复用 `statistics.paired_comparison` 的统计量：

| 行 | 指标 | 来源 |
|----|------|------|
| 258-259 | Mean per-task delta (pass@1) + Difference 95% CI (paired bootstrap) | `_paired_data` line 215-231 |
| 262-269 | Win-rate（A/B/ties）+ McNemar (pass^k) | `paired_comparison()` |
| 273-278 | 逐任务 delta 明细表 | `comp.per_task_deltas` |

HTML 侧 `_build_paired_html()`（line 48-90）共享同一份数据，嵌入 `build_html()`（line 282-407）。

#### 9.4 输出位置

报告输出到 `benchmarks/reports/comparison.md` 和 `benchmarks/reports/comparison.html`（`main()` line 411，写入 line 449-455）。

---

### 10. Verifier Adapter — 评测框架插件化

**文件**：`benchmarks/adapters.py`

#### 10.1 协议

`VerifierAdapter` Protocol（line 37-44）定义标准接口：

```python
class VerifierAdapter(Protocol):
    def verify(
        self, loaded: LoadedTask, task_output, patch_text: str, log=None
    ) -> Verdict: ...
```

`Verdict` dataclass（line 22-35）：标准化的验证结果（status / reason / detail / score / **resolved**）。`resolved` 是 C2 新增的 strict-resolved 布尔，用于 `$/resolved-task` 分母。

#### 10.2 注册机制

- `register_verifier(task_family, adapter_cls)`：把适配器类注册到全局注册表
- `get_verifier(task_family, **kwargs)`：按 task_family 查找并实例化适配器
- 当前注册了 `"swebench"` → `SwebenchAdapter`（并兼容 `"swebench-verified"` 等实例级 family）

#### 10.3 SwebenchAdapter

`SwebenchAdapter`（line 50-155）实现 SWE-bench Verified 验证协议，`verify()` 在 line 76：

1. 生成 `predictions.jsonl`（agent patch + instance_id + model name）（line 85-92）
2. **model name 转义修复（CP-4）**：`_report_model_dir()`（line 68-74）对 model name 做 `replace("/", "__")` 转义——harness 按 `model_name_or_path` 生成报告目录，未转义会导致 report 路径找不到（该修复已合入）
3. 调用官方 `swebench.harness.run_evaluation` Docker 验证器（line 98）
4. 读取 `report.json`，检查 `resolved` 字段（line 147-155）
5. 返回 `Verdict(status="passed" if resolved else "failed")`

**注意**：SWE-bench 验证需要 Docker — `SwebenchAdapter` 通过 `subprocess.run` 调用官方 harness，harness 内部使用 Docker 容器运行测试。

---

### 11. 任务数据集 — 72 个 coding 任务

#### 11.1 任务计数确认（合并 master 后已核实）

`benchmarks/tasks/` 下共有 **74 个 task.json**（`benchmarks/tasks/*/task.json` glob 结果）：

| 类别 | 数量 | 说明 |
|------|------|------|
| 本地任务（`task_family=local`） | **34** | 22 A 轨回归基线 + 12 B 轨当前演进 |
| SWE-bench Verified 子集（`task_family=swebench`） | **38** | 全部 `track=verified`，dataset = `princeton-nlp/SWE-bench_Verified` |
| gate-smoke（CI 门禁专用） | 2 | 在 `gate-smoke/` 二级目录，不计入 coding 任务 |

**coding 任务合计 = 72**（34 本地 + 38 Verified）。`run_all()`（runner.py:192-195）对 `benchmarks/tasks` 做一层 `iterdir()`，默认加载全部 72 个；gate-smoke 在二级目录，只有 `benchmark-gate` 命令显式指定才跑。

> **数字口径**：上一版口径为 36（26 本地 + 10 SWE-bench 外部）；master 合并后本地任务经 B 轨扩展为 34（22 A + 12 B），Verified 子集经 build-subset 管线生成为 38（原 10 + 本机生成 28），合计 72。`docs/benchmark-run-protocol.md` 的协议目标口径为 82–90（A 轨 20–24 + B 轨 12–16 + Verified 50），是升级方向而非现状。

#### 11.2 本地任务 34 = 22 A 轨 + 12 B 轨

**A 轨·历史重建回归基线（22）**：基于 2026-06 前合入特性的历史重建任务，作为回归基线（有答案泄漏面，结果页强制披露，非公平评测）：

| 任务 ID | 任务 ID |
|---------|---------|
| asterwynd-001-tool-registry | asterwynd-012-sse-streaming |
| asterwynd-002-asterwynd-runner | asterwynd-013-hook-manager |
| asterwynd-003-agentloop-trace | asterwynd-014-logging-tracing |
| asterwynd-003-read-write-tools | asterwynd-015-retry-budget |
| asterwynd-004-harden-write | asterwynd-017-interactive-fix |
| asterwynd-006-memory-manager | asterwynd-018-warning-passes |
| asterwynd-007-skill-loader | asterwynd-019-runner-timeout |
| asterwynd-008-parent-channel | asterwynd-020-close-clients |
| asterwynd-009-subagent-manager | asterwynd-022-long-term-memory |
| asterwynd-010-agent-loop | asterwynd-022-collaborative-context-audit |
| asterwynd-011-repeater-fix | asterwynd-readme-title |

**B 轨·当前演进（12）**：基于当前 HEAD 真实缺陷/增强构造的任务（面试核心），每个任务 issue.md 不给路径 + 确定性 test_command + base 红/gold 绿红绿可复现：

| 任务 ID | 覆盖点 |
|---------|--------|
| asterwynd-002-sandbox-executor | 沙箱执行器 |
| asterwynd-004-benchmark-cli | benchmark CLI |
| asterwynd-005-bash-workspace | Bash 工作区边界 |
| asterwynd-021-lsp-diagnostics | LSP diagnostics |
| asterwynd-b01-report-family-summary | 结果页 family 摘要（CP-3） |
| asterwynd-b02-running-benchmarks | ListRunningBenchmarks 只读工具装配链（CP-1） |
| asterwynd-b03-awaiting-grill-state | statechart 新态（CP-2） |
| asterwynd-b04-report-track-grouping | 结果页 track 分组 |
| asterwynd-b05-model-name-escaping | SwebenchAdapter model name 转义合成回归 |
| asterwynd-b06-save-memory-project-scope | LT-MEM-1 project scope 隔离 |
| asterwynd-b07-memory-context-source-split | LC-1 记忆注入归属下沉 |
| asterwynd-b08-pipe-to-absolute-shell | BF-1 绝对路径 shell 拦截修复 |

#### 11.3 SWE-bench Verified 子集（38）

全部标注 `track=verified`、`dataset_name=princeton-nlp/SWE-bench_Verified`、`scenario=bug-fix`。按 repo 分布（manifest 已核实）：

| repo | 数量 |
|------|------|
| psf/requests | 8 |
| pallets/flask | 1 |
| pytest-dev/pytest | 11 |
| sympy/sympy | 8 |
| mwaskom/seaborn | 2 |
| pylint-dev/pylint | 8 |

difficulty 分布：easy 17 / medium 16 / hard 5。子集从轻量+中等池逐条过滤 KNOWN_BAD 与重实例（不含 django/sphinx），避免测试慢与权重失真。

#### 11.4 gate-smoke 任务

| 任务 ID |
|---------|
| gate-smoke-001 |
| gate-smoke-002 |

CI 回归门禁专用（确定性高、IO 近零），不计入 coding 任务。

#### 11.5 外部 repo 任务的依赖安装

`_install_repo_deps()`（runner.py:649）使用 SWE-bench 的 `MAP_REPO_VERSION_TO_SPECS` 配置确定 Python 版本和 pip 包。使用 `uv venv` + `uv pip install` 安装依赖。对 `psf/requests` 附加 `pytest-httpbin` + `werkzeug<3.0`。

---

### 12. Verified 子集 build-subset 管线（评测升级）

**文件**：`benchmarks/swebench_subset.py`

#### 12.1 配比选择

`build_subset()`（line 73-125）按 repo 配比从候选实例选子集：

```python
# swebench_subset.py:20-29 — 40 条补齐配比（OQ-V1）
SUBSET_TARGETS: dict[str, int] = {
    "psf/requests": 4, "pallets/flask": 6, "pytest-dev/pytest": 8,
    "sympy/sympy": 8, "mwaskom/seaborn": 6, "pylint-dev/pylint": 8,
}
HEAVY_REPOS = {"django/django", "scikit-learn/scikit-learn", ...}  # 重实例不纳入
```

选择逻辑：逐条过滤 KNOWN_BAD 与重实例、排除既有 instance_id（OQ-V3 续跑收敛）、按配比从池中取。`SubsetPlan.summary()`（line 57-63）输出 selected / skipped 明细。

#### 12.2 落盘 + 机械校验 + 金补丁自检

- `cmd_build_subset()`（line 415-505）：加载（HF_ENDPOINT 镜像）→ 字段探针 → 排除既有 → 选子集 → 落盘 fixture → `validate_fixture` 机械校验 → 抽样 gold-check
- **L3 金补丁自检**：`gold_check` 对每个 repo 抽样 1 条（`--full-gold-check` 全量），把 fixture 的 gold.patch 应用到 base_commit 并跑 test_command，验证"金补丁能通过测试"——保证 fixture 本身可解（OQ-V2①）
- **manifest 登记**：`update_manifest_verified()`（line 380-412）统计 `track=verified` 的 fixture，写入 `manifest.json` 的 `verified` 摘要段（count / by_repo / by_difficulty，OQ-V6①）

#### 12.3 数据不可达降级

数据集访问不可用（如无 huggingface 网络）时，本模块仍提供选择逻辑与校验规则，实际 fixture 生成在数据可访问环境执行；生成后可用 `validate_fixture` 机械校验、`gold_check` 自检（docstring line 5-8）。

---

### 13. CI 回归门禁

**文件**：`.github/workflows/ci.yml`

#### 13.1 两个 CI Job

| Job | 名称 | 触发条件 | 说明 |
|-----|------|----------|------|
| `validate` | validate | PR + push to master | pytest + OpenSpec validate + artifact checker |
| `benchmark-gate` | benchmark-gate | PR + push to master | 回归门禁（line 58-59） |

#### 13.2 benchmark-gate Job 细节

触发的命令（line 96）：

```bash
uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke \
  --source-repo . \
  --runs-dir /tmp/benchmark-gate-runs \
  --baseline benchmarks/baseline.json \
  --require-baseline \
  --skip-p95
```

关键参数：
- `--source-repo .`：以当前仓库为 source repo，创建 worktree
- `--runs-dir /tmp/benchmark-gate-runs`：产出目录
- `--baseline benchmarks/baseline.json`：门禁 baseline 文件
- `--require-baseline`：强制 requirement baseline 存在
- `--skip-p95`：跳过 p95 延迟检查（gate-smoke 任务集确定性高、IO 近零，p95 受环境因素主导，不作为可靠回归信号）——与 gate.py 的 `check_p95=False` 对应

#### 13.3 关闭条件

Benchmark gate **仅在 PR 和 push to master 时触发**（line 3-7）。本地运行时需手动执行 `benchmark-gate` 命令。这不是一个自动化的 pre-commit hook。

---

### 14. 评测运行协议与预算（评测升级）

#### 14.1 运行协议文档

`docs/benchmark-run-protocol.md` 是 C3 转正的评测运行协议（跟踪 issue #159）：**只定协议；是否实际跑数、预算大小由使用者按需决定**。协议内容要点：

- **任务集口径**：A 轨 20–24 + B 轨 12–16 + Verified 50 = 82–90（协议目标形态，与当前 72 现状的差异需区分）
- **采样约定**：`--repeat 5`（N≥3 才有 pass^k 意义）、固定 seed 集合 `--seeds 0 1 2 3 4`、`--temperature 0.2`（pass@1 口径）；每轮记录 `(temperature, seed, model version)`，可复现性声明限定 (model version, provider, harness) 内
- **无效轮次不进分母**：`unsupported` / `approval-unavailable` / `docker-unavailable` 不计入 pass@1 与 pass^k 分母
- **自洽性五门禁**（`scripts/self_check.py`）：同模型同 harness 复现 / seed 复现 / 失败归因闭环 / 披露段齐全 / 报告元组完整

#### 14.2 预算：可配置、可取消（--budget-cap）

CLI 入口在 `agent/main.py:701`（`benchmark` 命令），预算参数在 line 735-757：

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --repeat 5 --seeds 0 1 2 3 4 --temperature 0.2 \
  --budget-cap 50        # 单轮建议上限；--budget-cap 0 或 --no-cap 取消
```

预算语义（main.py:749-757 + `_run_rounds_with_budget` line 821）：

- **单轮（per-round）口径**：任一轮累计成本超过 cap 即停止剩余轮次（用户决策 2026-08-17）
- **取消**：`--budget-cap 0` / `--no-cap` / 缺省 三者等价取消；负数拒绝
- **超限行为**：停止剩余轮次；当前轮已启动的并发任务自然完成（不 cancel，避免半截 trace）；当前轮结果标 `truncated`（`run.json` 的 `truncated: true`）
- **对统计的影响**：已发生成本照常计入 $/resolved-task 分母；compare 配对剔除 truncated 轮；pass^k 分母不含 truncated 轮（report.py:206-210, 276-283）

#### 14.3 结果页披露段（10 项核心 + Verified 子集）

`benchmarks/disclosure.py` 的 `markdown_disclosure_sections()`（line 294-403）渲染披露段：

| # | 披露段 | 数据来源 |
|---|--------|---------|
| 1 | 报告元组 | `report_tuple_rows` line 68-108（model/harness/task_set_hash/grader/成本口径/truncated） |
| 2 | SWE-bench 污染注记 | `SWEBENCH_AUDIT_NOTE` line 30-35（138 实例中 59.4% 有实质缺陷，OpenAI 2026-02 弃用；保留条件域） |
| 3 | 反作弊泄漏披露 | `anti_cheat_rows` line 111-122（A 轨回归基线定位，非公平评测） |
| 4 | reason × fault_owner 交叉表 | `fault_owner_cross_rows` line 125-132 |
| 5 | 成本与定价 | `cost_metrics_rows` line 135-146（$/resolved-task + cache hit rate + 定价表版本 + 仅 LLM token 计费） |
| 6 | 部分成功档（f2p/p2p） | `partial_rows` line 149-162 |
| 7 | 采样参数 | `sampling_rows` line 165-177（temperature/seed/model version） |
| 8 | 小样本声明 | `small_n_note` line 191-202（N=3–5 附声明） |
| 9 | 过程效率 | `process_efficiency_rows` line 222-242（ttf-edit / exploration） |
| 10 | 能力覆盖矩阵 | `coverage_rows` line 245-257（C1 manifest 套件级展示） |
| + | Verified 子集披露 | `verified_rows` line 260-277（count/by_repo/by_difficulty，不占覆盖矩阵） |

每个披露段对旧 run.json 缺失字段渲染 fallback 占位而非抛错（docstring line 9-11 的向后兼容要求）。

---

### 15. 未覆盖或默认关闭的功能总结

| 功能 | 状态 | 位置 | 说明 |
|------|------|------|------|
| `full_trace` | 默认 `False` | `trace_recorder.py:27` | 全量追踪开关，保留为序列化兼容用途，当前不启用 |
| `session_id` / `run_id` | 默认 `None` | `trace_recorder.py:29-30` | 需外部注入，无自动生成 |
| `keep_worktrees` | 默认 `False` | `runner.py:86` | 保留 worktree 用于调试，用完即清理 |
| `clone_cache_dir` | 默认 `None` | `runner.py:87-109` | 共享 clone 缓存加速，需显式传入 |
| `parallel` | 默认 `1`（串行） | `runner.py:85` | 并发数需手动增加 |
| 预算 cap | 默认取消 | `main.py:753-757` | `--budget-cap` 显式设置，0/`--no-cap` 取消 |
| `/review-loop` | 必检门禁 | `AGENTS.md` | 由 OpenSpec artifact checker 强制，非 CI 内置步骤 |
| 语义错误分类 | 不在此处 | `observability.py:5-7` | 需要 LLM judge，与 benchmark judge 一致 |
| Verified 子集扩展 | 40 条补齐未生成 | `swebench_subset.py` | 目标 50，当前 38；剩余 12 条需数据可达环境跑 `build-subset` |
| SWE-bench 多框架支持 | 仅 swebench | `adapters.py` | 其他框架（Harbor 等）需新增适配器 |

---

### 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/trace_recorder.py` | TraceRecorder — 18 种事件类型的全链轨迹记录器 + TraceRecorderSandboxSink |
| `agent/cost_tracker.py` | CostLedger — 三层成本归因（by_session/by_phase/by_tool）+ 17 模型 cache-aware 四档定价 + compute_cost_cached |
| `agent/observability.py` | ErrorClassifier — 5 类错误分类 + 17 条 error_type 映射 + 三级优先级 |
| `agent/run_identity.py` | new_session_id() / new_run_id() — 12 位 hex 标识生成 |
| `benchmarks/runner.py` | BenchmarkRunner — worktree 隔离 + Docker preflight + local/verify/httpbin 路径 |
| `benchmarks/task_schema.py` | TaskSpec — scenario(5) × difficulty(3) × track(A/B/verified) 任务规格与校验 |
| `benchmarks/task_set.py` | 套件级能力覆盖矩阵 — 7 能力列 + 5 场景列 + per-track 覆盖机械校验 |
| `benchmarks/statistics.py` | bootstrap_ci + pass_at_k + pass_k_success_rate + cost_per_resolved + fault_owner_cross + paired_comparison |
| `benchmarks/report.py` | Markdown/HTML 报告 — layer/task 聚合 + Pass^k + cost + failure attribution + 披露段 |
| `benchmarks/disclosure.py` | 结果页披露 — 报告元组 / 污染注记 / 反作弊 / 交叉表 / 成本 / f2p·p2p / 采样 / 小样本 / 过程效率 / 覆盖矩阵 / Verified |
| `benchmarks/gate.py` | 回归门禁 — success_rate drop > 5pp 或 p95 回归 → FAIL |
| `benchmarks/compare.py` | 跨 Agent 对比 CLI — 多 run 摘要 + 配对比较（per-task delta/差异 CI/win-rate/McNemar） |
| `benchmarks/adapters.py` | VerifierAdapter Protocol + SwebenchAdapter（含 model name 转义修复）+ 注册机制 |
| `benchmarks/swebench_subset.py` | Verified 子集 build-subset 管线 — 配比选择 + 落盘 + validate + gold_check + manifest 登记 |
| `benchmarks/models.py` | TaskResult/RunMetadata/BenchmarkReason(11)/LAYERS(4) + cache token/fault_owner 字段 |
| `benchmarks/task_set.py` | Manifest 覆盖矩阵加载 + validate_coverage |
| `benchmarks/tasks/manifest.json` | 任务集 manifest — coverage 登记 + anti_cheat_disclosure + verified 摘要 |
| `benchmarks/baseline.json` | 当前 baseline（fake agent, gate-smoke, success_rate=1.0） |
| `.github/workflows/ci.yml` | CI pipeline — validate + benchmark-gate 两个 job |
| `benchmarks/tasks/` | 74 个 task.json — 34 本地 + 38 Verified + 2 gate-smoke |
| `docs/benchmark-run-protocol.md` | 评测运行协议（C3 转正）— 采样/预算/对照口径/披露段/self_check 五门禁 |
