# Building Review: observability-deepening（第二批）

## Reviewer
- run id: review-obs2-2026-08-03-02
- base sha: 7c6fc3e
- head sha: ced08ec80169991e77488af0f9ff217d2bb61aca

## Verdict
CHANGES_REQUESTED

第二批（4.x CI 回归门禁 + 5.x session timeline 看板 + 6.3 量化 + 7.x 收尾校验）实现完整、测试充分、纯逻辑与 CLI/IO 分层清晰，`_build_benchmark_runner` 重构保真。存在 1 个中等规格漂移（spec delta 场景与 gate 实际边界不符）与 1 个中等测试可移植性问题，建议修复后进入 closing。不阻塞整体，但按仓库"Spec 对齐"硬要求需先对齐。

## Tasks Verification

- 4.1: ✅ `benchmarks/gate.py`：`load_baseline`/`compute_run_metrics`/`compare`/`GateVerdict` 纯逻辑齐备。P95 直接 `from benchmarks.report import _percentile`（benchmarks/gate.py:24），与 report.py 同 nearest-rank 实现（report.py:53）；非 PASS 任务从 P95 排除（gate.py:64-65），与 grill Decision 14 一致。success_rate 对齐 `PASS_STATUSES`。
- 4.2: ✅ `agent/main.py:873` `benchmark_gate` 子命令：`--require-baseline`/`--update-baseline`/`--baseline`/`--success-rate-drop`/`--p95-regression-frac`/`--skip-p95` 全实现；0 任务保护在 `metrics["total_tasks"] == 0` 分支先于 update-baseline 执行（main.py:944-947），不写空基线。
- 4.3: ✅ 复用 `report.collect_run_results`（gate.py:215, main.py:952）；bootstrap CI 未进阈值判定（compare 只比 success_rate/p95），符合 Decision 8。
- 4.4: ✅ `tests/benchmark/test_gate.py`（40 用例）：边界"恰好 5pp 不拦/略超拦"（test_compare_success_rate_drop_exactly_5pp_not_blocked）、"恰好 baseline*1.05 不拦"、无基线/无任务/失败任务 0.0 时长排除全覆盖。
- 4.5: ✅ `tests/benchmark/test_gate_cli.py`（7 用例）：fake agent 小任务集 + 合成基线端到端，劣化拦截/更新基线/require-baseline 分支齐全。
- 4.6: ✅ `benchmarks/tasks/gate-smoke/` 2 个近零 IO 任务（`python -c "import sys; sys.exit(0)"`），base_commit=`7c6fc3e`（仓库内既有祖先），不依赖本 PR 新代码；`benchmarks/baseline.json` 含 `git_sha`、`created_at`、per_task，schema_version=1。
- 4.7: ✅ `.github/workflows/ci.yml` 新增独立 `benchmark-gate` job：`fetch-depth: 0`、git 身份配置、`--require-baseline --skip-p95`；纯新增 job，未改动既有 validate job。
- 4.8: ✅ `_build_benchmark_runner`（main.py:783）与原 `benchmark()` 内联构造逐行核对保真（runner 分支、`_load_cli_config`、`suggest_parallel_default` 护栏、BenchmarkRunner 参数全一致）；`benchmark()` 行为未变。
- 4.9: ✅ `tests/benchmark/test_cli_benchmark.py` 9 用例通过，既有 benchmark 命令行为不回归。

- 5.1: ✅ `web/server.py:81` `GET /api/sessions/{session_id}/timeline`：找到第一个 `TracingHook`（web/session.py:43），降序 + `bar_pct` + 原始 `index`（web/session.py:53-66），过滤 `duration_ms > 0` 的 in-flight（web/session.py:50），无 session 返回 404（server.py:87-88）。
- 5.2: ✅ 粒度=tool_call→tool_result 对，tool_name 用工具注册名；"待 TUI 落地后校验粒度一致性"记录于 design.md Decision 12 修正（grill 已确认不硬耦合）。
- 5.3: ✅ `web/static/debug.js` `renderTimeline`（fetch + 横向条形图，成功绿/失败红/hover 展开 arguments）+ `#timeline-refresh` 按钮；`index.html`/`style.css` 对应容器与样式。
- 5.4: ✅ `tests/web_tests/test_timeline.py`：降序/bar_pct/无 calls/in-flight 过滤/index 语义 + TracingHook 双前缀（`[Error`/`[Permission denied`）+ list 结果防御 5 个测试全通过。
- 5.5: ✅ `tests/web_tests/test_server.py` 新增 API 契约（字段完整/降序/bar_pct/404）+ `/debug` HTML 含 timeline 容器断言。
- 5.6: ✅ `test_timeline.py::test_tracing_hook_permission_denied_is_failure` + `get_summary` failed 计数回归测试。

- 6.3: ✅ `tests/benchmark/test_observability_quantification.py`：(a) CostLedger.bill() 分组/总额（含 unknown model 0 成本）、(b) ErrorClassifier 样本集覆盖全部 4 类 + 文本兜底分支、准确率 100%、(c) AgentLoop（ScriptedLLM）工具错误路径 trace token+error_type（permission_denied）+ ledger 记录，全部通过。

