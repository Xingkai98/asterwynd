## 1. 规格

- [x] 1.1 修改 code-intelligence 规格，定义 tree-sitter 多语言符号提取边界。
- [x] 1.2 修改 coding-tools 规格，定义 repo map / symbol 工具的多语言输出。
- [x] 1.3 修改 workspace-safety 规格，定义 tree-sitter 解析不得绕过 read policy。
- [x] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [x] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认语言覆盖、依赖、降级策略、测试和文档影响。

## 2. 测试

- [x] 2.1 新增每种支持语言的 tree-sitter symbol extraction fixture 测试。
- [x] 2.2 新增未注册语言降级为文件级 repo map 条目的测试。
- [x] 2.3 新增 grammar 缺失或解析失败时不影响整体 repo map 的测试。
- [x] 2.4 新增工具输出兼容性测试。
- [x] 2.5 新增解析文件大小上限或输出截断测试。

## 3. 实现

- [x] 3.1 增加 tree-sitter parser / grammar registry。
- [x] 3.2 增加 per-language query registry。
- [x] 3.3 实现 tree-sitter extractor 并接入 repo map extractor 接口。
- [x] 3.4 扩展 repo map / symbol search 输出多语言符号。
- [x] 3.5 增加 grammar 缺失、解析失败和文件过大降级处理。

## 4. 验证

- [x] 4.1 运行 code intelligence 和 tool 测试。
- [x] 4.2 运行全量测试。
- [x] 4.3 跑通一个多语言 fixture benchmark smoke。
- [x] 4.4 运行 OpenSpec strict validate。
