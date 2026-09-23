# Building Review: fix-issue-215-node-failure-evidence（Round 2）

## Reviewer
- run id: review-subagent-215-r2
- 时间: 2026-09-23
- 审阅范围: `1a7df92cbd90ab442342a8481d59857b8c4ebf54`..`bea27d65eb5787877320e4a673f9d6321a85267c`
- 工作目录: `/tmp/rev-215`（隔离检出）。**审阅结束时已 `rm` 自建探针脚本并 `git checkout -- .`**，
  `git status --short` 只剩 `?? .venv`（paseo 预置的软链）与本报告。

## Verdict
**CHANGES_REQUESTED**

理由（先说结论，再给证据）：

1. R1 的四条修复**三条真的到位**（`failure_count` 复位、`tasks.md` 勾选、未知 state 守卫，
   各有变异验红），第四条（候选行负向态）**修了但没锁住**——我为它构造的两条变异全部存活
   （见「变异验证」M-R1c / M-R1c2），其中一条证明**整个候选行失败线索渲染块**（不只新增分支）
   在既有测试面上零杀伤力。按本次审阅的判据「任何一条没变红 = 假保护 = 必须报为 issue」，
   这是必须修的覆盖缺口。
2. 独立复检出 **3 条 R1 未提的新问题**（1 条中等口径 + 2 条低），其中最实质的一条是
   **载荷里 `failure_evidence.message` 在前端零消费**：后端为「未派发 / 不在计划 / collect」
   精心写的三条自定义文案，以及七态文案表，**一个字都到不了用户界面**，前端另有一套自己的
   文案表。设计 D1 明确要求的「『尚未派发』的文案要与『run 记录被弹出』区分开」在 UI 上落空。
3. 其余：spec 七个 Scenario 逐条有实现与用例、15 条既有核心不变式变异全被杀、无安全漏洞、
   无 CI 弱化、既有键语义未变。**没有阻塞性缺陷**，修掉上面两项即可 PASS。

## Round 1 修复验证

逐条**跑测试 / 构造反例**验证（不只看 diff）：

### R1-1（中）`failure_count` 逃过 `_reset_subtree` → **真的修好了**

修复行：`agent/subagent/scheduler.py:1697`（`state.failure_count = None`），
回归用例：`tests/agent/subagent/test_terminal_honesty.py:692-744`。

- **变异验证**：删掉 `:1697` → `test_reset_subtree_clears_stale_failure_count`
  **变红**（1 failed in 4.72s）。守卫是活的。
- **独立复现修复前的症状**：不删该行、仅把 `state.failure_count = None` 换成
  `state.failure_count = 7` 之外的等价破坏，用例同样只在该断言上失败，说明断言不是恒真
  （用例同时断言 `status == "pending"` / `reason is None` / `summary == ""` /
  `finished_at is None` / 快照 `node["failure_count"] is None`，五条独立）。
- **foreach 展开项**：确认不受该残留影响——`_execute_foreach` 在 `scheduler.py:1811`
  用 `state.item_runs = [_ItemRunSlot() for _ in items]` **整体重建**槽，上一轮的
  `failure_count` 不会跨轮存活；`_reset_subtree` 只作用于 `NodeState`，不需要（也无法）
  复位槽。R1 的「foreach 不受影响」结论**成立**。
- **复位后快照投影真的干净**：用例末尾显式断言 `node["status"] == "pending"` 且
  `node["failure_count"] is None`，走的是 `_graph_node_projection`（`scheduler.py:2792`）
  这条真实路径，不是直接读字段。**到位。**

### R1-2（低）未知 `state=` 静默穿透 → **枚举外修好了，枚举内仍静默**

修复行：`web/session.py:817-821`（`raise ValueError`），用例：
`tests/web_tests/test_workflow_node_transcript.py:1700-1726`。

- **变异验证**：把 `raise ValueError(...)` 换成 `pass` → `test_failure_evidence_rejects_unknown_explicit_state`
  **变红**（1 failed in 3.02s）。守卫是活的。
