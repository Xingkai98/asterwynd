# Bullet 1: AgentLoop 核心循环 — 代码走读

> 简历原文：实现可扩展 AgentLoop 核心循环（message-driven + 快照断点续传），以 7 切面 Hook 协议解耦迭代/LLM 调用/工具执行/错误处理/完成阶段，同构适配 OpenAI / Anthropic 双 Provider，集成 38 个内置工具

---

## 1. 核心循环 — message-driven 迭代引擎

**文件**：`agent/loop.py`

主类 `AgentLoop`（line 112），入口 `run()` → `_run()`（line 544）。核心是一个 for 循环：

```python
for iteration in range(start_iteration, self.max_iterations):  # loop.py:605
```

单次迭代的完整流程：

```
① _select_tool_schemas()  — 从 38 工具中 Top-K 选 schema 注入 LLM    (:622)
② _messages_with_run_context() — 拼接 context block (ContextBuilder)   (:624)
③ hooks.before_iteration()     — Hook 切面                            (:625)
④ _call_llm()                  — 调 LLM，返回 LLMResponse              (:626)
⑤ hooks.after_llm_call()      — Hook 切面                             (:631)
⑥ 无 tool_call → 判断是否 max_tokens 截断                               (:671)
   - 截断 → 续接消息 "Please continue..."，下一轮继续
   - 非截断 → end_turn，结束
⑦ 有 tool_call → 追加 assistant 消息到 messages                        (:704)
⑧ Phase 1：解析 arguments + 权限审批 + 模式策略判定                     (:706-844)
⑨ Phase 2: _execute_tool_calls() 并行/串行执行                          (:846)
⑩ Phase 3: 结果回填 messages + hook after_tool_execute                  (:849-937)
⑪ memory.compact_if_needed() 上下文压缩                                (:941)
```

"message-driven" 的含义：所有状态在 `messages: list[Message]` 中流转，没有外部状态机。messages 数组就是 Agent 的"记忆"。

### Phase 1: JSON 解析 + 权限审批（:706-844）

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

### 工具执行重试：RetryHook（`agent/hooks/builtin/retry.py`）

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

### Phase 2: 并行/串行分组逻辑（:1212-1279）

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

## 2. 快照断点续传

### 数据结构：SessionSnapshot（`agent/session.py:16`）

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

### 持久化：SessionStore（`:88`）

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

### 恢复路径（`loop.py:557-584`）

```python
if resume_snapshot is not None:
    # ① 保留当前 system 消息不变
    # ② 恢复 mode / todos / skills / user_system_prompt
    # ③ 重建 messages:
    #    messages = 当前 system + 快照对话 + "[Session resumed. ...]" + 新用户输入
    # ④ 从头迭代
```

### 恢复是 transcript 级，非 call-stack 级

如果中断时恰好在工具执行中（assistant tool_call 消息已写入但 tool_result 未写回），续传后：
- 对话历史中 tool_call 缺少对应的 tool_result（消息链不完整）
- **没有代码逻辑自动重新执行未完成的 tool_call**
- 模型会在下一轮看到不完整的工具链，自然地做出反应（"上次工具没结果，需要重新执行"）
- `subagent/manager.py:256-258` 注释明确：**"resume is transcript-level, not stack-level"**

---

## 3. 7 切面 Hook 协议

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
| `on_run_started` | `:596` | 仅在非 resume 路径触发 |
| `before_iteration` | `:625` | 每轮迭代前，传入 contextualized messages |
| `after_llm_call` | `:631` | LLM 返回后，可读 response.usage |
| `before_tool_execute` | `:1179` | 工具执行前 |
| `after_tool_execute` | `:1209` | 工具执行后，带 error_type |
| `on_error` | `:714, :1189, :1193` | JSON 解析失败 / Bash 超时 / 其他异常 |
| `on_completion` | `:679, :971` | end_turn 和 max_iterations 两个出口 |

**内置 Hook**（`agent/hooks/builtin/`）：

| Hook | 功能 |
|------|------|
| `LoggingHook` | 日志记录 |
| `TracingHook` | trace 打点 |
| `RetryHook` | 工具调用重试（max 3 次，指数退避） |
| `TokenBudgetHook` | token 预算监控 |

`HookManager`（`:29`）遍历所有 hook 独立执行，互不影响。

---

## 4. OpenAI / Anthropic 双 Provider

### 统一接口（`agent/llm.py:35`）

```python
class LLM(Protocol):
    async def chat(messages: list[Message], tools: list[dict] | None, model: str) -> LLMResponse: ...
```

### 两个实现

| 实现 | 文件 | API | 特点 |
|------|------|-----|------|
| `OpenAILLM` | `openai_llm.py:15` | Chat Completions | auto-caching，不打 cache_control |
| `AnthropicLLM` | `anthropic_llm.py:26` | Messages API | `supports_cache_control = True` |

### 关键差异：Cache Plan

- `AnthropicLLM.supports_cache_control = True` — 只有 Anthropic 路径打 `cache_control: {"type": "ephemeral"}` 断点
- `_apply_cache_plan()`（`loop.py:1084`）在每次 LLM 调用前检查 `supports_cache_control`，决定是否打断点
- OpenAI 走服务端 auto-caching，不需要手动放断点

### AnthropicLLM 三层降级（`:56-97`）

1. 正常调用
2. 400 + cache_control → **去掉 cache_control 重试**（DeepSeek-anthropic 等兼容端点可能拒绝）
3. 400 + vision → **去掉图像重试**

### Provider 分发（`agent/main.py:build_llm()`）

```python
if provider == "anthropic":
    return AnthropicLLM(...)
else:
    return OpenAILLM(...)  # 默认
```

---

## 5. 38 个内置工具

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

## 关键文件索引

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
