# Building Review: evaluation-protocol-reporting（C3）

Verdict: **PASS**

- Round: 2
- reviewer run: 本 review（独立零记忆 subagent，2026-08-18）
- base: `origin/master`（88ed98a），head: `5c89c28`（Round 1 修复提交）
- 审阅范围：`git diff origin/master...HEAD`（19 文件）+ `git diff b5313a0...HEAD`（Round 1 修复 6 文件）+ change 文档 + 正式 spec
- Round 1 verdict: CHANGES_REQUESTED（5 项修复），本轮逐一验证全部落实

## Round 1 Fixes Verification

| # | Round 1 问题 | 状态 | 证据 |
|---|---|---|---|
| 1 | 小样本声明 N 范围恒为 1（repeat>1 事实错误） | **已修复** | `benchmarks/disclosure.py:191-202`：改为按 task_id 累加有效轮数（`if is_valid_round(r.status, r.reason): by_task[r.task_id] += 1`），不再用 `valid_round_count([r])` 的 0/1 布尔。smoke（`--repeat 3 --seeds 0 1 2` fake）实测结果页「小样本声明」输出「有效轮次范围 N=3–3」。回归测试 `test_small_n_note_counts_valid_rounds_per_task`（4 结果含 1 无效轮 → 断言 N=3–3）。 |
| 2 | 过程效率表在 repeat>1 时每任务重复 N 行 | **已修复** | 新增 `disclosure.py:180-188 _unique_task_ids`（首见序去重），md 调用处（`:350`）与 HTML 调用处（`:430`）均传 `_unique_task_ids(ctx.results)`。smoke 实测 `## 过程效率` 每任务恰一行（t1、t2 各 1 行）。回归测试 `test_process_efficiency_rows_deduplicated_per_task`（body.count("| t1 |") == 1）。 |
| 3 | `--budget-cap` 在 repeat==1（缺省）时静默 no-op | **已修复** | `agent/main.py:793-801`：repeat==1 路径现执行 `effective_cap` 检查，超限置 `metadata.truncated=True` 并 `metadata.write_json(run_path/"run.json")`。回归测试 `test_budget_cap_overrun_single_run_marks_truncated`（`--budget-cap 1` + `_round_cost` 恒 999 → run.json `truncated: true`）。 |
| 4 | compare HTML 未转义 task_id | **已修复**（按指定范围） | `benchmarks/compare.py:70` `_build_paired_html` 的 delta 行 `html.escape(task_id)`。实测含 `<&` 的 task_id 渲染为 `t1&lt;&amp;script&gt;`，原始字符串不出现。残留观察：C3 新增的 Run Metadata HTML 段 cell 与既有主表 task_id cell 仍未转义（同一信任域，Round 1 判低、不阻塞），见 Issues。 |
| 5 | tasks 8.4/8.6 验证声明非实测口径 | **已修复** | `tasks.md` 8.4 改记「benchmark 套件含 C3 新增测试共 392 passed；全量 2172 passed，2 个环境相关失败」；8.6 澄清「`--model deepseek-v4-flash --model-version` 的 smoke 上 self_check 五门禁 PASS（裸 fake 不带 model/annotate 时 GATE 1/2/5 失败属预期严格行为）」。本 review 实测裸 fake smoke self_check 为 GATE 1/2/5 FAIL，与 8.6 描述一致。 |

回归测试核对：`tests/benchmark/test_c3_disclosures.py` 新增 2 项（small_n 计数、过程效率去重）、`tests/benchmark/test_c3_cli.py` 新增 1 项（单轮 truncated），合计 3 项（提示语「disclosures +3」为约数，实际 2 项，覆盖了 Round 1 两个中等问题的修复路径）。

## Tasks Verification

逐条对照 `tasks.md` 每个 `[x]` 任务，核对实现文件与真实代码（Round 1 已全量核验，本轮复核修复相关项 + 抽查其余）：

