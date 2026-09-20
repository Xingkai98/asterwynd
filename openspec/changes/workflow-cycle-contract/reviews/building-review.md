# Building Review: 循环图的契约对模型可见（workflow-cycle-contract）

我是**独立零记忆**的实现审阅员（`/review-loop`，AGENTS.md #90 机械强制）：本次会话未读取任何先前对话，
工作目录 `/home/happy/.paseo/worktrees/0frj3kg8/workflow-cycle-contract-2026-09-19`（分支
`workflow-cycle-contract/2026-09-19`）的代码、文档与 git 历史是我唯一的事实来源。审阅方法：
**先读 worktree 的源码建立调度器真实派发模型，再在 `/tmp` 下写独立脚本把「声明期判定」与「真实
`WorkflowScheduler.run()` 结果」逐图对照实跑**——所有结论都来自实跑输出，不采信 design/proposal 的自我断言。
特别地：为验证「被拒的图是否真的跑不起来」，我用 `git archive b0a6604` 把**基线代码**解到 `/tmp/base_src`
并在其上跑同一张图，以区分「基线本来也跑不起来」与「本次新校验误伤了一张本来能跑的图」。

## Reviewer

- run id: `review-workflow-cycle-contract-20260920-001`
- 时间: 2026-09-20
- 审阅对象: change `workflow-cycle-contract`（issue #219）的实现提交 `dba8809`
- 审阅范围: `agent/subagent/workflow.py`、`agent/tools/builtin/subagents.py`、
  `tests/agent/subagent/test_workflow_cycle_contract.py`、`tests/agent/subagent/test_terminal_honesty.py`
  及全部 change 文档 / delta spec / grill 记录
