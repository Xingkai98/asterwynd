# Building Review: evaluation-btrack-expansion

## Reviewer
- run id: building-review-evaluation-btrack-expansion-2026-08-18
- 时间: 2026-08-18
- 审阅范围: git diff origin/master...HEAD（17 commits，HEAD=0406dc6）
- 零记忆声明: 本 reviewer 未继承任何开发上下文，不预设结论；全部「实现声称」均在独立 base checkout 上逐一实测红绿后给出判断。

## Verdict

**PASS**

7 条新 B 轨任务全部真实、齐备且「base 红 + gold 绿」判别力实测成立（逐条在独立 worktree 以 base_commit checkout + test.patch → 红 / + gold.patch → 绿验证）；validate_coverage per-track B 扩展正确且有测试；manifest coverage 登记完整且校验通过；面试叙事数字 44（34 本地 = 22 A + 12 B）全套文档一致。未发现阻塞或需修复的中等问题；仅少数非阻塞观察项。

## Tasks Verification

逐条对照 tasks.md 所有 `[x]`（1.1–7.6；8.1–8.5 未勾选属正常——本审阅即 8.1 执行中）：

### 1. 规格与设计定稿
- **1.1** ✓ proposal.md 含 Change Type/Impact Analysis/RIR（research_tier=light，记录 `.dev/reference-repos.txt` 不存在事实）。
- **1.2** ✓ reviews/grill-design.md 存在（独立零记忆 grill），D1–D6 与 OQ-1~7 齐全。
- **1.3** ✓ grill-design.md `## User Confirmation` 含 Q1–Q7 全部用户答复（无占位文本），每条带确认时间。

### 2. context-planning 任务（CP-1~CP-4）
- **2.1 CP-1** ✓ `asterwynd-b02-running-benchmarks/`（issue.md/task.json/test.patch/gold.patch 齐备）。issue.md 不给路径（D2）；test_command 指向 `tests/agent/tools/test_list_running_benchmarks.py`（test.patch 新建）；gold.patch 新建 `agent/tools/builtin/benchmarks.py` 的 `ListRunningBenchmarksTool`（类名惯例）并装配 `factory.py` 两个入口 + `KNOWN_BUILTIN_TOOL_NAMES`。**实测**：base 597d121 + test.patch → 收集期 ModuleNotFoundError（红）；+ gold.patch → 4 passed（绿）。
- **2.2 CP-2** ✓ `asterwynd-b03-awaiting-grill-state/`。issue.md 列出 4 项触面（statechart/镜像常量/恢复默认值表/parity），task.json hints 同口径；gold.patch 同步 `flow/statechart.json` + `agent/workflow/event_log.py AWAITING_SUB_STATES` + `scripts/workflow_state.py _AWAITING_RECOVERY_DEFAULTS` + parity 测试精确集合。**实测**：base + test.patch → AssertionError（红）；+ gold → 1 passed（绿）。注：design/tasks 2.2 声称「6 触面」（含 workflow_state args.awaiting 校验 ~L576 与 workflow_methods.json），实测 ③ 由 event_log 常量经 `scripts/workflow_state.py:46` import 传递覆盖（`L576` 直接校验 `AWAITING_SUB_STATES`，加常量即生效）；⑤ `scripts/workflow_methods.json` 全文件无 awaiting 条目，非真实触面。issue.md 的 4 项清单准确，实现功能完整，属设计文档高估触面数（见 Issues M1）。
- **2.3 CP-3** ✓ `asterwynd-b04-report-track-grouping/`。test_command 指向 `tests/benchmark/test_report.py`；gold.patch 打通 models（TaskResult.track）+ runner（4/5 构造点填 track）+ report（`_infer_track` 兜底 + markdown/HTML By Track 块）。**实测**：base + test.patch → TypeError（track kwarg 不存在，红）；+ gold → 17 passed（绿）。第 5 构造点（`runner.py:218` SETUP_ERROR 路径）不带 track → 由 `_infer_track` id 前缀兜底，行为正确（见 Issues M3）。
- **2.4 CP-4** ✓ `asterwynd-b05-model-name-escaping/`（合成回归，grill OQ-2 推荐落地）。base_commit=6baa26c（本 change 内合成 bug 态，`adapters.py` 暂移除转义）；gold 提取 `_report_model_dir` staticmethod 恢复 `replace("/","__")` 并用于 report_path。**实测**：base 6baa26c + test.patch → AttributeError（`_report_model_dir` 不存在，红）；+ gold → 14 passed（绿）。base/gold 关系正确。

