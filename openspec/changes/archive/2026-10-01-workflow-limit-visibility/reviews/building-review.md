# Building Review — workflow-limit-visibility（Round 2）

- **Change**: `workflow-limit-visibility`（issue #275，`multi-agent-collaboration`）
- **Branch**: `workflow-limit-visibility/2026-10-01`
- **Round**: 2（复核 Round 1 的 CHANGES_REQUESTED 修复）
- **审阅基线**: `5e5d66c`（fix 提交，HEAD）
- **审阅者**: 独立零记忆 subagent，不继承开发上下文
- **方法**: 读 `git show 5e5d66c` 全 diff + 当前实现；**独立复现**（自写探针，非复跑既有脚本）Issue 1 场景；对 Issue 2 的哨兵锁**做一次真实变异**验证其为真锁后还原；跑全量门禁。

## Verdict

**PASS**

Round 1 的两个需修复项（Issue 1 MEDIUM 口径自洽、Issue 2 LOW 哨兵锁）均已真正消除：Issue 1 的矛盾在**模型可见输出**（`notes`）与 spec delta 两条路径上都被点破并加了限定，且有回归测试锁住；Issue 2 的哨兵锁经独立变异验证为**真锁**。无新引入问题。Issue 3（LOW，证据核对）按约定转收尾阶段，非阻塞。

## Round 2 复核

### Issue 1（MEDIUM，口径自洽）— **已消除**

**Round 1 问题**：自动插层撞闸路径上 `expanded_nodes ≠ graph_nodes + Σitems`（差额 = 被拒未落地的自动层），而 `notes` 与 spec delta 一条 Scenario 有无条件等式陈述 → 新的模型误读面。

**复核证据**：

1. **`notes` 已点明基线差异**（`agent/tools/builtin/subagents.py:1811-1819`）。新增段原文：

   > Reading `node_budget` on a TRIPPED graph: `graph_nodes` and `auto_inserted` describe the plan that actually LANDED, while `expanded_nodes` is the projection of a fully-expanded graph. When the gate rejects the graph at the auto-merge step those merge layers never land, so `expanded_nodes` can exceed `graph_nodes + sum(foreach items)` by exactly those rejected layers (e.g. 2 declared + 20 items that wanted 2 merge layers reports graph_nodes=2, auto_inserted=0, expanded_nodes=24). Trust `headroom` (the margin) over reconstructing it from `graph_nodes`; `expanded_nodes` is the authoritative billing size.

   三点要求全部命中：「`graph_nodes`/`auto_inserted` = 已落地」「`expanded_nodes` = 投影」「以 `headroom` 为准」。示例数字（`graph_nodes=2, auto_inserted=0, expanded_nodes=24`）与实测逐字相符（见下）。

2. **spec delta 已加限定 + 新 Scenario**（`specs/multi-agent-collaboration/spec.md`）：
   - Requirement 正文（`:35`）现在明写「`graph_nodes` 与 `auto_inserted` 反映**已落地**的计划，`expanded_nodes` 反映**展开完成后**的投影，两者基线不同——当闸门在自动插层处拒绝（该层从未落地）时 `expanded_nodes` 可大于 `graph_nodes + Σ foreach 展开项`」，并加「报告 SHALL 让调用方以 `headroom` 为准判断余量，SHALL NOT 要求其用 `graph_nodes` 反推 `expanded_nodes`」。
   - 新增一条独立 Requirement 子句（`:36`）：**SHALL NOT 出现「`expanded_nodes` 恒等于 `graph_nodes + Σ foreach 展开项`」这类无条件等式陈述**，若给出须附成立条件——这是把 Round 1 的误读面本身写成了反模式禁令。
   - 原「计费放大」Scenario 的等式（`:122`）已从无条件改为附条件：「（此时自动层已落地）」。`graph_nodes` 在字段清单里也补了「**已落地**」限定（`:35`）。
   - 新增 Scenario「自动插层即撞闸时基线不同仍如实」（`:126-133`），GIVEN/THEN 逐条覆盖 `graph_nodes`/`auto_inserted`=已落地、`expanded_nodes`=投影、不再要求等式、`headroom` 为负。

