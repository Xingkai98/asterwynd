# Building Review — sandbox-hardening（第二批，Round 3 最终）

- 审阅范围：`git diff origin/master...HEAD`（HEAD=`525a307`，含 3f00f94 第二批实现 + b8927b6 Round 1 修复 + 525a307 Round 2 测试修复）
- base sha（merge-base with origin/master）：`dc83b4c8c63395f827f59f33ae2d3b7fb724fed4`
- 审阅方式：独立零记忆 subagent（不继承开发上下文），逐条验证 Round 2 两个测试问题修复 + 确认 Round 1 五项功能修复 + 全量跑批
- 审阅时间：2026-08-02
- Round 1 verdict：CHANGES_REQUESTED（1 中等 + 4 minor）
- Round 2 verdict：CHANGES_REQUESTED（2 个测试问题：批内 flaky 测试 + 9.5 缺确定性回归）

## Verdict: PASS

Round 2 的两个测试问题已修复且验证充分；Round 1 的 5 项功能修复在代码与测试层面全部正确。此前 flaky 的 `test_limits_apply_cgroup_when_supported` 连续 10 次跑全绿；新增的 `test_attach_skipped_when_process_already_exited` 确定性钉住 9.5 跳过路径。OpenSpec strict validate 32/32；sandbox 相关 11 个测试文件 137 passed。无未解决的中等以上问题。

## Round 2 两个测试问题修复确认

| # | Round 2 发现 | 修复 | 验证 | 结论 |
|---|---|---|---|---|
| 1 | `test_limits_apply_cgroup_when_supported` 用 `echo hi`（瞬时退出）偶发失败（`fake.attached is True` 断言时序竞态） | `tests/agent/tools/test_process_backend_cgroup.py:53` 改用 `sleep 0.2; echo hi`，命令存活期覆盖 attach 调用窗口 | `sleep 0.2` 提供 200ms 窗口，attach 在 spawn 后毫秒级调用，确定性成立；**连续 10 次单独运行全绿** | **修复正确，不再 flaky** |
| 2 | 9.5 跳过路径无确定性回归测试 | 新增 `test_attach_skipped_when_process_already_exited`（test_process_backend_cgroup.py:62-75）：构造 `returncode=0` 的 ExitedProc，直接断言 `_attach` 返回 `None` 且 `fake.attached is False` | `_attach`（process_backend.py:148-149）`proc.returncode is not None → return None`，快命令跳过 attach 不误标 degraded；纯函数级断言，无时序依赖 | **修复正确，覆盖充分** |

两个修复均为最小改动、针对根因，未引入新问题。

## Round 1 五项功能修复确认（仍正确）

| # | 修复 | 代码验证 | 回归测试 | 结论 |
|---|---|---|---|---|
| 9.1 | `sandbox.timeout_seconds` 主路径生效 | `bash.py:84-88` `timeout=timeout`（None→后端默认），`build_sandbox_from_config`（factory.py）把 `config.sandbox.timeout_seconds` 传入后端构造 → `ProcessBackend.run` `timeout = timeout or self.timeout` | `test_backend_default_timeout_used_when_none_passed`（test_bash_tool_events.py:104-118）：`ProcessBackend(timeout=0.2)` + 不传 timeout → `sleep 60` 快速 timed_out | **充分** |
| 9.2 | cgroup 遗留目录清扫 | `cgroup.py:117-136` `sweep_stale`：解析 `asterwynd-<pid>-<seq>`、`_pid_alive`（os.kill(pid,0)）跳过 live、普通 fs 子文件先 unlink 再 rmdir；`create()` 时触发 | `TestSweepStale` 4 用例（test_cgroup.py:96-125）：removes dead / keeps live / create sweeps first / 容错 | **充分** |
| 9.3 | `_setup_cgroup` catch Exception | `process_backend.py:126` `except Exception`——非 OSError 控制器失败也置 degraded | `test_non_oserror_setup_failure_still_degrades`（test_process_backend_cgroup.py:171-184）：RuntimeError → degraded=True + exit_code=0 | **充分** |
| 9.4 | Docker 超时容器残留 | `docker_backend.py:132-202` `--cidfile`（mkstemp 预留唯一路径再 unlink）+ 超时后 `_remove_orphaned_container`（`docker rm -f` 读到的 cid）；finally unlink cidfile；best-effort 吞异常 | Docker 契约测试真实 `sleep 5` + timeout=1.0 触发超时路径（断言 timed_out） | **充分**（孤儿断言偏弱为已知观察项，非阻塞） |
| 9.5 | attach 三态语义 | `process_backend.py:137-150` `_attach` 返回 True（成功）/False（失败=degrade）/None（已退出=skip）；`effective_degraded = degraded or (attached is False)` | 既有 `test_attach_failure_degrades` + 本轮新增确定性 skip 回归（Round 2 #2） | **充分** |

## 8 维度评估

