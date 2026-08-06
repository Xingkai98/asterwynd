## Context

`agent-modes` 规格定义了四种 AgentMode：`build`、`read_only`、`plan` 和内部保留的 `bypass`。其中 `bypass` 是唯一没有用户入口的模式：`parse_agent_mode`（`agent/run_config.py:25-38`）默认拒绝 `bypass`（`allow_bypass=False` 时抛 "reserved for internal use"），`AgentRuntimeState.set_mode`（`agent/run_config.py:56-74`）走同一解析路径，因此 CLI `--mode`、交互 `/mode` 命令、Web session 切换全部无法进入 `bypass`。同时 BYPASS mode 的默认 permission profile 是 `fail_closed`（`agent/run_config.py:206`、`agent/config.py:300`），即拒绝一切能力。

需求是把 `bypass` 变成"所有命令自动执行、不经过审批"的用户可选模式。变更面集中在 mode 解析、默认 profile 映射和用户入口文案/选项；`ModePolicy.decide_tool`（`agent/run_config.py:101-175`）的判定顺序不需要改动——只要 BYPASS 默认 profile 自动放行全部风险等级，自然不再产生 `require_approval`。

## Goals / Non-Goals

**Goals:**

- `bypass` 成为用户可选 mode：CLI `--mode`、交互 `/mode`、Web 下拉/切换、`ASTERWYND_MODE` 环境变量、`default_mode` 配置均可用。
- `bypass` 默认自动放行所有已注册工具（LOW/MEDIUM/HIGH 风险全部 `allow`），不产生审批请求。
- 显式安全边界保持：`deny_tools` 配置、工具 `allowed_modes`、WorkspacePolicy、command_guard 仍然生效。
- 子 agent 权限钳制不变：子 agent 不能请求比父 agent 更宽松的 mode。

**Non-Goals:**

- 不改变 build/read_only/plan mode 的现有行为。
- 不改变 approval handler 机制与审批 UI。
- 不改变 WorkspacePolicy、command_guard 或 sandbox 的强制边界。
- 不新增除 bypass 之外的 mode。

## Decisions

### Decision 1: 新增 `bypass_default` permission profile

在 `BUILTIN_PERMISSION_PROFILES` 中新增 `bypass_default`：`allowed_capabilities=ALL_CAPABILITIES`、`auto_approve_max_risk=HIGH`、`approval_required_max_risk=HIGH`。

理由：`ModePolicy.decide_tool` 对风险 ≤ `auto_approve_max_risk` 的工具返回 `ALLOW`；风险只有 LOW/MEDIUM/HIGH 三级，因此 `auto_approve_max_risk=HIGH` 使所有工具都进入 `ALLOW` 分支，不再产生 `require_approval`。命名独立于 `build_legacy_auto_high_risk`（该 profile 语义是"build 的 legacy 兼容"），避免把 bypass 的语义挂在 legacy 名称上。

### Decision 2: `parse_agent_mode` 接受 `bypass`，`set_mode` 允许切换

`parse_agent_mode` 移除"reserved for internal use"拒绝逻辑，`bypass` 成为普通可解析值；`allow_bypass` 参数保留为兼容性无操作（不再影响结果）。`AgentRuntimeState.set_mode` 随之允许 `bypass`。`parse_agent_mode` 的 unsupported-mode 错误消息 `supported` 列表（`agent/run_config.py:33`）同步加入 `"bypass"`，保证未知 mode 报错文案列出已支持的 bypass。

理由：需求明确 bypass 是用户可选模式，所有用户入口（CLI `--mode`、交互 `/mode`、Web `set_mode`、`ASTERWYND_MODE`、`default_mode` 配置、子 agent mode 请求）最终都汇聚到 `parse_agent_mode`（`agent/run_config.py:25-38`；调用点 `agent/main.py:241`、`agent/config.py:413/439/472/486`、`web/session.py:231`、`agent/subagent/manager.py:183`），只改解析器即可统一放开，无遗漏入口。

### Decision 3: BYPASS 默认 profile 映射改为 `bypass_default`

`run_config.py:_default_permission_profiles_by_mode` 与 `config.py:permission_profiles_by_mode` 中 `AgentMode.BYPASS` 的默认值从 `"fail_closed"` 改为 `"bypass_default"`。`fail_closed` profile 保留，仍作为未知 mode 的兜底（`ModePolicy.permission_profile` 的 fallback）。

理由：两处映射是 BYPASS 生效的唯二来源；同步修改保证无论走 `ModePolicy(...)` 默认构造还是 `AsterwyndConfig` 配置解析，行为一致。配置层允许用户通过 `modes.bypass.permission_profile` 覆盖。

### Decision 4: 显式 deny 与 allowed_modes 仍为最终否决

`ModePolicy.decide_tool` 判定顺序不变：`allowed_modes` 排除、`deny_tools_by_mode` 排除、`profile.denied_tools` 排除在 capability/risk 判定之前。bypass 只放行"审批"，不放行显式禁止的工具。

理由：免审批模式不等于无安全边界；保留显式 deny 与 WorkspacePolicy/command_guard 是合理的最小防御，也与现有 `deny_tools` 配置语义一致。

### Decision 5: 子 agent mode 钳制不变

`SubAgentManager._clamp_mode`（`agent/subagent/manager.py:697-706`）中 BYPASS 为最宽松档位（order 2）。父 agent 为 BYPASS 时子 agent 可请求 BYPASS，但 build/read_only/plan 父 agent 不能把子 agent 提升为 BYPASS。

