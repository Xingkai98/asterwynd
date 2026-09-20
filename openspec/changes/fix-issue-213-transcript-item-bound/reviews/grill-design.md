# Design Grilling: 模型面出现的子 agent 文本一律 bounded（fix-issue-213-transcript-item-bound）

我是**独立设计评审者**，零记忆：本会话未读过任何先前对话、开发计划或推理过程。下面每条结论
只来自 (a) 本 change 的 OpenSpec 文档、(b) issue #213 原文、(c) 仓库当前代码与测试的**实跑输出**，
(d) 我在 `/tmp/grill_213/` 写的探针。所有「design 声称 X」都逐条对代码验证过；未验证的写进
Open Questions。

审阅方法的核心是**把 design 的决策按字面实现一遍再跑既有测试**（`/tmp/grill_213/grill_patch.py`
是一个 pytest 插件，monkeypatch 掉 `_bounded_summary` / `to_result_dict` / `_format_run_envelope` /
`_bounded_arguments` / `_worker_entry`，仓库文件零改动）。这比读 design 的自我描述更能暴露
「默认值翻转打破哪些调用点」——实跑结果见 Confirmed Decisions 第 2、3 条。

## Reviewer

- run id: `grill-fix-issue-213-2026-09-21-001`
- 时间: 2026-09-21
- 审阅对象:
  - `openspec/changes/fix-issue-213-transcript-item-bound/{proposal,design,diagnosis,tasks}.md`
  - `openspec/changes/fix-issue-213-transcript-item-bound/specs/{subagents,agent-runtime}/spec.md`
  - `agent/subagent/manager.py`（`_bounded_summary` / `TOOL_CALL_ARGUMENT_LIMIT` / `_bounded_arguments` /
    `_project_tool_calls` / `to_result_dict` / `inspect_transcript` / `_write_result_artifacts` /
    `_format_run_envelope` 及其 7 处调用点）
  - `agent/subagent/scheduler.py`（`:2108` `/` `:2169` `/` `:1700` `/` `:2260`）
  - `agent/subagent/patterns.py`（`_worker_entry` / `_legacy_result` / `_worker_budget`）
  - `agent/subagent/bus.py`（`publish` / `read` / `snapshot_payload`）
  - `agent/tools/builtin/subagents.py`（16 个工具类全查）
  - `web/session.py`（`TRANSCRIPT_CONTENT_LIMIT` / `_bounded_messages` / 两条 `inspect_transcript` 路由）
  - `web/static/workflow_transcript.js`
  - 既有测试：`tests/agent/subagent/**`、`tests/web_tests/test_workflow_node_transcript.py`
- 基线: `b10f4bb`（分支 `fix-issue-213-transcript-item-bound/2026-09-21`，工作区 clean）
- 审阅方法（实跑命令，摘要；完整清单见文末「实跑命令」）:
  - `uv run pytest -q tests/agent/subagent/test_result_representations.py tests/agent/subagent/test_workflow_result_refs.py tests/web_tests/test_workflow_node_transcript.py -p no:randomly` → `32 passed`（基线绿）
  - `PYTHONPATH=/tmp/grill_213 GRILL_SCHEDULER_FULL={0,1} uv run pytest -q -p grill_patch -p no:randomly tests/agent/subagent/ tests/web_tests/test_workflow_node_transcript.py` → 模拟 design 全量落地
  - `PYTHONPATH=. uv run python3 - <<'PY'` 直接调 `inspect_transcript` / `to_result_dict` / `_bounded_summary` 复现 4 出口无界
  - `/tmp/grill_213/probe_d.py`（`_write_result_artifacts` 赋值顺序静态核验）
  - `/tmp/grill_213/probe_runpattern_budget.py`（`RunPattern` 预算放大实测）
  - `/tmp/grill_213/test_probe_or.py`（D7 取或的判别力实测）
  - `PYTHONPATH=. uv run python3 -c "from agent.subagent.workflow import parse_workflow_spec; ..."`（model 自撰 spec 的 `max_tokens` 放大实测）
  - `grep -rn` 全仓扫描常量 / 出口 / bus / 工具类引用（含 `web/`、`benchmarks/`、`docs/`、`web/static/*.js`）

## Confirmed Decisions

