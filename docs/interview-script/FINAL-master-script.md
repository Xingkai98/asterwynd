# Asterwynd 面试总讲稿（整合版）—— 面试前快速过一遍

> 本讲稿基于完整代码走读整理，所有数字均已核实到源码。与 `agent-internals.md` 有出入时**以代码为准**。
> 配套：[questions/](questions/) 下 Q01-Q15 单问题讲稿（本文件是它们之上的总纲 + 速查）。
> 最后更新：2026-08-08，基于 7 条简历 bullet 逐条走读。

---

## 0. 30 秒电梯 pitch（开场必须背熟）

> "我独立实现了一个 coding agent 系统 **Asterwynd**，约 2.7 万行生产代码、1700+ 自动化测试、44 任务评测闭环。它的核心是一个消息驱动的 AgentLoop，围绕它做了完整的能力纵深：上下文工程（8 源分层注入 + 稳定前缀命中 Prefix Cache + L1/L2 分层压缩）、工具系统（38 内置工具 + 动态 Top-K 选择 + 质量软降级）、长期记忆（LLM 写时三路去重 + importance×recency 衰减 + git 可逆写入）、多 Agent 编排（4 种模式 + 消息总线 + 预算硬 kill + 快照恢复）、3 层纵深防御安全体系，以及全链路可观测 + Benchmark 回归门禁。每条能力线都能讲清设计取舍和踩过的坑，有 ADR 记录决策。"

**关键叙事要点**：
1. 不是堆功能，是每条线做深到"能讲出取舍"。
2. 工程纪律：OpenSpec 需求先行 → grill 设计追问 → 独立 subagent 审阅闭环 → CI 门禁 → 归档收尾。
3. 数字都真实可复现（下面速查表）。

---

## 1. 项目故事线（"这是什么项目"）

| 维度 | 讲法 |
|------|------|
| **定位** | local、benchmarkable 的 coding agent，面向大厂 Agent 开发岗位的能力证明项目 |
| **主线** | Agent 运行时 → 工具调用 → 上下文 → 记忆 → 多 Agent → 可观测 → 评测闭环 |
| **不是** | 不是通用 agent 框架、不是复刻 Claude Code 功能清单（Q03 展开） |
| **验证** | 44 任务（34 本地 + 10 SWE-bench）+ bootstrap CI + CI 回归门禁 |

---

## 2. 七条简历 bullet 的"讲法 + 证据 + 拷打"

每条给：**一句话讲法 → 代码入口 → 面试官可能追问 → 加分细节**。

### Bullet 1 · AgentLoop 核心循环 + Hook + 双 Provider

- **讲法**："`messages` 是唯一主状态，消息驱动。主循环每轮：选工具 → 注入上下文 → 调 LLM → 无工具调用则结束，有则两阶段执行（预处理审批 + 并行执行）→ 回填 → 压缩检查。7 切面 Hook 解耦横切关注点；OpenAI/Anthropic 双 Provider 同构到统一 `LLMResponse`。"
- **入口**：`agent/loop.py:112` AgentLoop；主循环 `loop.py:605`；Hook 协议 `agent/hooks/manager.py:15`；Provider `agent/openai_llm.py` / `agent/anthropic_llm.py`。
- **拷打点**：
  - "为什么 message-driven？" → 天然匹配 LLM 输入输出；序列化 messages 即快照（断点续传基础）；tool-call 消息链合法性借 API 强制。
  - "快照续传怎么做？" → `loop.py:557` resume 分支还原 mode/todos/skills/messages；`agent/session.py` 原子写 + 哈希去重 + schema 校验。
  - "两个 provider 差异在哪些点？" → Anthropic system 拆顶层字段、连续 tool_result 合并到同一条 user 消息、text 必须在 tool_use 前；OpenAI 的 tool 消息图片延迟 flush。
- **加分细节**：`max_tokens` 截断续接（`loop.py:673`，踩过的坑）；Bash 不走 retry 而其他工具走（`loop.py:1196`）；审批参数脱敏 `redact_value`。

### Bullet 2 · 动态工具编排

