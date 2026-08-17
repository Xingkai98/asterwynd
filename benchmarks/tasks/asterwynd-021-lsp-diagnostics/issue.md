# LspDiagnostics 支持显式 language 覆盖

`agent/tools/builtin/lsp.py` 的 `LspDiagnosticsTool` 通过文件后缀推断语言（`_language_for`，映射 `.py`→python、`.ts`→typescript 等）。对无后缀或未知后缀文件（如 `README`、`Makefile`、扩展名缺失的文件），推断为 `None`，工具返回「no LSP server configured for this file type」——即使调用方明确知道该文件的真实语言，也没有办法强制指定。

## Task

给 `LspDiagnosticsTool` 增加可选 `language` 参数：当后缀推断为 `None` 时，用显式 `language` 覆盖；后缀能推断时显式值不生效（后缀优先）。这样对扩展名缺失但语言明确的文件（如无后缀的 Python 脚本），调用方可以显式指定语言拿到真实诊断。

## Requirements

- 工具参数新增可选 `language`（缺省不传）
- 无后缀文件（如 `README`）默认执行 → 「no LSP server」（后缀无法推断，保持现状）
- 无后缀文件 + `language="python"` → 走 python server 拿诊断（覆盖生效）
- `.py` 文件传 `language="python"` 行为不变（后缀优先）
- 既有 LSP 工具测试不得回归