- **决策**: **D1（截断只在出口、记录层保持全文）成立**——但 `design.md:22-24` 的证据引用必须改正，且本
  change 的测试改造清单漏了一条必改测试。`run.summary` 保留全文有**代码层**依据而不只是「两条测试」：
  `scheduler.py:2260` 的 `_merge_contributions_bounded` 用 `len(merged) <= budget * CHARS_PER_TOKEN`
  决定是否调 summarizer 压缩；若 `run.summary` 在记录层被截短，拼接结果会**静默低于**预算阈值而
  **跳过压缩**，下游聚合质量无声下降（不报错、不告警）。真有测试钉死记录层全文的是
  `test_result_representations.py:90`（`run_a.summary == LONG`）、`test_workflow_result_refs.py:101`、
  `:148` 三条（design 说「两条」，方向对但计数不准）；而 `design.md:23` 举的
  `run_envelope["summary"] == LONG`（`test_result_representations.py:84`）断言的是 **envelope** 而非
  `run.summary`——它**恰恰会被 D2 打破**（见下一条），不是 D1 的证据。**必改**：把
  `tests/agent/subagent/test_result_representations.py:84` 列入本 change 的「测试影响」，
  改为断言「`run.summary` 全文 / `envelope["summary"]` bounded / `bounded_summary` 与之同值」。
  ；理由: 实跑 `PYTHONPATH=/tmp/grill_213 GRILL_SCHEDULER_FULL=1 uv run pytest -q -p grill_patch
  tests/agent/subagent/test_result_representations.py::test_three_representations_are_distinct`
  → `AssertionError: assert 'FULL-RESULT-...n result_ref]' == 'FULL-RESULT-...-FULL-RESULT-'`（第 84 行），
  而 `test_run_summary_keeps_full_text`（第 90 行那条）在同一次运行中**通过**——证明「被打破的是
  envelope 断言、不是记录层断言」；来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **D2（`_format_run_envelope` 默认 bounded + 调度器显式要全量）成立且必需**，但调度器侧的
  精确落点是 `scheduler.py:2169` 的 `_await_run` **一处**，design 说「1 处」正确；须同时确认
  `scheduler.py:2108` 的 `manager.run_subagent(...)` 返回值（经 `manager.py:707` 的
  `_format_run_envelope`）虽然也会被默认 bounded，但该返回值只被消费 `run_id` / `status` / `reason`
  （`scheduler.py:2118-2145`），`summary` 字段无人读——**不构成功能 bug**。实跑反证：不加
  `full_summary=True` 时，`tests/agent/subagent/test_workflow_aggregator.py::test_collect_aggregate_compresses_through_the_summarizer`
  变红（`assert fake.calls` 为空：root 的 `state.summary` 被截到 2000 字后
  `_merge_contributions_bounded` 认为没超预算、直接跳过 summarizer），加上后恢复绿。
  ；理由: 见上两条实跑（同一命令的 `GRILL_SCHEDULER_FULL=0` / `=1` 对照：0 → `2 failed, 539 passed`；
  1 → `1 failed, 540 passed`，唯一剩下的失败就是上一条的 `:84`）；来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **D3（出口 2/3/4 复用 `bounded_summary` 的值、不引入新常量）不成立，必须改**。
  `bounded_summary` 的预算 `max(BOUNDED_SUMMARY_CHARS, max_tokens * 4)`（`manager.py:52-59`）里的
  `max_tokens` 是 **run 预算**，而 run 预算在两条模型可达的路径上都**没有上限校验**：
  (a) `RunPatternTool` 的 `params.worker_max_tokens`（`subagents.py:394-406` 的 params 是无约束
  `object`）→ `_worker_budget`（`patterns.py:65-77`）→ `WorkflowNode.max_tokens` → `run.max_tokens`；
  (b) `DeclareWorkflow`/`RunWorkflow` 的 `spec.nodes[].max_tokens` → `_parse_node_max_tokens`
  （`workflow.py:601-604`）→ `_positive_int`（`workflow.py:451-454`）只校验「正整数」，**无上界**。
  实测：`worker_max_tokens=50000` → 单 worker 在模型面的 summary 上限 **200,000 字符**；
  `spec` 里 `max_tokens=500000` → 上限 **2,000,000 字符**。也就是说 D3 给出的不是「界」，是**调用方
  可调的旋钮**——本 change 的标题「模型面子 agent 文本**一律** bounded」在出口 2/3/4 上不成立，
  只有 `max_tokens is None`（→ 2000）时才成立。**必改**，二选一：①给出口 2/3/4 一个**独立于 run 预算
  的硬上限**（可等于 `TRANSCRIPT_ITEM_LIMIT`），②对 `max_tokens` 加显式上限校验（`_positive_int`
  加 `maximum`）。design 选 D3 的理由是「避免出现第三个数」，但代价是把界交出去——这个取舍
  需要用户拍板（见 Open Question 1）。；理由: `probe_runpattern_budget.py` 输出
  `worker_max_tokens=50000 → node.max_tokens=50000 → bounded 预算=200000`；`parse_workflow_spec`
  实测 `max_tokens=500000 → 单 run 在模型面的 summary 上限 = 2,000,000 字符`；
  来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **D4（修 `_bounded_summary` 的假话）方向成立，但「两个调用点都能判」的实现方案会引入
  新的信息损失**。落盘路径 `manager.py:1308` 的 `_bounded_summary(...)` 调用发生在
  `run.result_ref = result_ref`（`:1311`）**之前**——若照 design 字面「读 `self.result_ref`/`self.summary_ref`」，
  此刻两者都是 `None`，落盘件会**永远**只说「已截断」而不给导航，恰好与 D4「有 ref 时告诉读者全文在哪」
  的意图相反。**必改**：落盘路径必须**显式传**「ref 必然存在」（该分支已 `save_result` 成功，
  `manager.py:1301`），不能读属性。另：D4 写「两个调用点都能判」，但 **D9 落地后调用点是三个**
  （`to_result_dict` / `_write_result_artifacts` / `patterns._worker_entry`）——第三个的 `has_ref`
  语义必须在 design 里显式定义，否则它会落到默认值上（安全但丢导航）。
  ；理由: `probe_d.py` 静态核验输出 `_bounded_summary 调用行: 1308` / `run.result_ref/summary_ref 赋值行: [1311, 1313]`
  / `调用发生在赋值之前? True`；实跑确认落盘件与 `to_result_dict` 的 bounded 尾部当前都是
  `'\n…[truncated; full result in result_ref]'`；来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **D5（常量改名 `TRANSCRIPT_ITEM_LIMIT` + `TOOL_CALL_ARGUMENT_LIMIT` 保留 alias）成立，
  不产生「半改半不改」分叉**。全仓 `TOOL_CALL_ARGUMENT_LIMIT` 引用共 4 处代码（`manager.py:64` 定义、
  `:75`、`:77`、`:88` 注释）+ 1 处 docstring（`web/session.py:749`）+ 6 处测试
  （`tests/web_tests/test_workflow_node_transcript.py:559,570,618,624,650,661,669,672`）——alias 一行全覆盖。
  `tests/web_tests/test_workflow_node_transcript.py:624` 现有的
  `assert TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT` 升级为三处同值后**仍是有效断言**
  （alias 被拆开、或 `TRANSCRIPT_ITEM_LIMIT` 与 `TRANSCRIPT_CONTENT_LIMIT` 漂移都会变红），不是恒真。
  **但**：`TRANSCRIPT_ITEM_LIMIT` 的 docstring **不得**声称它约束 `summary`（见 Open Question 7）——
  出口 2/3/4 的 `summary` 由 run 预算决定，不受这个常量管；若照 tasks.md:5-6 的字面写「约束
  arguments/content/summary 三处」，就是**用新名字说同一句旧谎**（旧名的病是名字与职责不符，
  新名会把病搬到 docstring）。；理由: `grep -rn "TOOL_CALL_ARGUMENT_LIMIT" .`（排除 `.codegraph`/`.git`）
  的完整命中清单见上；来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **D7（HTTP 层 `content_truncated` 取或 + 显式透传）成立，且有判别力**——但**只在
  「上游已截、本层预算更宽」的构造下**才有判别力，测试必须按这个构造写。实测：生产者输出
  `content_truncated=True` 且 content 已被截到 4000，路由 `content_limit=8000` 时，取或实现报 `True`、
  「只看本层长度」的变异报 `False` → 断言 `is True` 能让变异变红。反例：若把 `content_limit` 设成
  **小于**生产者上限（如 100），真实现与变异**同值**（都报 True），判别失效——即 design 的「变异验证」
  任务必须用宽松预算（`> TRANSCRIPT_ITEM_LIMIT`）构造，与既有
  `test_truncation_flag_composes_across_producer_and_route`（`:655-673`）的写法一致。
  **注意**：D7 的实现前提是**生产者先截 content 并回流 `content_truncated`**；若同一 change 里漏了
  出口 1 的 `content_truncated` 回流，取或的 `bool(message.get("content_truncated"))` 恒为 False，
  退化成只看本层——D1/D7 有隐含的落地顺序依赖。；理由:
  `/tmp/grill_213/test_probe_or.py` 输出：`[真实现 取或] content_truncated = True` /
  `[变异 只看本层] content_truncated = False` / `✅ 判别成立`；反例段输出「content_limit=100: 真实现=True, 变异=True ← 同值，无法判别」；
  来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **出口清单不完整——本仓库存在第 5 个模型面出口：message bus（两处）**，design 的
  Non-Goals「不动 bus……已有各自的 bounded 口径」与代码不符。`ReadBus` 工具
  （`subagents.py:313-345` → `bus.read`）在 `agent/subagent/bus.py:122-127` 有一条
  「单条超窗仍返回最新一条」的规则，实测一条 30,000 字的消息**原样返回 30,000 字符**；
  `RunPatternTool` 的返回值里 `patterns.py:438` 有 `result["bus"] = bus.snapshot_payload()`，
  而 `snapshot_payload`（`bus.py:143-147`）**既无条数上限也无单条上限**，实测 100 条 ×1600 字
  → **173,303 字符**全部进模型上下文。发布侧 `PublishBusMessageTool`（`subagents.py:262-267`）只在
  `estimate_tokens(content) > max_tokens` 时才 summarize，而 `max_tokens` 由调用方给、**无最大值约束**。
  这两处返回的都是**子 agent 撰写的内容**，落在本 change 标题「模型面子 agent 文本一律 bounded」
  的字面范围内。**处置需用户拍板**（见 Open Question 2）：纳入本 change，还是在 Non-Goals 里
  如实写明「bus 出口本次不覆盖，另开 issue」，而不是声称它已经 bounded。
  ；理由: 实跑 `bus.publish(summary="字"*30000)` → `bus.read()` 返回 `30000` 字符；
  `bus.snapshot_payload()` 100 条 → `173303` 字符；`grep -rn "bus.publish\|snapshot_payload"` 全仓确认唯一
  模型面路径是 `patterns.py:438`；来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **D9（`RunPattern` worker summary 走 bounded）方向成立**，`_worker_entry`
  （`patterns.py:333-354`，`summary` 在 `:345`）确实把 `run.summary` 全文塞进 worker dict，
  `_legacy_result` 再拼成长文本（`patterns.py:369-372`）。实跑既有 pattern 测试**无回归**
  （`tests/agent/subagent/test_patterns.py` + `test_pattern_templates.py` + `test_bounded_envelope.py`
  在 D9 模拟下 `37 passed`）——没有测试断言 worker summary 全文（`test_pattern_templates.py:185`
  只断言 `result["summary"]` 非空、`:242` 断言 `"reached max review rounds" not in worker["summary"]`，
  两者对 bounded 都不敏感）。**但 D9 继承决策 3 的缺陷**：用 `run.max_tokens` 定预算意味着
  `worker_max_tokens` 越大、每个 worker 在模型面能返回的文本越多，N 个 worker 的放大倍数仍由
  调用方控制。；理由: 见决策 3 的实测；pattern 测试实跑见
  `PYTHONPATH=/tmp/grill_213 GRILL_SCHEDULER_FULL=1 uv run pytest -q -p grill_patch ... test_patterns.py test_pattern_templates.py test_bounded_envelope.py` → `37 passed`；
  来源: grill-fix-issue-213-2026-09-21-001

