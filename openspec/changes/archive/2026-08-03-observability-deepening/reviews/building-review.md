# Building Review: observability-deepening（第二批）Round 2

## Reviewer
- run id: review-obs2-2026-08-03-03
- base sha: 7c6fc3e
- head sha: af26c32c10d8d3899e6403222f75f5cbdd446ebd

## Verdict
PASS

第一轮 CHANGES_REQUESTED 的 4 项修复（spec 边界对齐 / hermetic python3 / timeline debug 门槛 / load_baseline 校验）全部到位且与实现一致，无新增中等问题。两处 low 级观察（门禁场景缺独立单测 pin、checker 在 PASS manifest 生成前的中间态）不阻塞本批功能，PASS 后由 /review-loop 生成 review manifest 即可满足机械门禁。

## Round-1 Fixes Verification

- **10.1 spec 场景与 gate 绝对下限边界对齐** [✅]：
  - change delta（`openspec/changes/observability-deepening/specs/observability/spec.md:60-75`）与当前规格（`openspec/specs/observability/spec.md:72-87`）的 Benchmark Regression Gate requirement 均已改为 `max(baseline * 1.05, baseline + 1.0s)`（相对 5% + 1 秒绝对值下限措辞），"门禁拦截劣化 run"场景 p95 从 11.0 改为 **11.5**，并新增"p95 恰在绝对下限上限处通过"场景（基线 10.0、新 run 11.0 通过，上限 `max(10.5, 11.0)=11.0` 严格 `>`）。
  - 实现边界实测一致：`compare`（benchmarks/gate.py:153-155）`p95_ceiling = max(base*1.05, base+1.0)`，严格 `>` + eps；对基线 10.0，`p95=11.0` 不拦截（ok=True）、`p95=11.5` 拦截（blocked_reasons=["p95_latency"]）。spec 声称的灵敏度与实现完全对齐。
  - 已补绝对下限措辞，设计 Decision 15（绝对下限）现在写进正式规格，7.3 spec 同步闭合。

- **10.2 hermetic python3** [✅]：
  - `benchmarks/tasks/gate-smoke/gate-smoke-001/task.json`、`gate-smoke-002/task.json` 的 `test_command` 均改为 `python3 -c "import sys; sys.exit(0)"`。
  - `tests/benchmark/test_gate_cli.py` 的 `test_command`（fixture 与劣化用例）均改为 `python3`。
  - 本审阅环境仅存在 `python3`（无 `python` 可执行文件），`test_gate_cli.py` 7 个用例在无 shim 情况下全通过（此前 Round 1 有 3 个 exit 127）。测试与任务集对运行环境的隐式依赖消除。

- **10.3 timeline API debug 门槛** [✅]：
  - `web/server.py:91-92` 在 timeline 端点入口 `if not debug_enabled(): return JSONResponse(..., status_code=404)`，与 `/debug` 页面门槛（server.py:70-71）一致，在构建响应前短路。
  - `tests/web_tests/test_server.py:569-579` 新增 `test_timeline_api_disabled_when_debug_off` 回归测试（删 `ASTERWYND_DEBUG` 后请求 timeline → 404）；既有 `test_timeline_api_returns_shaped_calls` 与 `test_timeline_api_404_unknown_session` 在 try/finally 中显式设 `ASTERWYND_DEBUG=enabled`，隔离正确。
  - `debug_enabled()`（web/debug_hook.py:13-14）请求时读 env，无缓存；`app` fixture 函数级作用域，测试不受跨用例污染。
  - **前端渲染路径未破坏**：`debug.js` 的 `renderTimeline` 仅在 `#timeline-refresh` 点击 / `#debug-tab` 点击时触发，非自动加载；非 debug 模式 `#debug-tab` 隐藏（chat.js:1345-1347 由 `/api/debug-status` 控制）、timeline 面板位于 debug view 内不可达；即便触发，`renderTimeline` 对 `!resp.ok` 走 "session 不可用" 分支（debug.js:22-25），优雅降级无硬错误。

- **10.4 load_baseline 校验** [✅]：
  - `benchmarks/gate.py:183-189` `load_baseline` 校验 `metrics` 为 dict 且 `metrics.success_rate` / `metrics.p95_latency_s` 为 int/float，缺失或形状畸形抛干净 `ValueError("baseline ... missing metrics.success_rate / metrics.p95_latency_s")`，不再在 `compare` 深处抛 KeyError。
  - `tests/benchmark/test_gate.py:251-256` 新增 `test_load_baseline_malformed_metrics_raises_clean_error`（`{"schema_version": 1, "metrics": {}}` → ValueError）。实测通过。
  - 已提交的 `benchmarks/baseline.json` 仍可正常加载（metrics 形状合法），无回归。

