# Building Review (Round 2): 循环图的契约对模型可见（workflow-cycle-contract）

我是**独立零记忆**的实现审阅员（`/review-loop` 第 2 轮，AGENTS.md #90 机械强制）：本次会话未读取任何先前
对话，本 worktree 的代码、文档与 git 历史是我唯一的事实来源。所有结论都来自**亲自 Read / 实跑**，不采信
首轮报告或 design 的自我断言。

审阅方法（本轮的重点是「不信首轮、自己验」）：先把 `scheduler.py` 的真实派发链
（`_ready_nodes` / `_data_deps_satisfied` / `_is_entry` / `_dispatch` / `_execute_route` /
`_fire_best_effort_deadlines` / `_reset_subtree`）全文读完，建立**调度器派发语义的独立模型**；再在 `/tmp`
下写独立脚本把「声明期判定」与「真实 `WorkflowScheduler.run()` 结果」逐图对照。为验证首轮两条误报修复，
我把**基线 `b0a6604`** 与**首轮修复前 `dba8809`** 两份代码分别 `git archive` 解到 `/tmp` 并在其上实跑同一
批图，以区分「本来也跑不起来」与「本次改动误伤/漏判」。核心验证手段是**随机图 fuzz 交叉验证**：随机生成含
route/subagent/aggregate/foreach 的小图，凡被 `WorkflowCycleError` 拒的，一律实跑 `run()` 看被点名
「can never be dispatched」的节点是否真的没跑。

## Reviewer

- run id: `review-workflow-cycle-contract-20260920-r2`
- 时间: 2026-09-20
- 审阅对象: change `workflow-cycle-contract`（issue #219），首轮修复提交 `38d7630` + 文档同步 `afeb27b`
- 审阅范围: `agent/subagent/workflow.py`、`agent/tools/builtin/subagents.py`、
  `tests/agent/subagent/test_workflow_cycle_contract.py`、`tests/agent/subagent/test_terminal_honesty.py`，
  以及全部 change 文档 / delta spec / 首轮审阅记录
