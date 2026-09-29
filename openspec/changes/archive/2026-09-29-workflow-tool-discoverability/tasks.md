# Tasks: Workflow 工具面可发现性

> 实现前须完成 grill（`reviews/grill-design.md`）与**停轮确认**。测试先行（TDD）：每条实现任务先落回归/新测试再落代码。

## 0. 实现前设计追问（batch-grill-me）——**未解除阻塞**

> **状态（立项时点）**：design 的 D1–D10 已成型，但 **Q1–Q4 刻意未拍板**（design 的 `## Open Questions`）。**grill-confirmation-gate 未通过，实现不得开工。**

- [x] 0.1 用独立零记忆 subagent 执行 `batch-grill-me`（或等价设计追问），逐项审视 `design.md` 的 D1–D10，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥3 条 + `## Open Questions`）
- [x] 0.2 **停轮**把 Q1–Q4 逐条**配具体例子**（design 的 Open Questions 节已给出 `gate` 带 `task` 的 spec、`merge` 的 `aggregate` 声明、`foreach` 的 `source` 陷阱、`ValidateWorkflow` 的探针风险四个场景）交用户确认；答复记录进 `grill-design.md` 的 `## User Confirmation`（每条 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）
- [x] 0.3 按 Q1–Q4 答复回写 design（D2/D6/D9/D10 + Non-Goals）与 spec delta、本任务清单
- [x] 0.4 **（不适用）** 用户 Q2 选「全量派生」，无需先归因再定幅度；且 grill R-E 已证原基线 transcript 不可恢复。归因改为在**本 change 重跑的基线**上做（见 4.2 / acceptance-evidence.md）：在基线 transcript 上统计 20 个探针的**失败归因分解**（分别由 `channel`/`strategy`/`join`/`reducer`/`kind`/`mode` 引起各几次），据实回写 design D2

## 1. 规格

- [x] 1.1 更新 `multi-agent-collaboration` 的 spec delta（MODIFIED「DeclareWorkflow 描述暴露循环契约」+ ADDED「Workflow spec schema 的封闭取值从单一来源派生」）
- [x] 1.2 明确本 change 的范围（proposal「What Changes」）、非目标（design「Goals / Non-Goals」）和**验收标准**（proposal「验收」节）
- [x] 1.3 开发前使用 `batch-grill-me` 或等价设计追问审视 `design.md`（见第 0 节；不得把 agent 自己的推荐答案当作用户确认）
- [x] 1.4 维护 `## Impact Analysis`（proposal）：列出影响、不影响和待确认影响面
- [x] 1.5 维护 `## Reference Implementation Research`（proposal）：`research_tier: full` + 完整五字段
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录待 grill 项与机械门禁要求

## 2. 测试（TDD：先落测试再落代码）

- [x] 2.1 **T1 schema↔常量 parity**（最重要的单条）：断言 `DeclareWorkflow.spec` 与 `RunWorkflow.spec` 的 schema 中，`kind`/`channel`/`reducer`/`strategy`/`join`/`mode` 的 enum 与对应源码常量（`NODE_KINDS`/`CHANNELS`/`REDUCERS`/`AGGREGATE_STRATEGIES`/`JOIN_SEMANTICS`/`NODE_MODES`）**逐字相等**（元素 + 顺序）
- [x] 2.1a T1 的**变异验证**：临时改一个常量，测试必须变红；改回必须变绿（防恒真断言——#246 R3 / #196 都踩过）
- [x] 2.2 **T2 描述内容断言**（沿 `tests/agent/subagent/test_workflow_cycle_contract.py:545-575` 范式）：`control` 在 `DeclareWorkflow` 描述中**零命中**；`cases` 语义句存在（行首/`startswith`/first-match 措辞）；per-kind 字段表存在（`join`/`items`/`source` 作为**字段名**出现）；`$ref:` 出现
- [x] 2.2a T2 回归：既有循环契约断言（`"defaults to 1"` 等）**全部保持绿**——只插入与纠错，不删既有契约文字
- [x] 2.3 **T3 route `task` 处置**（依赖 Q1 拍板）：选 (a) 则新增「route 带 `task` → `WorkflowValidationError`」负向测试；选 (b) 则新增「route 带 `task` → `declared` 且返回体含 `warnings`」测试；选 (c) 则仅由 T2 覆盖
- [x] 2.4 **T4 负向路径**：`{"kind":"route","strategy":"concat"}` 的拒绝信息 SHALL 按**实际** kind 命名（现在是 `aggregate node 'g' ...`，见 design D7）
- [x] 2.5 **T5 描述长度守卫**：断言描述长度 ≤ 宽松上界（如 6000 字符），防分节演变成无节制扩张
- [x] 2.6 集成：`DeclareWorkflow` 用**描述里给出的修正后正例**逐字声明，SHALL 成功

