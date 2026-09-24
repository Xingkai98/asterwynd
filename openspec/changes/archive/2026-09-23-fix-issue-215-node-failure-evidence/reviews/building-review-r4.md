# Building Review: fix-issue-215-node-failure-evidence（Round 4）

## Reviewer

- run id: review-subagent-215-r4
- 时间: 2026-09-23
- 审阅范围: `1a7df92cbd90ab442342a8481d59857b8c4ebf54`..`e892e00cf011e90c3103fdeb54d5e3c015d30fd8`
- 工作目录: `/tmp/rev-215`（隔离检出）。审阅结束时已删除自建探针/变异驱动
  （`mutate.py` / `mutate_core.py` / `probe_*.py`）并 `git checkout -- .`，
  工作区只剩 `?? .venv`（paseo 预置软链）与本报告。

## Verdict

**PASS**

理由：

1. **R3 声称修好的四条保护，用自己的变异独立复核后全部真的成立**（不是只看 diff）：
   删条目列表 / 删失败文本 / 关截断页脚 / 去掉标题真实条数，四条各自**变红**，并把
   断言错误信息打出来确认红的是**本条断言**而不是环境 flake。R3 顺带修的那个真 bug
   （`failureItemSummary` 首行无界 → 绕过 300 字符预览上限）也有**可失败证据**：
   去掉 120 字符上限 → `assert 465 <= 200`，把上限放宽到 500 → 同样变红。
2. **R3 的三条低危修复也真的落地**：下钻挂载点 `content_limit` 透传现在有断言
   （删掉 → `assert 4000 <= 100` 变红）；D7 从**文本匹配**改成**行为断言**后，
   R3 报告里那条「语义等价的漂移写法存活」的洞**确实被堵上**（我在 `_foreach_candidates`
   里内联一个少 `queue_full` 的集合 → 变红，「被改写成 queued」）；「任务」tab 三态
   （`N` / `0` / 缺键）现在都有 DOM 断言，整段关掉、`None` 与 `0` 折叠、把
   高亮类去掉**三态各自变红**；`failureText` 兜底分支也补上了用例（删掉兜底 → 变红）。
3. **本轮共 37 条变异，36 条被杀；唯一「存活」的是一条纯文案回退**（把
   「预览已截断（最多 300 字符）。」改回 R3 之前的谎话措辞），它没有行为差异、
   而「截断标注**存在**」本身已被断言锁住，**不构成假保护**。
4. 核心不变式（七态不折叠、最近 N 条、真实 `total`、`truncated` / `text_truncated`
   标量、轻量 400 上限、`llm_error.status` 合成、`count_failures` 空 trace 区分、
   快照三态埋点、`_reset_subtree` 复位、`_ASSERTABLE_STATES` fail-fast）**18 条
   多轮已验过的不变式我全部重跑一遍，18/18 被杀**——没有靠上一轮的结论转述。
5. 其余维度未发现问题：spec delta 逐条有实现且有用例、**未见「写了但没实现」**；
   新增前端渲染**全部**走 `textContent`（`workflow*.js` 的 `innerHTML` 零命中）；
   懒加载契约在隔离重跑下成立（2/2）；CI 未弱化；无既有用例因新键变红。

本轮新发现 4 条**低**（均不阻塞），无中等及以上问题，故判 **PASS**。

## 前几轮修复验证

### R1-1（中）`failure_count` 逃过 `_reset_subtree` → **真的修好了**

`agent/subagent/scheduler.py:1697`。**变异 C17**（删掉该行）→
`test_terminal_honesty.py -k failure_count` **变红**（1 failed / 20 deselected）。
该用例含 5 条独立断言（`status`/`reason`/`summary`/`finished_at`/快照
`failure_count is None`），不是恒真。

### R1-2（低）未知 `state=` 静默穿透 → **真的修好了**

`web/session.py:767` 的 `_ASSERTABLE_STATES` 只收
`{not_applicable, unavailable, running}`，其余一律 `ValueError`。
**变异 C6**（把 `present`/`clean` 扩进去）→ `-k rejects_unknown_explicit_state`
**变红**。

### R2-2（中）前端零消费后端 `message` → **真的修好了**

`web/static/workflow_transcript.js:239-243` 的 `failureText` 优先取后端 `message`。
**变异 N7**（把优先分支改成 `if (false)`）→ `test_convo_tab_prefers_backend_message`
**变红**，报错正文正是那句只有后端会写的「该节点尚未派发」没有渲染出来。
**独立复核「兜底表是否成了死代码」**：不是——**变异 N7b**（兜底 `return ''`）被
本轮新增的 `test_convo_tab_falls_back_when_backend_message_is_missing`
**变红**捕获（R3 之前这条存活），说明 R3 的低-7 修复到位。

