# Building Review: bypass-mode

## Verdict

PASS

## Reviewer

- run id: review-subagent-bypass-mode-building-review
- 时间: 2026-08-06
- 角色: 独立零记忆实现审阅（issue #90 机械门禁）

## Tasks Verification

逐条对照 `tasks.md` 验证。tasks.md 现全部勾选（1.1-4.6 共 24 项 + 第 5 节审阅修复 5.1-5.3，见 Issues #1 已修复）；以下验证按任务内容逐条读代码确认。

### 1. 规格

- [x] 1.1 delta 规格 — 存在且含 MODIFIED "Agent mode 约束工具权限"（bypass 默认 profile `bypass_default`、自动放行语义）、ADDED "Bypass mode 自动执行工具不审批"（3 场景）、MODIFIED "session 切换"（拒绝→成功）。grill Must-fix 的 "且未被 `allowed_modes` 排除" 措辞已写入场景 WHEN（`openspec/changes/bypass-mode/specs/agent-modes/spec.md:29`）。
- [x] 1.2 同步当前规格 — **已完成**：`openspec/specs/agent-modes/spec.md` 并入 MODIFIED 需求、"session 切换到 bypass" 成功场景，且 delta 的 ADDED requirement "Bypass mode 自动执行工具不审批"（3 场景）已补入 `openspec/specs/agent-modes/spec.md:107-130`（位于 "mode deny override 来自统一配置" Requirement 之前，`spec.md:132`），文本含 "且未被 `allowed_modes` 排除" 与 delta 一致（见 Issues #2 已修复）。
- [x] 1.3 grill — `reviews/grill-design.md` 存在，含 5 条 confirmed decisions、4 条 Must-fix、Q1-Q4 用户确认记录，满足 grill-confirmation-gate。
- [x] 1.4 文档影响 — `docs/development-guide.md:52,219` `/mode` 列表含 bypass；`docs/architecture.md:90` Web 模式切换列表含 bypass；`README.md:112` "无人值守入口 fail closed" 已限定为 "（显式指定 `bypass` mode 时自动放行）"；`README_EN.md` 英文翻译同步一致。

### 2. 测试

- [x] 2.1 `parse_agent_mode("bypass")` 返回 `AgentMode.BYPASS`（`tests/agent/test_run_config.py:49`），原 "rejects_bypass" / "can_allow_internal_bypass" 两个拒绝断言已删除。
- [x] 2.2 `test_runtime_state_set_mode_accepts_bypass`（`test_run_config.py:70-82`）：切换成功且 transition 正确。
- [x] 2.3 `test_mode_policy_bypass_auto_allows_all_risk_levels` / `test_mode_policy_bypass_auto_allows_high_risk_without_approval`（HIGH 工具 `ALLOW` + `can_execute_without_approval=True`）/ `test_mode_policy_bypass_still_denies_configured_tool`（`deny_tools_by_mode` 下仍 `DENY`）。
- [x] 2.4 `test_bypass_mode_allows_browser_tools`（`test_browser_mode_policy.py:98-104`）：bypass 下浏览器工具可见 + `ALLOW`；手写 mode 映射已从 `fail_closed` 改为 `bypass_default`（`:28`），未遗漏（grill 明确警告过的静默 fail_closed 陷阱）。
- [x] 2.5 `test_mode_command_switches_to_bypass`（`test_slash_command_registry.py`）：`/mode bypass` 返回 "Mode changed: build -> bypass"；FakeAgent 中拒绝 bypass 的 raise 已删除。
- [x] 2.6 CLI — `test_cli_accepts_bypass_mode`（`--mode bypass` 成功启动）与 `test_cli_interactive_mode_command_switches_to_bypass`（交互 `/mode bypass`）均改写为接受；`test_cli.py` FakeAgent 拒绝 bypass 的 raise 已删除。
- [x] 2.7 Web — `test_websocket_set_mode_switches_to_bypass`（`test_server.py`）：`set_mode bypass` 返回 `mode_changed` + `new_mode=bypass`，后续 run 使用 bypass；`argument_hint` 断言已更新为 `<build|read_only|plan|bypass>`。

### 3. 实现

