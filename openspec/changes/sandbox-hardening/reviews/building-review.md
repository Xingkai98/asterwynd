# Building Review — sandbox-hardening（第二批）

- 审阅范围：`git diff origin/master...HEAD`（HEAD=`3f00f94`），第二批 = tasks.md 第 5/6/8 节 + 第 7 节收尾
- 审阅方式：独立零记忆 subagent（不继承开发上下文），逐文件读代码 + 跑测试
- 审阅时间：2026-08-02

## Verdict: CHANGES_REQUESTED

第二批所有 tasks 的 `[x]` 均有真实实现、测试通过（1511 passed）、OpenSpec validate 通过；但存在 1 个需修复的中等问题（`sandbox.timeout_seconds` 配置在前后台主路径上不生效，违背本 change 自身"配置了不得静默失效"的设计哲学）和若干 minor 观察项。修复后即可进入 PASS。

## Tasks Verification（第二批逐条）

| Task | 结论 | 证据 |
|---|---|---|
| 5.1 cgroup v2 限制 | ✅ 真实实现 | `agent/tools/sandbox/cgroup.py`：`CgroupController` Protocol + `CgroupV2Controller`；per-run 唯一目录（`asterwynd-<pid>-<seq>`，cgroup.py:127）；`memory.max`/`memory.swap.max=0`（cgroup.py:195-202）；`cpu.max`（cgroup.py:206）；cpuset 复制（cgroup.py:210-216）；starttime pid 复用防护（cgroup.py:166-174 + `_pid_starttime` cgroup.py:58）；oom 基线对比（cgroup.py:156-157 + `_read_oom_kills` cgroup.py:218）；cleanup 幂等（cgroup.py:159-189，rmdir 重试 + 普通 fs 子文件清理）。ProcessBackend 新增 `memory_mb/cpus/controller_factory/cgroup_supported`（process_backend.py:71-94）；`_BACKEND_KWARGS["process"]` 增加 memory_mb/cpus（sandbox/factory.py:22） |
| 5.2 超限 kill + 记录 | ✅ 真实实现 | OOM 检测 `controller.oom_killed()` → `SandboxResult.oom_killed=True` + `oom` 事件（reason=memory_limit，process_backend.py:175-182）；`SandboxResult` 新增 `oom_killed/degraded` 默认字段（base.py:106-107） |
| 5.3 降级 | ✅ 真实实现 | `_setup_cgroup` degrade-first（process_backend.py:108-128）：`needs_limits` 但 cgroup 不可用/`create()` 失败 → `degraded=True` + `degraded` 事件（每实例一次 `_degraded_emitted` 限流，process_backend.py:130-133）；attach 失败也计 degraded（process_backend.py:170） |
| 5.4 cgroup 单测 | ✅ 真实实现 | `tests/agent/tools/test_cgroup.py`（fake fs：memory.max/swap/cpu.max/cpuset 复制/唯一名/oom 基线/cleanup 幂等，131 行）；`tests/agent/tools/test_process_backend_cgroup.py`（注入 fake controller + 降级路径 + attach 失败降级 + 超时仍 kill，147 行） |
| 5.5 超时杀进程树 | ✅ 真实实现 | `start_new_session=True`（process_backend.py:164）+ `_kill_process_tree` `os.killpg(pid, SIGKILL)`（process_backend.py:40-54）；回归测试 `test_sandbox_timeout_kills_process_tree`（tests/agent/tools/test_sandbox.py:41-50，超时 0.5s 断言 <5s 返回） |
| 6.1 事件入 trace | ✅ 真实实现 | `agent/sandbox_events.py`：contextvar sink + `emit_sandbox_event` + `tool_call_id` 自动附加（sandbox_events.py:73-77）+ command 截断 300 字符折叠换行（sandbox_events.py:56-61）；`TraceRecorder.record_sandbox_event` + `TraceRecorderSandboxSink`（trace_recorder.py:145-152, 230-243）；`CommandGuard.last_reason`（command_guard.py:126，8 类 reason：denylist/pipe_to_shell/protected_redirect/rm_target_escape/mv_cp_dest/chmod_bits/timeout_range/curl_exfil） |
| 6.2 #78 schema 对齐 | ✅ 真实实现 | `sandbox` step type 新增，`timestamp` 仍在 TraceStep 字段、data 负载干净（trace_recorder.py:150-152 docstring + 测试 test_trace_recorder_sandbox_sink_records_sandbox_step 断言 data 无 timestamp）；`schema_version` 保持 `"1.1"`（trace_recorder.py:216） |
| 6.3 事件产生点接线 | ✅ 真实实现 | BashTool：workspace_policy 拒绝 → `denied` reason=workspace_policy（bash.py:70）；guard 拒绝 → `denied` reason=`command_guard:<last_reason>`（bash.py:73-76）。ProcessBackend 超时 → `kill`（process_backend.py:194）；DockerBackend 超时 → `kill`（docker_backend.py:140）。`BackgroundTaskManager._monitor` 超时 → `kill`（background.py:141-143）、stop → `kill` reason=user_stop（background.py:104-106）、cleanup → `kill` reason=cleanup（background.py:118-120）。`loop.run` save/restore sink（loop.py:472-499） |
| 7.1 设计审阅任务 | ✅ 证据充分 | design.md「Batch 2 设计定稿」+ workflow-events.jsonl seq 2（3 个独立审阅 agent，blocker/major 覆盖清单 22 项） |
| 7.2 benchmark smoke | ✅ 证据存在 | `/tmp/smoke/2026-08-02T12-26-37/`：run.json（task_count=34）+ summary.md；fake agent 任务失败为预期，无基础设施级错误（仅 swebench docker_unavailable） |
| 7.3 规格同步 | ✅ 真实实现 | `openspec/specs/workspace-safety/spec.md` 已含 cgroup v2 资源限制（237-253 行）与沙箱事件入 trace（255-269 行）两个 ADDED requirement + ExecutionBackend 2 个新 scenario（193-203 行）；workflow-events.jsonl seq 3 记录 |
| 8.1 registry/tools 透传 | ✅ 真实实现 | `build_default_tool_registry`/`build_coding_tool_registry`/`get_default_tools`/`get_coding_tools` 增 `sandbox` 参数并透传 BashTool（agent/tools/factory.py:177, 222, 277, 369）；`_apply_sandbox_to_tools` 回填预构建 BashTool（factory.py:145-159） |
| 8.2 main.py 接线 | ✅ 真实实现 | `build_sandbox_from_config` 提前构建 + fail-fast（factory.py:35-53, main.py:248-252）；传给 registry/BackgroundTaskManager/SubAgentManager（main.py:265-287） |
| 8.3 SubAgentManager | ✅ 真实实现 | 可选 `sandbox` 参数 + `_resolve_sandbox()` 懒构建自愈缓存（subagent/manager.py:308-329）；子 agent registry 传入 sandbox（manager.py:348） |
| 8.4 web/benchmark 接线 | ✅ 真实实现 | web/session.py:213-228；benchmarks/agent_runner.py:297-314 |
| 8.5 config YAML 解析 | ✅ 真实实现（含中等问题，见 Issue 1） | `_parse_sandbox_config` 接入 `_load_yaml_config`（config.py:363, 1167-1190）；backend/image/memory_mb/cpus/timeout_seconds 含校验；测试 4 个用例（test_config.py） |
| 8.6 Docker 后台优雅报错 | ✅ 真实实现 | `BackgroundTaskManager.start` 捕获 `NotImplementedError` → `RuntimeError`（background.py:52-60）；loop 转为 `[Error: ...]` 不崩溃（loop.py:1035-1042 既有 try/except）；单测 test_background_manager_surfaces_docker_not_implemented |
| 8.7 回归测试 | ✅ 真实实现 | test_factory_sandbox_wiring.py（registry 接线/回填/fail-fast/后台报错）+ test_config.py sandbox 4 用例 + test_command_guard last_reason + timeout 回归 |