### R2-3（低）`content_limit` 三处透传只有两处被锁 → **三处都锁上了**

- `single`（`web/session.py:1177`）：**变异 N9b** → 变红（`assert 4000 <= 100`）。
- `candidates`（`:1234`）：**变异 N9c** → 变红（`assert 400 <= 50`）。
- 下钻（`:1016`）：**变异 N9** → 变红（`assert 4000 <= 100`，R3 之前这条**存活**）。

R3 加的 `tightened = build_node_transcript_payload(..., content_limit=100)` 断言
（`tests/web_tests/test_workflow_node_transcript.py:1381-1391`）是真保护。

### R2-4（低）D7 单源守卫是文本匹配 → **改成行为断言，洞真的堵上了**

`tests/web_tests/test_workflow_node_transcript.py:1794` 的新用例构造一个真
`status="queue_full"` 的 run，断言候选不被改写成 `queued`。
- **变异 N8**（模块常量删 `queue_full`）→ **变红**
  （`queue_full 是终态，被改写成 queued 了…`）。
- **独立复现 R3 报告里那是「存活」的写法**：在 `_foreach_candidates` 里**内联**一个
  少 `queue_full` 的等价集合（旧守卫只查字面量、抓不到）→ **也变红**，报错同一句。
  即 R3 声称被修掉的那个洞**确实不存在了**，不是「换了个说法」。

### R3-1（中）`single` 形态证据**正文区**零覆盖 → **四条变异全部真的变红**

这是 R3 的阻塞项，我逐条独立重跑（断言正文见「变异验证」表）：

| 变异 | 改了哪行 | 跑了哪条测试 | 结果 |
|---|---|---|---|
| N1 删条目列表 | `workflow_transcript.js:262` `(evidence.items \|\| [])` → `[]` | `test_convo_tab_renders_failure_evidence_body` | **变红**，3/3 复现，等待 `.failure-item` 超时 |
| N2 删失败文本 | `:265` `const text = item.observation \|\| item.message;` → `null` | 同上 | **变红**，`预览截断没有标注…` |
| N3 关截断页脚 | `:274` `if (evidence.truncated)` → `if (false)` | 同上 | **变红**，`截断页脚缺失：…` |
| N4 标题去真实条数 | `:257-259` 标题 → 裸 `'失败证据'` | 同上 | **变红**，`标题丢了真实条数：'失败证据'` |

N1/N3 的红色是真信号而非环境 flake：N1 卡在 `.failure-item`（**只有**条目列表被删才会
缺），断言的定位器与 flake 的 `.workflow-svg` 不同；N3 直接给出断言文本。

**另外补一条 R3 没做的对照**：把标题的真实条数换成**返回条数**
（`` `失败证据（共 ${(evidence.items||[]).length} 条）` ``）→ 也**变红**
（`共 9 条` 不再出现在标题）。即这条断言锁的是**真实 `total`**，不只是「有数字」。

### R3「顺带修掉的真 bug」（`failureItemSummary` 首行无界）→ **真的修好了**

`web/static/workflow_graph.js:1165-1166`。
- **变异 N5**（去掉 120 上限）→ **变红**（`条目摘要无界：465 字符`，`assert 465 <= 200`）。
- **变异 N5b**（上限放宽到 500）→ **也变红**（同一条断言）。
  说明断言在 120 与 200 之间留的余量不是「随便写个宽松数」——收紧实现会被抓。

### R3 低-3（「任务」tab 线索 DOM 层无覆盖）→ **真的修好了**

`SNAPSHOT` fixture 补了 `failure_count: 3`（`:78`）/`0`（`:81`）/缺键（`join`）。
- **变异 N6**（整段线索关掉 `hint = null`）→ **变红**。
- **变异 N6b**（`failureCountHint` 把 `None` 折进 `0`）→ **变红**（ux_js 层）。
- **变异 N6c**（去掉 `drawer-failure-hint` 高亮类）→ **变红**，3/3 复现，
  等待 `.drawer-failure-hint` 超时（R3 报告里这条是**存活**的）。

### R3 低-5（「全文见本条记录」假承诺）→ 已改为事实表述