3. **独立复现**（自写 `/tmp/repro_issue1.py` + `/tmp/repro_edge.py`，非复跑 `research/node_budget_probe.py`）：`max_nodes=3` + 20 项 →

   ```
   run_status = graph_recursion_exceeded
   graph_nodes = 2, auto_inserted = 0, expanded_nodes = 24, limit = 3, headroom = -21
   ```

   与 fix 提交与 `notes` 示例**逐字一致**。跨 `max_nodes ∈ {2,3,4,5,23,24}` 的扫描进一步确认 `notes` 措辞精确：

   | max_nodes | 撞闸点 | graph | auto | expanded | headroom | expanded−(graph+20) |
   |---|---|---|---|---|---|---|
   | 2 / 3 | `_expand_plan`（自动层被拒） | 2 | 0 | 24 | −22 / −21 | **2**（=被拒层） |
   | 4 / 5 / 23 | `_check_foreach_budget`（自动层已落地） | 4 | 2 | 24 | −20/−19/−1 | 0 |
   | 24 | 不撞 | 4 | 2 | 24 | 0 | 0 |

   `notes` 用的「**can** exceed … **when** the gate rejects the graph at the auto-merge step … by exactly those rejected layers」限定词与作用域**完全正确**：差额 2 只在自动层被拒（`2/3`）时出现且恰等于被拒层数，在自动层已落地（`4/5/23`）时等式成立。**无过度声明。**

**结论**：Round 1 的「模型可见输出自相矛盾」已消除——`notes` 与 spec delta 现在都给出基线限定 + 具体反例，「以 `headroom` 为准」的指引消解了「哪个数权威」的歧义。回归测试 `test_node_budget_baseline_differs_when_auto_layer_is_rejected`（`test_workflow_limit_visibility.py:251-274`）锁住落地/投影两分支（含 `expanded != graph_nodes + 20` 的反等式断言 + 落地对照）。`notes` 层亦加宽松断言（`assert "landed" in text or "reject" in text`，`:328`）。

### Issue 2（LOW，测试锁强度）— **已补齐，且为真锁**

**复核证据**：新哨兵锁 `test_gate_count_reads_the_scheduler_route_counter`（`test_workflow_limit_visibility.py:386-403`）monkeypatch `WorkflowScheduler._execute_route`，在 route 执行后把 `self._route_counts` 替换为哨兵 `{node.id: 424242}`，断言 `report.nodes[gate].gate_count == 424242`——报告若在报告层以另一口径重算会得到真实值 `1`，读取闸门字段才会得到哨兵。

**独立变异验证**（本轮实测）：把 `agent/tools/builtin/subagents.py:1586` 的
`entry["gate_count"] = scheduler._route_counts.get(node.id, 0)` 改为 `entry["gate_count"] = 999999`（伪造值），跑测试：

```
FAILED ...::test_gate_count_reads_the_scheduler_route_counter
E   assert 999999 == 424242
2 failed, 25 passed
```

哨兵锁**变红**（同时值断言 `test_route_entry_exposes_max_routes_and_gate_count` 也变红）。已还原（`git status` 干净）。**是真锁**——满足 D6「调用级同源锁（非值相等）」纪律，与同文件另三处哨兵锁（`limits`/`expanded_nodes`/`limit`）口径一致。

### Issue 3（LOW，证据核对）— 转收尾，**非阻塞**

`tasks.md:6.3` 未勾，标注「收尾阶段在 PR 描述附 benchmark smoke 原始命令与对比摘要」——与 Round 1 约定一致。`tasks.md:4.4` 已记 smoke 结论（`Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29`，与 pristine baseline 逐项相同）。本 change 未触及 benchmark 路径，风险低；原始输出随 PR 描述补上即可。**不构成本轮 verdict 依据。**