- [x] 3.1 `bypass_default` profile（`agent/tool_permissions.py:157-166`）：`ALL_CAPABILITIES` + `auto_approve_max_risk=HIGH` + `approval_required_max_risk=HIGH`，含未来风险档退化注释。
- [x] 3.2 `parse_agent_mode` 接受 bypass、`allow_bypass` 死参数已删除（`agent/run_config.py:25-34`）；`_default_permission_profiles_by_mode` BYPASS → `bypass_default`（`:202`）。
- [x] 3.3 `agent/config.py:300` BYPASS 默认 `"bypass_default"`；`mode_config(mode).permission_profile or defaults[mode]` 用户覆盖路径不受影响（`:303`）。
- [x] 3.4 `agent/main.py` `--mode` help — **实际 6 处**全部含 bypass（`:353` run、`:386` 交互、`:666` web、`:711` benchmark、`:919` benchmark_gate、`:1095` session_resume；任务文案写 4 处，grill 已预告 4→6，实现覆盖全部 6 处）。`agent/commands/registry.py` `/mode` usage（`:416`）、argument_hint（`:418`）、无参错误文案（`:173`）三者一致含 bypass。
- [x] 3.5 `web/static/index.html` mode 下拉新增 `<option value="bypass">`（`:29`）。
- [x] 3.6 `asterwynd.example.yaml` modes 新增 `bypass: {permission_profile: bypass_default, deny_tools: []}`。
- [x] 3.7 `parse_agent_mode` unsupported-mode 错误 `supported` 列表含 `"bypass"`（`agent/run_config.py:31`）。

### 4. 验证

- [x] 4.1 定向测试：见 Test Results，134 passed。
- [x] 4.2 全量 `uv run pytest -q`：1801 passed / 1 failed（仅已知环境失败 `test_tree_sitter_extracts_java_and_kotlin_symbols`）/ 7 skipped。
- [x] 4.3 OpenSpec strict validate：29 passed / 0 failed（含 change/bypass-mode）。
- [x] 4.4 `scripts/check_openspec_artifacts.py`：passed（tasks 全勾选后 building-review 门禁已强制触发，要求 building-review.md + manifest PASS；见 Issues #1 已修复）。
- [x] 4.5 benchmark smoke：`uv run asterwynd benchmark ... --mode bypass` 正常启动不崩溃，产出 runs 目录（fake runner 36 任务通过率低属预期）。
- [x] 4.6 building review：本文档（manifest 由 review-loop 收尾生成）。

## Issues

Round 1 发现的问题均已在 Round 1 修复（tasks.md 第 5 节 5.1-5.3）：

- [已修复/中等] tasks.md 未勾选。现 1.1-4.6 全部 24 项 + 第 5 节 5.1-5.3 全部勾选，building-review 机械门禁已强制触发（`scripts/check_openspec_artifacts.py` 在 tasks 全勾选时要求 building-review.md + manifest PASS，验证运行见下）。文件: `openspec/changes/bypass-mode/tasks.md`（tasks 5.1 勾选 + 本报告 + manifest）
- [已修复/中等] 当前规格缺 delta 的 ADDED requirement。现 `openspec/specs/agent-modes/spec.md:107-130` 含完整 "Bypass mode 自动执行工具不审批" Requirement 与 3 场景（bypass 自动执行高危工具 / bypass 仍尊重显式 deny / bypass 作为用户可选 mode），位于 "mode deny override 来自统一配置"（`:132`）之前；要求文本含 "且未被 `allowed_modes` 排除" 与 delta 一致。`workflow-events.jsonl` 已补 seq=3 `current_spec_synced` 事件。文件: `openspec/specs/agent-modes/spec.md`、`openspec/changes/bypass-mode/workflow-events.jsonl`
- [已修复/轻微] task 3.7 错误消息无回归测试。已补 `test_parse_agent_mode_error_message_lists_bypass`（`tests/agent/test_run_config.py:52-54`，断言 `parse_agent_mode("unknown-mode")` 抛 ValueError 且 match "bypass"）。文件: `tests/agent/test_run_config.py:52`
- [已修复/轻微] 无 `_clamp_mode` bypass 专属测试。已补 `test_create_subagent_cannot_escalate_to_bypass_from_build_parent`（build 父 + 子请求 bypass → 钳回 build，`tests/agent/subagent/test_subagent_manager.py:64-71`）与 `test_create_subagent_inherits_bypass_from_bypass_parent`（bypass 父 + 子 mode=None → 继承 bypass，`:74-81`）。文件: `tests/agent/subagent/test_subagent_manager.py:64,74`
- [记录/轻微] `bypass_default` 与 `build_legacy_auto_high_risk` 字段完全一致（ALL_CAPABILITIES + HIGH/HIGH）。design Decision 1 已明确论证命名独立性（bypass 语义不挂在 legacy 名称上），属有意为之，非冗余回归；仅记录，无需修改。
- [记录/轻微] tasks.md 3.4 文案写"全部 4 处 `--mode` help"，实际为 6 处（main.py 353/386/666/711/919/1095），实现已覆盖全部，任务文案已同步为"全部 6 处"。记录备查，无需修改。

