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

### D1 — 默认上界：**行数为主 + 字节兼底**，`≤ 界则全文返回`

**无显式 `limit` 时**（含无参数、`limit=None`、以及 `offset` 无 `limit` 续读三条路径），`Read` 默认返回**首个 N 行**（N = 默认上界常量，缺省 **2000 行**）：
- **行数 ≤ N 且 字节 ≤ B** → **返回全文**（与当前无界输出逐字节相同；覆盖实测中位 107 / 90 分位 540 的绝大多数文件）；
- **行数 > N** → 返回首 N 行 + 显式进度注记（见 D2）；
- **行数 ≤ N 但字节 > B**（少行超长行，如 minified/大 JSON）→ 也截断 + 注记。

**可配置（Q4 拍板）**：N / B **有内建默认**（模块常量 `DEFAULT_MAX_READ_LINES` / `DEFAULT_MAX_READ_BYTES`），且 **SHALL 可经 config 覆盖**（`tools.read.max_lines` / `tools.read.max_bytes`，仿 `tools.display`）；`ReadTool` 收 `max_lines`/`max_bytes` 构造参数，默认取常量；factory 从 config 取值接线（`main.py` / `subagent/manager.py` / `web/session.py` / `benchmarks/agent_runner.py`）。

**取值依据（经 grill + 对抗验证）**：
- **N = 2000 行**：两个独立参考实现（`pi` `truncate.ts:11`、`opencode` tool-output-store）的**共同默认**，保留；
- **B = 128KB**：**不用 50KB**——实测会误截 5 个核心文件（`config.py` 71K / `manager.py` 72K / `loop.py` 71K / `main.py` 58K / `command_guard.py` 53K，行数都 ≤2000、本该全文读）。128KB 远高于任何核心文件（最大 72KB），**只兜「少行超长行」**（如 1 行 4MB）。

### D2 — 超界时的注记与续读：**显式**（不静默）

注记 SHALL **显式**说明「已截断」并**给出 next offset**（符合 #248/#275「截断必须显式可见」纪律），形如 `[ReadProgress file=...; offset=0; total=M; truncated=true]` + 可行动提示（`continue with offset=N`）。

**`truncated=true` 的坐实依据**：`_READ_PROGRESS_RE`（`memory/manager.py:21`）右端锚定 `total=(\d+)\]`——**在其后加字段会静默失配**（返回 `None`、不报错），导致 summary 续读提示无声消失。因此**改注记格式 SHALL 同步改该正则**（双模块契约），并补**跨模块测试**。

### D3 — 小文件与「逐字节」口径修正（回归红线）

`行数 ≤ N 且 字节 ≤ B` 时返回全文。**口径修正（经对抗验证）**：spec/design 早先写「逐字节等于**文件**」**字面为假**——`Read` 走 `p.read_text(errors="replace")`（`read.py:88`）+ 换行归一化，**今天就已把 CRLF→LF、非 UTF-8→替换字符**（对所有文件、包括全文路径）。故红线改述为「**与当前无界输出逐字节相同**」（回归-vs-现状），而非「与文件相同」。

### D4 — 图片路径不变

`.png`/`.jpg`/... → `_read_image`（返回 `ContentBlock`）分支**不动**。图片的驻留问题（base64 单张可达 MB 级、绕过 token 计量）是 #280 对抗验证列出的**独立问题**，不在本 change（见 Non-Goals）。

### D5 — 逃逸面封堵（`limit=0`、`offset` 无 limit）

**经对抗验证发现的两个绕过口子，本 change 一并堵**：
- **`limit=0`**：`if limit:` 对 0 为假 → `Read(path, limit=0)` **返回全文**（实测 43889 字节），`Read(offset=0, limit=0)` 读到 EOF。修法：用 **`limit is not None`** 语义（0 也当显式值处理，按 0 行 + 注记，绝不落全文）；
- **`offset` 无 `limit`**：`read.py:98` `end = (start+limit) if limit else None` → `Read(path, offset=2000)` 无 limit **读到 EOF**（实测 146 万字节）。修法：`offset` 路径在无显式 `limit` 时**也施加默认界**（+ 注记给 next offset）。

### D6 — 续读进度不被默认读覆盖（修既有 bug）

`memory/manager.py` 的 `_extract_read_progress` 是**每文件 last-wins**：默认读发出的 `offset=0` 注记会**覆盖**模型先前显式分页到的真实 offset（实测：先 `offset=2000` 后 `offset=0` → hint 回退为 `0`，summary 建议「从头续读」）。

