# Asterwynd 代码走读材料（W01-W07）

> 按简历 7 条项目经历 bullet 逐条走读。每份材料含：**代码入口 → 核心逻辑 → 简历核实 → 面试加分点 → 高频拷打**。
> 与 `agent-internals.md` 有出入时**以代码为准**。
> 配套总纲见 [../FINAL-master-script.md](../FINAL-master-script.md)（整合版面试讲稿 + 数字速查表）。

| # | 文件 | 对应简历 bullet | 核心模块 |
|---|------|----------------|---------|
| W01 | [W01-agent-loop.md](W01-agent-loop.md) | bullet 1 | AgentLoop 主循环 + Hook + 双 Provider |
| W02 | [W02-tool-governance.md](W02-tool-governance.md) | bullet 2 | 动态工具编排 |
| W03 | [W03-multi-agent.md](W03-multi-agent.md) | bullet 3 | 多 Agent 编排模式 |
| W04 | [W04-context-engineering.md](W04-context-engineering.md) | bullet 4 | ContextBuilder 上下文工程 |
| W05 | [W05-long-term-memory.md](W05-long-term-memory.md) | bullet 5 | 长期记忆系统 |
| W06 | [W06-security.md](W06-security.md) | bullet 6 | 3 层纵深防御 |
| W07 | [W07-observability-benchmark.md](W07-observability-benchmark.md) | bullet 7 | 可观测 + Benchmark |
| 自测 | [self-test-QA.md](self-test-QA.md) | 全部 | 面试自测 Q&A（对照 W01-W07 用） |

## 简历数字核实结果（走读前先看这个）

| 简历表述 | 真实值 | 结论 |
|---------|--------|------|
| "40+ 内置工具" | 38 内置 + MCP/子代理动态 → 全量 40+ | ✅ 已修正：简历改"38 个内置工具" |
| "7 切面 Hook" | 正好 7 个 | ✅ |
| "8 个上下文源" | 正好 8 个 | ✅ |
| "4 种多 Agent 编排" | 正好 4 种 | ✅ |
| "3 层纵深防御" | policy → guard → sandbox | ✅ |
| "36+ 任务（26 本地 + 10 SWE-bench）" | 26 + 10 = 36 | ✅ |
| "1700+ 自动化测试" | 130 文件 / ~1691 函数 | ✅ |
| "~27K 行生产代码" | 26875 行 | ✅ |