- 基线 sha: `b0a6604f858c5ea19f95f77618026c250749b2ad`
- head sha: `afeb27b2181f6d37ccb8028098d599688ae4205b`
- 实跑命令（均在本 worktree 根目录、`export PATH=/home/happy/.local/bin:$PATH` 下执行；临时脚本全部在
  `/tmp/r2/`，未进仓库）：
  - `PYTHONPATH=/tmp/r2:$PWD uv run python /tmp/r2/fuzz3.py {s} {n}`
    —— 多 verdict（CONTINUE/GO/APPROVED/STOP/REJECT）随机图 fuzz，搜「被拒但被点名节点真的跑了」的误报；
    另用 `fuzz2.py`（含 foreach + best_effort）、`seq.py`（verdict 时序：GO/STOP 交替，探索乐观上界）
  - `PYTHONPATH=/tmp/r2:$PWD uv run python /tmp/r2/overstrict.py {s} {n}` / `fn_hunt2.py` / `fn_size.py`
    —— 反向验证：被拒图的被点名节点是否真的从未派发；以及「声明放行但某个环零节点完成、图仍报成功」的漏报
  - `PYTHONPATH=/tmp/r2:/tmp/base_src uv run python /tmp/r2/base_run.py`（基线）
    与 `PYTHONPATH=/tmp/r2:/tmp/prev uv run python /tmp/r2/prev_check.py`（首轮修复前 `dba8809`）
    —— 证明首轮 Issue 1/2 是真修复（不是「基线也跑不起来」）
  - `PYTHONPATH=/tmp/r2:$PWD uv run python /tmp/r2/{msgcheck,fixcheck,desc_examples,big,worst,perf,fn_min,fn_b2,fn_real,weakassert}.py`
    —— 报错三要素逐句核对 + **逐条照做验证修法有效性** + 描述内正反例实跑 + 报错长度上界 + 性能
  - `python3 /tmp/r2/mutate.py`（配 `/tmp/mut` 全仓副本）—— 变异验证：逐条改坏实现，看新增用例是否变红
  - `uv run pytest -q` / `uv run pytest tests/agent/subagent tests/agent/tools -q` / `uv run pytest tests/web_tests -q`
  - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
  - `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
  - `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/r2/smoke`
  - 全程未修改仓库任何文件（`git status` 干净；产出只有本文件）

## Verdict

**PASS**

首轮 4 条误报/文案缺陷（blocker 1 / major 2 / minor 2）**逐条实跑复核确认真修复**——两条误报在修复前
提交 `dba8809` 上可复现、在 HEAD 上消失，且其中 best_effort 一条在**基线 `b0a6604`** 上确能声明并真循环；
约 700 张随机被拒图逐个实跑，**零误报**；6 条新增用例逐个做变异验证，**全部被杀死**。本轮新发现的问题
均为 minor/low（一个方向正确但可收窄的漏报面、一个 manifest 绑定的流程漏洞、一处注释口径），无 blocker、
无未解决 major。

## Round 1 Issue Re-check

| # | 首轮结论 | 本轮复核 | 证据 |
|---|---|---|---|
| 1 | **blocker**：不动点漏 `deadline_fired` 短路，误拒环内 `best_effort` 聚合 | **已修好** | 修复前 `dba8809` 对该图抛 `WorkflowCycleError`；HEAD **接受**且实跑与基线一致（`graph_recursion_exceeded`、`body=completed`、`gate` 派发 3 次）。**基线对照**：`b0a6604` 上该图 `parse_workflow_spec` **accepted**、`body` completed——证明这是「本来能跑、首版误伤」，修复方向正确。代码落点 `workflow.py:926-935`（`best_effort` + `deadline_s` + 任一数据源可派发）。 |
| 2 | **major**：`_route_activators` 漏 `cases[].to`/`default` 目标 | **已修好** | `dba8809` 对「route 目标无声明边」图抛 `WorkflowCycleError`；HEAD **接受**。新增 `_route_activators`（`workflow.py:854-878`）把 `cases[].to`（`:873`）、`default`（`:875`）、声明出边（`:877-878`）一并计入。方向正确（超集）。 |
| 3 | **major**：报错把 route **控制边**说成 required 数据等待 | **已修好，且逐条照做验证** | waiting 段（`workflow.py:1003-1010`）显式 `if edge.source in control_sources: continue`。实跑 `_spin_spec` 报错，逐句核对三问：「谁在等谁」只列 `'body' is not an entry: ... activated by route(s) cycle_gate, which cannot run either` 与 `'cycle_gate' waits for required data from 'body' (same cycle)`——**不再出现**首轮那句假话；「怎么改」三选一逐条实跑：`required:false on body->cycle_gate` → accepted；条目二的字面读法（只把 body 喂自环外、不列 entry）→ **仍被拒**（措辞偏歧义，见 Notes），但按其括注「若还有 route 指向它，要列进 `spec.entry`」照做 → accepted；条目三（断环）→ accepted。**每条建议照做后图都真的能过**。 |
| 4 | **minor**：报错无界增长、截断不注明剩余条数 | **已修好** | 新增 `_bounded` + `_ERROR_LIST_LIMIT = 8`（`workflow.py:833-852`）。实测 58 节点环报错 **1299** 字符、199 节点环 **1331** 字符（首轮为 8117），三段列表均带 `(+N more)`，如 `... n51 (+51 more)`。 |
| 5 | **minor**：`tasks.md` 复选框与实现不符，门禁静默 | **已修好** | 现 45 个 `[x]` / 5 个 `[ ]`（未勾的是 6.4/6.5/6.6/6.8/6.9）。门禁已**咬合**：`check_openspec_artifacts.py` 现在会走到 review-manifest 检查并报 `ERROR: ... review manifest missing`（exit 1）——首轮「跑审阅也不会被拦」的状态消失。该报错属预期内（manifest 由审阅 PASS 后生成），见 Notes。 |
| 6 | **low**：测试覆盖缺口（无 best_effort 环/无 route 无声明边/无自环/无多环并存）＋ 2 条弱断言 | **已修好** | 6 条新用例齐备（`test_workflow_cycle_contract.py` 共 25 个 test 函数）：`test_best_effort_aggregate_in_cycle_is_not_a_false_positive`、`test_route_activation_without_declared_edge_is_not_a_false_positive`、`test_self_loop_route_is_accepted`、`test_one_stuck_cycle_among_startable_ones_is_rejected`、`test_error_message_is_bounded_for_a_large_cycle`、`test_reason_does_not_blame_the_control_edge`。2 条弱断言已加严为具体节点串（`:485` 断言整句 `'cycle_gate' waits for required data from 'body' (same cycle)`；`:578/:580` 断言 `gate->producer` / `body->gate`），删段落必然变红。 |
| 7 | **low**：`docs/openspec-change-backlog.md` 仍写被 grill 推翻的旧判据 | **未修好（预期内）** | `docs/openspec-change-backlog.md:110` 仍为「空转环：SCC 内无产出节点；回边死锁：route 有同环内 `required` 数据入边」。tasks 7.7 明说「随 6.6 移除整条条目」，而 6.6 未做，故属收尾范围；backlog 是受保护路径，更新需 `workflow-events.jsonl` 事件。**不构成本轮阻塞**，但收尾时必须处理（见 Issue 3）。 |

## Task Verification

| 任务 | 结论 | 证据 |
|---|---|---|
| 1.1 #219 形态被声明期拒绝 | **做了** | `parse_workflow_spec(_spin_spec())` → `WorkflowCycleError`；对照真实 `run()`（绕过后）`status=stalled`、环内节点 `blocked` |
| 1.2 环内有 subagent 但互等 → 拒绝 | **做了** | 实跑 `_inner_lock_spec()` → 拒绝并点名 `b`/`c`（`workflow.py:964` 的判据确实覆盖「有产出节点」判据会漏的形态） |
| 1.3 环内有能自启动 entry → 通过 | **做了** | `_startable_loop_spec()` accepted |
| 1.4 环内 `aggregate(strategy="llm")` → 通过 | **做了** | 用例通过；实跑 `inner` completed |
| 1.5 环内 `foreach` → 通过 | **做了** | 用例通过 |
| 1.6 回边从 route 出发 → 通过 | **做了** | `is_control_edge(gate->producer)` 为真 |
| 1.7 回边 `required:false` 且环能启动 → 通过 | **做了** | `_open_back_edge_spec()` accepted |
| 1.8 环外 required 数据边喂进环、环内无 entry → 拒绝 | **做了** | 用例 `:305` 通过 |
| 1.9 官方 4 pattern 仍能声明 | **做了** | `test_builtin_patterns_still_declare` parametrize 4 例全绿；我另实跑 `compile_pattern` 逐个声明，4/4 accepted；并单独核对 4 个 pattern 的 route 形态（仅 `peer-review` 有 route，且其 route **有数据入边** `reviewer`，故 `cases` 可达） |
| 1.10 改造 `test_terminal_honesty.py` | **做了，且无生产旁路** | `_spec_without_cycle_check`（`:39`）用 `workflow.py` 既有 `_parse_node`/`_parse_edge` 直接组装 dataclass；5 处 `bypass=True` 全用于 `_deadlock_spec()`。全仓 `WorkflowSpec(` 构造点仅 `workflow.py:419`（正门）与 `aggregation.py:251`（plan 展开期重建，非校验旁路），**未新增公开旁路** |
| 2.1 新增 `_validate_cycle_can_start` | **做了** | `workflow.py:964`；不动点实体 `workflow.py:882::_dispatchable_nodes` |
| 2.2 新增 `WorkflowCycleError` | **做了** | `workflow.py:83`；工具层 `subagents.py:437` 用它分流指向性 hint |
| 2.3 复用既有 `_strongly_connected_components`，不改它 | **做了** | `git diff b0a6604..HEAD -- agent/subagent/workflow.py` 未触及 Tarjan 本体 |
| 2.4 只对环分量判定 | **做了** | `workflow.py:949::_cycle_members`（大小>1 或自环）；`_validate_cycle_can_start` 只遍历环分量 |
| 2.5 执行顺序（置于既有校验之后） | **做了（落点与文档行号口径不同，见 Notes）** | `workflow.py:417` 在 entry/terminal 解析之后。实测「无 route 的环」仍由 `_validate_cycles` 先报（`cycle without a route node is not allowed`），优先级未被改写 |
| 3.1 报错含三要素 | **做了** | `workflow.py:988-1053`（哪个环 / 谁在等谁 / 怎么改），实测三段齐备 |
| 3.2 同环 required 数据边点名 + 建议 | **做了** | 实测报错含 `declare "required": false on the back-edge(s) 'body' -> 'cycle_gate'`，照做后 accepted |
| 3.3 `_invalid_spec` 指向性 hint | **做了** | `subagents.py:429-452`；实测 `hint` 含 `workflow_id` 字样与「按 how-to-fix 改后重声明」 |
| 3.4 断言三要素 + 模型视角核对 | **做了** | `:519` 的 `test_declare_failure_is_self_sufficient_for_the_model`；我独立做了模型视角核对（见上表 Issue 3 行） |
| 4.1 描述补核心规则句 | **做了** | `subagents.py:488-491`（`starts on its own` / `must not wait on anything inside the cycle`） |
| 4.2 描述覆盖回边方向/`required:false`/`max_routes` | **做了** | `:492-497`（`defaults to 1` / `per route node` / `NOT reset`） |
| 4.3 描述附最小正例与反例 | **做了，且两段都可实跑** | 我按描述逐字重建两段骨架实跑：正例 accepted 且真循环（verdict `REJECT` 时 `producer`/`reviewer` 各跑 4 次、`graph_recursion_exceeded`）；反例 rejected，且**描述里写的修法**（`required:false on body->gate`）照做后 accepted |
| 4.4 测试断言描述含契约词 | **做了** | `:553/:559/:571`，已改为断言具体节点串 |
| 5.1 运行期诊断不做 | **符合说明** | `tasks.md:58` 已 `[x]` 并写明理由 |
| 6.1 官方 4 pattern 回归红线 | **做了** | 同 1.9 |
| 6.2 变异验证（有区分度的变异） | **做了，我复现并扩展到 6 条** | `/tmp/r2/mutate.py`：删 `deadline_fired` 分支 / 删 `cases`+`default` 激活来源 / 恢复控制边苛责 / 去掉 `_bounded` 截断 / 删 `required` 判断 / 删「是 entry」分支 —— **6/6 全部 KILLED** |
| 6.3 `tests/agent/subagent/` + 全量 pytest | **做了** | `tests/agent/subagent tests/agent/tools` → **911 passed**；全量 → **2971 passed, 8 skipped, 3 failed**（3 条全是 web_tests 浏览器用例，与本 change 无关，见 Notes） |
| 6.3b benchmark smoke | **做了** | `--agent fake` 正常收敛（72 tasks / 5 passed / 38 unsupported / 29 failed，为既有分布），无声明期校验引发的崩溃 |
| 6.4 同步 current spec | **未做（预期内）** | `grep -c "循环图形的声明期校验\|workflow-cycle-contract" openspec/specs/multi-agent-collaboration/spec.md` = 0，属收尾 |
| 6.5 `/review-loop` | **本条即该任务** | —— |
| 6.6 归档 + backlog 移除 | **未做（预期内）** | 见 Round-1 Issue 7 |
| 6.7 validate + artifact checker | **做了（当前 HEAD 上 checker exit 1，属预期内中间态）** | `validate --all --strict` → **30 passed / 0 failed**；`check_openspec_artifacts.py` → `ERROR: review manifest missing`（exit 1）。原因：首轮报告 `building-review.md` 存在但无 manifest，而 `_check_review_manifests` 的 glob 分支**不依赖** `_tasks_all_complete` 就会去校验 manifest（`scripts/check_openspec_artifacts.py:1065-1071`）。审阅收敛后生成 manifest 即恢复，见 Notes |
| 6.8 建 PR | **未做（预期内）** | —— |
| 6.9 文档影响检查 | **部分** | `docs/openspec-change-backlog.md:110` 仍是被推翻的旧判据（同 Round-1 Issue 7）；`docs/architecture.md:104` 的相关段落只讲运行期回边语义，未受本 change 影响，无需改 |

## Issues

### 1. **minor** — 判据在一个**可静态消除**的方向上过近似，漏掉「环真的跑不起来」的图；图级仍报 `completed`（#219 的图形状）

判据方向本身**正确**（过近似 = 超集 = 只漏报不误报，design D1/proposal:58 明确接受），我没有找到任何误报。
但 `_route_activators`（`workflow.py:854-878`）的过近似里有两条分支可以**静态证明永远不会发生**，因而
放行了一些真的会停滞的环。两条子机制我都做了最小复现实跑：

- **(a) route 无任何数据入边时，`cases[].to` 永远不可能被选中。** 调度器 `_route_verdict`
  （`scheduler.py:2451-2470`）的判定文本只由 `data_incoming` 的上游产出拼接而来；无数据入边则 `raw=""`，
  而 `matches_route` 的守卫 `if not verdict or not label: return False`（`scheduler.py:317-318`）直接返回
  False——于是 `cases` 永不命中，`state.targets` 恒为 `default`。静态模型却仍把 `cases[].to` 算作激活来源
  （`workflow.py:873`）。
- **(b) route 的声明出边若既不是该 route 的 `case.to` 也不是 `default`，该出边永不被选中。** 但
  `workflow.py:877-878` 无条件把「route 出边的 target」计入激活来源。
- **复现（(b)，最小）**：`start`(route, entry, default→`R`) → `R`(route, default→`out`，另有声明边 `R→X`)，
  环 `X↔Y`（`X→Y`、`Y→X` 均为控制边），`entry=["start"]`：
  ```
  静态：activators[X]=['R','Y'] → dispatchable 含 X/Y → cycles=[['Y','X']] 全可派发 → ACCEPTED
  实跑（verdict 取 GO/CONTINUE/STOP 三者一致）：
       gstatus=completed  counts={completed:3, failed:0, total:5}
       R   targets=['out']      ← 从未选中 X
       X   blocked  reason='入边互相等待（Y），本节点永远未就绪'
       Y   blocked  reason='入边互相等待（X），本节点永远未就绪'
  ```
  **(a) 的等价最小复现**（`/tmp/r2/fn_min.py`）同样：`gstatus=completed`，环内 `L` 为 `skipped`、
  `R` 从未选中它。**#219 要消灭的「图报成功、环内节点一个没跑」在图形状上复现了**（节点级因由已被
  `workflow-terminal-honesty` 修好、如实说「入边互相等待」，但图级仍 `completed`）。
- **漏报面评估**：我在 `/tmp/r2/fn_size.py`、`fn_hunt2.py` 上按「被拒/放行 + 多 verdict + verdict 时序」
  扫描，放行图中出现「某个环零节点完成且图报成功」的比例约 **10%–20%**（如 seed 71: 3 张放行图里 1 张；
  seed 72: 6 张里 4 张），且**全部**可归到上述 (a)/(b) 两条。作为对照，我用**贴近真实写法**的生成器
  （环体有数据回边、route 有 `body` 作为数据输入的 peer-review 形态，`/tmp/r2/fn_realistic.py`）扫了
  36 张放行图，**0 张死环**——因为真实循环里 route 总有数据可判。所以结论是：**漏报面存在但窄，且集中在
  「route 没有数据入边」这类本身就无判定意义的图上**；真正会重新造成 #219 静默停滞的常见形态（模型把回边
  写反、忘写 entry）仍被拦住。
- **建议（非阻塞）**：若要收窄，可在 `_route_activators` 里加两条**仍保持超集性质、但消除「永不发生」的
  激活**的判据——(a) 该 route 至少有一条数据入边才计入其 `cases[].to`；(b) 声明出边的 target 必须是该
  route 的某个 `case.to` 或 `default` 才计入。两条都只删「可静态证明永不选中」的来源，不会重新引入误报。
  无论改不改，建议补一条用例把**本 change 选定的方向**钉住（现行测试只钉了「不误报」，没钉「漏报可接受」
  的边界），否则下一位读者看到 `fn_min` 这类图会以为是回归。
- 另注：`_route_activators` 的 `activators.setdefault(case.to/default, ...)` 用了 `setdefault`，而
  `case.to`/`default` 已被 `_validate_kind_specific`（`workflow.py:1101`）保证是已知节点、恒在 `index` 中，
  这两处 `setdefault` 是纯防御；把 (b) 的判据收紧时正好可以顺手简化。

### 2. **minor** — review manifest 绑定的是`building-review.md`，而 manifest 生成器**不读报告里的 verdict**；本轮按提示另写 `building-review-r2.md`，会让「CHANGES_REQUESTED 报告 → PASS manifest」成为可能

- **证据**：`agent/workflow/review_manifest.py:91` 的 `build_review_manifest` 有默认参数 `verdict="PASS"`，
  它只记录调用方传入的 verdict，**从不解析报告正文**；`report_hash` 绑定的是
  `review_report_path(...)` = `reviews/building-review.md`（`:52-59`）。而
  `verify_review_manifest`（`:135-173`）只校验 schema / change_id / phase / `verdict == "PASS"` /
  字段非空 / **报告哈希匹配**，**不检查报告正文是否真的写了 PASS**。
- **为什么本轮会踩到**：本轮的产出约定是**新文件** `building-review-r2.md`（不改首轮那份）。于是收敛后的
  artifact 集合会同时存在：`building-review.md` = 首轮的 **CHANGES_REQUESTED**、
  `building-review-r2.md` = 本轮的 PASS。而 `check_openspec_artifacts.py:1065` 的
  `review_dir.glob("*-review.md")` 只匹配 `building-review.md`（`building-review-r2.md` 不匹配），
  manifest 也只绑定前者——**门禁会把首轮那份 CHANGES_REQUESTED 报告哈希当作 PASS 的证据**。
  我实测确认该 glob 行为（`building-review-r2.md` 不进 `*-review.md`），也确认
  `verify_review_manifest` 不会因报告正文写着 CHANGES_REQUESTED 而报错。
- **影响**：这不影响本次实现本身的正确性（本轮结论来自实跑），但它是 #90 机械强制的一个**认证漏洞**：
  「禁止只靠手写 PASS 文本通过 gate」（AGENTS.md 受保护 artifact 证据条）的那道门，可以被一个
  正文写着 CHANGES_REQUESTED 的报告配上 PASS manifest 通过。
- **建议（收尾时处理，非本轮阻塞）**：让**权威 phase 报告** `building-review.md` 在闭环收敛后反映最终
  verdict（由主 session 把最终 PASS 结论落到该文件，或把 r2 内容合并进去），**再**生成 manifest；或让
  `build_review_manifest` 校验报告正文含 `PASS`。二者取一即可。

### 3. **low** — `docs/openspec-change-backlog.md:110` 仍是 grill 已推翻的旧判据（与首轮 Issue 7 同，仍未做）

- **证据**：`:110` 写「两条**声明期静态校验**（空转环：SCC 内无产出节点；回边死锁：route 有同环内
  `required` 数据入边）」，`:108` 仍写「环内必须有产出节点」。这两条正是 `reviews/grill-design.md` 实测
  证伪、design.md:8-11 明说已重写的判据；change 自身的 design/proposal/spec delta 都已按 grill 重写，
  只有 backlog 未同步，形成「同一 change 两种口径并存」。
- 属 tasks 6.6/7.7 的收尾范围（backlog 是受保护路径，更新需 `workflow-events.jsonl` 结构化事件），
  **不构成本轮阻塞**，但收尾移除条目时必须一并处理，否则「判据长什么样」在仓库里仍有第二份说法。

## Notes

非阻塞观察项：

- **本轮全量 pytest 的 3 条失败与本 change 无关，且与任务书里点名的两条「已知失败」不是同一批**：
  `tests/web_tests/test_multi_session_browser.py::test_multi_tab_exit_does_not_affect_other_tab_reconnect`、
  `tests/web_tests/test_workflow_graph_browser.py::test_legend_is_visible_and_collapsible`、
  `tests/web_tests/test_workflow_graph_browser.py::test_collapsed_group_shows_aggregated_status`。
  证据表明是**全量并发下的浏览器用例竞态**：三条单独跑 **3/3 全绿**；`tests/web_tests/` 整目录单独跑
  **340 passed / 0 failed**；两条文件一起跑 **29 passed**。且本 change `git diff --name-only b0a6604..HEAD`
  里 **web 相关改动为 0**。任务书点名的两条
  （`test_tree_sitter_extracts_java_and_kotlin_symbols`、`TestE2eEngineCliSmoke::test_engine_cli_validate_exit_code`）
  我单独实跑均 **passed**，且未出现在本次全量的失败列表里。
- **`check_openspec_artifacts.py` 当前 exit 1 是审阅闭环的正常中间态，不是任务 6.7 造假**：
  `_check_review_manifests`（`scripts/check_openspec_artifacts.py:1060-1071`）里，只要 `reviews/` 下存在
  `*-review.md` 就会去校验其 manifest，**不受** `_tasks_all_complete` 前置约束；当前 `building-review.md`
  在、manifest 不在，故报错。6.5 收敛后生成 manifest 即恢复。注意它与 Issue 2 叠加：恢复的前提是
  `building-review.md` 的正文与被绑定的 verdict 一致。
- **报错「怎么改」条目二的字面读法会误导**：`workflow.py:1043-1047` 的 `give the cycle a node that starts
  on its own: make {seed!r} (or another member) an entry whose required inputs come from outside the cycle; if
  a route also points at it, list it in spec.entry`。我实跑其**字面读法**（只把 `body` 从环外喂入、不加
  entry）→ **仍被拒**；只有加上「列进 `spec.entry`」才对。对 `_spin_spec` 这种 body 也有 route 控制入边的
  图，真正生效的是后半句。建议把「先列 entry」前置为显式步骤（或把 `make {seed} an entry` 写成主句、把
  「required inputs come from outside」写成附注），可进一步降低模型的试错成本。**当前文案已足够让模型改对**
  （三条建议里有两条照做即过），故列为观察项而非 issue。
- **报错成员列表按字典序、`seed` 取 `min(members)`**：图大时 `min(["n10","n2"]) == "n10"`，建议里的
  「make 'n10' an entry」只是示例节点，不影响正确性；但若想让建议更符合直觉，可按声明序取。
- **`_bounded` 的 `items: Any` 型参与文档**：`workflow.py:836-852` 的 docstring 说「接受可迭代对象（不是
  单个字符串——传字符串会被逐字符拆开）」，而代码首行 `if isinstance(items, str): items = [items]` 已
  处理字符串，措辞与实现略有出入（应为「字符串会被当单项处理」）。纯措辞，不影响行为。
- **测试文件头注释的「取最小集」与 design 的「取超集」相互矛盾**：
  `tests/agent/subagent/test_workflow_cycle_contract.py:6-7` 写「按调度器真实派发语义……的**最小不动点**
  静态判定——**取最小集**，故只拒绝可证明跑不起来的环，不误报」。判据实际取的是**过近似（超集）**；
  「最小不动点」是单调算子的标准术语（从空集迭代到不再增长），但与「最小集」并列会让人误以为判据偏保守。
  建议改成「取最小不动点，但每条规则都取乐观口径（过近似 ⇒ 超集）」，与 design D1 一致。
- **性能可接受**：`/tmp/r2/perf.py` 实测 200 节点 DAG 约 **5.6 ms**、200 节点大环约 **2.8 ms**、
  199 节点最坏环（全数据边）约 **14.9 ms**；默认 `max_nodes=200` 下声明期开销在 10^0–10^1 ms 量级。
- **`test_one_stuck_cycle_among_startable_ones_is_rejected` 的 `assert "live" not in message`** 是子串
  断言，将来文案里出现 `deliver`/`lively` 之类会假红。当前无此风险，属可选加固。
- **`_entry_set` 并入隐式入口仍是冗余而非偏差**（首轮 Notes 的结论我复核成立）：`workflow.py:819-829`
  把「无任何入边」的节点并入 entry 集，而 `parse_workflow_spec` 只在 `entry` 为空时才推导隐式入口——看似
  多给了 entry；但这类节点没有控制入边，不动点第 2 条的「`not controllers`」分支本就覆盖它，方向仍是超集。
- **校验落点与文档行号口径**：design.md:240-242 与 tasks 2.5 说新校验「置于 `_validate_cycles` 之后」，
  实际在 `workflow.py:417`（全量既有校验**与** entry/terminal 解析之后）。该位置**必要**（判据要用含隐式
  推导的最终 entry 集），行为也符合 2.5 的意图；建议把文档行号口径改成与实现一致，省得下一位读者按文档去
  `_validate_cycles` 后面找。

## 复现脚本清单（均在 `/tmp/r2/`，未进仓库）

| 脚本 | 用途 |
|---|---|
| `fuzz2.py` / `fuzz3.py` / `seq.py` | 随机图 fuzz 搜误报（多 verdict；含 verdict 时序版） |
| `overstrict.py` / `fn_hunt2.py` / `fn_size.py` / `fn_realistic.py` | 反向验证：被拒图的被点名节点是否真没跑；放行图的漏报面与分类 |
| `base_run.py`（配 `/tmp/base_src`） | **基线 `b0a6604`** 上跑 best_effort 环图，证明首版误伤 |
| `prev_check.py`（配 `/tmp/prev`） | **首轮修复前 `dba8809`** 上复现 Issue 1/2，证明修复真实 |
| `msgcheck.py` / `fixcheck.py` / `desc_examples.py` | 报错三要素核对、逐条照做验证修法、描述正反例实跑 |
| `big.py` / `worst.py` | 大环报错长度上界与截断注明 |
| `fn_min.py` / `fn_b2.py` / `fn_real.py` | 漏报（Issue 1）两条子机制的最小复现实跑 |
| `perf.py` | 大图校验性能 |
| `mutate.py` | 变异验证（6 条变异对新增用例，配 `/tmp/mut` 全仓副本） |
| `weakassert.py` | 复核被加严的断言是否真有区分度 |
