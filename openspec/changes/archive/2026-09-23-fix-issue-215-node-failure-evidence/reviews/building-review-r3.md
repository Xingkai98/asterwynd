# Building Review: fix-issue-215-node-failure-evidence（Round 3）

## Reviewer
- run id: review-subagent-215-r3
- 时间: 2026-09-23
- 审阅范围: `1a7df92cbd90ab442342a8481d59857b8c4ebf54`..`80d2c2bd11a352908099beb0d88c35b9b4f09cdf`
- 工作目录: `/tmp/rev-215`（隔离检出）。**审阅结束时已删除自建探针脚本（`mutate.py` /
  `probe_r3.py` / `probe_r3b.py` / 两条临时浏览器用例）并 `git checkout -- .`**，
  `git status --short` 只剩 `?? .venv`（paseo 预置的软链）与本报告。

## Verdict
**CHANGES_REQUESTED**

理由（先说结论，再给证据）：

1. **R2 的两条中等问题都真的修好了**，且**这次有可失败证据**（M1 杀「前端不读后端
   message」、M2/M20/M26 杀候选行渲染块的三条路径）——不是只看 diff 说通过。
   R2 的四条低危（3/4/5/6）也逐条落地（M22/M23/M5/M4/M34/M6 被杀，文档口径已统一）。
2. **但同一类覆盖缺口在「对话」tab 的 `single` 形态证据**正文区**仍然存在，且面比 R2 那条更大**：
   我把「条目列表整段删掉」「文本整段删掉」「截断页脚删掉」「标题里的真实条数删掉」四条变异
   分别灌进**浏览器全量 + 非浏览器 137 条**测试，**全部存活**（M39/M40/M41/M32/M33）。
   这一段正是本 change 的**头号交付物**——用户读到「哪个工具失败了、为什么」的文本就长在这里；
   而 Q2（用户已确认）专门要求的「前端预览 ~300 字符 + 显式截断标注」也落在这一段里没有任何
   测试。按 R2 对同构问题（候选行渲染块零覆盖）判**中**的先例，这里同样是**中**，不是可改进项。
3. 另 3 条低（下钻挂载点的 `content_limit` 透传无覆盖、R2 补测只覆盖三处里的两处；
   「任务」tab 快照线索整段可被静默关掉；单源常量的守卫是**文本匹配**而非语义，
   等价的漂移写法存活）——见 Issues 2/3/4，均**不阻塞**。
4. 其余维度**没有发现问题**：20+ 条核心不变式变异全被杀；无安全漏洞（新增前端渲染**全部**
   走 `textContent`/`el()`，`workflow*.js` 里 `innerHTML` 零命中）；无 CI 弱化；
   既有键语义未变；spec delta 逐条有实现与用例，**未见「写了但没实现」的条款**；
   懒加载契约在隔离重跑下成立（`test_convo_tab_lazily_fetches_transcript` 1 passed）。

## Round 1 / Round 2 修复验证

逐条**跑测试 / 构造反例**验证（不只看 diff）：

### R1-1（中）`failure_count` 逃过 `_reset_subtree` → **真的修好了**

`agent/subagent/scheduler.py:1697`。**变异验证**：删掉该行 → `-k failure_count`
**变红**（1 failed）。`tests/agent/subagent/test_terminal_honesty.py:735/743` 五条独立断言
（`status`/`reason`/`summary`/`finished_at`/快照 `failure_count is None`），不是恒真。

### R1-2（低）未知 `state=` 静默穿透 → **本次改为 fail-fast，真的修好了**

`web/session.py:823-831` 现在只接受 `_ASSERTABLE_STATES = {not_applicable, unavailable, running}`，
其余一律 `ValueError`。**变异验证**：把该 frozenset 扩进 `present`/`clean` → M4 **变红**；
把守卫换成 `pass` 的旧形态已被 `test_failure_evidence_rejects_unknown_explicit_state` 覆盖。
**独立复检「枚举内仍静默」这一半**（R2 Issue 5）：已消除——`present`/`clean`/`empty_trace`/
`no_trace` 现在**显式传入即报错**（探针实测四个取值全抛 `ValueError`），
不再是「三个被尊重、其余被忽略」的混合语义。

### R1-3（低，R2 判为未完成）候选行负向态渲染块 → **真的修好了，且有可失败证据**

实现 `web/static/workflow_transcript.js:296-318`；fixture 补了 `clean` 与 `present` 两种态
（`tests/web_tests/test_workflow_graph_browser.py:509/514`）；用例 `:869`。