## Issues

### Issue 1（中等，需修复）— `sandbox.timeout_seconds` 配置在前后台主路径上不生效

`config.sandbox.timeout_seconds` 被解析（`agent/config.py:1189`）并传入后端构造（`agent/tools/factory.py:53`、`agent/subagent/manager.py:327`），但唯一的前台 Bash 调用点在 `agent/tools/builtin/bash.py:83` 总是传 `timeout=timeout or 30.0`（30.0 恒为 truthy），导致 `ProcessBackend.run` 的 `timeout = timeout or self.timeout`（`agent/tools/sandbox/process_backend.py:153`）永远用 30.0，配置值（例如 45）从不生效。后台路径同理：`loop.py:427-433` 直接把 tool-call 的 timeout（可能为 None）传给 `BackgroundTaskManager.start`，不用配置值。

这与 design.md Decision 5 声称的"`timeout_seconds` 可从 `asterwynd.yaml` 生效"相矛盾，也违背本 change 自身的"配置了不得静默失效"（degrade-first）哲学。修复方向：BashTool 缺省时让后端应用自身默认（如 `timeout=timeout if timeout is not None else self.sandbox.timeout`，或让 BashTool 持有 config timeout），并补一个端到端用例。注：该行 `timeout or 30.0` 是 batch 1 遗留，但 batch 2 的 `_parse_sandbox_config` 使其成为真实缺陷。

