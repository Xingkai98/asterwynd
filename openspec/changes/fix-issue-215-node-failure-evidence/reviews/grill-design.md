# Grill: fix-issue-215-node-failure-evidence 设计追问

## Reviewer

- run id: grill-subagent-215
- 时间: 2026-09-23
- 机制: paseo 托管 agent（`claude/claude-fable-5[1m]`，plan 模式，零记忆——不继承开发会话上下文）
- 产出方式: 独立 subagent 挑战 `design.md` + 逐条读真实代码复核其事实断言；主 agent 对 D6 冲突补一轮追问后由该 subagent 给出裁决

## Confirmed Decisions

- **决策**: 投影挂载点与数据源成立——`failure_evidence` 从 `run.trace.steps` 读、零新增采集、写侧一行不改；理由: 数据在内存里已齐备（`agent/trace_recorder.py:129` 的 `tool_result` 带 `tool_name/status/observation/error_type`，`:226` 的 `llm_error` 带 `error_type/message`），全仓 `run.trace =` 仅四个写入点（`agent/subagent/manager.py:1334/1410/1425/1444`），唯一读取点 `agent/subagent/snapshot.py:77` 只数 `llm_iteration` 步数、与失败无关；来源: grill-subagent-215
- **决策**: 条目字段沿用 trace step 既有键名（`status`/`error_type`/`tool_name`/`observation`/`message`），节点级用 `state` 不用 `status`；理由: 实测 `TraceRecorder.to_dict()`（`agent/trace_recorder.py:229-244`）产出的形状正是 `{"step","type","data","timestamp"}` + `data` 内嵌上述键，design 假设的嵌套与代码逐字一致，改名会制造第二套词表；来源: grill-subagent-215
- **决策**: bounded 三元组「最近 N 条 + 真实 `total` + `truncated`」+ 单条复用 `TRANSCRIPT_CONTENT_LIMIT`（4000，`web/session.py:731`）；理由: `step` 序号由 `record()` 的 `len(self.steps)+1` 保证单调（`agent/trace_recorder.py:51-58`），「最近 N 条」有确定判据；单条复用既有常量而非新造数字，与 #213 已建立的单条上限同口径；来源: grill-subagent-215
- **决策**: 「运行中只如实报 `running`、不做实时可见性」的边界成立；理由: 四个 trace 写入点全在终态函数内（`_complete_run`/`_mark_failed`/`_mark_cancelled`/`_mark_budget_exceeded`），运行中 `run.trace` 恒为 `None`；来源: grill-subagent-215
- **决策**: 「加键不破坏既有 34 条 transcript 用例」的结论成立；理由: `tests/web_tests/test_workflow_node_transcript.py` 全 34 条用例无载荷键集精确断言（`grep "set(payload\|payload.keys()\|sorted(payload\|payload == {"` 零命中），只有 `payload["included_tool_results"] is False`（`:121/:604`）与 `"raw" in payload`（`:183`）这类值断言；路由层用例（`tests/web_tests/test_workflow_control_server.py:95-97`）只断言 `kind == "none"` 与 `json.dumps(payload)` 可序列化；来源: grill-subagent-215
- **决策**: D1 的六值状态枚举方向成立（「不把无数据与无错误折叠」是必须守的原则），但**取值集合需按 Q4 修正**；理由: 六个取值中 `present`/`clean`/`running`/`empty_trace`/`no_trace` 五条路径经代码复核真实存在，`unavailable` 的成因描述需订正（见「必须修改」与「风险」），且 `none` 形态的四条路径无处安放；来源: grill-subagent-215

> **撤回**：首轮报告 `## Confirmed Decisions` 中「前端落在既有『任务』tab（D6）」一条**作废**。该结论只证明了*渲染*可行（DOM 模式与样式类已存在），未证明*取数*可行——`renderDrawerTask`（`web/static/workflow.js:1115-1165`）整个函数体零 `fetch`，其唯一数据源是 `entry.snapshot` 投影出的 `node`，而 `failure_evidence` 只挂在 `/nodes/{id}/transcript` 载荷上（全仓唯一取数入口是「对话」tab 的 `workflow_transcript.js:55-82`）。两端不在同一条数据通路上，属**阻塞性设计缺陷**，改判为 Q6 交用户拍板。