## 3. 实现

- [x] 3.1 `agent/subagent/workflow.py`：把 `mode` 的合法值从 `_parse_node` 的内联元组（`:503-506`）提为模块常量 `NODE_MODES`，供校验与 schema 共用（**不改校验行为**）
- [x] 3.2 `agent/subagent/workflow.py`：把 kind 专属解析器的错误文案改为按节点**实际** kind 命名并指出字段适用 kind（design D7；**只改文案，不改接受/拒绝行为**）
- [x] 3.3 `agent/tools/builtin/subagents.py`：新增 schema 派生 helper（从 `workflow.py` 常量展开嵌套 `properties`/`items`/`enum`），供两个工具共用（design D2 / D9）
- [x] 3.4 `agent/tools/builtin/subagents.py`：`DeclareWorkflowTool.parameters` 从裸 object 升级为派生 schema
- [x] 3.5 `agent/tools/builtin/subagents.py`：`RunWorkflowTool` 的 `spec` 分支同步同一份派生 schema（两条入口一致）
- [x] 3.6 `agent/tools/builtin/subagents.py`：改写描述里 4 处字符串 `control`（`:518` 术语 + `:530,531,536` 非法示例），全部改为不出现该 token 的表述，示例改用合法的 `summary`（design D3）
- [x] 3.7 `agent/tools/builtin/subagents.py`：描述新增「门控 vs 渠道正交」一段（design D3）
- [x] 3.8 `agent/tools/builtin/subagents.py`：描述新增 `cases` 一节（行首匹配 + first-match-wins + 具体在前 + 正例与反例 + `when` 的两种形态）（design D4）
- [x] 3.9 `agent/tools/builtin/subagents.py`：描述新增 per-kind 字段适用表（design D5）
- [x] 3.10 `agent/tools/builtin/subagents.py`：描述**分节化**（design D8）——既有循环契约一节逐字保留，只做插入与纠错
- [x] 3.11 `agent/tools/builtin/subagents.py`：描述里的枚举**改为指向 schema**，不再逐字重复（design D9）
- [x] 3.12 **（不适用）** Q1 选 (b)，不选 (a)：不改 `patterns.py:205`，不改 15 处测试
- [x] 3.13 **仅当 Q1 选 (b)**：`declared` 返回体新增 `warnings` 数组；route 带非空 `task` 时给出可行动提示（沿用 `_invalid_spec`/`_invalid_input` 的结构化返回先例）
- [x] 3.14 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现
- [x] 3.15 如果实现中发现 RIR 结论需要修正，先回写 Reference Implementation Research 和本任务清单
- [x] 3.16 更新必要文档（`docs/openspec-change-backlog.md` 入队 + 关键词扫描 `README.md`/`README_EN.md`/`docs/agent-internals.md`/`docs/architecture.md` 的工具清单段落；如无事实变化则在 review 记录中说明）

## 4. 端到端验收（本 change 的唯一有效性证据）