## Tasks Verification

对照 `tasks.md`（基线 `5e5d66c`）。实现期任务（1.x–3.x、6.1–6.2）全部落到位；未勾项均为**未到位阶段**，符合阶段纪律。

| # | 任务 | 证据 | 状态 |
|---|---|---|---|
| 1.1 | issue #275 / `proposal.md` | `proposal.md` 存在，含 Change Type/Why/RIR/Impact | ✓ |
| 1.2 | `design.md` | `design.md` 存在（D1–D6、Risks、Testing Strategy） | ✓ |
| 1.3 | spec delta | `specs/multi-agent-collaboration/spec.md` MODIFIED 2 条 + 新 Scenario | ✓ |
| 1.4 | 侦察脚本 | `research/{gap,gate_trip,node_budget}_probe.py` | ✓ |
| 1.5 | RIR findings | `proposal.md` `## Reference Implementation Research`（`research_tier: full`） | ✓ |
| 2.1 | grill 独立 subagent | `reviews/grill-design.md` | ✓ |
| 2.2 | 停轮 Open Questions | `grill-design.md` `## Open Questions` + 具体例子 | ✓ |
| 2.3 | 用户答复回写 | `grill-design.md` `## User Confirmation`（Q1–Q6，含时间） | ✓ |
| 2.4 | 订正回写 | design/proposal/spec delta 已按 Q1 口径订正（D2 计费口径等） | ✓ |
| 3.1 | 失败测试先行 | `tests/agent/subagent/test_workflow_limit_visibility.py`（27 用例） | ✓ |
| 3.2 | 报告 `limits` | `subagents.py:1661`（复用 `_limits_report()`） | ✓ |
| 3.3 | 闸门投影记录 | `scheduler.py:2124-2127`、`2184-2186`（`_projected_expanded_nodes`，只增不改判定） | ✓ |
| 3.4 | 报告 `node_budget` | `subagents.py:1668-1675` | ✓ |
| 3.5 | route `max_routes`+`gate_count` | `subagents.py:1585-1586`（同源 `_route_counts`） | ✓ |
| 3.6 | `diagnostics` 无条件挂载 | `subagents.py:1683` + `test_diagnostics_is_mounted_unconditionally_even_when_empty` | ✓ |
| 3.7 | `notes` 口径说明 | `subagents.py:1803-1827`（含 Round 2 新增段） | ✓ |
| 3.8 | `DeclareWorkflow` 描述三闸默认值 | 描述层（`test_workflow_tool_discoverability.py` 锁） | ✓ |
| 3.9 | 描述可发现性测试 | `tests/agent/subagent/test_workflow_tool_discoverability.py` | ✓ |
| 3.10 | 调用级同源锁 | 四处哨兵锁（`limits`/`expanded`/`limit`/`gate_count`），本轮变异验证 gate_count 为真锁 | ✓ |
| 3.11 | scheduler 侧投影/判定不变 | `test_workflow_limit_visibility.py:373,393` | ✓ |
| 3.12 | 既有 dry run 测试不失效 | `tests/agent/subagent/test_workflow_dry_run.py`（并入 subagent 套 824 passed） | ✓ |
| 4.1 | `/review-loop` 至 PASS | 本报告（Round 2 = PASS） | ✓（本轮） |
| 4.2 | 全量 pytest | 实跑 3857 passed / 2 pre-existing fail（见下） | ✓ |
| 4.3 | 真实 LLM 验收 N=3 | 未到位阶段（收尾，主 session 跑） | — 未到位 |
| 4.4 | benchmark smoke | `tasks.md:4.4` 自述与 pristine 逐项相同（原始输出转 6.3） | ⚠（见 Issue 3） |
| 5.1–5.4 | 同步 spec / 归档 / backlog / validate | 收尾阶段（未到位） | — 未到位 |
| 5.5 | artifact checker | 见下「门禁」——因 manifest 未写而红，属预期 | — 未到位 |
| 5.6–5.7 | 文档影响 / PR | 收尾阶段（未到位） | — 未到位 |
| 5.8 | (post-merge) 关 issue | 已带 `(post-merge)` 标记，归档门豁免 | ✓（标记正确） |
| 6.1 | Issue 1 修复 | notes + spec delta + 回归测试 | ✓ |
| 6.2 | Issue 2 修复 | 哨兵锁 + 变异验证 | ✓ |
| 6.3 | Issue 3 收尾 | 未勾，标注收尾阶段处理 | — 未到位 |

