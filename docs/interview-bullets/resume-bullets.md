# 简历项目亮点

- 实现可扩展 AgentLoop 核心循环（message-driven + 快照断点续传），以 7 切面 Hook 协议解耦迭代/LLM 调用/工具执行/错误处理/完成阶段，同构适配 OpenAI / Anthropic 双 Provider，集成 38 个内置工具
- 实现动态工具编排：BM25 粗筛 + 向量精排两阶段按对话上下文 Top-K 注入工具 schema，核心工具稳定层常驻且不占 Top-K 预算、配合 cache_control 断点保 LLM Prefix Cache 命中，工具语义去重 + 质量评分驱动软降级
- 内置 4 种多 Agent 编排模式（orchestrator-worker / peer-review / hierarchical / bidding）+ 子 agent 消息总线、token/时间双维度预算硬 kill 与快照恢复
- 实现 ContextBuilder 统一编排 8 个上下文源，稳定前缀分层注入、字节级不变命中 LLM Prefix Cache，搭配 AutoCompact L1/L2 层级压缩与 tool-call pending 标记防止工具链断裂
- 构建长期记忆系统，LLM 写时四分支去重（supplement/update/conflict + new 兜底），importance × recency 联合时效衰减（30 天半衰期）、超期未访问自动归档且可恢复，git commit-before-write + revert 机制保障数据可逆
- 实现 3 层纵深防御安全体系：工作区路径边界 + 敏感文件 deny 与 mode 权限 fail-closed → CommandGuard 语义级命令检查覆盖绕过变体 → 进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端，配合细粒度工具权限、受控只读浏览器（URL 白名单 + 只读工具集）和人工审批链路
- 建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；72 个 coding 任务（34 本地 = 22 A 轨回归基线 + 12 B 轨当前演进 + 38 SWE-bench Verified 子集）在 git worktree / Docker 隔离执行，pass@1/pass^k/成本（cache-aware）与 fault_owner 归因统计，场景×难度分层覆盖矩阵，支持跨 Agent 配对比较与 CI 回归门禁
