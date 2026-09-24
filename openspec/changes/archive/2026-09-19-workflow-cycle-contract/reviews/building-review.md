# Building Review: 循环图的契约对模型可见（workflow-cycle-contract）

**本文件是权威阶段报告，覆盖 `/review-loop` 的两轮**（`/review-loop` 要求「PASS 或 3 轮封顶」）。
第 1 轮由独立零记忆 subagent 跑，verdict = CHANGES_REQUESTED（7 条）；第 2 轮由**另一位**独立零记忆
subagent 重跑（**不采信首轮结论、自己复现**），verdict = **PASS**。

两份审阅都不读此前任何对话，只以本 worktree 的代码、文档与 git 历史为事实来源；所有结论来自**实跑**，
不采信 design/proposal 的自我断言。第 2 轮的核心手段是**随机图 fuzz 交叉验证**：随机生成含
route/subagent/aggregate/foreach 的小图，凡被 `WorkflowCycleError` 拒的，一律实跑
`WorkflowScheduler.run()`，看被点名「can never be dispatched」的节点是否真的没 `completed`。

## Reviewer

- run id（Round 1）: `review-workflow-cycle-contract-20260920-001`
- run id（Round 2）: `review-workflow-cycle-contract-20260920-r2`
- 时间: 2026-09-20
- 审阅对象: change `workflow-cycle-contract`（issue #219）
- 基线 sha: `b0a6604`（立项提交）
- Round 1 head sha: `dba8809`（首版实现）
- Round 2 head sha: `afeb27b`（首轮修复 `38d7630` + 文档同步 `afeb27b`）
- 审阅范围: `agent/subagent/workflow.py`、`agent/tools/builtin/subagents.py`、
  `tests/agent/subagent/test_workflow_cycle_contract.py`、`tests/agent/subagent/test_terminal_honesty.py`，
  以及全部 change 文档 / delta spec / grill 记录