## 必须修改

- **spec delta 必须钉住键名与枚举取值**：`openspec/changes/fix-issue-215-node-failure-evidence/specs/web-ui/spec.md:5-11` 通篇只说「载荷 SHALL 携带失败证据」「状态为『有失败证据』」，**从未出现 `failure_evidence` 这个键名**，也从未列出 `state` 的取值集合与条目字段名。后果：实现可以换名/换枚举值而仍「符合 spec」，验收只能靠人读——这正是 issue #215 的失败模式（文档承诺了、验收抓不住）。要求：requirement 里写死键名 `failure_evidence`、枚举取值集合、每条条目的字段名单。
- **`none` 形态的判据与取值必须逐条定死**：design.md:150 只写「按节点类型给 `unavailable` 或『该节点不产生 run』的说明」，但代码里有**四条互不相同**的 `none` 路径，且没有一条能由「节点类型」单独判出：
  - `state is None`（节点不在当前执行计划里）→ `web/session.py:906-912`，既有用例 `tests/web_tests/test_workflow_node_transcript.py:212`；
  - route 节点 → `web/session.py:940-947`；
  - collect 聚合 **与未派发节点共用同一分支** → `web/session.py:951-961`（`message` 文案在 `:957-960` 分「纯逻辑聚合」/「未执行（未派发或未产生 run）」两种）；
  - 下钻时 subagent 已不在内存 → `web/session.py:857-861`（`kind` 被改写成 `none`）。

  其中「未派发节点」是**真实且被现有测试打到的路径**（`tests/web_tests/test_workflow_control_server.py:95-97` 的 live workflow 用例命中的就是它）。把「route/collect 天然不产生 run」与「run 记录解析不到」折叠进同一个 `unavailable`，正是 D1 自己禁止的那类折叠。见 Q4。