- 7.1: ✅ grill 证据存在 `reviews/grill-design.md`（8 条 Confirmed Decisions，≥3 门槛满足；checker `_extract_grill_decisions` 格式兼容）。
- 7.2: ✅ benchmark smoke 证据：baseline.json git_sha=94161e6、created_at=2026-08-02（真实 run 录制）；gate-smoke README 记录三次实测 0.5s/7.8s/20.5s；test_gate_cli 端到端覆盖。
- 7.3: ✅ `openspec/specs/observability/spec.md` 已含 Benchmark Regression Gate + Session Timeline 两个新 requirement；`workflow-events.jsonl` seq 3 有 `current_spec_synced` 事件（改受保护 artifact 需结构化事件，满足）。

> 注：tasks 7.1/7.2/7.3 仍为 `[ ]`（未勾选），符合"closing 时勾选"的流程；证据均已存在。

## Issues

- **1. spec delta 场景与 gate 实际阈值边界不符（p95=11.0 不被拦截）** [严重度: medium]：
  `openspec/specs/observability/spec.md` 与 change delta 的"门禁拦截劣化 run"场景写：`GIVEN 基线 success_rate=0.95、p95_latency_s=10.0; WHEN 新 run 的 success_rate=0.85 或 p95_latency_s=11.0; THEN 门禁返回非零`。实现中 `p95_ceiling = max(10*1.05, 10+1.0) = 11.0`，且边界严格 `>`（benchmarks/gate.py:153-155 + eps），实测 `compare` 对 p95=11.0 返回 ok=True（只有 >11.0 才拦截）。即场景的 p95=11.0 分支不满足，且规格正文"相对劣化超过 5%"对 <20s 基线实际被绝对下限放大到 >1s 绝对差（10%）。实现本身是 design Decision 15 的刻意选择（grill 确认），但 spec 同步（7.3）未把绝对下限写进规格，导致正式规格声称的灵敏度高于实现。建议：修改 spec 场景（如 p95=11.5 或加 `max(baseline*1.05, baseline+1s)` 措辞）以对齐实现。

- **2. gate-smoke 任务与 test_gate_cli 硬依赖 `python` 可执行文件，本地/裸环境必失败** [严重度: medium]：
  `benchmarks/tasks/gate-smoke/*/task.json` 与 `tests/benchmark/test_gate_cli.py` 的 `test_command` 均为 `python -c "import sys; sys.exit(0)"`。本审阅环境仅有 `python3`（无 `python`），结果 3 个 CLI 测试以 exit 127（command not found）失败；加 `python` shim 后 7 个全过。CI 因 `actions/setup-python` 提供 `python` 可过，但门禁任务集与测试对运行环境隐性依赖，非 hermetic。建议：task.json 用 `python3`（或 `sys.executable` 注入），测试用 `sys.executable`，保证任意环境可复现。

- **3. timeline API 未受 `ASTERWYND_DEBUG=1` 门槛保护** [严重度: low]：
  `/debug` 页面本身有 `debug_enabled()` 门槛（web/server.py:68-75），但 `GET /api/sessions/{session_id}/timeline`（server.py:81-89）不检查 debug 开关，直接暴露工具调用 `arguments`（可能含路径/命令等敏感信息）。session_id 为 12 hex（48-bit，run_identity.py），不易猜测，本地 demo 工具场景风险低；但与 design Decision 13"debug 门槛对 demo 可接受"的表述不一致。建议：端点加 `if not debug_enabled(): return 404` 或显式文档化该 API 无门槛。

- **4. 畸形 baseline JSON 触发 KeyError 而非干净报错** [严重度: low]：
  `load_baseline`（gate.py:168-178）只校验 `schema_version`，不校验 `metrics` 形状；手改的 baseline 缺 `metrics` 时 `compare` 在 gate.py:138-141 抛 KeyError（实测确认）。建议：`load_baseline` 校验 `metrics.success_rate/p95_latency_s` 存在并给出可读错误。

## Test Results

- `python3 -m pytest tests/benchmark/test_gate.py tests/benchmark/test_gate_cli.py tests/benchmark/test_observability_quantification.py tests/web_tests/test_timeline.py -q`
  - 本机直接跑：**3 failed, 40 passed**（test_gate_cli 3 个失败，原因=无 `python` 可执行文件，见 Issue 2）
  - 加 `python` shim（`PATH=/tmp/pyshim:$PATH`）后：**43 passed**（环境问题，非实现缺陷）
- `tests/web_tests/test_server.py`：37 passed（含 timeline API 契约 + 404 + 静态资产断言）
- `tests/benchmark/test_cli_benchmark.py`（4.9 回归）：9 passed
- `tests/agent/hooks/test_logging_tracing.py` + `tests/agent/test_loop.py`：65 passed
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`：OpenSpec artifact checks passed
- 已知无关失败 `tests/agent/code_intelligence/test_tree_sitter_symbols.py` 未运行（审阅范围外）

## 结论

第二批实现质量高：任务逐项均有真实实现与测试，`_build_benchmark_runner` 重构保真，timeline 后端整形 + 前端极薄渲染的分工正确，TracingHook 双前缀判定 + list 防御修复到位，CI job 为纯新增且处理了 shallow checkout 部署级阻塞。门禁纯逻辑阈值边界（严格 `>`、绝对下限、非 PASS 排除）有单测 pin，CLI 0 任务保护正确。

CHANGES_REQUESTED 依据是 Issue 1（正式 spec 场景与 gate 实际边界不符，spec 对齐是仓库硬要求）与 Issue 2（测试/任务集对 `python` 可执行文件的非 hermetic 依赖）。两者均为中小修复，不阻塞整体功能。Issue 3/4 为 low，可随修复一并处理。修复后按 /review-loop 复审至 PASS，再勾选 7.x 并归档。