- 基线 sha: `b0a6604f858c5ea19f95f77618026c250749b2ad`
- head sha: `dba8809387b410c8d292be2bf1b733b2f686c161`
- 审阅方法（实跑命令，均在 worktree 根目录、`export PATH=/home/happy/.local/bin:$PATH` 下执行）：
  - `PYTHONPATH=.:/tmp/rev_cycle uv run python /tmp/rev_cycle/main.py`
    —— 12 张图的「声明期判定 vs 真实 `run()`」对照（含 #219 形态、grill Q1 形态、4 个官方 pattern）
  - `PYTHONPATH=.:/tmp/rev_cycle uv run python /tmp/rev_cycle/fuzz{2,3,4,5,6,7}.py`
    —— 随机小图 fuzz（每轮最多 6 万张，逐个实跑 `run()`），搜「被拒但环真的转过」的误报
  - `PYTHONPATH=.:/tmp/rev_cycle uv run python /tmp/rev_cycle/{fuzz6,minimize,verify_fp,gap_b3,trace_gap_b}.py`
    —— 误报的最小化与机理确认（打印 `_ready_nodes` 的每次 ready 集合与 `activations`/`deadline_fired`）
  - `cd /tmp/base_src && PYTHONPATH=/tmp/base_src uv run python /tmp/rev_cycle/base_run.py`
    —— **在基线提交上**跑同一张图，确认它在基线能声明且能跑
  - `PYTHONPATH=.:/tmp/rev_cycle uv run python /tmp/rev_cycle/{msg_accuracy,fixes,follow_advice,advice_gapb,big_scc,perf,mutation}.py`
    —— 报错三要素的事实核对、修法有效性、信息量上界、性能、变异验证
  - `uv run pytest tests/agent/subagent tests/agent/tools -q` / `uv run pytest -q`
  - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
  - `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
  - `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/rev_cycle/smoke`
  - 全程未修改仓库任何文件（临时脚本全部在 `/tmp/rev_cycle/`；为检验 review 门禁曾临时把 `tasks.md`
    勾选全开，用后已还原，`git status` 干净）

## Verdict

**CHANGES_REQUESTED**

新校验在两张**能被调度器真正跑起来**的图上误报（其中一张在基线提交上声明成功且环真的转过多轮），
推翻了 design D1「取最小不动点 ⇒ 不会误报」的核心安全论证；且报错文案的「缺什么」段把 `route` 的
**控制边**说成 `required` 数据等待（照该条改是无效动作），与本 change 关键路径（D5/Q3「报错必须足以让
模型自己改对」）冲突。

## Task Verification

逐条对 `tasks.md` 与代码/测试找证据。**注意**：`tasks.md` 里 1.x–4.x 与 6.x 的复选框全部留空
（只有 0.x 与 5.1 是 `[x]`），但下面逐条核验的结果表明它们**在实现层基本都做了**——复选框状态与实现
事实不符（见 Issue 5）。

| 任务 | 结论 | 证据 |
|---|---|---|
| 1.1 #219 形态被声明期拒绝 | **做了** | `workflow.py:417` 调用；实跑 `_spin_spec()` → `WorkflowCycleError`，`tests/agent/subagent/test_workflow_cycle_contract.py:83`。runtime 对照：该图在真实 `run()` 里 `status=stalled`、环内节点 `blocked`（`/tmp/rev_cycle/main.py` 输出），拒绝方向正确 |
| 1.2 环内有 subagent 但互等 → 拒绝 | **做了** | 实跑 `_inner_lock_spec()` → 拒绝并点名 `b`/`c`；对照真实 `run()`：`b`/`c` 双双 `blocked`、图报 `completed`——判据确实覆盖了「环内无产出节点」判据会漏掉的形态 |
| 1.3 环内有能自启动 entry → 通过 | **做了** | 测试 `:168`；实跑真实 `run()` 该图 `graph_recursion_exceeded` 且 `producer` 跑了 9 次（环真的转起来） |
| 1.4 环内 `aggregate(strategy="llm")` 能启动 → 通过 | **做了** | 测试 `:206`；实跑 `inner` completed、`gate` 派发 3 次 |
| 1.5 环内 `foreach` 能启动 → 通过 | **做了** | 测试 `:218`；同 1.4 实跑通过 |
| 1.6 回边从 route 出发 → 通过 | **做了** | 测试 `:233` |
| 1.7 回边 `required:false` 且环能启动 → 通过 | **做了** | 测试 `:268`；实跑该图 `body` 一次都没跑（#220 的既有空转语义），但**声明期放行**与 1.7 的任务口径一致（本 change 不修运行期） |
| 1.8 环外 required 数据边喂进环、环内无 entry → 拒绝 | **做了** | 测试 `:305`；实跑 `body`/`gate` 双双 `blocked` |
| 1.9 官方 4 pattern 全部仍能声明通过 | **做了** | 测试 `:323`（`parametrize` 4 例）；我另用 `compile_pattern` 逐个实跑声明，4/4 accepted（含 `peer-review`，初版 D2 的误杀已消除） |
| 1.10 改造 `test_terminal_honesty.py` 绕过声明期校验 | **做了**（质量见下） | `test_terminal_honesty.py:39` 新增 `_spec_without_cycle_check`，5 处 `_deadlock_spec()` 用例改走它（`:198/:209/:338/:425/:516/:665`）；未新增生产旁路 |
| 2.1 新增 `_validate_cycle_can_start`（最小不动点） | **做了** | `workflow.py:900`（不动点实体 `:831::_dispatchable_nodes`） |
| 2.2 新增 `WorkflowCycleError` | **做了** | `workflow.py:83`；工具层 `agent/tools/builtin/subagents.py:435` 用它分流 hint |
| 2.3 复用既有 `_strongly_connected_components`，不改它 | **做了** | `git show dba8809 -- agent/subagent/workflow.py` 未触及 `:700` 的 Tarjan |
| 2.4 只对环分量判定（大小 > 1 或自环） | **做了** | `workflow.py:885::_cycle_members`；`workflow.py:921` 只遍历环分量 |
| 2.5 执行顺序（置于 `_validate_cycles` 之后、不改既有报错优先级） | **做了**（落点与文档描述不同，见 Notes） | `workflow.py:417` 在全量既有校验**与 entry 解析之后**；实测「无 route 的环」仍由 `_validate_cycles` 先报（fuzz 输出 `cycle without a route node`），优先级未被改写 |
| 3.1 报错含三要素 | **做了**（要素二有事实错误，见 Issue 3） | `workflow.py:925-929`（哪个环）/ `:933-960`（谁在等谁）/ `:973-989`（怎么改） |
| 3.2 同环 required 数据边点名 + 建议 | **做了** | `workflow.py:963-979`；实跑 `_spin_spec` 报错含 `declare "required": false on the back-edge(s) ["'body' -> 'cycle_gate'"]`，照做后声明通过 |
| 3.3 `_invalid_spec` 指向性 hint（含 workflow_id 事实） | **做了** | `agent/tools/builtin/subagents.py:435-443`；实跑 `_declare` 返回 `hint` 含 `workflow_id` 字样 |
| 3.4 断言错误信息含要素（不只断言抛异常）并做「模型视角」核对 | **做了** | 测试 `:333/:342/:352/:361`；我独立复核了 3.4 的「模型视角」要求（见 Issue 3：核对不通过） |
| 4.1 描述补核心规则句 | **做了** | `agent/tools/builtin/subagents.py:488-491`（`starts on its own` / `must not wait on anything inside the cycle`） |
| 4.2 描述覆盖回边方向 / `required:false` / `max_routes` | **做了** | `:491-497`（`defaults to 1` / `per route node` / `NOT reset`） |
| 4.3 描述附最小正例与反例 | **做了** | `:499-511`（`Correct cycle (...)` / `Rejected cycle (...)`），两段都是可实跑的 spec 骨架，我逐条实跑：正例 accepted 且真循环，反例 rejected |
| 4.4 测试断言描述含关键契约词 | **做了**（断言偏弱，见 Issue 6） | 测试 `:395/:401/:413` |
| 5.1 运行期诊断不做 | **符合说明** | `tasks.md:58` 已 `[x]` 并写明理由；design C 段与 proposal 一致 |
| 6.1 官方 4 pattern 回归红线 | **做了** | 同 1.9 |
| 6.2 变异验证（用有区分度的变异） | **做了** | 我在 `/tmp` 复刻判据做变异：删 `required` 判断 → 1.7 正例被误拒（可被抓住）；删「是 entry」分支 → `peer-review` 被误拒（可被 1.9 抓住）。两条变异都有区分度，与 design Testing Strategy 的更新一致 |
| 6.3 `tests/agent/subagent/` + 全量 pytest | **做了** | `tests/agent/subagent tests/agent/tools` → 905 passed；全量 → **2968 passed, 8 skipped**（我另单独跑了两条「已知无关失败」，均 passed） |
| 6.3b benchmark smoke | **做了** | `uv run asterwynd benchmark ... --agent fake` 正常收敛输出汇总（72 tasks / 5 passed / 29 failed，与本次改动无关的既有分布），无声明期校验引发的崩溃 |
| 6.4 同步 current spec | **未做（预期内）** | `openspec/specs/multi-agent-collaboration/spec.md` 尚未含新 Requirement（`grep -c workflow-cycle-contract` = 0）——属收尾阶段动作 |
| 6.5 `/review-loop` | **本条即该任务** | —— |
| 6.6 归档 + backlog 移除 | **未做（预期内）** | `dispatch` 后由收尾完成 |
| 6.7 OpenSpec validate + artifact checker | **做了** | `validate --all --strict` → 30 passed / 0 failed；`check_openspec_artifacts.py` → passed |
| 6.8 建 PR | **未做（预期内）** | —— |
| 6.9 文档影响检查 | **部分（见 Issue 7）** | `docs/openspec-change-backlog.md:110` 仍写着**被 grill 推翻的旧判据**；变更自身的 proposal/design/tasks/spec delta 已按 grill 重写 |

## Issues

### 1. **blocker** — 判据漏掉 `_ready_nodes` 的 `deadline_fired` 短路，误拒「环内 best_effort 聚合」这类真能跑起来的图

- **证据**：`agent/subagent/scheduler.py:1486-1488` —— `_ready_nodes` 对 `state.deadline_fired` 为真的
  节点**直接放行**，既不看 `_data_deps_satisfied` 也不看 `activations`（`scheduler.py:1486-1488`）：
  ```python
  if state.deadline_fired:
      ready.append(state)
      continue
  ```
  `deadline_fired` 的唯一置位点是 `scheduler.py:2195-2201::_fire_best_effort_deadlines`（`join == "best_effort"`
  且 `deadline_ref` 已设、`deadline_s` 已过）。而 `workflow.py:831::_dispatchable_nodes` 的最小不动点
  **只复刻了数据门控 + `activations` 两条**，没有这条短路。判据因此在这个方向上**偏悲观**（漏掉一条真实
  派发路径），与 design.md:60-64「乐观只漏报、不误报」的安全论证方向相反。
- **复现**（最小 spec，3 节点；`best_effort` 聚合在环内、环是 `gate ↔ body`）：
  ```json
  {"goal": "gap B", "recursion_limit": 20, "max_runs": 60,
   "nodes": [
     {"id": "seed", "kind": "subagent", "task": "seed", "outputs": ["result"]},
     {"id": "gate", "kind": "route", "task": "gate", "max_routes": 3,
      "cases": [{"when": "GO", "to": "body"}], "default": "body"},
     {"id": "body", "kind": "aggregate", "strategy": "collect",
      "join": "best_effort", "deadline_s": 0.05, "outputs": ["result"]}],
   "edges": [
     {"from": "seed", "to": "body", "required": false, "reducer": "concat"},
     {"from": "gate", "to": "body"},
     {"from": "body", "to": "gate", "reducer": "concat"}],
   "entry": ["seed"], "terminal": ["gate"]}
  ```
  实跑（`/tmp/rev_cycle/trace_gap_b.py`，打印每轮 ready 集）：
  ```
  [ready] ['body'] | seed:(st=cancelled) body:(st=pending, act=0, deadline_fired=True)   ← 到点直接放行
  [ready] ['gate'] | body:(completed)
  [route gate] targets=['body']
  ... 三轮后
  final: graph_recursion_exceeded {'gate': 3}   body=completed  gate=blocked
  ```
  即 `body` **真的被派发并完成**、`gate` **真的派发了 3 次**——环转了；但声明期报的是
  `cycle can never start: nodes ['body', 'gate'] ... can never be dispatched`，与实跑直接矛盾。
- **基线对照**（证明这是「误伤本来能跑的图」，不是「基线也跑不起来」）：`git archive b0a6604 | tar -x -C /tmp/base_src`
  后在基线代码上跑同一张图 → `parse_workflow_spec` **accepted**、`run()` 结果同样是
  `graph_recursion_exceeded {'gate': 3}`、`body=completed`。**这张图在本次改动前声明成功且能循环。**
- **影响面**：`best_effort` + route 环是 design D1 自己点名要支持的形态（`scheduler.py:2281` 的
  `_merge_contributions_bounded` 与 `best_effort` 都是既有能力），而 tasks/design 的测试清单里
  **没有一条 best_effort 环用例**（`grep best_effort tests/agent/subagent/test_workflow_cycle_contract.py` 为空），
  所以这个误报没有测试能拦住。
- **建议修法**（择一，需在 design/spec 同步理由）：
  (a) 把 `deadline_fired` 复刻进不动点——即 `best_effort` 且 `deadline_s` 非空的节点视为「可自启动」；
  或 (b) 承认这一路径不可静态判定，把判据**收窄为「环内无可派发节点 **且** 环内不存在 `best_effort` 聚合」
  （即在该形态上放行、退回运行期诊断）；并**必须补一条 best_effort 环的实跑用例**（声明放行 + 环真转）。

### 2. **major** — 判据只认「声明边」上的 route 激活，漏掉 `cases`/`default` 目标无声明边时的激活，误拒真循环的图

- **证据**：`workflow.py:851-858` 的 `control_incoming`/`data_incoming` 完全由**声明边**构造
  （`if edge.source in control_sources` 决定这条边是控制边还是数据边）。但调度器
  `scheduler.py:1741-1777::_execute_route` 的激活对象是 `state.targets`——来自 `cases[].to` / `node.default`，
  **按 target id 直接 `activations += 1`（`:1771-1775`），从不检查有没有对应边**；而
  `workflow.py::_validate_kind_specific` 只要求 `case.to`/`default` 是**已知节点 id**，不要求存在边。
  于是「route 用 default 指向环内节点、但没写这条边」是一张能被调度器真正跑起来的合法图，
  静态模型却看不到这条激活路径。
- **复现**（`/tmp/rev_cycle/trace_cand3b.py`，fuzz 自动搜出后最小化）：`n3`(route，entry) 的 `default` 指向
  `n0` 但**没有 `n3 -> n0` 边**；环 `{n0, n1, n2}` 中 `n1` 只有数据入边（无控制入边，`_ready_nodes`
  的第 4 个条件对它直接不成立）。
  ```
  静态：entry=['n3']，可派发=['n3']；被拒环 = [['n0','n1','n2']]
  实跑：ready#4 ['n1','n3'] → route n1 -> ['n0']、route n3 -> ['n0'] → n0 重跑
        final: graph_recursion_exceeded {'n3': 3, 'n1': 2}，n0=completed
  ```
  被报错点名「can never be dispatched」的 `n1` 派发了 2 次、`n0` 跑到了 `completed`。
- **搜索证据**：约束 fuzz（要求每个 route 目标都有声明边，`/tmp/rev_cycle/fuzz5.py`）在 351 张被拒图中
  仍有 20 张「被拒环内的 route 真的转过」；`fuzz7.py` 另有 32 张「实现拒、spec 字面判据放行且图健康」。
  这说明误报不是孤例，而是判据建模面的系统性缺口。
- **建议修法**：把 `cases[].to` / `default` 也计入控制激活来源（按「可能被选中」的乐观口径并入
  `control_incoming`，方向仍是只漏报不误报）；或反过来在校验层**要求 route 的每个 `cases`/`default`
  目标必须有声明边**（这是更强的 schema 收紧，需在 spec 里写明并补测试）。无论选哪条，都应补一条
  「route 目标无声明边」的用例锁定方向。

### 3. **major** — 报错「缺什么」段把 `route` 的**控制边**说成 `required` 数据等待，该条修法是无效动作

- **证据**：`workflow.py:934-937` 的 waiting 循环遍历的是**全量 `edges`**（`for edge in edges`），
  只过滤 `edge.required`，**没有排除 route 出边**；而同一函数 :963-971 构造 `same_cycle_required` 时
  **排除了** `edge.source not in control_sources`。同一份报错里两处口径不一致。
- **实跑**（`/tmp/rev_cycle/msg_accuracy.py`，`_spin_spec` 即 #219 形态）：
  ```
  waiting on: 'body' waits for required data from 'cycle_gate' (same cycle); ...
  ```
  但 `cycle_gate` 是 `route`，`cycle_gate -> body` 是**控制边**、按 `is_control_edge`（`workflow.py:252-254`）
  与 `data_incoming`（`:256-262`）**不参与数据门控**。而模型能做的动作是「给这条边加 `required: false`」——
  我实跑了这个动作：**图仍被拒**（该边本来就不门控，改了没有任何效果）。
  真正有效的是 `how to fix` 段点名的 `'body' -> 'cycle_gate'`（实跑：照做后 accepted）。
- **为什么是本 change 的关键路径**：`_invalid_spec` 的返回体**没有 `workflow_id`**（design D3 已写明），
  `reason` + `hint` 是模型唯一信息来源。用户裁决（grill Q3）是「要确保给到 llm 足够的信息引导他改正」，
  而「缺什么」段的第一条就把模型指向一个**改了也没用**的边——这正是 `workflow-terminal-honesty` 立下的
  「答错比答不出更糟」标准要消灭的那类假话。同一 design 的 D5 也明确把
  `'body' waits for required data from 'cycle_gate' (same cycle)` 列为**要素二的样板文案**（design.md:133），
  所以这条不是笔误，是设计里就写错了。
- **建议修法**：waiting 段复用 `data_incoming` 口径（排除 route 出边），或在文案里显式区分
  「required 数据等待」与「等待 route 激活」；并补一条断言：报错中不得把控制边的 source 说成
  required 数据等待（可用 `_spin_spec` + `assert "'body' waits for required data from 'cycle_gate'" not in msg`）。

### 4. **minor** — 报错信息在环较大时无界增长，且「有界截断」的两处都没兑现

- **证据**：`workflow.py:925-929` 的 `members`/`stuck` 列表**未截断**，:963 的 `same_cycle_required`
  **未截断**，:960 的 waiting 列表虽 `waiting[:6]` 截断但**不注明「还有 N 条」**。
- **实跑**（`/tmp/rev_cycle/big_scc.py`）：`n=60` 的环报错 **8117 字符**、`n=40` 为 3949 字符；成员列表
  单段就占 4137 字符。design D5 写的是「**有界列出，超出截断并注明还有几个**」，spec delta 也要求
  「环的成员节点 id」（`spec.md:12` 三要素之一）——当前实现与这两处描述不符。
- **旁证**：我没有在 `agent/` 里找到工具结果长度上限/截断代码，所以这段文本会原样进入模型上下文。
  `max_nodes` 默认 200 使得上界有限（实测量级 10^4 字符），不致命，但属于「本 change 自己定的规格没做到」。
- **建议修法**：给 `members`/`same_cycle_required` 加上限并在截断处注明剩余条数（如 `... (+N more)`）。

### 5. **minor** — `tasks.md` 复选框与实现事实不符，导致 `/review-loop` 的机械门禁不生效

- **证据**：`tasks.md` 当前 8 个 `[x]`（全部是 0.x + 5.1）、**33 个 `[ ]`**；但上表逐条核验表明 1.x–4.x
  与 6.1–6.3b/6.7 在实现层都已完成。`scripts/check_openspec_artifacts.py:982::_tasks_all_complete` 要求
  「全部 `[x]`」才判定实现完成，`:1031` 的 review-manifest 门禁与 `:585` 的「自认未完成」内容门槛
  都以此为前置。实测：当前 `tasks.md` 状态下 `check_openspec_artifacts.py` 输出 `passed`（**不检查
  building-review/manifest**）；只有当我把复选框全部打开时，同一命令才报
  `ERROR: building-review.md missing — 独立 subagent 审阅未运行`。
- **影响**：也就是说，「没跑审阅」这件事在当前仓库状态下**不会**被门禁拦住，`#90` 的机械强制在这份
  change 上是空转的。这与 grill Q5（`:262`）依赖的「证据链」口径也不一致。