- **决策**: **前端 `web/static/workflow_transcript.js` 不存在独立的放大路径**，design 未提及它是
  正确的。该文件只渲染 HTTP 路由给它的 `message.content`（`:301`）、`payload.summary`（`:214-216`）、
  `content_limit`（`:141-143`）与 `arguments_truncated`（`:353`），**不做二次放大**；两条
  `inspect_transcript` 路由（`web/session.py:856`、`:991`）都过 `_bounded_messages`，是仅有的两条。
  「4 个出口」中的出口 1/2/3/4 确实都经 `json.dumps` 进模型上下文——这一点 design 的清单是准的。
  ；理由: `grep -rn "content_truncated\|content_limit\|truncated" web/static/workflow_transcript.js`；
  `grep -n "_bounded_messages(\|inspect_transcript(" web/session.py` → 恰好 2 条路由、2 次 `_bounded_messages`；
  来源: grill-fix-issue-213-2026-09-21-001

## Open Questions

- **Q1（最关键）：出口 2/3/4 的「界」由谁定？** 实测：`RunPattern(params={"workers":1,"worker_max_tokens":50000})`
  时，单个 worker 在模型面的 summary 上限是 **200,000 字符**；`RunWorkflow(spec=...)` 里
  `nodes[0].max_tokens=500000` 时上限是 **2,000,000 字符**——两者都由**模型自己**在工具参数里写。
  具体场景对比（同一份 30,000 字子 agent 输出，走 `GetSubagentRun`）：
  - 现状（不改）：返回 **30,000 字符**，无截断标记。
  - 按 design D3 落地：`max_tokens=None` 时返回 **2,040 字符**（✅ 真的 bounded 了）；
    `max_tokens=50000` 时返回 **30,000 字符**（❌ 与现状**完全一样**，因为 200,000 预算 > 30,000）。
  → 也就是说：**同一份输出、同一个工具，是否被 bounded 取决于调用方给不给、给多大 `max_tokens`**。
  请拍板选哪条路：
  - (a) 出口加**独立于 run 预算的硬上限**（例如 4000，与 `TRANSCRIPT_ITEM_LIMIT` 同值）——
    界不可被调用方放大，代价是模型面出现「第三个数」，且大 `max_tokens` 的 workflow 节点在看到
    自己产出的摘要时会被裁得更狠；
  - (b) 保留 D3 的「随 run 预算」口径，但**对 `max_tokens` 加显式上界校验**
    （`workflow.py:451` 的 `_positive_int` 加 `maximum`、`RunPatternTool` 的 params 加 schema 约束）
    —— 保住「一个概念一个数」，但界仍等于「最大允许预算 × 4」，需要一并定这个最大值是多少；
  - (c) 接受现状，在 spec / Non-Goals 里如实写明「run envelope 的 summary 上限 = run 摘要预算」，
    并把「预算由调用方控制」记为已知边界（则本 change 不能声称「一律 bounded」）。