`web/static/workflow_transcript.js:269` 现为「预览已截断（最多 300 字符）。」，
`design.md:247` 的 Q2 行同步订正。
**注意（不算 issue）**：把文案**回退**成旧措辞时 `test_convo_tab_renders_failure_evidence_body`
**不红**（`0 passed?` 见变异表末行）——即**具体措辞**无守护，只有「截断标注存在」
被守护。纯文案回退无行为差异，且本 change 要守的是「截断必须告知」这一不变式，
故按**非问题**记录，不升级为假保护。

## Tasks Verification

对照 `tasks.md` 每个 `[x]` 读代码/跑测试确认（行号为当前 HEAD）：

- [x] grill 前置（独立零记忆 subagent + 停轮确认 Q1–Q7）→ `reviews/grill-design.md`
  有 6 条 Confirmed Decisions + `## User Confirmation`（7/7，每条配真实场景例子）
- [x] 常量组（`FAILURE_EVIDENCE_LIMIT=5` / `FAILURE_EVIDENCE_PREVIEW_LIMIT=400` /
  `_TERMINAL_RUN_STATUSES` / `FAILURE_EVIDENCE_STATES` 七值 / `_ASSERTABLE_STATES`）
  → `web/session.py:741/745/751/759/767`
- [x] `_failure_evidence(...)` 只遍历不复制 → `web/session.py:770-849`；判据在
  `agent/trace_recorder.py:258-270`；变异 C14（判据收窄成 `== "error"`）**被杀**
- [x] 七态 + 各负向态可读文案 → `web/session.py:826-847`（`settle` 成对取文案）+ `:859-868`；
  参数化七值用例 `test_every_failure_evidence_state_has_a_distinct_readable_message`
- [x] 条目 bounded（最近 N / 时间正序 / `text_truncated` / `llm_error.status` 合成）
  → `web/session.py:843/872-897`；变异 C7/C8/C9/C10/C13 **均被杀**
- [x] `build_node_transcript_payload` 三态挂载 → `single` `:1177`；`candidates` `:1234`；
  `none` `:1090`（state is None）/`:1130`（route）/`:1147`（collect 与未派发）；下钻 `:1016`
- [x] 终态判据单源（D7）→ `web/session.py:751-752` + `:1214`；行为断言 `:1794`，
  文本守卫在 `:1820`；变异 N8 + 内联漂移**均被杀**
- [x] `NodeState` / `_ItemRunSlot` 计数字段 → `scheduler.py:257` / `:215`
- [x] 埋点在 `_await_run` 之后、每 run 一次、`queue_full` 早退绕过 →
  `scheduler.py:2175-2177`、`:2134-2145`；变异 C18 **被杀**
- [x] `_graph_node_projection` 投影 → `scheduler.py:2792`；变异 C16 **被杀**
- [x] 前端「对话」tab 挂载 → `workflow_transcript.js:119`（调用）/`:245-278`（实现）；
  正文区四条变异 N1–N4 **全部被杀**
- [x] 前端纯函数 → `workflow_graph.js:1124-1174`；`None`/`0` 折叠（N6b）、
  未知 state 降级（C 组已验）、摘要上限（N5/N5b）**均被杀**
- [x] 「任务」tab 一行快照线索（零请求）→ `web/static/workflow.js:1137-1147`；
  变异 N6/N6b/N6c **均被杀**
- [x] 样式 → `web/static/style.css:1753-1778`（复用既有抽屉语汇）
- [x] 测试清单逐条在位；**断言非恒真**（37 条变异，36 杀）
- [x] 回归 `tests/web_tests/` + `tests/agent/subagent/` → **953 passed, 7 skipped**
- [x] `diagnosis.md` 6 章 + Grill 订正表 → `diagnosis.md:155-167`
- [x] 关键词扫描 → `docs/architecture.md:106` 新增「失败证据投影」一段
- [x] `docs/known-debt.md:276-295` 两条死代码发现 + seq 2/3 解释事件
- [ ] `tasks.md:97/98`（spec 同步）/`:105`（backlog 移除）/`:114`（manifest）/
  `:116-120`（验证）/`:123-125`（收尾）：核对后**诚实**——`openspec/specs/**` 本次
  零改动（`git diff --name-only origin/master...HEAD` 无该路径），与两条未勾一致；
  review manifest 确实不存在（artifact checker 实测报 `review manifest missing`）；
  `:113` 的「封顶轮后待用户授权」已由本轮（用户授权的 R4）满足，需在归档前回写。

## Issues

按判据校准：以下四条**均有**「用户看到错的东西 / 承诺未兑现 / 假保护」以外的实际后果
（措辞不精确、规格歧义、CI 可靠性、注释与实现不符），但**后果面都有限**，故判**低**，
不阻塞合入。**无中等及以上问题。**