- **任务逐项验证**：tasks.md 第 5/6/8/9 节全部 `[x]`，逐项对应真实代码与测试：任务 5（cgroup.py + process_backend.py + test_cgroup/test_process_backend_cgroup）、任务 6（sandbox_events.py + trace_recorder.py + loop.py save/restore + BackgroundTaskManager kill 事件 + CommandGuard.last_reason）、任务 7（benchmark smoke 于 tasks.md 7.2 记录；spec 同步 workflow-events seq 3；设计追问 seq 2）、任务 8（factory.py / main.py / web/session.py / benchmarks/agent_runner.py / SubAgentManager._resolve_sandbox / _parse_sandbox_config + test_factory_sandbox_wiring / test_config）、任务 9（9.1-9.5 回归测试均存在且通过）。Round 2 两个测试修复未单列进 tasks.md，属轻微文档观察项（见下），不构成缺陷。
- **正确性**：cgroup v2 工程细节正确（per-run 唯一目录、starttime 防 pid 复用、oom 基线对比、cleanup 幂等 + EBUSY 重试、cpuset 初始化）；timeout 透传正确；attach 三态语义正确（进程先退出 = skip 不 degrade）。测试修复后不再有已知竞态。
- **Spec 对齐**：`openspec/specs/workspace-safety/spec.md` 含 cgroup v2 资源限制 + 沙箱事件入 trace 两个 ADDED requirement + ExecutionBackend 2 个新 scenario，与实现一致；change spec delta 同步完成（workflow-events seq 1/3）。OpenSpec strict validate 32/32。
- **冗余度**：sweep_stale/cleanup 与 is_supported 职责边界清晰；sandbox_events sink 为中性 seam；run_sync 明确标注无 cgroup 的辅助方法。无重复实现。
- **测试覆盖**：回归测试充分——timeout 透传 / sweep_stale / 非 OSError degrade / attach 失败 degrade / attach 跳过（本轮新增确定性测试）/ 超时杀进程树均有；sandbox 相关 11 文件 137 passed；此前 flaky 测试 10/10 稳定。
- **安全性**：sweep_stale 不触碰 live pid（os.kill(pid,0) + rmdir EBUSY 兜底）；cleanup 仅在 starttime 匹配时 `cgroup.kill`；docker `rm -f` 仅针对本 run 的 cid；timeout 透传后默认仍受后端构造值约束，无无限运行回归。无注入/越权/信息泄露新路径。
- **可维护性**：sandbox_events contextvar sink + loop save/restore（镜像 `_active_trace_recorder` 模式）清晰；`_attach` 三态 docstring 明确；`--cidfile` 流程注释充分；测试命令改为 `sleep 0.2` 带注释说明理由。
- **CI 完整性**：全量 sandbox 相关测试绿（137 passed）；OpenSpec strict validate 32/32；`check_openspec_artifacts.py` 仅报 review manifest missing（预期，PASS 后生成）。此前威胁 CI 稳定性的 flaky 测试已消除。

## Issues

### Round 3 无阻塞 issue

Round 2 的两个问题（Issue 1 flaky、Issue 2 缺确定性回归）均已修复并验证。Round 2 的 Issue 3（Docker 孤儿无强断言）/ Issue 4（后台不应用 config timeout，设计事实）/ Issue 5（attach 窄竞态，低影响）保持为非阻塞观察项，无需在本 change 处理。

### 非阻塞观察项：Round 2 测试修复未在 tasks.md 单列

Round 2 的两个测试修复直接落在 commit `525a307`，tasks.md 未新增"审阅修复（Round 2）"节。因二者是对 tasks.md 9.5 既有修复的测试补强、且本报告完整记录，不构成功能/门禁缺陷；建议归档时在 tasks.md 9.5 后附一行 Round 2 测试修复说明（可选）。

## Test Results（Round 3）

- 指定测试批：`test_process_backend_cgroup.py` / `test_cgroup.py` / `test_bash_tool_events.py` / `test_sandbox.py`：**37 passed**（3.34s）
- flaky 复验：`test_limits_apply_cgroup_when_supported` 连续 **10/10 全绿**
- sandbox 相关全量（追加 test_sandbox_backends / test_command_guard / test_factory_sandbox_wiring / test_sandbox_events / test_loop_sandbox_events / test_config / test_background）：**137 passed**（40.73s）
- OpenSpec strict validate：**32 passed, 0 failed**
- 受保护 artifact：本轮 diff 中 `openspec/specs/workspace-safety/spec.md` 有改动，对应 workflow-events seq 1/3（current_spec_synced）已记录；其余受保护路径（known-issues / known-debt / backlog / archive）无改动。review manifest 待生成。

## 结论

Round 2 的两个测试问题已按要求修复：flaky 测试确定性化（`sleep 0.2`），9.5 跳过路径补齐确定性回归测试（直接断言 `_attach` 返回 None）。Round 1 的 5 项功能修复经复验仍全部正确。批内测试稳定（10/10）、sandbox 相关 137 项全绿、OpenSpec strict validate 通过、受保护 artifact 事件齐备。无未解决的中等以上问题，判定 **PASS**。
