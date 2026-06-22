## 1. 规格

- [x] 1.1 修改 code-intelligence 规格，定义 repo map 和 Python symbol 能力。
- [x] 1.2 修改 coding-tools 规格，定义新增只读工具。
- [x] 1.3 修改 workspace-safety 规格，定义扫描边界。
- [x] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。

## 2. 测试

- [x] 2.1 新增 Python symbol extraction 单元测试。
- [x] 2.2 新增 repo map 遵守 ignore rules 和 denied paths 的测试。
- [x] 2.3 新增 code intelligence 工具 schema 和执行测试。
- [x] 2.4 新增大型目录输出截断或限制测试。
- [x] 2.5 新增多语言文件级 repo map 测试，确认非 Python 文件保留文件条目但不伪造符号。

## 3. 实现

- [x] 3.1 增加 repo scanner 和可替换 extractor 接口。
- [x] 3.2 增加 Python AST symbol extractor。
- [x] 3.3 增加 repo map 输出格式。
- [x] 3.4 增加只读工具并注册到 coding tools。
- [x] 3.5 接入 WorkspacePolicy 和 ignore patterns。

## 4. 验证

- [x] 4.1 运行 code intelligence 和 tool 测试。
- [x] 4.2 运行全量测试。
- [x] 4.3 用一个 benchmark 任务做 smoke，确认工具可用。
- [x] 4.4 运行 OpenSpec strict validate。
