## 1. 规格

- [ ] 1.1 更新受影响 capability 的 spec delta。
- [ ] 1.2 明确本 change 的范围、非目标和验收标准。
- [ ] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案；不得把 agent 自己的推荐答案当作用户确认。
- [ ] 1.4 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [ ] 1.5 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。

## 2. 测试

- [ ] 2.1 按 TDD 先新增或调整相关单元测试。
- [ ] 2.2 覆盖跨模块行为的集成测试。
- [ ] 2.3 覆盖入口层测试，例如 CLI、Web、benchmark 或未来 TUI。
- [ ] 2.4 覆盖负向路径和回归场景。

## 3. 实现

- [ ] 3.1 实现最小可验证路径。
- [ ] 3.2 接入相关入口和 artifact 记录。
- [ ] 3.3 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现。
- [ ] 3.4 更新必要文档。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行项目 OpenSpec artifact checker。
- [ ] 4.5 确认 baseline CI 命令可本地通过：`uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`。
- [ ] 4.6 如果涉及 AgentLoop、工具协议、coding tools、workspace safety、benchmark runner 或其他 coding-agent 核心路径，跑通至少一个 benchmark smoke。
- [ ] 4.7 如果涉及 Web，运行 Web session/server 测试；必要时运行浏览器 smoke。
- [ ] 4.8 如果涉及 TUI、browser/computer use、外部服务或其他人工交互入口，运行对应 smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
