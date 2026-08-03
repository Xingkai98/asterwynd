# Grill: observability-deepening 设计追问

## Reviewer
- run id: grill-obs2-2026-08-03-01
- 时间: 2026-08-03

## Confirmed Decisions

- **决策**: 门禁采用纯逻辑模块 `benchmarks/gate.py` + CLI 薄封装（Decision 5）成立。理由：`agent/main.py` 的 `benchmark` 命令参数已约 130 行，把阈值判定/退出码/报告文本与 IO（跑 benchmark、读 JSON）分离后，集成测试可直接测纯逻辑函数而不触发真实 benchmark 运行；这与现有 `benchmark` 命令"CLI 组装 runner、纯逻辑在 benchmarks/ 下"的结构一致。注意：`benchmark-gate` 是 Typer 顶层命令（`@app.command()`，与 `benchmark` 平级，非其子命令），runner 构造逻辑（FakeAgentRunner 分支、`suggest_parallel_default` 资源护栏）在 `benchmark()` 内并未抽取成共享函数，`benchmark-gate` 若不抽一个 `_build_benchmark_runner()` helper 就会复制 ~130 行参数与分支，后续两命令容易漂移。来源: grill-obs2-2026-08-03-01
- **决策**: 基线 JSON 格式（Decision 6）合理，`task_set` 防跨任务集误比较、`success_rate` 对齐 `report.PASS_STATUSES`、`p95_latency_s` 对齐 `report._percentile` 的 nearest-rank 口径均正确。理由：`report.py` 的 `_percentile` 用 `min(int(n*p), n-1)`，`compare.py` 用 `durations[int(n*0.95)]`——经数值核对，对 p=0.5/0.95/0.99 且 n>=1 两者结果完全一致（`min` 的 clamp 只在 p>=1 时生效，`int(n*0.95)<=n-1` 恒成立），所以"与 report 同口径"是可达的；唯一分歧在空列表（report 返回 0.0，compare 直接 IndexError）与 n=1 极端。gate 应直接 `from benchmarks.report import _percentile` 复用而非再实现第三套。补充：当 gate-smoke 只有 2 个任务时，nearest-rank P95 就是两个时长中的最大值（索引 1），"P95" 在样本下退化为 max，这是后续 jitter 风险的根源（见风险 1）。来源: grill-obs2-2026-08-03-01
- **决策**: 阈值语义"成功率绝对 5pp + P95 相对 5%"（Decision 7）的口径选择正确，且无基线/无任务两分支、阈值可配（`--success-rate-drop`/`--p95-regression-frac`）覆盖了主要边界。理由：成功率用绝对百分点、延迟用相对百分比是两类指标最直觉的读法；spec delta 的 "more than 5 percentage points / degrades more than 5% relative" 与之一致。需精化两点：(a) 精确边界必须定死是 `>` 还是 `>=`（spec 写 more than，测试 4.4"恰好 5%"必须 pin 例如 current=baseline*1.05 不拦截、1.0501 拦截）；(b) gate-smoke 的时长是亚秒级，相对 5% 对 0.05s 基线的含义是 ±2.5ms 绝对抖动即拦截，应加一个延迟绝对值下限（如 `max(基线*1.05, 基线+阈值秒)`），否则小延迟下相对阈值无意义。来源: grill-obs2-2026-08-03-01
- **决策**: Timeline 数据源复用 `TracingHook.calls` + 后端整形（Decision 11）在实现上可行。理由：`web/session.py` 创建 AgentLoop 时传 `hooks=HookManager([TracingHook()])`，且 `session.agent.hooks.hooks` 已被 `run_session` 直接读写（debug hook 的 append/remove），因此 `GET /api/sessions/{id}/timeline` 通过 `session.agent.hooks.hooks` 列表找第一个 `isinstance(h, TracingHook)` 完全可访问，无需新增 session hook 链暴露接口。`bar_pct`/降序整形放后端可单测，与"前端极薄渲染"分工自洽。需补充边界：`before_tool_execute` 会先把 `duration_ms=0.0, success=True` 的条目 append 进 `calls`，run 中途查询会看到 0ms 绿色假条目，设计只假设"刷新按钮在 run 结束后手动刷新"，API 本身未强制——应过滤 `duration_ms==0` 或返回 `running` 标志。来源: grill-obs2-2026-08-03-01
- **决策**: 前端用 `/debug` 视图 Timeline 面板 + API 契约测试兜底（Decision 13）可接受。理由：仓库无 package.json/JS 测试设施，把排序/条宽逻辑放后端 Python 可单测、前端只做极薄渲染是当前约束下的合理分工；契约测试（字段完整/降序/bar_pct）+ `/debug` HTML 含 `timeline-container` 是能机械验证的最强兜底。需要明确接受的风险：前端 fetch/渲染/错误处理 JS 路径完全无自动化覆盖，回归只能靠手动 smoke。来源: grill-obs2-2026-08-03-01
- **决策**: `--update-baseline` 显式标志覆盖（Decision 9）成立。理由：门禁可持续的前提是"信任跑之后固化基线"，显式标志避免误覆盖；即使劣化超阈值也允许覆盖并警告，与"用户确认"语义一致。需补一条：`--update-baseline` 时若当前跑 0 任务（metrics 无法计算）应同样报错退出，不能写空基线（当前设计把"无任务退出非零"放在 Decision 7，CLI 必须在该分支先于写入执行）。来源: grill-obs2-2026-08-03-01
- **决策**: "与 TUI 对齐事件粒度"应降级为"文档记录对齐意图"，不作为硬耦合（Decision 12 修正）。理由：`add-minimal-tui-runtime-view` 的 tasks 全部未勾选、处于 planning 阶段，其 design 只写了"TUI 消费 AgentLoop/Web/trace 共用运行事件或轻量 adapter"这一方向性描述，尚未确定最终事件消费模型，当前无可对齐的实现；本 change 的 timeline 消费 TracingHook（内存态）本就不依赖 TUI 代码，5.2"文档记录对齐点"的措辞已隐含此意，应在实现时把"待 TUI 落地后再校验粒度一致性"写进文档。另外 Decision 12 的"duration_ms 与 trace tool_result 同源"表述不准确：TracingHook 在 `after_tool_execute` 用 `perf_counter` 计时，trace 的 `duration_ms` 来自 loop `_execute_single_tool` 的 `time.time()` 窗口（包裹整个执行含 retry），两者不同钟不同窗口，只能算"相近语义"而非同源。来源: grill-obs2-2026-08-03-01
- **决策**: 6.3 量化（CostLedger.bill / ErrorClassifier 准确率 / AgentLoop 工具错误路径端到端）用确定性验证而非真实 LLM benchmark，方向正确且可复现。理由：真实 LLM benchmark 受环境制约，确定性样本（ScriptedLLM）能覆盖成本分组、分类、trace token+error_type、ledger 记录四条关键路径。需补强：(b) 的"标注样本集分类准确率=100%"是弱断言，必须要求样本集覆盖全部 4 个 ErrorCategory 且覆盖"文本兜底"分支（如 `timed out`→NETWORK_TIMEOUT），否则只能证明部分类别；建议改为"每类≥1 样本 + 兜底分支≥1 样本，准确率=100%"。来源: grill-obs2-2026-08-03-01

