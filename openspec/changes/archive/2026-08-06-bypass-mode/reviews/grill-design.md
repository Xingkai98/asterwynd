# Grill: bypass-mode 设计追问

## Reviewer

- run id: grill-subagent-bypass-mode-design-review
- 时间: 2026-08-06
- 角色: 独立零记忆设计评审（issue #95 机械门禁），挑战而非确认设计。对照实际代码逐项验证 design.md 的主张，不继承任何开发上下文。

## Confirmed Decisions

- **决策**: `parse_agent_mode` 单点放开即可统一解锁全部用户入口，design Decision 2 成立；理由: 所有入口（CLI `--mode`、交互 `/mode`、Web `set_mode`、`ASTERWYND_MODE`、`default_mode` 配置、子 agent mode 请求）最终都汇聚到 `parse_agent_mode`（`agent/run_config.py:25-38`；调用点 `agent/main.py:241`、`agent/config.py:413/439/472/486`、`web/session.py:231`、`agent/subagent/manager.py:183`），放开解析器后无遗漏入口；来源: grill-subagent-bypass-mode-design-review
- **决策**: 新增 `bypass_default` profile（ALL capabilities + `auto_approve_max_risk=HIGH`）能使任意风险工具判定 `ALLOW`，design Decision 1 成立；理由: `decide_tool` 判定链（`agent/run_config.py:101-175`）在 capability 检查通过后，`risk_lte(risk, auto_approve_max_risk)` 即返回 `ALLOW`（144-154），而风险档只有 LOW/MEDIUM/HIGH 三档（`agent/tool_permissions.py:18-21`），HIGH ≤ HIGH 恒成立；`approval_required_max_risk=HIGH` 并非冗余，而是 `PermissionProfile.__post_init__`（`agent/tool_permissions.py:60-65`）强制 `approval_required >= auto_approve` 的唯一合法取值；来源: grill-subagent-bypass-mode-design-review
- **决策**: `deny_tools` 与 `allowed_modes` 在 `decide_tool` 的 allow 分支之前生效，design Decision 4 成立；理由: 判定顺序为 `allowed_modes` 排除（`agent/run_config.py:104-112`）→ `deny_tools_by_mode` 排除（113-120）→ profile.denied_tools 排除（121-128）→ capability 检查（129-143）→ auto_approve ALLOW（144-154），bypass 只放行"审批"、不放行显式禁止；来源: grill-subagent-bypass-mode-design-review
- **决策**: BYPASS 默认 profile 映射两处同步修改（`agent/run_config.py:206` 与 `agent/config.py:300`）且用户覆盖路径不受影响，design Decision 3 成立；理由: 这两处是 BYPASS 默认 profile 的唯二来源；`config.py:302-303` 的 `mode_config(mode).permission_profile or defaults[mode]` 让 `modes.bypass.permission_profile` 用户自定义仍优先；`_default_modes()`（`agent/config.py:1393-1394`）返回全部 4 个 mode 的 `ModeConfig()`，BYPASS 始终在映射内；来源: grill-subagent-bypass-mode-design-review
- **决策**: `_clamp_mode` 子 agent 钳制语义在 bypass 用户可选后依然成立，design Decision 5 成立；理由: `agent/subagent/manager.py:697-707` 中 BYPASS order=2（最宽松），父 BYPASS 时子请求 BYPASS 因 `2 > 2` 不成立而放行，父 BUILD 时子请求 BYPASS 被钳回 BUILD（`2 > 1`）；子 agent 不能比父更宽松；来源: grill-subagent-bypass-mode-design-review

## Open Questions

- **Q1**: 核心语义确认——bypass 模式下 HIGH 风险工具（Bash 命令执行、Write 写盘、网络写/外部副作用）全部自动执行、不经过审批，安全网仅为 `modes.bypass.deny_tools`、`tools.command_denylist`、WorkspacePolicy 路径限制和 Bash 工具内部命令黑名单/白名单。是否确认按此实现？；推荐：确认。这是需求原文（"所有命令自动执行、不经过审批"）的直接落地，需用户明确拍板
- **Q2**: 子 agent 继承——bypass 父 agent 的默认子 agent（`create_subagent(mode=None)` 继承父 mode）会以 bypass 运行，整棵子树免审批。是否接受该行为并写入文档说明？；推荐：接受。符合"子 agent 不能比父更宽松"的既有钳制不变量（`agent/subagent/manager.py:182-185, 697-707`），无需改代码，但应在 docs 中明确
- **Q3**: 文档影响范围——需更新 `docs/development-guide.md:52,219` 的 `/mode` 模式列表、`docs/architecture.md:90` 的 Web 模式切换列表、`README.md:112` 的"CLI 单轮和 benchmark 等无人值守入口 fail closed"表述（需限定为"默认 build 下；显式 bypass 时自动放行"），并同步 `README_EN.md` 英文翻译。是否按此范围执行？；推荐：按此执行（符合 AGENTS.md 文档影响检查；此为事实变化，非无边界全量改文档）
- **Q4**: `allow_bypass` 参数去留——放开解析器后该参数成为死参数（当前唯一调用是 `tests/agent/test_run_config.py:57`）。是删除参数还是保留为 no-op？；推荐：实现时删除参数并更新对应测试（更干净）；保留 no-op 亦可接受，属于实现细节，不改变外部行为