- **讲法**："38 个内置工具全塞给 LLM 浪费 token。用 BM25 粗筛 50 → embedding 精排取 Top-K=5 注入；7 个核心工具构成稳定层、恒在前且字节不变，保住 Prefix Cache 命中；注册时语义去重、运行时质量评分软降级。"
- **入口**：`agent/tools/governance/selector.py:66`；接线 `agent/tools/factory.py:113`；注入点 `agent/loop.py:986` `_select_tool_schemas`。
- **拷打点**：
  - "稳定层为什么不占 Top-K 预算？" → 稳定前缀必须字节不变才能命中缓存，变层才是变化的尾巴（`selector.py:107`）。
  - "质量降级会禁用工具吗？" → 不会，软降级只退出变层候选，schema 仍可见、仍可调用，权限模型不动（`registry.py:114`）。
- **加分细节**：NGramEmbedding 零依赖默认 + `EmbeddingProvider` Protocol 可换真 embedding；延迟预算只记录不阻塞；语义去重是软提示非硬约束（"模型自己决定"）。

### Bullet 3 · 多 Agent 编排

- **讲法**："4 种编排模式，确定性骨架（spawn N → wait → collect）+ 模式内智能由 LLM 子 agent 承载。消息总线只交换语义摘要、三层预算防爆炸。token 超限走 hook、时间超限走后台 monitor，两条路径都先写检查点再 kill——预算 kill 永远可恢复。"
- **入口**：`agent/subagent/patterns.py`；`bus.py`；`budget.py`；`snapshot.py`；`manager.py`。
- **拷打点**：
  - "4 种模式分别适合什么？" → orchestrator-worker 并行扇出；peer-review 迭代批判；hierarchical 可嵌套（depth 上限 3）；bidding 独立方案 + selector 评选。
  - "bidding 为什么不用 bus 传提案？" → drop-oldest 会丢关键投标，用紧凑摘要 + 读 artifacts（`patterns.py:179`）。
  - "token 超时怎么 kill？" → 时间超限时 hook 不触发（卡在工具调用），monitor 先写 `_budget_kill_reason` 再 cancel，CancelledError handler 记 budget_exceeded 而非 cancelled（`manager.py:645`）。
- **加分细节**：恢复是 transcript 级而非 stack 级（诚实边界）；模式钳位（子 ≤ 父权限）；并发 4 / 深度 3 护栏（防无界烧钱）。

### Bullet 4 · ContextBuilder 上下文工程

- **讲法**："8 个上下文源按 P0-P5 优先级编排。critical（P0/P1）永不裁剪，cacheable 稳定前缀（P0/P1/P2）字节级不变命中 Prefix Cache。AutoCompact 做 L1/L2 分层压缩（L1 增量摘要、L2 在累计超 6K 时压缩成顶层结论）；压缩前给未完成的 tool call 打 pending 标记，防止工具链断裂。"
- **入口**：`agent/context/builder.py:27`；8 源注册 `agent/loop.py:1339`；压缩 `agent/memory/manager.py:141`。
- **拷打点**：
  - "稳定前缀怎么命中缓存？" → `build_blocks` 把 cacheable 层标 `cache=True`，Anthropic 在最后稳定块放 cache_control 断点（`loop.py:1103` `_compute_cache_plan`）。
  - "L1/L2 为什么分层？" → 只压 L1 会无限膨胀；L2 把多个 L1 压成顶层结论，且 L2 输入带旧 L2 base，顶层结论不丢上下文（`manager.py:285`）。
  - "tool-call pending 是什么？" → 压缩会把中间 tool result 压掉，assistant 的 tool_call 若没有对应 result 就标记 `[call#<i>: <id> pending]`（`manager.py:409`），防止消息链非法。
- **加分细节**：摘要作为 user 消息注入（"先前上下文而非系统约束"）；Read 分页进度保留 `(file, offset, total)`；静态源渲染缓存（`builder.py:45`）。

### Bullet 5 · 长期记忆

- **讲法**："写时 LLM 三路去重（supplement/update/conflict）+ new 兜底，相似度低于阈值短路零成本。importance × recency 联合衰减（30 天半衰期、超期未访问且分数低于阈值自动归档、可恢复）。**git commit-before-write 保证可逆**——误判了也能 checkout 回来。对比 mem0 后自主选 git 路线，ADR 记录。"
- **入口**：`agent/memory/persistent.py`；去重 `agent/memory/dedup.py`；可逆 `git_backend.py`；ADR `docs/adr/ADR-0002*`。
- **拷打点**：
  - "为什么不用 mem0 的 ADD-only？" → ADD-only 的前提是读路径有强 ranker（时间/BM25/实体多信号），Asterwynd 只有 NGramEmbedding。可逆性做在写路径上：commit-before-write（ADR-0002）。
  - "误判了怎么恢复？" → `MemoryGitBackend.revert` 两段式：先 snapshot 当前态 → checkout 旧 body + 重建索引 + 记 changelog → 再 commit（`git_backend.py:69`）。
  - "衰减怎么算？" → `score = importance × 0.5^(days/30)`；importance 1-5 默认 3；recall/search 会 touch 更新 last_accessed_at（`persistent.py:840`）。
