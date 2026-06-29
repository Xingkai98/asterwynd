## 1. 规格

- [ ] 1.1 更新 tool-system 规格，定义 capability、risk level、origin/provenance、legacy 字段兼容关系和三值权限判定。
- [ ] 1.2 更新 agent-modes 规格，定义 mode permission profile / policy matrix，明确 plan mode 不等同 read_only mode。
- [ ] 1.3 新增 agent-runtime 规格，定义 AgentLoop 在工具执行前处理 `allow` / `deny` / `require_approval` 和审批结果。
- [ ] 1.4 更新 workspace-safety 规格，明确 WorkspacePolicy 仍是执行前强制边界。
- [ ] 1.5 更新 configuration 规格，定义内置 profile、自定义 permission profile、deny override 和 fail-fast 原则。
- [ ] 1.6 新增 CLI 规格，定义 interactive 审批和 single-prompt fail closed。
- [ ] 1.7 新增 Web UI 规格，定义审批请求事件、用户决定回传和 session/run 路由。
- [ ] 1.8 新增 benchmark 规格，定义无人值守运行遇到 `require_approval` 时 fail closed。
- [ ] 1.9 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.10 开发前使用 `grill-with-docs` 审视 `design.md`，逐项确认 capability 枚举、risk level、origin、profile schema、approval handler 语义、subagent 审批策略、参数预览/脱敏规则、迁移策略和测试策略；当前文档不得直接视为最终实现方案。

## 2. 测试

- [ ] 2.1 按 TDD 新增 Tool permission metadata 单元测试，覆盖新字段和 legacy 字段推导。
- [ ] 2.2 新增 ModePolicy profile 测试，覆盖 build/read_only/plan/bypass 行为和 `allow` / `deny` / `require_approval` 三值判定。
- [ ] 2.3 新增 ToolRegistry schema filter 和 execute 前重新判权测试。
- [ ] 2.4 新增 AgentLoop approval 测试，覆盖用户批准、拒绝、超时、approval handler unavailable，并验证 tool-call 消息链合法。
- [ ] 2.5 新增内置工具 metadata 标注测试。
- [ ] 2.6 新增配置解析测试，覆盖内置 profile、自定义 profile、deny override 和非法配置 fail fast。
- [ ] 2.7 新增 CLI interactive 审批测试，覆盖批准/拒绝；新增 CLI single-prompt 测试，覆盖 require_approval fail closed。
- [ ] 2.8 新增 Web UI 审批测试，覆盖审批请求事件、用户决定回传、多 session/run 路由和取消。
- [ ] 2.9 新增 benchmark 测试，覆盖 require_approval fail closed，避免无人值守任务卡住。

## 3. 实现

- [ ] 3.1 新增 Tool permission metadata 模型，例如 ToolCapability、ToolRiskLevel、ToolOrigin 和 ToolPermission。
- [ ] 3.2 新增 PermissionDecision / PermissionDecisionType，表达 `allow` / `deny` / `require_approval` 和判定原因。
- [ ] 3.3 在 Tool 基类提供 legacy `read_only` / `dangerous` 到新 metadata 的兼容推导。
- [ ] 3.4 为内置工具显式标注 capability、risk level 和 origin。
- [ ] 3.5 将 ModePolicy 改为基于 permission profile 判权，同时保留现有 mode 默认行为或按已确认 profile 变化迁移。
- [ ] 3.6 将 deny_tools override 接入 profile 判权链路。
- [ ] 3.7 新增 ApprovalRequest、ApprovalResponse、ApprovalHandler 和 FailClosedApprovalHandler。
- [ ] 3.8 将 AgentLoop 接入 approval handler，在工具执行前处理 `require_approval`。
- [ ] 3.9 实现 CLI interactive approval handler；CLI single-prompt 使用 fail closed handler。
- [ ] 3.10 实现 Web UI approval handler 和 session/run 事件路由。
- [ ] 3.11 确认并实现 subagent approval 策略；未确认前不得默认绕过审批。
- [ ] 3.12 更新 trace/debug/display 中可用的 tool permission metadata 和 approval record。
- [ ] 3.13 更新相关文档，说明 `dangerous` 是 legacy compatibility flag，不表示工具来源。

## 4. 验证

- [ ] 4.1 运行 run_config、tool registry、factory、配置相关测试。
- [ ] 4.2 运行 AgentLoop approval 测试。
- [ ] 4.3 运行 CLI/Web/benchmark mode 和审批入口测试。
- [ ] 4.4 运行全量测试。
- [ ] 4.5 运行 OpenSpec strict validate。
- [ ] 4.6 运行项目 OpenSpec artifact checker。
- [ ] 4.7 跑通至少一个 benchmark smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-refine-tool-permission-model/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.3 运行 `openspec validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
