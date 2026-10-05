# Building Review：readme-narrative-refresh（实现审阅）

- **change**: `readme-narrative-refresh`（issue #296）
- **审阅对象**: `README.md` / `README_EN.md` / `docs/architecture.md` / `docs/development-guide.md` / `docs/assets/readme/*` / change 自身文档
- **审阅性质**: 独立零记忆、只读、实现质量审阅
- **审阅基线**: 工作区 HEAD `8a255b0`，分支 `readme-narrative-refresh/2026-10-06`
- **verdict（Round 2）**: **PASS**

---

## Round 1 摘要（保留）

Round 1 对交付物做了逐条任务验证 + 对 `reviews/fact-check.md` 九条修复的落地复核 + spec 对齐 + 中英一致性 + 图/安全核验，结论 **CHANGES_REQUESTED**，提出 7 条 issue：

| # | 严重度 | 问题 |
|---|---|---|
| I-1 | Medium | 「扩展指南」整节被删除（违反 proposal Non-Goal「长内容一律折叠而非丢弃」） |
| I-2 | Medium | `docs/architecture.md:63`（新增行）重新引入「总叶子数 >10」，与本 change 在 README 的删除动作自相矛盾 |
| I-3 | Low | `<summary>` 标签残留「Claw-SWE-Bench」（正文已删） |
| I-4 | Info | `openspec validate --all --strict` 当前 exit 1（change 未归档，无 spec delta） |
| I-5 | Medium·流程 | `tasks.md` 0/30 全未勾选（归档阻塞） |
| I-6 | Low | 稳定核心层工具名单漏 `Glob`（与代码常量不一致） |
| I-7 | Low | 中英脚注不对称 |

**Round 1 已确认通过项**（本轮未回归）：9 条 fact-check 修复全部落地；数字/DSL/上下文/记忆/安全/工具治理常量/CLI flag 与代码一致；图片路径全可达；SVG 内嵌字体、无 foreignObject/外链、图源入库；安全扫描无泄露；中英结构/命令/数字一致；`check_openspec_artifacts.py` 通过。

---

## Round 2 复核（对修复声明的逐条验证）

### I-1 ·「扩展指南」补回 —— ✅ 已落地

- **证据**：`README.md:324` 与 `README_EN.md:324` 各新增一个 `<details>`（`<summary>扩展指南（添加工具 / Hook / 技能）</summary>` / `Extension guide (add a tool / Hook / skill)`），CN 块 `:324-382`、EN 块 `:324-382`。
- **内容完整性**（对照 `git show HEAD:README.md` 的 `## 扩展指南` 三小节）：
  - 添加新工具：3 步说明 + `@tool_parameters` 完整代码示例（旧 README 仅 3 行文字，新版更完整）。
  - 添加新 Hook：**7 个生命周期方法**示例（`on_run_started`/`before_iteration`/`after_llm_call`/`before_tool_execute`/`after_tool_execute`/`on_error`/`on_completion`）。
  - 添加新技能：`SKILL.md` YAML frontmatter 模板 + 注入时机说明 + `/skills`、`/skills reload`。
- **事实复核**：Hook 方法数 7 与 `agent/hooks/manager.py:16-27`（7 个 `async def`）一致——**旧 README 写「6 个方法」是错的**，新版改正为 7，属事实改进。`@tool_parameters(name, description, parameters)` 与 `agent/tools/base.py:19-22` 签名一致；`class MyTool(Tool)` + `read_only = True` 与 `base.py:49`（`async def execute`）、`:42`（`read_only: bool = False`）一致；`from agent.tools import Tool, tool_parameters, ToolRegistry` 与 `agent/tools/__init__.py:2-3` 导出一致；`from agent.hooks import HookManager, Hook` 与 `agent/hooks/__init__.py:2` 一致。
- **判定**：两 README 均补，内容完整且比旧版更准确，`git diff` 可见（新增行）。**关闭**。

### I-2 · `architecture.md:63` 删除「总叶子数 >10」 —— ✅ 已落地