## Test Results

```bash
# Round 1 定向回归（Round 1 修复新增测试）
uv run pytest tests/agent/test_run_config.py tests/agent/subagent/test_subagent_manager.py -q
# 30 passed in 1.28s
#   含 test_parse_agent_mode_error_message_lists_bypass、
#   test_create_subagent_cannot_escalate_to_bypass_from_build_parent、
#   test_create_subagent_inherits_bypass_from_bypass_parent

# Round 1 定向测试（bypass-mode 全路径）
uv run pytest tests/agent/test_run_config.py tests/agent/tools/test_browser_mode_policy.py \
  tests/agent/commands/test_slash_command_registry.py tests/test_cli.py tests/web_tests/test_server.py -q
# 134 passed in 4.61s

uv run pytest -q
# 1801 passed, 7 skipped, 1 failed in 106s
# 唯一失败：tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols
# （已知环境失败，clean baseline 同样失败，与本 change 无关）

npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
# 29 passed, 0 failed

# Round 1 修复后重跑 artifact checker（tasks 全勾选，building-review 门禁强制触发）
PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
# 生成 review manifest 后：OpenSpec artifact checks passed

uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-bypass --mode bypass
# 正常启动不崩溃，产出 runs 目录（fake runner 任务通过率低属预期）
```

## 结论

实现完整、正确、安全，Round 1 审阅发现的 2 个中等 + 2 个轻微问题已全部修复并补回归测试：

- `parse_agent_mode` 单点放开，全仓无 `allow_bypass` 残留调用，无 "reserved for internal use" 残留；unsupported-mode 错误消息 supported 列表含 `"bypass"` 且有回归测试（`test_parse_agent_mode_error_message_lists_bypass`）。
- `bypass_default` profile 定义正确（ALL_CAPABILITIES + HIGH/HIGH，`decide_tool` 中 HIGH ≤ HIGH 恒真进入 `ALLOW` 分支）；BYPASS 默认映射在 `run_config.py` 与 `config.py` 两处一致改为 `bypass_default`。
- 安全边界未放宽：`decide_tool` 判定顺序不变（`allowed_modes` → `deny_tools_by_mode` → profile.denied_tools → capability → auto_approve），`deny_tools` 在 BYPASS 下仍 `DENY`（有测试）；`_clamp_mode` 未改动、子 agent 钳制仍成立，且有 bypass 专属回归测试（build 父无法提升子到 bypass / bypass 父默认子继承 bypass）；`fail_closed` 保留为未知 mode 兜底。
- 全部 6 处 `--mode` help、`/mode` usage/argument_hint/无参文案、Web 下拉、example.yaml 一致暴露 bypass。
- 原"拒绝 bypass"断言在 5 个测试文件中全部改写为"接受/自动放行"，`test_browser_mode_policy.py` 手写映射已同步为 `bypass_default`（grill 警告的静默 fail_closed 陷阱已规避）。
- 当前规格 `openspec/specs/agent-modes/spec.md` 已完整并入 delta（MODIFIED + ADDED requirement 3 场景），`workflow-events.jsonl` 含 seq=3 spec-sync 事件；tasks.md 全部勾选，building-review 门禁强制触发并由本报告 + manifest 满足。
- 定向 134 + 30 测试全绿，全量 pytest 仅已知环境失败（tree_sitter，clean baseline 亦失败），OpenSpec strict validate 与 artifact checker 均通过。

按项目门禁判定，给予 **PASS**。
