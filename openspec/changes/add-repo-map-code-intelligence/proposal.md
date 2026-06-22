## Why

当前 agent 依赖 Grep、Find、ListFiles 和 Read 做文本级代码定位。多文件任务中，agent 容易漏掉相关模块、接口调用点和测试入口。

本 change 先实现轻量 repo map 和 Python symbol extraction，不直接上完整 LSP，目标是服务 coding-agent 主线：更快定位任务相关文件和关键符号。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 repo map 生成能力，按 workspace policy 和 ignore rules 扫描代码文件。
- 新增 Python 符号提取，覆盖 module、class、function、method 和 import 摘要。
- 新增只读工具暴露 repo map 和符号查询。
- trace SHALL 记录 code intelligence 工具调用。

## Capabilities

### Modified Capabilities

- `code-intelligence`: 从预留能力域升级为轻量 repo map / symbol 能力。
- `coding-tools`: 增加只读代码理解工具。
- `workspace-safety`: code intelligence 扫描必须遵守 workspace policy。

## Impact

- 影响代码：
  - `agent/code_intelligence/`
  - `agent/tools/builtin/`
  - `agent/tools/__init__.py`
- 影响测试：
  - `tests/agent/code_intelligence/`
  - `tests/agent/tools/`
- 不实现完整 LSP、不做跨语言语义索引、不接外部向量库。
