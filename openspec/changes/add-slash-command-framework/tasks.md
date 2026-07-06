## 1. 规格

- [ ] 1.1 更新 `cli` spec delta，定义 slash command registry 和首批命令。
- [ ] 1.2 更新 `memory-context` spec delta，定义手动 `/clear` 和 `/compact` 行为。
- [ ] 1.3 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.4 明确本 change 不包含 `/skills`、TUI 命令面板或 Web 命令入口。
- [ ] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认 command result 结构、CLI 消息状态、MemoryManager 状态、错误提示、测试策略和文档影响。
- [ ] 1.6 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [ ] 1.7 维护 `## Reference Implementation Research`；开发前补充更具体的参考实现文件和设计影响。
- [ ] 1.8 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。

## 2. 测试

- [ ] 2.1 新增 command registry 单元测试，覆盖注册、别名、未知命令、帮助文本和参数错误。
- [ ] 2.2 新增 CLI 交互测试，覆盖 `/help`、`/exit`、裸 `exit`、`/status`、`/mode`。
- [ ] 2.3 新增 CLI 交互测试，覆盖 `/clear` 清理当前会话历史。
- [ ] 2.4 新增 CLI 交互测试，覆盖 `/compact` 主动触发 MemoryManager compact。
- [ ] 2.5 新增或调整 MemoryManager 测试，覆盖手动 clear/forced compact 的可观测结果。

## 3. 实现

- [ ] 3.1 新增最小 slash command registry 和 command result 类型。
- [ ] 3.2 将 CLI 交互模式接入 command registry。
- [ ] 3.3 迁移现有 `/mode` 行为，并保留裸 `exit/quit/q` 兼容。
- [ ] 3.4 实现 `/help`、`/exit`、`/status`。
- [ ] 3.5 实现 `/clear` 和 `/compact`，确保当前 messages 与 MemoryManager 状态一致。
- [ ] 3.6 更新必要文档。

## 4. 验证

- [ ] 4.1 运行 CLI 和 command registry 相关测试。
- [ ] 4.2 运行 memory 相关测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate。
- [ ] 4.5 运行项目 OpenSpec artifact checker。
- [ ] 4.6 如实现触碰 AgentLoop 或工具协议，跑通至少一个 benchmark smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-add-slash-command-framework/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [ ] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