- 实跑命令（两轮均在 worktree 根目录、`export PATH=/home/happy/.local/bin:$PATH` 下执行；临时脚本全在
  `/tmp`，未进仓库）：
  - `uv run python` + `PYTHONPATH` 注入的**声明期判定 vs 真实 `run()`** 逐图对照（12 张手写图 +
    随机图 fuzz 数千张）；两轮各写独立脚本，互不复用
  - `git archive b0a6604` → `/tmp/base_src`（基线）与 `git archive dba8809` → `/tmp/prev`
    （首轮修复前），在**这两份代码上分别实跑同一批图**，区分「本来也跑不起来」与「本 change 误伤」
  - `PYTHONPATH=. uv run pytest tests/agent/subagent tests/agent/tools -q` / `uv run pytest -q`
  - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
  - `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
  - `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/...`
  - 变异验证：逐条改坏实现，看新增用例是否变红
  - 两轮全程未修改仓库任何文件（`git status` 干净）

## Verdict

**PASS**

首轮 7 条（blocker 1 / major 2 / minor 2 / low 2）中，**6 条已修好并经第 2 轮逐条实跑复核**
（两条误报在修复前提交 `dba8809` 上可复现、在 HEAD 上消失，其中 best_effort 一条在**基线 `b0a6604`**
上确能声明且真循环）；第 7 条（backlog 同步）是收尾动作，已在本轮一并处理。第 2 轮新发现 3 条，均为
minor/low，无 blocker、无未解决 major。

**判据安全性证据**（本 change 最关键的风险面：误伤合法图）：

- 第 2 轮 fuzz：**约 700 张随机被拒图**逐个实跑，被点名节点**零误报**。
- 本 session 另跑 fuzz（三个种子，含 best_effort/route 无声明边等对抗性形态）：**155 张被拒图**逐个实跑，
  **零误报**。
- 官方 4 pattern（orchestrator-worker / peer-review / hierarchical / bidding）**全部仍能声明通过**（测试锁定）。
- 变异验证：**10 条变异全部被杀死**（其中第 2 轮独立复现 6 条）。

## Round 1 Issue Re-check（第 2 轮独立复核）

| # | 首轮结论 | 复核 | 证据 |
|---|---|---|---|
| 1 | **blocker**：不动点漏 `_ready_nodes` 的 `deadline_fired` 短路，误拒环内 `best_effort` 聚合 | **已修好** | 修复前 `dba8809` 对该图抛 `WorkflowCycleError`；HEAD **接受**且实跑与基线一致（`graph_recursion_exceeded`、`body=completed`、`gate` 派发 3 次）。**基线对照**：`b0a6604` 上该图 accepted——证明是「本来能跑、首版误伤」 |
| 2 | **major**：`_route_activators` 漏 `cases[].to`/`default` 目标 | **已修好** | `dba8809` 对「route 目标无声明边」图抛错；HEAD **接受**。`_route_activators` 把 `cases[].to` / `default` / 声明出边一并计入 |
| 3 | **major**：报错把 route **控制边**说成 required 数据等待（照做无效） | **已修好，且逐条照做验证** | waiting 段显式 `if edge.source in control_sources: continue`。实测「谁在等谁」**不再出现**首轮那句假话；「怎么改」三选一逐条实跑，**每条建议照做后图都真的能过** |
| 4 | **minor**：报错无界增长、截断不注明剩余条数 | **已修好** | 新增 `_bounded` + `_ERROR_LIST_LIMIT = 8`。实测 58 节点环报错 **1299** 字符、199 节点环 **1331** 字符（首轮 8117），三段列表均带 `(+N more)` |
| 5 | **minor**：`tasks.md` 复选框与实现不符 → 门禁静默 | **已修好** | 现 45 `[x]` / 5 `[ ]`；门禁已**咬合**（会走到 review-manifest 检查并报错） |
| 6 | **low**：测试覆盖缺口 + 2 条弱断言 | **已修好** | 6 条新用例齐备；2 条弱断言加严为具体节点串，删段落必然变红 |
| 7 | **low**：`docs/openspec-change-backlog.md` 仍写被 grill 推翻的旧判据 | **本轮处理** | 随归档移除整条条目（受保护路径，带 `workflow-events.jsonl` 结构化事件） |

## Round 2 Issues（新发现）

### 1. **minor** — 判据在一个可静态消除的方向上过近似（漏报面窄且已记录）

判据方向**正确**（过近似 = 超集 = 只漏报不误报），两轮 fuzz 均未找到误报。但 `_route_activators`
的两条分支可**静态证明永远不会发生**，因而放行少量真的会停滞的环：

- **(a)** route **无任何数据入边**时，`cases[].to` 永远不可能被选中——`_route_verdict` 的判定文本
  只由 `data_incoming` 上游产出拼接，无数据入边则 `raw=""`，`matches_route` 的
  `if not verdict or not label: return False` 直接返回 False，`state.targets` 恒为 `default`；
- **(b)** route 的声明出边若既不是该 route 的 `case.to` 也不是 `default`，该出边永不被选中——
  `_execute_route` 只把 `cases`/`default` 写进 `state.targets`。

两条子机制第 2 轮均做了最小复现实跑：图级 `completed`，而环内节点 `blocked`（节点因由已由
`workflow-terminal-honesty` 如实说「入边互相等待」）。

**为什么 PASS 仍然成立**：漏报面**窄且集中在退化形状**——第 2 轮用贴近真实写法的生成器
（环体有数据回边、route 有 `body` 作数据输入）扫 36 张放行图，**0 张死环**；真正会重新造成 #219
的常见形态（模型把回边写反、忘写 entry）仍被拦住。而放行只出现在「route 没有数据入边」这类本身
**没有判定意义**的图上。**本 change 明确选择「只漏报不误报」的方向**（design D1），此为该选择的
已知代价，已记录于 design.md 的 D1 与 Risks。

### 2. **minor** — review manifest 只按哈希绑定报告、不读正文 verdict，存在「CHANGES_REQUESTED 报告 + PASS manifest」的认证漏洞

- **证据**：`agent/workflow/review_manifest.py` 的 `build_review_manifest` 有默认参数
  `verdict="PASS"`，只记录调用方传入的值，**从不解析报告正文**；`report_hash` 绑定
  `review_report_path(...)` = `reviews/building-review.md`。`verify_review_manifest` 只校验
  schema / change_id / phase / `verdict == "PASS"` / 字段非空 / 报告哈希匹配，**不检查正文是否写了 PASS**。
  而 `check_openspec_artifacts.py` 的 `review_dir.glob("*-review.md")` 只匹配 `building-review.md`。
  于是「正文写着 CHANGES_REQUESTED 的报告 + PASS manifest」能通过门禁——与 AGENTS.md
  「禁止只靠手写 PASS 文本通过 gate」的意图相反。
- **本轮处理**：**已消除**。闭环收敛后把权威报告 `building-review.md` 重写为**最终 PASS 结论**
  （即本文件，覆盖两轮），再生成 manifest，使被绑定的报告正文与 manifest 的 verdict 一致。
- **建议（后续 change / 另立 issue）**：让 `build_review_manifest` 在写入前校验报告正文含
  `PASS`（或在 `verify_review_manifest` 里加同款检查），从机制上堵住这条缝。属 #90 门禁自身的加固，
  超出本 change 范围。

### 3. **low** — `docs/openspec-change-backlog.md` 仍是旧判据

与首轮 Issue 7 同条，随归档移除处理（见上表第 7 行）。

## Task Verification

逐条对 `tasks.md` 与代码/测试找证据（两轮独立核验，结论一致）。

| 任务 | 结论 | 证据 |
|---|---|---|
| 1.1 #219 形态被声明期拒绝 | **做了** | `parse_workflow_spec(_spin_spec())` → `WorkflowCycleError`；对照真实 `run()`（绕过后）`status=stalled`、环内节点 `blocked` |
| 1.2 环内有 subagent 但互等 → 拒绝 | **做了** | 实跑 `_inner_lock_spec()` → 拒绝并点名 `b`/`c`（覆盖「有产出节点」判据会漏的形态） |
| 1.3 环内有能自启动 entry → 通过 | **做了** | `_startable_loop_spec()` accepted；实跑该图 `producer` 跑 9 次（环真转起来） |
| 1.4 环内 `aggregate(strategy="llm")` → 通过 | **做了** | 用例通过；实跑 `inner` completed |
| 1.5 环内 `foreach` → 通过 | **做了** | 用例通过 |
| 1.6 回边从 route 出发 → 通过 | **做了** | `is_control_edge(gate->producer)` 为真 |
| 1.7 回边 `required:false` 且环能启动 → 通过 | **做了** | `_open_back_edge_spec()` accepted |
| 1.8 环外 required 数据边喂进环、环内无 entry → 拒绝 | **做了** | 用例通过；实跑 `body`/`gate` 双双 `blocked` |
| 1.9 官方 4 pattern 仍能声明 | **做了** | `parametrize` 4 例全绿；两轮均另用 `compile_pattern` 逐个实跑声明，**4/4 accepted** |
| 1.10 改造 `test_terminal_honesty.py` | **做了，且无生产旁路** | `_spec_without_cycle_check` 用既有 `_parse_node`/`_parse_edge` 直接组装 dataclass；全仓 `WorkflowSpec(` 构造点仅 `workflow.py`（正门）与 `aggregation.py`（plan 展开期重建），**未新增公开旁路**；改后断言强度未弱化 |
| 2.1 新增 `_validate_cycle_can_start` | **做了** | 由 `parse_workflow_spec` 调用；不动点实体 `_dispatchable_nodes` |
| 2.2 新增 `WorkflowCycleError` | **做了** | 工具层 `_invalid_spec` 用它分流指向性 hint |
| 2.3 复用既有 `_strongly_connected_components`，不改它 | **做了** | `git diff b0a6604..HEAD` 未触及 Tarjan 本体 |
| 2.4 只对环分量判定 | **做了** | `_cycle_members`（大小 > 1 或自环）；校验只遍历环分量 |
| 2.5 执行顺序 | **做了** | 在 entry/terminal 解析**之后**（判据要用最终 entry 集）；实测「无 route 的环」仍由 `_validate_cycles` 先报，优先级未改写 |
| 3.1 报错含三要素 | **做了** | 「哪个环 / 谁在等谁 / 怎么改」三段齐备 |
| 3.2 同环 required 数据边点名 + 建议 | **做了** | 报错含 `declare "required": false on the back-edge(s) ...`，**照做后 accepted** |
| 3.3 `_invalid_spec` 指向性 hint | **做了** | hint 含 `workflow_id` 事实与「按 how-to-fix 改后重声明」 |
| 3.4 断言三要素 + 模型视角核对 | **做了** | 独立做了模型视角核对：逐句三问 + 逐条建议照做验证 |
| 4.1–4.4 提示面 | **做了，且正反例都可实跑** | 按描述逐字重建两段骨架实跑：正例 accepted 且真循环；反例 rejected，且描述里写的修法照做后 accepted |
| 5.1 运行期诊断不做 | **符合说明** | 已 `[x]` 并写明理由 |
| 6.1 官方 4 pattern 回归红线 | **做了** | 同 1.9 |
| 6.2 变异验证 | **做了（两轮共 10 条全部 KILLED）** | 删 `deadline_fired` 分支 / 删 `cases`+`default` 激活来源 / 恢复控制边苛责 / 去掉 `_bounded` 截断 / 删 `required` 判断 / 删「是 entry」分支 / 判据退化成「环内有无 subagent」 / 去掉 how-to-fix 段落 / 去掉 directional hint / 去掉 route 激活建模 |
| 6.3 全量 pytest | **做了** | `tests/agent/subagent tests/agent/tools` → **911 passed**；全量 → 见 Notes（失败与本 change 无关） |
| 6.3b benchmark smoke | **做了** | `--agent fake`：72 tasks / 5 passed / 38 unsupported / 29 failed，**与 master 逐字段一致**（含 5 个 passed 的 task id 完全相同） |
| 6.4 同步 current spec | 收尾 | —— |
| 6.5 `/review-loop` | **本条即该任务** | 两轮，3 轮封顶内收敛 |
| 6.6 归档 + backlog 移除 | 收尾 | —— |
| 6.7 validate + artifact checker | **做了** | `validate --all --strict` → 30 passed / 0 failed；artifact checker 在 manifest 生成后通过 |
| 6.8 建 PR | 收尾 | —— |
| 6.9 文档影响检查 | **做了** | backlog 条目随归档移除；`docs/architecture.md` 相关段落只讲运行期回边语义，未受本 change 影响，无需改 |
| 7.1–7.9 首轮修复 | **全部完成** | 见上表 Round 1 Issue Re-check |

## Notes

非阻塞观察项：

- **全量 pytest 的失败与本 change 无关**：两轮各自观察到的失败均为 `tests/web_tests/` 的**浏览器竞态**
  （单独跑/整目录跑全绿；本 change 的 diff 里 web 改动为 0），另加任务书已点名的两条环境性失败
  （`test_tree_sitter_extracts_java_and_kotlin_symbols`、`TestE2eEngineCliSmoke::test_engine_cli_validate_exit_code`，
  master 上同样红）。判据以此为准：它们不涉及 workflow DSL / 调度器 / 工具描述。
- **报错「怎么改」条目二的措辞可再前置一步**：`give the cycle a node that starts on its own: make {seed!r}
  (or another member) an entry whose required inputs come from outside the cycle; if a route also points at
  it, list it in spec.entry`——第 2 轮实测其**字面读法**（只把节点从环外喂入、不加 entry）仍会被拒，
  必须连带照做后半句。三条建议里有两条照做即过，文案已足够让模型改对，故列为观察项。
- **`_bounded` 的 docstring 措辞与实现略有出入**（说「传字符串会被逐字符拆开」，实际首行已把字符串
  包成单项）。纯措辞，不影响行为。
- **`_entry_set` 并入隐式入口是冗余而非偏差**（两轮一致结论）：这类节点没有控制入边，不动点里
  「没有控制入边」的分支本就覆盖它，方向仍是超集。
- **性能可接受**：第 2 轮实测 200 节点 DAG 约 5.6 ms、200 节点大环约 2.8 ms、199 节点最坏环约 14.9 ms；
  默认 `max_nodes=200` 下声明期开销在 10^0–10^1 ms 量级。
- **校验落点在文档里可用行号口径表达**：落点是「全量既有校验**与** entry/terminal 解析之后」，
  理由是该位置能拿到含隐式推导的最终 entry 集。