- **变异验证**：删掉负向态分支（`:313` 的 `else if` → `else if (false)`）→ **变红**
  （1 failed, 21 passed，90s）；整个证据块守卫关掉（`:296` 的 `if (evidence)` → `if (false)`）
  → **变红**（1 failed）；只删正向计数线索（`if (evidence.total > 0)` → `if (false)`）→ **变红**
  （1 failed, 21 deselected）。R2 的两条存活变异**现在都被杀**。
- **独立复核「两种态是否真的都可见、有无重复或冲突」**：探针（已删）实测候选行文本
  `#0 … ok已检查，无失败记录。completed` 与
  `#1 … RuntimeError: boom⚠ 3 条工具/LLM 失败（点进去看）failed`——两者互斥（`total > 0`
  走计数线索、否则走文案），**无语义冲突**；候选行**不展开条目**（正文留给下钻），与 Q5 一致。

### R2-2（中）`failure_evidence.message` 前端零消费 → **真的修好了**

`web/static/workflow_transcript.js:239-243` 的 `failureText(evidence)` 优先取后端 `message`，
三处调用点（`:252` 负向态单行、`:261` 正文、`:315` 候选行）全部改走它。
**变异验证**：把「优先取 message」那行改成 `if (false)` → M1 **变红**（1 failed）。
**独立复核「前端兜底表是否变成死代码」**：不是死代码——它仍在**后端没给 message**时兜底
（老载荷 / 后端降级）；我构造「删掉兜底 return」的变异 M35 **存活**，说明该兜底分支**无测试**，
但它只在后端违约时才走，属**低**（Issue 4）。
**独立复核 D1 要求的那处区分是否真的到了 UI**：`test_convo_tab_prefers_backend_message` 用一句
**只有后端会写**的「该节点尚未派发，暂时没有失败证据。」断言它被渲染（`:948`），实测通过。

### R2-3（低）`content_limit` 未透传 → **三处里透传了两处，第三处无覆盖**

`web/session.py:1016`（下钻）/`:1177`（single）/`:1234`（candidates）三处均已传参。
**变异验证**：
- 删 **single** 挂载点的 `content_limit=content_limit` → M22 **变红**；
- 删 **candidates** 挂载点的 → M23 **变红**；
- 删 **下钻** 挂载点的（M3）→ `-k content_limit` **2 passed，存活 ✗**。

即 R2 的修复**本体正确**，但「三处透传」这一命题**只有两处被测试锁住**，下钻那处可被静默回退。
R2 commit message 如实写了「三处传参 + 两条用例」，故不算假声明，见 Issue 2（低）。

### R2-4（低）D7 常量副本 → **引用统一了，但守卫是文本匹配**

`web/session.py:1214` 已改引 `_TERMINAL_RUN_STATUSES`。**变异验证**：
- 把 `:1214` 改回**逐字还原原内联写法** → M34 **变红**（
  `test_terminal_run_statuses_has_a_single_source` 的字符串包含检查命中）；
- 改成**语义等价但字面不同的**内联集合（少 `queue_full`）→ M31 **存活 ✗**
  （`-k terminal_run_statuses` 1 passed）。

即「模块常量与候选判据一致」这条不变式只有**字面**守卫，语义漂移仍可能发生，
且 `queue_full` 那半在候选路径上**零语义测试**（`grep queue_full tests/web_tests/` 只有
注释与这条字符串断言）。见 Issue 4（低）。

### R2-5（低）显式 `state=` 混合语义 → **见 R1-2，已改为整体 fail-fast，修好了**

### R2-6（低）`no_trace` 口径打架 + `tasks.md` 已做未勾 → **修好了**

- 口径：`diagnosis.md:157-167` 新增「Grill 订正（2026-09-23）」表并订正成因段
  （`empty_trace` 两处调用点 `manager.py:1086`/`:1100`、`no_trace` 防御性口径、
  `queue_full` 弹出点 `manager.py:1035`），`docs/openspec-change-backlog.md:155-160` 同步。
  **我逐条复核了这些行号**：`manager.py:1035` 确为 `session.runs.pop()`、`:1086`/`:1100` 确为
  两处空 `TraceRecorder`、`:1524` 确为 `_mark_budget_exceeded(..., "time", None)` 且
  其 `if run.status == "queued"`（`:1522`）在 `_start_task` 先置 `running` 后恒假——
  **订正后的口径与代码一致，未引入新的自相矛盾**。
- `tasks.md:100` / `:103` 已勾；`workflow-events.jsonl` seq 3 有 `protected_artifact_explained`
  解释事件覆盖 backlog 改动。

## Tasks Verification

对照 `tasks.md` 每个 `[x]` 读代码/跑测试确认（只列有实质结论的；行号为当前 HEAD）：

- [x] grill 前置（独立零记忆 subagent + 停轮确认 Q1–Q7）→ `reviews/grill-design.md` 有 6 条
      Confirmed Decisions 与 `## User Confirmation`（7/7 确认，且**每条都配了真实场景例子**，
      符合 AGENTS.md 的「每条 Open Question 必须配一个具体例子」硬要求）
