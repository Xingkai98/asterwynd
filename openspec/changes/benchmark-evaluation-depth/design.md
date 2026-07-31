# Design: benchmark-evaluation-depth

## Context

Asterwynd 现有 benchmark（`openspec/specs/benchmark/spec.md`）已经能：从 tasks 目录读任务、支持多 agent runner、按任务写 `result.json`/`trace.json`/`runner.log`、区分 `passed/passed_with_warnings/failed/error/unsupported`、支持 Docker-based SWE-bench harness、用 `status + reason` 统一结果语义、`compare.py` 能输出 p50/p95/p99 延迟与 token 成本对比表。`benchmarks/models.py` 的 `TaskResult`/`RunMetadata` 已经携带 `status/reason/iterations/tool_calls/input_tokens/output_tokens/duration_seconds` 等字段。

现有 SWE-bench 支持（`_run_swebench_harness`）已经具备 adapter 的雏形：按 `task.execution_environment == "docker"` 与 `task.task_family == "swebench"` 分流，把 agent patch 转成 SWE-bench `predictions.jsonl`，调 `swebench.harness.run_evaluation`，再把 `report.json` 标准化为 `status`/`reason`/`detail`。但它是硬编码在 `BenchmarkRunner` 里的一个 if 分支，新增评测框架（如 Harbor）就得继续叠加 if。

弱项（面试复盘反复点名）：

- 结果粒度是"单次通过/失败"布尔值，没有任务分层，无法回答"这个 agent 在工具调用/上下文/规划哪个层面强"。
- 没有重复运行，单次结果不可当作稳定数字引用。
- 没有均值/标准差/置信区间/Pass@k，无法讲统计显著性。
- 开放式任务（无 hidden test）没有 judge 判定流程与人工回流。
- 失败只归因到 reason 字符串，没有按层、按模式的占比与回查入口。
- 没有一个渲染好的、可直接在面试中打开引用的量化结果页。

本 change 在既有 `benchmark` 能力域之上做增量扩展，全部 requirements 以 ADDED 方式并入 `benchmark` spec，不动单次运行语义。参考实现调研结论：本地 `.dev/reference-repos.txt` 不存在，改用 SWE-bench 论文/Codex pass@k/OpenAI Evals 方法论作为替代依据。

## Goals / Non-Goals

**Goals:**

- 建立任务能力分层体系（`execution`/`tool-usage`/`context-planning`/`multi-step-solving`），按层聚合统计。
- 支持同一配置 N>=3 次重复运行，聚合为分布。
- 输出均值/标准差/置信区间与 `Pass@k`，统计可复现。
- 开放式任务支持 judge 判定与人工回流标记。
- 失败按 reason 分类归因，支持占比与样例回查。
- 渲染可直接引用的量化结果页（markdown/HTML）。
- 用 adapter 模式抽象评测框架的验证阶段，支持无缝接入不同评测框架（SWE-bench、Harbor 等），把现有硬编码的 `_run_swebench_harness` 重构为第一个 adapter。

**Non-Goals:**

- 不改动既有单次运行语义、status/reason 取值与既有 artifact 结构（全部向后兼容扩展）。
- 不新建数据集/新任务族；复用现有 `benchmarks/tasks/`。
- 不做分布式/多机 benchmark 调度。
- 不替代面试表达与沟通训练（那属于 wayfinder map 的 out of scope）。
- 本 change 不做跨节点负载均衡。
- 本 change 首批只实现 adapter 接口 + 迁移 SWE-bench；Harbor 等具体框架的适配作为后续独立 change（复用本 change 的接口/统计/结果页管线）。
- adapter 只抽象验证/评分阶段，不包执行阶段（worktree vs sandbox 差异大，强行统一会过度设计）。

## Decisions

### Decision A0: 评测框架用 VerifierAdapter 抽象，边界画在验证阶段

**方案**：定义 `VerifierAdapter` 接口，只包验证/评分阶段，input 为任务定义 + agent 产出（patch / answer / transcript），output 为标准化 `Verdict { status, reason, detail, score? }`。用既有 `task_family` 作为选择 key，构建 registry（`task_family -> adapter`），调用方只查 key 拿 adapter、不 switch。新增框架 = 新增一个 adapter 文件 + 注册 + 契约测试，`BenchmarkRunner`/统计/结果页零改动。把现有硬编码的 `_run_swebench_harness` 重构为第一个 adapter（`swebench`），消除 if 分支。

**备选**：
- 继续用 if 分支累加框架。被拒：新增框架改共享 `BenchmarkRunner`，选择逻辑越来越长，碰坏其他框架风险高。
- adapter 包整个执行+验证阶段。被拒：执行阶段差异大（SWE-bench 是 worktree 改代码，Harbor 是 sandbox 跑 agent），强行统一会过度设计；验证阶段才是"框架"核心、最该可插拔。执行阶段如需适配（如接 Harbor sandbox）走独立 `ExecutionAdapter` 边界，不扩大 `VerifierAdapter`。