- **建议修法**：把已完成条目勾上（未做的 6.4/6.6/6.8 保持 `[ ]` 或按阶段拆分），让门禁真正咬合；
  这也是本 change 收尾（6.7）之前必须处理的一步。

### 6. **low** — 测试覆盖缺口：误报的两个形态与若干边界没有用例

- **证据**：`test_workflow_cycle_contract.py` 的 19 个 test 函数（22 例）覆盖了 #219 形态、grill Q1 形态、
  4 个官方 pattern 与报错三要素，但：
  - **无 `best_effort` 环用例**（Issue 1 的误报因此没被拦住）；
  - **无「route 目标无声明边」用例**（Issue 2）；
  - **无自环用例**（`_cycle_members` 的 `component[0] in adjacency[...]` 自环分支 `workflow.py:894`
    没被任何测试执行；我实跑自环 route → accepted、`run()` 正常）；
  - **无「多个环同时存在、其中一个可启动一个不可启动」用例**（我实跑：可启动的那个环照常跑完，
    不可启动的被拒——行为正确，但无测试锁定）。
- **另有断言偏弱处**：`:333::test_reason_says_what_is_missing` 只断言 `"wait" in msg.lower()` 与
  `"required" in msg.lower()`；`:413` 只断言 `"correct"/"valid"/"works"` 与 `"wrong"/"rejected"/"bad"`
  出现过——把正例段整体删掉后（`Correct cycle` 仍在别处出现）这类断言未必变红。它们不是「假保护」
  （确实有区分度），但保护强度低于 design Testing Strategy 承诺的「报错三要素逐条断言」。