### Issue 2（minor）— cgroup 遗留目录清扫未实现

design.md Decision 5 要求"`is_supported()`/构造时清扫遗留 `asterwynd-*` 目录"，但 `agent/tools/sandbox/cgroup.py` 只在 `cleanup()`（cgroup.py:159）处理当前 run 的目录，`is_supported()`（cgroup.py:102-118）与 `__init__` 均无遗留清扫。后端进程被强杀（SIGKILL）时遗留的空 `asterwynd-*` cgroup 目录会累积（每个为空、无进程，风险低）。建议按 design 补齐或在 follow-up 记录。

### Issue 3（minor，batch 1 遗留）— Docker 超时 kill 可能泄漏容器

`agent/tools/sandbox/docker_backend.py:143` 超时只 `proc.kill()` 杀掉 `docker run` CLI 客户端；容器已在 daemon 启动，`--rm` 只在容器自然退出时移除，被 kill 的 CLI 不会自动停容器，超时命令可能残留运行中的容器（`--network none` 下外传受限，但占用资源）。batch 2 只在该路径补了 `kill` 事件，未改 kill 机制。建议 follow-up：超时用 `docker kill <container>`。

### Issue 4（minor）— `_setup_cgroup` 仅捕获 `OSError`

`agent/tools/sandbox/process_backend.py:126` 只 `except OSError`；若 `controller.create()` 抛出非 OSError 异常，会传播到外层 `except Exception`（process_backend.py:217），返回的 result 里 `degraded=degraded`（此时为 False，process_backend.py:225），降级标志丢失。实际 `_apply_limits` 只有文件写操作（OSError 子类），风险低，但建议 catch `Exception` 更稳。

### Issue 5（minor）— Docker 后台优雅报错缺 loop 级端到端测试

`tests/agent/tools/test_factory_sandbox_wiring.py:84-90` 覆盖了 `BackgroundTaskManager.start` 抛 `RuntimeError`，但未覆盖"BashTool(docker) + run_in_background=True → 返回 `[Error: ...]` 字符串、loop 不崩溃"的完整链路。机制本身可靠（loop.py:1035-1042 捕获异常转 `[Error: ...]`），建议补一个集成用例。

## Test Results

- 第二批相关测试文件（test_cgroup / test_process_backend_cgroup / test_sandbox_events / test_bash_tool_events / test_loop_sandbox_events / test_factory_sandbox_wiring / test_config / test_command_guard / test_background / test_sandbox）：**126 passed**（19.4s）
- 全量 pytest（排除已知环境失败 `test_tree_sitter_extracts_java_and_kotlin_symbols`）：**1511 passed, 7 skipped, 1 deselected**（121s）
- OpenSpec strict validate：**32 passed, 0 failed**
- 模块导入无循环依赖（main/loop/factory/process_backend/cgroup/sandbox_events/background/trace_recorder 全部可导入）
- 注：`scripts/check_openspec_artifacts.py` 当前报 building-review.md missing，属预期（本文档即为产出物）；本 verdict 为 CHANGES_REQUESTED，review-loop 流程会据此驱动修复后再审。

## 结论

第二批实现质量整体高：cgroup v2 工程细节（per-run 唯一目录、starttime 防 pid 复用、oom 基线对比、degrade-first、cleanup 幂等）与设计一致；事件入 trace 的 schema 兼容策略正确；config→BashTool 跨入口接线修复完整；超时 killpg 修复有回归测试。唯一需修复的中等问题是 `sandbox.timeout_seconds` 在主路径不生效（Issue 1），其余为 minor 观察项（含 2 个 batch 1 遗留，可作 follow-up）。修复 Issue 1 后本批即可 PASS。
