# Bullet 2: 动态工具编排 — 代码走读

> 简历原文：实现动态工具编排：BM25 粗筛 + 向量精排两阶段按对话上下文 Top-K 注入工具 schema，核心工具稳定层常驻且不占 Top-K 预算、配合 cache_control 断点保 LLM Prefix Cache 命中，工具语义去重 + 质量评分驱动软降级

---

## 整体架构

4 个机制都在 `agent/tools/governance/` 目录，由 `ToolRegistry`（`registry.py`）统一编排。调用入口在 `agent/loop.py:986` `_select_tool_schemas()`，每次迭代前触发。

```
每次迭代前 (_select_tool_schemas):
┌──────────────┐
│ 38 个工具全量  │
└──────┬───────┘
       │ 分离
  ┌────┴────┐
  │ 稳定层 7 │────────────── 始终注入，排最前，不参与任何筛选
  └─────────┘
       │ 其余 ~30
  ┌────┴────┐
  │ 质量过滤  │────────── 低分工具从变层候选剔除（软降级）
  └────┬────┘
       │
  ┌────┴────┐
  │ BM25粗筛 │────────── 取 top 50（当前 ~30 工具，实际未筛选，仅排序）
  └────┬────┘
       │
  ┌────┴────┐
  │向量精排  │────────── cosine → top 5
  └────┬────┘
       │
  稳定层(7) + 变层(5) = 最终注入 LLM 的 ~12 个 tool schema
       │
  ┌────┴────┐
  │cache断点 │────────── 打在最后一个稳定工具上（Anthropic 专属）
  └─────────┘
```

**重要前提**：整个动态选择 + 质量评分功能**默认关闭**（`config.py:89,104`：`enabled: bool = False`）。开启方式是 `asterwynd.yaml` 中 `tools.selection.enabled: true` 和 `tools.quality.enabled: true`。关闭时走 `get_all_schemas()` 全量注入。

---

## 机制 1: BM25 粗筛 + 向量精排两阶段检索

**文件**：`agent/tools/governance/selector.py`

核心类 `ToolSelector`（line 22）：

```python
class ToolSelector:
    def __init__(self, embedder, top_k=5, coarse_k=50, latency_budget_ms=50.0):
        ...
```

### 调用触发

`agent/loop.py:1004-1024`，每次迭代构造 query：

```python
# query = 最新一条 user 消息 + 最多 3 个最近的工具调用名
query = "用户问题 recently used: Read, Edit, Bash"
return self.tool_registry.select_schemas(query, k=5)
```

### 两阶段流程（`_select_impl`, line 81）

```
Stage 1: BM25 粗筛
  对所有非稳定工具 description 做 BM25 打分（k=1.5, b=0.75）
  → 取 top coarse_k=50

Stage 2: 向量精排
  对 query 做 embedding → 与候选工具向量 cosine 比较
  → 取 top top_k=5
```

**当前局限性**：38 工具 - 7 稳定层 = ~30 候选，`coarse_k=50` 意味着 BM25 阶段不做筛选，仅排序。这是**前瞻性设计**——为工具数量增长到 100+（大量 MCP 工具接入）预留的。

### Embedding 后端

**文件**：`agent/embedding/provider.py`

默认 `NGramEmbedding`（line 42）：**字符 n-gram MD5 哈希向量**（256 维），零外部依赖。**不是神经网络的语义 embedding**。

通过 `EmbeddingProvider` Protocol（line 26）可插拔换成 sentence-transformers 等真实模型，不需要改任何 governance 代码：

```python
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> Vector: ...
    def cosine(self, a: Vector, b: Vector) -> float: ...
```

---

## 机制 2: 核心工具稳定层 + Prefix Cache

### 稳定工具集

**文件**：`agent/loop.py:85-87`

```python
CORE_STABLE_TOOL_NAMES = (
    "Read", "Edit", "Write", "Bash", "Glob", "Grep", "InspectGitDiff",
)
```

这 7 个工具被视为"任何 coding 任务都需要的核心工具"，schema 字节级确定。

### 在 ToolSelector 中的行为

`selector.py:86, :104-108`：

```python
# ① 稳定层永远排最前，按注册顺序固定
stable_names = [n for n in self._names if n in self._stable]

# ② 不参与 BM25 排序（从候选池排除）
# ③ 变层 Top-K 追加在稳定层后，不占 top_k 配额
tail = [name for name, _ in ranked[: self._top_k]]
return stable_names + tail
```

不管什么任务，Read/Edit/Write/Bash/Glob/Grep/InspectGitDiff 永远在工具列表最前面且位置不变。

### cache_control 断点

**文件**：`agent/loop.py:1103-1148` + `agent/anthropic_llm.py:167-194`

