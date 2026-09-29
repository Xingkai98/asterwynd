# Tasks: 挂载 A 改守护式 reset，修跨上下文收尾清空 mode 上限（fix-issue-261-mode-ceiling-flake）

> 关联 issue：[#261](https://github.com/Xingkai98/asterwynd/issues/261)。
> 本 change 为**生产代码 bugfix**（非测试侧）；根因与证据见 `diagnosis.md`，方案见 `proposal.md`。
>
> **机制已由用户确认钉死**（最小脚本 + 真实代码路径确定性复现；对照实验证明只有
> 「循环已关 + GC 终结」才污染），故本 change 直接进入实现，不再走 grill（bugfix 且
> 设计空间已被 `fix-issue-255` 锁定；grill 门槛见 AGENTS.md 的「设计追问」，非平凡
> change 才强制）。

## 1. 根因定位（诊断先行）

- [x] 1.1 复现 CI 失败：并发跑 `tests/agent/subagent/` 全目录，命中与 CI 完全一致的
      `AssertionError: assert 'build' == 'read_only'` + `Task was destroyed but it is pending!`
- [x] 1.2 否证 issue 的测试侧假设：延迟注入到 run 体与 mode 冻结点，测试**仍通过且变慢**
      ⇒ 断言点已等待 mode 冻结
- [x] 1.3 钉死机制：遗留 pending task 的循环关闭后被 GC 终结，协程 finalize 在当前上下文
      执行 `finally`（含挂载 A 的恢复），把活跃上限清成 `None`
- [x] 1.4 对照实验证明判别条件：`cancel()`（task 自身上下文）不污染；只有「循环已关 +
      GC 终结」污染——解释早期最小探针为何未复现
- [x] 1.5 产出最小确定性复现脚本 + 真实代码路径脚本（`repro/min_repro_261.py`、
      `repro/realpath_ab.py`），A/B 记录（现状 5/5 REPRODUCED → 修法 5/5 CLEAN）

## 2. 回归测试（TDD：先红后绿）

- [x] 2.1 新增 `test_abandoned_pending_run_teardown_does_not_clobber_live_ceiling`：
      遗留 pending run（循环已关）+ 活跃只读 run → 活跃 run 期间 GC 终结遗留 task
- [x] 2.2 **先跑红**：实现未改前该用例失败，且失败形态与 CI 一致（`assert 'build' == 'read_only'`）
- [x] 2.3 **变异验证**：把实现改回 `set_mode_ceiling(previous_ceiling)` 后该用例**变红**；
      还原后变绿

## 3. 实现（挂载 A）

- [x] 3.1 `AgentLoop.run` 起点：`ceiling_token = set_mode_ceiling(self.runtime_state.current_mode)`
- [x] 3.2 `finally`：`try: reset_mode_ceiling(ceiling_token) except ValueError: pass`
      （跨上下文迟后终结时跳过，不污染活跃上下文）
- [x] 3.3 删除不再使用的 `previous_ceiling = current_mode_ceiling()`；把 import 收窄为
      `reset_mode_ceiling, set_mode_ceiling`
- [x] 3.4 就地注释说明「为何用 reset 而非 set」（指向 issue #261 的机制）

## 4. `set_sandbox_sink` 同源隐患调查（本 change 不修）

- [x] 4.1 写复现脚本 `repro/sandbox_sink_repro.py`（形态 A：sink 被清成 `_NOOP`，事件静默丢失）
- [x] 4.2 写复现脚本 `repro/sandbox_sink_misroute.py`（形态 B：事件串写进旧 run 的 trace），
      并加 `PLANT_ABANDONED=False` 对照证明归因
- [x] 4.3 结论：**能复现且可观测**（实证缺陷，非理论隐患）；建议**单独立项**
- [x] 4.4 在 `diagnosis.md` 记录结论与修复建议；**不**在本 change 改 `set_sandbox_sink`

## 5. 验证

- [x] 5.1 `uv run pytest tests/agent/subagent/test_mode_ceiling.py -q`（含新回归）
- [x] 5.2 `uv run pytest tests/agent/subagent/ -q` 全目录
- [x] 5.3 全量 `uv run pytest -q`（记录既有环境坑失败，如与本 change 无关的
      `TestFindScopeRoot`，根因 `/tmp/.git` 为空目录）
- [x] 5.4 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`
      （本 change 触及 `AgentLoop` 路径，按 AGENTS.md 需跑）
- [x] 5.5 OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 5.6 Artifact checker：`uv run python scripts/check_openspec_artifacts.py --base-ref ee06df7`
- [x] 5.7 **同步 current spec**：把本 change 的 delta 合并进 `openspec/specs/subagents/spec.md`
      （MODIFIED 既有 Requirement「子 agent mode 上限按执行上下文继承」+ 新增 Scenario
      「被遗留 run 的迟后收尾不改变活跃 run 的上限」）

## 6. 审阅闭环

- [x] 6.1 运行独立审阅闭环（零记忆 subagent），产出 `reviews/building-review.md`
      （**verdict = PASS**，1 轮收敛；reviewer 亲自复跑最小复现/真实路径 A/B/变异验证/门禁；
      2 条非阻塞 follow-up 见该报告 `## Issues`）
- [x] 6.2 生成 review manifest（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash）；
      **在 tasks.md 最终化之后再生成**

## 7. 文档影响与收尾

- [x] 7.1 文档影响检查：扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与
      mode 上限 / sandbox sink 相关的段落，只更新本变更造成的事实变化
      （结论：无需更新——`docs/known-debt.md` 的 mode 条目描述的是另一条不受影响的残留）
- [x] 7.2 同步 `docs/openspec-change-backlog.md`（立项登记 → 归档时移除）
- [x] 7.3 受保护路径（backlog、归档目录、当前规格）的修改写 `workflow-events.jsonl` 结构化解释事件
- [x] 7.4 归档到 `openspec/changes/archive/2026-09-29-fix-issue-261-mode-ceiling-flake/`
- [ ] 7.5 (post-merge) 关闭关联 issue #261 并加完成说明 comment（含「issue 正文的测试侧
      判断已被否证」的订正说明）
- [ ] 7.6 (post-merge) 为审阅报告 `## Issues` 1 开的 follow-up issue：`set_sandbox_sink`
      跨上下文收尾污染（已知悉，独立载体、本 change 未修）——由主 session 决定是否开单