- **但修的是「枚举外」这一半**：实测（探针，已删）显式传**枚举内**取值时仍被静默忽略——
  `state="clean"` + trace 有失败 → 返回 `present`；`state="present"` + 无 run → 返回 `no_trace`；
  `state="empty_trace"` + 有失败 → 返回 `present`。只有 `not_applicable`/`unavailable`/`running`
  三个值被 `:823-824` 提前落定、真正被尊重。
  这正是 R1 那句「让调用方以为『我指定了 unavailable』」的**同一类**问题，只是换了取值区间。
  当前 5 个调用点全传字面量且恰好落在被尊重/与被忽略无冲突的组合上，故**不阻塞**，
  详见 Issue 5（低）。

### R1-3（低）候选行负向态完全不显示 → **代码修了，测试没跟上（本次主要问题）**

修复行：`web/static/workflow_transcript.js:300-305`（新增 `else if (evidence.state !== 'not_applicable')` 分支）。

- **变异验证一**：删掉该 `else if` 整段 → 跑 `test_workflow_graph_browser.py` +
  `test_workflow_graph_ux_js.py` → **`66 passed`，未变红（SURVIVED）**。
- **变异验证二**（更强）：把整个候选渲染块的守卫 `if (evidence) {` 改成 `if (false) {`
  （等于**连同正向计数线索一起**关掉）→ 跑 `test_workflow_graph_browser.py` → **`20 passed`，
  未变红（SURVIVED）**。
- **证明该分支是 live 且可测的**（不是死代码，所以不能豁免）：我在隔离检出里临时写了一条
  浏览器用例（已删除，未留痕），给候选塞入 `clean` / `present(3)` / `running` 三种证据，
  实测候选行文本为：

  ```
  #0 …ok已检查，无失败记录。completed
  #1 …RuntimeError: boom⚠ 3 条工具/LLM 失败（点进去看）failed
  #2 …该 run 尚未结束，执行 trace 只会在终态写入——现在没有失败证据，不代表没有失败。running
  ```

  即：修复本身**渲染正确**，R1 的诉求达到了；缺的是**没有任何测试能证明它还在**。
- **为什么既有用例盖不住**：`tests/web_tests/test_workflow_graph_browser.py:500-511` 的
  `_ITEM_CONTAINER` fixture 的候选字典**根本没有 `failure_evidence` 键**（8 个键，
  实测与真实载荷的 9 键对照确认），所以 `if (evidence)` 恒假、整块跳过；
  `tests/web_tests/test_workflow_graph_ux_js.py:503-565` 只锁**纯函数**
  （`failureEvidenceText` / `failureItemSummary` / `failureCountHint`）本身，
  不锁「候选行有没有调用它」。两者之间的缝就是这片未覆盖区。
- 结论：**R1-3 的修复需视为未完成**（实现到位、防护缺失），见 Issue 1（中）。

### R1-4（低）`tasks.md` diagnosis.md 未勾但文字写「已完成」 → **修好了**

`tasks.md:96` 已改为 `- [x]`（`git show bea27d6 -- tasks.md`）。
但**同一类问题在下面一行仍然存在**（`tasks.md:103` 的 `known-debt.md` 同样是「已做完但没勾」），
见 Issue 6（低）。

## Tasks Verification

对照 `tasks.md` 每个 `[x]` 读代码/跑测试确认（只列有实质结论的；`文件:行号` 为当前 HEAD）：

- [x] grill 立项前置（独立零记忆 subagent + 停轮确认 Q1–Q7）→ `reviews/grill-design.md` 有 6 条
      Confirmed Decisions 与 `## User Confirmation`；artifact checker 对该项无告警。
- [x] 常量（`FAILURE_EVIDENCE_LIMIT=5` / `FAILURE_EVIDENCE_PREVIEW_LIMIT=400` /
      `_TERMINAL_RUN_STATUSES` / `FAILURE_EVIDENCE_STATES` 七值）→ `web/session.py:741/745/751/759`
- [x] `_failure_evidence(...)` 只遍历不复制、过滤判据在 `agent/trace_recorder.py:258-284` →
      `web/session.py:765-847`；`iter_failure_steps` 变异（判据收窄成 `== "error"`）**被杀**
