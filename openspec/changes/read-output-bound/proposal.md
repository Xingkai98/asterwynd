# Proposal: Read 工具默认输出上界 — 从源头削掉巨型工具结果

关联跟踪 issue：[#280](https://github.com/Xingkai98/asterwynd/issues/280)（其**第一步**，B）。诊断来源：[#278](https://github.com/Xingkai98/asterwynd/issues/278)（已关闭）。

## Change Type

- primary: feature
- secondary:
  - tool-surface
  - context

## Why

### 问题：Read 默认返回全文，是巨型工具结果的**源头**

#278 实测复现了 4GB cgroup OOM，根因是 agent 常驻上下文无上界；**上下文解剖**（决定性证据）显示常驻字节 **95%+ 是工具结果**，其中**单条最大 20.7 万字节**——来自 `Read` 读一个大文件。

`Read` 工具（`agent/tools/builtin/read.py`）**已内置分页**（`limit`/`offset` + `[ReadProgress]` 进度注记，`read.py:93-101`），**但无参数时默认 `return content` 全文**（`read.py:105`）。模型不显式传 `limit`/`offset` 时，一个 3000 行的文件**整个塞进上下文**——单条就吃掉 `max_tokens=80_000` 的 ~62%。

本 change 是 #280 对抗验证给出的**正确第一步**：「先治源头，再谈剪枝」——巨型单条**从源头就不产生**，「新鲜（当轮要用）vs 巨型」的死结消失大半（不需要「巨型新鲜结果也立即剪」那种会伤害任务完成的药方）。

### 本 change 的作用边界（**如实记录，避免误判**）

**B 只削「单条峰值」，不解决「累积」**——OOM 是跨多轮累积造成的。实测 `agent/` 的 145 个 `.py`：**中位数 107 行、90 分位 540 行、最大 3196 行**——**绝大多数文件很小，B 对它们无影响**；B 只拦「单次读超大文件」。

⇒ **B 大概率缓解但不会让峰值数量级下降**（#280 对抗验证的 C0 风险）。**B 的价值之一是"用一次实测把「要不要做 A（spill/ref）」从判断变成数据"**：做完测一次——降得不够 → 数据证明 A 必须做；降够了 → A 可缓。**这是本 change 与 A（`agent-context-bound`，已挂起）的关系。**

## What Changes

**`Read` 工具默认输出加界**：

- **无 `limit`/`offset` 时**：默认只返回**首个 N 行**（N = 默认上界，如 2000），并在末尾附 `[ReadProgress file=...; offset=0; total=M]` 进度注记（**复用已有格式**），让模型知道「还有多少未读、如何续读」；
- **文件 ≤ N 行时**：**逐字节返回全文**（现状不变，绝大多数小文件零影响）；
- **显式传 `limit`/`offset` 时**：行为不变（模型可主动分页续读）；
- 默认上界 SHALL 可配置（`config`），并 SHALL 是一个明确的常量。

**不变**：图片路径（`.png`/`.jpg`... → `_read_image`，返回 `ContentBlock`）行为不变；`WorkspacePolicy` 校验、分页语义、`[ReadProgress]` 格式不变。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `context-engineering`：
  - **MODIFIED** 既有 Requirement「Pagination Progress Preservation」——`Read` SHALL 对**超过默认上界**的文件**默认**返回「首个上界行数 + 进度注记」，SHALL NOT 无参数时返回全文；文件未超上界时 SHALL 全文返回；显式 `limit`/`offset` 时行为不变。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

| # | 指标 | 主/辅 |
|---|---|---|
| **R0** | 单次 `Read` 一个超大文件（如 `scheduler.py` 3196 行）返回的**行数与字节数**均受默认上界约束（行 > 2000 或**字节 > 128KB** 时截断） | **主指标** |
| **R0b** | **逃逸面封堵**：`limit=0` 不返回全文；`offset` 无 `limit` 不到 EOF；少行超长行（1 行 4MB）被字节界截 | **主指标** |
| **R1** | ≤ 界的文件**与当前无界输出逐字节相同**（绝大多数文件零回归；口径=与现状比，非与文件比） | **主指标** |
| R2 | 进度注记**显式**说明截断 + 给 next offset（返回体含 `truncated` 与续读指引） | 辅 |
| R3 | 默认读的 `offset=0` 注记**不覆盖**真实的显式分页进度（修既有 bug） | 辅 |
| **E0** | **端到端**：#278 复现任务下 asterwynd RSS 峰值**对比基线**（#278 实测尖峰 **1228MB**）——**不设"必须数量级下降"的硬门槛**；实测**如实记录**，作为「A 是否必须」的判据 | **对照（不设门槛）** |

**通过门槛**：R0 + R0b + R1 成立、R2/R3 可验证。**E0 只作对照观测**（降多少如实记录，不判定成败——判成败的是"要不要做 A"这个后续决定）。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 命中 `light` 判据「常规功能增强；成熟模式的局部应用」。**不判 `full` 的理由**：本 change 是**既有能力**（`Read` 早已支持分页，`read.py:93-101`）的**默认值收紧**，不引入新框架/新依赖/新协议面；「长文件默认分页 + 进度注记」是**业界成熟模式**（见 findings）。不判 `exempt`：确有行为变更（默认输出）、且触及 spec。
- research questions:
  - **RQ1**：业界 coding agent 的「读文件」工具如何处理超大文件——默认分页？截断？还是全给？
- findings:
  1. **成熟模式：默认分页 + 进度注记是业界通行做法。** 本项目 `Read` 已具备该形态（`limit`/`offset` + `[ReadProgress]`），本 change 只是把「默认」从"全文"改为"首屏 + 提示续读"。**项目内先例**：`context-engineering` 的「Pagination Progress Preservation」Requirement 已要求「大文件分页 + 进度在压缩前持久化」——本 change 是让**默认行为**符合该既有意图。
  2. **待 grill 用参考仓库补强**：核对 `codex`/`kimi-code`/`zcode` 等仓库的读文件工具默认行为（`read_file`/`view` 的默认行数上限），作为默认上界取值的依据。
- design impact: 见 design **D1**（默认上界取值）、**D2**（超界时的注记与续读）、**D3**（≤上界逐字节不变）。

## Impact Analysis

- **能力域**: `context-engineering`（Read 的上下文行为）。
- **代码**:
  - `agent/tools/builtin/read.py` — `execute` 无 `limit`/`offset` 分支加默认上界 + 进度注记。**这是本 change 唯一的核心改动点。**
  - `agent/config.py` — 默认上界常量可配置（可选，若 grill 认为需要）。
- **测试**:
  - **必须新增**：超上界文件 → 返回首个上界行 + `[ReadProgress]`（`total` 正确）；**≤ 上界文件 → 逐字节等于全文**（回归防护，确保绝大多数小文件零变化）；显式 `limit`/`offset` 行为不变；图片路径不变。
  - **必须回归**：所有依赖 `Read` 的测试（`tests/agent/tools/`）；既有分页测试。
- **文档**:
  - `openspec/specs/context-engineering/spec.md`（MODIFIED 1；受保护路径）。
  - `docs/openspec-change-backlog.md`（受保护路径）。
  - `README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描。
- **流程（process）**: 触及受保护路径，需结构化事件 + grill + building review；实现须独立 worktree、`read-output-bound/2026-10-02` 分支。**change type = feature → 实现前必须走 `batch-grill-me` + 停轮确认**。
- **与 A（`agent-context-bound`，挂起）的边界**：**B 是 A 的前置探索**。B 只改 `Read` 默认输出（工具面）；A 是 messages spill + ref 存储 + 压缩硬顶（内存管理架构）。**B 做完的实测数据决定 A 是否/如何做。** A 的文档（proposal/design/grill/对抗验证）保留在其分支上作为输入。
- **代价权衡**: 默认上界会让模型对大文件**多发一次分页续读**（round-trip）——但只对**超上界的少数文件**（实测中位 107 行）；绝大多数文件零变化。收益是从源头消除巨型单条。
- **可回滚性**: 改动集中在一个函数的一支分支；回滚 = revert。

## Non-Goals（摘要）

- **不治累积**（读很多小文件跨轮累积）——那需要 A（spill/ref），本 change 不碰。
- **不改图片路径**（`_read_image` / `ContentBlock` 返回）——图片的驻留问题另议（#280 对抗验证已列）。
- **不改 `Bash`/`Grep` 等其他工具的输出**——本 change 只动 `Read`。
- **不做 spill/ref、不新增 ref 存储**（属 A）。