- **下钻形态的 run 解析缺 fallback 定义**：`_item_drilldown_payload`（`web/session.py:805-864`）拿到的 `run_id` 来自查询参数，而前端只在 truthy 时才带（`web/static/workflow_transcript.js:66-68`）；同时 `SubAgentManager.find_run` 在 `run_id is None` 时**恒返回 None**（`agent/subagent/manager.py:591-598`，逐条比较 `run.run_id == run_id`，`None` 不匹配任何 run）。按 design 直译实现，「候选列表 → 点某项」这条**最常见的路径**就会报 `unavailable`（谎报数据缺口）。必须写明：`run_id` 为空时回落到该 session 的最近一个 run（等价于 `manager._find_run` 的 None 分支，`agent/subagent/manager.py:1574-1583`，`session.runs[-1]`）。
- **`llm_error` 条目的 `status` 取值必须写死**：D3（design.md:132）把 `status` 列为**每条**条目的字段，但 `record_llm_error` 只写 `error_type` 与 `message`（`agent/trace_recorder.py:226`），`data` 里**没有 `status` 键**。实现若直接 `step["data"].get("status")` 会得到 `None`，与「条目 SHALL 含 `status`」的 spec 文字冲突。要求：明确 `llm_error` 条目的 `status` 恒为 `"error"`（由投影合成），或明确 spec 只对 `tool_result` 要求 `status`。
- **截断标志的命名对 `llm_error` 不成立**：design D3 每条只给一个 `observation_truncated`，但 `llm_error` 被截断的字段是 `message` 而非 `observation`（`agent/trace_recorder.py:226`），flag 名与被截字段对不上，正是 F3 警告的「同一个词指两件事」类问题。要求二选一并写进 spec：把标志改为对两种条目同义的单名（如 `text_truncated`），或明确「`observation_truncated` 对 `llm_error` 条目表示 `message` 被截断」。注意**不可**改用 `truncated`——该键在载荷顶层已是「条数被截断」语义（`agent/subagent/manager.py:1158`），会造成语义碰撞。
- **`running` 的判据必须指名常量，且不要造第四份副本**：`web/session.py` 目前**没有**任何 TERMINAL 常量（`grep TERMINAL_RUN_STATUSES web/session.py` 零命中）。项目里已有三份同义清单：`agent/subagent/manager.py:153-155`（4 值，不含 `queue_full`）、`agent/subagent/scheduler.py:88-90`（5 值，含 `queue_full`）、以及 `web/session.py:1019-1021` 硬编码的字面量元组。design.md:108 只说「`TERMINAL_RUN_STATUSES` 不含当前 status」，没说用哪一份。要求：指定来源并优先复用 `web/session.py:1019-1021` 那份（或提为模块级常量），否则会出现第四份。
- **「大 trace 响应体积有界」测试必须按可杀变异的形状写**：design 的风险栏（design.md:216/266）把这条当作主要缓解，但若断言写成「`len(json.dumps(payload)) < 某个宽松常数`」，一个「返回全部失败条目」的实现照样能过（无失败时本来就小）；且 `run.trace` 本身**从不进入响应**，体积有界完全由「只取 ≤N 条 + 单条截断」保证，与「只遍历不复制」无关。要求测试成立的最小断言集：(a) `len(items) <= FAILURE_EVIDENCE_LIMIT`；(b) `sum(len(item.get("observation") or "") + len(item.get("message") or "") for item in items) <= N * content_limit`；(c) `total == 300`（真实总数，与返回条数不等）；(d) 用**全部 300 步都是失败且 observation 各 30000 字**的 trace 构造，使「不截断」与「不设上限」两条变异必红。既有同源写法见 `tests/web_tests/test_workflow_node_transcript.py:131-135`（`limit=2` + 逐条长度断言），照此风格即可，别退化成整包长度比较。
- **三态挂载要有测试，不能只在 tasks 的实现行里提一句**：tasks.md:28-30 写了实现侧「三态分支各挂载」，但测试清单（tasks.md:37-51）只覆盖 `single` 语义的状态枚举。缺 (a) `candidates` 形态每个候选各带 `failure_evidence`；(b) `_item_drilldown_payload` 顶层带 `failure_evidence`；(c) `none` 形态的状态与文案（见上条）。
- **前端改动必须有测试覆盖，建议走既有 node+vm 纯函数路径**：design.md:240-241 说「不新增浏览器 smoke」。可接受与否取决于覆盖方式——`web/static/workflow.js` 的 DOM 渲染在非浏览器测试里**零覆盖**（该文件的既有测试都是 `tests/web_tests/test_workflow_graph_browser.py` 的 playwright 用例，且 `web/static/workflow_transcript.js` 全仓只有一个 cache-busting URL 断言 `tests/web_tests/test_server.py:447`）。建议：把失败证据的**文案映射与条目格式化**抽成 `web/static/workflow_graph.js` 的纯函数（`window.AsterwyndWorkflowGraph` 上，先例是 `nodeLabel`/`nodeColor`/`explainNode`），用 `tests/web_tests/test_workflow_graph_ux_js.py:20-33` 那套 node+vm harness 锁定「各 `state` → 文案」的映射；`workflow.js`/`workflow_transcript.js` 只剩建 DOM。这样既不加 smoke，又让「把 `clean` 当 `no_trace`」这类变异在前端层也可见。
- **文档影响需补一处**：`docs/architecture.md:105` 逐字描述了该 transcript 路由的返回形态（「三态 union … bounded 且不调 LLM」），本次新增 `failure_evidence` 后该句不再完整，收尾时应同步一句（tasks.md:58 的关键词扫描清单里有 `docs/`，但没有点名这个文件）。

## Open Questions

- **Q1**: 是否加「已恢复」标记（`recovered`）？grill 复核后**推荐不加**，改为在区块层面带 run 上下文（如「该 run 已完成（`completed`）；本 run 内出现 3 次工具失败」）。
  - 判据在代码上**可算**：失败步之前的 `tool_call` step 带完整 `arguments`（`agent/loop.py:920-926` 先 `record_tool_call` 再 `record_tool_result`），所以「同工具 + 同参数后继成功」不是做不到，只是要再扫一遍并做 dict 相等比较。
  - 但**语义不可靠**：同 `tool_name` 的后继 `status == "ok"` 完全可能是**另一次不同的调用**，按「同工具后继成功」判据会写出**假话**。要判准必须比对 `arguments`，而参数里的临时路径/环境变量差异会让精确比较在真实 trace 上频繁漏判（漏判 = 把自愈报成隐患，比不报更糟）。
  - **场景例子**：节点 A 的 trace 里 step 7 是 `Bash{"command": "uv run pytest tests/x"}` 失败（`error_type=tool_error`），step 13 是 `Bash{"command": "ls -la"}` 成功。按「同工具后继成功」判据，step 7 这条会被打上「已恢复」——而用户读到的是假话（那条失败从未被处理）。节点 B 的 step 7 失败后**再没有任何** `Bash` 步骤 → 报「未恢复」。同一份 trace 用不同判据会得到相反结论，说明这个标记当前没有可靠语义。
  - **替代方案（grill 推荐）**：区块标题带 run 状态上下文——「已完成 · 本 run 内出现 3 次失败（显示最近 3 条）」。这句是**事实**，不依赖任何推断，成本一行文案。恢复语义（含重试轨迹）归 #202 更自然：那里有完整 step 序列，可以画「失败 → 重试 → 成功」。