- **Q2：bus（`ReadBus` + `RunPattern` 的 `result["bus"]`）是否纳入本 change？** 具体场景：
  一个 workflow 里 100 个 worker 各调一次 `PublishBusMessage(sender=..., topic="finding", content=<1600 字>)`，
  随后父 agent 调 `RunPattern(pattern="orchestrator-worker", task=...)`——实测返回体里
  `result["bus"]` 一项就是 **173,303 字符**，全部进父 agent 上下文；若某个 worker 直接发 30,000 字
  （`max_tokens` 给足），`ReadBus` 会把这一条**原样**返回 30,000 字符。design 的 Non-Goals 写
  「已有各自的 bounded 口径」——实测**不成立**（只有 `compact_summary(max_chars=2000)` 有界，但它
  只被 `manager.py:1427` 用于**会话恢复注入**，不是 `ReadBus`/`RunPattern` 的路径）。请拍板：
  - (a) 本次一并纳管（`snapshot_payload` 加条数/单条上限，或在 `ReadBus`/`RunPattern` 出口过
    `_clip`）——范围变大，但 change 标题「一律 bounded」才立得住；
  - (b) 本次不纳管，但把 Non-Goals 的措辞从「已有各自的 bounded 口径」改成如实描述
    （「bus 出口本次不覆盖，实测无界，另开 issue 跟踪」）——保证文档不说假话，是本仓库的硬要求。

