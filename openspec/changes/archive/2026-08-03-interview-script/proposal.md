# Proposal: 面试讲稿文档 — 由浅入深 15 问 + 代码走读 + 维护约束

## Change Type

primary: docs
secondary:
  - change-documentation

## 需求

1. 新建 `docs/interview-script/`，为面试准备的分层讲稿文档：**由浅入深 15 个顶层问题**，每问一个文件。
2. 每个问题含两部分：
   - **讲稿**（300-500 字）：面试时口头叙述，讲清该项目这一能力线怎么实现、踩过什么坑、怎么取舍。
   - **代码走读**（不限篇幅，讲清楚为止）：为支撑讲稿需走读的代码，列出入口调用链、关键文件、关键函数与设计理由。
3. **维护约束（建议性）**：每次有新的设计或架构变更后，应更新/新增对应问题的讲稿与走读；在 AGENTS.md 记录该约束作为建议。

## 背景

项目定位是大厂 Agent 相关开发岗位面试的 Coding Agent 系统（`docs/project-positioning.md`）。目前 `docs/architecture.md`、`docs/coding-agent-roadmap.md` 等是工程文档，但缺少**面向面试叙述的分层讲稿**——把"项目有哪些模块、怎么实现、为什么这么设计、踩过什么坑"组织成可直接口头表达的内容。

面试场景（issue #72 wayfinder 观察）：
- 4/8 场面试涉及可观测性/性能分析，3/8 涉及上下文工程，4/8 涉及多 Agent 架构。
- 面试官问"这个项目有多少模块/怎么实现/上下文怎么压缩/记忆怎么存/CI 怎么做/子 agent 怎么协作"。

本文档把已实现的能力（#74-79、#89、#99 等）组织成 15 个由浅入深的问答，每个带代码证据。

## 非目标

- 不是完整源码注释/API 文档（已有 docstring 与 `docs/architecture.md`）。
- 不覆盖所有代码，只覆盖面试叙述需要走的代码路径。
- 第一批固定 15 问，后续可扩展但不在本 change 内。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `docs/interview-script/Q01-Q15-*.md` | 新增 15 个问题文档 |
| `docs/interview-script/README.md` | 索引 + 使用说明 |
| `AGENTS.md` | 文档地图加 `interview-script`；维护约束（建议性） |
| `docs/openspec-change-backlog.md` | 未实现队列加本 change |
| 代码 | 无（纯文档，不改代码） |

## Reference Implementation Research

- status: disabled
- reason: 这是纯面试讲稿文档，不设计新技术方案，无需参考其他项目实现；参考的是本项目自身已实现的代码（各能力线的实现路径即是走读内容）。

## 验收

- `docs/interview-script/` 下 15 个问题文件 + README 索引存在。
- 每问：讲稿 300-500 字 + 代码走读（含调用链 + 关键文件 + 关键函数 + 设计理由）。
- AGENTS.md 文档地图含 `interview-script`，并记录维护约束。
- 讲稿覆盖：模块全景 / AgentLoop / 上下文 / 工具 / 记忆 / LLM / 多agent / 可观测 / 沙箱 / 错误 / CI / benchmark / 流程 / 记忆可逆性坑。