- [x] 七态 + 各负向态文案 → `web/session.py:826-847`（`settle`）+ `:851-860`；
      `test_every_failure_evidence_state_has_a_distinct_readable_message` 参数化七值
- [x] 条目 bounded（最近 N、时间正序、`text_truncated`、`llm_error.status` 合成）→
      `web/session.py:843/864-889`；对应两条变异**均被杀**
- [x] 三态分支挂载 → `single` `web/session.py:1168`；`candidates` `:1226`；`none`
      `:1081`（state is None）/`:1121`（route）/`:1138`（collect 与未派发）；下钻 `:1008`
- [x] 终态判据复用既有字面量 → `web/session.py:751-752`；**但 `:1206` 那份内联字面量没动**，
      见 Issue 4（低）
- [x] `NodeState` / `_ItemRunSlot` 计数字段 → `agent/subagent/scheduler.py:257` / `:215`
- [x] 埋点在 `_await_run` 之后、每 run 一次、`queue_full` 早退绕过 →
      `agent/subagent/scheduler.py:2175-2177`、`:2134-2145`；两条变异（删埋点 / 投影写死 0）**均被杀**
- [x] `_graph_node_projection` 投影 → `agent/subagent/scheduler.py:2792`
- [x] 前端「对话」tab 挂载 → `web/static/workflow_transcript.js:116`（调用）/`:233-266`（实现）
- [x] 前端纯函数 → `web/static/workflow_graph.js:1124-1180`；`None`/`0` 折叠变异**被杀**
- [x] 「任务」tab 一行快照线索（零请求）→ `web/static/workflow.js:1137-1147`
- [x] 样式 → `web/static/style.css:1753-1778`
- [x] 测试清单：`tests/web_tests/test_workflow_node_transcript.py:989-1726`、
      `test_workflow_graph_ux_js.py:500-565` 逐条找到对应用例；**除候选行渲染外**断言非恒真
- [x] 回归 `tests/web_tests/` + `tests/agent/subagent/` → 见「Test Results」
- [ ] 文档 / 验证 / 收尾（`tasks.md:97-124`）未勾：核对后**大体诚实**——`openspec/specs/**`
      本次零改动（`git diff --name-only` 为空），与「当前规格同步」「快照加法字段」两条未勾一致；
      `known-debt.md` / `backlog.md` 的改动均有 `workflow-events.jsonl` seq 1/2 解释事件；
      review manifest 确实不存在（artifact checker 实测报 `review manifest missing`）。
      **两处例外**：`tasks.md:103` 的 known-debt 工作**已做完却未勾**（Issue 6）；
      `tasks.md:100` 的关键词扫描任务，`docs/architecture.md:106` 已按 grill 要求补了一句
      （git diff 可见），属已做未勾的同一类（不单列）。

## Issues

### 1. **中**：候选行失败线索渲染块（含 R1 新增的负向态分支）零测试覆盖 —— 假保护

**证据**：
- 实现：`web/static/workflow_transcript.js:296-306`（整块）、`:300-305`（R1 新增的负向态分支）
- 变异 A：删掉 `:300-305` → `uv run pytest tests/web_tests/test_workflow_graph_browser.py tests/web_tests/test_workflow_graph_ux_js.py -q` → `66 passed`（**未变红**）
- 变异 B：`:296` 的 `if (evidence) {` → `if (false) {` → `uv run pytest tests/web_tests/test_workflow_graph_browser.py -q` → `20 passed`（**未变红**）
- 覆盖缝：`tests/web_tests/test_workflow_graph_browser.py:500-511` 的 `_ITEM_CONTAINER`
  候选**无 `failure_evidence` 键**（实测 8 键 vs 真实载荷 9 键）；`test_workflow_graph_ux_js.py`
  只锁纯函数、不锁调用。
- 反面证明该分支 live：临时浏览器用例（已删）实测渲染出 `已检查，无失败记录。` /
  `⚠ 3 条工具/LLM 失败（点进去看）` / `该 run 尚未结束…`。