- [x] 常量五件套（`FAILURE_EVIDENCE_LIMIT=5` / `FAILURE_EVIDENCE_PREVIEW_LIMIT=400` /
      `_TERMINAL_RUN_STATUSES` / `FAILURE_EVIDENCE_STATES` 七值 / `_ASSERTABLE_STATES`）
      → `web/session.py:741/745/751/759/767`
- [x] `_failure_evidence(...)` 只遍历不复制、判据在 `agent/trace_recorder.py:258-284`
      → `web/session.py:770-855`；`iter_failure_steps` 变异（判据收窄成 `== "error"`）**被杀**（M24）
- [x] 七态 + 各负向态文案 → `web/session.py:826-847`（`settle`）+ `:859-868`；
      `test_every_failure_evidence_state_has_a_distinct_readable_message` 参数化七值
- [x] 条目 bounded（最近 N、时间正序、`text_truncated`、`llm_error.status` 合成）
      → `web/session.py:843/872-897`；变异 M8/M9/M10/M27 **均被杀**
- [x] 三态分支挂载 → `single` `:1177`；`candidates` `:1234`；`none` `:1090`（state is None）/
      `:1130`（route）/`:1147`（collect 与未派发）；下钻 `:1016`
- [x] 终态判据单源（D7）→ `web/session.py:751-752` + `:1214`；
      **但守卫是文本匹配**（Issue 4）
- [x] `NodeState` / `_ItemRunSlot` 计数字段 → `agent/subagent/scheduler.py:257` / `:215`
- [x] 埋点在 `_await_run` 之后、每 run 一次、`queue_full` 早退绕过 →
      `agent/subagent/scheduler.py:2175-2177`、`:2134-2145`；变异 M16 **被杀**
- [x] `_graph_node_projection` 投影 → `agent/subagent/scheduler.py:2792`
- [x] 前端「对话」tab 挂载 → `web/static/workflow_transcript.js:119`（调用）/`:245-278`（实现）；
      **正文区无覆盖**（Issue 1）
- [x] 前端纯函数 → `web/static/workflow_graph.js:1124-1180`；`None`/`0` 折叠变异 M19 **被杀**
- [x] 「任务」tab 一行快照线索（零请求）→ `web/static/workflow.js:1137-1147`；
      **整段无覆盖**（Issue 3）
- [x] 样式 → `web/static/style.css:1753-1778`
- [x] 测试清单：`tests/web_tests/test_workflow_node_transcript.py:989-1812`、
      `test_workflow_graph_ux_js.py:500-565`、`test_workflow_graph_browser.py:869-943`
      逐条找到对应用例；**除「对话」tab 证据正文区外**断言非恒真
- [x] 回归 `tests/web_tests/` + `tests/agent/subagent/` → 见「Test Results」
- [x] `diagnosis.md` 6 章 + Grill 订正表 → `diagnosis.md:145-167`
- [x] 关键词扫描 → `docs/architecture.md:106` 新增「失败证据投影」一段（git diff 可见）
- [x] `docs/known-debt.md:276-295` 两条死代码发现 + seq 2 解释事件
- [ ] `tasks.md:97/98`（spec 同步）/`:105`（backlog 移除）/`:112`（manifest）/`:116-120`（验证）/
      `:123-125`（收尾）：核对后**诚实**——`openspec/specs/**` 本次零改动
      （`git diff --name-only origin/master...HEAD` 无该路径），与两条未勾一致；
      review manifest 确实不存在（artifact checker 实测报 `review manifest missing`）。
      `:123`（归档）与 `:125`（关 issue）无 `(post-merge)` 标记——归档门禁要求
      closeout 类任务标注，`:125` 已标，`:123` 是归档动作本身（归档时完成）故无需标。

## Issues

### 1. **中**：「对话」tab 的 `single` 形态**失败证据正文区**零测试覆盖 —— 本 change 头号交付物无人守护

**证据**（四条变异，各自与实现在同一处，全部存活）：

| 变异 | 改了哪行 | 所跑测试 | 结果 |
|---|---|---|---|
| M40 | `web/static/workflow_transcript.js:262` `(evidence.items \|\| []).forEach` → `[].forEach`（**整段条目渲染关掉**） | `tests/web_tests/test_workflow_graph_browser.py`（全量浏览器） | **22 passed，未变红 ✗** |
| M39 | 同上 | `test_workflow_node_transcript.py` + `test_workflow_control_server.py` + `test_workflow_graph_ux_js.py` + `test_workflow_graph_server.py`（**137 条非浏览器**） | **137 passed，未变红 ✗** |
| M32 | `:265` `const text = item.observation \|\| item.message;` → `const text = null;`（**失败文本整段不渲染**） | 同 M40 的口径 + 下钻用例 | **3 passed，未变红 ✗** |
| M41 | `:274` `if (evidence.truncated) {` → `if (false) {`（**截断页脚关掉**） | 浏览器全量 + ux_js 全量 | **68 passed，未变红 ✗** |
| M33 | `:257-259` 标题去掉真实条数（`失败证据（共 N 条）` → `失败证据`） | 浏览器两条证据用例 | **2 passed，未变红 ✗** |

