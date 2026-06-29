## 1. 规格

- [ ] 1.1 更新 `change-documentation` spec delta，定义 reference-agent parity artifact 的字段、状态和职责边界。
- [ ] 1.2 更新 `benchmark` spec delta，定义对标能力项与测试/benchmark evidence 的映射要求。
- [ ] 1.3 明确本 change 的范围、非目标和验收标准。
- [ ] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。

## 2. 调研与矩阵

- [ ] 2.1 建立 `docs/reference-agent-parity.md` 或等价长期文档。
- [ ] 2.2 记录参考对象分层：Codex CLI 为主对标，Claude Code、Aider、OpenCode 为辅参照。
- [ ] 2.3 建立能力项字段：domain、reference_agent、reference_source、reference_capability、asterwynd_status、asterwynd_evidence、gap_priority、follow_up_change、last_checked。
- [ ] 2.4 填写首版能力矩阵，覆盖 agent runtime、tool system、workspace safety、coding tools、code intelligence、memory/context、subagents、skills、MCP、CLI/TUI/Web、benchmark、observability。
- [ ] 2.5 对 `gap` 和重要 `partial` 项标注已有 OpenSpec change 或待新增 change。

## 3. 文档与流程

- [ ] 3.1 更新 `docs/coding-agent-roadmap.md` 中与对标策略相关的路线说明。
- [ ] 3.2 必要时更新 `docs/project-positioning.md` 或能力证明链相关文档，只记录当前 change 造成的事实变化。
- [ ] 3.3 更新 `docs/openspec-change-backlog.md`，根据首版矩阵调整后续 change 顺序或补充新 change。

## 4. 验证

- [ ] 4.1 运行 OpenSpec strict validate。
- [ ] 4.2 运行项目 OpenSpec artifact checker。
- [ ] 4.3 人工抽查首版矩阵中的 `supported` / `equivalent` 项，确认均有规格、代码、测试、benchmark 或运行证据。
- [ ] 4.4 人工抽查 `gap` / 重要 `partial` 项，确认已链接 OpenSpec change 或明确 `out_of_scope` 理由。
- [ ] 4.5 本 change 不直接修改 AgentLoop、工具协议、coding tools、workspace safety 或 benchmark runner；若后续拆出的 runtime change 涉及这些核心路径，必须跑通至少一个 benchmark smoke。

## 5. 合入后收尾

- [ ] 5.1 PR 合入后，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-establish-reference-agent-parity-matrix/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.3 运行 `openspec validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