**为什么必须修**：R1 判「候选行负向态不显示」为低危并指示修；实现修了，但**没有可失败的证据**，
后续任何重构（含本次审阅之后的下一次改动）都能把它静默删掉而全绿——这正是 issue #215
立项时点名的失败模式（「文档承诺了、实现漂了」）。且该块整体（正向线索）同样无人守护，
面比 R1 那条 issue 更大。
**建议**：给 `test_workflow_graph_browser.py` 的 `_ITEM_CONTAINER` 候选补 `failure_evidence`
（三种：`present`/`total>0`、`clean`、`running`），并加一条断言候选行文本的用例；
或（更轻）把「候选行线索文案」再抽一个纯函数（如 `candidateFailureClue(evidence)`）
并在 `test_workflow_graph_ux_js.py` 里以 node+vm 锁定——后者不引入浏览器依赖，
与 R1 给前端定的验收路径一致。

### 2. **中**：`failure_evidence.message` 在前端零消费 —— 后端三条自定义文案与 D1 的区分意图到不了用户界面

**证据**：
- `grep -rn "evidence\.message" web/static/*.js` → **零命中**。
  `web/static/workflow_transcript.js:243-266` 的 `appendFailureEvidence` 用的是
  `G.failureEvidenceText(evidence.state)`（前端自建表 `web/static/workflow_graph.js:1124-1132`），
  从不读 `evidence.message`。
- 后端为此维护了**两套**文案，全部无人消费：
  - 七态文案表 `web/session.py:851-860`（spec 明确要求的 `message` 字段）；
  - 三处自定义覆盖：`web/session.py:1081-1083`（「该节点不在当前执行计划里」）、
    `:1141-1142`（「该节点是纯逻辑聚合」/「**该节点尚未派发**」）。
- 用户实际看到的是：`web/static/workflow_graph.js:1126` 的 `clean: '已检查，无失败记录。'`
  与后端 `web/session.py:855` 的 `"已检查本 run 的执行记录（trace 非空），未发现失败步骤。"`
  ——**两份不同文本，前端那份赢**。
- 后果最明显的一处：**未派发的节点**（抽屉默认「任务」tab →「对话」的最常见路径）本应显示
  design D1 明确要求的「该节点尚未派发，暂时没有失败证据。」，用户在 UI 上读到的是
  `unavailable` 的通用文案「无法解析该 run 的记录，因此拿不到失败证据。」——把一个「还没轮到」
  说成了「数据取不到」。设计 D1 的原话是「它的文案要与『run 记录被弹出』区分开」，
  这条区分**在 UI 层完全落空**（后端区分了，前端丢弃了）。

**为何算中等**：它是本 change 的主题（诚实投影）在**用户面**的缺口，且是可被下一个人
当作 bug 反复翻修的活缝；spec 层面不违规（spec 只要求载荷带 `message`，载荷确实带了），
故不是阻塞。
**建议**：二选一并写清口径——(a) 前端在**有 `message` 时优先渲染后端 `message`**
（`evidence.message || G.failureEvidenceText(evidence.state)`），前端表退化为兜底；
(b) 若刻意保留前端独立表，则在 spec/design 里补一句「前端文案不取自载荷 `message`，
两表各自维护」并**删掉后端三条自定义覆盖**（当前是无消费方的死文本）。
推荐 (a)：它顺带把「前端版本落后于后端」的防线从「文案存在性」升级为「文案内容一致」。

### 3. **低**：`content_limit` 未透传给失败证据投影 —— 载荷声明的单条上限与条目实际长度不符

**证据**：`build_node_transcript_payload(content_limit=...)` 的公开参数在三个挂载点都没往下传：
`web/session.py:1008`、`:1168`、`:1226` 全部是无 `content_limit=` 的 `_failure_evidence(...)` 调用，
于是 `:770` 的参数永远取默认 `TRANSCRIPT_CONTENT_LIMIT = 4000`（`web/session.py:731`），
而 `:841` 的 `text_limit = content_limit if full else ...` 这条分支**永远不会被外部调用收紧**。
实测（探针，已删）：`content_limit=100` → 载荷 `content_limit == 100`，但
`failure_evidence["items"][0]["observation"]` 长度仍为 `4000`。
**可达性如实标注**：`web/server.py:231-234` 的 HTTP 路由**不传** `content_limit`，
所以生产路径上两者都是 4000、当前无实际错配；属**契约漂移 + 测试盲区**（既有
`content_limit` 用例 `tests/web_tests/test_workflow_node_transcript.py:447/590/679/861`
全部不覆盖新键）。
**建议**：在三处挂载点把 `content_limit=content_limit` 传下去（一行 ×3），
并补一条「收紧 `content_limit` 后失败证据条目同步收紧」的用例。