- **Q3：`RunPattern` 的 worker summary 上限取哪个？**（design 自己的 Open Question 2，我给出了实测依据）
  具体场景：`RunPattern(pattern="orchestrator-worker", params={"workers": 3, "worker_max_tokens": 5000})`，
  三个 worker 各产出 30,000 字。取 `bounded_summary`（随 `max_tokens`）时每个 worker 返回约
  两万字符、三个合计约六万字符；取固定 4000 时合计约一万二千字符。前者与出口 2/3 口径一致
  但**放大倍数仍由 `worker_max_tokens` 控**；后者与出口 1（inspect）一致但引入「同叫 summary、
  两个数」。请拍板取哪个。

- **Q4：`_bounded_summary` 新增的「ref 存在」参数，第三个调用点（`patterns._worker_entry`）传什么？**
  具体场景：一个在 workflow 里跑完的 worker，`run.result_ref` 确实存在（`_write_result_artifacts`
  成功落盘），其 summary 被 `_worker_entry` 截断。传 `has_ref=True` → worker 条目会写
  「全文在 result_ref」，但 `_worker_entry` 返回的 dict **并不含** `result_ref` 字段本身
  （`patterns.py:342-354` 只有 `subagent_id`/`status`/`summary`/`reason`/`usage`）——模型看到
  「全文在 result_ref」却**拿不到这个 ref**，等于在出口 4 复制了本 change 正要消灭的那句假话。
  传 `has_ref=False` → 只写「已截断」，安全但丢导航。请拍板：(a) `_worker_entry` 补上 `result_ref`
  字段再传 `True`；(b) 传 `False`，只保留「已截断」；(c) 其他。