理由：这是已有的权限继承约束，语义在 bypass 变为用户可选后依然成立，无需改动。

### Decision 6: 用户入口文案与选项同步

`bypass` 必须出现在所有用户入口：`agent/main.py` 全部 4 处 `--mode` help（`run` 命令 `:353`、交互 `:386`、`web` `:666`、`benchmark` `:711`）、`agent/commands/registry.py` 的 `/mode` usage 与 `argument_hint`（`:416,418`）、`web/static/index.html` mode 下拉、`asterwynd.example.yaml` modes 示例。

理由：用户可选 mode 必须在所有入口可见可输；遗漏会导致"配置能开但界面不能选"的不一致。全部入口枚举由独立 grill 对照代码验证。

### Decision 7: 文档影响范围

同步更新 mode 相关文档段落：`docs/development-guide.md` 的 `/mode` 模式列表、`docs/architecture.md` 的 Web 模式切换列表、`README.md` 中"CLI 单轮和 benchmark 等无人值守入口 fail closed"表述（限定为"默认 build 下；显式 bypass 时自动放行"），并同步 `README_EN.md` 英文翻译。

理由：AGENTS.md 文档影响检查要求更新本次变更造成的事实变化；bypass 从"内部保留"变为"用户可选"是这些文档段落中的事实变化。

## Pre-Implementation Review

- Questions resolved:
  - 独立 subagent design grilling 已运行并产出 `reviews/grill-design.md`（run id `grill-subagent-bypass-mode-design-review`），对照代码逐项验证 5 条决策成立，并修正 4 个必须修改项（入口文案枚举、supported 错误消息、spec 场景措辞、文档影响范围）。
  - Open Questions 由用户逐项确认并记录于 `reviews/grill-design.md` 的 `## User Confirmation` 节。
- Options considered:
  - 复用 `build_legacy_auto_high_risk` 作为 BYPASS 默认 profile（少一个 profile）。
  - 新增独立 `bypass_default` profile。
  - 保留 `allow_bypass` 标志并在用户入口显式传 True。
  - 移除 `allow_bypass` 标志。
- Rejected alternatives:
  - 复用 `build_legacy_auto_high_risk`：语义命名不清晰，bypass 语义不应挂在 legacy build 名称上。
  - 保留 `allow_bypass` 并在各入口显式传 True：四处入口都要改动且容易遗漏新入口，直接放开解析器更一致。
- Final confirmations:
  - 所有命令（LOW/MEDIUM/HIGH 风险工具）在 bypass 下自动执行、不经过审批——用户需求原文确认。
  - bypass 作为用户可选模式在 CLI、交互命令、Web、配置四处暴露。
  - 显式 deny、`allowed_modes` 排除、WorkspacePolicy、command_denylist 与 Bash 内部命令黑名单仍生效。
  - 子 agent 权限钳制不变量保持：父 BYPASS 时默认子 agent 继承 BYPASS（整棵子树免审批），父非 BYPASS 时子 agent 不能提升为 BYPASS。
- Remaining risks:
  - 用户误切 bypass 后高危工具自动执行；由显式 deny 配置、`tools.command_denylist`、WorkspacePolicy 路径限制、Bash 内部正则黑名单+安全前缀白名单和文档说明缓解。
  - 现有"拒绝 bypass"测试需同步更新；`tests/agent/tools/test_browser_mode_policy.py` 手写 mode 映射若遗漏 BYPASS→bypass_default 会静默 fail_closed，改测试时同步。

## Risks / Trade-offs

- [Risk] 用户误切 bypass 后高危工具（命令执行、网络写入）自动执行，不经过审批。Mitigation: 显式 `deny_tools` 仍生效；子 agent 钳制限制权限提升；`/mode` 切换有明确反馈；文档与 `--help` 说明 bypass 语义。
- [Risk] `fail_closed` 兜底语义变化。Mitigation: `fail_closed` 保留并继续作为未知 mode fallback，仅不再作为 BYPASS 默认。
- [Risk] 放宽 bypass 影响既有"内部保留 mode"测试与 Web 拒绝场景。Mitigation: 更新 `test_run_config.py`、`test_browser_mode_policy.py`、`test_slash_command_registry.py`、`test_cli.py`、`test_server.py` 中相关断言，并新增 bypass 自动执行回归测试。
- [Risk] `_clamp_mode` 顺序若被误改会导致权限提升。Mitigation: 本次不修改 `_clamp_mode`，并通过子 agent 测试保持覆盖。

## Testing Strategy

- 单元测试：
  - `parse_agent_mode("bypass")` 返回 `AgentMode.BYPASS`；`AgentRuntimeState.set_mode("bypass")` 成功且保持新 mode。
  - `ModePolicy` 以 BYPASS 运行时，HIGH 风险工具判定为 `ALLOW`（不再 `REQUIRE_APPROVAL`/`DENY`）。
  - `deny_tools_by_mode` 在 BYPASS 下仍产生 `DENY`。
  - build mode 的高危工具仍 `REQUIRE_APPROVAL`（回归不破坏）。
- 集成测试：
  - CLI `--mode bypass` 正常启动 run。
  - 交互 `/mode bypass` 返回 `Mode changed: build -> bypass`。
  - Web `set_mode bypass` 事件返回 `new_mode=bypass`。
- 全量 `uv run pytest -q`、OpenSpec strict validate、`scripts/check_openspec_artifacts.py`。
