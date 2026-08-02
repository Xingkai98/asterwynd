# 工具治理 规格

## Purpose

定义 工具治理 能力域的规格：语义去重、动态选择、生命周期状态机、质量评分、MCP 健康检查。当前实现位于 `agent/tools/governance/` 与 `agent/embedding/`。

## Requirements

### Requirement: 工具治理能力域基线

工具治理能力域 SHALL 提供基础能力，深化需求通过 OpenSpec change 的 ADDED Requirements 合入演进。

#### Scenario: 能力域可扩展

- **GIVEN** 一个针对 工具治理 能力域的 OpenSpec change
- **WHEN** 该 change 的 spec delta 被接受
- **THEN** 能力域的 requirement 随 ADDED Requirements 演进

### Requirement: 语义去重（软提示）

工具治理系统 SHALL 在工具注册时对全体工具描述做 embedding 预计算，cosine 超过可配置阈值（n-gram 后端默认 0.7）标记 `duplicate_of` 为 first-registered primary；选择时若被标记工具进入 Top-K，SHALL 注入差异说明作为软提示（非硬约束）。

#### Scenario: 相似工具被标记

- **GIVEN** 两个工具描述 embedding cosine > 阈值
- **WHEN** 工具注册完成
- **THEN** 后注册工具 SHALL 被标记 `duplicate_of` 先注册工具
- **AND** 该标记作为 Tool 元数据存储，不注入正式 schema

#### Scenario: 不同能力工具不误标

- **GIVEN** 两个工具描述 embedding cosine < 阈值
- **WHEN** 工具注册完成
- **THEN** 两者 SHALL NOT 互相标记为 duplicate

### Requirement: 动态选择（稳定层 + Top-K）

工具治理系统 SHALL 提供 BM25 粗筛（Top50）→ embedding 精排 → Top-K 注入的动态选择流水线；稳定层核心工具 SHALL 确定性排序始终注入；选择延迟 SHALL 记录并受可配置预算约束，超预算降级为全量注入。

#### Scenario: Top-K 选择

- **GIVEN** 工具集与一个 query
- **WHEN** 选择流水线运行
- **THEN** 返回相关 Top-K 工具（稳定层工具始终包含）
- **AND** 选择延迟被记录

#### Scenario: 超预算降级

- **GIVEN** 选择延迟超过可配置预算
- **WHEN** 选择流水线运行
- **THEN** 降级为全量可见工具注入（保持向后兼容）

### Requirement: 生命周期状态机

工具治理系统 SHALL 管理工具生命周期 `low_traffic → deprecation → grace → removed`；`mark_deprecated` 触发 deprecation 并立即进入 grace（工具仍可见 + deprecation notice）；grace 到期自动 `removed` 并从选择/schema 排除。

#### Scenario: grace 到期移除

- **GIVEN** 工具被 mark_deprecated 且 grace 到期
- **WHEN** 生命周期状态机推进
- **THEN** 工具进入 `removed`
- **AND** 从 `get_all_schemas` 排除

### Requirement: Tool 元数据旁路表

工具治理系统 SHALL 在 ToolRegistry 内维护 `dict[tool_name, ToolMetadata]` 旁路表（不改 Tool 基类），存储 `duplicate_of`/`lifecycle_state` 等治理字段；`get_all_schemas` SHALL 不注入治理字段以保证稳定前缀。

#### Scenario: 治理字段不进正式 schema

- **GIVEN** 一个被标记的工具
- **WHEN** `get_all_schemas` 返回 schema
- **THEN** schema 中 SHALL NOT 包含 `duplicate_of`/`lifecycle_state` 字段

### Requirement: 工具注入缝

`agent-runtime` 的工具注入 SHALL 使用 Top-K 选择（`select_schemas(query, k=5)`）替代无条件全量 `get_all_schemas` 注入，保留 `tools=tool_schemas if tool_schemas else None` 降级语义。

#### Scenario: 无 selector 时回退全量

- **GIVEN** 未配置 selector
- **WHEN** loop 注入工具 schema
- **THEN** 回退为全量可见工具注入（原行为）

### Requirement: 质量评分（软降级）

工具治理系统 SHALL 按调用结果聚合每工具 quality score（成功率/平均耗时因子/用户确认率加权，权重可配置）；低于可配置阈值（默认 0.4，需 min_samples 默认 5）的工具有资格软降级——从动态选择的可变层候选排除，但 `get_all_schemas` 仍可见可调用；quality SHALL NOT 覆盖权限判定；窗口状态 SHALL 支持 JSON 持久化跨 run 聚合。

#### Scenario: 低分工具退出可变层

- **GIVEN** 一个工具 quality score 低于降级阈值
- **WHEN** `select_schemas` 运行
- **THEN** 该工具 SHALL NOT 出现在可变层选择候选
- **AND** 稳定层工具 SHALL 始终注入（即使被降级）

#### Scenario: 软降级不改变权限

- **GIVEN** 一个被权限模型拒绝的工具且 quality score 很高
- **WHEN** `get_all_schemas` 或 `execute` 运行
- **THEN** 权限判定结果 SHALL NOT 改变

### Requirement: MCP 运行期健康检查

工具治理系统 SHALL 对 MCP server 提供运行期健康检查：后台定时 `ping`（间隔可配置默认 30s）+ 真实调用失败率滑动窗口（默认 20）；失败率超阈值（默认 0.5）或 ping 失败时 server 进入 `degraded`，其 tools SHALL 从 `get_all_schemas`/`select_schemas` 排除；窗口滑动或 ping 恢复后 SHALL 自动恢复。`McpServerStatus` SHALL 暴露 `health_ok`/`last_health_check`/`calls`/`failures`/`failure_rate`/`degraded`。

#### Scenario: 失败率超阈值降级

- **GIVEN** 某 MCP server 最近调用失败率 ≥ 阈值
- **WHEN** 状态查询或 schema 暴露
- **THEN** server SHALL 标记 `degraded`
- **AND** 该 server 的 tools SHALL 从 schema 排除

#### Scenario: 健康恢复自动解除

- **GIVEN** 已降级 server 的失败率窗口滑动至低于阈值且 ping 恢复
- **WHEN** 状态查询或 schema 暴露
- **THEN** `degraded` SHALL 自动解除
- **AND** 该 server 的 tools SHALL 重新可见