- **建议**：补上述四类用例；把 :413 改成断言正例/反例的**具体节点串**（如 `gate->producer (control back-edge)`
  与 `body->gate (DATA edge`），使删段落必然变红。

### 7. **low** — `docs/openspec-change-backlog.md` 仍写着被 grill 推翻的旧判据

- **证据**：`docs/openspec-change-backlog.md:110`：`+ 两条**声明期静态校验**（空转环：SCC 内无产出节点；
  回边死锁：route 有同环内 required 数据入边）`——这是 0.7 已重写的旧方案（grill 实测证伪并已被
  用户裁决替换，见 `reviews/grill-design.md:258-259`）。同段 :108 的契约清单里也仍是「环内必须有产出节点」。
- **影响**：change 自身的 design/proposal/tasks/spec delta 已按 grill 重写，但 backlog 未同步，形成
  「同一 change 的两种口径并存」。tasks 6.9（文档影响检查）与 6.6（backlog 移除）尚未做，属收尾范围，
  但 backlog 是**受保护路径**，更新时需 `workflow-events.jsonl` 结构化事件。
- **建议**：收尾同步时把该段的判据描述改为不动点判据（或直接随 6.6 移除整条 backlog 条目）。

## Notes

非阻塞观察项，供后续跟进：

- **判据落点与文档描述不符（非缺陷）**：design.md:213 与 tasks 2.5 说新校验「与 `_validate_cycles` /
  `_validate_foreach_source_cycles` **并列**，置于其后」，实际落在 `workflow.py:417`——在全量既有校验**与
  `entry`/`terminal` 解析之后**。这个位置是**必要的**（判据要用含隐式推导的最终 entry 集，见 `:414-416`
  的注释），行为也符合 2.5 的意图（「无 route 的环」仍由 `_validate_cycles` 先报，实测确认优先级未变）。
  建议顺手把 design/tasks 的行号口径改成与实现一致，避免下一位读者按文档去 `_validate_cycles` 后面找。