- **证据**：`docs/architecture.md:63` 现为「单 aggregate 直接上游 >10 时，调度器自动插入分层 aggregate（逐层分组 `ceil(n / 10)` 直到顶层输入 ≤ 10），每层输出遵守 token 预算（leaf 300 / shard 800 / domain 1500 / root 3000，可配置）」。`grep -rn '总叶子数' README.md README_EN.md docs/architecture.md` → **无命中**（README 与 architecture 口径已一致）。
- **新引入的 `ceil(n/10)` 断言复核**：与 `agent/subagent/aggregation.py:126-143` `plan_layer_insertions` 逐字对应——`groups = math.ceil(remaining / max_fan_in)` 逐层向上直到 `groups <= max_fan_in`；`build()` 在 `:305-318` 以 `contributions = sum(expansions.get(edge.source, 1) ...)` 调用。新断言**准确**，未引入新错误。
- **判定**：自相矛盾消除，且新措辞比原 spec 更贴近实现。**关闭**。

### I-3 · `<summary>` 标签去 Claw-SWE-Bench —— ✅ 已落地

- **证据**：`README.md:184` `<summary>更多运行方式（provider 覆盖 / Web Debug / 编排 benchmark）</summary>`；`README_EN.md:184` `<summary>More run modes (provider override / Web Debug / orchestration benchmark)</summary>`。`grep -in claw README.md README_EN.md` → 正文与标签均无命中。
- **判定**：悬空引用消除。**关闭**。

### I-5 · `tasks.md` 勾选 —— ✅ 已落地

- **证据**：`grep -c '^- \[x\]' tasks.md` = **27**；未勾 = **3**，全为收尾阶段任务：`6.1 归档 change` / `6.2 清理 backlog` / `6.3 发起 PR`（`tasks.md:49-51`）。
- **判定**：1.1–5.7 全部勾选，与实测交付一致；余 3 条属归档/PR 阶段，此时结构上未完成属预期，将由收尾阶段执行并勾选。**关闭**（收尾时须确保 6.1–6.3 完成或按门禁规则处理）。

### I-6 · 稳定核心层措辞改「实际注册的核心工具」 —— ✅ 成立，采纳

- **证据**：`README.md:109` / `README_EN.md:109` 改为「`CORE_STABLE_TOOL_NAMES` 里**实际注册的**核心工具（`Read`/`Edit`/`Write`/`Bash`/`Grep`/`InspectGitDiff`）」。
- **断言复核**：`agent/tools/governance/selector.py:86` `stable_names = [n for n in self._names if n in self._stable]`——`self._names` 只在 `register`（`:48`）时追加已注册工具名，而 `Glob` 在 `agent/tools/` 下**无同名工具类**（`grep -rln 'class Glob' agent/tools/` 无命中），故 `Glob` 永不进入 `self._names`，被该列表推导过滤掉。**有效稳定层恰为 6 个已注册工具**。
- **判定**：措辞**准确**，比强行罗列 `Glob`（未注册、运行时从不出现）更贴合实际，且避免了「文档声称存在 `Glob` 工具而仓内无该类」的误导。优于 Round 1 建议。**关闭**。

### 不修项（记为「已知/接受」）

- **I-4** · `openspec validate --all --strict` exit 1：**已知/接受**。docs-only change 无 `specs/` delta，归档后 change 退出 validate 集合即通过（先例 `2026-06-21-align-observability-and-benchmark-docs`）。须确保归档 move 在本 PR 内完成。
- **I-7** · 中英脚注不对称（`README_EN.md:396` `> Chinese source` 无 CN 对应行）：**已知/接受**，属旧 README 既有，低危。

---

## Round 2 无回归复核

- 图片引用：8 处 `docs/assets/...` 全部命中文件（含新增图）。
- 标签平衡：`<details>` / `<summary>` CN 与 EN 均 5 open / 5 close（新增 1 个扩展指南折叠，平衡）。
- 中英结构：5 个 `<details>` 一一对应（`184`/`222`/`283`/`324`/`404`）；特色卡 1–6 编号一致。
- 未发现新问题。

---

## Round 2 结论

- **verdict: PASS**
- I-1 / I-2 / I-3 / I-5 / I-6 五条修复**全部落地、逐条复核为真**；I-6 的新措辞比原建议更准确。I-4 / I-7 记为**已知/接受**。Round 1 已通过项无回归，无新增 issue。

---

*审阅方式：独立零记忆只读审阅；事实断言逐条对照 `agent/` 源码与 `openspec/specs/` 复核；图以 cairosvg 实渲染核验结构（沙箱无 CJK SVG 字体，中文回退为渲染器限制，非 SVG 缺陷）。*
