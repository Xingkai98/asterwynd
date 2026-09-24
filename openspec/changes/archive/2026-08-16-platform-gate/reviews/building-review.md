# Building Review: platform-gate

## Verdict

**PASS**

Round 1 独立审阅：tasks 1.1-4.4 逐条有产物/测试证据，实现与 design D1-D11、spec delta、current spec 的 SHALL 语句三者一致；GET-modify-PUT payload 构造、verify 白名单比对、fail-closed 错误处理、幂等、测试隔离均按设计落地；实测单测、OpenSpec strict validate 31/31、artifact checker、治理回归 55/55 全绿。无新确认的功能/安全/正确性/测试缺陷。Round 1 附两条低严重度校验宽严度建议（非阻塞），已作为审阅后加固修复（补回归测试，复测 23/23 全绿），见 Issues 节。

## Scope

- 审阅范围：`git diff cf57a91..HEAD`（立项 cf57a91 → 实现 commit f7e912b，共 9 文件 +1036/-41）
- 审阅 base: `cf57a9100256ae2358efa83daaaad8cde6754a23`（立项）
- 审阅 head: `f7e912bf67a49f53e17d0252aaa9e9fd7e98f86f`（Round 1 审阅的实现 commit）
- 审阅者 run id: `review-platform-gate-20260816-1`（独立零记忆，Round 1）
- 审阅后加固（PASS 判定后的非阻塞建议修复，独立 commit，不影响 PASS verdict）：`platform_gate.py` 的 `_validate_target` 增加空 `contexts` 拒绝（`or not contexts`）、`resolve_repo` 的 `--repo` 改用 `^[^/]+/[^/]+$` 严格格式校验；新增 `test_schema_rejects_empty_contexts` + `test_error_repo_flag_invalid_format_exit_2` 两条回归测试（详见 Issues 节）。加固后 `tests/test_platform_gate.py` 23/23 全绿。

## Per-Task Verification

逐条对照 tasks.md 1.1-4.4（4.5 / 5.x 为合入后 PR 收尾任务，未勾选属预期，checker 不强制）：

### 1. 规格

- [x] 1.1 proposal.md 含需求/非目标/行为定义/Impact Analysis，关联 issue #138 + 父 map #121（`openspec/changes/platform-gate/proposal.md:1-3`）。
- [x] 1.2 design.md 含 Context/Goals/Non-Goals/Decisions（D1-D11）/Risks/Trade-offs/Testing Strategy 全节（`design.md`）。
- [x] 1.3 Impact Analysis 维护并回写实现期发现（临时分支 PUT 实测、verify/apply 命令、--repo 短路；`proposal.md:76-83`）。
- [x] 1.4 RIR `research_tier: full` + status: enabled + reason 命中「走 grill 的非平凡 change」，4 条 research questions 全部有 findings 且带 GitHub 官方语义 + 公开 issue 引用，design impact 明确；「本地参考仓库不可用」在 findings 记录了不可用事实（`proposal.md:86-104`）。
- [x] 1.5 `reviews/grill-design.md` 存在，6 条 Confirmed Decisions + Q1-Q10 全部有实质 User Confirmation（2026-08-16 时间戳，无占位文本）；Q1/Q2 BLOCKING 已吸收进 D1/D3。
- [x] 1.6 backlog 已登记，配 `backlog_updated` 事件（`workflow-events.jsonl` seq 2）。
- [x] 1.7 spec delta 已合并到 `openspec/specs/platform-gate/spec.md`（SHALL 目标语言；delta 与 current spec 的两条 ADDED requirement 文本逐字一致，实测 diff 为空），配 `current_spec_synced` 事件（seq 3）；current spec 保留的「复用 GitHub branch protection 语义」为占位期既有 requirement，非本次新增，口径一致。

### 2. 测试

- [x] 2.1 payload 构造：`test_apply_constructs_put_payload_with_all_required_fields`（四必需字段 + `restrictions: null`、enabled→布尔、剔除 url/checks/contexts_url、reviews 保留 GET 可写子字段仅覆盖 count）+ `test_apply_idempotent_same_payload_twice` / `test_apply_idempotent_first_and_second_payload_equal`（幂等）+ `test_apply_strips_nested_description_from_put_body`（顶层 + 两层嵌套 `_description` 均不进 PUT body）全绿。
- [x] 2.2 verify 比对：`test_verify_consistent_exit_0` / `test_verify_drift_exit_1`（一致 exit 0 / 漂移 exit 1 + 逐字段 diff）/ `test_verify_ignores_readonly_derived_fields`（忽略 checks/url/contexts_url）/ `test_verify_contexts_order_insensitive`（排序集合比对）/ `test_verify_null_declared_field_is_drift_not_crash` + `test_verify_missing_field_is_drift_not_crash`（null/缺失=漂移 exit 1 不崩溃）全绿。
- [x] 2.3 错误处理：`test_error_gh_missing_exit_2` / `test_error_auth_failure_exit_2` / `test_error_api_put_failure_exit_2` / `test_error_schema_invalid_exit_2`（exit 2 fail-closed 且 `fake.assert_not_called()` 证明不调 gh/git）全绿。
- [x] 2.4 JSON schema：`test_real_config_schema_valid`（checked-in `platform-gate.json` 结构 + `_description` 被剥离）/ `test_description_fields_do_not_affect_schema` / `test_schema_rejects_unknown_top_level_key` 全绿。
- [x] 2.5 全量 pytest 回归：本审阅实测相关测试全绿 + 治理回归 55/55；pre-existing tree-sitter 环境失败（`tests/agent/code_intelligence/test_tree_sitter_symbols.py`）与本次 diff 无关（未触及任何被改模块）。

