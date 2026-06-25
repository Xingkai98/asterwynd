## 1. 规格

- [ ] 1.1 更新 tool-system 规格，定义 capability、risk level、origin/provenance 和 legacy 字段兼容关系。
- [ ] 1.2 更新 agent-modes 规格，定义 mode permission profile / policy matrix，明确 plan mode 不等同 read_only mode。
- [ ] 1.3 更新 workspace-safety 规格，明确 WorkspacePolicy 仍是执行前强制边界。
- [ ] 1.4 更新 configuration 规格，定义内置 profile、deny override 和后续自定义 matrix 的 fail-fast 原则。
- [ ] 1.5 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.6 开发前使用 `grill-with-docs` 审视 `design.md`，逐项确认 capability 枚举、risk level、origin、profile 语义、配置范围、迁移策略和测试策略。

## 2. 测试

- [ ] 2.1 按 TDD 新增 Tool permission metadata 单元测试，覆盖新字段和 legacy 字段推导。
- [ ] 2.2 新增 ModePolicy profile 测试，覆盖 build/read_only/plan/bypass 行为。
- [ ] 2.3 新增 ToolRegistry schema filter 和 execute 前重新判权测试。
- [ ] 2.4 新增内置工具 metadata 标注测试。
- [ ] 2.5 新增配置解析测试，覆盖内置 profile、deny override 和非法配置 fail fast。
- [ ] 2.6 新增 CLI/Web/benchmark mode 入口回归测试，确认默认行为不变。

## 3. 实现

- [ ] 3.1 新增 Tool permission metadata 模型，例如 ToolCapability、ToolRiskLevel、ToolOrigin 和 ToolPermission。
- [ ] 3.2 在 Tool 基类提供 legacy `read_only` / `dangerous` 到新 metadata 的兼容推导。
- [ ] 3.3 为内置工具显式标注 capability、risk level 和 origin。
- [ ] 3.4 将 ModePolicy 改为基于 permission profile 判权，同时保留现有 mode 默认行为。
- [ ] 3.5 将 deny_tools override 接入 profile 判权链路。
- [ ] 3.6 更新 trace/debug/display 中可用的 tool permission metadata。
- [ ] 3.7 更新相关文档，说明 `dangerous` 是 legacy compatibility flag，不表示工具来源。

## 4. 验证

- [ ] 4.1 运行 run_config、tool registry、factory、配置相关测试。
- [ ] 4.2 运行 CLI/Web/benchmark mode 入口测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate。
- [ ] 4.5 运行项目 OpenSpec artifact checker。
- [ ] 4.6 跑通至少一个 benchmark smoke。

## 5. 合入后收尾

- [ ] 5.1 PR 合入后，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-refine-tool-permission-model/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.3 运行 `openspec validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