| Task | 实现证据 | 状态 |
|---|---|---|
| 1.1 proposal 完整性 | `proposal.md` 含 Change Type / Impact Analysis / RIR（research_tier=full + 本地参考仓库不可用事实）。 | ✅ |
| 1.2 batch-grill-me 审视 design | `reviews/grill-design.md` 存在，D1–D8 逐项追问 + 对照代码验证。 | ✅ |
| 1.3 grill 停轮 + User Confirmation | `grill-design.md` `## Open Questions` 18 条 + `## User Confirmation` 18 条实质答复（2026-08-17），Q1–Q18 均有确认时间。 | ✅ |
| 1.4 spec delta 一致 | delta 以 MODIFIED 承接渲染义务，向后兼容扩展；正式 spec 已同步。 | ✅ |
| 2.1 协议文档转正 | `docs/benchmark-run-protocol.md`（154 行）存在，中文，无 wayfinder 引用，落真实 `uv run asterwynd benchmark …` 命令面。 | ✅ |
| 2.2 协议内容 | 任务集 82–90、模型/采样（repeat 5 + seeds 0..4 + temp 0.2）、`--budget-cap`/`--budget-cap 0`/`--no-cap`、per-round cap 超限标 truncated、对照口径、artifact 布局、五门禁、reproduction、Verified 40 fixture 前置（#156）。 | ✅ |
| 3.1 报告元组渲染 | `disclosure.py::report_tuple_rows`（68–108 行，含 truncated 行）+ `runner.py::run_all` 填充 task_set_hash/adapter_version/prompt_version/pricing_table_version/network/max_iterations/timeout_seconds/provider（262–271 行）。smoke 实测元组字段齐全。 | ✅ |
| 3.2 污染注记 + 反作弊 | `disclosure.py` SWEBENCH_AUDIT_NOTE 常量表（注来源 R1 2026-08-17）+ `anti_cheat_rows` 读 manifest。 | ✅ |
| 3.3 fault_owner 交叉 + 成本 | `fault_owner_cross_rows` + `cost_metrics_rows`（复用 C2 `fault_owner_cross`/`cost_per_resolved`/`cache_hit_rate`）。 | ✅ |
| 3.4 partial/采样/小N/过程效率 | `partial_rows`/`sampling_rows`/`small_n_note`/`process_efficiency_rows` 均实现；本轮确认 small_n 按任务累计有效轮、过程效率按任务去重。 | ✅ |
| 3.5 能力覆盖矩阵 | `coverage_rows` 读 manifest capabilities/coverage，套件级展示。 | ✅ |
| 3.6 golden 片段测试 | `test_c3_disclosures.py` 全片段断言（不含时间戳/路径）。 | ✅ |
| 4.1 compare HTML 配对段 | `compare.py::_build_paired_html` 与 md `build_paired_report` 共享 `_paired_data`（Q1「不漂移」达成）；本轮确认 task_id HTML 转义。 | ✅ |
| 4.2 run 元数据 md/html | `_run_metadata_rows` + `build_summary`/`build_html` 的 `metas` 参数。 | ✅ |
| 4.3 配对渲染测试 + 回归 | `test_c3_compare.py` 9 项 + 既有 compare 测试全过。 | ✅ |
| 5.1 --budget-cap/--no-cap/负数 | `agent/main.py` 749–758 行（冲突/负数拒绝 + effective_cap），812–835 行 per-round 超限停止剩余轮次 + truncated 落盘；本轮确认 repeat==1 也检查 cap。 | ✅ |
| 5.2 --preflight | `runner.py::preflight`（139–157 行）退出码 0/1/2。 | ✅ |
| 5.3 CLI 测试 | `test_c3_cli.py` 覆盖超限 truncated（多轮 + 单轮）、取消上限、preflight 内存/Docker 分支、pass^k 剔除 truncated 轮。 | ✅ |
| 6.1 self_check 五门禁 | `scripts/self_check.py` gate1–5；gate3 无 κ artifact 降级为 fault_owner 覆盖率（Q9）。 | ✅ |
| 6.2 缺失报告 + exit 码 + --skip | `main()` 非零统一 exit 1，`--skip <n>` 可重复，全过 exit 0。 | ✅ |
| 6.3 门禁测试 | `test_c3_self_check.py` 各门禁缺失/全过/skip/集成（含 exit 0/1）。 | ✅ |
| 7.1 delta MODIFIED 注记 | delta `specs/benchmark/spec.md` MODIFIED 渲染边界注记→已实现。 | ✅ |
| 7.2 delta 同步正式 spec | `openspec/specs/benchmark/spec.md` 已含 4 个 ADDED Requirement（协议/预算/预检/self_check）+ MODIFIED 渲染条款；差异与 delta 一致。 | ✅ |
| 8.1 Impact Analysis 无残留 | proposal Impact Analysis 无 unknown/TBD/待确认。 | ✅ |
| 8.2 RIR 最终结论 | design RIR 记录不可用事实 + map 决策替代依据。 | ✅ |
| 8.3 backlog 更新 | `docs/openspec-change-backlog.md` C3 批次行 + 未实现队列状态均已更新（实现完成 2026-08-18）。 | ✅ |
| 8.4 测试声明实测口径 | 本轮实测 benchmark 套件 395 passed（含 3 项新回归）；tasks 已记 392（Round 1 修复后 395，写任务时为 392 快照）。 | ✅ |
| 8.5 validate + artifact checker | 本轮实测 `openspec validate --all --strict` 30 passed；artifact checker 现报 building-review-manifest 缺失（见 Test Results，审阅闭环收尾预期态）。 | ✅ |
| 8.6 benchmark smoke | 本轮实测 `--repeat 3 --seeds 0 1 2` fake smoke 结果页含全部披露段，small_n N=3–3、过程效率每任务一行；裸 fake self_check GATE 1/2/5 FAIL 与 tasks 8.6 描述一致（预期严格行为）。 | ✅ |