**覆盖缝定位**：
- `tests/web_tests/test_workflow_graph_browser.py` 的三个载荷 fixture 里，只有
  `_ITEM_CONTAINER`（候选：`:509`/`:514`）与 `test_convo_tab_prefers_backend_message` 的
  `kind: "none"` 载荷（`:915`）带 `failure_evidence`；**`_ITEM_SINGLE`（`:522-535`）没有该键**，
  所以「下钻到单项」这条唯一能渲染出**条目正文**的路径，在浏览器用例里被 `if (!evidence) return;`
  静默跳过。
- `test_workflow_graph_ux_js.py:500-565` 只锁**纯函数**（`failureEvidenceText(s)` /
  `failureItemSummary` / `failureCountHint`）本身，**不锁 DOM 装配**。
- `test_workflow_node_transcript.py` / `test_workflow_control_server.py` 锁的是**载荷**，
  对渲染零知情。

**反面证明该区是 live 且渲染正确**（不是死代码，所以不能按「未使用」豁免）：我在隔离检出里
临时加了一条探针用例（**已删除**，未留痕），给下钻载荷塞入 `present / total=9 / truncated=true`
与两条条目（`tool_result` + `llm_error`），实测 `.drawer-body` 文本为：

```
失败证据（共 9 条）该 run 已结束；其执行记录里有失败步骤（下面是最近的几条）。
Bash · step 7 · tool_error · 3 failed, 12 passed（文本已截断）3 failed, 12 passed预览已截断，全文见本条记录。
（未知工具） · step 9 · network_timeout · upstream timed outupstream timed out共 9 条，只显示了最近 2 条。
```

即实现**正确**，缺的是「没有任何测试能证明它还在」。

**为什么必须修（为什么是「中」而不是「低」）**：
- 这是本 change 的**立项动机落地处**——issue #215 要回答的就是「哪个工具失败了、为什么」，
  而**答案的正文只长在这段代码里**。删掉整段（M40）或删掉文本（M32），全套 949 条测试全绿，
  用户回到「绿节点、零信号」的原始症状，**没有任何机械防线**。这正是 issue #215 立项时点名的
  失败模式（「文档承诺了、实现漂了」）。
- 这段里还压着一条**用户已确认的决策**：grill Q2 的「前端预览另设 ~300 字符短上限 + 显式标注
  截断」——`web/static/workflow_transcript.js:266-270` 就是它。删掉那条 note（对应
  `item.text_truncated || text.length > 300` 分支）同样全绿。而「预览比正文短却不告知」
  正是本仓库**已踩过两次**的坑（issue #212 / #213，`web/session.py:_bounded_messages` 的
  docstring 明写「只比较本层长度会谎报完整」）。
- 与 R2 的判据**同构且面更大**：R2 判「候选行失败线索渲染块零覆盖」为**中**并打回；
  本次这条是 `single` 主路径上**更大**的一段（5 条独立变异存活），按同一标准不能降级。

**建议（最小修法，不新增浏览器基础设施）**：给 `tests/web_tests/test_workflow_graph_browser.py`
的 `_ITEM_SINGLE`（`:522`）补上一条 `present / truncated=True` 的 `failure_evidence`（含
`tool_result` 与 `llm_error` 各一条、其中一条文本 > 300 字符），并加一条断言：
下钻后 `.drawer-body` 里出现**工具名 + 错误文本首行**、出现「预览已截断」note、
出现「共 N 条，只显示了最近 M 条。」页脚。这样 M32/M33/M40/M41 四条变异会同时变红
（我已在探针里验证过这四种渲染确实发生，断言可以直接照抄上面的实测文本）。

### 2. **低（不阻塞）**：下钻挂载点的 `content_limit` 透传无测试锁定

**证据**：变异 M3（删掉 `web/session.py:1016` 的 `content_limit=content_limit`）→
`pytest tests/web_tests/test_workflow_node_transcript.py -k content_limit` **2 passed，存活**。
R2 的修复本体正确（三处都传了），但补的两条用例
（`test_failure_evidence_honours_content_limit` 走 `single`、
`test_failure_evidence_content_limit_applies_to_candidates` 走候选）
**都不经过 `_item_drilldown_payload`**，第三处可被静默回退。
**建议**：给 `test_item_drilldown_carries_full_failure_evidence` 加 `content_limit=100`
并断言条目长度 ≤ 100（一行），或另加一条。

