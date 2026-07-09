## 1. 规格

- [ ] 1.1 更新 `memory-context` spec delta：定义跨 session 持久记忆模型、存储格式、注入语义。
- [ ] 1.2 更新 `tool-system` spec delta：定义 SaveMemory / RecallMemory 工具行为。
- [ ] 1.3 开发前使用 `grill-with-docs` 审视 `design.md`。
- [ ] 1.4 维护 `## Impact Analysis`。
- [ ] 1.5 维护 `## Reference Implementation Research`。

- [ ] 1.7 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。

## 2. 测试

- [ ] 2.1 PersistentMemory 单元测试：写入新记忆文件、更新已有记忆、读取 MEMORY.md 索引。
- [ ] 2.2 PersistentMemory 单元测试：MEMORY.md 不存在时返回空上下文。
- [ ] 2.3 SaveMemory 工具测试：创建 user/feedback/project/reference 四类记忆。
- [ ] 2.4 RecallMemory 工具测试：按 type 过滤、无 type 返回全部。
- [ ] 2.5 AgentLoop 集成测试：存在记忆时注入 `## Project Memory` 段。
- [ ] 2.6 AgentLoop 集成测试：不存在记忆时不注入。
- [ ] 2.7 文件格式兼容性测试：生成的 `.md` 文件有合法的 YAML frontmatter。

## 3. 实现

- [ ] 3.1 实现 `agent/memory/persistent.py` —— PersistentMemory 类。
- [ ] 3.2 实现 `agent/tools/builtin/memory.py` —— SaveMemory / RecallMemory 工具。
- [ ] 3.3 在 `factory.py` 注册 memory 工具到所有 mode。
- [ ] 3.4 在 AgentLoop `_messages_with_run_context` 中注入 persistent memory 上下文。
- [ ] 3.5 更新 AGENTS.md / CLAUDE.md 中的 auto-memory 指令（参考 Claude Code）。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行 artifact checker。
- [ ] 4.5 手动验证：两个 session 之间记忆持久化。

- [ ] 4.5 跑通至少一个 benchmark smoke，验证变更不影响 agent 执行正确性。

## 5. PR 收尾

- [ ] 5.1 归档到 `openspec/changes/archive/YYYY-MM-DD-add-persistent-cross-session-memory/`。
- [ ] 5.2 从 backlog 移除。
- [ ] 5.3 确认 Impact Analysis 无残留未知项。
- [ ] 5.4 运行全量校验。