### 1. **低**：「任务」tab 的线索把所有失败都叫「工具失败」，而它数的是工具失败 **+ LLM 错误**

**证据链**（三处互相矛盾）：

- 计数口径：`agent/trace_recorder.py:272-284` 的 `count_failures` → `:275`
  `if step_type == "llm_error"` **也计入**。实测：只有一条 `llm_error` 的 trace
  `count_failures` 返回 `1`。
- 「任务」tab 文案：`web/static/workflow_graph.js:1182-1183` 把该数字渲染成
  「⚠ 本 run 内 N 次**工具失败** →『对话』tab 查看」（`design.md:207` 也是这个措辞）。
- 同一仓库的兄弟出口用的是**准确**措辞：`web/static/workflow_transcript.js:312`
  「⚠ N 条**工具/LLM** 失败（点进去看）」。

**端到端实测**（自建探针，跑完已删；用本 change 自己的 `_BoomLLM`，即它 E2E 验收
用例用的那个 LLM）：

```
run status = failed        trace step types = ['run_started', 'llm_error']
tool_result steps = 0      llm_error steps = 1
snapshot count = 1
「任务」tab hint = '⚠ 本 run 内 1 次工具失败 →「对话」tab 查看'
```

即**一个工具都没失败**、失败的是 LLM 调用（`agent/loop.py:1172-1180` 记录后 re-raise
→ `_mark_failed`），而抽屉**默认**打开的那个 tab 告诉用户「工具失败」。
本 change 自己的端到端用例 `tests/web_tests/test_workflow_control_server.py:254`
断言的正是 `items[0].type == "llm_error"`、`:261` 断言
`node["failure_count"] == evidence["total"]`——三处口径在**同一个用例**里并置。

**影响面（如实说明，这是判「低」而非「中」的理由）**：`llm_error` 一定伴随 run
失败（`record_llm_error` 后立刻 `raise`，全仓无 LLM 重试；`RetryHook` 只包工具，
`agent/loop.py:1295`），所以**可以完成的 run 其失败只可能是工具失败**——本 change 的
核心场景（绿节点内部有失败）里这条文案是**对的**。错只出现在**已经红了的节点**上：
用户看到红色的 run 被告知「工具失败」，而实际是模型/网络错误，排查方向被带偏。

**建议**：`failureCountHint` 复用兄弟出口的措辞（「N 次工具/LLM 失败」）即可，
一行改动；`design.md:207` 的措辞同步订正。**注意 `failureCountHint` 目前无任何
口径断言**（`tests/web_tests/test_workflow_graph_ux_js.py:528-538` 只断言
`⚠`/`次`/三态分离），改文案不会变红，属可选改进。

### 2. **低**：`candidates` 载荷**顶层没有** `failure_evidence`，与 requirement 首段的字面口径不一致

**证据**：spec delta 第 5 行写「Web 服务的 workflow 节点 transcript 只读接口 SHALL
在**同一个载荷中**以键名 `failure_evidence` 提供该 run 的失败证据投影」；第 81-82 行的
Scenario 才把 candidates 形态收敛为「每个候选 SHALL 各自携带」。
实测（自建探针，已删）：

```
fan    kind=candidates  top-level failure_evidence? False
       per-candidate? True
       top-level keys = ['candidates','has_more','kind','limit','node_id',
                         'node_kind','offset','reason_full','reason_length',
                         'reason_truncated','total']
```

即 candidates 载荷**自身没有**该键（其余三形态 `single` / `none` 都有）。
**无功能后果**：前端 `appendFailureEvidence`（`workflow_transcript.js:245-247`）
对缺键是显式跳过，候选行证据由 `renderCandidates`（`:308-318`）逐项渲染，
与 Q5 一致；用例 `test_failure_evidence_key_is_additive_for_all_shapes:1418`
也正是这么断言的。属**规格措辞**问题：一份只读 requirement 首段的人会以为
「任何节点的载荷顶层都有这个键」。
**建议**：在 requirement 首段补半句「（`candidates` 容器形态下该键挂在每个候选上）」，
或把该句限定为「（除容器形态外）」。零代码改动。

### 3. **低**：本轮新增的两条浏览器用例未沿同文件既有的 `_wait_app_ready` 守卫 → 间歇性红

