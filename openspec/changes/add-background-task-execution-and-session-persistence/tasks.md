## 1. 规格

- [ ] 1.1 更新 `agent-runtime` spec delta：定义后台任务生命周期和会话持久化语义。
- [ ] 1.2 更新 `coding-tools` spec delta：定义 Bash 后台执行行为和 TaskOutput/TaskStop 工具。
- [ ] 1.3 开发前使用 `grill-with-docs` 审视 `design.md`。
- [ ] 1.4 维护 `## Impact Analysis`。
- [ ] 1.5 维护 `## Reference Implementation Research`。

- [ ] 1.7 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。

## 2. 测试

- [ ] 2.1 BackgroundTaskManager 测试：启动后台进程、检查状态、获取输出。
- [ ] 2.2 BackgroundTaskManager 测试：超时自动终止、进程清理。
- [ ] 2.3 Bash 工具测试：run_in_background=True 返回 task_id。
- [ ] 2.4 TaskOutput 测试：block 模式等待完成、非阻塞模式立即返回。
- [ ] 2.5 TaskStop 测试：终止运行中的后台任务。
- [ ] 2.6 AgentLoop 集成测试：后台任务完成后自动注入结果。
- [ ] 2.7 SessionStore 测试：保存快照、从快照恢复、消息序列化。
- [ ] 2.8 SessionStore 测试：损坏文件返回明确错误。
- [ ] 2.9 AgentLoop 集成测试：恢复后继续正常迭代。
- [ ] 2.10 CLI 测试：--resume 参数加载会话、session list/rm 子命令。

## 3. 实现

- [ ] 3.1 实现 `agent/background.py` — BackgroundTaskManager。
- [ ] 3.2 实现 `agent/session.py` — SessionStore + SessionSnapshot。
- [ ] 3.3 扩展 `agent/tools/builtin/bash.py` — run_in_background 参数。
- [ ] 3.4 实现 `agent/tools/builtin/tasks.py` — TaskOutput / TaskStop。
- [ ] 3.5 在 `factory.py` 注册 TaskOutput / TaskStop。
- [ ] 3.6 AgentLoop：迭代开始时注入已完成后台任务结果。
- [ ] 3.7 AgentLoop：迭代结束时自动保存 session。
- [ ] 3.8 AgentLoop：退出时清理所有后台进程。
- [ ] 3.9 CLI：`--resume` 参数 + `session list/rm` 子命令。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行 artifact checker。
- [ ] 4.5 手动验证：后台执行 sleep 10 命令并在中途用 TaskOutput 检查。
- [ ] 4.6 手动验证：保存 session 后用 --resume 恢复。

- [ ] 4.5 跑通至少一个 benchmark smoke，验证变更不影响 agent 执行正确性。

## 5. PR 收尾

- [ ] 5.1 归档到 `openspec/changes/archive/YYYY-MM-DD-add-background-task-execution-and-session-persistence/`。
- [ ] 5.2 从 backlog 移除。
- [ ] 5.3 确认 Impact Analysis 无残留未知项。
- [ ] 5.4 运行全量校验。