## Tasks Verification

- 4.1-4.9（门禁纯逻辑 / CLI / runner 重构 / gate-smoke 任务集 / CI job）：与 Round 1 结论一致，`_build_benchmark_runner` 重构保真，CI job 纯新增；本轮 4.6 的 task.json 已同步 python3。
- 5.1-5.6（timeline API / 整形 / debug 面板 / 测试）：与 Round 1 一致；本轮 5.1/5.5 补上 debug 门槛回归。
- 6.3（量化测试）：与 Round 1 一致，全过。
- 7.1-7.3 仍为 `[ ]`（closing 时勾选），证据均已在（grill-design.md 8 条决策、baseline smoke、spec 同步 + workflow-events.jsonl seq 3）。

## Issues

- **A. "恰在绝对下限上限处通过"门禁场景无独立单测 pin** [严重度: low]：
  10.1 在 spec 中新增"基线 10.0、p95=11.0 通过"场景，但 `tests/benchmark/test_gate.py` 未对该 floor 主导（基线 <20s）的精确边界新增单测——现有边界测试覆盖的是相对主导边界（基线 30、31.51 拦，`test_compare_p95_just_over_blocked`；基线 30、31.5 恰通过，`test_compare_custom_p95_regression_frac`）与 floor 语义（基线 0.05、1.05 上限，`test_compare_p95_absolute_floor_*`）。实现行为经审阅实测正确（11.0 过 / 11.5 拦），语义已被既有测试 pin，缺的只是 11.0/10.0 这个具体组合的显式回归。属覆盖增强，非功能缺陷。

- **B. artifact checker 当前对 review manifest 报错** [严重度: low, 流程性]：
  `scripts/check_openspec_artifacts.py` 当前报 `review manifest missing: openspec/changes/observability-deepening/reviews/building-review-manifest.json`——因 Round 1 的 building-review.md 已随修复提交但 manifest 尚未生成。这是审阅闭环中间态：AGENTS.md 规定"审阅通过后生成 review manifest"，PASS 后由 /review-loop 生成 manifest（绑定 reviewer run/base/head sha/tasks/spec/diff/report hash）即闭合；tasks 7.x 未勾选时 `_tasks_all_complete` 为 False，硬门禁（building-review + manifest 强制）未触发。非代码缺陷，无需本批修复。

- **C. load_baseline 对顶层非 dict JSON 仍抛 AttributeError** [严重度: low]：
  `load_baseline` 的 `data.get("schema_version")` 假设顶层为 dict；手改 baseline 为 JSON 数组时仍抛 AttributeError 而非 ValueError。超出 10.4 上报范围（缺 metrics 的常见畸形已覆盖），且极不可能出现，不改不阻塞。

## Test Results

- `uv run pytest tests/benchmark/test_gate.py tests/benchmark/test_gate_cli.py tests/benchmark/test_observability_quantification.py tests/web_tests/test_timeline.py tests/web_tests/test_server.py -q`
  - **82 passed**（本环境仅 `python3`、无 `python`，`test_gate_cli.py` 7 用例无 shim 全过——10.2 修复生效）
- `uv run pytest tests/benchmark/ tests/web_tests/ -q`（全量相关层）：**279 passed, 7 skipped**
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：**30 passed, 0 failed**（含 change/observability-deepening 与 spec/observability）
- 边界实测：基线 p95=10.0，ceiling=11.0；11.0 通过、11.5 拦截；success_rate 恰好 5pp 不拦、略超拦截——与 spec 场景一致。
- `scripts/check_openspec_artifacts.py`：当前仅报 review manifest missing（见 Issue B，流程性中间态）。
- 已知无关失败 `tests/agent/code_intelligence/test_tree_sitter_symbols.py` 未运行（审阅范围外）。

## 结论

第一轮 CHANGES_REQUESTED 的 4 项修复全部到位：spec 场景与 gate 实际边界（含绝对下限、严格 `>`）精确对齐，门禁任务集与 CLI 测试在仅 `python3` 环境全通过，timeline API 受 debug 门槛保护且不破坏前端渲染路径，`load_baseline` 对畸形基线抛干净 ValueError 并带回归测试。测试矩阵（相关层 279 passed + OpenSpec strict validate 30/30）证明无回归。

Verdict **PASS**。Issue A/C 为 low 级覆盖/鲁棒性增强，可后续处理；Issue B 为审阅闭环中间态，PASS 后由 /review-loop 生成 review manifest 即闭合。进入 closing：勾选 7.1-7.3、归档、跑 artifact checker 确认绿、发起 PR。
