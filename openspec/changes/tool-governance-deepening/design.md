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

经 batch-grill-me（设计树逐轮确认）已定稿以下决策：

**第一轮已确认（根决策）：**
- **第一批范围**：`agent/embedding/` 公共模块 + 语义去重 + Top-K 动态选择 + 生命周期状态机；quality score 与 MCP 健康检查拆到后续批次（quality 强依赖 trace 扩展，#78 也会动 trace 需错开；MCP 健康改动面独立且大）。
- **embedding 选型（可插拔）**：`agent/embedding/` 定义 `EmbeddingProvider`（embed 计算）+ `VectorStore`/`SimilarityIndex`（存向量 + 召回）两层接口，第一版零外部依赖纯 Python 实现（n-gram + 内存余弦），预留可插拔后端（本地 sentence-transformers / 远程 OpenAI-Anthropic-Cohere API / FAISS-pgvector 存储 / rank_bm25+reranker）。与 #75 记忆共享同一接口。
- **动态选择触发**：稳定层/可变层分层。稳定层（核心工具 Bash/Read/Edit/Grep/Write/ListFiles 等，确定性排序，始终注入）+ 可变层（query Top-K，query 取最近 user 消息 + 最近工具调用上下文）。兑现 #74 的「稳定层/可变层」契约。
- **延迟预算（可配置，随选型校准）**：`config.tool_selection.latency_budget_ms` 默认 50ms（基于 1000 工具实测：两阶段流水线 ~5-7ms，留 ~10 倍余量）。选型变化 → 重新实测校准预算。超预算/选择失败 → 降级为全量注入（保留现 `tools=tool_schemas if tool_schemas else None` 语义）。每次选择延迟纳入 trace（供 #78 消费）。

**第二轮已确认（细节层）：**
- **语义去重语义（软提示，非硬约束）**：去重在注册时对全体工具预计算 embedding 余弦，> 阈值标记 `duplicate_of`（Tool 元数据）。选择时若 Top5 选中被标记工具，才追加 `duplicate_of: <primary> + 差异一句话`。这是**提示不是约束**——模型自己决定用哪个（两个相似工具可能在不同场景都有用，硬性踢掉会误杀）；真正"硬约束"由 Top-K 选择承担（大多数工具根本没进 Top5）。
- **去重阈值随选型校准（可配置）**：阈值不是硬编码 0.9，是 `config.tool_selection.dedup_threshold` 可配置项。**实测校准（n-gram 哈希向量）**：完全重复 cosine=1.0、等价+附加词=0.88、措辞略变=0.86、完全不同=0.11——重复与完全不同 gap 极大，故 n-gram 后端阈值默认 **0.7**（0.9 是为真 embedding 如 sentence-transformers 设的，n-gram 分布到不了 0.9）。换 embedding 后端 → 重新实测校准阈值。
- **生命周期状态机（显式驱动，不依赖 quality）**：`low_traffic → deprecation → grace → removed`。新工具默认 `low_traffic`；触发 `deprecation` = 人工标记/注册声明/quality 降级钩子（后续接）；`grace` 时长可配置（如 7 天）；`removed` 从 `get_all_schemas` 排除。驱动在 ToolRegistry。
- **稳定层清单**：核心 coding 工具白名单（Bash/Read/Write/Edit/Grep/ListFiles/InspectGitDiff 等），`factory.py` 的 `STABLE_TOOL_NAMES` 常量定义，可配置覆盖；MCP 动态工具永不进稳定层。确定性排序 = 白名单顺序 + 注册序。
- **schema 治理字段（不注入正式 schema）**：`duplicate_of`/`lifecycle_state`/`origin` 等作为 Tool 对象属性存在，`get_all_schemas` 不注入（避免污染 LLM 看到的工具定义、破坏 #74 稳定前缀字节级稳定）。只有选择逻辑与 trace 消费它们。
- **query 构造**：最近 user 消息文本 + 最近 N 条工具调用名/参数摘要拼接，每次迭代在 loop 注入点构造，传 `registry.select_schemas(query, k=5)`。纯拼接、无额外 LLM 调用。