修法（**已定稿，经 grill Q5 + 对抗 M3 拍板**）：给注记一个**显式标记字段** `truncated=true`（默认截断的注记带、真实分页注记不带），manager 侧按 **`truncated && offset==0`** 跳过——即「默认截断的 `offset=0`」不算续读位点，而 `offset≠0` 的 truncated 注记来自显式 `offset` 分页、是真续读位点，仍计入。**不得**让默认截断的 `offset=0` 覆盖真实的续读进度（否则直接违反 `context-engineering` 的 Pagination Progress Preservation 意图）。

> **实现落点**：`read.py` 的 `_truncated_note`（发 `truncated=true`）↔ `manager.py` 的 `_extract_read_progress`（`if match.group("truncated") and int(match.group(2)) == 0: continue`）。

### D7 — `total` 语义钉死

注记中的 `total` **恒为文件总行数**，与 `offset` 无关（不是剩余行数）——spec/design 显式钉死，避免改造中被误解。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **大文件被截，模型第一次读不到全部** | 注记**显式**说明截断 + 给 next offset（D2）；上界 2000 行对实测 90 分位（540 行）无影响。 |
| **尾部内容丢失**（head-only 截断固有代价——文件尾常是关键如 `if __name__`/导出注册表） | next offset 指引让模型能续读到尾；若实测证明不够，考虑 head+tail 采样（本轮不做，记 debt）。 |
| **字节界误截核心文件** | 已避开：B=128KB 远高于最大核心文件 72KB（50KB 方案已否决）。 |
| **注记格式改动打断 summary 续读** | 双模块契约：改 `read.py` 必须同步 `_READ_PROGRESS_RE` + 跨模块测试（D2）。 |
| **默认读覆盖真实续读进度**（既有 bug） | D6 修：`offset=0` 默认截断不覆盖显式分页进度。 |
| **模型可能忽略进度注记** | 注记**显式**（不再是隐式「返回行数 < total」）；R2 验收断言注记含 `truncated` 与 next offset。 |
| **本 change 治不了累积 → E0 峰值可能降得不够** | **这是预期的**——E0 只作对照、不设门槛；降得不够正是「A 必须做」的数据。补确定性字节界单测做 CI 回归。 |
| **`limit` 是正 `None`/`0` 的语义混淆** | D5 用 `limit is not None` 显式区分；`limit=0` 单测锁定。 |

## Testing Strategy

- **新增** `tests/agent/tools/test_read_output_bound.py`（或并入既有 read 测试）：
  - **超行上界文件** → 返回首个 N 行 + 显式截断注记（`total` = 文件总行数，`truncated=true`）；
  - **少行超长行**（1 行 4MB）→ 被字节界截（D1 的 B）；
  - **`limit=0`** → **不返回全文**（D5 逃逸面）；
  - **`offset` 无 `limit`** → 有界（不到 EOF）（D5 逃逸面）；
  - **≤ 界的文件** → **与当前无界输出逐字节相同**（回归红线 D3，口径修正）；
  - **显式正 `limit`** → 与改动前一致；
  - **图片路径** → 不变（返回 `ContentBlock`）；
  - **边界**：恰 N 行、N+1 行、恰 B 字节、B+1 字节。
- **新增（跨模块契约）**：注记格式改动后 `_READ_PROGRESS_RE` 仍能解析（`truncated=true` 不被右锚定吃掉）——`read.py` 与 `memory/manager.py` 双模块测试。
- **新增**：D6——默认读的 `offset=0` 注记**不覆盖**真实的显式分页进度（last-wins 不回退）。
- **回归**：`tests/agent/tools/` 全部；`tests/agent/tools/test_read_doc_and_pagination.py`（注意 `test_offset_without_limit_reads_to_eof` 与新界语义的关系——经核实该测试用 50 行小文件，仍通过）。
- **端到端（对照）**：#278 复现器缩比版，如实记录 RSS 峰值对比基线（**不设门槛**）；补一条**确定性字节界单测**做 CI 回归（E0 本身无法进 CI）。

## Pre-Implementation Review

grill 阶段填写（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）。**按新增流程纪律：grill 结论须先走独立对抗验证（`grill-adversarial.md`）再拍板。**

## Impact Analysis（design 视角的补充）

见 `proposal.md` 的 `## Impact Analysis`。补充：

1. **改动面**——`read.py`（默认界 + 显式注记 + `ReadTool` 上界构造参数）、`memory/manager.py`（正则容忍 + D6 跳过，双模块契约）、`config.py`（`tools.read.{max_lines,max_bytes}` + 全调用链接线）；回滚 = revert。
2. **回归红线是 D3**——小文件逐字节不变，是「不波及绝大多数使用」的关键；测试必须显式断言。
3. **与 A 的关系**——E0 的观测结果是「A 是否必须」的判据；A 的文档（含 grill + 对抗验证）保留在 `agent-context-bound` 分支作为输入。