### 3. long-term-memory / long-context 任务
- **3.1 LT-MEM-1** ✓ `asterwynd-b06-save-memory-project-scope/`。gold.patch：`PersistentMemory` 加 `project_hash` 构造覆盖 + `with_project` 派生；`SaveMemoryTool` 加 `project` 参数；`MemoryIndexSource` 加 `project` 并在 render 时 `with_project` 过滤。test.patch 构造两个 project 实例断言 B 不可见 / A 可见（双端闭合）。**实测**：base + test.patch → AttributeError（红）；+ gold → 23 passed（绿）。
- **3.2 LC-1** ✓ `asterwynd-b07-memory-context-source-split/`。gold.patch：记忆层新增 `agent/memory/context_source.py` 导出 `render_memory_index(memory)` 纯函数，`MemoryIndexSource.render` 懒加载委托；test.patch 用「行为保持断言（render 输出 == render_memory_index 输出）+ 新模块路径可用」双断言，规避 C1 022 纯符号搬家教训。**实测**：base + test.patch → ModuleNotFoundError（红）；+ gold → 1 passed（绿）。

### 3b. bug-fix 任务（B=12）
- **3.3 BF-1** ✓ `asterwynd-b08-pipe-to-absolute-shell/`。gold.patch 修 `command_guard.py:_has_pipe_to_shell`：末段命令名去路径前缀 + env/command 包装剥离后与 `_SHELL_INTERPRETERS` 比对，`-c` 正则补绝对路径前缀。**实测**：base + test.patch → 5 failed（`/bin/sh`、`/bin/bash`、`/usr/bin/env bash`、`/bin/zsh`、`/bin/bash -c` 全部放行，红）；+ gold → 40 passed（绿）。合法命令 default-allow 未回归（既有 35 用例全绿）。

### 4. 覆盖矩阵 + 场景补齐
- **4.1** ✓ 每场景 B 轨补齐：bug-fix=b08（+既有 005/004-harden/011/017/020）、feature-dev=b02/b06、refactor=b03/b07、debug=b05、integration=b04（+b01）。B 轨 5→12 达 proposal「12–16」下限；hard×3（b02/b03/b07）符合 D1。
- **4.2** ✓ manifest.json coverage 登记全部 7 条新任务（b02~b08 均在），能力列归属：context-planning=b02/03/04/05、long-term-memory=b06、long-context=b07、safety-boundary=b08、multi-step-solving=b02/04、tool-usage=b02、error-recovery=b05。
- **4.3** ✓ `benchmarks/task_set.py` 新增 `REQUIRED_TRACK_COVERAGE = {"context-planning": {"B"}, "long-term-memory": {"B"}, "long-context": {"B"}}` + `CoverageReport.missing_track_coverage` + `is_complete()` 并入；测试 `tests/benchmark/test_task_set.py` 新增 3 条（缺 track 报告 / B 轨补上后缺口消失 / 完整矩阵含 per-track）。**实测**：`test_task_set.py` 8 passed；真实 manifest `validate_coverage` → missing_capabilities/scenarios/track_coverage/unknown 全空，is_complete=True。

