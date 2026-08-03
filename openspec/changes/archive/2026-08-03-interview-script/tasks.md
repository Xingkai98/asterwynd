# Tasks: 面试讲稿文档 — 分层 15 问 + 代码走读 + 维护约束

## 1. 文档骨架

- [x] 1.1 `docs/interview-script/README.md`：索引 + 使用说明（五层分组 + 15 问列表）
- [x] 1.2 `docs/interview-script/` 下建 15 个问题文件占位（标题 + 空节）

## 2. 第一层：开场必问

- [x] 2.1 `Q01-architecture-overview.md`：项目定位与模块全景
- [x] 2.2 `Q02-agent-loop.md`：AgentLoop 主循环
- [x] 2.3 `Q03-differentiation.md`：与竞品差异化

## 3. 第二层：核心运行时

- [x] 3.1 `Q04-context-engineering.md`：上下文管理
- [x] 3.2 `Q05-tool-system.md`：工具系统
- [x] 3.3 `Q06-long-term-memory.md`：长期记忆
- [x] 3.4 `Q07-llm-provider.md`：LLM Provider

## 4. 第三层：关键能力

- [x] 4.1 `Q08-multi-agent.md`：多 Agent 协作
- [x] 4.2 `Q09-observability.md`：可观测性
- [x] 4.3 `Q10-sandbox.md`：安全沙箱
- [x] 4.4 `Q11-error-type.md`：工具错误处理

## 5. 第四层：工程化闭环

- [x] 5.1 `Q12-ci-testing.md`：CI 与测试体系
- [x] 5.2 `Q13-benchmark.md`：Benchmark 评测体系
- [x] 5.3 `Q14-dev-process.md`：开发流程

## 6. 第五层：深度亮点

- [x] 6.1 `Q15-memory-reversibility.md`：记忆可逆性坑

## 7. 维护约束与收尾

- [x] 7.1 AGENTS.md：文档地图加 `interview-script` + 建议性维护约束
- [x] 7.2 spec delta 合入 `openspec/specs/interview-script/spec.md`（受保护，需 workflow-events）
- [x] 7.3 归档 + 更新 backlog + artifact checker + openspec validate
