# Asterwynd 面试自测 Q&A（对照 W01-W07 用）

> 用法：看完 W01-W07 后，先**不看答案**逐题自答，再展开对照。答不上的回看对应走读文件。
> 每题的"答案"基于源码核实，面试被追问时按这个口径答。

---

## W01 · AgentLoop + Hook + 双 Provider

**Q1. AgentLoop 为什么是 message-driven？**
- messages 是唯一主状态，无状态机。
- ① 天然匹配 LLM 输入输出格式；② 序列化 messages 即会话持久化（快照续传基础）；③ tool-call 消息链合法性借 API 强制。

**Q2. 主循环一次迭代做什么？**
- 后台任务检查 → 动态选工具 schema → 注入 8 层上下文 → 调 LLM → 有 tool_call 则两阶段执行（预处理审批 + 并行执行）→ 回填 tool 消息 → 压缩检查。兜底 max_iterations=20。

**Q3. 快照断点续传怎么实现？**
- run() finally 块保底保存（清理后台/存会话/恢复回调/恢复 sandbox sink/flush 账本）；_run() resume_snapshot 分支还原 mode/todos/skills/messages + 插 `[Session resumed...]`。session.py 原子写 + 哈希去重 + schema 校验。

**Q4. 7 切面 Hook 是哪 7 个？为什么用 Hook？**
- on_run_started / before_iteration / after_llm_call / before_tool_execute / after_tool_execute / on_error / on_completion。解耦横切关注点（记录/重试/预算），加新能力不改核心循环。

**Q5. OpenAI / Anthropic 两个 provider 有哪些具体差异？**
- Anthropic：system 拆顶层字段、连续 tool_result 合并到同一条 user 消息、text 在 tool_use 前（DeepSeek 端点要求）。OpenAI：tool 消息里的图片延迟 flush 到下一条非 tool 消息。统一归一到 LLMResponse(content/tool_calls/stop_reason/usage)。

---

## W02 · 动态工具编排

**Q1. 两阶段检索具体流程？**
- BM25 粗筛全部非稳定工具取前 50 → embedding 精排取 top_k=5 → 输出 = 稳定层（恒在前、不占预算）+ 变层 top5。query 由最近 user 消息 + 最近 3 个工具名构成。

**Q2. 稳定层为什么不占 Top-K 预算？**
- 稳定层字节不变 → 保 Prefix Cache 命中。变层才是变化的尾巴（selector.py:107）。

**Q3. 语义去重是硬约束吗？**
- 不是，软提示。标记 duplicate_of 但不注入官方 schema，模型自己决定；只在选中时注入差异说明。

**Q4. 质量降级会禁用工具吗？**
- 不会。低于阈值(0.4)只退出变层候选，schema 仍可见、仍可调用，权限模型不动（registry.py:114）。

---

## W03 · 多 Agent 编排

**Q1. 4 种模式分别是什么？**
- orchestrator-worker（扇出并行聚合）/ peer-review（迭代批判）/ hierarchical（可嵌套 manager）/ bidding（独立方案 + selector 评选）。

**Q2. bidding 为什么不用 bus 传提案？**
- bus drop-oldest 会丢关键投标。用紧凑摘要 + 读 artifacts。

**Q3. token 预算超限的两条 kill 路径？**
- token 超限：BudgetHook.after_llm_call 抛 BudgetExceededError → 先写检查点再标记。时间超限（卡在工具调用）：后台 monitor 先写 _budget_kill_reason 再 cancel → CancelledError handler 记 budget_exceeded。两条路径都先写检查点。

**Q4. 快照恢复是 stack 级还是 transcript 级？**
- transcript 级。折叠历史，恢复时 model 重试 in-flight 工具调用。诚实边界。

---

## W04 · ContextBuilder

**Q1. 8 个上下文源分哪几层？**
- P0 SystemPrompt / P1 AsterMd / P2 MemoryIndex / P4 SkillIndex+SkillActive / P5 PlanMode+PlanningState+Todo。

**Q2. critical / cacheable / static 三个属性各管什么？**
- critical=永不裁剪（P0/P1）；cacheable=稳定前缀层，参与 cache_control 断点 + 不裁剪（P0/P1/P2）；static=渲染可缓存（P0/P1）。MemoryIndex 故意非 static（SaveMemory 会改写索引）。

**Q3. 稳定前缀怎么命中 Prefix Cache？**
- build_blocks 把 cacheable 层标 cache=True，Anthropic 在最后一个稳定块放 cache_control 断点（loop.py:1103 _compute_cache_plan）。