## Open Questions

- gate-smoke 任务的 `base_commit` 策略未定：现有任务（如 asterwynd-001）用具体历史 SHA，`_create_worktree` 执行 `git worktree add --detach <path> <base_commit>`。GitHub Actions `actions/checkout@v4` 默认 fetch-depth=1（shallow），CI 检出里大概率没有该 SHA 对象，worktree add 会直接失败。要么新 job 显式 `fetch-depth: 0`，要么 gate-smoke 任务的 base_commit 语义定义为"当前 HEAD 可达的祖先"并保证浅克隆能解析。设计 Decision 10 未提这一点。
- 门禁 P95 相对阈值的延迟绝对值下限取值未定（防亚秒级 jitter 误拦）。
- 失败/崩溃任务 `duration_seconds` 默认 0.0（`TaskResult.from_dict` 缺省 / runner 的 BaseException 分支），纳入 P95 会系统性拉低延迟、掩盖回归。gate 的 `compute_run_metrics` 是否排除失败任务时长、或把 0.0 视为缺失，设计未定。
- timeline 是否过滤 in-flight `duration_ms==0` 条目；`success` 语义是否改用 trace 的 error_type 而非 TracingHook 字符串启发式（见风险 3）。
- baseline.json 是否记录生成时的 git sha（当前只有 created_at），以便审计基线对应的代码版本。
- 6.3(b) 标注样本集的最终构成（类别覆盖清单）未写进 tasks。

## 风险

