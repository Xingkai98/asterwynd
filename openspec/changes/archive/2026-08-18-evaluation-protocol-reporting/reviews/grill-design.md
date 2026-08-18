# Grill: evaluation-protocol-reporting 设计追问

## Reviewer
- run id: 372378bb-dca1-4e76-89db-1e235517ce65
- 时间: 2026-08-17

## 审阅范围与对照证据

对 `design.md` D1–D8 逐项追问，并对照下列代码/文档验证 design 主张：
- `benchmarks/report.py`、`benchmarks/compare.py`、`benchmarks/statistics.py`、`benchmarks/models.py`、`benchmarks/runner.py`、`agent/main.py`（benchmark CLI）、`benchmarks/adapters.py`、`agent/trace_recorder.py`
- `openspec/specs/benchmark/spec.md`（正式 spec + 顶部边界注记）
- `openspec/changes/evaluation-protocol-reporting/specs/benchmark/spec.md`（C3 delta）
- `scripts/self_check.py`（不存在）、`docs/benchmark-run-protocol.md`（不存在）
- `benchmarks/tasks/manifest.json`、`benchmarks/tasks/swebench-*`（10 条 fixture）
- `wayfinder-research/docs/research/eval-run-protocol-2026-08-17.md`（T1，149 行）
- `tests/benchmark/test_evaluation_metrics_compare.py`

## Confirmed Decisions

- **决策**: D1 运行协议文档转正路径成立（T1 文档存在，149 行，内容含任务集口径/模型/采样/预算/对照/五门禁）；理由: 已验证 `wayfinder-research/docs/research/eval-run-protocol-2026-08-17.md` 存在且结构与 D1 描述一致；`docs/benchmark-run-protocol.md` 当前确实不存在（ls 证实）；来源: 372378bb-dca1-4e76-89db-1e235517ce65
- **决策**: D2 渲染缺失现状成立（report.py 未渲染报告元组/污染注记/反作弊/fault_owner 交叉表/$/resolved/部分成功档/采样参数/小N/过程效率/覆盖矩阵）；理由: 逐行核对 `report.py::_render` 与 `render_html`，只有按层聚合、任务表、Token Cost、按 reason 的 Failure Attribution，无 fault_owner 交叉表与其余披露段；来源: 372378bb-dca1-4e76-89db-1e235517ce65
- **决策**: D4 CLI 现状成立（benchmark CLI 有 --repeat/--provider/--model/--agent/--seeds/--temperature/--model-version，无 --budget-cap/--no-cap/--preflight）；理由: 核对 `agent/main.py` benchmark 命令签名（700–735 行）与 typer 选项；来源: 372378bb-dca1-4e76-89db-1e235517ce65
- **决策**: D5 前置现状成立（`scripts/self_check.py` 与 `docs/benchmark-run-protocol.md` 均不存在，ls 证实）；来源: 372378bb-dca1-4e76-89db-1e235517ce65
- **决策**: C2 数据模型确实已备新字段（`TaskResult.partial/fault_owner/cache_read_tokens/cache_write_tokens/temperature/seed`；`RunMetadata.task_set_hash/max_iterations/timeout_seconds/network/adapter_version/prompt_version/pricing_table_version/temperature/seed/model_version/swebench_dataset_version/swebench_package_version`）且 statistics 层已实现 `paired_comparison`/`cost_per_resolved`/`fault_owner_cross`/`process_efficiency`/`swebench_versions`；理由: 逐字段核对 `models.py`（61–149 行）与 `statistics.py`；来源: 372378bb-dca1-4e76-89db-1e235517ce65
- **决策**: D6 spec 边界注记存在（正式 spec 顶部第 7 行「渲染边界：…归 C3」），C3 delta 以 MODIFIED 承接渲染义务与正式 spec 不冲突；来源: 372378bb-dca1-4e76-89db-1e235517ce65

## Open Questions