- **Q2**: 条目上限 `FAILURE_EVIDENCE_LIMIT` 取多少？grill **推荐保留 5**，但前端预览另设短上限。
  - 证据：单条上限 4000 是**单条消息**的口径（`web/session.py:727-731` 的注释明说这是 issue #213 的迁移上限），不是「抽屉里一行」的口径；失败条目在 `.drawer-body`（`web/static/style.css:1738`，`padding:14px` 的可滚动区）里通常渲染成 2-3 行。
  - **场景例子**：一个 40 步的 run 里有 9 条失败 → N=5 时用户看到最近 5 条（约 10-15 行）+「共 9 条，已截断」，仍在一个手机屏的滚动预算内；N=10 会让「失败证据」压过「任务」本身。因此：`FAILURE_EVIDENCE_LIMIT = 5` 保留，**载荷**里单条仍截到 4000（与既有口径一致，便于对账），**前端预览**取前 ~300 字符 + 「预览已截断，全文见『对话』tab」的既有 note 模式（`web/static/workflow.js:1192-1196` 已有同款写法）。这样 N 只决定条目数，不决定体积。
- **Q3**: `state == "clean"` 时前端显示什么？grill **推荐 (b) 一行淡色「已检查，无失败记录」**。
  - **场景例子**：用户点开一个正常完成的节点（`state == "clean"`、条目为空、trace 12 步无失败）。选 (a) 时他看到的是**和改动前一模一样**的抽屉——无从知道系统**检查过**（F2 的教训正是「`ok` 不能是默认值」，而「什么都不显示」恰恰让「未评估」与「无异常」共用同一个视觉）；选 (b) 时他读到一行灰字「已检查，无失败记录（trace 12 步）」，把「系统看过且干净」与「没有数据」在视觉上分开；选 (c) 需要额外一个折叠控件，而 `drawer-why` 之后并没有既有的折叠模式，等于新造交互。
  - 与 D1 的一致性要求：`running` / `no_trace` / `empty_trace` / `unavailable` **也必须各显示一行自己的文案**（不能只有 `clean` 显示），否则「clean 显示、其它不显示」又会退化成「不显示 = 没事」。
- **Q4**: D1 六值枚举是否过度设计？`none` 形态（route / collect / 未派发）往哪放？grill 复核后**推荐扩到 7 个取值**，新增 `not_applicable`；六值本身**不过度**（逐条复核见「代码事实复核」）。
  - **场景 A（route 节点）**：`gate` 节点走 route，`state.subagent_id` 为 `None`，现有载荷是 `{kind:"none", verdict, targets, raw}`（`web/session.py:940-947`）。它**天然不产生 run**，若报 `unavailable`（「无法解析该 run」），用户会以为数据丢了；正确的话是「该节点不产生 run，无失败证据可言」。
  - **场景 B（未派发节点）**：`tests/web_tests/test_workflow_control_server.py:95-97` 里那个 live workflow 的 `a` 节点，`state.subagent_id` 为 `None`、`message == "该节点未执行（未派发或未产生 run）"`（`web/session.py:957-960`）。它既不是 route/collect，也没有「解析不到的 run」——它是**还没轮到**。
  - **具体判据建议（可直接落代码）**：`state is None` → `unavailable`（节点不在计划里）；`node.kind == "route"` 或 `aggregate + collect` → `not_applicable`；`not state.subagent_id` 且非上述 → `unavailable` + 文案「该节点尚未派发」。若嫌两义共用 `unavailable` 不妥，可再拆 `pending`，但 grill 不推荐——「尚未派发」与「run 记录被弹出」对用户是同一句话：「现在没有证据，原因见文案」，而 route/collect 是**结构上不可能有**，必须分开。
