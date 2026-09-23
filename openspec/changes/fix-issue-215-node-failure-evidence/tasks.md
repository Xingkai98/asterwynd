# Tasks — fix-issue-215-node-failure-evidence

## 立项目标（M3.6 补实现，收窄版）

在 workflow 节点 transcript 载荷里补上**失败证据**投影，把 `run.trace.steps` 里已经存在、
但全仓零出口的失败信号（`status != ok` 的 `tool_result` + `llm_error`）投出来，并用显式状态枚举
区分「没有 trace」与「trace 里没有失败」。

## 实现前设计追问（batch-grill-me）

- [x] 进入实现前用 `batch-grill-me` / `/grill` 由**独立零记忆 subagent** 追问 `design.md`，逐项确认
      依赖 / 风险 / 测试策略 / 文档影响，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed
      Decisions）—— 2026-09-23 完成，独立 paseo 托管 subagent（plan 模式），6 条 Confirmed Decisions
- [x] grill 产出的 `## Open Questions` **停轮**抛用户确认（每条配真实场景例子），答复写入
      `reviews/grill-design.md` 的 `## User Confirmation` —— 用户已逐项答复 Q1–Q7（含 Q6 计数粒度），
      机械校验 7/7 已确认、0 未确认

### Grill 已确认的结论（2026-09-23，用户全部采纳 grill 推荐）

- [x] Q1 `recovered`：**不加**；区块标题改为事实表述「该 run 已完成（`completed`）；本 run 内出现 N 次工具失败」
- [x] Q2 上限：`FAILURE_EVIDENCE_LIMIT = 5` 保留；载荷单条截 4000；前端预览另设 ~300 字符 + note 标注
- [x] Q3 `clean`：**(b)** 一行淡色「已检查，无失败记录（trace N 步）」；负向态各配一行文案
- [x] Q4 `none` 形态：**扩到七值**，新增 `not_applicable`（route / collect）
- [x] Q5 candidates：每候选只带**轻量**证据；完整证据只在下钻与 `single`
- [x] Q6 前端落点：**方案 D**——「对话」tab 承载证据主体 + 「任务」tab 一行快照计数；**不动** spec 懒加载条款与既有浏览器用例
- [x] Q6 计数粒度：**None/0/N 三态**，`0` 显示淡色「已检查、无失败」，`None` 不显示
- [x] Q7 死代码：**记 `docs/known-debt.md` 一条**（`StopReason.ERROR` 零赋值点 + `no_trace` 无活跃生产者）

## 实现（后端投影）

- [x] `web/session.py`：新增失败证据常量（条目上限 `FAILURE_EVIDENCE_LIMIT = 5`、轻量上限
      `FAILURE_EVIDENCE_PREVIEW_LIMIT = 400`、单条文本复用 `TRANSCRIPT_CONTENT_LIMIT` 口径），
      docstring 说明「为什么不是新采集」
- [x] `web/session.py`：新增 `_failure_evidence(run_or_missing, *, full: bool)` 投影函数——**只遍历不复制**
      trace steps，过滤 `tool_result` 的 `status != "ok"` 与全部 `llm_error`；返回
      `state` / `total` / `truncated` / `message` / `items`
- [x] `web/session.py`：状态枚举**七态**落地（`present` / `clean` / `running` / `empty_trace` /
      `no_trace` / `unavailable` / `not_applicable`），每个负向态配**可读原因文案**，不折叠「无数据」与「无错误」
- [x] `web/session.py`：条目 bounded——只取**最近** N 条（按 trace 步骤序号），显示顺序为时间正序；
      单条 `observation` / `message` 截断到单条上限并置 `text_truncated`（**grill 订正**：不是
      `observation_truncated`）；`llm_error` 条目的 `status` 由投影固定为 `"error"`（trace 里没有这个键）
- [x] `web/session.py`：`build_node_transcript_payload` 的**三态分支**（`single` / `candidates` /
      `none`）各挂载 `failure_evidence`；`none` 分支按 D1 判据表（`state is None` → `unavailable`；
      route / collect → `not_applicable`；未派发 → `unavailable` + 文案）；`candidates` 用**轻量**形态，
      `_item_drilldown_payload` 用**完整**形态
- [x] `web/session.py`：终态判据复用 `:1019-1021` 那份字面量（D7），不新造第四份

## 实现（快照计数，Q6 方案 D）

- [x] `agent/subagent/scheduler.py`：`NodeState` 与 `_ItemRunSlot` 新增有界计数字段（三态 `None`/`0`/`N`）
- [x] `agent/subagent/scheduler.py`：在 `_launch_run` 的 `await self._await_run(...)` 之后**每 run 算一次**
      （普通节点与 foreach 展开项共用这一处埋点）；`queue_full` 早退路径不经过埋点 → 计数保持 `None`
- [x] `agent/subagent/scheduler.py`：`_graph_node_projection` 投影该字段

## 实现（前端）

