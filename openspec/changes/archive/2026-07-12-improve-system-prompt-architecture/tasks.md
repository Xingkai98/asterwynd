## 1. 规格

- [ ] 1.1 修改 `agent-runtime` spec delta，定义统一 system prompt builder。
- [ ] 1.2 修改 `cli` 和 `web-ui` spec delta，定义入口复用统一 prompt。
- [ ] 1.3 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认段落顺序、动态变量和角色合成方式。
- [ ] 1.5 开发前补实 `## Reference Implementation Research`。

## 2. 测试

- [ ] 2.1 新增 prompt builder 单元测试。
- [ ] 2.2 新增 CLI/Web system prompt 一致性测试。
- [ ] 2.3 新增 role prompt 合成测试。
- [ ] 2.4 新增关键约束存在性和重复注入回归测试。

## 3. 实现

- [ ] 3.1 新增统一 prompt builder。
- [ ] 3.2 迁移 CLI prompt 构造路径。
- [ ] 3.3 迁移 Web session prompt 构造路径。
- [ ] 3.4 迁移 role registry 的基础约束合成。

## 4. 验证

- [ ] 4.1 运行 prompt、CLI、Web session 相关测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行项目 OpenSpec artifact checker。
- [ ] 4.5 跑通 CLI 和 Web smoke。
- [ ] 4.6 跑通至少一个 AgentLoop benchmark smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前归档本 change。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change。
- [ ] 5.3 确认 Impact Analysis 和 Reference Implementation Research 已更新为最终结论。
