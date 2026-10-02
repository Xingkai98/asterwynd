# Design: Read 工具默认输出上界

## Context

`Read`（`agent/tools/builtin/read.py`）已内置分页（`limit`/`offset` + `[ReadProgress]`，`read.py:93-101`），**但无参数时 `return content` 全文**（`read.py:105`）——这是 #278 实测「单条工具结果 20.7 万字节」的源头。本 change 给默认输出加上界。

### 已实测的机制事实（本设计的地基）

1. **`Read.execute` 三条路径**（`read.py:78-105`）：① 图片（`.png`/`.jpg`... → `_read_image`，返回 `ContentBlock`）；② **`offset` 存在 → 分页切片 + `[ReadProgress]`**；③ **无 `offset` → `if limit: 截前 limit 行`，否则 `return content` 全文**（问题所在）。
2. **`ReadProgress` 格式已定**：`[ReadProgress file="<path>"; offset=<n>; total=<m>]`（`read.py:100`）。
3. **`agent/` 文件规模**（实测）：145 个 `.py`，中位 **107 行**、90 分位 **540 行**、最大 **3196 行**——**绝大多数文件很小**，本 change 只影响少数超大文件。
4. **spec 归属**：`context-engineering` 的「Pagination Progress Preservation」已要求「大文件分页 + 进度」。本 change 让**默认行为**符合该意图。
5. **业界先例**：`opencode` 的工具输出「按**行数或字节**取先到者截断 + marker + `truncated: true`」，并明说「token 压力属于上下文组装与压缩，不属工具」——与本 change「工具层加界、累积留给上层」的分工一致。

## Goals / Non-Goals

### Goals

- `Read` 对超大文件的**默认**输出有界，使巨型单条工具结果**从源头不产生**。
- **绝大多数小文件零影响**（≤ 上界 → 逐字节返回全文）。
- 模型**知道**还有未读内容且能续读（进度注记）。

### Non-Goals

- 不治**累积**（读很多小文件跨轮堆叠）——属 A（`agent-context-bound`）。
- 不改图片路径、不改 `Bash`/`Grep` 等其他工具输出。
- 不做 spill/ref、不新增 ref 存储。

## Decisions

### D1 — 默认上界：**行数**为主，`≤ 上界则全文返回**

无 `limit`/`offset` 时，`Read` 默认返回**首个 N 行**（N = 默认上界常量，缺省 **2000 行**）：
- `total ≤ N` → **逐字节返回全文**（现状不变，覆盖实测中位 107 / 90 分位 540 的绝大多数文件）；
- `total > N` → 返回首 N 行 + `[ReadProgress file=...; offset=0; total=M]`。

**取值依据**：`opencode` 用「行数或字节取先到者」；本 change 先用**行数**（与既有 `limit` 语义一致，最小改动）。2000 行 ≈ 覆盖 `agent/` 90 分位文件（540 行）的 3.7 倍——**只有真正的大文件（如 3196 行的 scheduler.py）会被截**。字节维度是否同时加，见 Open Questions。

> **待 grill 确认**：默认上界取值（2000？）；是否同时约束字节（opencode 是「行数 **或** 字节」）；上界是否可配置。

### D2 — 超界时的注记与续读：**复用既有 `[ReadProgress]` 格式**

**不加新标记**——直接复用 `offset` 路径已用的 `[ReadProgress file=...; offset=0; total=M]`。模型读到 `total > 返回行数` 即知可续读（传 `offset=N`）。**与既有分页语义、与 `context-engineering` 的 Pagination Progress Preservation 完全一致**。

> **待 grill 确认**：`offset=0` 语义（表示「读了开头」）是否清晰？是否要额外一句可行动提示（如「传 offset=2000 续读」）？

### D3 — 小文件逐字节不变（回归红线）

`total ≤ N` 时 `return content`（**逐字节等于现状**）。这是**防回归红线**：绝大多数文件（实测中位 107 行）走这条路径，行为必须与改动前**完全一致**——否则会波及大量依赖 `Read` 的测试与真实使用。

### D4 — 图片路径不变

`.png`/`.jpg`/... → `_read_image`（返回 `ContentBlock`）分支**不动**。图片的驻留问题（base64 单张可达 MB 级、绕过 token 计量）是 #280 对抗验证列出的**独立问题**，不在本 change（见 Non-Goals）。

### D5 — 显式 `limit`/`offset` 行为不变

模型显式传参时，完全走既有逻辑。本 change **只改「无参数」这一支**的默认。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **大文件被截，模型第一次读不到全部** | 进度注记让它知道并可续读；上界 2000 行对实测 90 分位（540 行）无影响。 |
| **有些文件本就需要一次全文**（如小配置） | ≤ 2000 行不截——绝大多数文件走全文路径。 |
| **模型可能忽略进度注记** | 注记沿用既有格式（`offset` 路径已在用，模型已见过）；R2 验收「返回体含 `[ReadProgress]` 且 `total > 上界`」。 |
| **本 change 治不了累积 → E0 峰值可能降得不够** | **这是预期的**——E0 只作对照、不设门槛；降得不够正是「A 必须做」的数据。 |
| **默认上界太小伤大文件任务** | 取值 2000 行（覆盖 90 分位 3.7×）；可配置；grill 可调。 |

## Testing Strategy

- **新增** `tests/agent/tools/test_read_output_bound.py`（或并入既有 read 测试）：
  - **超上界文件** → 返回首个 N 行 + `[ReadProgress]`（`total` 正确 = 文件总行数）；
  - **≤ 上界文件** → **逐字节等于全文**（回归红线 D3）；
  - **显式 `limit`/`offset`** → 行为与改动前一致；
  - **图片路径** → 不变（返回 `ContentBlock`）；
  - **边界**：恰好 N 行、N+1 行。
- **回归**：`tests/agent/tools/` 全部；既有分页测试。
- **端到端（对照）**：#278 复现器缩比版，如实记录 RSS 峰值对比基线（**不设门槛**）。

## Pre-Implementation Review

grill 阶段填写（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）。**按新增流程纪律：grill 结论须先走独立对抗验证（`grill-adversarial.md`）再拍板。**

## Impact Analysis（design 视角的补充）

见 `proposal.md` 的 `## Impact Analysis`。补充：

1. **改动面极小**——`read.py` 一个函数的一支分支 + 一个常量（可配置）。
2. **回归红线是 D3**——小文件逐字节不变，是「不波及绝大多数使用」的关键；测试必须显式断言。
3. **与 A 的关系**——E0 的观测结果是「A 是否必须」的判据；A 的文档（含 grill + 对抗验证）保留在 `agent-context-bound` 分支作为输入。