**根因（本轮新定位，解释了 README/记忆里那条「browser 用例偶发 flake」）**：
`tests/web_tests/test_workflow_graph_browser.py:123-137` 的 `_wait_app_ready`
docstring 已写明：`chat.js` 的 ws 握手 → 建 tab → `showView('chat')` 是**异步**的，
可能发生在测试派发 workflow 事件**之后**，把 workflow-view 的 active class 摘掉，
表现为 `#workflow-canvas svg.workflow-svg` **间歇性可见性超时**（`locator resolved
to hidden`）。该文件里 **13 条**用例调用了这个守卫，但**新增的 5 条**
（`test_task_tab_shows_failure_clue_from_snapshot`、
`test_convo_tab_falls_back_when_backend_message_is_missing`，
以及 R2/R3 的 `test_convo_tab_prefers_backend_message`、`candidate_rows_*` 等）
**没调**，只等 `window.AsterwyndWorkflow !== undefined`。

**实测（每条 5–6 次隔离重跑）**：

| 用例 | 单跑失败率 |
|---|---|
| 新增 `..._task_tab_shows_failure_clue_from_snapshot` | 0/5 |
| 新增 `..._falls_back_when_backend_message_is_missing` | **2/5**（第 2、3 次，33s/35s 超时） |
| 既有 `test_workflow_view_auto_opens_and_draws_svg` | **2/5** |
| 既有 `test_workflow_view_desktop_horizontal_layout` | **3/5** |
| 既有 `test_convo_tab_lazily_fetches_transcript` | **5/6** |
| 既有 `test_convo_tab_prefers_backend_message` | 1/6 |

**判「低」的理由**：失败率与**既有**用例同量级甚至更低（既有用例更糟），
增量缺陷很有限，且这是仓库已知的环境性 flake——按本轮审阅口径不报为 issue 主体。
**但**本轮把它**定位到根因并给出可复现的修法**：把两条新用例补上
`await _wait_app_ready(page)`（紧接 `wait_for_function` 之后、`_start_workflow` 之前）
并给 `wait_for_selector` 加 `state="visible"`，实测 **3/3 稳定通过**（同选择下未加时
为间歇红）。建议在改文案时顺手补上，让这两条守护「头号交付物」的断言在 CI 里不靠运气。
**另说明**：R3 报告记录的 `test_convo_tab_lazily_fetches_transcript` 隔离重跑
「1 passed」结论我复现到了同样的通过（2/2），但它 **5/6 单跑会红**——该结论当时
不足以支撑「懒加载契约成立、非 flake」，正确说法是「该断言在**全量**跑下稳定通过
（953 passed），单跑反而不稳」。

### 4. **低**：`_ItemRunSlot.failure_count` 的注释声称被容器快照消费，实际全仓无读取方

**证据**：`agent/subagent/scheduler.py:212-215` 写「与 `NodeState.failure_count` 同口径
——展开项的容器快照**要靠它**显示『这一项里面有没有工具失败』」。但：

- 容器快照读的是 `state.failure_count`（`:2792`，`state` 是 `NodeState`），
  **从不读** `slot.failure_count`；实测容器节点 `failure_count = None`
  （`items_failed = 1`、`item_states = ['completed','failed','completed']`），
  与 R2/R3 记录一致。
- `grep -rn "\.failure_count" agent/ web/`：写入点 `:2207`，读取点只有 `:2792`
  （`NodeState`），`_ItemRunSlot` 那半**只有测试在读**
  （`tests/web_tests/test_workflow_node_transcript.py:1576`）。

R3 已把这条记为「非 issue」并建议补一句 docstring，但 R3 的修复 commit
（`e892e00`）**未触及 `scheduler.py`**，所以注释现在仍是一句**未来时当现在时**的假话
——正是本 change 反复点名的「文档承诺了、实现漂了」同构问题（虽无用户面后果）。
**建议**：把该注释改成事实口径（「当前无消费方，为 #202 的项级线索预留」），
或让容器投影真的带上（`[slot.failure_count for slot in state.item_runs]` 是有界的
小整数数组，不违反快照有界纪律，但属超出本 change 范围）。

**记录（非 issue，本轮复核仍成立）**

- foreach **容器**自身的快照 `failure_count` 恒为 `None`；容器级线索由既有
  `items_failed` 承担（`scheduler.py:2853` → `workflow_graph.js:410` `itemsFailed`
  → `workflow.js:785`/`:842` 消费）。**本轮独立确认该链路是活的**（有真实读取方），
  非「假装覆盖」。
- `design.md:268` 仍写「D1 **六值**枚举是否有过度设计」——该行位于
  「Pre-Implementation Review」**grill 前的历史提问清单**，保留才是对的
  （`design.md:292/362` 与 `proposal.md:102` 已由 R3 订正为**七值**，本轮复查无残留）。