Task 9.x 未勾选（review-loop/归档/PR），符合「审阅闭环进行中」状态。

## Issues

**无未解决中等以上问题。**

低优先观察（不阻塞，可随收尾处理或记债务）：

1. `benchmarks/compare.py` C3 新增的 Run Metadata HTML 段 cell（`build_html` 内 `meta_html` 拼接，约 359–361 行）仍原样插入 run.json 字段；既有主表 task_id cell（约 299 行）同样未转义。同一信任域（本地工具、受控任务目录），与 Round 1 Issue 4 同档判低；本轮仅按指定范围修复了配对段 task_id。
2. HTML 转义修复未配专属回归测试（`test_c3_compare.py` 未断言 `&lt;`/`&amp;` 转义行为）；修复本身正确（已手动验证），建议补一条防回退。

## Test Results

- `uv run pytest tests/benchmark/ -q`：**395 passed**（14.5s）。Round 1 为 392，修复新增 3 项回归测试（disclosures +2、cli +1），全绿无回归。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：**30 passed**。
- `uv run python scripts/check_openspec_artifacts.py`：现报 `review manifest missing: reviews/building-review-manifest.json`——这是审阅闭环中途的**预期态**（`building-review.md` 已存在、manifest 未生成）。PASS 判定后由 `/review-loop` 生成 manifest 即解除；非代码缺陷。
- 端到端 smoke（`--repeat 3 --seeds 0 1 2` fake）：结果页含全部披露段标题；`## 小样本声明` = 「有效轮次范围 N=3–3」；`## 过程效率` 每任务一行；报告元组字段齐全（task_set_hash/adapter/prompt/pricing/network/temperature/seed）。
- 已知环境失败（tree-sitter Java 语法、flow/engine 系统 python 缺 agent 模块）与本次变更无关，不在 benchmark 套件内。

## 结论

Round 1 的 5 项修复全部落实并经代码阅读、回归测试、端到端 smoke 三重验证：小样本 N 按任务累计有效轮（repeat=3 报 N=3–3）、过程效率每任务去重一行、repeat==1 单轮超限标 truncated、compare 配对段 task_id HTML 转义、tasks 8.4/8.6 改实测口径。实现覆盖全部 1–8 阶段 `[x]` 任务，grill 18 条确认决策全部落实，spec delta 与正式 spec 同步一致，测试全绿。两个 Round 1 中等缺陷的修复均带回归测试锁定。残留仅为两项低优先观察（Run Metadata HTML cell 未转义、转义修复无专属回归测试），不构成阻塞。

**Verdict: PASS**——所有 `[x]` 有真实实现，Round 1 修复全部落实，无未解决中等以上问题，相关测试通过。审阅闭环收尾步骤（生成 review manifest、勾选 9.x、归档）按 `/review-loop` 与 OpenSpec 收尾流程继续。