## 风险

- [Must-fix] design Decision 6 只写"`agent/main.py` `--mode` help"一处，但实际有 4 处 `--mode` help 字符串（`agent/main.py:353` run、`:386` 交互、`:666` web、`:711` benchmark），以及 `agent/commands/registry.py:416,418` 的 `/mode` usage + argument_hint 均需加入 bypass；遗漏会导致"部分入口文案不一致"。
- [Must-fix] `parse_agent_mode` 的 unsupported-mode 错误消息 `supported` 列表（`agent/run_config.py:33`）在放开后需加入 "bypass"，否则未知 mode 报错文案不列出已支持的 bypass。
- [Must-fix/规格对齐] delta 规格 `openspec/changes/bypass-mode/specs/agent-modes/spec.md` 场景"bypass mode 自动放行所有风险工具"写"所有已注册且未被显式 deny 的工具 SHALL 判定为 allow"，但 plan 工具 `UpdatePlan`/`ExitPlanMode` 的 `allowed_modes=("plan",)`（`agent/tools/builtin/plan.py:49`）在 bypass 下会被 DENY（`agent/run_config.py:105`）。ADDED requirement 文本已包含"allowed_modes 约束仍然生效"，但场景措辞建议补"未被显式 deny 且未被 allowed_modes 排除"，避免规格与实现被 reviewer 判定不一致。
- [安全] bypass 自动放行 HIGH 风险工具（Bash/Write/网络写），缓解层包括 `modes.bypass.deny_tools`、`tools.command_denylist`、WorkspacePolicy 路径限制、Bash 工具内部正则黑名单+安全前缀白名单（`README.md:112` 描述的既有层）。design Risk 段落已列前几项，建议补充 Bash 内部黑名单这一层以完整呈现缓解面。
- [边界] `bypass_default` 的 `approval_required_max_risk=HIGH` 在现有三档风险下不可达；若未来新增高于 HIGH 的风险档，该 profile 会退化到 REQUIRE_APPROVAL 而非 DENY。当前可接受，建议在 profile 定义处加注释说明意图。
- [测试陷阱] `ModePolicy.permission_profile` 对"不在传入映射中的 mode"回退 `fail_closed`（`agent/run_config.py:179-186`）。生产调用方均传完整 4-mode 映射（`agent/main.py:266`、`web/session.py:262`、`agent/subagent/manager.py:516`、`benchmarks/agent_runner.py:303`），无生产风险；但 `tests/agent/tools/test_browser_mode_policy.py:24-29` 手写映射，若更新时遗漏 BYPASS→bypass_default 会静默 fail_closed，需在改测试时同步。
- [门禁] 本 change 是非 docs + 有 spec delta + tasks 会全勾选，必须满足 building-review 门禁（`scripts/check_openspec_artifacts.py`：tasks 全勾选时要求 `reviews/building-review.md` + manifest PASS）。design Testing Strategy 未显式提该门禁，但 tasks 4.5 已列，无死锁。

## User Confirmation

> 主 agent 停轮逐项确认（grill-confirmation-gate）。用户对 Q1-Q4 的答复如下，全部实质确认。

- **Q1**: 用户答复：确认全部放行——bypass 下 HIGH 风险工具（Bash 命令执行、Write 写盘、网络写/外部副作用）全部自动执行不审批，安全网为 modes.bypass.deny_tools、tools.command_denylist、WorkspacePolicy 路径限制和 Bash 工具内部命令黑名单；确认时间: 2026-08-06
- **Q2**: 用户答复：接受继承——bypass 父 agent 的默认子 agent（mode=None 继承父 mode）以 bypass 运行，整棵子树免审批，符合"子 agent 不能比父更宽松"钳制不变量，并写入文档说明；确认时间: 2026-08-06
- **Q3**: 用户答复：按推荐范围执行——更新 docs/development-guide.md 的 /mode 列表、docs/architecture.md 的 Web 模式切换列表、README.md"无人值守入口 fail closed"表述并同步 README_EN.md 翻译；确认时间: 2026-08-06
- **Q4**: 用户答复：删除参数——移除 parse_agent_mode 的 allow_bypass 死参数并更新对应测试；确认时间: 2026-08-06