- `web/session.py:869` 起的 `_FAILURE_EVIDENCE_MESSAGES`（后端七态文案）与
  `workflow_graph.js:1129-1137`（前端七态文案）**是两份**，但不是冗余：
  Q6/R2 确立「后端 message 优先、前端表只作兜底」，且有机械防线
  （`test_failure_evidence_text_covers_every_backend_state`，后端新增 state 而前端
  没跟上会变红）。两份措辞不同但七条**语义一致**，已逐条比对，无串台。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/web_tests/ tests/agent/subagent/ -q -p no:randomly` | **953 passed, 7 skipped**，211.97s |
| `pytest tests/web_tests/test_workflow_graph_browser.py -k "renders_failure_evidence_body or task_tab_shows_failure_clue or falls_back_when_backend"` | 首次 **2 failed**（svg 不可见 → 见 Issue 3）；加 `_wait_app_ready` 后 **3/3 passed**（探针，已还原） |
| `pytest .../test_workflow_graph_browser.py -k lazily` （隔离重跑） | **2/2 passed**（5.6s / 6.3s）→ 懒加载契约在**全量与隔离**下均成立 |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **Totals: 30 passed, 0 failed** |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | **review manifest missing** —— 对应 `tasks.md:114`（未勾，预期；manifest 须在 `tasks.md` 最终化后生成） |
| 变异 | **37 条：36 条变红 / 1 条存活**（存活者为纯文案回退，判非假保护，见上） |

**无既有用例**因新增 `failure_evidence` / `failure_count` 键变红。

## Spec Scenario 对齐

对 `specs/web-ui/spec.md`（delta）逐条核对实现与用例：

| Spec 条款 / Scenario | 覆盖 |
|---|---|
| 键名 `failure_evidence`；数据源 = `status != ok` 的 `tool_result` + 全部 `llm_error`；不新增采集 / 不调 LLM / 不写盘 | `web/session.py:770-849` + `agent/trace_recorder.py:258-270`；`test_failure_evidence_projection_is_read_only:1298`（断言 trace 与快照逐字节不变）；真实 HTTP 路由 `test_workflow_control_server.py:219` |
| `state`/`total`/`truncated`/`message`/`items` 五键 | `web/session.py:812-813`；`test_failure_evidence_key_is_additive_for_all_shapes:1418` |
| 七值枚举**且仅**七值 | `web/session.py:759-762`；参数化七值用例 |
| 「没有 trace」与「trace 里没有失败」**不折叠** | 变异 C1/C2/C3 **均被杀** |
| `not_applicable` 与 `unavailable` **不折叠** | `web/session.py:1130/1147-1152`；变异 C5 **被杀** |
| 条目含 `type`/`step`/`status`/`error_type`/`tool_name`/`text_truncated`，文本按类型二选一 | `web/session.py:872-897`；`test_failure_evidence_tolerates_missing_and_empty_fields:1273` |
| `llm_error` 的 `status` 由投影固定 `"error"` | `web/session.py:881`；变异 C13 **被杀** |
| bounded：最近 N / 时间正序 / 单条 ≤ `content_limit` / `truncated` 标量 | `web/session.py:843-847`；变异 C7/C8/C9/C10 **均被杀**；三处 `content_limit` 透传 N9/N9b/N9c **均被杀** |
| 截断或不可用给**可读文案**，不给空列表或 `null` | 载荷 `web/session.py:859-868`；**前端消费**由 N7（后端 message 优先）与 N7b（兜底表）双向守护 |
| SHALL NOT 改变前端取数时机（懒加载） | `web/static/workflow.js:1135-1147` 只读 `node.failure_count`，零 `fetch`；浏览器用例隔离重跑 **2/2 passed** |
| Scenario `present`（completed + 中途工具失败） | `test_failure_evidence_present_on_completed_run_with_tool_failure:991` + 真实路由 `test_workflow_control_server.py:219-261` |
| Scenario `clean`（正向声明） | `:1052`；变异 C1 **被杀** |
| Scenario `running` | `:1073`；变异 C4 **被杀** |
| Scenario `no_trace` | `:1091`；变异 C3 **被杀** |
| Scenario `empty_trace` | `:1107`；变异 C2 **被杀** |
| Scenario `unavailable`（run 记录被弹出 / 未派发） | `:1125` / `:1169`；`test_unknown_node_is_unavailable_not_not_applicable:1678` |
| Scenario `not_applicable`（route / collect） | `:1146`；变异 C5 **被杀** |
| Scenario 条目超上限（最近 N / 真实 total / `truncated` / 正序） | `:1183`；变异 C7/C8/C9 **被杀** |
| Scenario 候选轻量（`items` ≤1、单条 ≤400）；下钻为完整形态 | 投影 `web/session.py:843-844`；`test_candidates_carry_lightweight_failure_evidence:1317`、`test_item_drilldown_carries_full_failure_evidence:1355`；变异 C11/C12 **被杀** |

**未见「spec 写了但没实现」**（本 change 的原始病根）。唯一措辞口径出入是
`candidates` 顶层键（Issue 2），无功能后果、Scenario 已覆盖该形态。

## 变异验证

自建驱动（`mutate.py` / `mutate_core.py`，跑完已删）：改实现 → 跑指定测试 → 记录 →
`finally` 逐字还原并 `assert` 复原成功。**37 条：36 条变红 / 1 条存活（纯文案回退）。**

分类口径：浏览器文件的已知 flake 特征是
`TimeoutError: Page.wait_for_selector … svg.workflow-svg`（app 异步初始化的竞态，
见 Issue 3）。仅当红灯定位在这个选择器上才算「flake-red」，否则算真红——
N1/N6c 的定位器分别是 `.failure-item` / `.drawer-failure-hint`（只有对应代码被删才会缺），
且我已 **3× 复现**确认。

### A. R3 声称的四条保护（本轮最重点，逐条独立复跑）

| # | 变异（改了哪行） | 所跑测试 | 结果 |
|---|---|---|---|
| N1 | `workflow_transcript.js:262` 条目列表 → `[]` | browser `-k renders_failure_evidence_body` | **变红** ✓（3/3，等待 `.failure-item`） |
| N2 | `:265` 失败文本 → `null` | 同上 | **变红** ✓（`预览截断没有标注…`） |
| N3 | `:274` 截断页脚 → `if (false)` | 同上 | **变红** ✓（`截断页脚缺失…`） |
| N4 | `:257-259` 标题去掉真实条数 | 同上 | **变红** ✓（`标题丢了真实条数：'失败证据'`） |
| N4b | 标题改用**返回条数** | 同上 | **变红** ✓（`共 2 条` ≠ `共 9 条`） |

### B. R3 新增/顺带修的两处

| # | 变异 | 所跑测试 | 结果 |
|---|---|---|---|
| N5 | `workflow_graph.js:1166` 去掉摘要 120 上限 | browser `-k renders_failure_evidence_body` | **变红** ✓（`条目摘要无界：465 字符`） |
| N5b | `:1166` 上限放宽到 500 | 同上 | **变红** ✓（同一条断言） |

### C. R2/R3 低危修复的洞（本轮独立复现）

| # | 变异 | 所跑测试 | 结果 |
|---|---|---|---|
| N6 | `workflow.js:1140`「任务」tab 线索整段关掉 | browser `-k task_tab_shows_failure_clue` | **变红** ✓ |
| N6b | `workflow_graph.js:1180-1181` `None` 折进 `0` | browser + ux_js | **变红** ✓（ux_js 层） |
| N6c | `workflow.js:1143` 高亮类去掉 | browser（同上） | **变红** ✓（3/3，等待 `.drawer-failure-hint`） |
| N7 | `workflow_transcript.js:241` 不读后端 message | browser `-k prefers_backend_message` | **变红** ✓ |
| N7b | `:242` 去掉兜底表 | browser `-k falls_back_when_backend` | **变红** ✓（R3 前存活） |
| N8 | `session.py:752` 终态集删 `queue_full` | `-k queue_full_run_is_not_reported` | **变红** ✓ |
| N8b | 在 `_foreach_candidates` 内联**少一个 `queue_full`** 的等价集合 | `-k queue_full` | **变红** ✓（**这正是 R3 报的存活写法**） |
| N9 | `session.py:1016` 下钻去 `content_limit` | `-k content_limit or drilldown` | **变红** ✓（R3 前存活） |
| N9b | `:1177` single 去 `content_limit` | `-k content_limit` | **变红** ✓ |
| N9c | `:1234` candidates 去 `content_limit` | `-k content_limit` | **变红** ✓ |
| N10 | `:269` 截断措辞**回退**成旧谎话 | browser `-k renders_failure_evidence_body` | **存活** ✗（纯文案，非假保护，见 R3 低-5） |
| N11 | `:267` 去掉 `<pre>` 的 300 截断 | browser（同上） | **变红** ✓（`预览未收窄：429 字符`） |

### D. 核心不变式（不采信上轮结论，全部重跑）

| # | 变异（`agent/`/`web/`） | 结果 |
|---|---|---|
| C1 | `clean` → `no_trace` 折叠（`session.py:838`） | **变红** ✓ |
| C2 | `empty_trace` → `no_trace` 折叠 | **变红** ✓ |
| C3 | `no_trace` → `clean` 折叠 | **变红** ✓ |
| C4 | 删 `running` 判定 | **变红** ✓ |
| C5 | collect 的 `not_applicable` → `unavailable` | **变红** ✓ |
| C6 | `_ASSERTABLE_STATES` 放宽（fail-fast 弱化） | **变红** ✓ |
| C7 | 最近 N 条 → 最早 N 条 | **变红** ✓ |
| C8 | `total` 改成返回条数 | **变红** ✓ |
| C9 | `truncated` 标量恒 False | **变红** ✓ |
| C10 | `text_truncated` 恒 False | **变红** ✓ |
| C11 | 轻量形态去掉 400 上限 | **变红** ✓ |
| C12 | candidates 改完整形态（体积放大） | **变红** ✓ |
| C13 | `llm_error.status` 不合成 | **变红** ✓ |
| C14 | 失败判据收窄成 `== "error"` | **变红** ✓ |
| C15 | `count_failures` 空 trace 返回 `0` | **变红** ✓ |
| C16 | 快照 `failure_count` 写死 `0` | **变红** ✓ |
| C17 | 删 `_reset_subtree` 的 `failure_count = None` | **变红** ✓ |
| C18 | 删 `_launch_run` 计数埋点（写 `None`） | **变红** ✓ |

### E. 前端文案覆盖

N10（唯一存活）之外的文案层均有守护：七态文案表完整性
（`test_failure_evidence_text_covers_every_backend_state`，后端加 state 前端没跟上即红）、
未知 state 可读降级（`test_failure_evidence_text_degrades_readably_for_unknown_state`）、
摘要单行（`test_failure_item_summary_shows_tool_step_and_error_type`）。
**注意**：`failureCountHint` 的**具体措辞**（「工具失败」）无单独断言——
这正是 Issue 1 建议改动时不会变红的原因，也说明 Issue 1 是**遗留措辞**而非
「改坏了测试」。

## 结论

R3 的全部修复（1 中 + 7 低）**逐条经独立变异验证成立**，其中最关键的
「头号交付物正文区」四条保护**真的变红**（N1–N4），R3 顺带发现并修掉的
`failureItemSummary` 无界问题是**真 bug 且真被锁住**（N5/N5b），D7 守卫从文本匹配
改成行为断言后连「内联等价漂移」也抓得住（N8b）。核心 18 条不变式我全部重跑，
18/18 被杀，**无一假保护**。

本轮新发现 4 条**低**：①「任务」tab 线索把 `llm_error` 也叫「工具失败」
（只在已失败的节点上误导，规格与兄弟出口都已用「工具/LLM」措辞，一行可改）；
② `candidates` 载荷顶层无 `failure_evidence`（与 requirement 首段字面口径出入，
无功能后果，补半句规格即可）；③ 新增两条浏览器用例未沿同文件既有 `_wait_app_ready`
守卫，间歇红（**本轮定位到根因并验证修法 3/3 稳定**，与既有用例同病且更轻）；
④ `_ItemRunSlot.failure_count` 注释声称被容器快照消费，实际全仓无读取方（R3 已记、
未修）。四条**均不阻塞**。

按判据校准，本轮**没有**发现「用户看到错的东西且后果面大」「承诺未兑现」
或「假保护」级别的问题，故判 **PASS**。

**给开发方的两条合入前建议（可选，不影响 verdict）**：
1. 把 `design.md:207` 与 `workflow_graph.js:1182-1183` 的「工具失败」改成
   「工具/LLM 失败」（Issue 1，一行）。
2. 给两条新浏览器用例补 `await _wait_app_ready(page)`（Issue 3，让头号交付物的
   断言在 CI 里不靠运气）。

**合入前仍需完成**（`tasks.md` 未勾项，非本次审阅缺陷）：spec delta 合入
`openspec/specs/web-ui/spec.md`、backlog 移除、生成 review manifest（须在
`tasks.md` 最终化后）、跑 OpenSpec strict validate + artifact checker + benchmark smoke、
归档到 `openspec/changes/archive/2026-09-23-fix-issue-215-node-failure-evidence/`。
