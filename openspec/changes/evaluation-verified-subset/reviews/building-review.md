# Building Review: evaluation-verified-subset（Round 2）

## Reviewer

- run id: review-evaluation-verified-subset-round2-2026-08-18
- 时间: 2026-08-18
- 独立零记忆声明：本 reviewer 未继承开发上下文；全部结论基于对 Round 1 审阅报告、change 文档与代码的独立复核。Round 1 结论（5 项 CHANGES_REQUESTED）仅作核验清单，逐项以代码事实与实测重新验证。
- 验证方式：读 `benchmarks/swebench_convert.py`（`_test_file_from_patch`/`build_test_command`/`generate_tasks`）、`benchmarks/swebench_subset.py`（`cmd_build_subset` resume 分支）、`.gitignore` diff、tasks.md；shlex 扫描全部 38 条 fixture 的 test_command；运行回归测试。

## Verdict

**PASS**

Round 1 的 5 项 CHANGES_REQUESTED 全部落地或按既定口径处理：sympy 8 条裸函数名 test_command 已按 test.patch 文件路径重建为 `-k` 形式且无裸标识符；`--resume` 已从死代码改为续跑收敛语义；`.gitignore` 已补 `.gold-check*`；tasks.md 5.3/5.3b 已勾选；Issue 5（REPO_TEST_COMMAND_TEMPLATES 死代码）为非本 change 引入的既有债务，未修且已记录，不阻塞。回归测试全绿。

## Tasks Verification

逐条核对 tasks.md 的 `[x]` 任务（6.x 为 `[ ]`，属 PR 前正常待办）：

| Task | 状态 | 证据 |
|---|---|---|
| 1.1 proposal 三件套完整 | ✅ | proposal.md:5-48（Change Type/Impact Analysis/RIR research_tier=light） |
| 1.2 batch-grill-me 审视 D1–D5 | ✅ | reviews/grill-design.md 全文 |
| 1.3 停轮 + User Confirmation | ✅ | grill-design.md:117-126，OQ-V1~V6 逐条含用户答复与确认时间 |
| 2.1 build-subset 子命令 | ✅ | swebench_subset.py:529-536（--output/--targets/--skip-gold-check/--full-gold-check/--resume/--known-bad-file） |
| 2.2 流程接线 | ✅ | swebench_subset.py:424-469（load_verified→_probe_dataset→build_subset→generate_tasks） |
| 2.3 落盘后自动 validate，invalid exit 1 | ✅ | swebench_subset.py:471-476 |
| 3.1 hf-mirror 实际生成 28 新/38 总 | ✅（产物可证） | benchmarks/tasks/ 38 条 swebench-* fixture 实盘；网络无法复跑 |
| 3.2 validate_fixtures_dir 全过 | ✅（复验） | 38 条 task.json track/scenario/difficulty 归一化合法；manifest verified 段 count=38 与实盘一致 |
| 3.3 L3 抽样自检 | ✅（机制+记录） | gold_check external 路径（swebench_subset.py:205-238）；sympy/seaborn/pylint 未自检为 github 不可达的已确认设计，非缺陷 |
| 3.4 结果回写 change 文档 | ✅ | design.md/proposal.md/backlog 回写 |
| 4.1 manifest verified 摘要登记 | ✅（复验） | manifest.json `verified` 段 count=38、by_repo/by_difficulty 与 38 条实盘一致（medium=16/easy=17/hard=5） |
| 4.2 临时文件清理 | ✅ | `.gold-check*` 无残留（.gitignore 已加忽略规则）；git status clean |
| 5.1/5.2 Impact Analysis + RIR | ✅ | 已维护，无 `unknown`/`TBD`/`待确认` 残留 |
| 5.3/5.3b backlog + spec sync | ✅（Round 1 Issue 4 已修复） | tasks.md:31-32 现为 `[x]`；workflow-events.jsonl 记录 spec/backlog 结构化解释事件 |
| 5.4/5.5/5.6 测试/validate/checker/smoke | ✅ | 见 Test Results；checker 当前仅报 review manifest 缺失（review-loop 中途预期状态，非缺陷） |

## Issues

### Round 1 Issue 1（major）：sympy 8/38 fixture 裸函数名 test_command → **已修复**

