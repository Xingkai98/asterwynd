# Tasks — fix-issue-215-node-failure-evidence

## 立项目标（M3.6 补实现，收窄版）

在 workflow 节点 transcript 载荷里补上**失败证据**投影，把 `run.trace.steps` 里已经存在、
但全仓零出口的失败信号（`status != ok` 的 `tool_result` + `llm_error`）投出来，并用显式状态枚举
区分「没有 trace」与「trace 里没有失败」。

## 实现前设计追问（batch-grill-me）

- [ ] 进入实现前用 `batch-grill-me` / `/grill` 由**独立零记忆 subagent** 追问 `design.md`，逐项确认
      依赖 / 风险 / 测试策略 / 文档影响，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed
      Decisions）
- [ ] grill 产出的 `## Open Questions` **停轮**抛用户确认（每条配真实场景例子），答复写入
      `reviews/grill-design.md` 的 `## User Confirmation`

## 实现

- [ ] `web/session.py`：新增失败证据常量（条目上限 `FAILURE_EVIDENCE_LIMIT`、单条文本复用
      `TRANSCRIPT_CONTENT_LIMIT` 口径），docstring 说明「为什么不是新采集」
- [ ] `web/session.py`：新增 `_failure_evidence(state, run)` 投影函数——**只遍历不复制** trace steps，
      过滤 `tool_result` 的 `status != "ok"` 与全部 `llm_error`；返回 `state` / `total` / `truncated` /
      `message` / `items`
- [ ] `web/session.py`：状态枚举六态落地（`present` / `clean` / `running` / `empty_trace` /
      `no_trace` / `unavailable`），每个负向态配**可读原因文案**，不折叠「无数据」与「无错误」
- [ ] `web/session.py`：条目 bounded——只取**最近** N 条（按 trace 步骤序号），显示顺序为时间正序；
      单条 `observation` / `message` 截断到单条上限并置 `observation_truncated`
- [ ] `web/session.py`：`build_node_transcript_payload` 的**三态分支**（`single` / `candidates` /
      `none`）各挂载 `failure_evidence`；`none` 分支按节点类型取「能否解析到 run」决定是 `unavailable`
      还是「该节点不产生 run」
- [ ] `web/static/workflow.js`：详情抽屉「任务」tab 新增「失败证据」区（位于既有 `drawer-why` 之后），
      渲染状态文案 + 条目（工具名 / 步序 / `status` / `error_type` / observation 摘要）
- [ ] `web/static/style.css`：失败证据区的样式（复用既有 drawer 类，不新增框架/依赖）

## 测试

- [ ] `tests/web_tests/test_workflow_node_transcript.py`：`completed` + trace 含失败步骤 →
      `state == "present"`，条目字段完整（工具名 / 步序 / `status` / `error_type`）
- [ ] trace 有步骤但无失败 → `state == "clean"`（**不是** `no_trace`）
- [ ] run 未到终态 → `state == "running"`（**不是** `no_trace`）
- [ ] 终态 + `trace is None` → `state == "no_trace"`（**不是** `clean`）
- [ ] 终态 + `steps == []` → `state == "empty_trace"`（**不是** `no_trace`、**不是** `clean`）
- [ ] `queue_full`（run 被弹出 `session.runs`）→ `state == "unavailable"`（**不是** `clean`）
- [ ] 失败条目多于 N → 只回最近 N 条、按时间正序、`total` 为真实总数、`truncated is True`
- [ ] 超长 `observation`（用 30000 字，**必须真超上限**）→ 不超过单条上限且
      `observation_truncated is True`（参数教训：输入必须真的超限，否则断言恒真）
- [ ] 大 trace（数百步）→ 响应体积有界（投影不复制全量 steps）
- [ ] 空 `observation` / 缺字段 → 不抛异常、给出可读降级
- [ ] 变异验证：把 `no_trace` 与 `empty_trace` 折叠 / 把 `clean` 当 `no_trace` / 去掉截断标志 /
      改成取**最早** N 条 → 对应测试必须变红 → 还原后变绿
- [ ] 回归：`tests/web_tests/` 全量 + `tests/agent/subagent/` 全量通过（确认加性键不破坏既有 34 条）

## 文档

- [ ] `diagnosis.md`：bugfix 门禁要求的 6 章（已完成，含实测探针输出）
- [ ] spec delta：`specs/web-ui/spec.md`（ADDED「workflow 节点失败证据只读投影」，含 6 个 Scenario）
- [ ] **当前规格同步**：delta 合入 `openspec/specs/web-ui/spec.md`（`current_spec_synced` 事件）
- [ ] 关键词扫描 `docs/`、`README.md`、`CONTEXT.md`、`docs/architecture.md` 中与 workflow 图 /
      节点详情 / 诊断相关的段落，只更新本次变更造成的事实变化
- [ ] `docs/openspec-change-backlog.md` 移除本 change 条目（`backlog_updated` 事件）

## 审阅闭环

- [ ] Round 1 独立 subagent 审阅（`/review-loop`）
- [ ] 按 verdict 修复（CHANGES_REQUESTED 则修复 + 加回归测试再审，最多 3 轮）
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash

## 验证

- [ ] 全量 pytest 通过
- [ ] OpenSpec strict validate 通过
- [ ] project artifact checker 通过
- [ ] benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-215`
- [ ] 端到端验收：用与 `diagnosis.md` 相同形状的 trace 走真实 HTTP 路由，确认失败证据可读出