### 3. **低（不阻塞）**：「任务」tab 的快照失败线索整段无覆盖

**证据**：把 `web/static/workflow.js:1140` 的 `G.failureCountHint(node.failure_count)` 改成
`null`（M28）→ 浏览器全量 + ux_js 全量 **68 passed，未变红**；把 `:1143` 的
`drawer-failure-hint` 高亮类去掉（M29）→ 浏览器全量 **22 passed，未变红**。
即 Q6 方案 D 里「`N>0` 显示 ⚠ 计数、`0` 显示淡色、`None` 不显示」这三态**在 DOM 层没有任何断言**，
只有纯函数 `failureCountHint` 被 ux_js 锁住（M19 被杀）。
**可达性说明**：`SNAPSHOT` fixture（`:69-89`）的节点没有 `failure_count` 键，所以
`failureCountHint(undefined)` 恒返回 `null`、整段被跳过——与 R2 那条 fixture 缝**完全同构**。
**建议**：给 `SNAPSHOT` 的一个节点补 `"failure_count": 3`、另一个补 `0`，加一条断言
「任务」tab（抽屉默认 tab）文本含 `⚠` 与 `已检查、无失败`——这条同时能覆盖 Q6 的
「零请求」不变量（不需要新 fixture）。

### 4. **低（不阻塞）**：D7 单源守卫是**文本匹配**，语义等价漂移存活；`failureText` 兜底分支无覆盖

**证据（D7）**：`tests/web_tests/test_workflow_node_transcript.py:1790-1800` 靠
`assert inline not in source` 检查三个**字面字符串**。把 `web/session.py:1214` 改回**逐字**
原内联写法 → M34 **变红**（字符串命中）；改成**少一个 `queue_full` 的集合字面量** → M31 **存活**。
即守卫只禁止「某一种拼法」，防不住 R2 Issue 4 真正担心的那件事（**取值集合漂移**）——
而 `queue_full` 在候选路径上确实**零语义测试**（`grep queue_full tests/web_tests/` 只命中注释
与本断言自身）。建议把断言从「源码里不得出现某字符串」改成**行为断言**：
构造一个 `status="queue_full"` 的 run，断言 `_foreach_candidates` 不把它改写成 `queued`
（`test_terminal_honesty.py` 已有三副本一致性用例族，可挂在那里）。

**证据（failureText 兜底）**：把 `web/static/workflow_transcript.js:242`
`return G.failureEvidenceText(evidence && evidence.state);` 整行删成 `return '';`（M35）→
浏览器 + ux_js 全量 **68 passed，存活**。该分支只在「后端没给 message」时走（老载荷 / 降级），
属防御性路径，**低**。（对照：优先取 message 那一半有 M1 守护，是活的。）

### 5. **低（不阻塞）**：「预览已截断，全文见本条记录。」指向一处 UI 里并不存在的「全文」

`web/static/workflow_transcript.js:269` 写的这句承诺了「本条记录」里有全文，但实际上：
载荷 item 文本上限是 `content_limit`（默认 4000），前端只渲染 300 字符，**界面里没有任何入口
能读到那 4000**（载荷里没有「展开全文」出口，`_failure_item` 也不带原文）。
这与本 change 反复强调的「不给用户假话」自相矛盾，也是 #213 那一类坑的镜像
（#213 修的是「截断不告知」，这里变成「告知了一个取不到的全文」）。
**建议**：改成事实表述（如「预览已截断（最多 300 字符）」），或把 grill Q2 原话里
「全文见『对话』tab」的口径一并订正——**注意 Q2 原文那句同样不成立**（此处**就是**「对话」tab），
建议在 design.md 的 Q2 行补一句「前端预览上限与 note 措辞落地为『预览已截断（最多 300 字符）』」。

### 6. **低（不阻塞）**：同 change 内仍有三处「六值」旧口径未随 Q4 订正

- `openspec/changes/fix-issue-215-node-failure-evidence/proposal.md:102`：design impact 仍写
  「**状态枚举六值**（`present` / `clean` / `running` / `empty_trace` / `no_trace` / `unavailable`）」，
  与同一 change 的 `design.md:102-117`（七值，含 `not_applicable`）与 spec delta 打架。
- `design.md:292` / `design.md:362`（两处 Risks 表）：「六个状态取值被后续改动悄悄合并」——
  同一张表下面的缓解措施说的却是七值语义。
- `design.md:268` 属「Pre-Implementation Review」的历史提问清单（「六值是否有过度设计」），
  **保留合理**（那是 grill 前的快照），无需改。

