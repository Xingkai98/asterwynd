# Building Review: evaluation-verified-subset

## Reviewer

- run id: review-evaluation-verified-subset-2026-08-18
- 时间: 2026-08-18
- 独立零记忆声明：本 reviewer 未继承任何开发上下文；全部结论基于对 change 文档、代码与生成 fixture 的逐一实际核验（`benchmarks/swebench_subset.py`、`benchmarks/swebench_convert.py`、`benchmarks/disclosure.py`、三个新增/修改测试文件、38 条 swebench-* fixture 的 task.json/test.patch、manifest.json、workflow-events.jsonl、proposal/design/tasks/grill-design.md）。
- 网络受限说明：本机无法访问 huggingface/github，无法复跑 hf-mirror 真实生成与 L3 网络自检；相关结论以代码事实 + 落盘产物交叉核对为准。

## Verdict

**CHANGES_REQUESTED**

核心管线（build-subset 接线、convert 字段修复、validate 内建、manifest 摘要、disclosure 披露段）实现真实且测试全绿；但 **8/38（sympy 全系）fixture 的 test_command 由裸函数名（无 `.py::` 路径前缀）拼接，无法运行目标测试**——现代 pytest 对裸标识符收集 0 项（已实测），评测时要么静默假 PASS（跑 0 个测试）、要么恒失败，Verify 子集评估有效性受影响，须修复 + 加回归守卫后再合入。

## Tasks Verification

逐条核对 tasks.md 的 `[x]` 任务（5.x/6.x 为 `[ ]`，属 PR 前正常待办；其中 5.3/5.3b 已实际执行但未勾选，见 Issue 4）。

| Task | 状态 | 证据 |
|---|---|---|
| 1.1 proposal 三件套完整 | ✅ | proposal.md:5-48（Change Type/Impact Analysis/RIR research_tier=light + reason + `.dev/reference-repos.txt` 不存在记录） |
| 1.2 batch-grill-me 审视 D1–D5 | ✅ | reviews/grill-design.md 全文；D1–D5 逐项判断表（:37-43）+ 9 项核查（:46-57） |
| 1.3 停轮 + User Confirmation | ✅ | grill-design.md:117-126，OQ-V1~V6 逐条含用户答复与确认时间 2026-08-18 |
| 2.1 build-subset 子命令 | ✅ | swebench_subset.py:521-528（--output/--targets/--skip-gold-check/--resume/--known-bad-file） |
| 2.2 管线接线 | ✅ | swebench_subset.py:424-461（load_verified→_probe_dataset→build_subset(exclude_ids)→generate_tasks(dataset 复用, gitee 优先)） |
| 2.3 落盘后自动 validate，invalid exit 1 | ✅ | swebench_subset.py:463-467（`if problems: ... return 1`） |
| 3.1 hf-mirror 实际生成 28 新/38 总 | ✅（产物可证） | benchmarks/tasks/ 下 38 条 swebench-* fixture 实盘；design.md:21 与 proposal.md:24 回写实测结果；网络无法复跑 |
| 3.2 validate_fixtures_dir 全过 | ✅（复验） | 本人扫描 38 条 task.json：track/scenario/difficulty 归一化全部合法；manifest 与实盘一致（见 Test Results） |
| 3.3 L3 抽样自检 3 PASS/3 未自检 | ⚠️ 机制在、覆盖有缺口 | gold_check external 路径已实现（swebench_subset.py:205-238）；build-subset 默认抽样每 repo 1 条 + 记录（:470-495）。但 sympy/seaborn/pylint 3 repo 未自检（github 不可达，已记录），且 sympy 系 test_command 裸函数名问题使自检即使跑也不可靠（见 Issue 1） |
| 3.4 结果回写 change 文档 | ✅ | design.md:21、proposal.md:24、backlog 条目（docs/openspec-change-backlog.md） |
| 4.1 manifest verified 摘要登记 | ✅（复验） | benchmarks/tasks/manifest.json `verified` 段（count=38/by_repo/by_difficulty），与 38 条实盘逐项核对一致 |
| 4.2 临时文件清理 | ✅ | 扫描 benchmarks/tasks 无 `.gold-check*` 残留；git status clean；无未跟踪文件泄漏 |

## Issues

### Issue 1（major）：sympy 8/38 fixture 的 test_command 为裸函数名，无法运行目标测试

