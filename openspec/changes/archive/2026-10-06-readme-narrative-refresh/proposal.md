# Proposal: README 叙事重做（readme-narrative-refresh）

关联跟踪 issue：[#296](https://github.com/Xingkai98/asterwynd/issues/296)（【docs】README 叙事重做）。

## Change Type

- primary: docs
- secondary: []

## Why

`README.md` / `README_EN.md` 已落后于项目现状，且**没有叙事**：

- **头牌能力缺席**：项目最独特的能力——声明式动态 Workflow 编排——在 README 里几乎完全不可见。`agent/workflow/` 在项目结构里只写「Handoff 状态机」，而实际已是整套编排系统：`DeclareWorkflow`/`StartWorkflow`/`RunWorkflow`、4 种节点（`subagent`/`aggregate`/`route`/`foreach`）、树状分层汇聚、四维总预算、四维成本归因、运行态图可视化、`DryRunWorkflow` 零成本试错、可回放编排记录。README 只有一句「编排 benchmark 三模式」。
- **功能表是「模块字典」不是「卖点」**：15 行平铺表格，看不出哪几个是亮点、每个难在哪。
- **没有自举工程叙事**：完全没有体现「用 Agent 开发 Agent」这条闭环（OpenSpec 需求先行 → grill 设计追问 → 独立对抗验证 → review-loop → CI 门禁 → 归档收尾）。
- **数字口径漂移**：`README.md` 说 34 个本地任务、`README_EN.md` 说 33，实际（master `8a255b0`）为 34 个本地 + 38 个 SWE-bench Verified = 72；内置工具数、上下文源数、测试数同样过期。
- **零图片**：README 目前没有任何架构图或示意图，仓库里已有的 `docs/assets/asterwynd-architecture.excalidraw` 未被引用，且内容不含编排层。
- **文档地图缺口**：`docs/architecture.md` 未描述多 Agent 编排与 workflow 图可视化。

## What Changes

以 **landing-first** 重排 README（中文 + 英文同步，遵守 AGENTS.md 的 README 同步规则）：

1. **Hero + 徽章 + 电梯 pitch**：一段话说清「是什么 + 跟别的 coding agent 差在哪」。
2. **特色区 6 张卡**（按吸睛度排序），每张含「一句话钩子 + 关键机制 + 为什么难」，**每张配一张 Excalidraw 示意图**：
   - 动态 Workflow 编排 / 上下文工程 / 长期记忆 / 三层纵深防御 / 工具治理 / 可观测 + 评测闭环。
3. **重画一张最新系统架构图**（`.excalidraw` 源 + 导出 `.svg`），覆盖编排层与可观测层。
4. **自举工程闭环 banner**：单列一节讲「用 Agent 开发 Agent」。
5. **快速开始精简**到核心命令；长内容（内置工具表、项目结构、AutoCompact 详解、Sub-Session 示例、扩展指南、Web UI 清单、环境变量表、Benchmark 评测流程 8 步）下沉并用 `<details>` 折叠保信息，不丢内容。
6. **修正 `docs/architecture.md`**：补多 Agent 编排与 workflow 运行态可视化段落。

## 交付物

- `docs/assets/readme/` 新增 7 张图的 `.excalidraw` 源 + 导出 `.svg`（`architecture` / `workflow-orchestration` / `feature-{context,memory,safety,tools,observability}`）。
- `README.md` / `README_EN.md` 重写。
- `docs/architecture.md` 补编排能力描述，并修正既有错误口径（`claw-swe-bench/` 已不在 tree、节点/边档数、聚合触发条件）。
- `docs/development-guide.md`：修正 fake smoke 示例的编辑锚点（旧串 `# Asterwynd` 在任何 README 里都不存在）。

### 独立零记忆 subagent 对抗式事实校对（`reviews/fact-check.md`）

审阅发现并修复 7 处事实错误 + 1 处口径问题（全部经我方逐条代码复核为真）：

| # | 问题 | 修正 |
|---|------|------|
| F2 | CostLedger 四维写作 `by_session`（legacy 三维之一） | 改 `by_workflow`（新四维），并说明 legacy 三维仍保留 |
| F6 | 稳定层工具名单写 `Find`/`ListFiles` | 依 `CORE_STABLE_TOOL_NAMES` 改 `Read/Edit/Write/Bash/Grep/InspectGitDiff` |
| F4/F5 | 图状态「节点七档/边五档」 | 改「节点八档/边六档」（与 `workflow_graph.js` / `architecture.md:135` 对齐） |
| F7 | 日志在 `logs/` | 改「平台用户日志目录（`platformdirs.user_log_path`）」 |
| F9 | 结构树声称 `agent/tui/` 存在 | 删除（目录不存在，spec 明确「尚未实现 TUI」） |
| F10 | `claw-swe-bench/` + `CLAW-SWE-BENCH.md` 4 处引用 | 全部移除（两者均已不在 tree） |
| F1 | 聚合「总叶子数 >10」独立判据 | 删去该半句（实现只按「单 aggregate 上游 >10」触发） |
| F8 | 快速开始 fake smoke 的编辑锚点 | 改 `# Asterwynd` → `Asterwynd`（旧串已不存在；同步 `development-guide.md`） |

**注**：F9/F10/F8 是**旧 README 继承的既有错误**（目录/文件早已从 tree 删除而 README 未更新），本 change 顺手修正；F1 与 `multi-agent-collaboration` spec 第 180 行的措辞一致性另见「边界」。

## 数字口径（以 master `8a255b0` 实测为准）

| 指标 | 值 | 出处 |
|------|-----|------|
| `agent/` 生产代码 | 38,508 行 / 147 个 `.py` | `find agent -name '*.py'` |
| 自动化测试 | 225 个测试文件 / 3,511 个测试函数 | `tests/` |
| 内置工具 | 40 个（含默认关闭的浏览器工具） | `agent/tools/factory.py` `KNOWN_BUILTIN_TOOL_NAMES` |
| 上下文源 | 9 个（含仅根 loop 注入的 workflow asset index） | `agent/loop.py:_build_context_builder` |
| Hook 切面 | 7 个 | `agent/hooks/manager.py` |
| 编排模式 | 4 个（orchestrator-worker / peer-review / hierarchical / bidding） | `agent/subagent/patterns.py` |
| Workflow 节点类型 | 4 个（subagent / aggregate / route / foreach） | `agent/subagent/workflow.py` |
| Benchmark 任务 | 72（34 本地 [22 A 轨 + 11 B 轨 + 1 无 track] + 38 SWE-bench Verified） | `benchmarks/tasks/` |

## Non-Goals

- 不改任何业务代码、CLI 行为或 OpenSpec specs。
- 不删除原有 README 信息——长内容一律**折叠**而非丢弃（被删除的只有 `claw-swe-bench/`/`tui/` 这类**指向已不存在目录**的失效引用）。
- 不引入新截图/GIF（本 change 只做 Excalidraw 图）。

## 边界 / 后续（非本 change）

- **`CORE_STABLE_TOOL_NAMES` 含 `Glob`，但仓内无 `Glob` 工具类**（实际是 `Find`/`ListFiles`）——历史遗留项，README 以常量为准如实描述；是否修常量另议。
- **`benchmarks/tasks/asterwynd-readme-title` fixture 自相矛盾**：`base_commit` README 首行是 `# MyAgent`，而 `gold.patch` 期望 `# Asterwynd` → fake smoke 在该 fixture 上必然 `old_string not found`（既有问题，非本 change 引入）。
- **spec `multi-agent-collaboration:180` 的「总叶子数 >10」** 与实现（只按单 aggregate 上游数触发）潜在不齐——本 change 不在 README 复述该半句，spec 本身的澄清另议。

## Capabilities

### New Capabilities

无（docs-only）。

### Modified Capabilities

无。本 change 不改变实现和 OpenSpec specs。
