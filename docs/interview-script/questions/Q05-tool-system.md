# Q05: 工具系统——注册、治理、动态选择

## 讲稿

工具系统是 agent 能力的入口。Asterwynd 工具系统分三层：**注册、安全、治理**。

**注册层**。`ToolRegistry` 是工具注册中心，所有工具继承 `Tool` 基类，用 `@tool_parameters` 声明 schema（名称、描述、参数），注册进 registry 后 schema 暴露给 LLM。工具分内置（Read/Write/Edit/Bash/Grep 等）和外部（MCP 工具包装成 `McpTool`，模型可见名为 `mcp__<server>__<tool>`）。

**安全层**。每个工具带 `ToolPermission`——capability（如 workspace_read/workspace_write/command_execute）、risk level（low/medium/high）、origin（builtin/mcp）三要素。`ModePolicy` 按 permission profile 产生 `allow`/`deny`/`require_approval` 三值判定。默认 build mode 直接允许 low/medium，高风险（Bash、Write）需审批。`WorkspacePolicy` 负责路径/命令白名单黑名单，不能被 capability metadata 绕过。

**治理层（#77，这是面试亮点）**。工具会越来越多，全塞给 LLM 浪费 token。`ToolSelector` 做动态选择：**稳定层**（核心 coding 工具如 Bash/Read/Write/Edit）常驻注入、排序在前，其余 slot 用 BM25 粗筛 → embedding 重排填满 Top-K。`SemanticDeduper` 做语义去重，`ToolQualityStore` 做质量评分软降级——低分工具从候选退出但稳定层工具即使被降级也始终注入。

面试重点：动态选择解决"工具多塞不下"的问题，而稳定层保证核心工具永不缺席；质量软降级是"用历史数据淘汰不可靠工具"的工程闭环。

## 代码走读

### 入口与调用链

```
AgentLoop._select_tool_schemas (loop.py:622) → ToolRegistry.select_schemas (registry.py:95)
  → ToolSelector.select (governance/selector.py:66) → 稳定层 + BM25 粗筛 + embedding 重排
  → ToolRegistry.execute → Tool.execute
```

### 关键文件逐段

**`agent/tools/registry.py` `class ToolRegistry`**
- `register(tool)`（31 行）：注册工具，暴露 schema。
- `set_selector`/`set_deduper`/`set_quality`（39-45 行）：注入治理组件（#77 接线点）。
- `select_schemas(query, k)`（95 行）：动态选择工具 schema，供 LLM 调用。
- `_sync_governance_indexes`（76 行）：工具注册时同步到 selector/deduper 索引。
- 质量降级：`_is_quality_degraded`（63 行）+ `is_stable`（selector）共同决定"稳定层即使降级也注入"。

**`agent/tools/base.py`** — `Tool` 基类 + `@tool_parameters`。
- 声明 schema（name/description/parameters）、`read_only`、`permission`。
- 这是所有内置工具的契约（`agent/tools/builtin/` 下每个工具一个类）。

**`agent/tools/factory.py`** — 工具装配。
- `KNOWN_BUILTIN_TOOL_NAMES`（65 行）：内置工具白名单。
- `_wire_governance`（105 行）：selection enabled 时装配 selector/deduper/quality。
- 工具构造列表（约 334 行）：实例化所有内置工具，注册进 registry。

**`agent/tools/governance/selector.py` `class ToolSelector`**
- `index_tool`（47 行）：工具描述 → embedding 向量 + BM25 统计。
- `set_stable_tools`（58 行）：稳定层白名单（`agent/loop.py:81` `CORE_STABLE_TOOL_NAMES`），Q3 契约"核心工具常驻"。
- `is_stable`（62 行）：稳定层判断。
- `select`（66 行）：稳定层恒在前 + BM25 粗筛 → embedding 重排 → Top-K 填满。
- 延迟记录：`last_selection_latency_ms` + `last_timed_out`（79 行），供质量评分用。

**`agent/tools/governance/dedup.py` `class SemanticDeduper`** — 语义去重：embedding 相似度超阈值视为重复工具，避免重复注入。

**`agent/tools/governance/quality.py` `class ToolQualityStore`** — 质量评分：加权 blend（成功率/平均耗时/审批率），低于 `degrade_threshold` 软降级退出候选。

**`agent/tool_permissions.py`** — `ToolPermission`（capability/risk/origin）+ `ModePolicy` 三值判定 + permission profiles。

**`agent/workspace_policy.py`** — 路径/命令安全边界（allowlist/denylist/敏感路径），不被 capability metadata 绕过。

### 设计理由

- **注册与治理分离**：registry 只管注册/执行，selector/deduper/quality 是可选治理插件，通过 `set_*` 注入——不启用治理时零开销。
- **稳定层 vs 动态 Top-K**：动态选择省 token，但核心工具不能因 query 不匹配被挤出；稳定层常驻 + 排序在前是两者的平衡（#86 修复过稳定层未接线的 bug）。
- **质量软降级而非硬删除**：工具表现差就退出候选，但稳定层豁免——避免"某个时刻某工具临时降分导致核心能力缺失"。
- **BM25 粗筛 → embedding 重排**：BM25 快但粗糙，embedding 准但慢；两级流水在延迟预算内兼顾精度（`latency_budget_ms` 默认 50ms）。
- **三要素权限**：capability（能干什么）+ risk（多危险）+ origin（哪来的），比单一 dangerous flag 表达力强；MCP 工具默认 high + 审批，本地配置才降权。
