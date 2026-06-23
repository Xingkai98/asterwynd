## Why

当前 WebSearch / WebFetch 已作为 read-only 研究工具存在，但规格只覆盖最小行为。后续 coding agent 需要更稳定的联网研究能力，包括搜索失败诊断、可测试的 provider 边界、结果结构化和更清晰的错误反馈。

历史讨论中只找到一条关于 WebSearch hardening 的流程备注，没有 active OpenSpec change；因此需要补一个正式 change 承接后续细化。

## Change Type

- primary: feature
- secondary: [research]

## What Changes

- 明确 WebSearch 搜索失败、无结果、解析失败和 provider 异常的行为。
- 改善 WebSearch 返回结果结构，保留标题、URL、摘要等可展示字段。
- 明确 WebFetch 内容类型、截断、错误和重定向边界。
- 为联网研究工具建立 fake provider / fixture 测试策略，避免测试依赖真实网络。

## Capabilities

### Modified Capabilities

- `research-tools`: 增强 WebSearch / WebFetch 可靠性和可诊断性。

## Impact

- 影响代码：
  - `agent/tools/builtin/web_search.py`
  - `agent/tools/builtin/web_fetch.py`
  - `agent/tools/factory.py`
- 影响测试：
  - `tests/agent/tools/`
- 后续需要补充具体失败案例和 provider 行为样本。