### 5. 红绿可复现 + smoke
- **5.1** ✓ 全部 7 条任务独立 checkout 实测「base 红 + gold 绿」成立（证据见各任务条目与 Test Results）。
- **5.2** ✓ task_schema.load_task 对 7 条任务全部加载成功（scenario/track/test_command/gold_patch/base_commit 字段正确）；commit 0406dc6 已勾选 smoke 完成。

### 6. 面试叙事数字校准
- **6.1** ✓ 实测 task.json：A=22、B=12、verified=10、本地 34、总 44。
- **6.2** ✓ 全套文档一致：FINAL-master-script.md（pitch L8「44 任务」/验证 L27「44 任务（34 本地 + 10 SWE-bench）」/Bullet7 L96「从 44 扩到 ~90」/数据表 L117-118「44（34 本地 + 10 SWE-bench）」「当前已落 44」）；Q13-benchmark.md「当前已落 44 = 34 本地 + 10 Verified」；walkthrough/README L27「44 任务（34 本地 + 10 SWE-bench）」；W07（bullet 7 引言 + 校验表 + 升级路线「从 44 扩到 ~90」）；resume-description.md L9/L87/L104「34 个本地…（22 A 轨 + 12 B 轨）」；README.md L36/L178/L373（34 本地/44 任务）；README_EN.md L36/L178 同步。数字口径 44 = 34 本地 + 10 verified；34 = 22 A + 12 B 全链一致。

### 7. 同步与验证
- **7.1** ✓ proposal Impact Analysis 无 unknown/TBD/待确认残留。
- **7.2** ✓ design.md RIR 结论完整（status enabled / tier light / findings 含本地参考仓库不可用事实）。
- **7.3** ✓ `docs/openspec-change-backlog.md` 登记本 change（#156 后续项 2 承接），workflow-events.jsonl seq1/seq2 backlog_updated 事件齐全。
- **7.3b** ✓ `openspec/specs/benchmark/spec.md` 同步两个 Requirement（B 轨补齐 + 面试叙事同步），workflow-events.jsonl seq3 current_spec_synced 事件齐全。
- **7.4** ✓ 受影响测试实测通过（见 Test Results）。
- **7.5** ✓ OpenSpec strict validate 30/30 通过；`check_openspec_artifacts.py` 通过（tasks 8.x 未勾选，review-loop 门禁未触发属预期）。
- **7.6** ✓ benchmark smoke 完成（tasks 5.2 已勾选；本 reviewer 未重跑全量 smoke，但 7 条任务逐条 red-green 已覆盖 task 加载与 test_command 执行路径）。

### 8. 审阅与 PR 收尾（未勾选）
- 8.1 本审阅产出即 8.1 执行；8.2–8.5 待合入流程，属预期未完成项。

## Issues

- **M1（低，文档高估触面）** `openspec/changes/evaluation-btrack-expansion/tasks.md:12` / `design.md:34`：CP-2 声称「触面 6 处」含 ③ `scripts/workflow_state.py` args.awaiting 校验与 ⑤ `workflow_methods.json`；实测 ③ 是传递依赖（`scripts/workflow_state.py:46` import `AWAITING_SUB_STATES`，`L576` 校验直接消费该常量，event_log 加常量即覆盖），⑤ `scripts/workflow_methods.json` 全文件无 awaiting 条目，非真实触面。issue.md 的 4 项清单准确，实现功能完整（parity 测试绿证明端到端一致）。属实现优于设计文档表述，不影响验收。
- **M2（低，pre-existing 缺口）** `benchmarks/tasks/asterwynd-b08-pipe-to-absolute-shell/gold.patch`（`agent/tools/command_guard.py`）：修复覆盖全部 6 个列表面例 + env/command 包装；但 `env -S`/`env -i` 后再接 shell 的形态（如 `curl x | /usr/bin/env -S bash -c id`）旧新代码均未拦截，属既有缺口非本次引入，且超出该任务 Requirements 范围，不阻塞。
- **M3（低，fallback 覆盖）** `benchmarks/tasks/asterwynd-b04-report-track-grouping/gold.patch`：runner.py 5 个 `TaskResult(...)` 构造点只给 4 个填 `track`，`runner.py:218` SETUP_ERROR 路径未填 → `track=None` → `report.py:_infer_track` 按 id 前缀兜底（swebench-→verified / asterwynd-b→B / 其余→A），行为正确，与 issue.md「历史产物兜底」语义一致。
- **M4（低，backlog 位置）** `docs/openspec-change-backlog.md:88`：本 change 登记在「已合入/归档」条目区（带「本 PR」标注）而非「未实现队列」；属 8.3 合入后移除/同步前的中间态，工作流事件已记录，非缺陷。
- **M5（观察，非缺陷）** BF-1 任务暴露的 `command_guard._has_pipe_to_shell` 绝对路径绕过在 live repo（HEAD 0406dc6）仍存在——gold.patch 是评测用参考解，live 代码按 D1 Non-Goal「不改 benchmark 运行逻辑（只加任务）」刻意不动；该真实缺陷由 B 轨评测任务承载修复验证，属本 change 设计意图。