- **Q5**: `candidates` 形态每候选都带完整证据，体积会放大到不可接受？grill 推荐**每项带轻量证据**。
  - **场景例子**：默认 `limit=50`（`web/server.py:195-202` 的 `limit: int = 50`），上限 `CANDIDATE_MAX_LIMIT=200`（`web/session.py:738`）。若每个候选都带完整证据（≤5 条 × ≤4000 字符），最坏每候选 20KB，200 项 = **4MB** 的一个 JSON 响应，手机端会明显卡。既有载荷已经带了 `task`/`summary`/`reason` 各 4000（`web/session.py:1034-1036`），所以这是**在已有放大上再乘一层**。
  - **推荐**：candidates 形态的每项带**轻量证据**——`state` / `total` / `truncated` + 至多 1 条最新失败（单条 ≤400 字符，字段同 D3）；完整证据（最近 5 条 × 4000）只在**下钻**（`_item_drilldown_payload`）与 `single` 形态给。这与 design 的意图（用户点进去看细节）一致，且把最坏响应压到 ~90KB 量级。
- **Q6**（阻塞项）: 失败证据的前端落点放哪个 tab？design D6（design.md:162-166）说放「任务」tab，但**该 tab 没有任何取数通路**——见顶部「撤回」说明。grill 推荐**方案 D**：证据主体进「对话」tab + 「任务」tab 一行来自快照的失败计数线索。
  - **方案 A（证据主体改放「对话」tab）**：改动面 = `web/static/workflow_transcript.js`（新增 `appendFailureEvidence`，在 `paint()`（`:100-119`）里 `appendBackLink` 之后、按 `payload.kind` 分派之前调用一次，三形态共用）+ `web/static/style.css`（复用 `.drawer-text`/`.drawer-note`）；后端零改动。**不违反任何现有 spec/测试**：spec `openspec/specs/web-ui/spec.md:836` 的懒加载条款不动，`tests/web_tests/test_workflow_graph_browser.py:488-493` 的「打开面板不得有 /transcript 请求」继续成立；change 自己的 spec delta 只说载荷内容、**未提 tab 落点**，无需改。需改的是 `proposal.md:36` 与 `design.md:162-166` 两处表述。**代价**：抽屉默认开在「任务」tab（`web/static/workflow.js:52`/`:1045`），用户不切 tab 就看不到——#215 的症状在默认视图里原样保留。
  - **方案 B（保留「任务」tab，打开抽屉即 fetch）**：**违反两条**——spec `openspec/specs/web-ui/spec.md:836` 正文「前端 SHALL 在切到「对话」tab 时才请求（懒加载）」，以及 `tests/web_tests/test_workflow_graph_browser.py:488-493` 的 `assert not [u for u in requests if "/transcript" in u]` 会直接变红。且该决策是归档 change **刻意**做的（理由写在既有测试 docstring `tests/web_tests/test_workflow_graph_browser.py:474-476`：「放『任务』tab 意味着一打开面板就得发 transcript 请求，破掉 D4 的懒加载」）——选它等于反转一条有成文理由的既往决策。
  - **方案 C（全量证据进快照节点投影）**：**违反 spec 的有界性纪律**——`openspec/specs/web-ui/spec.md:497-499` 只允许 `reason`/`task`/起止/`budget`/foreach 项字段这批加法字段，`:503-508` 的 Scenario 要求「快照 SHALL NOT 出现随规模膨胀的字段」；而快照按节点事件推送、`GRAPH_SNAPSHOT_WINDOW_S = 0.1` 合并（`web/session.py:526-527`），一个 12 项全失败的 foreach 容器 ≈ 240KB/帧。测试不会红（`tests/web_tests/test_workflow_graph_server.py:99` 只断言 `node["id"]`），但 spec 要改且违背该出口自定的有界口径。
  - **方案 D（推荐）**：**「对话」tab 承载证据主体 + 「任务」tab 一行来自快照的有界计数**。与 A 的唯一差别是再给快照加**一个整数字段**（不是证据列表）。**改动面**：`agent/subagent/scheduler.py` 的 `NodeState`/`_ItemRunSlot` 加字段 + 在 `_launch_run` 的 `terminal = await self._await_run(...)`（`:2167`）之后扫一次 `run.trace` 存计数（此点同时覆盖普通节点与 foreach 展开项，因为 `_run_foreach_item` 复用同一条 `_launch_run` 路径，`reuse_state` 分别是 `NodeState`/`_ItemRunSlot`）+ `_graph_node_projection`（`:2739-2773`）投影该字段 + `web/static/workflow.js:1115` 加一行文案；spec 需给快照 requirement 的加法字段清单 ADDED 一项（`:497-499`）。**不违反**懒加载（`:836` 不动、浏览器用例 `:488-493` 不动，关闭抽屉前零请求），且「给快照加有界加法字段」正是归档 change 加 `item_states`/`budget` 时走过的同一条路。
  - **场景例子**：节点 `a` 的 run 终态 `completed`，trace 里 step 7 是 `Bash{"command":"uv run pytest -q"}` → `status=error`、`observation="3 failed, 12 passed"`，step 9 是 `llm_error{error_type:"network_timeout"}`。用户点节点 `a`，抽屉默认开在「任务」tab → **A**：他看到 状态/类型/耗时/runs/因由/任务，与改动前逐字相同，没有失败线索，切到「对话」才看到「失败证据：2 条」；**B**：他立刻看到两条详情，代价是每次点节点都发一次 transcript 请求；**C**：图上节点直接带失败徽标，代价是快照膨胀；**D**：他看到一行「⚠ 本 run 内 2 次工具失败 →『对话』tab 查看」，点一次看到详情，全程零请求。
  - **若选 D，还需定两件事**：其一，快照字段粒度——只给计数（`None` = 无 trace/不可用，仅 >0 时显示）还是三态（`None`/`0`/`N`，`0` 也显示一行淡色「已检查、无失败」，与 Q3 的 `clean` 正向声明一致）；其二，计数算在哪——grill 推荐在 `_launch_run` 的 `_await_run` 之后**每 run 算一次**（普通节点与 foreach 展开项共用一处埋点），而不是在 `_graph_node_projection` 里每帧现算（后者 50 节点 × 80 步 = 每帧 4000 次 step 访问且随帧重复）。
  - **退路**：若要把范围压到最小，选**方案 A**（只改前端落点 + 两处文档），代价是默认 tab 继续无信号。