R2 Issue 6 只订正了 `diagnosis.md` 与 `backlog.md`，**漏了 proposal.md 与 design.md 的这两处**。
影响有限（spec delta 自身口径正确），但属本 change 自己点名的「文档承诺了、实现漂了」的同构问题。
**建议**：把 proposal.md:102 与 design.md:292/362 的「六」改成「七」并补 `not_applicable`。

**记录（非 issue，与 R2 同结论，本次复核仍成立）**
- foreach **容器**自身的快照 `failure_count` 恒为 `None`（探针实测：
  `{'failure_count': None, 'items_failed': 1, 'item_states': ['completed','failed','completed']}`），
  因埋点写的是 `_ItemRunSlot` 而容器没有单一 run。**符合 Q6 设计**（容器级线索由既有
  `items_failed` 承担，前端 `web/static/workflow_graph.js:410` 已消费）。但
  `_ItemRunSlot.failure_count`（`scheduler.py:215`）全仓**仍无任何读取方**
  （`grep` 确认：写 `:2207`，读只有测试），`tasks.md:51` 与
  `test_snapshot_failure_count_covers_foreach_items` 合起来会让读者误以为容器快照覆盖了展开项计数。
  建议在该字段 docstring 补一句「当前无消费方，为 #202 预留」。
- `_resolve_run` 直接访问 `manager._sessions`（`web/session.py:903-906`）：与 R1/R2 同结论，
  可接受（docstring 给了理由，回落语义与 `inspect_transcript` 同口径），且有
  `test_drilldown_without_run_id_still_resolves_the_run` 锁定（M21 被杀）。