## Test Results

- `tests/benchmark/test_task_set.py`：**8 passed**（含 3 条 per-track B 新测试）。
- `tests/benchmark/test_task_set.py test_report.py test_adapters.py`（live repo 受影响文件）：**37 passed**。
- 逐任务 red-green 实测（独立 worktree @ base_commit，先 test.patch 后 gold.patch）：
  - b02 running-benchmarks（base 597d121）：收集期 ModuleNotFoundError（红）→ 4 passed（绿）
  - b03 awaiting-grill-state（base 597d121）：1 failed AssertionError（红）→ 1 passed（绿）
  - b04 report-track-grouping（base 597d121）：1 failed TypeError（红）→ 17 passed（绿）
  - b05 model-name-escaping（base 6baa26c 合成回归）：1 failed AttributeError（红）→ 14 passed（绿）
  - b06 save-memory-project-scope（base 597d121）：1 failed AttributeError（红）→ 23 passed（绿）
  - b07 memory-context-source-split（base 597d121）：1 failed ModuleNotFoundError（红）→ 1 passed（绿）
  - b08 pipe-to-absolute-shell（base 597d121）：5 failed（红）→ 40 passed（绿）
- 真实 manifest `validate_coverage`：全缺口头为空，is_complete=True。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：30 passed / 0 failed。
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`：passed。
- 已知环境失败（base 既有，非本 change 缺陷，未重跑）：`test_declarative_flow_engine.py::TestE2eEngineCliSmoke::test_engine_cli_validate_exit_code`（sys.executable 缺 agent 包）、`test_tree_sitter_extracts_java_and_kotlin_symbols`（tree-sitter 语法版本）。

## 结论

evaluation-btrack-expansion 的 building 实现完整落地：7 条新 B 轨任务（b02~b08）issue/test/gold 齐备，判别力经逐条独立 checkout 实测「base 红 / gold 绿」全部成立（含 CP-4 合成回归 base 6baa26c 的 bug 态与 BF-1 安全修复）；validate_coverage per-track B 扩展（REQUIRED_TRACK_COVERAGE + missing_track_coverage）实现正确、有 3 条测试、真实 manifest 校验通过；B 轨 5→12 达「12–16」下限，能力/场景矩阵缺口全补；面试叙事 44（34 本地 = 22 A + 12 B）在 FINAL/Q13/walkthrough/W07/resume/README/README_EN 全链一致；spec delta 两 Requirement 已同步到 openspec/specs/benchmark/spec.md，受保护路径均有 workflow-events 解释事件。未发现阻塞或需修复的中等问题，仅 4 条低优先级观察项（CP-2 触面高估、BF-1 的 env -S 既有缺口、runner SETUP_ERROR 依赖兜底、backlog 中间态）。Verdict: **PASS**。