- **Q5：`GetSubagentRun` 的 `summary` 变 bounded 后，要不要给「全文长度」提示？**（design 自己的
  Open Question 1）具体场景：子 agent 产出 30,000 字，`GetSubagentRun` 返回 2,040 字 + `summary_ref`。
  模型现在的选择是 (i) 只读这 2,040 字就下判断，或 (ii) 先 `ReadWorkflowResult(ref, offset=0, limit=4000)`
  翻页读完。若返回体只给一个 `summary_truncated: true` 布尔，模型**不知道被裁掉了 28,000 字**，
  可能误判「这就是全部」；若附带 `summary_chars: 30000` / `truncated_chars: 27960`，模型能判断
  值不值得翻页。请拍板：只给布尔，还是补长度元数据（补的话，这次补到什么粒度）。

- **Q6：UI 上要不要提示 content 被截断？**（design 自己的 Open Question 3）具体场景：用户在 web
  「workflow 节点 transcript」抽屉里看某个子 agent 的消息。改前：`arguments` 被截时该轮显示
  「（参数已截断）」（`workflow_transcript.js:353`），`content` 不截所以不需要提示。改后：
  `content` 超过 4000 字会被截，但 UI **没有任何提示**，用户看到的是一段**读着通顺、实则中断**的文本
  （截断处没有省略号，因为 `_bounded_messages` 是 `content[:content_limit]` 裸切）。
  请拍板：(a) 本次一并补 UI 提示（对称于 `arguments_truncated`），(b) 记为有意边界、另开 issue，
  (c) 在 design 的「明确不做」里写清理由。

- **Q7：`TRANSCRIPT_ITEM_LIMIT` 的 docstring 该怎么写？** 具体场景（tasks.md:5-6 的字面实现）：
  常量定义为「约束 `arguments` / `content` / `summary` 三处」。但 `inspect_transcript` 的
  `summary` 分支（出口 1）用 4000，而 `GetSubagentRun` 的 `summary`（出口 2）用 run 预算——
  同一个字段名 `summary` 在两条模型面路径上**是两个数**。若 docstring 写「约束 summary」，
  读者会以为出口 2 也受 4000 管，**这是新的名字说谎**（旧名的病是名字窄于职责，新名会变成
  docstring 宽于职责）。请拍板 docstring 的准确措辞，例如是否写成
  「约束**模型面消息投影**的 `arguments`/`content`，以及 inspect 出口的 `summary`」。

## 风险

- **风险（高）：D3 的「界」可被模型自己放大**（决策 3 / Q1）。这是本次审阅最重要的新发现：
  本 change 的核心承诺是「模型面子 agent 文本一律 bounded」，但按 design 字面落地后，出口 2/3/4
  的上限是 `max(2000, max_tokens*4)`，而 `max_tokens` 经 `RunPatternTool.params.worker_max_tokens`
  和 `WorkflowNode.max_tokens` 两条路径由**发起调用的模型**设定，两处都无上界校验
  （`workflow.py:451-454` 只校验正整数）。**按现状落地，issue #213 的场景在用大 `max_tokens` 时
  不会被修复**，而且是静默的——测试若只用默认 `max_tokens=None` 构造，会全绿通过。