| Selector 状态 | 断点策略 | 缓存范围 |
|:---|:---|:---|
| **OFF**（默认） | 最后一个 cacheable system block | system + tools 整体缓存 |
| **ON** | **最后一个核心稳定工具** | system + 稳定工具前缀缓存，变层不缓存 |

```python
# loop.py:1133-1148
selector = getattr(self.tool_registry, "_selector", None)
if selector is None:
    return CachePlan(stable_system_block_count=N, stable_tool_count=0)
else:
    # selector ON：稳定工具是连续前缀 → 在最后一个稳定工具上打断点
    stable_tool_count = 0
    for tool in tools:
        if tool.name in stable_names:
            stable_tool_count += 1
        else:
            break  # 遇到第一个非稳定工具立即停止
    return CachePlan(stable_system_block_count=0, stable_tool_count=stable_tool_count)
```

**重要**：`cache_control` 断点**仅 Anthropic 路径生效**（`loop.py:1095`）：

```python
if not getattr(self.llm, "supports_cache_control", False):
    return  # OpenAI 服务端 auto-caching，不需要手动打断点
```

Anthropic 的 `_apply_cache_plan`（`:167-194`）把 `cache_control: {"type": "ephemeral"}` 打到对应 block，一轮对话中稳定前缀不变时，KV cache 不重复计算。

---

## 机制 3: 工具语义去重

**文件**：`agent/tools/governance/dedup.py`

核心类 `SemanticDeduper`（line 20）：

```python
class SemanticDeduper:
    def add(self, tool_name, description):
        vector = self._embedder.embed(description)
        for other in self._descriptions:
            sim = self._embedder.cosine(vector, self._vectors[other])
            if sim > self._threshold:  # 默认 0.7
                self._duplicate_of[tool_name] = other  # 标记为重复
                break
```

注册期触发（`registry.py:81-83`）：每个新工具注册时与已注册工具两两 cosine 比较，超过阈值 → 标记 `duplicate_of`。

**这是软标记，不是硬约束**：被标记的工具依然可以注册、调用、出现在 schema 中。标记存为旁路元数据，不注入官方 tool schema。

**注意**：`difference_explanation()`（line 48-61，给模型注入差异说明的软提示）目前**没有任何运行时路径调用**。去重检测是真实做的，但"给模型看差异说明"这条没接线。

---

## 机制 4: 质量评分驱动软降级

**文件**：`agent/tools/governance/quality.py`

核心类 `ToolQualityStore`（line 18）：

### 评分公式

```python
score = 0.5 × success_rate + 0.3 × duration_factor + 0.2 × approval_rate

# duration_factor = 1.0 - avg_duration / 30000  （越快分越高）
# approval_rate：无审批信号时权重重归一为 0.5×成功 + 0.3×耗时
```

滑动窗口 50 个调用，最少 5 个样本才产出评分。

### 降级行为

`registry.py:114`：

```python
if self._is_quality_degraded(name) and not self._selector.is_stable(name):
    continue  # 从变层候选排除
```

- 阈值 < 0.4 → 软降级
- 稳定层工具**不受降级影响**
- 权限模型**不动**（`get_all_schemas()` 仍可见，模型仍可手动调用）
- 不是禁用，是软移除变层候选

### 公式的已知问题

经代码走读 + 业界调研发现三个问题（已提 issue #120）：

| 问题 | 说明 |
|------|------|
| `duration_factor` 不应作为质量信号 | "快=好"不成立（`git clone` 比 `ls` 慢不代表质量差）。业界无人用耗时做质量评分 |
| `approval_rate` 是策略偏好，不应混入质量 | 审批率高只说明人允许用了。审批是安全控制面，应是独立信号 |
| 缺少核心信号 | 业界标准：Tool Selection Accuracy（选对工具了吗）、Invalid Tool Rate（幻觉出新工具）、Error Type Classification（区分错误类型） |

**不影响简历表述**——"质量评分驱动软降级"属实，公式最优性是后续优化方向。

---

## 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/tools/governance/selector.py` | ToolSelector：BM25 + embedding 两阶段选择 |
| `agent/tools/governance/dedup.py` | SemanticDeduper：注册期语义去重 |
| `agent/tools/governance/quality.py` | ToolQualityStore：滑动窗口质量评分 + 软降级 |
| `agent/tools/registry.py` | ToolRegistry：统一编排 governance 组件 |
| `agent/embedding/provider.py` | EmbeddingProvider Protocol + NGramEmbedding 默认实现 |
| `agent/config.py` | ToolSelectionConfig / QualityConfig（默认关闭） |
| `agent/loop.py:85-87` | CORE_STABLE_TOOL_NAMES |
| `agent/loop.py:986-1024` | _select_tool_schemas() 注入点 |
| `agent/loop.py:1084-1148` | _apply_cache_plan / _compute_cache_plan |
| `agent/anthropic_llm.py:167-194` | AnthropicLLM._apply_cache_plan 实际打断点 |
