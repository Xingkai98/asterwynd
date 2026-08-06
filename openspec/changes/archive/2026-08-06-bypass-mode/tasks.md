## 1. 规格

- [x] 1.1 修改 `agent-modes` 规格 delta：`bypass` 从内部保留/fail_closed 改为用户可选/自动放行；更新默认 profile 映射；新增"session 切换到 bypass 成功"与"bypass 自动执行不审批"场景。
- [x] 1.2 同步当前规格到 `openspec/specs/agent-modes/spec.md`。
- [x] 1.3 开发前使用独立 subagent design grilling（`reviews/grill-design.md`）审视 `design.md`，确认实现细节、依赖、风险、测试策略和文档影响。
- [x] 1.4 文档影响：更新 `docs/development-guide.md` 的 `/mode` 模式列表、`docs/architecture.md` 的 Web 模式切换列表、`README.md` 中"CLI 单轮和 benchmark 等无人值守入口 fail closed"表述，并同步 `README_EN.md` 英文翻译。

## 2. 测试

- [x] 2.1 新增 `parse_agent_mode` 接受 `bypass` 的单元测试；更新原有"拒绝 bypass"断言。
- [x] 2.2 新增 `AgentRuntimeState.set_mode("bypass")` 成功切换的单元测试。
- [x] 2.3 新增 `ModePolicy` BYPASS 下 HIGH 风险工具 `ALLOW`（不 `REQUIRE_APPROVAL`）的测试；`deny_tools` 在 BYPASS 下仍 `DENY`。
- [x] 2.4 新增 bypass 下浏览器工具可见的测试（替换原"fail_closed 拒绝"断言）。
- [x] 2.5 更新 slash command registry 测试：`/mode bypass` 成功。
- [x] 2.6 更新 CLI 测试：`--mode bypass` 成功启动；交互 `/mode bypass` 成功。
- [x] 2.7 更新 Web 测试：`set_mode bypass` 成功。

## 3. 实现

- [x] 3.1 `agent/tool_permissions.py` 新增 `bypass_default` profile（ALL capabilities，auto_approve_max_risk=HIGH）。
- [x] 3.2 `agent/run_config.py`：`parse_agent_mode` 接受 bypass；`_default_permission_profiles_by_mode` 中 BYPASS 改 `bypass_default`。
- [x] 3.3 `agent/config.py`：`permission_profiles_by_mode` 中 BYPASS 默认改 `bypass_default`。
- [x] 3.4 `agent/main.py` 全部 6 处 `--mode` help（run/交互/web/benchmark/benchmark-gate/session resume）加入 bypass；`agent/commands/registry.py` `/mode` usage 与 `argument_hint` 加入 bypass。
- [x] 3.5 `web/static/index.html` mode 下拉加入 bypass。
- [x] 3.6 `asterwynd.example.yaml` modes 示例加入 bypass。
- [x] 3.7 `parse_agent_mode` unsupported-mode 错误消息 `supported` 列表加入 `"bypass"`。

## 4. 验证

- [x] 4.1 运行新增与更新的单元/集成测试。
- [x] 4.2 运行全量 `uv run pytest -q`。
- [x] 4.3 运行 OpenSpec strict validate。
- [x] 4.4 运行 `scripts/check_openspec_artifacts.py`。
- [x] 4.5 跑通至少一个 benchmark smoke（fake runner）。
- [x] 4.6 运行独立 subagent building review（`reviews/building-review.md` + manifest）。

## 5. 审阅修复（Round 1）

- [x] 5.1 补充当前规格的 ADDED requirement：`Bypass mode 自动执行工具不审批`（3 个场景），并补 workflow-events.jsonl 对应 spec-sync 事件。
- [x] 5.2 勾选全部 tasks 项，触发 building-review 机械门禁。
- [x] 5.3 新增回归测试：`parse_agent_mode` 错误消息列出 bypass；`_clamp_mode` 下 build 父无法提升子到 bypass、bypass 父默认子继承 bypass。
