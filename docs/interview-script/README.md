# 面试讲稿文档

面向大厂 Agent 相关开发岗位面试的分层讲稿。按**由浅入深**组织 15 个顶层问题，每个问题一个文件，含两部分：

- **讲稿**（300-500 字）：面试时口头叙述，讲清"这条能力线怎么实现 + 为什么这么设计 + 踩过什么坑"。
- **代码走读**（不限篇幅，讲清楚为止）：为支撑讲稿需走读的代码，列出入口调用链、关键文件、关键函数与设计理由。

## 使用方式

面试前建议**先通读讲稿建立叙事，再走读代码建立证据**。每问自包含，不依赖其他问题。

## 五层结构（由浅入深）

### 第一层：开场必问（讲清"这是什么项目"）

| # | 问题 | 一句话 |
|---|------|--------|
| [Q01](questions/Q01-architecture-overview.md) | 项目定位与模块全景 | 目标岗位、主线能力链、模块地图 |
| [Q02](questions/Q02-agent-loop.md) | AgentLoop 主循环 | 一次对话从输入到输出的完整链路 |
| [Q03](questions/Q03-differentiation.md) | 与竞品差异化 | 不只是能用，每条能力线做多深 |

### 第二层：核心运行时（面试追问主体）

| # | 问题 | 一句话 |
|---|------|--------|
| [Q04](questions/Q04-context-engineering.md) | 上下文管理 | 怎么构造、压缩、注入 |
| [Q05](questions/Q05-tool-system.md) | 工具系统 | 注册、治理、动态选择 |
| [Q06](questions/Q06-long-term-memory.md) | 长期记忆 | 存储、去重、衰减、可逆 |
| [Q07](questions/Q07-llm-provider.md) | LLM Provider | 抽象、错误、成本 |

### 第三层：关键能力（面试"有没有踩过坑"）

| # | 问题 | 一句话 |
|---|------|--------|
| [Q08](questions/Q08-multi-agent.md) | 多 Agent 协作 | spawn、快照、预算、消息总线、编排模式 |
| [Q09](questions/Q09-observability.md) | 可观测性 | trace、metrics、成本归属、异常分类 |
| [Q10](questions/Q10-sandbox.md) | 安全沙箱 | 命令护栏、隔离、资源限制 |
| [Q11](questions/Q11-error-type.md) | 工具错误处理 | error_type 结构化 |

### 第四层：工程化闭环（面试"怎么保证质量"）

| # | 问题 | 一句话 |
|---|------|--------|
| [Q12](questions/Q12-ci-testing.md) | CI 与测试体系 | 分层测试 + 门禁 |
| [Q13](questions/Q13-benchmark.md) | Benchmark 评测 | 分层指标 + SWE-bench |
| [Q14](questions/Q14-dev-process.md) | 开发流程 | OpenSpec + grill + 审阅闭环 |

### 第五层：深度亮点（面试"讲一个踩过的坑"）

| # | 问题 | 一句话 |
|---|------|--------|
| [Q15](questions/Q15-memory-reversibility.md) | 记忆可逆性坑 | mem0 转向 ADD-only → 我们 git 对冲 |

## 维护约束

每次有新的设计或架构变更后，应检查本目录中对应问题是否需更新讲稿与代码走读；若变更引入新能力线，可新增问题文件。该约束为建议，不设机械门禁。

## 材料结构（两层互补）

本目录有两套材料，按"使用时机"分工，**不是冗余**：

| 材料 | 组织方式 | 使用时机 |
|------|---------|---------|
| **questions/ 单问题讲稿**（Q01-Q15） | 按面试问题（15 个顶层问），每问 = 讲稿(300-500字) + 代码走读 | **深入准备时逐问看**；含 walkthrough 没有的工程流程/差异化（Q03/12/14） |
| **walkthrough/ + FINAL-master-script.md** | 按简历 bullet（7 条）+ 总纲 + 数字速查 | **面试前一晚/当天快速过**；速查型 |

- **深入**：按问题看 Q 系列（每个问题自包含）。
- **速查**：按简历 bullet 过 walkthrough/，最后对 FINAL-master-script.md 的数字速查表 + 高频拷打清单自测。
- **自测**：walkthrough/self-test-QA.md 提供逐模块 Q&A，对照源码核实。