- **Q7**: `diagnosis.md` 记录的两条「死代码」发现在本 change 里怎么处置？grill 推荐**记 `docs/known-debt.md` 一条**，合并写两处并标注「本 change 显式不做」。
  - 发现 1：`StopReason.ERROR` 全仓零赋值点（定义 `agent/result.py:14`、唯一提及 `agent/subagent/manager.py:1324`、测试断言 `tests/agent/test_result.py:18`），`manager.py:1324` 的 `failed` 分支实际不可达——`diagnosis.md:111-123` 已实证但明确排除。
  - 发现 2（grill 新发现，见「风险」）：`agent/subagent/manager.py:1524` 的 `trace=None` 分支不可达，即 `no_trace` 当前**没有活跃生产者**。
  - `docs/known-debt.md` 是受保护路径，改动需在 `workflow-events.jsonl` 里有结构化解释事件（`scripts/flow-policy.json` 的 `governance=event_explained`），tasks.md 目前没有这条任务。请拍板：记（走 `artifact-event` 通道）还是不记（则须在 design 里说明为什么不记）。

## 风险

- **`no_trace` 的成因与代码不符（design 自称「实测确认过」但该分支不可达）**：`agent/subagent/manager.py:1524` 确在 `_mark_budget_exceeded(..., trace=None)` 把 `run.trace` 写成 `None`（经 `:1444`），但它的前置条件恒假——该调用位于 `_monitor_run_timeout`（`:1500-1535`），monitor 只在 `_start_task` 里创建（`:968-974`），而 `_start_task` **在创建 monitor 之前**已同步把 `run.status` 置为 `"running"`（`:963-966`）并把任务登记进 `_active_tasks`；全仓没有把 `status` 写回 `"queued"` 的点。因此 monitor 醒来时 `task is None` 只可能意味着「run 已终态」，`if run.status == "queued"`（`:1522`）永不成立。结论：**`no_trace` 当前没有活跃生产者**，D1 表（design.md:110）与 spec Scenario（specs/web-ui/spec.md:35-40）对它的「成因」描述是推测。建议：保留取值（便宜，且「不要折叠」的原则值得守），但把成因改写成**防御性**口径，并补一条直接构造 `run.trace = None` 的单测；spec 文案不要暗示存在活的触发路径。该结论由静态调用链分析得出，实现时建议用探针复核一次（探针能证明「写了 None」，不能反证可达性——可达性只能靠调用链论证）。
- **`empty_trace` 的成因只写了两个调用点中的一个，且行号偏移**：design.md:109 引 `manager.py:1085`，实际空 `TraceRecorder` 出现在 **`:1086`**（排队取消）与 **`:1100`**（`cancel_subagent_run` 的 running 分支）。`:1100` 那条在常规路径上会被 `_run_loop` 的 `except asyncio.CancelledError` 先 `_mark_cancelled(session, run, trace)`（`agent/subagent/manager.py:1228-1233`）置为终态，随后 `:1420-1421` 的「already terminal」守卫直接 return——即它是第二道兜底。行号与成因描述都要订正，否则「每个负向态对应一条实测确认过的路径」的成色打折。
- **`queue_full` 弹出点行号偏移**：design.md:111 / diagnosis.md:145 引 `manager.py:1033-1034`，实际的 `session.runs.pop()` 在 **`:1035`**（守卫 `if session.runs and session.runs[-1] is run:` 在 `:1034`）。
- **`unavailable` 的测试只能是「半合成」的，要在注释里说清**：`agent/subagent/scheduler.py:2125-2126` 明确写着 workflow 因准入背压「永不撞 queue_full」（`_dispatch_capacity = max_active + max_queued_runs`），所以 tasks.md:43 那条用例不能靠跑一个真实 workflow 触发，必须手工构造（直接调 `_take_back_if_queue_full` 或伪造一个 `run_id` 指向已弹出的 run）。这是可接受的，但用例注释要写明「生产路径在 workflow 内预期为 0 次」，否则后来者会以为它是热路径。
- **前端「预览长度」与「载荷长度」不同口径会再次踩 #213 的坑**：若前端把 4000 的载荷再截到 300 显示却不带任何截断提示，用户会以为失败输出就这么短。实现时须复用既有 note 模式（`web/static/workflow.js:1192-1196`）显式说明「预览已截断，全文见对话 tab」。
- **跨层常量重复有扩大趋势**：本次若在 `web/session.py` 再引入一份终态清单（design.md:108），同一语义的副本会从 3 份变 4 份（`agent/subagent/manager.py:153`、`agent/subagent/scheduler.py:88`、`web/session.py:1019`）。建议顺手把 web 层那份提为模块级常量并复用它，代价一行、收益是后续改动只有一个落点。