**理由**：接口最小且稳定，契约测试锁住接口防漂移；标准化中间表示（`TaskResult`/`status`/`reason`）让下游统计与结果页只认一种形状、跨框架复用，这才构成"无缝扩展"。

### Decision 1: 分层复用既有 `category` 字段，而非新增字段或重载 task_family

**方案**：复用 `TaskSpec` 既有 `category` 字段作为能力分层载体，取值为 `execution`/`tool-usage`/`context-planning`/`multi-step-solving`，缺省归入 `execution` 默认层。分层是跨框架统一维度，与框架来源（`task_family`）正交解耦。

**备选**：
- 新增独立 `evaluation_layer` 字段。被拒：`category` 语义天然是"任务所属能力维度"，新增会造成职责重叠、多维护一个字段。
- 复用 `task_family`（local/swebench）。被拒：`task_family` 是执行/框架语义（local vs docker vs harbor），把能力分层塞进去会让两种维度混在同一字段，破坏既有 `task_family` 规格含义。

**理由**：`category` 语义匹配且已是既有字段，零 schema 改动；缺省默认层保证兼容；分层与框架来源正交，靠标准化中间表示统一承载。

### Decision 2: 统计方法用 bootstrap 置信区间 + Pass@k，纯 Python 自实现

**方案**：对每层/每任务聚合：均值、标准差、95% 置信区间（bootstrap 百分位法，固定随机种子保证可复现）；通过类任务输出 `Pass@k`（k 取该任务重复次数 N，按既有通过判定统计）。无 hidden test 的开放式任务不做 Pass@k，改用 judge 判定。

**备选**：
- 解析置信区间（正态近似）。被拒：重复次数 N>=3 时样本小，正态近似在非对称分布上不可靠；bootstrap 对指标不设分布假设，且固定种子可复现。
- 引入 numpy/scipy 求 CI 与统计。被拒：bootstrap 置信区间仅需几十行（`random.seed` + `random.sample` 重采样求百分位），Pass@k 用组合计数公式，避免给项目新增外部统计依赖。

**理由**：小样本下 bootstrap 比正态近似稳健，且方法学可直接在面试引用；纯 Python 自实现保持项目轻依赖风格，固定种子可复现。

### Decision 3: 开放式任务 judge 用确定判定 + 人工回流标记

**方案**：开放式任务提供判定流程（如对 agent 输出跑一组规则/比较式 judge），判分结果写入 result；同时记录 `human_reviewed` 标记与判定理由，供人工回流审计。

**备选**：完全依赖人工逐条判定。被拒：benchmark 无人值守场景不现实；完全自动又缺可信度。折中为 judge 自动初判 + 人工回流标记。

**理由**：兼顾无人值守可运行与可审计性，判分口径一致。

### Decision 4: 失败归因在既有 reason 之上增加按层占比与回查

**方案**：按 `reason` 分类统计各层失败模式占比；每个失败模式输出可回查的任务 id + 运行轮次 + trace 路径。

**备选**：新增一套失败分类枚举。被拒：既有 `BenchmarkReason` 已覆盖主要失败类别（test_failure/timeout/max_iterations 等），重造会与既有 artifact 字段冲突。

**理由**：复用既有 `reason` 语义，只加聚合视图，向后兼容且避免口径分裂。git bisect 入口通过失败样例回查 trace 定位，作为本 change 的兼容入口，不做独立 bisect 引擎。

### Decision 5: 结果页作为新增渲染模块，复用 compare 数据

**方案**：新增一个评测结果页渲染模块（输入一次带重复运行+统计的 run 聚合，输出 markdown/HTML），复用 `compare.py` 已有的延迟/成本口径，新增分层与统计章节。结果页保留并展示任务的 `task_family`（framework）维度，可标注或按框架过滤，避免多框架数据混在一起不可比。

**备选**：改造既有 `compare.py` 输出。被拒：`compare.py` 是跨 run 对比工具，职责不同；新增模块聚焦单 run 的评测深度渲染，职责单一。

**理由**：单一职责，不破坏既有 compare 行为，结果页独立可引用；framework 维度与分层正交，靠标准化中间表示的 `task_family` 字段即可承载。

### Decision 6: 重复运行在 CLI 层循环，不侵入 runner 单次语义

**方案**：`--repeat N` 在 `agent/main.py` 的 `benchmark()` 里循环 N 次调用 `runner.run_all()`，每轮独立 `run_id`，最外层聚合。缺省 1 保持既有单次行为。