- [x] `web/static/workflow_transcript.js`：「对话」tab 新增失败证据区——在 `paint()` 里三形态共用挂载点
      （`single` 置于消息体之前；`candidates` 每行只显示计数线索；`none` 按取值显示/不显示）
- [x] `web/static/workflow_graph.js`：新增「`state` → 文案」与「条目 → 一行摘要」**纯函数**（供 node+vm 测试锁定）
- [x] `web/static/workflow.js`：详情抽屉「任务」tab 的 `drawer-why` 之后加**一行快照计数线索**
      （`0` 淡色「已检查、无失败」/ `N>0` 「⚠ 本 run 内 N 次工具失败 →『对话』tab 查看」/ `None` 不显示）
- [x] `web/static/style.css`：失败证据区样式（复用既有 drawer 类，不新增框架/依赖）

## 测试

- [x] `tests/web_tests/test_workflow_node_transcript.py`：`completed` + trace 含失败步骤 →
      `state == "present"`，条目字段完整（工具名 / 步序 / `status` / `error_type`）
- [x] trace 有步骤但无失败 → `state == "clean"`（**不是** `no_trace`）
- [x] run 未到终态 → `state == "running"`（**不是** `no_trace`）
- [x] 终态 + `trace is None` → `state == "no_trace"`（**不是** `clean`）
- [x] 终态 + `steps == []` → `state == "empty_trace"`（**不是** `no_trace`、**不是** `clean`）
- [x] `queue_full`（run 被弹出 `session.runs`）→ `state == "unavailable"`（**不是** `clean`）；
      用例注释写明「生产路径在 workflow 内预期 0 次」，构造方式是半合成的
- [x] route 节点 / collect 聚合 → `state == "not_applicable"`（**不是** `unavailable`）
- [x] 未派发节点 → `state == "unavailable"` + 「尚未派发」文案
- [x] `llm_error` 条目 → `status == "error"`（投影合成）、`tool_name is None`、文本在 `message`
- [x] 失败条目多于 N → 只回最近 N 条、按时间正序、`total` 为真实总数、`truncated is True`
- [x] 超长 `observation`（用 30000 字，**必须真超上限**）→ 不超过单条上限且 `text_truncated is True`
      （参数教训：输入必须真的超限，否则断言恒真）
- [x] **体积有界**（grill 指定的断言形状）：300 步全失败 × 每条 30000 字的 trace →
      `len(items) <= N`、`sum(len(observation)+len(message)) <= N * content_limit`、`total == 300`、
      `truncated is True`（**不得**写成整包长度比较）
- [x] 三态挂载各有用例：`candidates` 每候选各带**轻量**证据（≤1 条 × ≤400 字符）；`_item_drilldown_payload`
      顶层带**完整**证据；`none` 形态的取值与文案
- [x] 快照计数：终态 run 有 N 条失败 → 快照节点带 `N`；零失败 → `0`；无 trace / 未派发 → `None`
- [x] `tests/web_tests/test_workflow_graph_ux_js.py`：前端「七态 → 文案」纯函数映射（node+vm harness）
- [x] 空 `observation` / 缺字段 → 不抛异常、给出可读降级
- [x] 既有 34 条 transcript 用例 + 既有浏览器懒加载用例（`test_workflow_graph_browser.py`）不因新增键变红
- [x] 变异验证：把 `no_trace` 与 `empty_trace` 折叠 / 把 `clean` 当 `no_trace` / 把 `not_applicable` 当
      `unavailable` / 去掉截断标志 / 改成取**最早** N 条 / `llm_error` 的 `status` 不合成 → 对应测试必须变红
      → 还原后变绿
- [x] 回归：`tests/web_tests/` 全量 + `tests/agent/subagent/` 全量通过

## 文档

- [ ] `diagnosis.md`：bugfix 门禁要求的 6 章（已完成，含实测探针输出）
- [ ] **当前规格同步**：delta 合入 `openspec/specs/web-ui/spec.md`（`current_spec_synced` 事件）
- [ ] **快照加法字段**：`openspec/specs/web-ui/spec.md` 的 workflow 图快照 requirement 加法字段清单
      ADDED 一项（Q6 方案 D 的计数）
- [ ] 关键词扫描 `docs/`、`README.md`、`CONTEXT.md`、`docs/architecture.md` 中与 workflow 图 /
      节点详情 / 诊断相关的段落（**grill 点名 `docs/architecture.md:105` 的返回形态描述已不完整**），
      只更新本次变更造成的事实变化
- [ ] `docs/known-debt.md`：记两条死代码发现（`StopReason.ERROR` 零赋值点 + `no_trace` 无活跃生产者），
      标注「本 change 显式不做」（受保护路径，走 `artifact-event` 事件通道）
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

## 收尾（post-merge 之外的最后一步）

- [ ] 归档 change 到 `openspec/changes/archive/2026-09-23-fix-issue-215-node-failure-evidence/`
- [ ] 给 issue #215 添加完成说明 comment 并关闭（post-merge）
