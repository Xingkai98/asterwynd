## Why

当前 `bypass` 是 AgentMode 枚举中的内部保留 mode，默认映射到 `fail_closed` permission profile（拒绝一切能力），并且用户入口（CLI `--mode`、交互 `/mode` 命令、Web session 切换）一律拒绝该 mode。实际开发中需要一种"所有命令自动执行、不经过审批"的旁路模式，用于可信环境下的自动化开发、benchmark 冒烟和面试演示，避免高危工具逐次审批打断流程。

本 change 将 `bypass` 从"内部保留 + fail closed"改为"用户可选 + 自动放行"的真实模式：所有已注册且未被显式 deny 的工具自动执行，不经过审批。

## Change Type

- primary: feature
- secondary: []

## What Changes

- `bypass` 成为用户可选 mode：`parse_agent_mode` 接受 `bypass`，`AgentRuntimeState.set_mode` 允许切换到 `bypass`。
- 新增 `bypass_default` permission profile：允许全部 capability，`auto_approve_max_risk=HIGH`、`approval_required_max_risk=HIGH`，使所有工具判定为 `allow`，不产生 `require_approval`。
- BYPASS mode 的默认 profile 映射从 `fail_closed` 改为 `bypass_default`（`run_config.py` 与 `config.py` 两处）。
- CLI `--mode bypass`、交互 `/mode bypass`、Web mode 下拉与 session 切换、`ASTERWYND_MODE=bypass` 配置均可用。
- 显式 `deny_tools` 配置与工具 `allowed_modes` 约束仍然生效：bypass 只放行审批，不放行显式禁止的工具。
- `fail_closed` profile 保留，仅作为未知 mode 的兜底。

## Capabilities

### Modified Capabilities

- `agent-modes`: 更新 bypass mode 语义与默认 profile 映射；新增"session 切换到 bypass 成功"场景；新增 bypass 自动执行场景。

## Dependencies

- 无新外部依赖。依赖现有 `introduce-agent-mode-policy` / `add-runtime-mode-switching` 已落地的 mode policy、`PermissionProfile`、`AgentRuntimeState` 和 CLI/Web mode 切换路径。

## Impact Analysis

- 影响代码：
  - `agent/tool_permissions.py`：新增 `bypass_default` profile。
  - `agent/run_config.py`：`parse_agent_mode` 允许 bypass；BYPASS 默认 profile 映射改 `bypass_default`。
  - `agent/config.py`：BYPASS 默认 profile 映射改 `bypass_default`。
  - `agent/main.py`：`--mode` help 文案加入 bypass。
  - `agent/commands/registry.py`：`/mode` usage 文案加入 bypass。
  - `web/static/index.html`：mode 下拉加入 bypass。
  - `asterwynd.example.yaml`：modes 示例加入 bypass。
- 影响测试：
  - `tests/agent/test_run_config.py`：bypass 解析/切换/策略测试从"拒绝"改为"允许并自动放行"。
  - `tests/agent/tools/test_browser_mode_policy.py`：bypass 下浏览器工具改为可见。
  - `tests/agent/commands/test_slash_command_registry.py`：`/mode bypass` 成功。
  - `tests/test_cli.py`：`--mode bypass` 成功。
  - `tests/web_tests/test_server.py`：Web 切换到 bypass 成功。
- 不改变 build/read_only/plan mode 行为；不改变 approval handler 机制；不改变 WorkspacePolicy 与 command_guard。

## Reference Implementation Research

- status: enabled
- reason: bypass/免审批模式是 coding agent 的常见能力（Claude Code bypassPermissions、Codex auto 模式等），需要确认免审批模式在用户入口、子 agent 钳制、显式 deny 优先级上的常见处理方式。
- research questions:
  - 主流 coding agent 的免审批模式如何暴露（CLI 参数 / 会话内切换 / 配置）？
  - 免审批模式下是否仍保留显式 deny / 黑名单拦截？
  - 免审批模式如何约束子 agent 权限继承？
- findings:
  - 当前工作区 `.dev/reference-repos.txt` 未提供可直接对比的参考仓库；本地无可用参考实现索引。
  - 本项目已有 `build_legacy_auto_high_risk` profile（自动放行 HIGH 风险）作为先例，说明"全部自动放行"的 profile 形态已在代码中实践过。
  - 子 agent 权限钳制已有 `_clamp_mode` 排序（BYPASS 为最宽松），免审批模式应沿用"子 agent 不能比父更宽松"的既有约束。
- design impact:
  - 采用独立 `bypass_default` profile（而非复用 `build_legacy_auto_high_risk`），保持语义命名清晰。
  - 显式 `deny_tools` 与 `allowed_modes` 继续作为最终否决，与现有 `ModePolicy.decide_tool` 判定顺序保持一致。
