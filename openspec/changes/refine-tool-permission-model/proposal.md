## Why

当前 Tool 权限模型只有 `read_only`、`dangerous` 和 `allowed_modes`。这个模型能支撑早期 read-only/build/plan 边界，但随着 MCP、browser/computer use、自定义扩展、subagent runtime 和未来可实验 plan mode 增加，两个 boolean 开始承载过多语义：

- `dangerous` 同时像风险等级、隔离需求和高副作用标记。
- 外部来源的 tool 容易被误解为天然 dangerous，但来源和风险是两条不同概念轴。
- `plan` mode 当前被实现为 read-only 同义策略，难以表达“允许低风险实验，但仍不允许提交写入”的计划阶段。
- 用户自定义 mode 只能通过 deny list 收紧，不能用清晰的能力矩阵表达允许范围。

本 change 目标是重构工具权限模型，让 Tool metadata、mode policy、workspace safety 和外部工具接入有可扩展的共同语言。

当前 change 是方向性设计和规格草案，不是可直接实现的最终方案。真正开始开发前，必须继续用 `grill-with-docs` 充分讨论 capability 枚举、risk 分级、origin 取值、profile 配置开放范围、默认行为兼容策略和测试矩阵。

## Change Type

- primary: feature
- secondary: [refactor]

## What Changes

- 引入 Tool capability、risk level 和 origin/provenance 三条独立元数据轴。
- Agent mode SHALL 通过 permission profile / policy matrix 判定工具可见性和执行权限，而不是硬编码 `read_only and not dangerous`。
- Permission profile SHALL 综合 capability、risk level、origin 和 override 判定权限；后续用户 MAY 通过配置组合这些维度形成扩展 profile，但初始实现是否开放完整自定义 matrix 仍需开发前确认。
- 保留兼容层，把现有 `read_only` / `dangerous` 映射到新模型，分阶段迁移内置工具。
- `dangerous` 语义 SHALL 收敛为 legacy compatibility flag；新实现应优先使用 capability + risk level。
- `plan` mode SHALL 不再在概念上等同 `read_only`，而是绑定默认保守 permission profile；是否允许实验型工具由 profile 明确表达。

## Capabilities

### Modified Capabilities

- `tool-system`: 工具权限元数据从两个 boolean 演进为 capability / risk / origin 模型。
- `agent-modes`: mode policy 从硬编码规则演进为 profile / matrix。
- `workspace-safety`: workspace policy 与 tool capability 的关系需要明确。
- `configuration`: 后续支持 mode profile 和 tool permission override 的配置结构。

## Impact

- 影响代码：
  - `agent/tools/base.py`
  - `agent/tools/registry.py`
  - `agent/run_config.py`
  - `agent/tools/factory.py`
  - 内置工具 metadata
  - 配置解析路径
- 影响测试：
  - `tests/agent/test_run_config.py`
  - `tests/agent/tools/test_registry.py`
  - `tests/agent/tools/test_factory.py`
  - CLI/Web/benchmark mode 入口测试
- 影响文档：
  - `CONTEXT.md`
  - `openspec/specs/tool-system/spec.md`
  - `openspec/specs/agent-modes/spec.md`
  - `docs/architecture.md`
  - `docs/testing-guide.md`