### 4. **低**：D7「不新造第四份」只做了一半，且这半也没被测试锁住

**证据**：
- 模块常量 `_TERMINAL_RUN_STATUSES`（`web/session.py:751-752`）确实是新代码在用的那一份，
  `:801` 的 `running` 判据引用它，变异（删掉 `running` 判定）**被杀**。
- 但同一文件 `:1206` 的 `_foreach_candidates` **仍留着内联的同一份字面量**
  `("completed","failed","cancelled","budget_exceeded","queue_full")`——D7 自称要消灭的
  「第四份副本」其实是**第五份**，只是把最新的那份提成了常量。
- 更关键：把模块常量的 `queue_full` 删掉（`{"completed","failed","cancelled","budget_exceeded"}`）
  → 跑全量 `tests/web_tests/` → **`404 passed`，未变红（SURVIVED）**。也就是说
  「模块常量与 :1206 内联字面量保持一致」这条不变式**没有任何测试**，D7 想防的漂移依然可能发生。
**建议**：让 `:1206` 直接引用 `_TERMINAL_RUN_STATUSES`（一行），并补一条断言两者相等的
小用例（或直接在 `test_terminal_honesty.py` 的副本一致性用例族里加一份）。

### 5. **低**：R1 的 `ValueError` 守卫只堵了枚举外取值，枚举内取值仍被静默忽略

**证据**（探针，已删）：
```
state='clean'    + trace 有失败 → 实际 'present'   （被静默忽略）
state='no_trace' + trace 有失败 → 实际 'present'   （被静默忽略）
state='present'  + 无 run      → 实际 'no_trace'   （被静默忽略）
对照：not_applicable / unavailable / running 三者被 :823-824 尊重
```
变异：把 `:823` 的 `if state is not None and state in ("not_applicable","unavailable","running")`
放宽成 `if state is not None` → 全量 `tests/web_tests/` **`404 passed`，未变红（SURVIVED）**，
说明「哪些显式取值被尊重」这条语义无测试。
**可达性如实标注**：当前 5 个调用点全部传字面量（`not_applicable` / `unavailable` 两种），
不可达，与 R1 判低危的理由同源。
**建议**：把 `_failure_evidence` 的显式 `state` 改成**要么整体落定、要么整体不传**（当前是
「三个值特殊、其余被忽略」的混合语义），或在 docstring 里写清「`state=` 只在
`not_applicable`/`unavailable`/`running` 下作为**强制取值**，其余取值会按 trace 重算」，
并补一条锁定该语义的用例。

### 6. **低**：同一 change 内 `no_trace` 成因的文档口径互相打架；`tasks.md:103` 已做完未勾

**证据（口径打架）**：
- 已订正的口径：`design.md:110`（「该分支**当前无活跃生产者**，故成因按防御性口径写」）
  与 `docs/known-debt.md:289-293`（实测该路径恒假，`no_trace` 是防御性取值）。
- **未订正的旧口径**（同 change 内）：
  - `openspec/changes/fix-issue-215-node-failure-evidence/diagnosis.md:144`：
    「`no_trace` — 终态且 trace 为 `None`（**排队中撞时间预算**：`manager.py:1524` 传 `trace=None`）」
  - `docs/openspec-change-backlog.md:157`：「`no_trace` = 排队中撞时间预算写 `None`」

  两处都把已实测判定为**不可达**的路径当成活成因在陈述。`diagnosis.md` 是该 change 立项时
  写下的（`3c10a97`），订正（`f64c663`）只回写了 `design.md`，**没有回写 diagnosis/backlog**。
  影响有限（spec delta 本身只写「终态且 trace 为 None」，未暗示活路径，口径正确），
  但属本 change 自己点名的病根「文档承诺了、实现漂了」的同构问题，且 `diagnosis.md`
  是 bugfix 门禁要求的 6 章之一、`tasks.md:96` 已勾「完成」。