## 代码事实复核

| design 声称 | 实测 | 结论 |
|---|---|---|
| `trace_recorder.py:129` 产出 `tool_result`（带 `tool_name`/`status`/`observation`/`error_type`） | `def record_tool_result` 在 `:103`，`self.record("tool_result", **data)` 在 `:129`，data 键含 `tool_name/status/duration_ms/observation/error_type`（`agent/trace_recorder.py:110-129`） | 符合 |
| `trace_recorder.py:226` 产出 `llm_error`（`error_type`/`message`） | `def record_llm_error` 在 `:220`，`self.record("llm_error", error_type=…, message=…)` 在 `:226` | 符合；但该 step 的 `data` **无 `status`、无 `tool_name`**，design D3 把 `status` 列为每条字段需补规则（见「必须修改」） |
| 每个 step 有 `type`/`data`/`step`，`data` 内嵌 status/error_type/observation/tool_name/message | `to_dict()`（`agent/trace_recorder.py:229-244`）输出 `steps = [asdict(TraceStep)]`，`TraceStep` 字段为 `step/type/data/timestamp`（`:18-23`） | 符合（阻塞性风险排除） |
| 四个终态落点 `manager.py:1334/1410/1425/1444` 一行不改 | 逐行核对：`_complete_run:1334`、`_mark_failed:1410`、`_mark_cancelled:1425`、`_mark_budget_exceeded:1444`；`grep "run.trace ="` 全仓仅这 4 处 | 符合 |
| 排队取消新建空 `TraceRecorder`：`manager.py:1085` | 实际 `:1086`（另一个同类点 `:1100`） | **行号不符** |
| 排队中撞时间预算传 `trace=None`：`manager.py:1524` | 行号正确，但该分支条件恒假（见「风险」） | **行为不符（不可达）** |
| `queue_full` 把 run 弹出 `session.runs`：`manager.py:1033-1034` | `session.runs.pop()` 在 `:1035`（守卫在 `:1034`） | **行号不符** |
| `manager.py:1140-1141` 过滤 `role == "tool"` 消息 | `if not include_tool_results:` `:1140`，`messages = [msg for msg in messages if msg.role != "tool"]` `:1141` | 符合 |
| `manager.py:1324` 的 `StopReason.ERROR` 判据 + 全仓零赋值点 | `:1324` 逐字一致；`StopReason.ERROR` 命中仅 `agent/result.py:14`（定义）与 `tests/agent/test_result.py:18`（断言） | 符合 |
| `web/server.py:195-202` 路由签名无 `include_tool_results` | `async def node_transcript(...)` 在 `:195`，参数到 `:202`，无该参数 | 符合 |
| `web/session.py:875` 默认 `include_tool_results=False` | `include_tool_results: bool = False` 在 `:875` | 符合 |
| `web/static/workflow_transcript.js:55-70` 未传该参数 | url 拼装在 `:61-68`，只带 `subagent_id`/`run_id` | 符合 |
| `TRANSCRIPT_CONTENT_LIMIT`=4000、`CANDIDATE_MAX_LIMIT`=200 | `web/session.py:731` / `:738` | 符合 |
| 全仓唯一读 `run.trace` 的地方是 `snapshot.py:77`，只数 `llm_iteration` | `trace = run.trace or {}` 在 `:77`，`:79` 只 `sum(1 for s in steps if s.get("type") == "llm_iteration")` | 符合 |
| 既有 34 条 transcript 用例无精确键集断言 | 该文件 34 个用例，`grep "set(payload\|payload.keys()\|sorted(payload\|payload == {"` 该文件零命中 | 符合 |
| `run.trace` 是内存里的 dict（`to_dict()` 结果） | `SubagentRunRecord.trace: dict \| None`（`agent/subagent/manager.py:184`），写入即 `to_dict()` 结果 | 符合；因此「只遍历不复制」省下的是「复制全部 steps」，不是序列化成本——体积有界完全靠「只取 ≤N 条 + 单条截断」，测试断言须按此写（见「必须修改」） |
| `.dev/reference-repos.txt` 不存在 | `.dev` 目录整个不存在 | 符合 |
| `running` 判据用「`TERMINAL_RUN_STATUSES` 不含当前 status」 | 该常量在 `web/session.py` **不存在**；项目内有三份同义清单（manager 4 值 / scheduler 5 值 / `web/session.py:1019-1021` 字面量） | **未指定来源**，需补（见「必须修改」） |
| trace step 顺序即时间序、`step` 单调 | `record()` 用 `step=len(self.steps)+1` 追加（`agent/trace_recorder.py:51-58`），列表序与 `step` 序一致 | 符合；但实现应取**列表序**为准，`step` 仅作展示 |
| D6：前端落在「任务」tab，`renderDrawerTask` 渲染 | `renderDrawerTask`（`web/static/workflow.js:1115-1165`）零 `fetch`，数据源只有 `entry.snapshot`；`/transcript` 载荷唯一取数入口在「对话」tab（`web/static/workflow_transcript.js:55-82`） | **不符（阻塞）**，见 Q6 |
| spec delta 覆盖 design 的全部决定 | 7 个 Scenario 覆盖 present/clean/running/no_trace/empty_trace/unavailable/超上限；**缺** `none` 形态（route/collect/未派发）与 candidates/drilldown 挂载；且全文未钉键名与枚举字面量 | **部分不符**（见「必须修改」） |

## User Confirmation

（停轮中：Q1–Q7 逐项抛用户确认，收到答复后逐条写入本节的 `- **Q<n>**: 用户答复：…；确认时间: …` 记录。在全部确认前不写实现代码。）