- **证据**：`benchmarks/swebench_convert.py:123-124`——`build_test_command` 把 FAIL_TO_PASS 原值 `" ".join(tests)` 直接拼进 shell 命令，无路径剥离/校验。受影响 fixture 的 task.json `test_command` 全部形如：
  - `benchmarks/tasks/swebench-sympy__sympy-11618/task.json:6` → `python -m pytest test_issue_11617 --tb=short -p no:warnings`
  - `benchmarks/tasks/swebench-sympy__sympy-12096/task.json:6` → `python -m pytest test_issue_12092 ...`
  - `benchmarks/tasks/swebench-sympy__sympy-12419/task.json:6` → `python -m pytest test_Identity ...`
  - `benchmarks/tasks/swebench-sympy__sympy-12481/task.json:6` → `python -m pytest test_args ...`
  - `benchmarks/tasks/swebench-sympy__sympy-12489/task.json:6` → `python -m pytest test_Permutation_subclassing ...`
  - `benchmarks/tasks/swebench-sympy__sympy-13031/task.json:6` → `python -m pytest test_sparse_matrix ...`
  - `benchmarks/tasks/swebench-sympy__sympy-13091/task.json:6` → `python -m pytest test_equality test_comparisons_with_unknown_type ...`
  - `benchmarks/tasks/swebench-sympy__sympy-13372/task.json:6` → `python -m pytest test_evalf_bugs ...`
- **扫描方法**：对全部 38 条 test_command 逐条解析 pytest 参数，凡无 `.`/`::`/`/` 路径特征的裸标识符即命中；命中恰为 sympy 全 8 条，其余 30 条（requests/flask/pytest/seaborn/pylint）均为完整 node id 或 `-k` 形式，未命中。
- **实证**：本机（现代 pytest 8.x，uv 环境）`python -m pytest test_issue_11617` 对含该测试函数的仓库输出 `collected 0 items`——目标测试根本不被收集。裸标识符不指向任何文件/目录，pytest 不会从仓库中按函数名反查文件。
- **后果**：评测时该 test_command 要么 rc=0 但跑了 0 个测试（**静默假 PASS**，把未验证的 agent 补丁判为 resolved），要么收集错误 rc≠0（fixture 恒失败）——两种情况下 8 条 sympy fixture 都无法有效评定 agent 对 bug 的修复。L3 gold_check 对这些 fixture 同样不可靠。
- **根因链**：数据集 FAIL_TO_PASS 存的是裸函数名（build_test_command 无剥离逻辑，故命令直接反映原值）→ 生成时未拦截 → sympy 未自检（github 不可达，已确认设计）→ 缺陷未被捕获。同时 spec「金补丁自检剔除坏实例」Scenario 3 的覆盖在此 repo 缺口被放大。
- **修复建议**（供 Round 2）：a) `build_test_command`/`generate_tasks` 增加校验——test_command 参数必须含文件路径（`.py` 或 `::`），裸函数名直接报错或按 test.patch 的文件头解析出路径后重建 node id；b) 对受影响 sympy fixture 重生成或剔除；c) 新增回归测试锁定「test_command 不含裸函数名」（用 test.patch 的 `diff --git a/<path>` 交叉校验）。
- **待 Round 2 实测确认**：pytest 精确退出码（0=假 PASS 场景 / 5=无测试收集 / 2=collect 错误）在隔离环境确认；sympy 8 条 FAIL_TO_PASS 数据集原值在可联网环境确认。受影响 fixture 精确清单 = sympy-11618/12096/12419/12481/12489/13031/13091/13372（8 条），以本次扫描为准，如 Round 2 复扫有出入以实测为准。

### Issue 2（minor）：`--resume` 为死代码，实际行为由无条件 exclude 替代

- **证据**：`benchmarks/swebench_subset.py:437-443`——`cmd_build_subset` 无条件 `collect_existing_instance_ids(args.output)` 并作为 `exclude_ids` 传入 `build_subset`；随后 `:451-458` 的 `--resume` 分支再次按输出目录存在的 instance_id 过滤 `iids`，此时 `skip` 恒空（build_subset 已排除所有既有 ID）。
- **后果**：`--resume` 无任何实际效果；OQ-V3② 的「续跑跳过已存在」语义实际由排除逻辑承担。测试 `test_build_subset_cli_resume_skips_existing`（tests/benchmark/test_swebench_subset.py:233-285）实际通过的是排除路径而非 resume 分支（assert 结果成立但覆盖的是同一机制）。重跑时会换选其它候选实例（可能超目标数），非「续跑补齐到原计划集合」。不破坏主功能，但语义误导，建议 Round 2 明确 `--resume` 语义或删除该分支并修测试注释。