- **Q1（重要）: compare.py 的配对比较其实已接入 markdown 路径，design D3 的前提「未接入 paired_comparison」不成立**。实测 `compare.py:16` 已 `from benchmarks.statistics import paired_comparison`，`build_paired_report`（132–180 行）渲染 per-task delta/CI/win-rate/McNemar，`main()` 316 行写 `build_summary(runs) + build_paired_report(runs)`，且已有对应测试（`test_evaluation_metrics_compare.py`）。真正缺的是：HTML 路径 `build_html` 不含配对段、run 元数据只读 agent/model。
  场景例子：现在直接 `python benchmarks/compare.py <runA> <runB>`，生成的 `benchmarks/reports/comparison.md` 已含「## Paired Comparison」段（含 Mean per-task delta/CI/Win-rate/McNemar），只有 `.html` 没有。所以 tasks 4.1 的表述「compare.py 接入 statistics.paired_comparison」应改为「build_html 补配对段 + run 元数据补齐」，否则实现者会以为从零接线，重复 C2 已做的工作。请确认任务清单 4.1 的措辞与范围。

- **Q2（重要）: 报告元组数据源存在「字段已声明、runner 未写入」的断链**。`models.py::RunMetadata` 声明了 `task_set_hash/adapter_version/prompt_version/pricing_table_version/network/max_iterations/timeout_seconds`，但 `runner.py:181-201` 构造 RunMetadata 时只填 run_id/agent/model/mode/时间/counts/temperature/seed/model_version/swebench 版本，上述报告元组字段从未被任何生产者写入 run.json。
  场景例子：跑一次 `--repeat 3` 后看任一 `run.json`，`task_set_hash`、`adapter_version`、`pricing_table_version`、`network` 全是缺省 None；D2 item1 若「读 RunMetadata 新字段」渲染报告元组，结果页的 harness/task_set_hash/成本口径全是空。设计需明确：由 C3 扩展 runner 填充这些字段，还是渲染层按「缺失可空」兜底？若是兜底，spec「报告元组完整」场景就无法真正满足——请决策填充方。

- **Q3（重要）: report.py 渲染入口没有携带 RunMetadata，D2「读 RunMetadata」缺数据路径**。`render_report` 只接收 `AggregateRun`（含 agent/model/repeat/results/run_ids）或 `list[TaskAggregate]`，不含任何报告元组字段；`main.py` 聚合路径（802–811 行）虽有 `rounds_meta`（list[RunMetadata]），但构造 AggregateRun 时只透传 agent/model/repeat。
  场景例子：实现 D2 item1 时，渲染函数在 `_render` 内部拿不到 `task_set_hash`/`pricing_table_version`——要么给 `AggregateRun` 加 `metadata` 字段并让 main.py 传入，要么渲染层自己读 `run.json`。设计没有指明这条数据管线，请决策接口形态。

- **Q4（重要）: `incomplete` 状态在 C2 数据模型中不存在，「C2 数据模型可承载」不成立**。`models.py` 的 `RunMetadata` 没有 status 字段，`TaskResult.status` 是自由字符串但无任何生产者写 `"incomplete"`；runner 的 `run.json` 只有 passed/warnings/unsupported/failed 计数。
  场景例子：`--budget-cap 0.1` 在 5 轮中第 3 轮超限，系统「停止该 run 并标 incomplete」——写在哪里？run.json 顶层加 `status:"incomplete"`？还是 RunMetadata 加 `truncated: bool`？还是 TaskResult 标记？当前模型加不了，需要 C3 扩字段。请决策 incomplete 的落点与比较/结果页如何处理它（compare 配对时 incomplete 轮是否剔除？pass^k 分母是否含它？）。

- **Q5（重要）: 预算超限中断粒度与成本累计点未定义**。成本只在任务完成、result.json 落盘后（tokens）才可知；runner 用 `asyncio.gather` 并行跑任务，没有「运行中」的流式成本回调。D4 说「运行中累计成本超限停止该 run」，但没说是 per-task 检查、per-round 检查还是 per-token 调用检查，也没说并发在跑的任务如何取消。
  场景例子：`--repeat 5 --parallel 4 --budget-cap 5`，第 2 轮已启动 4 个并发任务，第 1 个完成后累计成本 $4.9，此时另外 3 个还在跑——是等它们完成再停？立即 cancel？第 2 轮标 incomplete 后，第 3–5 轮还跑不跑？请按 T1「停止剩余轮次」口径明确中断粒度与已启动任务的处理。

