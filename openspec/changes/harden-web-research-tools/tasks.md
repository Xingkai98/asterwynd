## 1. 规格

- [x] 1.1 修改 research-tools 规格，定义 WebSearch / WebFetch 的失败和结果结构语义。
- [x] 1.2 开发前补充具体失败案例和 provider fixture。
- [x] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md` 和 `diagnosis.md`，逐项确认 provider 边界、错误语义、fixture 和测试策略。

## 2. 测试

- [x] 2.1 新增 WebSearch fake provider / fixture 测试。
- [x] 2.2 新增 WebFetch 错误、截断和内容类型测试。

## 3. 实现

- [x] 3.1 整理 WebSearch 结果结构和错误信息。
- [x] 3.2 整理 WebFetch 错误信息和截断语义。
- [x] 3.3 拆出 WebSearch 轻量 provider adapter 边界，当前仅实现 DuckDuckGo HTML provider，不实现 registry、多 provider fallback、优先级或配置。

## 4. 验证

- [x] 4.1 运行 research tools 相关测试。
- [x] 4.2 运行 OpenSpec strict validate。
- [x] 4.3 跑通至少一个 benchmark smoke。
