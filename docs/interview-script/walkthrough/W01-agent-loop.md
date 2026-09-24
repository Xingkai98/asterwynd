# W01 · AgentLoop 核心循环 + Hook 协议 + 双 Provider

**对应简历 bullet 1**：*"实现可扩展 AgentLoop 核心循环（message-driven + 快照断点续传），以 7 切面 Hook 协议解耦迭代/LLM 调用/工具执行/错误处理/完成阶段，同构适配 OpenAI / Anthropic 双 Provider，集成 40+ 个内置工具"*

## 代码入口

```
CLI:  agent/main.py                    ← 命令行入口
        └─ 构造 AgentLoop(llm, tool_registry, ...)
            └─ await loop.run(messages, session_id=..., trace_recorder=...)
Web:  web/server.py → SessionManager   ← WebSocket 入口（同一 AgentLoop）
Benchmark: benchmarks/agent_runner.py  ← 评测入口（同一 AgentLoop）
```

核心：**`agent/loop.py`，`AgentLoop` 类（112 行起）**。

## 核心逻辑

### message-driven 主循环

`messages` 是唯一主状态。无状态机，进展全在消息列表：LLM 读 messages → 返回文本/工具调用 → 工具结果以 tool 角色回填 → 下一轮继续。

```python
# loop.py:605 — 主循环
for iteration in range(start_iteration, self.max_iterations):
    tool_schemas = self._select_tool_schemas(messages)             # 622: 动态工具选择
    contextualized = await self._messages_with_run_context(messages) # 624: 上下文注入
    response, streamed = await self._call_llm(messages, tools, ...)  # 626: 调 LLM
    ...
    messages.append(Message(role="assistant", content=..., tool_calls=...))  # 704
    executed = await self._execute_tool_calls(pending)             # 847: 执行工具
    for entry in executed:
        messages.append(tool_result_message(tool_call.id, result))  # 932: 回填
    compacted = await self.memory.compact_if_needed(messages, ...)  # 941: 压缩检查
```

**为什么 message-driven**：
1. 天然匹配 LLM 输入输出格式，不需要维护和 LLM 视角不同的"世界状态"
2. 序列化 messages 即会话持久化（快照断点续传的基础）
3. tool-call 消息链合法是硬约束，借 API 强制一致性

### 单次迭代步骤（loop.py:605-941）

| 步骤 | 行号 | 内容 |
|------|------|------|
| 1 | 608 | 后台任务完成检查（run_in_background=true 的 Bash） |
| 2 | 622 | 动态工具选择（Top-K=5，核心工具恒在前） |
| 3 | 624 | 8 层上下文注入（见 W04） |
| 4 | 626 | LLM 调用（流式/非流式自适应）+ cost_ledger 记录 |
| 5 | 671 | 无 tool_call → 结束 / max_tokens 续接 |
| 6 | 706 | Phase 1 预处理（解析 args → 查工具 → 权限决策 → 审批） |
| 7 | 847 | Phase 2 执行（并行分组 asyncio.gather） |
| 8 | 850 | Phase 3 后处理（trace + 事件 + 回填） |
| 9 | 941 | 压缩检查（max_tokens − 15K 阈值） |

兜底：`max_iterations=20`，到顶返回 `MAX_ITERATIONS`。

### 快照断点续传

- 保存：`run()` finally 块（loop.py:527-542）保底做 5 件事：清理后台任务 → 保存会话 → 恢复事件回调 → 恢复 sandbox sink → flush 成本账本。**即使崩溃也尽量存**。
- 恢复：`_run()` 的 `resume_snapshot` 分支（loop.py:557-575）还原 mode/todos/skills/user_system_prompt，拼回历史消息，插入 `[Session resumed...]`。
- 实现：`agent/session.py`，`tmp + os.replace` 原子写 + 内容哈希去重 + schema 主版本校验。

### 7 切面 Hook 协议（agent/hooks/manager.py:15-27）

```python
class Hook(Protocol):
    async def on_run_started(self, run_config) -> None
    async def before_iteration(self, iteration, messages) -> None
    async def after_llm_call(self, response) -> None
    async def before_tool_execute(self, tool_call) -> None
    async def after_tool_execute(self, tool_call, result, error_type=None) -> None
    async def on_error(self, error) -> None
    async def on_completion(self, result) -> None
```

覆盖 5 个阶段（迭代/LLM 调用/工具执行前后/错误/完成），`HookManager` 按注册顺序**同步串行**。内置：LoggingHook / TracingHook / RetryHook（唯一行为修改型，仅非 Bash 工具）/ TokenBudgetHook。

### 双 Provider 同构

```
LLM (Protocol, llm.py:35) ← 只约束 async chat(messages, tools, model)
    └─ BaseLLM (llm.py:71) ← httpx 连接池、SSE 解析、超时（流式 60s/非流式 180s）、懒初始化+锁
        ├─ OpenAILLM (openai_llm.py)     ← /v1/chat/completions
        └─ AnthropicLLM (anthropic_llm.py) ← /v1/messages，system 独立字段
```

**同构体现**：统一 `LLMResponse(content, tool_calls, stop_reason, reasoning_content, usage)`；Anthropic stop_reason 映射（tool_use→tool_calls 等）；消息格式差异封装（Anthropic 的 tool_result 合并、text 在 tool_use 前；OpenAI 的图片延迟 flush）；视觉降级 `vision_mode`；surrogate 清理；日志脱敏。

### Prefix Cache 机制（为 W02/W04 铺垫）

`_apply_cache_plan`（loop.py:1084）：只有声明 `supports_cache_control` 的 provider（Anthropic）收到 breakpoint 计划；OpenAI 自动缓存、绝不能收到 cache_control。

## 简历核实

| 简历 | 核实 | 结论 |
|------|------|------|
| "40+ 内置工具" | `KNOWN_BUILTIN_TOOL_NAMES` = **38**（factory.py:71），全开 +10 子代理控制 + MCP 按需 → 40+ | ⚠️ 口径偏紧 |
| "7 切面 Hook 协议" | 正好 7 个方法 | ✅ |
| "message-driven + 快照断点续传" | messages 唯一主状态 + resume_snapshot | ✅ |

## 面试加分点

1. **Bash 不走 retry，其他工具走**（loop.py:1196）——Bash 有 timeout/沙箱，重试语义不同。
2. **审批参数脱敏** `redact_value`（loop.py:786-790）——审批时 LLM 看到的 args 已脱敏，防 secrets 泄露 trace。
3. **并行分组智能跳过审批工具**（loop.py:1212-1242）——需要审批的调用强制进串行组。
