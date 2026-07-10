## 1. 规格

- [x] 1.1 更新 `agent-runtime` spec delta：定义后台任务生命周期和会话持久化语义。
- [x] 1.2 更新 `coding-tools` spec delta：定义 Bash 后台执行行为和 TaskOutput/TaskStop 工具。
- [x] 1.3 开发前使用 `grill-with-docs` 审视 `design.md`（2026-07-10 完成，两轮：grill + Codex review，结论写入 design.md Pre-Implementation Review）。
- [x] 1.4 维护 `## Impact Analysis`。
- [x] 1.5 维护 `## Reference Implementation Research`。
- [x] 1.7 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。

## 2. 测试

- [x] 2.1 BackgroundTaskManager 测试：启动后台进程、检查状态、获取输出（真实子进程 sleep 0.5 + echo）。
- [x] 2.2 BackgroundTaskManager 测试：超时自动终止、TaskStop 终止、进程清理、finally 覆盖。
- [x] 2.3 Bash 工具测试：run_in_background=True 返回 task_id、后台命令仍过安全门、timeout 为秒（float）。
- [x] 2.4 TaskOutput 测试：block 模式等待完成、非阻塞模式立即返回、output_truncated 标志。
- [x] 2.5 TaskStop 测试：终止运行中的后台任务、状态变为 killed。
- [x] 2.6 AgentLoop 集成测试：后台任务完成后注入 role=user 观测消息（真实子进程）、check_completed() 去重。
- [x] 2.7 SessionStore 测试：保存快照、从快照恢复、消息序列化、全 snapshot hash 去重。
- [x] 2.8 SessionStore 测试：损坏文件返回明确错误、schema_version 兼容（major/minor）、原子写入（tmp+rename）、配对文件缺失、runtime_fingerprint mismatch warning。
- [x] 2.9 AgentLoop 集成测试：恢复时重建 system prompt、过滤旧 system 消息、恢复后继续正常迭代。
- [x] 2.10 CLI 测试：--resume 参数、session list（表格/JSON）/resume/rm（确认/-f）子命令。
- [x] 2.11 SandboxExecutor 测试：run_background() 返回 BackgroundProcessHandle、read_chunk() 读输出。

## 3. 实现

- [ ] 3.0 前置：SandboxExecutor.run_background() + BackgroundProcessHandle 协议（含 read_chunk、poll、terminate、kill、wait）。
- [ ] 3.0b 前置：PlanItem.from_dict() 静态方法（含基础校验）。
- [ ] 3.0c 前置：SkillRuntime.active_skill_names public property。
- [ ] 3.1 实现 `agent/background.py` — BackgroundTaskManager。
  - TaskEntry: 状态 running/completed/failed/timeout/killed/orphaned + output_truncated + reported 标志
  - MAX_OUTPUT_BYTES=64KB 可配置
  - register() 创建 asyncio.create_task(_monitor()) 后台监控协程
  - monitor 协程：drain pipe（read_chunk）、超时检测、状态更新
  - check_completed() 返回新完成任务列表并标记 reported=True
  - cleanup(): SIGTERM → 等 cleanup_timeout → SIGKILL
- [ ] 3.2 实现 `agent/session.py` — SessionStore + SessionSnapshot。
  - SessionSnapshot 含 schema_version + runtime_fingerprint
  - 保存：temp file + os.replace() 原子写入
  - 加载：配对文件检测 + JSON 损坏报告 + semver 兼容策略
  - 去重：整个 snapshot dict hash（覆盖 messages/mode/todos/skills/iteration）
  - 恢复消息过滤：只保留 user/assistant/tool，去除旧 system 消息
- [ ] 3.3 扩展 `agent/tools/builtin/bash.py` — run_in_background 参数（通过 run_in_background_cb 回调），timeout 统一为 float 秒。
- [ ] 3.4 实现 `agent/tools/builtin/tasks.py` — TaskOutput / TaskStop（通过 get_task_cb / stop_task_cb 回调），TaskOutput timeout 为 float 秒。
- [ ] 3.5 在 `factory.py` 注册 TaskOutput / TaskStop。
- [ ] 3.6 AgentLoop：迭代开始时 check_completed() 拉取完成任务 → 构建 role=user 观测消息注入 messages。
- [ ] 3.7 AgentLoop：`run()` 方法中 `_run()` 返回后保存 session，全 snapshot hash 去重。
- [ ] 3.8 AgentLoop：_run() try/finally cleanup() 清理所有后台进程（cleanup_timeout 可配置）。
- [x] 3.9 CLI：`--resume` 参数 + `session list/resume/rm` 子命令（表格/--json、rm 确认/--force）。
- [x] 3.10 AgentLoop._run() 新增 resume_snapshot 参数：恢复时重建 system prompt、过滤旧 system 消息、runtime_fingerprint 对比 warning。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试（82 tests pass: test_loop, test_session, test_background, test_sandbox, test_tasks）。
- [x] 4.2 运行全量测试 `uv run pytest -q`（812 passed, 7 skipped, 9 pre-existing infra failures）。
- [x] 4.3 运行 OpenSpec strict validate（changes: 4 passed, specs: 20 passed）。
- [ ] 4.4 运行 artifact checker（项目中暂无 artifact checker）。
- [ ] 4.5 手动验证：后台执行 sleep 10 命令并在中途用 TaskOutput 检查。
- [ ] 4.6 手动验证：保存 session 后用 --resume 恢复。
- [ ] 4.7 跑通至少一个 benchmark smoke，验证变更不影响 agent 执行正确性。

## 5. PR 收尾

- [ ] 5.1 归档到 `openspec/changes/archive/YYYY-MM-DD-add-background-task-execution-and-session-persistence/`。
- [ ] 5.2 从 backlog 移除。
- [ ] 5.3 确认 Impact Analysis 无残留未知项。
- [ ] 5.4 运行全量校验。

## 已知 Debt（不在本次实现范围）

- PlanItem.from_dict() 严格校验（本次只做基础字段校验）
- `.asterwynd/` gitignore 策略