- **加分细节**：LLM 提供的 target_name 写前校验 kebab-case 防路径穿越（`persistent.py:568`）；懒初始化 git（写前才 init）；内联 git identity 兼容 CI。

### Bullet 6 · 3 层纵深防御

- **讲法**："第一层 WorkspacePolicy：路径边界 + 敏感文件 deny + 命令拒绝列表。第二层 CommandGuard：语义级命令校验覆盖绕过变体（flag 重排、timeout 包裹、$IFS、反斜杠转义）。第三层沙箱：ProcessBackend + cgroup v2 资源限制 或 Docker 容器隔离（--network none），双后端可选。细粒度工具权限（8 能力 × 3 风险 × profile）+ 人工审批链 + 浏览器沙箱。"
- **入口**：`agent/workspace_policy.py`；`agent/tools/command_guard.py`；`agent/tools/sandbox/{process_backend,cgroup,docker_backend}.py`；`agent/tool_permissions.py`；`agent/run_config.py:97`。
- **拷打点**：
  - "三层各守什么？" → 路径边界守文件、guard 守命令语义、sandbox 守真正隔离。**guardrail 不是 boundary**（引用 Claude Code 2025 CVE：正则校验可绕过）。
  - "cgroup 不可用怎么办？" → degrade-first：降级为纯 timeout，结果带 `degraded=True` + 一次性事件——绝不静默声称限制了（`process_backend.py:8`）。
  - "`timeout 5 rm -rf /` 能绕过吗？" → 不能，`_check_timeout` 递归检查被包命令（`command_guard.py:269`）。
- **加分细节**：`memory.swap.max=0` 硬禁 swap 防 malloc 炸弹绕过 OOM；pid-reuse starttime 守卫防杀错进程；`add_root` 祖先目录守卫；审批参数脱敏；fail_closed profile 是兜底（∅ 能力）。

### Bullet 7 · 可观测 + Benchmark

- **讲法**："TraceRecorder 全链 step 流（run_started→llm_iteration→tool_call→approval→sandbox→compaction→completion）；CostLedger 按 session/phase/tool 三维成本归因；ErrorClassifier 结构化错误分类（4 类 + unknown 兜底，审批拒绝系归到 permission_denied）。评测 44 任务在 git worktree 隔离执行，bootstrap 95% CI（固定 seed 可复现），CI 回归门禁对比 baseline。评测在升级：任务集从 44 扩到升级目标 ~90（场景×难度分层，A 轨 20–24 + B 轨 12–16 + Verified 50）、指标加 pass^k 与 cost@pass、SWE-bench 引用带污染披露——设计已定，实现中。"
- **入口**：`agent/trace_recorder.py`；`agent/cost_tracker.py`；`agent/observability.py`；`benchmarks/{runner,statistics,gate,compare}.py`。
- **拷打点**：
  - "评测怎么防止 agent 作弊？" → `_hide_agent_invisible_task_files` 评测前藏掉 task.json（`runner.py:632`）。
  - "回归门禁怎么判定？" → 成功率 drop >5pp 或 p95 超 `max(基线×1.05, 基线+1s)` → FAIL；p95 只算通过任务；epsilon 防浮点误报（`gate.py:148`）。
  - "bootstrap CI 怎么保证可复现？" → 固定 seed=0，2000 次重采样，纯 Python 无依赖（`statistics.py:38`）。
- **加分细节**：ErrorClassifier 诚实边界（幻觉类不自动分类，需 LLM judge）；CostLedger 与 trace 解耦（财务记录 vs 过程记录）；`_flushed_count` 游标防重复追加。

---

## 3. 数字速查表（全部核实过，面试被追问时直接答）