- **Q6（重要）: `--budget-cap` 缺省语义矛盾**。D4 写「建议默认 $50」与「缺省不设上限保持既有行为」两句并存；proposal 写「默认建议 $50」；spec delta 写「建议默认 $50…缺省 SHALL 不设上限保持既有行为」。三者对「不带 flag 时到底有没有上限」表述冲突。
  场景例子：用户 `uv run asterwynd benchmark benchmarks/tasks --agent asterwynd --repeat 5`（不带 --budget-cap），按 spec delta 是「不设上限」，按 proposal 是「默认 $50 上限」——成本可能跑 $100+ 也不停。请明确：默认无 cap（spec delta 为准），`$50` 只是协议文档中的「建议值」？还是 CLI 默认即 50？并同步修 proposal/design 措辞。

- **Q7（重要）: `--budget-cap 0` 与 `--no-cap` 的 argparse 解析语义**。typer 用 `Optional[float] = None` 表达「未传」，`--budget-cap 0` 会解析为 `0.0`；需明确 `0.0`、`None`、`--no-cap` 三者等价取消，还是 `0.0` 有别的含义。同时负数（`--budget-cap -1`）应拒绝。
  场景例子：用户先设 `--budget-cap 50` 后想取消，传 `--budget-cap 0`，typer 得到 `0.0`；若逻辑写成 `if cap and cap > 0: enforce`，`0.0` 自然取消，可行——但需显式写进设计并在 CLI 测试覆盖（`--budget-cap 0` / `--no-cap` / 缺省 / 负数四分支），不能靠隐式 falsy。

- **Q8: `--preflight` 的 Docker daemon 失败与 exit code 语义未定义**。spec delta 只定义了「内存 <8GiB → 提示 L1 + 退出码 1」；D4 说「Docker daemon 探测 + 内存检查」，但 Docker daemon 不可用时退出码是多少？与内存不足的 1 如何区分？
  场景例子：机器 16GiB 内存充足但 Docker 未启动，`--preflight` 应返回 0（Docker 无关紧要？）还是 1（有 docker 任务不可跑）？且本地无 docker 任务时 Docker down 是否也算「需降级」？请给出退出码表（如 0=可跑、1=需 L1、2=Docker 不可用），并在 spec delta 补充 Scenario。

- **Q9: self_check 五门禁的输入 artifact 与判定标准不可机械解析**。D5 只写「校验五门禁」，没说每门禁读哪个文件、判定谓词是什么、`<run_dir>` 是指单轮目录还是聚合目录。
  场景例子：门禁 1「同模型同 harness 复现（report 元组存在且一致）」——「一致」和什么比？跨 5 轮 run.json 的 model/harness 字段互比？门禁 2「seed 复现（采样参数记录完整）」——读哪里的 temperature/seed/model_version？门禁 3「失败归因闭环（fault_owner + 校准证据 + reason×owner 交叉表存在）」——「校准证据」（κ 值）存哪个文件？当前没有任何 artifact 写校准证据。请逐门禁列出输入文件 + 判定谓词 + 缺数据时的行为（跳过？报错？exit 几？）。

- **Q10: self_check 「可配置跳过」与 exit 码策略不具体**。Risks 提「可配置跳过」，D5 提「每门禁 exit 非零时输出缺失项；全部通过 exit 0」，但没说：跳过是 flag（`--skip gate4`）、env 还是 config？每门禁各自 exit code 是多少（1–5 区分还是统一 1）？spec delta 说「每门禁缺失 SHALL 报告具体项并以非零退出码表达」——非零是统一 1 还是逐门禁不同？
  场景例子：某 run 只有本地任务、无 swebench，门禁 4「披露段齐全（污染注记…）」天然不适用——用户想跳过门禁 4 只查 1/2/3/5，命令怎么写？`--skip 4`？跳过时 exit 0 吗？请给出可测的跳过语法与 exit code 表。