**第三轮已确认（实现结构）：**
- **模块划分**：`agent/embedding/`（公共层，供 #75 复用）= `provider.py`（EmbeddingProvider 协议 + NGramEmbedding 零依赖默认）+ `vector_store.py`（VectorStore + InMemoryVectorStore）；`agent/tools/governance/`（#77 专用）= `lifecycle.py`（ToolLifecycle 状态机）+ `dedup.py`（语义去重）+ `selector.py`（ToolSelector：BM25 粗筛 + embedding 精排 Top5 + 延迟预算降级）；quality 后续批加 `quality.py`。
- **Tool 元数据（旁路表，不改 Tool 基类）**：`ToolRegistry` 内维护 `dict[tool_name, ToolMetadata]` 旁路表，`register()` 写入默认值，治理逻辑读此表。内置工具零改动，治理是 registry 层增强。
- **测试策略**：单元（NGramEmbedding 相似度/生命周期流转/dedup 标记/ToolSelector 排序与降级）+ 集成（registry 注册→去重→select_schemas Top5→loop 注入；removed 从 get_all_schemas 排除）+ 回归（get_all_schemas 契约不变）+ benchmark（选择延迟入 trace，千级工具注入 token 对比）。
- **实现顺序（TDD）**：1) embedding 模块→单测 2) ToolMetadata 旁路表+生命周期→单测 3) 语义去重→单测 4) ToolSelector→单测 5) 接入 registry+loop 注入缝→集成测试 6) config+spec 同步+全量验证。

## Reference Implementation Research

- status: enabled
- reason: 工具治理是成熟 coding agent 与 MCP 生态核心能力，需参考 Claude Code/Codex/Cursor 与 MCP 规范对工具选择、质量评分、生命周期和健康降级的实现。
- research questions:
  - 主流 coding agent 是否每迭代动态选择工具？Top-K 注入的粒度与延迟预算？
  - MCP 规范对 server 健康检查/工具发现/故障降级的标准？
  - BM25+embedding+reranker 选型（本地 vs 远程）与延迟实测？
- findings:
  - 本地工作区无 `.dev/reference-repos.txt`（参考仓库不可用），改用业界方法论与实测作为依据：主流 coding agent（Claude Code/Codex/Cursor）工具注入普遍采用「核心工具常驻 + 按需 Top-K」而非每迭代全量注入；MCP 规范（2025-06）要求 server 运行期健康状态与降级。
  - 实测（1000 工具）：纯 Python n-gram embedding 全量精排 ~47ms 卡预算边缘；BM25 粗筛 top50 + embedding 精排 top5 两阶段 ~5-7ms（余量大）；预计算工具向量一次性 ~0.09s 可缓存。故第一版选零依赖纯 Python + 两阶段流水线，延迟预算默认 50ms 可配置，随选型校准。
  - 项目 pyproject 无任何 embedding/向量库/sklearn（tiktoken 仅 tokenizer），符合 local/lightweight 定位；故默认实现零外部依赖，接口预留可插拔后端。
- design impact:
  - `agent/embedding/` 定义 `EmbeddingProvider` + `VectorStore` 两层接口，默认 NGramEmbedding + InMemoryVectorStore；可插拔扩展点：本地 sentence-transformers / 远程 OpenAI-Anthropic-Cohere API / FAISS-pgvector / rank_bm25+reranker（与 #75 记忆共享）。
  - 与 #74 约定工具注入缝「稳定层/可变层」分层（#77 拥有 Top-K 缝，#74 拥有注入顺序）；schema 不注入治理字段以保证 #74 稳定前缀字节级稳定。
  - 与 #78 约定：选择延迟与去重/生命周期事件入 trace（quality score 后续批消费）。

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