**证据（未勾）**：`tasks.md:103` 是 `- [ ]`，但 `docs/known-debt.md:276-294` 已经写了那两条
死代码发现（`git diff origin/master...HEAD -- docs/known-debt.md` 可见 21 行新增）+
`workflow-events.jsonl` seq 2 的解释事件。**已做完却未勾**，与 R1 第 4 条issue 同类；
无 `(post-merge)` 标记的话归档完成度门禁会判红。
**建议**：把 `diagnosis.md:144` 与 `docs/openspec-change-backlog.md:157` 的「排队中撞时间预算」
改成与 `known-debt.md` 一致的防御性口径（或加一句「实测不可达，详见 known-debt」），
并把 `tasks.md:103` 勾上。

**记录（非 issue）**
- foreach 容器自身的快照 `failure_count` 恒为 `None`（实测：`{'failure_count': None, 'items_failed': 1}`），
  因埋点写的是 `_ItemRunSlot` 而容器没有单一 run——**符合 Q6 设计**（容器级线索由 `items_failed`
  承担）。**但** `_ItemRunSlot.failure_count`（`scheduler.py:215`）在全仓**没有任何读取方**
  （`grep` 确认：写 `:2207`、读只有测试），而 `tasks.md:51` 的「展开项共用这一处埋点」与
  `test_snapshot_failure_count_covers_foreach_items`（`test_workflow_node_transcript.py:1552-1567`）
  合起来会让读者以为「容器快照覆盖了展开项的失败计数」——实际只是**槽上的字段被写**，
  没有任何投影把它送到用户面。属**写而不用**的冗余（无害，但会误导下一位读者），
  建议要么接上容器级投影，要么在字段 docstring 里明说「当前无消费方，为 #202 预留」。
