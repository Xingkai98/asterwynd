# Tasks: sandbox sink 改守护式 reset，修跨上下文收尾污染后续 run 的事件归属（fix-issue-264-sandbox-sink-context）

> 关联 issue：[#264](https://github.com/Xingkai98/asterwynd/issues/264)。
> 本 change 为**生产代码 bugfix**（非测试侧）；根因与实测证据见 `diagnosis.md`，方案见 `proposal.md` / `design.md`。
>
> **是否走 grill：本 change 直接进入实现，不单独跑 `batch-grill-me`。** 论证：
>
> 1. 本 change 是 **bugfix**（`Change Type: primary: bugfix`），不是分流表里「走 grill 的非平凡
>    change」；仓库机械门禁对 bugfix 亦不要求 grill 证据（`check_openspec_artifacts.py` 的
>    `DESIGN_TYPES = {feature, refactor, process}` 不含 bugfix）。
> 2. **机制已由上游钉死**：根因与 #261 同源，`#261` 的 `diagnosis.md` 已给出确定性复现 + 对照
>    实验（`cancel()` 不污染 / 「循环已关 + GC 终结」污染），本 change 的 `diagnosis.md` 在**当前
>    树上**重跑并复核。
> 3. **设计空间被上游锁定**：`reset_sandbox_sink(token)` 只是 `fix-issue-255` 建立、
>    `fix-issue-261` 验证过的 `set_mode_ceiling` / `reset_mode_ceiling` 同形结构在 sandbox 通道的
>    复制；三个设计点（D2 `_NOOP` 语义 / D3 API 形态 / D4 token 门控）各有**一手实测结论**
>    （`repro/design_points_probe.py`），**无待用户拍板的真实分叉点**。
> 4. 与 #261 的先例一致（该 change 同样是 bugfix 且在 tasks 顶部显式论证跳过 grill）。

## 1. 根因定位（诊断先行）

- [x] 1.1 在**最新 master**（#261 已合入）上重跑 `repro/sandbox_sink_repro.py`（形态 A），
      确认**仍复现**：5/5 `sink_clobbered=True`（覆盖面 `_NOOP`）、`LIVE trace 收到 sandbox 事件: []`
- [x] 1.2 在最新 master 上重跑归档的 `sandbox_sink_misroute.py`（形态 B）——**本机 0/10 不复现**；
      定位为**脚本 GC 时机脆弱**（`llm.mgr` 在 plant 阶段仍持有 manager，遗留 task 未被回收），
      **非缺陷消失**：加一行 plant 阶段 `gc.collect()` 的确定性变体 `sandbox_sink_misroute_gcwindow.py`
      **10/10 复现**（`LIVE [] / OLD 1 条`），对照 `PLANT_ABANDONED=False` 3/3 无串写
- [x] 1.3 用注入 `set_sandbox_sink` 调用栈的探针确认：遗留 task 的 `finally`（`loop.py:600`）
      运行在**当前活跃上下文**里（栈里出现 `_run_once → gc.collect`），且把过期 sink 写进活跃上下文
- [x] 1.4 回答三个设计点并留一手实测（`repro/design_points_probe.py`）：
      D1 token 在「从未 set」/「set 过」两种情况均可 reset，二次 reset 抛 `RuntimeError`；
      D2 跨上下文 reset 抛 `ValueError` 与 default 取值无关（`_NOOP` 与 `None` 行为一致）；
      D3 同一遗留终结路径下 `set(prev)` 污染、守护式 reset 不污染
- [x] 1.5 证据脚本归档到 `repro/`（形态 A、形态 B 原版路径适配 + 确定性 GC 窗口变体 + 设计点探针 + README）

## 2. 回归测试（TDD：先红后绿）

- [x] 2.1 新增 `test_abandoned_pending_run_teardown_does_not_clobber_live_sink`
      （`tests/agent/test_loop_sandbox_events.py`）：遗留 pending 子 run（循环已关）+ 活跃带
      `TraceRecorder` 的 run → 活跃 run 内 `gc.collect()` 终结遗留 task → 断言活跃 sink 未被改写、
      其 `emit_sandbox_event("denied", ...)` 落入**自己**的 trace（不丢、不串）
- [x] 2.2 **先跑红**：实现未改前该用例失败，失败形态 = 活跃 recorder 收到 0 条 sandbox 事件
- [x] 2.3 **变异验证**：把 `finally` 改回 `set_sandbox_sink(previous_sandbox_sink)` 后该用例**变红**；
      还原后变绿
- [x] 2.4 补一条「嵌套同上下文恢复」断言：有 recorder 的父 run 内跑一个带 recorder 的子 run，
      子 run 退出后父 run 的后续 sandbox 事件仍落父 trace（锁住 D1 的同上下文分支）

## 3. 实现（sandbox sink 通道）

- [x] 3.1 `agent/sandbox_events.py`：`set_sandbox_sink(sink)` 改为返回 token
      （`_current_sink.set(sink)` 的返回值；类型注解随 `context.py` 约定放宽为 `Any`），
      并更新模块 docstring 的 save/restore 说明（指出应用 token + `reset_*` 而非手工 save/restore）
- [x] 3.2 `agent/sandbox_events.py`：新增 `reset_sandbox_sink(token: Any) -> None`，转发
      `_current_sink.reset(token)`（与 `reset_mode_ceiling` 同形）
- [x] 3.3 `agent/loop.py`：run 起点改 `sink_token = None` / `if trace_recorder: sink_token = set_sandbox_sink(...)`
- [x] 3.4 `agent/loop.py` `finally`：`if sink_token is not None: try: reset_sandbox_sink(sink_token)
      except ValueError: pass`（跨上下文迟后终结时跳过，不污染活跃上下文）
- [x] 3.5 删除不再使用的 `previous_sandbox_sink = current_sandbox_sink()` 行；把 import 收窄为
      `reset_sandbox_sink, set_sandbox_sink`
- [x] 3.6 就地注释说明「为何用 reset 而非 set」并指向 issue #264（与 #261 的注释风格一致）

## 4. 验证

- [x] 4.1 `uv run pytest tests/agent/test_sandbox_events.py tests/agent/test_loop_sandbox_events.py -q`（含新回归）
- [x] 4.2 `uv run pytest tests/agent/test_background.py tests/agent/tools/test_process_backend_cgroup.py tests/agent/tools/test_bash_tool_events.py -q`（`set_sandbox_sink` 既有调用点）
- [x] 4.3 `uv run pytest tests/agent/subagent/ -q`（#261 的同源回归保持绿）
- [x] 4.4 全量 `uv run pytest -q`（记录既有环境坑失败，如与本 change 无关的
      `tests/agent/memory/test_persistent.py::TestFindScopeRoot::*`，根因本机 `/tmp` 是 git 仓库）
- [x] 4.5 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`
      （本 change 触及 `AgentLoop` 路径，按 AGENTS.md 需跑）
- [x] 4.6 复跑 `repro/sandbox_sink_repro.py` 与 `repro/sandbox_sink_misroute_gcwindow.py`：
      实现后两者均应变为**未复现**（退出码 0）——本 change 的收尾证据
- [x] 4.7 OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 4.8 Artifact checker：`uv run python scripts/check_openspec_artifacts.py --base-ref <base>`
- [x] 4.9 **同步 current spec**：把本 change 的 delta 合并进 `openspec/specs/workspace-safety/spec.md`
      （MODIFIED 既有 Requirement「沙箱事件入 trace」+ 新增 Scenario「被遗留 run 的迟后收尾不改变
      活跃 run 的事件归属」）

## 5. 审阅闭环

- [x] 5.1 运行独立审阅闭环（零记忆 subagent），产出 `reviews/building-review.md`
      （verdict 须为 **PASS**；reviewer 应亲自复跑 repro 两个脚本 + 变异验证 + 门禁）
- [x] 5.2 生成 review manifest（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash）；
      **在 tasks.md 最终化之后再生成**

## 6. 文档影响与收尾

- [x] 6.1 文档影响检查：扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与 sandbox 事件 /
      contextvar 恢复相关的段落，只更新本变更造成的事实变化
- [x] 6.2 同步 `docs/openspec-change-backlog.md`（立项登记 → 归档时移除）
- [x] 6.3 受保护路径（backlog、归档目录、当前规格）的修改写 `workflow-events.jsonl` 结构化解释事件
- [x] 6.4 归档到 `openspec/changes/archive/2026-09-29-fix-issue-264-sandbox-sink-context/`
- [ ] 6.5 (post-merge) 关闭关联 issue #264 并加完成说明 comment