- **风险（中）：D4 的落盘路径若照字面「读属性」会生产新的信息损失**（决策 4）。`manager.py:1308`
  的调用早于 `:1311-1313` 的赋值，读属性恒为 `None`。这是**顺序陷阱**：写测试时若只断言
  `result_ref is None` 的场景，会漏掉「有 ref 时落盘件仍需导航」的回归。

- **风险（中）：`specs/subagents/spec.md` 的「SHALL NOT 依赖调用方用长度比较自行推断」不可机械验证**
  （见「spec delta 可验证性」段）。这条措辞要求「标志存在且被使用」，但任何确定性测试能断言的只有
  「标志值正确」——「调用方没有用长度比较推断」是**对调用方行为的约束**，本仓库的测试无法证伪。
  建议把该句的**可测内核**（标志必须随文本回流、跨层取或）写成独立 Scenario，把「不自推断」
  降为 rationale 而非 SHALL 断言。

- **风险（中）：D7 的落地顺序依赖**（decision 7）。取或的左侧
  `bool(message.get("content_truncated"))` 只有在**同一 change 内**先让 `inspect_transcript`
  回流该标志后才有意义。若实现被拆成两个 commit / 被部分回滚，取或会静默退化为「只看本层」，
  而**现有测试不会变红**（因为没有测试断言「上游标志为 True、本层更宽 → 结果 True」之外的组合）。
  建议测试同时覆盖「上游截了、本层更宽」与「上游没截、本层截了」两个方向。

- **风险（低）：`test_result_representations.py:84` 的改造可能被漏掉**（决策 1）。design 的
  「测试影响」小节只点名了 `tests/web_tests/test_workflow_node_transcript.py:624`，而实测这条
  `:84` 是 D2 落地后**唯一**变红的既有测试。若实现者照 design 的清单改测试，会在跑全量 pytest 时
  才发现——建议直接把这条写进 tasks.md 的测试清单。

- **风险（低）：`docs/agent-internals.md:975-1004` 的 inspect 示例已过时**，design 已识别；
  补充扫描结果：`docs/interview-script/run-pattern-web-demo.md`、`docs/interview-script/walkthrough/W03-multi-agent.md`、
  `docs/interview-bullets/walkthrough.md` 也含 `bounded_summary`/`InspectSubagentTranscript`
  关键词，收尾时需一并判断是否受影响（AGENTS.md 的「建议性维护约束」同时要求检查
  `docs/interview-script/`）。

## spec delta 可机械验证性（挑战 G）

逐条判定两个 MODIFIED Requirement 的 Scenario 能否写成确定性断言：

| Scenario | 可机械验证？ | 说明 |
|---|---|---|
| subagents / 查看最近消息 | ✅ | 断言行数与「不含整份 transcript」即可 |
| subagents / 超长单条内容在模型面被截断 | ✅ | `len(content) <= 4000 and content_truncated is True`（输入须 >4000） |
| subagents / 超长摘要同样受限 | ✅ | 同上，对 `summary` |
| subagents / 工具结果消息与普通消息同口径 | ✅ | 与上一条同断言，输入换 tool 角色 |
| subagents / 模型面与 HTTP 面同值 | ✅ | 三处常量相等断言（`TRANSCRIPT_ITEM_LIMIT` / `TOOL_CALL_ARGUMENT_LIMIT` / `TRANSCRIPT_CONTENT_LIMIT`） |
| agent-runtime / 父 run 查询子 run 结果 | ✅ | 既有 `GetSubagentRun` 行为断言 |
| agent-runtime / 超长子 agent 输出在模型面被 bounded | ⚠️ **有条件** | `summary <= 摘要预算` 可断言，但「摘要预算」本身是 `max(2000, max_tokens*4)`——**只测默认 `max_tokens=None` 时该断言才锁住真实界**（见 Q1） |
| agent-runtime / 截断标记不指向不存在的引用 | ✅ | `assert "result_ref" not in payload["bounded_summary"]`（当 `result_ref is None`）——**注意这是否命题写法，不能写成恒真的「包含『已截断』」** |
| agent-runtime / 调度器内部消费仍取全量 | ✅ | 断言 `state.summary == run.summary`，或直接跑 `test_workflow_aggregator` 那条（实测它能捕获，见决策 2） |

**不可证伪的措辞**（建议改）：

