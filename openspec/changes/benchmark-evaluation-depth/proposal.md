# Proposal: benchmark-evaluation-depth

## Change Type

- primary: feature
- secondary: process

## Why

面试复盘中评测体系被反复点名，是当前最致命短板：现有 benchmark 只能给出"通过/失败/超时"这类布尔结论，缺少分层、可重复运行、统计显著性和可直接引用的量化数据。问到"Asterwynd 的评测怎么做"时，无法从分类、统计方法讲到量化结果。这个 change 把现有 benchmark 从"通过/失败"升级为分层、可比较、可引用的数据面板。

## What Changes

- 引入任务分层体系：对 `benchmarks/tasks/` 下现有任务与新增任务进行能力分层（如基础执行/工具调用/上下文与规划/多步问题求解），复用 `TaskSpec` 既有 `category` 字段标注层级（不新增字段），形成可复用的任务盘点清单。
- 支持同一配置的 **N>=3 次重复运行**：runner 允许一次调用执行多轮重复，聚合为按任务、按层级的分布结果，而不是单次孤点。
- 引入统计显著性与置信区间：对重复运行结果做均值/标准差计算，用 bootstrap 或解析近似给出置信区间；支持 `Pass@k` 这类稳定性指标。
- 判分主干为确定性验证：所有任务统一走确定性 VerifierAdapter 判定（hidden test/脚本/状态比对），与业界主流一致；LLM judge 判分作为开放产出评测的可选后续项，本 change 不实现。
- 引入失败归因：按失败 `reason` 分类统计，支持失败模式占比与样例回查，为后续 git bisect 定位性能退化提供入口。
- 产出量化武器页：把上述指标汇总为一个可在面试中直接引用的结果页（markdown/HTML），覆盖 Pass@k、均值/标准差、置信区间、延迟分布和 token 成本。
- 用 `VerifierAdapter` 抽象评测框架的验证阶段：把现有硬编码的 `_run_swebench_harness` 重构为第一个 adapter，以 `task_family` 为 key 走 registry，使新增评测框架（如 Harbor）只需新增 adapter + 契约测试即可无缝接入，不改共享 runner/统计/结果页。首批只做接口 + SWE-bench 迁移，Harbor 适配作为后续独立 change。

## Capabilities

### New Capabilities

无。本 change 全部为既有 `benchmark` 能力域的增量扩展，不引入新 capability。

### Modified Capabilities

- `benchmark`: 结果汇总与 artifact 语义扩展——新增任务能力分层、重复运行聚合、统计指标（均值/标准差/置信区间/Pass@k）、确定性判分统一、失败归因、量化结果页渲染、以及 `VerifierAdapter` 框架抽象（含 SWE-bench 迁移）的 requirements；全部以 ADDED 方式追加，与既有 `RunMetadata`/`TaskResult`/result artifact 兼容扩展（新增字段而非替换），既有 status/reason 语义保持不变。

## Reference Implementation Research

- status: enabled
- reason: 评测深度是 coding-agent 领域有成熟方法论的能力，需要对照主流方案（SWE-bench、Codex 的 Pass@k、OpenAI Evals 的统计方法）确认指标口径与分层方式，避免自造一套不可对外引用的口径。
- research questions:
  1. SWE-bench 如何定义 pass@k、如何做多轮重复与统计汇总？
  2. 主流水准如何对 benchmark 任务分层（任务难度/能力维度）？
  3. 业界 agent benchmark 由什么题型组成，验证方式是确定性还是需要 judge（LLM 主观评分）？开放问答占比高吗？
  4. 失败归因与性能退化（git bisect）的常见实现入口是什么？
- findings: 当前工作区本地 `.dev/reference-repos.txt` 不存在，本地参考仓库不可用。依据规则记录该不可用事实。作为替代依据，调研了 11 类业界主流 agent benchmark（SWE-bench/SWE-bench Pro、Terminal-Bench 2.0、Aider、OpenHands、GAIA、HumanEval/MBPP、BrowseComp、WebArena-Verified、τ-bench、MLE-bench、Harbor-Index/τ³-bench/ContextBench），结论：业界 agent benchmark 以任务式/多步操作为主流，判分以**确定性验证**为主（hidden test patch 跑 pytest 判 F2P/P2P、文件系统状态 diff、DB 状态哈希、官方 metric 重算、规范化精确匹配），几乎不依赖 LLM judge 主观打分；越权威者（GAIA、τ-bench、WebArena-Verified）越刻意回避 judge（不可复现、有偏差、无法评测 SOTA）。开放问答占比低，仅 BrowseComp（事实问答数值容差）、MT-Bench（对话质量）等"答案无唯一客观标准"的开放产出才真正用 LLM judge。这确认：评测主干应为确定性 VerifierAdapter，judge 仅作为开放产出评测的可选后端。SWE-bench 的 pass@k、Codex 的采样次数与置信区间推导、OpenAI Evals 统计工具仍作为统计口径参考。后续实现阶段若本地参考仓库恢复，应优先用 codegraph 复核具体调用链。
- design impact: 统计口径（pass@k、bootstrap 置信区间）与任务分层 schema 是设计阶段的输入。评测主干采用确定性 VerifierAdapter 判分（与业界主流一致）；judge（含 LLM judge + 人工回流校准）降级为可选后端，本 change 不实现，作为引入开放产出任务时的后续项。

## Impact Analysis

- **能力域**: `benchmark`（结果汇总与评测语义扩展）。
- **代码**: `benchmarks/`（`models.py` 增加分层与统计字段、`runner.py` 支持重复运行聚合与 adapter registry、新增 `VerifierAdapter` 接口及 `swebench` adapter 迁移、`compare.py`/新增报告模块渲染结果页、`swebench_analyze.py` 兼容扩展）、CLI 参数（`benchmark` 命令支持 `--repeat` 等）。
- **测试**: 新增 `tests/benchmark/` 分层、重复运行、统计聚合、确定性判分、结果页渲染与 adapter 契约测试；迁移 SWE-bench 后跑既有兼容测试确认 status/reason 映射不变；涉及 benchmark 路径必须覆盖 benchmark 层级测试，并跑 benchmark smoke 验证。
- **文档**: `openspec/specs/benchmark/spec.md` 同步扩展（ADDED requirements）、`docs/benchmark-plan.md` 与 `docs/openspec-change-backlog.md` 更新、README 同步。
- **基准**: 不改变既有 benchmark 单次运行的语义与既有 `benchmark` 规格的行为；全部为向后兼容扩展。
- **流程（process）**: 引入评测方法论约定——任务能力分层口径、重复运行与统计口径、VerifierAdapter 框架接入契约，后续所有评测任务与框架接入需遵循此约定。