### Issue 3（minor）：.gitignore 缺 `.gold-check*` 规则

- **证据**：`.gitignore:4` 仅 `.venv/`；`swebench_subset.py:214,259` gold_check 会在 fixture 目录内创建 `.gold-check`/`.gold-check-venv`。
- **现状**：当前已清理（任务 4.2 ✅，git status clean），但未来 build-subset 或 gold-check 运行后残留有被误提交风险。建议补忽略规则。

### Issue 4（minor，流程口径）：tasks.md 5.3/5.3b 已实际执行但未勾选

- **证据**：收尾 commit 5d00ebf 已做 backlog 登记与 spec sync（workflow-events.jsonl seq 2/3 记录了 `docs/openspec-change-backlog.md` 与 `openspec/specs/benchmark/spec.md` 的结构化解释事件）；但 tasks.md:31-32 仍为 `[ ]`。
- **后果**：`[ ]` 状态使 artifact checker 不进入 building-review 强制门禁——当前属合理（PR 前），但「已做未勾」在收尾时会造成口径混乱，建议 Round 2 同步勾选。5.x/6.x 其余未勾属 PR 前正常待办（测试全量、archive、PR）。

### Issue 5（minor，既有债务，非本 change 引入）：REPO_TEST_COMMAND_TEMPLATES 死代码未被触碰

- **证据**：`benchmarks/swebench_convert.py:44-50` 定义，全仓无消费方（grep 确认仅声明处）；本次 diff 未改动。冗余度维度：本 change 未与既有工具重复实现、未触碰死代码，符合「不扩大债务」；可后续单独清理。

### Issue 6（info，安全维度结论）

- shell 注入面：`swebench_subset.py:194-202,229-237` 用 `shell=True` 执行 `task.test_command`，其参数来自数据集 FAIL_TO_PASS——SWE-bench 为可信研究数据集（非对抗输入），且该拼接逻辑为既有 `build_test_command`（本次未改），风险低；无凭证/敏感信息；git clone/apply/checkout 均为 list 形式无 shell；`task_dir = output_base / f"swebench-{iid}"`（swebench_convert.py:168）instance_id 为 `repo__name-NNN` 格式、无路径穿越面。结论：无新增可利用漏洞。

## Test Results

实际跑出（uv run，uv 位于 `~/.local/bin/uv`）：

- `uv run pytest tests/benchmark/test_swebench_subset.py tests/benchmark/test_swebench_convert.py tests/benchmark/test_c3_disclosures.py -q` → **49 passed, 1 skipped**（skip 为 @integration hf-mirror 网络测试，RUN_INTEGRATION 未设置）in 2.50s。
- `uv run pytest tests/benchmark/ -q` → **412 passed, 1 skipped** in 14.81s。
- 未跑全仓 pytest（已知环境性失败 tree-sitter / declarative-flow-engine 与本次无关，见任务说明）。
- 额外复验：
  - 38 条 fixture 逐条 validate 字段全过；difficulty 分布 17 easy/16 medium/5 hard 与 manifest `verified` 段逐项一致（count=38/by_repo 全对）。
  - 既有 10 条 fixture（requests×6/flask×1/pytest×3）`git diff origin/master...HEAD` 无任何改动。
  - CI 未弱化：无 `.github/`/workflow 变更；`pyproject.toml` 仅新增 `integration` marker。
  - `.gold-check*` 无残留；git status clean。

## 结论

build-subset 管线、convert 字段修复（track/scenario/difficulty/version/gitee 优先）、validate 内建、manifest verified 摘要与 disclosure 披露段均实现真实，测试 49+412 全绿，文档/backlog/spec sync/受保护路径事件齐备——管线本体质量良好。**唯一 major 问题**：sympy 全 8 条 fixture 的 test_command 为裸函数名（`pytest test_issue_11617` 等），现代 pytest 收集 0 项测试，评测时无法有效验证 agent 修复（假 PASS 或恒失败）；该问题因 sympy 未自检（github 不可达，已确认设计）而未被捕获。判定 **CHANGES_REQUESTED**：修复方式为在生成/校验侧拦截裸函数名 test_command（按 test.patch 文件路径重建 node id 或剔除）+ 新增回归测试，随后重扫受影响 fixture 并补记自检覆盖，再进入再审。其余 minor 项（--resume 死代码、.gitignore、tasks 勾选口径）可随修复一并处理。