- **`_entry_set` 并入隐式入口，方向安全**：`workflow.py:827-828` 把「无任何入边」的节点并入 entry 集，
  而 `parse_workflow_spec` 只在 `entry` 为空时才推导隐式入口——看似多给了 entry。实测无影响：这类节点
  必然没有控制入边，不动点第 2 条的「没有控制入边」分支已经覆盖它，所以这一并集是冗余而非偏差。
- **大图性能可接受**：`/tmp/rev_cycle/perf.py` 实测——200 节点 / 1970 条边约 57 ms，200 节点近全连接
  （19919 条边，实际不可能出现，`max_nodes` 与 reducer 校验会先拦）约 512 ms。默认 `max_nodes=200`
  下声明期开销在 10^0–10^2 ms 量级，无风险。
- **`test_terminal_honesty.py` 的改造（grill Q5）经独立复核合格**：`_spec_without_cycle_check`
  （`:39-72`）用的是 `workflow.py` 既有的解析 helper（`_parse_node`/`_parse_edge`）直接组装 dataclass，
  **没有在生产代码里新增旁路**（我 grep 了 `agent/` 下 `WorkflowSpec(` 的构造点：只有
  `workflow.py:419` 与 `aggregation.py:251`，都不是新加的口子）。改后的断言强度未被弱化：被改造的
  5 处仍断言运行期行为（`status == "stalled"`、零节点 `completed`、`blocked` 因由含「入边互相等待」、
  因由长度落在前端展示预算内、前端标记词表与后端文案一致），且 `bypass=True` 只用在 `_deadlock_spec()`
  这一张**声明期本就该被拒**的死锁图上，其余用例仍走 `parse_workflow_spec` 正门。这个处理是正确的。