| 数字 | 真实值 | 出处 |
|------|--------|------|
| 代码行数 | 26875 行（agent/ 目录） | `find agent -name "*.py" \| xargs cat \| wc -l` |
| 自动化测试 | 148 测试文件 / ~1997 测试函数 | `tests/` |
| 内置工具 | 38 个（KNOWN_BUILTIN_TOOL_NAMES 已知名数，含默认关闭的浏览器工具） | `agent/tools/factory.py` `KNOWN_BUILTIN_TOOL_NAMES` |
| 全量工具（含 MCP/subagent） | 40+（38 内置已知名数含默认关闭的浏览器工具 + 10 子代理控制 + MCP 按需动态挂载） | 同上 + `loop.py:358` |
| 上下文源 | 8 个 | `loop.py:1339` |
| Hook 切面 | 7 个 | `hooks/manager.py:15` |
| 编排模式 | 4 种 | `subagent/patterns.py:203` |
| 评测任务 | 44（34 本地 + 10 SWE-bench） | `benchmarks/tasks/` |
| 评测任务（升级目标） | ~90（设计已定：A 轨 20–24 + B 轨 12–16 + Verified 50；当前已落 44） | C1 `evaluation-task-spec` |
| pass^k | 全部 k 次成功（可靠性指标） | statistics.py 新增聚合（C2） |
| cost@pass | $/resolved-task，cache-aware 四档定价 | cost_tracker 扩展（C2/C3） |
| fault_owner | {agent, task, environment, unknown} | C2 |
| 预算 | `--budget-cap <USD>` / 0 取消 | C2/C3 |
| 记忆衰减 | 30 天半衰期、importance 1-5、归档阈值 1.5 | `memory/persistent.py:43-51` |
| 压缩阈值 | max_tokens − 15K；L2 触发 6K | `memory/manager.py:155,83` |
| 上下文注入预算 | min(20K, 窗口×20%) | `loop.py:1337` |
| 工具选择 | Top-K=5、BM25 粗筛 50、延迟预算 50ms | `config.py:90-91` |
| 质量降级 | 窗口 50、阈值 0.4、成功率/耗时/审批 = 0.5/0.3/0.2 | `governance/quality.py:24-30` |
| 编排护栏 | 并发 4、深度 3 | `subagent/manager.py:146-154` |
| 错误分类 | 4 类业务 + unknown 兜底 | `observability.py:20` |
| bootstrap CI | 95%，2000 次重采样，seed=0 | `statistics.py:38` |
| 回归门禁 | 成功率 drop >5pp；p95 基线×1.05+1s 绝对下限 | `gate.py:34-35` |
| 默认超时 | Bash 30s；LLM 流式 60s / 非流式 180s | `sandbox/process_backend.py:72`；`llm.py:105` |

> **口径要点**：简历已改为"38 个内置工具"（精确数）。若被追问"为什么不是 40+"，答"38 内置 + MCP 和子代理控制工具动态挂载后到 40+"。

---

## 4. 高频拷打清单（"讲一个踩过的坑"）

1. **max_tokens 截断丢内容** → 追加"Please continue"续接（`loop.py:673`）。
2. **Anthropic tool_result 必须合并** → 连续 tool 消息并到同一条 user 消息（`anthropic_llm.py:138`）。
3. **压缩弄断工具链** → tool-call pending 标记 + recent 窗口回溯 assistant（`manager.py:371`）。
4. **记忆误判不可逆** → git commit-before-write + revert（ADR-0002，对 mem0 的取舍）。
5. **cgroup 不可用会"假装限制"** → degrade-first 绝不静默（`process_backend.py:8`）。
6. **`timeout 5 rm -rf /` 绕过** → 递归检查被包命令（`command_guard.py:269`）。
7. **subagent 卡死 kill 成"用户取消"** → 先标 `_budget_kill_reason` 再 cancel（`manager.py:645`）。
8. **gate 浮点误报** → `1.0-0.95` 的 epsilon 守卫（`gate.py:148`）。
9. **评测 agent 读 task.json 作弊** → 评测前隐藏 task 文件（`runner.py:632`）。
10. **openai 图片 tool 消息** → 延迟 flush 到下一条非 tool 消息（`openai_llm.py:277`）。

---

## 5. 简历口径记录

- 走读共核实 7 条 bullet，**无硬错误**。
- ✅ 本次走读修正：bullet 1 "40+ 内置工具" → "38 个内置工具"（精确数），已重编译为 1 页 PDF。
- 之前已修正（历史）：37→36+ 任务、41→40+ 工具、移除"减少上下文膨胀 40%"、"6 种错误类型"去数字化、fail-closed 归位、双层→双后端。
- 待用户确认：面试加分点（评测防作弊、guardrail 不是 boundary 等）是否整合进简历。
