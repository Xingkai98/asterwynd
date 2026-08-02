# Design: 工具治理做深 — 语义去重 + 动态选择 + 质量评分

## Context

当前工具系统是"注册 + 权限"两层扁平结构：`ToolRegistry.get_all_schemas()` 每轮全量返回，`agent/loop.py` 每迭代全量注入，无 Top-K 选择。MCP 只在启动记录 status，无运行期健康。trace 只有单次 run 的 status/duration_ms，无跨 run 质量聚合。面试追问"1000 个工具怎么让模型选对"时只能答 BM25 概念。

## Goals / Non-Goals

**Goals:**

- 建立工具描述语义去重（embedding 余弦 >0.9 自动标记 + 差异说明注入）。
- 建立 BM25 粗筛 → embedding 精排 → reranker 重排 → Top5 注入的动态选择流水线。
- 建立基于调用成功率/平均耗时/用户确认率的 quality score，低分自动降级。
- 建立工具生命周期状态机（low traffic → deprecation → grace → removed）。
- 建立 MCP 运行期健康检查 + 失败率监控 + 自动降级。
- 先立 `agent/embedding/` 公共模块，供 #75 记忆复用。

**Non-Goals:**

- 不重做 tool permission 模型（allow/deny/require_approval 已存在，quality 降级与其组合）。
- 不做 MCP 之外的动态工具发现。
- 不实现跨 run 持久化质量 store 的复杂存储（轻量文件/JSON 起步）。

## Decisions

### Decision 1: `agent/embedding/` 公共模块先行，接口由本 change 定义

**方案**：本 change 先立 `agent/embedding/`（embedding 计算 + 向量相似度），接口稳定后供 #75 记忆（向量召回/去重冲突检测）复用。避免两个 change 各自建 embedding 基础设施。

**备选**：各自实现。被拒：重复建设，且接口不一致会导致后续难统一。

**理由**：共享基础设施是低成本高收益的公共底座。

### Decision 2: 动态选择流水线分两级，Top5 注入

**方案**：BM25 粗筛（全部工具 → Top50）→ embedding 精排 → reranker 重排 → Top5 注入 LLM tools 参数。每迭代选择，选择延迟纳入 trace。

**备选**：仅 BM25。被拒：面试口径和实际效果都要求多级选择。

**理由**：两级选择在延迟与精度间平衡，Top5 是主流 agent 的常用注入规模。

### Decision 3: quality score 用调用成功率/平均耗时/用户确认率，低分降级

**方案**：按 run 聚合 `status`/`duration_ms`/`approval`，算 quality score = 权重(成功率, 平均耗时, 用户确认率)。低于阈值自动降级（从 get_all_schemas 排除或降优先级）。

**备选**：仅成功率。被拒：无法反映耗时和用户偏好。

**理由**：多维度评分更贴近"工具好不好用"的真实语义。

### Decision 4: 生命周期状态机 four-state

**方案**：`low_traffic → deprecation → grace → removed`。新工具进 low_traffic 验证；触发 deprecation（quality 低/去重/停用）→ grace period → 自动从 get_all_schemas 移除。deprecation notice 注入 schema/上下文。

**备选**：无状态。被拒：无法管理工具退役。

**理由**：显式生命周期是工具治理的必备能力。

### Decision 5: MCP 运行期健康检查 + 失败率监控 + 自动降级

**方案**：McpServerStatus 增加运行期 health ping、失败率窗口统计、degraded 字段；失败率超阈值自动隐藏该 server 的 tools。

**备选**：仅启动态检查。被拒：无法反映运行期故障。

**理由**：MCP 动态工具需要运行期治理。

## Pre-Implementation Review

- 待 planning 阶段（batch-grill-me）确认本设计，并补齐 Reference Implementation Research 实质 findings 与 design impact。

## Reference Implementation Research

- status: enabled
- reason: 工具治理是成熟 coding agent 与 MCP 生态核心能力，需参考 Claude Code/Codex/Cursor 与 MCP 规范对工具选择、质量评分、生命周期和健康降级的实现。
- research questions:
  - 主流 coding agent 是否每迭代动态选择工具？Top-K 注入的粒度与延迟预算？
  - MCP 规范对 server 健康检查/工具发现/故障降级的标准？
  - BM25+embedding+reranker 选型（本地 vs 远程）与延迟实测？
- findings: 待 planning 阶段补充（proposal 阶段已登记 status/reason/questions；实质调研在本 change planning 阶段完成）。
- design impact: 待 planning 阶段补充；先决条件是与 #74 约定工具注入缝「稳定层/可变层」分层、与 #78 约定 trace 质量事件 schema。

## Risks / Trade-offs

- **[动态选择延迟放大] → Top-K 选择延迟纳入 trace，设置延迟预算（如 <50ms），超限降级为全量注入。**
- **[语义去重误判] → cosine 阈值可配置，去重标记提供人工确认入口。**
- **[quality 降级误伤] → 降级阈值可配置，降级前保留审计日志。**
- **[与 #74 Prefix Cache 张力] → 先约定「稳定层/可变层」分层策略，动态 Top-K 只变 tail，不破坏稳定前缀。**
- **[embedding 依赖] → 轻依赖纯 Python 起步，可替换为远程 embedding 服务。**

## Testing Strategy

- 单元测试：语义去重（embedding 相似度阈值）、BM25/embedding 排序、quality score 计算、生命周期状态机流转、MCP 健康降级。
- 集成测试：Top-K 注入 loop 集成、quality 降级与权限组合。
- 回归测试：既有 ToolRegistry/ModePolicy 测试不回归。
- benchmark 层级：工具选择延迟纳入 trace 验证。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/loop.py` | 工具注入缝（全量 get_all_schemas → Top-K） |
| `agent/tools/registry.py` | 语义去重、生命周期、Top-K 入口 |
| `agent/tools/factory.py` | 装配点 |
| `agent/trace_recorder.py` | 质量事件 schema |
| `agent/embedding/`（新） | 公共模块 |
| `agent/mcp/manager.py` | 运行期健康检查 |
| `agent/tool_permissions.py` | quality 与权限组合 |
| `agent/config.py` | 工具治理配置段 |
| `benchmarks/` | 质量聚合复用 statistics |