**备选**：在 `BenchmarkRunner` 内部加 `repeat` 参数做多轮。被拒：`run_all()` 是单次 run 的权威入口，侵入内部会破坏单次语义、改动面大。

**理由**：复用既有单次 run 全部行为；多轮天然产生独立 `run_id`，符合既有 artifact 结构，聚合在最外层隔离。

### Decision 7: 开放式任务复用"无 test_patch"判定，不新增字段

**方案**：以 `TaskSpec.test_patch_file` 是否存在判定开放式任务：无 test_patch 即视为开放式，跳过 Pass@k、走 judge 判定。

**备选**：新增 `open_ended: bool` 字段显式标记。被拒：`test_patch_file` 已存在，"有没有 hidden test"就是有没有 test_patch 的直接反映，新增字段徒增维护。

**理由**：零 schema 改动，语义正交直接。

### Decision 8: 结果页为独立 `benchmarks/report.py`，不复用 compare 职责

**方案**：新增 `benchmarks/report.py`，输入一次聚合 run，输出 markdown + HTML，复用 `compare.py` 的延迟/成本口径。HTML 沿用项目现有 style（参考 `reports/comparison.html`），不引第三方模板。

**备选**：扩展 `compare.py` 输出。被拒：`compare.py` 是跨 run 对比工具，单 run 评测渲染与它职责不同，混在一起破坏单一职责。

**理由**：单一职责，不破坏既有 compare 行为，结果页独立可引用。

## Risks / Trade-offs

- **[重复运行放大成本] → 用可配置 N（验收默认 3），结果页标注重复次数与总成本，避免无界放大。**
- **[bootstrap 在 N 小时置信区间宽] → 区间如实展示，作为"证据强度"而非失败；文档说明小样本局限。**
- **[分层标签覆盖不全 → 归入默认层，结果页标注默认层占比，避免静默失真。]**
- **[开放式 judge 误判 → 记录判定理由与人工回流标记，可审计可修正，且与既有 reason 语义兼容。]**
- **[新增 CLI `--repeat` 与既有参数冲突 → 复用既有 benchmark CLI 参数解析，`--repeat` 缺省 1 保持既有行为。]**
- **[adapter 抽象过早/过晚 → 以"已有两种验证形态"为抽象触发点（现有 SWE-bench + 待接 Harbor），不预为未出现的形态抽象；契约测试锁接口。]**
- **[迁移 `_run_swebench_harness` 有回归风险 → 迁移后跑既有 SWE-bench 兼容测试确认 status/reason 映射不变。]**

## Pre-Implementation Review

在进入 building phase 前，用 `grill-with-docs` 对 design.md 逐项确认以下决策：

- 分层字段名与取值集合是否与 CONTEXT.md/architecture 词汇一致。
- bootstrap 实现是否复用现有统计依赖，还是要新增依赖（如 numpy/scipy）；若新增，需确认依赖策略。
- judge 判定流程的输入输出 schema，以及开放式任务如何被标记（task schema 新增字段）。
- 结果页渲染输入的数据结构（聚合层模型），是否直接落在 `benchmarks/models.py`。
- `--repeat` 在 CLI 与 runner 的传递路径，以及 `RunMetadata` 如何表示聚合。
- `VerifierAdapter` 接口的 `Verdict` 字段与契约测试断言（status/reason/score 映射）是否足够锁住接口防漂移。
- registry 的 key 选择：确认 `task_family` 作为选择 key 的边界，以及未知 task_family 的 fallback（unsupported）。
- 迁移 `_run_swebench_harness` 后既有 SWE-bench status/reason 映射不变的回归验证方式。
- 测试策略：`tests/benchmark/` 下单元 + benchmark smoke 的覆盖范围。

（此节在 grill-with-docs 完成后补充最终结论；不粘贴聊天流水。）

## Testing Strategy

- 单元测试（`tests/benchmark/`）：分层聚合、bootstrap 置信区间（固定种子可复现）、Pass@k 计算、judge 判定、失败归因占比、结果页渲染（golden 片段）。
- adapter 契约测试：每个 adapter 跑同一套契约断言（fake 任务 → Verdict 的 status/reason/score 映射），锁住接口防漂移；未知 task_family 断言 fallback 为 unsupported。
- 迁移回归测试：SWE-bench adapter 迁移后，既有 swebench 任务的 status/reason 映射与迁移前一致。
- benchmark 层级测试：新增评测任务的 smoke 验证（`--repeat 3` 跑一组小任务）。
- 兼容测试：既有单次运行 artifact 结构不变、既有 `benchmark` spec 场景不回归。
- 每个 bug fix 需新增回归测试；涉及 benchmark 路径必须覆盖 benchmark 层级测试。
