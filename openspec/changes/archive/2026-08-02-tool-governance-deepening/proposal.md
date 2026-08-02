# Proposal: 工具治理做深 — 语义去重 + 动态选择 + 质量评分

## Change Type

primary: feature
secondary:
  - tools
  - agent-runtime

## 需求

1. 工具描述语义去重：embedding 余弦相似度 >0.9 自动标记，生成差异说明注入 prompt
2. 动态选择流水线：BM25 粗筛（Top50）→ embedding 精排 → reranker 重排 → Top5 注入上下文
3. 质量评分：基于调用成功率/平均耗时/用户确认率的 quality score，低分自动降级
4. 生命周期状态机：新工具 low traffic 验证 → deprecation notice → grace period → 移除
5. MCP 动态工具：健康检查 + 失败率监控 + 自动降级

## 背景

当前工具系统是"注册 + 权限"两层扁平结构：`ToolRegistry.get_all_schemas()` 每轮把全部允许工具无差别返回，`agent/loop.py` 每个迭代全量注入 LLM tools 参数，无 Top-K 选择。MCP 工具只在启动 connect 时记录 `McpServerStatus`（ready/error），无运行期健康/失败率字段。trace 里只有单次 run 的 status/duration_ms，无跨 run 聚合的质量数据源。

面试场景追问"1000 个工具你怎么让模型选对"时，当前只能答 BM25 概念，没有落地。

## 非目标

- 不重做 tool permission 模型（allow/deny/require_approval 已存在，本 change 与其组合）。
- 不实现跨 run 持久化质量 store 的复杂存储（先用轻量文件/JSON，后续可换）。
- 不做 MCP 之外的动态工具发现。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/loop.py` | 工具注入缝（当前每迭代全量 get_all_schemas → Top-K 选择） |
| `agent/tools/registry.py` | 语义去重、生命周期状态、Top-K 选择入口 |
| `agent/tools/factory.py` | 装配点：所有工具经 factory 注册 |
| `agent/trace_recorder.py` | 质量事件 schema（status/duration/approval）需先定义 |
| `agent/embedding/`（新） | 公共 embedding/向量模块，供 #75 记忆复用 |
| `agent/mcp/manager.py` | MCP 运行期健康检查 + 失败率监控 + 降级 |
| `agent/tool_permissions.py` | quality 降级与权限判定组合 |
| `agent/config.py` | 新增工具治理配置段（cosine 阈值/质量窗口/生命周期时长） |
| `benchmarks/` | 质量聚合可复用 PR #80 的 statistics（bootstrap CI） |

## Reference Implementation Research

- status: enabled
- reason: 工具治理（语义去重/动态选择/生命周期/MCP 健康）是成熟 coding agent 和 MCP 生态的核心能力，应参考 Claude Code、Codex、Cursor 及 MCP 规范对工具选择、质量评分和降级策略的实现。
- research questions:
  - Claude Code / Codex 如何处理工具选择与 Top-K 注入？是否每迭代动态选择？
  - MCP 规范（2025-06 版）对 server 健康检查、工具发现和故障降级的标准是什么？
  - BM25+embedding+reranker 的典型延迟预算与选型（本地 vs 远程）？
- findings:
  - 待 planning 阶段补充（本 proposal 阶段完成 status/reason/questions 登记；实质调研在本 change 的 planning 阶段完成，findings 反哺 design 决策）。
- design impact:
  - 待 planning 阶段补充；先决条件：定义工具注入缝的「稳定层/可变层」分层策略（与 #74 Prefix Cache 约定），并定义 trace 质量事件 schema（与 #78 约定）。

## Dependencies

- 依赖 PR #80（benchmark-evaluation-depth，已合入）：质量聚合复用 statistics bootstrap CI。
- 与 #75 长期记忆共享 `agent/embedding/` 公共模块（本 change 先立接口）。
- 与 #78 可观测性共享 trace 质量事件 schema（需先定契约）。

## 验收

- 同一配置可输出语义去重标记、Top-K 选择延迟、质量评分分布、生命周期状态机流转。
- 面试可引用"1000 工具怎么管"的量化数据（语义去重 cosine 阈值、两阶段选择延迟、quality score 组成）。