- 我在**全量** `tests/web_tests/` + `tests/agent/subagent/` 下未观察到任何失败
  （949 passed / 7 skipped，一次跑通），R2 记录的
  `test_workflow_view_desktop_horizontal_layout` flake 本次未复现。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/web_tests/ tests/agent/subagent/ -q -p no:randomly` | **949 passed, 7 skipped**，369.35s |
| `uv run pytest tests/web_tests/test_workflow_node_transcript.py -q` | **75 passed** |
| `uv run pytest tests/web_tests/test_workflow_graph_browser.py -q -k lazily`（隔离重跑） | **1 passed**（16.47s）→ 懒加载契约成立，非 flake |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **Totals: 30 passed, 0 failed (30 items)** |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | **exit 1**：`review manifest missing: …/reviews/building-review-manifest.json` —— 对应 `tasks.md:112`（未勾，预期；manifest 须在 `tasks.md` 最终化之后生成） |
| 全部变异 | 41 条（40 条有效）：**31 变红 / 9 存活**。存活即 Issue 1（5 条）、Issue 2/3/4（4 条） |

**无既有用例**因新增 `failure_evidence` / `failure_count` 键变红；浏览器用例本次**无 flake**。

## Spec Scenario 对齐

对 `openspec/changes/fix-issue-215-node-failure-evidence/specs/web-ui/spec.md` 逐条核对实现与用例：

| Spec 条款 / Scenario | 覆盖 |
|---|---|
| 载荷以 `failure_evidence` 提供投影；数据源是 `status != ok` 的 `tool_result` + 全部 `llm_error`；不新增采集/不调 LLM/不写盘 | `web/session.py:770-855` + `agent/trace_recorder.py:258-284`；`test_failure_evidence_projection_is_read_only:1296`（断言 trace 与快照逐字节不变）；端到端 `test_workflow_control_server.py:219` |
| 键名 `state`/`total`/`truncated`/`message`/`items` | `web/session.py:812-813`；`test_failure_evidence_key_is_additive_for_all_shapes:1405` |
| 七值枚举**且仅**七值 | `web/session.py:759-762`；参数化七值用例 + `not_applicable` 与 `unavailable` 分离 |
| `not_applicable` 与 `unavailable` 不折叠 | `web/session.py:1130` / `:1147-1152`；变异 M30（collect → unavailable）**被杀** |
| 条目含 `type`/`step`/`status`/`error_type`/`tool_name`/`text_truncated`，文本按类型二选一 | `web/session.py:872-897`；`test_failure_evidence_tolerates_missing_and_empty_fields:1271` |
| `llm_error` 的 `status` 由投影固定 `"error"` | `web/session.py:881`；变异 M10 **被杀** |
| bounded：最近 N 条 / 时间正序 / 单条 ≤ `content_limit` / `truncated` 标量 | `web/session.py:843-847`；变异 M8/M9/M22/M27 **均被杀**；下钻那处见 Issue 2 |
| 不可用/截断给**可读文案**，不给空列表或 `null` | 载荷满足（`web/session.py:859-868`，`settle` 成对取文案；变异 M6 杀「message 与 state 串台」）；**前端消费**由 M1 守护 |
| SHALL NOT 改变前端取数时机（懒加载） | `web/static/workflow.js:1115-1147` 区间 `fetch`/`XMLHttpRequest` **零命中**；浏览器用例隔离重跑 **1 passed** |
| Scenario: `present`（completed + 中途工具失败） | `test_failure_evidence_present_on_completed_run_with_tool_failure:989` + 真实 HTTP 路由 `test_workflow_control_server.py:219-261` |
| Scenario: `clean`（正向声明） | `test_failure_evidence_clean_is_a_positive_statement:1050`；变异 M12 **被杀** |
| Scenario: `running` | `test_failure_evidence_running_is_not_no_trace:1071`；变异 M18 **被杀** |
| Scenario: `no_trace` | `test_failure_evidence_no_trace_when_terminal_without_trace:1089`；变异 M17 **被杀** |
| Scenario: `empty_trace` | `test_failure_evidence_empty_trace_is_not_no_trace:1105`；变异 M13 **被杀** |
| Scenario: `unavailable` | `test_failure_evidence_unavailable_when_run_record_is_gone:1123` + `test_unknown_node_is_unavailable_not_not_applicable:1665` |
| Scenario: `not_applicable` | `test_failure_evidence_not_applicable_for_route_and_collect:1144`；变异 M30 **被杀** |
| Scenario: 条目超上限（最近 N / 真实 total / truncated / 正序） | `test_failure_evidence_returns_most_recent_n_in_time_order:1181`；变异 M8/M27 **被杀** |
| Scenario: 候选集只带轻量证据（`items` ≤1、单条 ≤400）；下钻为完整形态 | 投影层 `web/session.py:843-844`；变异 M11/M38（轻量上限）、M37（下钻改轻量）**均被杀**；`test_candidates_carry_lightweight_failure_evidence:1315`、`test_item_drilldown_carries_full_failure_evidence:1353` |

**未见「spec 写了但没实现」的条款**（本 change 的原始病根）。spec 只约束**载荷**，
故 Issue 1 是覆盖缺口而非 spec 违规——但它守的是 Q2 那条**用户已确认的前端**决策。

## 变异验证

自建驱动（`mutate.py`，跑完已删）：改实现 → 跑指定测试 → 记录 → `finally` 逐字还原并断言复原。
**41 条（40 条有效，M39 首次因超时未取到结果，已改口径重跑）：31 条变红、9 条存活。**

| # | 变异（改了哪行） | 所跑测试 | 结果 |
|---|---|---|---|
| M1 | 前端不读后端 message（`workflow_transcript.js:243`） | browser `-k candidate_rows or pref*backend*` | **变红** ✓ |
| M2 | 候选行负向态分支关掉（`:313`） | 浏览器全量 | **变红** ✓ |
| M3 | 下钻挂载点去 `content_limit`（`session.py:1016`） | `-k content_limit` | **存活 ✗** → Issue 2 |
| M4 | `_ASSERTABLE_STATES` 扩进 present/clean（`:767`） | `-k rejects_unknown` | **变红** ✓ |
| M5 | 模块常量删 `queue_full`（`:752`） | `-k terminal_run_statuses` | **变红** ✓ |
| M6 | `settle` 忽略自定义 message（`:819`） | `-k 'never_dispatched or not_applicable or unknown_node'` | **变红** ✓ |
| M7 | 不报真实 total（`:845`） | `-k most_recent` | **变红** ✓ |
| M8 | 最近 N → 最早 N（`:850`） | `-k most_recent` | **变红** ✓ |
| M9 | `text_truncated` 恒 False（`:895`） | `-k truncat` | **变红** ✓ |
| M10 | `llm_error.status` 不合成（`:881`） | `-k llm_error_item_status` | **变红** ✓ |
| M11 | 轻量形态去掉 400 上限（`:849`） | `-k lightweight` | **变红** ✓ |
| M12 | `clean` 折叠成 `no_trace`（`:838`） | `-k clean_is_a_positive` | **变红** ✓ |
| M13 | `empty_trace` 折叠成 `no_trace`（`:834`） | `-k empty_trace` | **变红** ✓ |
| M14 | `count_failures` 空 trace 返回 0（`trace_recorder.py:281`） | `-k count_failures` | **变红** ✓ |
| M15 | 删 `_reset_subtree` 复位（`scheduler.py:1697`） | `-k failure_count`（terminal_honesty） | **变红** ✓ |
| M16 | 快照计数写死 0（`scheduler.py:2792`） | `-k snapshot` | **变红** ✓ |
| M17 | `no_trace` 折叠成 `clean`（`:832`） | `-k no_trace` | **变红** ✓ |
| M18 | 删 `running` 判定（`:806`） | `-k running_is_not` | **变红** ✓ |
| M19 | 前端 `None`/`0` 折叠（`workflow_graph.js:1174`） | `-k failure_count_hint` | **变红** ✓ |
| M20 | 证据块守卫 `if (evidence)` → `if (false)`（`:296`） | 浏览器全量 | **变红** ✓ |
| M21 | `_resolve_run` 去掉 run_id=None 回落（`:910`） | `-k drilldown_without_run_id` | **变红** ✓ |
| M22 | single 挂载点去 `content_limit`（`:1177`） | `-k content_limit` | **变红** ✓ |
| M23 | candidates 挂载点去 `content_limit`（`:1234`） | `-k content_limit` | **变红** ✓ |
| M24 | 失败判据收窄成 `== "error"`（`trace_recorder.py:283`） | `-k iter_failure_steps` | **变红** ✓ |
| M25 | 前端未知 state 不再降级（`workflow_graph.js:1131`） | `-k degrades_readably` | **变红** ✓ |
| M26 | 候选行正向计数线索关掉（`:308`） | `-k candidate_rows` | **变红** ✓ |
| M27 | `truncated` 标量恒 False（`:852`） | `-k most_recent` | **变红** ✓ |
| M28 | 「任务」tab 线索整条关掉（`workflow.js:1140`） | 浏览器 + ux_js 全量 | **存活 ✗** → Issue 3 |
| M29 | 「任务」tab 高亮类去掉（`workflow.js:1143`） | 浏览器全量 | **存活 ✗** → Issue 3 |
| M30 | collect 的 `not_applicable` → `unavailable`（`:1151`） | `-k not_applicable` | **变红** ✓ |
| M31 | 候选判据改成语义等价的**另一种**内联集合（`:1214`） | `-k terminal_run_statuses` | **存活 ✗** → Issue 4 |
| M32 | 条目文本整段不渲染（`:265`） | 浏览器证据/下钻用例 | **存活 ✗** → Issue 1 |
| M33 | 证据标题去掉真实条数（`:257`） | 浏览器证据用例 | **存活 ✗** → Issue 1 |
| M34 | 候选判据改回**逐字**原内联写法（`:1214`） | `-k terminal_run_statuses` | **变红** ✓（仅文本命中，见 M31） |
| M35 | `failureText` 去掉兜底表（`:242`） | 浏览器 + ux_js 全量 | **存活 ✗** → Issue 4 |
| M36 | 删掉证据区挂载调用（`:119`） | 浏览器全量 | **变红** ✓ |
| M37 | 下钻改轻量形态（`session.py:1017`） | `-k drilldown` | **变红** ✓ |
| M38 | candidates 改完整形态（`:1234`） | `-k lightweight` | **变红** ✓ |
| M39 | 条目渲染整段关掉（`:262`） | 非浏览器 137 条 | **存活 ✗** → Issue 1 |
| M40 | 条目渲染整段关掉（`:262`） | 浏览器全量 22 条 | **存活 ✗** → Issue 1 |
| M41 | 截断页脚关掉（`:274`） | 浏览器 + ux_js 全量 68 条 | **存活 ✗** → Issue 1 |

其中 M1/M2/M20/M26（R2 修复的新代码）与 M3/M4/M5/M6/M31/M34（R2 低危修复）覆盖本次要求
重点核验的对象；M15/M16（R1 修复）与 M7–M19、M21–M27、M30、M36–M38 覆盖核心不变式
（clean/no_trace 折叠、最近 N 条、轻量上限、`count_failures` 空 trace、快照埋点、
`_reset_subtree` 复位）；M28/M29/M32/M33/M35/M39/M40/M41 是本次独立发现的覆盖缺口。

## 结论

R1 的中等问题与 R2 的两条中等问题**都已真正修复，且这次都有可失败证据**（M1/M2/M15/M20/M26 均变红）；
R2 的四条低危也逐条落地（含文档口径统一）。本次独立复检的核心新发现是：
**本 change 头号交付物——「对话」tab 的失败证据正文——在 `single` 形态下零测试覆盖**，
五条变异（删整段条目 / 删文本 / 删截断页脚 / 删标题条数）全部存活于浏览器全量与非浏览器 137 条之下，
而这段代码里压着 grill Q2 那条**用户已确认**的「前端预览 300 字符 + 显式截断标注」。
按 R2 对同构问题（候选行渲染块零覆盖）判「中」的先例，这一条同为**中**，是本次唯一阻塞项。
其余三条低（下钻 `content_limit` 无覆盖、「任务」tab 线索无覆盖、单源守卫是文本匹配）与
两条文档口径项**均不阻塞**，建议随同一条回归测试一并处理。