## Issues

**无中等以上问题。** Round 1 的两项修复均验证通过；未发现新引入问题。

两条**非阻塞**观察（不影响 verdict，供收尾参考）：

1. **`notes` 第一段仍是无条件表述，靠紧随的第二段消歧**。`subagents.py:1803-1810` 首段仍写 `expanded_nodes = the billing size the gate actually counts (graph nodes PLUS each foreach item)`，「graph nodes」未带「已落地/投影」限定；消歧完全依赖紧跟其后的新增段（`1811-1819`）。当前读法上第二段明确「二者基线不同 + 以 headroom 为准 + 具体反例」，误读面已闭合；若收尾想更保守，可把首段的「graph nodes」改为「fully-expanded graph nodes」。**非必须**。
2. **哨兵锁与值断言同文件并存**（`gate_count` 现既有值断言又有哨兵锁），属强度冗余、方向正确，无需处理。

## Test Results

实跑（本 worktree，HEAD `5e5d66c`）：

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/subagent/test_workflow_limit_visibility.py -q` | **27 passed** |
| `uv run pytest tests/agent/subagent/ -q` | **824 passed** |
| `uv run pytest -q`（全量） | **3857 passed, 2 failed, 9 skipped** |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **29 passed, 0 failed**（含 `change/workflow-limit-visibility`） |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | exit 1：`review manifest missing`（预期，见下） |
| 变异验证（Issue 2 哨兵锁） | 改 `gate_count` 为伪造值 → **2 failed**（哨兵锁 + 值断言），已还原 |

**全量 2 条失败** = `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir` 与 `::test_malformed_git_file_falls_back_to_scan`——本机 `/tmp/.git` 导致的**既有环境噪声**（任务已声明为 pre-existing），与本 change 无关。

**artifact checker 的红**：仅 `review manifest missing` 一条。该门在 `tasks` 全勾且 change 有代码改动时触发，本 change 正处此态；manifest 由 `/review-loop` 在 **PASS 之后**生成（fix 提交自述「artifact checker 待 Round 2 PASS 后写 manifest」）。故此为 Round 2 PASS 之前的结构性预期状态，**非缺陷**；本报告给出 PASS 后即可写 manifest 消红。

## 结论

- **Verdict = PASS。**
- **Issue 1（MEDIUM）已消除**：`notes` 补段点明「`graph_nodes`/`auto_inserted` = 已落地、`expanded_nodes` = 投影、以 `headroom` 为准」；spec delta 加基线限定 + 新增「自动插层即撞闸」Scenario + 一条反无条件等式的 Requirement 子句；独立复现数字逐字吻合，跨 `max_nodes` 扫描确认措辞无非过度声明；回归测试锁住两分支。
- **Issue 2（LOW）已成真锁**：哨兵锁经独立变异变红（`assert 999999 == 424242`）后还原，符合 D6 调用级同源锁纪律。
- **Issue 3（LOW）** 按约定转收尾（`tasks.md:6.3`），非阻塞。
- 八个审阅维度（任务逐项验证、正确性、Spec 对齐、冗余度、测试覆盖、安全性、可维护性、CI 完整性）均无中等以上问题；全量测试与 OpenSpec strict validate 绿；唯一门禁红（artifact checker manifest）为 PASS 前的预期状态。
- **变更可进入收尾（写 manifest → 同步 spec → 归档 → PR）。**

**工作区状态**：变异验证后已还原，`git status` **干净**。