**Q4. L1/L2 层级压缩是什么？**
- L1 是每次 compact 的四段式摘要（已完成/待办/疑难点/进行中）；L2 在累积 ≥2 块且 ≥6K tokens 时把（旧 L2 base + 累积 L1）再压成顶层结论，防无限膨胀。

**Q5. tool-call pending 标记防什么？**
- 压缩把中间 tool result 压掉后，若 assistant 的 tool_call 没有对应 result，消息链非法。标记 `[call#<i>: <id> pending]` 让 LLM 知道这个调用还没结果。

---

## W05 · 长期记忆

**Q1. 写时三路去重是哪三路？**
- supplement（并进旧 body）/ update（替换）/ conflict（互打标记都保留）+ new 兜底。recall 相似度低于阈值短路 new，零 LLM 成本。

**Q2. importance × recency 衰减公式？**
- score = importance × 0.5^(days/30)。归档条件 AND：超 30 天未访问 + score < 1.5。recall/search 会 touch 更新 last_accessed_at。

**Q3. git commit-before-write 是什么？**
- 每次破坏性写前先 git add + commit 记录旧状态，再执行写入；提交失败 abort（宁可写失败不丢旧内容）。revert 两段式：先 snapshot 当前态 → checkout 旧 body + 重建索引 + 记 changelog → 再 commit。

**Q4. 为什么不用 mem0 的 ADD-only？**
- ADD-only 前提是读路径有强 ranker（时间/BM25/实体），Asterwynd 只有 NGramEmbedding。可逆性做在写路径：commit-before-write 对冲 LLM 误判。跟 mem0 是路线取舍，不是能力不如。

---

## W06 · 3 层纵深防御

**Q1. 三层各守什么？**
- 路径边界守文件、guard 守命令语义、sandbox 守真正隔离。guardrail 不是 boundary（Claude Code 2025 CVE：正则校验可绕过）。

**Q2. CommandGuard 覆盖了哪些绕过变体？**
- rm flag 重排/拆开、chmod 变体、kill -SIGKILL、base64|bash、node -e、nc、/dev/tcp/、fork bomb、$IFS、反斜杠转义、timeout 包裹递归检查。

**Q3. cgroup 不可用怎么办？**
- degrade-first：降级为纯 timeout，结果 degraded=True + 一次性事件，绝不静默声称限制了。

**Q4. 权限决策 5 级链？**
- allowed_modes → deny_tools_by_mode → profile.denied_tools → capabilities ⊆ allowed → risk vs auto_approve → risk vs approval_required → DENY。

**Q5. fail_closed 是默认吗？**
- 不是默认行为，是兜底：某 mode 无匹配 profile 时落到 fail_closed（∅ 能力 → 全 DENY）。

---

## W07 · 可观测 + Benchmark

**Q1. 可观测三件套各做什么？**
- TraceRecorder：全链 step 流（run_started→llm_iteration→tool_call→approval→sandbox→compaction→completion）。CostLedger：按 session/phase/tool 三维成本归因。ErrorClassifier：4 类结构化错误 + unknown 兜底。

**Q2. ErrorClassifier 是几类？**
- 4 类业务（PERMISSION_DENIED/NETWORK_TIMEOUT/MODEL_ERROR/PARAMETER_ERROR）+ UNKNOWN 兜底。审批拒绝系归 PERMISSION_DENIED。

**Q3. 评测怎么防止 agent 作弊？**
- 评测前 _hide_agent_invisible_task_files 把 task.json 藏起来，测完恢复。

**Q4. 回归门禁怎么判定？**
- 成功率 drop >5pp 或 p95 超 max(基线×1.05, 基线+1s) → FAIL。p95 只算通过任务，epsilon 防浮点误报。

**Q5. bootstrap CI 怎么保证可复现？**
- 固定 seed=0，2000 次重采样，纯 Python 无依赖（statistics.py:38）。

---

## 高频"讲一个坑"（选 3 个背熟）

1. **max_tokens 截断丢内容** → 追加 "Please continue" 续接（loop.py:673）。
2. **记忆误判不可逆** → git commit-before-write + revert（ADR-0002）。
3. **subagent 卡死 kill 成"用户取消"** → 先标 _budget_kill_reason 再 cancel（manager.py:645）。
4. **压缩弄断工具链** → tool-call pending 标记（manager.py:409）。
5. **评测 agent 读 task.json 作弊** → 评测前隐藏 task 文件（runner.py:632）。
