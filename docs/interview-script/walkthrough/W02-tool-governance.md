# W02 · 动态工具编排（Tool Governance）

**对应简历 bullet 2**：*"实现动态工具编排：BM25+Embedding 两阶段检索按任务 Top-K 注入工具 schema，稳定核心工具层保 LLM Prefix Cache 命中，工具语义去重 + 质量评分驱动软降级"*

## 代码入口

```
agent/tools/governance/
├── selector.py    ← ToolSelector（BM25 → embedding 两阶段检索）
├── dedup.py       ← SemanticDeduper（描述语义去重）
├── lifecycle.py   ← ToolLifecycle（4 态生命周期）
└── quality.py     ← ToolQualityStore（质量评分 + 软降级）

接线处：
- agent/tools/factory.py:113 _wire_governance()  ← 配置启用时挂上 selector/deduper/lifecycle/quality
- agent/tools/registry.py:95 select_schemas()     ← 注入点入口
- agent/loop.py:986 _select_tool_schemas()        ← 主循环每轮调用
```

## 核心逻辑

### 两阶段检索（selector.py:66-108）

```
query（最近 user 消息 + 最近 3 个工具名）
  ├─ Stage 1: BM25 粗筛（coarse_k=50）标准参数 k=1.5, b=0.75
  ├─ Stage 2: Embedding 精排 → cosine → top_k=5
  └─ 输出 = 稳定层（恒在前，不占 top_k 预算） + 变层 top_k
```

关键细节：
- **稳定层不占 Top-K 预算**（selector.py:107）：核心工具 `CORE_STABLE_TOOL_NAMES`（loop.py:85-87：Read/Edit/Write/Bash/Glob/Grep/InspectGitDiff 7 个）永远注入且排最前，schema 字节稳定 → 保 Prefix Cache 命中。
- **默认 embedding 零依赖**：`NGramEmbedding`（embedding/provider.py:42，字符 n-gram 哈希 2048 维），通过 `EmbeddingProvider` Protocol 可换真 embedding。
- **延迟预算**（selector.py:31）：`latency_budget_ms=50`，超时只记录不 block 主循环。
- **无 selector 降级**（loop.py:999-1001）：回退 `get_all_schemas()`（全量 + mode 过滤）。

### 语义去重（dedup.py）

- 注册时把每个工具 description 嵌入，两两 cosine。
- **超过阈值（0.7）标记 `duplicate_of` 第一个主工具**（先注册为主）。
- **软提示非硬约束**（docstring 明确）：不注入官方 schema，模型自己决定；只在真正被选中时注入差异说明。
- 阈值校准：n-gram embedding 下语义等价≈0.86、完全不相关≈0.11，所以 n-gram 默认 0.7；真 embedding 用 0.9。

### 质量评分 + 软降级（quality.py）

- 滑动窗口 50 次调用，三维加权：成功率 0.5 + 耗时因子 0.3 + 审批通过率 0.2。
- **审批被拒调用**（executed=False）只计入审批信号，不计入成功率/耗时（quality.py:60-63）。
- **低于 degrade_threshold=0.4 → 软降级**（registry.py:114）：离开变层候选，但仍可见、仍可调用——权限模型不动。
- 数据可选持久化 JSON，run 结束 flush。

### 生命周期（lifecycle.py）

4 态：`low_traffic → deprecation → grace → removed`。显式驱动，不依赖质量分。7 天宽限期，grace 期内可见但带提示。

## 简历核实

| 简历 | 核实 | 结论 |
|------|------|------|
| "BM25+Embedding 两阶段检索 Top-K 注入" | selector.py 完全吻合 | ✅ |
| "稳定核心工具层保 Prefix Cache" | CORE_STABLE_TOOL_NAMES + set_stable_tools + cache_plan | ✅ |
| "工具语义去重 + 质量评分驱动软降级" | dedup.py + quality.py 吻合 | ✅ |

## 面试加分点

1. **"软降级不动权限模型"**——体现工程严谨。
2. **"语义去重是软提示"**——不是硬删工具，模型自己决定，体现对 LLM 行为模型的正确理解。