- **Q11: self_check 门禁 4 的披露清单与 D2 十项清单不一致**。D5 门禁 4 列「污染注记 + 严格 resolved + f2p/p2p 保留 + A 轨泄漏 + 小 N 声明」；D2 十项是报告元组/污染注记/反作弊/fault_owner 交叉表/$/resolved/部分成功档/采样参数/小N/过程效率/覆盖矩阵。两处清单交集不完整，且「严格 resolved」在 D2 与 spec 边界注记中都不存在，是门禁 4 独有概念。
  场景例子：一个 run 缺「覆盖矩阵」但门禁 4 不查它（清单没列），而 spec 边界注记/正式 spec 要求结果页展示覆盖矩阵——门禁与渲染义务对不上。请统一 D2 十项、self_check 门禁 4、spec delta「披露段齐全」三处清单为同一枚举（建议以 spec delta 场景为唯一事实源）。

- **Q12: 过程效率渲染缺 trace 数据路径**。`statistics.process_efficiency(trace_events)` 需要 trace.json 事件（tool_call/tool_result/edit + timestamp），但 `report.py` 的 `collect_run_results` 只读 result.json，从不读 trace.json；`render_report` 的输入也没有 trace 事件。
  场景例子：D2 item9「过程效率（time-to-first-successful-edit / exploration fraction）」要渲染，report.py 必须在聚合时为每个 task 打开 `run_dir/tasks/<id>/trace.json` 并喂给 `process_efficiency`——这条读取管线设计完全没写。请明确 trace 读取位置（collect_run_results 内？单独 loader？）与缺 trace 时的兜底（跳过过程效率段？）。

- **Q13: 反作弊披露与污染注记的「数字/事实」来源未定**。D2 item2 写「OpenAI 2026-02 弃用 + 138 实例 59.4% 缺陷」，item3 写「A 轨回归基线定位 + 来源/时间范围」。实测 `manifest.json` 有 `anti_cheat_disclosure`（track_a_note/source/time_range/training_cutoff/positioning），可支撑 item3；但「138 实例 59.4%」「OpenAI 2026-02 弃用」是 R1 调研常数，不在任何 run artifact/manifest 中。
  场景例子：结果页污染注记段写「138 实例 59.4% 缺陷」——这个数字是硬编码常量还是 manifest/run.json 字段？如果硬编码，未来 SWE-bench 数字更新要改代码；且「OpenAI 2026-02」是时间敏感事实。请决策：污染注记的数值来源（常量表？manifest 扩展？）与版本钉住（swebench_dataset_version/swebench_package_version 已在 RunMetadata，runner 会写，好）。

- **Q14: manifest.json 的路径解析未定义**。D2 item3（反作弊）与 item10（覆盖矩阵）都读 manifest，但 report.py 拿不到 tasks_dir 路径（它只拿 run_dir / AggregateRun）。
  场景例子：渲染覆盖矩阵时，report.py 怎么找到 `benchmarks/tasks/manifest.json`？是相对 source_repo 约定路径、运行时传入、还是 run.json 里记 manifest 路径？请给出解析规则与缺失 manifest 时的兜底（跳过矩阵段？）。

- **Q15: process_efficiency 的事件格式与 trace_recorder 实际写入格式是否对齐**。`statistics.process_efficiency` 期望 event 形如 `{"type":"tool_call","data":{"tool_name":...},"timestamp":...}` 与 `{"type":"edit","data":{"status":"ok"}}`。`trace_recorder.py` 的 `record_tool_call` 写 `type="tool_call"`、`record_edit` 写 `type="edit", status=status`——基本对齐，但 edit 的 status 取值（"ok"/"success"）是否与 recorder 实际写入一致、`tool_result` 的配对栈是否 LIFO 匹配，未见测试。
  场景例子：写过程效率 golden 测试时，用 trace_recorder 真实产出的 trace 跑 `process_efficiency`，若 edit status 是别的取值（如 "applied"），`time_to_first_successful_edit` 恒为 None。请补一条端到端 trace→process_efficiency 的单元测试，并在设计中写明事件契约。