### 3. 实现

- [x] 3.1 `scripts/platform-gate.json`：目标状态声明（strict=true + contexts=[validate, benchmark-gate]、conversation enabled=true、reviews count=0 + approve=1 触发条件 `_description`、enforce_admins enabled=true），schema 风格对齐 flow-policy.json（`"schema": "1.0"`）。
- [x] 3.2 `scripts/platform_gate.py`（stdlib-only 单文件）：`--apply` GET-modify-PUT（`build_put_payload` 保留 GET 可写子字段 + 四必需字段 + `restrictions: null` + 递归剔除只读派生 + 递归剥离 `_description`）；`--verify` 白名单归一化比对（`compare` 只读声明字段，null/缺失=漂移 exit 1）；`--config` 输入路径 + stdout 唯一 JSON 输出 + diff 走 stderr；`--repo` 短路 git remote；错误 fail-closed exit 2。
- [x] 3.3 文档：AGENTS.md 新增「platform-gate 平台闸门（合入门禁）」节（required checks 全绿 + conversations 全 resolve + approve=1 触发条件与应急回滚 + `--verify`/`--apply` 命令与顺序红线）。
- [x] 3.4 新影响面已回写 Impact Analysis（临时分支 PUT 实测「零残留」、命令与测试覆盖更新）。

### 4. 验证

- [x] 4.1 相关单测：本审阅实测 `tests/test_platform_gate.py` 21 passed。
- [x] 4.2 全量 pytest：相关测试 + 治理回归全绿（pre-existing tree-sitter 除外，见 2.5）。
- [x] 4.3 OpenSpec strict validate：本审阅实测 31/31 passed（含 change/platform-gate、spec/platform-gate）。
- [x] 4.4 artifact checker：本审阅实测「OpenSpec artifact checks passed」（tasks 4.5/5.x 未勾选，review manifest 未生成属预期中间态，checker 不强拦）。

## Issues

无新确认缺陷（功能/安全/正确性/测试层面）。Round 1 附两条低严重度校验宽严度建议（非阻塞，不影响 PASS），**已在审阅后修复**：

- **✅ 已修复（审阅后加固）[轻微·建议] `_validate_target` 对空 `contexts` 列表放行**。Round 1 发现 `scripts/platform_gate.py:149-153` 的条件对 `[]` 空真放行，配置作者误写 `contexts: []` 时 `--apply` 会 PUT 空 required checks（门禁回退风险，虽可被 apply 前 diff 与事后 verify 检出，危害有界）。修复：条件补 `or not contexts`。回归测试：`test_schema_rejects_empty_contexts`（`contexts: []` → `PlatformGateError`「非空」）。
- **✅ 已修复（审阅后加固）[轻微·建议] `resolve_repo` 的 `--repo` 格式校验不拦多段路径**。Round 1 发现 `Xingkai98/asterwynd/extra` 三段值通过格式校验、直到 gh API 层才 fail-closed。修复：改用 `^[^/]+/[^/]+$` 严格校验。回归测试：`test_error_repo_flag_invalid_format_exit_2`（三段路径 → exit 2 + `--repo` 格式错误提示 + 零 gh/git 调用）。

两条修复均不改变 checked-in 配置与操作路径（真实仓 `Xingkai98/asterwynd`），加固后 `tests/test_platform_gate.py` 23/23 全绿。

## 实测结果

1. `uv run pytest tests/test_platform_gate.py -q` → Round 1 **21 passed**；审阅后加固复测 **23 passed in 0.80s**（全绿）。
2. `uv run python scripts/check_openspec_artifacts.py` → **OpenSpec artifact checks passed**（tasks 4.5/5.x 未勾选 + review manifest 未生成属预期中间态，checker 不强制）。
3. `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **31 passed, 0 failed（31 items）**（含 `spec/platform-gate`、`change/platform-gate`）。
4. `uv run pytest tests/test_flow_policy.py tests/test_workflow_guard.py -q` → **55 passed in 17.91s**（治理测试未被破坏）。

补充实测（正确性探针）：
- `parse_repo_from_url` 对 SSH/HTTPS/`ssh://` 三种格式均正确解析为 `owner/repo`，非 GitHub 主机返回 None（`test_error_git_remote_non_github_format_exit_2` 覆盖）。
- GET 返回 `required_pull_request_reviews: null` 的漂移场景下 `build_put_payload` 产出合法 PUT 形状（reviews 对象含 count=0，其余四必需字段齐全），不会崩溃。
- `--repo` 短路验证：`test_repo_flag_shortcircuits_git` 断言调用链中无任何 `git` 子进程（D9/Q8 落实）。
- delta spec 与 current spec 的两条 ADDED requirement 文本逐字一致（`difflib` 实测无差异）。

## Other Notes

- 平台实况验证（tasks 4.5/5.6）与归档收尾（5.1-5.7）为 PR 合入后主 session 执行项，本审阅不验证；design 已记录 2026-08-16 临时分支 `platform-gate-put-probe` 非破坏性 PUT 实测（四必需字段 + `restrictions: null` + enabled→布尔均成功，随后 DELETE 保护 + 删分支零残留）。
- AGENTS.md 不在 `scripts/flow-policy.json` 受保护路径清单内（D7 成立），本次修改无需 workflow-events 事件。
- approve=1 暂缓（count=0）为已锁定用户决策（grill Q6 确认「先不搞评分」），`_description` 记录触发条件，非缺陷。