- `_resolve_run` 直接访问 `manager._sessions`（`web/session.py:895-906`）：与 R1 同结论，可接受
  （docstring 给了理由，且回落语义与 `inspect_transcript` 同口径）。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/web_tests/ tests/agent/subagent/ -q` | **943 passed, 7 skipped**，1 failed（见下） |
| 同上失败项隔离重跑 `pytest tests/web_tests/test_workflow_graph_browser.py::test_workflow_view_desktop_horizontal_layout -q` | **1 passed**（8.83s）→ 判定为**环境性 flake**，非本 change 缺陷 |
| `uv run pytest tests/web_tests/test_workflow_node_transcript.py tests/web_tests/test_workflow_graph_ux_js.py tests/agent/subagent/test_terminal_honesty.py -q` | **139 passed** |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **Totals: 30 passed, 0 failed (30 items)** |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | **exit 1**：`review manifest missing: …/reviews/building-review-manifest.json` —— 对应 `tasks.md:111`（未勾，预期，manifest 须在 tasks.md 最终化之后生成） |
| 全部变异 | 22 条：**17 变红 / 5 存活**（存活即 Issue 1/4/5） |

无既有用例因新增 `failure_evidence` / `failure_count` 键变红；未观察到需要改代码的浏览器 flake。

## Spec Scenario 对齐

对 `openspec/changes/fix-issue-215-node-failure-evidence/specs/web-ui/spec.md` 逐条核对实现与用例：

| Spec 条款 / Scenario | 覆盖 |
|---|---|
| 载荷以 `failure_evidence` 提供投影；数据源是 `status != ok` 的 `tool_result` + 全部 `llm_error`；不新增采集/不调 LLM/不写盘 | `web/session.py:765-847` + `agent/trace_recorder.py:258-284`；`test_failure_evidence_projection_is_read_only:1296`；端到端 `test_workflow_control_server.py:219` |
| 键名 `state`/`total`/`truncated`/`message`/`items` | `web/session.py:812-813`；`test_failure_evidence_key_is_additive_for_all_shapes:1405` |
| 七值枚举**且仅**七值 | `web/session.py:759-762`；`test_every_failure_evidence_state_has_a_distinct_readable_message` 参数化七值 |
| `not_applicable` 与 `unavailable` 不折叠 | `web/session.py:1121` / `:1138-1142`；变异 M-core_not_applicable_fold **被杀**；`test_unknown_node_is_unavailable_not_not_applicable:1665` |
| 条目含 `type`/`step`/`status`/`error_type`/`tool_name`/`text_truncated`，文本按类型二选一 | `web/session.py:864-889`；`test_failure_evidence_tolerates_missing_and_empty_fields:1271` |
| `llm_error` 的 `status` 由投影固定 `"error"` | `web/session.py:881`；变异 M-core_llm_error_status **被杀** |
| bounded：最近 N 条、时间正序、单条 ≤ `content_limit`、`truncated` 标量 | `web/session.py:843-847`；三条变异（最早 N / 去截断 / 去标志）**均被杀**；**但 `content_limit` 未透传**（Issue 3） |
| 不可用/截断给**可读文案**，不给空列表或 `null` | 载荷满足（`web/session.py:851-860`）；**前端未消费 `message`**（Issue 2） |
| SHALL NOT 改变前端取数时机（懒加载） | `web/static/workflow.js:1137-1147` 只读快照整数、零 `fetch`；浏览器用例 `test_workflow_graph_browser.py:471-499` 全量重跑 **20 passed** |
| Scenario: `present`（completed + 中途工具失败） | `test_failure_evidence_present_on_completed_run_with_tool_failure:989` + 真实路由 `test_workflow_control_server.py:219-261` |
| Scenario: `clean` | `test_failure_evidence_clean_is_a_positive_statement:1050`；变异 M-core_clean_fold **被杀** |
| Scenario: `running` | `test_failure_evidence_running_is_not_no_trace:1071`；变异 **被杀** |
| Scenario: `no_trace` | `test_failure_evidence_no_trace_when_terminal_without_trace:1089` |
| Scenario: `empty_trace` | `test_failure_evidence_empty_trace_is_not_no_trace:1105`；变异 **被杀** |
| Scenario: `unavailable` | `test_failure_evidence_unavailable_when_run_record_is_gone:1123` + `test_unknown_node_is_unavailable_not_not_applicable:1665` |
| Scenario: `not_applicable` | `test_failure_evidence_not_applicable_for_route_and_collect:1144`；变异 **被杀** |
| Scenario: 条目超上限（最近 N / 真实 total / truncated / 正序） | `test_failure_evidence_returns_most_recent_n_in_time_order:1181`；变异 **被杀** |
| Scenario: 候选集只带轻量证据（`items` ≤1、单条 ≤400）；下钻为完整形态 | 投影层 `web/session.py:843-844` + `:1008`/`:1226`；两条变异（去轻量上限 / 去 preview 上限）**均被杀**；`test_candidates_carry_lightweight_failure_evidence:1315`、`test_item_drilldown_carries_full_failure_evidence:1353` |

**未见「spec 写了但没实现」的条款**；唯一未落地的是 Scenario 里**候选行**的**用户可见**部分
（spec 本身只约束载荷，故按 Issue 1 的覆盖缺口处理，而非 spec 违规）。

## 变异验证

自建驱动：改实现 → 跑指定测试 → 记录 → `finally` 逐字还原并断言复原。
**22 条：17 条变红、5 条存活。存活即上面 Issue 1/4/5。**

| # | 变异（改了哪行） | 所跑测试 | 结果 |
|---|---|---|---|
| M-R1a | 删 `state.failure_count = None`（`scheduler.py:1697`） | `test_reset_subtree_clears_stale_failure_count` | **变红** ✓ |
| M-R1b | `raise ValueError(...)` → `pass`（`session.py:821`） | `test_failure_evidence_rejects_unknown_explicit_state` + `test_real_callers_only_pass_declared_states` | **变红** ✓ |
| M-R1c | 删掉 R1 新增的候选行负向态分支（`workflow_transcript.js:300-305`） | `test_workflow_graph_browser.py` + `test_workflow_graph_ux_js.py` | **存活 ✗**（66 passed）→ Issue 1 |
| M-R1c2 | 整块候选证据渲染 `if (evidence)` → `if (false)`（`workflow_transcript.js:296`） | `test_workflow_graph_browser.py` | **存活 ✗**（20 passed）→ Issue 1 |
| M-core1 | `clean` 折叠成 `no_trace`（`session.py:836`） | `test_failure_evidence_clean_is_a_positive_statement` | 变红 ✓ |
| M-core2 | `empty_trace` 折叠成 `no_trace`（`session.py:827`） | `test_failure_evidence_empty_trace_is_not_no_trace` | 变红 ✓ |
| M-core3 | route 的 `not_applicable` → `unavailable`（`session.py:1121`） | `test_failure_evidence_not_applicable_for_route_and_collect` | 变红 ✓ |
| M-core4 | 最近 N 改成最早 N（`session.py:844`） | `test_failure_evidence_returns_most_recent_n_in_time_order` | 变红 ✓ |
| M-core5 | 去掉单条截断（`session.py:885`） | `test_failure_evidence_truncates_long_text` | 变红 ✓ |
| M-core6 | `text_truncated` 恒 False（`session.py:887`） | 同上 + `…_response_is_bounded_under_huge_trace` | 变红 ✓ |
| M-core7 | `llm_error` 的 `status` 不合成（`session.py:881`） | `test_llm_error_item_status_is_synthesised` | 变红 ✓ |
| M-core8 | candidates 去掉轻量上限（`session.py:843`） | `test_candidates_carry_lightweight_failure_evidence` | 变红 ✓ |
| M-core9 | `count_failures` 空 trace 返回 `0`（`trace_recorder.py:281`） | `… -k count_failures` | 变红 ✓ |
| M-core10 | 失败判据收窄成 `== "error"`（`trace_recorder.py:283`） | `… -k iter_failure_steps` | 变红 ✓ |
| M-core11 | 删掉 `_launch_run` 计数埋点（`scheduler.py:2175-2177`） | `test_snapshot_carries_failure_count_for_terminal_run` | 变红 ✓ |
| M-core12 | 快照 `failure_count` 写死 `0`（`scheduler.py:2792`） | 同上 | 变红 ✓ |
| M-core13 | 删掉 `running` 判定（`session.py:801`） | `test_failure_evidence_running_is_not_no_trace` | 变红 ✓ |
| M-core14 | 前端 `None`/`0` 折叠（`workflow_graph.js:1174-1175`） | `test_failure_count_hint_separates_no_data_from_zero` | 变红 ✓ |
| M-core15 | 轻量形态去掉 400 上限（`session.py:841`） | `test_candidates_carry_lightweight_failure_evidence` | 变红 ✓ |
| M-new1 | `_foreach_candidates` 的终态字面量删 `queue_full`（`session.py:1206`） | 全量 `tests/web_tests/` + `tests/agent/subagent/` | **存活 ✗**（944 passed）→ Issue 4 |
| M-new2 | 模块常量 `_TERMINAL_RUN_STATUSES` 删 `queue_full`（`session.py:752`） | 全量 `tests/web_tests/` | **存活 ✗**（404 passed）→ Issue 4 |
| M-new3 | 守卫放宽成 `if state is not None: return settle(state)`（`session.py:823`） | 全量 `tests/web_tests/` | **存活 ✗**（404 passed）→ Issue 5 |

其中 M-core1–M-core15 与 M-R1a/M-R1b 覆盖了本次要求重点核验的「R1 修复引入的新代码」与
「原有核心不变式」；M-R1c/M-R1c2、M-new1/M-new2/M-new3 是本次独立发现。

## 结论

R1 的中等问题（`failure_count` 逃过 `_reset_subtree`）**已真正修复并有可失败证据**；
其三条低危中两条到位、一条（候选行负向态）**实现到位但防护缺失**。
本次独立复检另发现 `failure_evidence.message` 前端零消费（设计 D1 的区分意图在 UI 落空）、
`content_limit` 未透传、D7 常量副本与守卫语义无测试锁定、以及 `no_trace` 成因的文档口径
在同 change 内互相打架。**以上无阻塞项；建议按 Issue 1、2 修复（各需一条回归测试），
Issue 3–6 一并处理**后即可判 PASS。