- **Q16: HTML 结果页是否也要渲染全部披露段**。D2 说「report.py 渲染披露段」但没区分 markdown 与 HTML；`report.py` 有 `render_report`（md）与 `render_html` 两条路径，`main.py` 聚合路径只写 `evaluation-report.md`，HTML 路径目前无人调用。
  场景例子：面试要引用的是「结果页」，若只实现 markdown 披露段，`render_html` 仍是旧版无披露——spec「结果页（markdown/HTML）」是否要求两边一致？请决策：披露段只进 markdown，还是 HTML 同步（工作量×2，需对应 golden 测试）。

- **Q17: 能力覆盖矩阵属于 spec 边界注记之外的第十项**。正式 spec 顶部边界注记列的是 9 项（$/resolved-task/cache hit rate/定价表版本、reason×owner 交叉表、报告元组、SWE-bench 污染注记、部分成功档、采样参数、小样本声明、过程效率展示），「能力覆盖矩阵」不在注记中，来自正式 spec「任务支持显式能力分层」Requirement 的场景（套件级能力覆盖矩阵）。
  场景例子：tasks 3.5 把覆盖矩阵单列为任务，design D2 把它编号为第 10 项——但边界注记是 9 项。这不冲突（两个 spec Requirement 都要求渲染），但 D2 的「10 项」口径与 spec 注记「9 项」不一致，self_check/文档引用时会乱。请统一口径：披露段 = 边界注记 9 项 + 能力覆盖矩阵（独立 Requirement），总数是多少就说多少。

- **Q18: `--budget-cap` 对单轮（repeat=1）与多轮（repeat>1）的语义**。D4/T1 说「停止该 run」，T1 说「一轮 ≤ $50」——cap 是 per-round 还是累计全 run？`--repeat 5 --budget-cap 50` 是每轮 50 还是五轮共 50？
  场景例子：5 轮各 15 元 = 75 元，若 cap 是累计则第 5 轮被截断、前 4 轮完整；若是 per-round 则 5 轮全跑。T1 明确「一轮 ≤ $50」，但 spec delta 写「累计成本超过 --budget-cap 停止该 run」用的是累计口径。请按 T1 per-round 口径统一 spec/design，并在 CLI 测试覆盖 repeat>1 + cap 超限。

## User Confirmation

全部 18 条 Open Questions 由用户审阅后按推荐确认，主 session 于 2026-08-17 转达实质答复。