- **[门禁 P95 在 gate-smoke 下=jitter 放大]**: gate-smoke 仅 2 任务，nearest-rank P95 = 两个 duration 的最大值，而 `duration_seconds = round(time.time()-start, 1)` 是纯墙钟（含 worktree 创建、git 操作、test 命令、清理），fake agent 只保证"决策确定性"不保证"计时确定性"。基线在开发者机器录制、CI 在共享 ubuntu-latest 跑，慢任务的绝对抖动很容易超 5% → 门禁大概率误拦 → 每个后续 PR 都要处理 flaky gate。设计风险节声称的缓解"固定 seed 避免环境抖动"在门禁路径上不存在（seed 只进了 `bootstrap_ci`，而 bootstrap CI 明确不进阈值判定），该缓解不成立。缓解建议：gate-smoke 测试命令设计成近乎零 IO（如 `python -c "..."` 直接 exit 0）、阈值加绝对值下限、或 CI job 先跑一次门禁只拦"基础设施回归"（status 变化）而把延迟阈值放宽。
- **[shallow checkout 阻塞 Decision 10]**: `actions/checkout@v4` 默认 shallow，`git worktree add --detach <worktree> <base_commit>` 需要 base_commit 对象存在；现有 ci.yml 无 fetch-depth 配置。若不加 `fetch-depth: 0`，新 job 在 CI 上必然任务级 error → gate 必红，且不是被测代码的回归。这是部署级阻塞，必须在 job 里显式处理。
- **[timeline success 语义与 batch1 分类矛盾]**: `TracingHook.after_tool_execute` 用 `success = not result.startswith("[Error")` 判定，而权限拒绝结果实际以 `[Permission denied: ...` 开头（`agent/tools/registry.py` 及 loop.py 第 828 行单独判 `[Permission denied`），因此权限拒绝调用会被记成 success=True、渲染成绿色，与本 change 第一批刚建成的 `permission_denied` 一级错误分类直接矛盾。timeline 的 success 字段要么改判 `[Error`/`[Permission denied` 双前缀，要么复用 trace 的 error_type。
- **[TracingHook 对 list 结果脆弱（既有缺陷，timeline 继承）]**: HookManager 协议 `after_tool_execute(tool_call, result: str | list[ContentBlock])`，但 `TracingHook.after_tool_execute` 签名是 `result: str` 并直接 `.startswith(...)`；`_execute_single_tool` 返回类型为 `str | list`。一旦某工具返回 ContentBlock 列表，hook 内 AttributeError 会沿 hook 链抛出，可能打断工具执行路径。timeline 依赖 TracingHook 的健壮性，需在本次至少加防御（`isinstance(result, str)`），根治可记为债务。
- **[失败任务 duration=0.0 掩盖延迟回归]**: 集成到 `collect_run_results` 的 TaskResult 若 `duration_seconds` 缺失（如 runner 异常分支、BaseException 聚合分支）回退 0.0，会拉低 run 级 P95，使延迟回归在 success_rate 未跌破阈值时被掩盖。gate 统计口径需明确。
- **[门禁默认 fail-open]**: 无 `--require-baseline` 时静默跳过（退出 0），依赖 CI 记得传。可接受但应打印显眼跳过信息，避免开发者误以为门禁在守。
- **[CLI 逻辑重复]**: `benchmark-gate` 复制 `benchmark()` 的 runner 构造/资源护栏逻辑，若不同步抽取共享 helper，两命令的参数语义会漂移。
- **[gate-smoke 任务与 base_commit 的测试语义陷阱]**: fake agent 不配置 edit_file 时不做任何改动，worktree 停在 base_commit，test_command 必须在该历史提交上无改动即通过。若误写依赖本 PR 新代码的测试（常见错误），gate 永远红。任务集设计必须验证"base_commit 裸跑即绿"。

## 与门禁机制（issue #95 / checker）的兼容性确认

- `scripts/check_openspec_artifacts.py` 的 `_extract_grill_decisions` 只认 `## Confirmed Decisions` 段内以 `- **决策**：`（或半角冒号）开头的行，本报告已按此格式写 8 条，≥3 门槛满足；grill 证据（本文件）会短路 `_check_design_review_task` 的 literal-marker 回退。
- 本 change 有 spec delta（`specs/observability/spec.md`），tasks 4.x/5.x 全部勾选后 `_tasks_all_complete` 为真，checker 将强制 `reviews/building-review.md` + review manifest（`/review-loop`）；第二批不与既有机制冲突，但 building 阶段改 `openspec/specs/**` 时需 `workflow-events.jsonl` 的 `current_spec_synced` 事件（7.3 已列出）。
- 阈值边界语义（`>` vs `>=`）需与 spec 的 "more than 5 percentage points" 保持一致，避免单测/集成测试/spec 三者漂移。