- [x] 4.1 **清空全局资产库** `~/.asterwynd/projects/<hash>/workflow-assets/`（残留资产污染 `ListWorkflowAssets`，本次实测已被 5 个 `description="d"` 的垃圾资产干扰）
- [x] 4.2 跑**基线**（改前）：用户 Q5 拍板 **N=1**（不引用无法复核的文档数字，也不跑 3 次），如实标注局限。真实 LLM + `--mode bypass`，记录 S0–S6（transcript 落 `reviews/baseline-transcript-2026-09-29.log`，session `1045cbb69fa4`；首次尝试因传输 `ReadError` 中断，保留为 `-run1-aborted.log`）
- [x] 4.3 跑**改后** 3 次：同提示词、同模型，记录 S0–S6
- [x] 4.4 落盘证据到 `reviews/`（`acceptance-evidence.md` + 三个 transcript；隔离修正与 S0 口径发现一并记录）（基线表 + 改后表 + 原始 transcript 路径 + 资产文件对照）
- [x] 4.5 主 session 软判断：读 transcript 回答「它在**理解工具** vs **理解任务**上花了多少」（两者必须分开）
- [x] 4.6 通过门槛判定：**严格口径 0/3 达标**（改后 S0 = 6/7/4，基线 9；S6 三次均成立）。已按未达标分支**记录实际差异与归因**——`invalid_spec` 中「域不可见」类由 **4/5 降到 1/4**（未归零；残留 run 3b 的 `unknown node field 'desc_placeholder'`）；剩余探针 100% 属**运行期语义**（不在本 change 范围）。**两项订正**：①改后 run 3 初次 S0=0 系 run 2 末尾 SaveMemory 注入 run 3 起始上下文所致，已 quarantine 后干净重跑（run 3b，S0=4）；②「域不可见类归零」订正为「1/4 未归零」。**交主 session 决定是否迭代**（见 `acceptance-evidence.md` 与 `building-review.md` 的「需用户决策」）

## 5. 验证

- [x] 5.1 运行相关单元/集成测试（`uv run pytest tests/agent/subagent/ tests/agent/tools/ -q`）
- [x] 5.2 运行全量测试（`uv run pytest -q`）
- [x] 5.3 运行 OpenSpec strict validate（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）
- [x] 5.4 运行项目 artifact checker（`uv run python scripts/check_openspec_artifacts.py`）
- [x] 5.5 确认 baseline CI 命令可本地通过（`uv run pytest -q` + strict validate + artifact checker）
- [x] 5.6 **benchmark smoke**（本 change 触及 `agent/tools/`，命中 `_requires_benchmark_smoke`）：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`
- [x] 5.7 确认 `patterns.py` 四个模板的 `spec_hash` 对照（若 Q1 选 (a)，peer-review 的 hash 变化 SHALL 被显式断言并写明原因）
- [x] 5.8 确认工具**数量与名字不变**（回归 `test_workflow_tools.py` 的工具集断言）
- [x] 5.9 **受保护 artifact 结构化事件**：改 `openspec/specs/**` 落 `current_spec_synced`、改 `docs/openspec-change-backlog.md` 落 `backlog_updated`（`uv run python scripts/workflow_state.py artifact-event ...`）

## 6. 审阅闭环与 PR 收尾

- [x] 6.1 跑 `/review-loop`（独立审阅闭环）：**2 轮收敛，最终 verdict = PASS**（R1 CHANGES_REQUESTED → 修 `subagents.py:634` 的 control token + T2 断言扩到 parameters 树 → R2 PASS）。产出 `reviews/building-review.md`；manifest 见 6.2
- [x] 6.2 review manifest 在本 change 的 `tasks.md` 最终化（含归档 move）之后生成（AGENTS.md「Review manifest 纪律」）
- [x] 6.3 把 spec delta 同步到 current spec（`openspec/specs/multi-agent-collaboration/spec.md`：MODIFIED 1 + ADDED 1），确认 delta 与同步后的存量文件口径一致
- [x] 6.3a 已归档到 `openspec/changes/archive/2026-09-29-workflow-tool-discoverability/`（日期前缀已带）
- [x] 6.4 从 `docs/openspec-change-backlog.md` 移除本 change（改挂「已归档」记录），并同步并行开发批次
- [x] 6.5 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`
- [x] 6.6 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖
- [ ] 6.7 (post-merge) 发起 PR 并合入（由主 session 确认后执行；worktree 不 push）
- [ ] 6.8 (post-merge) 给 issue #248 加完成说明 comment 并关闭