- **Q1**: 用户答复：tasks 4.1 改措辞「build_html 补配对段 + run 元数据补齐」，HTML 复用 C2 已实现的 build_paired_report，不重复实现 markdown 配对；确认时间: 2026-08-17
- **Q2**: 用户答复：C3 扩展 runner 填充 RunMetadata 报告元组字段（task_set_hash/adapter_version/prompt_version/pricing_table_version/network），否则 spec「报告元组完整」违约；确认时间: 2026-08-17
- **Q3**: 用户答复：AggregateRun 加 metadata 字段，main.py 聚合时透传 rounds_meta，render_report 可读 RunMetadata；确认时间: 2026-08-17
- **Q4**: 用户答复：RunMetadata 加 truncated: bool；compare 剔除 incomplete 轮、pass^k 分母不含 truncated 轮；确认时间: 2026-08-17
- **Q5**: 用户答复：按轮检查预算，超限停止后续轮次；轮内已启动的自然完成不 cancel，该轮标 truncated；确认时间: 2026-08-17
- **Q6**: 用户答复：以 spec delta 为准——缺省不设上限，$50 只作协议建议值，修 proposal/design 措辞；确认时间: 2026-08-17
- **Q7**: 用户答复：--budget-cap 0/None/--no-cap 等价取消，负数报错，CLI 测试覆盖 4 分支；确认时间: 2026-08-17
- **Q8**: 用户答复：preflight 退出码 0=可跑、1=内存<8GiB 需 L1、2=Docker 不可用；spec delta 补 Scenario；确认时间: 2026-08-17
- **Q9**: 用户答复：self_check 逐门禁定输入 + 判定谓词；门禁 3（失败归因闭环）因无 κ artifact 降级为查 fault_owner 覆盖率并在协议注明；确认时间: 2026-08-17
- **Q10**: 用户答复：--skip <n> 可重复；非零统一 exit 1；确认时间: 2026-08-17
- **Q11**: 用户答复：以 spec delta「披露段齐全」清单为唯一事实源；能力覆盖矩阵独立另查（注记 9 项披露段 + 覆盖矩阵独立 Requirement）；确认时间: 2026-08-17
- **Q12**: 用户答复：聚合时读 run_dir/tasks/<id>/trace.json 喂 process_efficiency，缺 trace 跳过该段；确认时间: 2026-08-17
- **Q13**: 用户答复：污染披露数字集中常量表注来源日期；版本钉住用 RunMetadata.swebench 版本字段；确认时间: 2026-08-17
- **Q14**: 用户答复：manifest.json 路径由 CLI 从已知 tasks 路径传入，report.py 加可选参数，缺失时跳过矩阵/反作弊段；确认时间: 2026-08-17
- **Q15**: 用户答复：补端到端 trace_recorder→process_efficiency 单元测试锁 trace 事件契约；确认时间: 2026-08-17
- **Q16**: 用户答复：披露段 md 全量 + HTML 复用同一段渲染函数，golden 双覆盖；确认时间: 2026-08-17
- **Q17**: 用户答复：口径统一「注记 9 项披露段 + 能力覆盖矩阵独立 Requirement」；确认时间: 2026-08-17
- **Q18**: 用户答复：预算 cap 按 T1 per-round，spec delta 措辞「任一轮超限停止剩余轮次」；确认时间: 2026-08-17

## 风险

- **配对比较重复实现风险**：design D3 的前提（compare 未接入 paired_comparison）在 markdown 路径不成立，若按 tasks 4.1 原样实现可能重复 C2 已完成的 `build_paired_report`，或在 HTML 里另起炉灶导致 md/html 两份配对逻辑漂移。建议复用 `build_paired_report`，HTML 只补渲染壳。
- **报告元组断链导致 spec 违约**：若 Q2/Q3 不解决，`RunMetadata` 报告元组字段恒为空，spec「报告元组完整」场景（`openspec/specs/benchmark/spec.md` 425–428 行）无法满足，self_check 门禁 1 也必然失败。这是本 change 最容易被 review-loop 打回的点，需在实现前定填充方。
- **预算中断与 incomplete 模型缺失**：Q4/Q5 未决时，`--budget-cap` 超限行为无法落盘，compare/结果页对 incomplete 轮的处理悬空，CI benchmark 层测试难写。且「不伪造结果」的承诺依赖 incomplete 可表达。
- **self_check 五门禁不可机械解析**：Q9/Q10/Q11 若维持现状，self_check 会因判定谓词不明而变成「人工目检脚本」，与 T1「自洽数字蓝本」的机械保证目标相悖，review-loop 会质疑其可测性。
- **披露段渲染兜底遗漏**：旧 run.json 无新字段时，Q2/Q12/Q14 三类兜底（RunMetadata 空、无 trace、无 manifest）都需显式 fallback，spec delta「缺失字段 SHALL 渲染兜底占位而不报错」是硬 Requirement，遗漏任何一类都会在旧数据回归测试中炸。
- **golden 片段测试易碎**：D2 十项中污染注记含时间敏感数字（OpenAI 2026-02）、过程效率含浮点时间，golden 断言需只锁片段结构与常量数字，不锁 trace 时间戳/CI 数值，否则 fixture 一改就碎（design 已在 Risks 提片段断言，需在测试策略落实为「不含时间戳/路径」的断言规范）。
- **D6 spec 同步范围**：delta 以 MODIFIED 改写「渲染可引用的量化结果页」并新增 4 个 ADDED Requirement，同步回正式 spec（tasks 7.2）时需确认不改动 C2 已合入的指标 Requirement 文本（pass^k/成本/配对），只增渲染义务，避免 spec 漂移被 strict validate 拦下。