1. `specs/subagents/spec.md`：「被截断的字段……SHALL NOT 依赖调用方用长度比较自行推断」
   —— 「调用方不自推断」是对**调用方行为**的约束，测试无法观测。可测的内核是「标志随文本回流」
   与「跨层取或」，建议拆成独立 Scenario（见「风险」第 3 条）。
2. `specs/subagents/spec.md`：「同一份 inspect 结果在模型面与 HTTP 面 SHALL NOT 分叉」
   —— 「不分叉」若只指数值相等则可测（已有断言）；若指**行为**相等（同一输入两路返回同长），
   则 HTTP 路由的 `content_limit` 是公开参数、可任意传，行为相等**不成立**（既有
   `test_transcript_tool_call_arguments_are_bounded` 就故意传 `content_limit=40`）。建议把措辞
   收敛为「**默认**上限同值」，不要扩大到「行为不分叉」。
3. `specs/agent-runtime/spec.md`：「`summary` 字段 SHALL 不超过该 run 的摘要预算」
   —— 可测，但「摘要预算」的定义缺引用（是 `BOUNDED_SUMMARY_CHARS` 还是 `max_tokens*4`？
   两者取 max 是**行为**而非可读的数字）。建议在 spec 里写明公式口径，否则测试与实现各写各的。

## 实跑命令（完整清单）

```bash
# 基线
uv run pytest -q tests/agent/subagent/test_result_representations.py \
  tests/agent/subagent/test_workflow_result_refs.py \
  tests/web_tests/test_workflow_node_transcript.py -p no:randomly        # 32 passed

# design 字面落地模拟（调度器未传 full_summary → 2 failed, 539 passed）
PYTHONPATH=/tmp/grill_213 GRILL_SCHEDULER_FULL=0 uv run pytest -q -p grill_patch -p no:randomly \
  tests/agent/subagent/ tests/web_tests/test_workflow_node_transcript.py

# design 字面落地模拟 + 调度器显式 full_summary（→ 1 failed, 540 passed）
PYTHONPATH=/tmp/grill_213 GRILL_SCHEDULER_FULL=1 uv run pytest -q -p grill_patch -p no:randomly \
  tests/agent/subagent/ tests/web_tests/test_workflow_node_transcript.py

# 精确定位被打破的断言
PYTHONPATH=/tmp/grill_213 GRILL_SCHEDULER_FULL=1 uv run pytest -q -p grill_patch -p no:randomly \
  tests/agent/subagent/test_result_representations.py::test_three_representations_are_distinct

# 4 出口无界复现 + 预算浮动
PYTHONPATH=. uv run python3 - <<'PY'  # to_result_dict / inspect_transcript 两个 scope / _bounded_summary
PY

# D4 赋值顺序
python3 /tmp/grill_213/probe_d.py

# D7 取或判别力
PYTHONPATH=. uv run python3 /tmp/grill_213/test_probe_or.py

# D9 预算放大
PYTHONPATH=. uv run python3 /tmp/grill_213/probe_runpattern_budget.py

# model 自撰 spec 的 max_tokens 无上界
PYTHONPATH=. uv run python3 -c "from agent.subagent.workflow import parse_workflow_spec; \
from agent.subagent.manager import _bounded_summary; \
s=parse_workflow_spec({'goal':'g','nodes':[{'id':'a','kind':'subagent','task':'t','max_tokens':500000}],'terminal':['a']}); \
print(s.nodes[0].max_tokens)"

# bus 出口实测
PYTHONPATH=. uv run python3 -c "from agent.subagent.bus import MessageBus; \
b=MessageBus(); [b.publish(sender=f'w{i}',topic='f',summary='F'*1600,token_count=400) for i in range(100)]; \
import json; print(len(json.dumps(b.snapshot_payload(),ensure_ascii=False)))"    # 173303

# pattern 测试无回归（D9 下）
PYTHONPATH=/tmp/grill_213 GRILL_SCHEDULER_FULL=1 uv run pytest -q -p grill_patch -p no:randomly \
  tests/agent/subagent/test_patterns.py tests/agent/subagent/test_pattern_templates.py \
  tests/agent/subagent/test_bounded_envelope.py                                     # 37 passed
```

**零改动自查**：`git status --short` 仅显示 `?? openspec/changes/fix-issue-213-transcript-item-bound/reviews/grill-design.md`
一个未跟踪文件；探针脚本全部在 `/tmp/grill_213/`，仓库工作区未被修改。