- **`WorkflowCycleError` 的引入是必要的**：`agent/tools/builtin/subagents.py:445-452::_invalid_spec` 靠
  `isinstance` 分流指向性 hint；同时它让 `test_runtime_diagnosis_survives_declaration_rejection`
  （`:423`）能表达「运行期测试知道该绕过哪一个入口」。命名与周边（`WorkflowValidationError` /
  `WorkflowBudgetExceeded`）一致，注释密度与文件其余部分相当。
- **提示面文案实测可照做**：我逐字实跑了 `DeclareWorkflow` 描述里的正例与反例骨架（`/tmp/rev_cycle/fixes.py`）：
  正例 accepted 且 `run()` 真的循环（`graph_recursion_exceeded`，`producer`/`reviewer` 都 complete），
  反例 rejected 且 `run()` 报 `stalled`。两段示例是**准确**的，D4 的「契约靠示例传达」落实到位。
- **任务 6.4/6.6/6.8 属收尾阶段**，本轮不视为缺失；但 Issue 5 指出它们留在 `[ ]` 会让门禁静默，
  建议收尾时按「哪些阶段该勾」重新整理复选框。

## 复现脚本清单（均在 `/tmp/rev_cycle/`，未进仓库）

| 脚本 | 用途 |
|---|---|
| `main.py` | 12 张图的「声明期判定 vs 真实 `run()`」对照 + 官方 4 pattern |
| `fuzz2/3/4/5/6/7.py` | 随机图 fuzz，搜「被拒但环真的转过」的误报（含约束版：route 目标都有声明边） |
| `minimize.py` | 误报图的贪心最小化（保留「被拒 + 环转过」） |
| `trace_gap_b.py` / `gap_b3.py` / `trace_cand3b.py` | Issue 1 / Issue 2 的机理确认（打印 ready 集与 `activations`/`deadline_fired`） |
| `base_run.py`（配 `/tmp/base_src`） | **在基线 `b0a6604` 代码上**跑同一张图，证明是误伤 |
| `msg_accuracy.py` / `fixes.py` / `follow_advice.py` / `advice_gapb.py` | Issue 3 的事实核对与修法有效性 |
| `big_scc.py` | Issue 4 的报错长度上界 |
| `perf.py` | 大图上的校验性能 |
| `mutation.py` | 6.2 变异验证的独立复刻（删 `required` 判断 / 删「是 entry」分支） |