- **修复证据（代码）**：`swebench_convert.py:112-127` `_test_file_from_patch(test_patch)` 从 test.patch `diff --git a/<path>` 头提取测试文件路径（偏好含 `test` 的路径）；`:130-165` `build_test_command` 以 `bare = [t for t in tests if "::" not in t and ".py" not in t]` 识别裸函数名，重建 `python -m pytest {test_file} -k '{expr}' --tb=short -p no:warnings`（`-k` 表达式外层单引号、内部为合法 Python 标识符 `or` 连接，无嵌套引号）；`:203` `generate_tasks` 调用处传入 `ex.get("test_patch", "")`。
- **修复证据（产物）**：shlex 扫描全部 38 条 fixture 的 test_command，无任何裸标识符路径参数。sympy 8 条实盘命令均为：
  - `sympy/geometry/tests/test_point.py -k 'test_issue_11617'`
  - `sympy/utilities/tests/test_lambdify.py -k 'test_issue_12092'`
  - `sympy/matrices/expressions/tests/test_matexpr.py -k 'test_Identity'`
  - `sympy/combinatorics/tests/test_permutations.py -k 'test_args'`
  - `sympy/combinatorics/tests/test_permutations.py -k 'test_Permutation_subclassing'`
  - `sympy/matrices/tests/test_sparse.py -k 'test_sparse_matrix'`
  - `sympy/core/tests/test_basic.py -k 'test_equality or test_comparisons_with_unknown_type'`
  - `sympy/core/tests/test_evalf.py -k 'test_evalf_bugs'`
  其余 30 条（requests/flask/pytest/seaborn/pylint）均为完整 node id 或 `-k` 形式。
- **回归守卫（新增）**：`tests/benchmark/test_swebench_subset.py:357-365` `test_generated_fixture_test_commands_have_no_bare_identifiers`（shlex 解析、跳过 `-k`/`-p`、断言无裸参数）；`tests/benchmark/test_swebench_convert.py:63-70` `test_bare_function_names_rebuild_with_test_patch_file`、`:72-91` `test_bare_function_names_without_patch_uses_k_only`（含 shlex 校验裸函数名只出现在 `-k` 内）。
- **残留（info，不阻塞）**：`build_test_command` 的 `repo` 形参未被函数体使用（既有签名，非本次回归）；`-k` 为子串匹配，理论上可能多收集同名前缀用例，属可接受精度范围。

### Round 1 Issue 2（minor）：`--resume` 死代码 → **已修复**

- 修复证据：`swebench_subset.py:437-466`。`--resume` 时 `exclude_ids = set()`（选择池含既有实例，`build_subset` 确定性排序保证每次选中同一目标集），落盘前按输出目录已存在的 `swebench-<iid>/task.json` 过滤跳过——续跑收敛、不覆盖既有、不漂移。非 resume 路径仍走 `exclude_ids = existing_ids`。
- 测试强化：`tests/benchmark/test_swebench_subset.py:234-289` `test_build_subset_cli_resume_skips_existing` 断言既有 requests-0 未被覆盖写（无 `test_command` 键），其余 3 条生成。真实覆盖 resume 分支（此前测试实际走的是排除路径）。

### Round 1 Issue 3（minor）：.gitignore 缺 `.gold-check*` → **已修复**

- 证据：`.gitignore` 新增 `.gold-check*` 规则。

### Round 1 Issue 4（minor）：tasks.md 5.3/5.3b 未勾选 → **已修复**

- 证据：tasks.md:31-32 现为 `[x]`（backlog 登记 + spec sync 均已实际执行并有 workflow-events.jsonl 解释事件）。

### Round 1 Issue 5（minor）：REPO_TEST_COMMAND_TEMPLATES 死代码 → **按既定口径处理（既有债务）**

- 非本 change 引入（全仓无消费方，本次 diff 未触碰），Round 1 已接受为既有债务；未修不阻塞。建议后续单独清理。

### Round 1 Issue 6（info，安全维度）→ **维持结论**

- shell 注入面 `shell=True` 执行 `task.test_command`（swebench_subset.py:194-202,229-237）参数来自可信研究数据集；git clone/apply/checkout 均为 list 形式无 shell；`task_dir = output_base / f"swebench-{iid}"` 无路径穿越面。Round 2 修复新增的 `-k` 表达式为 `or` 连接的纯标识符（`name.split("[")[0].split("::")[-1]` 已剥离参数化与路径分隔），外层单引号包裹、内部无引号字符，无新增注入面。结论：无新增可利用漏洞。

## Test Results

- `uv run pytest tests/benchmark/test_swebench_subset.py tests/benchmark/test_swebench_convert.py -q` → **33 passed, 1 skipped**（skip 为 @integration hf-mirror 网络测试，RUN_INTEGRATION 未设置）。
- 复验：38 条 fixture 逐条 shlex 扫描 test_command，无裸标识符；manifest verified 段与实盘一致；`git status` clean，无 `.gold-check*` 残留。
- 未跑全仓 pytest（已知环境性失败 tree-sitter / declarative-flow-engine 与本次无关）；artifact checker 报 review manifest 缺失为 review-loop 中途预期状态，非缺陷。

## 结论

Round 1 的 5 项 CHANGES_REQUESTED 全部按声明落地，且经独立复核确认：sympy 8 条 fixture 的 test_command 已由裸函数名重建为 `python -m pytest <test.patch文件> -k 'func'` 形式（无裸标识符，`-k` 引号正确），生成/校验侧已具备裸名拦截，回归测试（全 fixture 守卫 + 裸函数名重建单测）存在且全绿；`--resume` 语义修复、`.gitignore`、tasks 勾选均已处理；Issue 5 为既有债务已记录不阻塞。判定 **PASS**，无未解决的中等以上问题。
