# Tasks: 安全沙箱做深

> **批次范围**：第一批 = 第 1-4 节（ExecutionBackend 抽象 + ProcessBackend/DockerBackend + 命令护栏 + 攻击回归集 + 彻底迁移）；cgroup v2 为后续批（Docker 自带 --memory 资源限制）。
> **第二批（2026-08-02）**：第 5-6 节 + 第 7 节收尾 + 第 8 节接线修复（batch 1 遗漏）。设计经 batch-grill-me 等价审阅（3 个独立审阅 agent）定稿，见 design.md「Batch 2 设计定稿」。

## 1. 命令护栏（command_guard.py）

- [x] 1.1 轻量命令分词器（识别命令名/参数/重定向/管道/子 shell/引号/通配符）
- [x] 1.2 argv 语义校验：`rm` 目标越界、`cp/mv` 目标敏感、`chmod` 权限位、`timeout` 范围、路径落 workspace
- [x] 1.3 denylist 增强覆盖绕过面：`rm -fr`/`rm -r -f`/`rm -rf --`、`chmod 0777`/`chmod a+rwx`、`kill -SIGKILL`/`kill -KILL`、`node -e`/`deno eval`/`awk system()`、`base64 -d | bash`、`mv` 目标越界
- [x] 1.4 `assert_command_allowed` 接入 command_guard（契约不变，逻辑升级）
- [x] 1.5 单元测试：分词、argv 校验、denylist 增强、绕过面回归

## 2. ExecutionBackend 抽象 + 后端（sandbox/ 包）

- [x] 2.1 `sandbox/` 包重构：`base.py`（ExecutionBackend Protocol + SandboxResult + BackgroundProcessHandle 从 sandbox.py 迁移）
- [x] 2.2 `process_backend.py`：ProcessBackend（现有 subprocess 实现重构）
- [x] 2.3 `docker_backend.py`：DockerBackend（`docker run --rm --network none --memory 512m --cpus 2 -v <ws>:/workspace -w /workspace <image> sh -c "<cmd>"`）
- [x] 2.4 `factory.py`：`build_execution_backend(name)` → ProcessBackend/DockerBackend
- [x] 2.5 后端契约测试（统一跑 run/run_background/is_available；DockerBackend 真实 Docker 验证，`sg docker` 访问）
- [x] 2.6 **彻底迁移**：删除 `SandboxExecutor`，调用方（main.py/background.py/bash.py/__init__.py）改用 factory

## 3. 攻击回归集（数据驱动）

- [x] 3.1 构建 50+ 恶意命令攻击回归集（8 类：文件破坏/敏感读取/提权/任意代码执行/外传/资源耗尽/绕过变体/git 破坏），JSON case 清单
- [x] 3.2 测试读取清单 → 走命令护栏 + 后端 → 断言全部拦截
- [x] 3.3 接入 benchmark（复用 PR #80 runner）

## 4. config + 收尾

- [x] 4.1 config 新增 sandbox 配置段（backend 切换/镜像/资源上限）
- [x] 4.2 OpenSpec spec 同步
- [x] 4.3 全量 pytest + openspec validate + artifact checker
- [x] 4.4 benchmark 量化（阻断率、Docker 隔离验证）

## 5. cgroup v2 资源限制（第二批）

- [x] 5.1 `max_memory_mb` 生效：cgroup v2 限制 CPU/内存（本地 ProcessBackend）。新增 `agent/tools/sandbox/cgroup.py`（CgroupController Protocol + CgroupV2Controller：per-run 临时 cgroup、memory.max/memory.swap.max=0、cpu.max、cpuset 复制、starttime pid 复用防护、oom 基线对比、cleanup 幂等）；ProcessBackend 增加 memory_mb/cpus/controller_factory/cgroup_supported 参数
- [x] 5.2 超限自动 kill + 记录：OOM kill 检测 → `SandboxResult.oom_killed=True` + `oom` 事件（reason=memory_limit）
- [x] 5.3 低资源环境降级：cgroup 不可用/设置失败 → `SandboxResult.degraded=True` + `degraded` 事件（每实例限流一次）+ 退回纯超时
- [x] 5.4 单元测试：cgroup 限制逻辑（mock）。新增 `tests/agent/tools/test_cgroup.py`（fake fs）+ `tests/agent/tools/test_process_backend_cgroup.py`（注入 fake controller + 降级路径）
- [x] 5.5 顺带修复：ProcessBackend 超时只 kill shell 不 kill 进程组 → `start_new_session=True` + `killpg`，`sleep 60` 超时不再残留孤儿进程（回归测试 `test_sandbox_timeout_kills_process_tree`）

## 6. 沙箱事件入 trace（第二批，与 #78 协调）

- [x] 6.1 结构化 sandbox 事件（denied/reason/kill/oom/degraded）入 trace_recorder。新增 `agent/sandbox_events.py`（contextvar sink + emit_sandbox_event + tool_call_id 自动附加 + command 截断 300 字符）；`TraceRecorder.record_sandbox_event` + `TraceRecorderSandboxSink`；`CommandGuard.last_reason`（denylist/pipe_to_shell/protected_redirect/rm_target_escape/mv_cp_dest/chmod_bits/timeout_range/curl_exfil）
- [x] 6.2 与 #78 事件 schema 对齐：新增 `sandbox` step type 向后兼容（timestamp 是 TraceStep 字段、data 负载干净、schema_version 保持 1.1——策略：新 step type 不 bump，仅既有 step payload 结构性变更才 bump）
- [x] 6.3 事件产生点接线：BashTool（workspace_policy/command_guard 拒绝）、ProcessBackend/DockerBackend（超时 kill）、`BackgroundTaskManager._monitor`（超时/stop/cleanup kill）；`loop.run` save/restore sink（镜像 `_active_trace_recorder` 模式，嵌套 run 不串）

## 7. 收尾校验（checker 要求项）

- [x] 7.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）。2026-08-02 用 3 个独立审阅 agent 完成等价追问并定稿，见 design.md「Batch 2 设计定稿」+ workflow-events.jsonl seq 2
- [x] 7.2 benchmark smoke verification（coding-agent core change 要求）。`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 跑通 34 tasks，无基础设施级错误（fake agent 任务失败为预期），产出 run.json/summary.md
- [x] 7.3 当前规格同步：把 spec delta 合并到 `openspec/specs/workspace-safety/spec.md`（第二批 ADDED requirement：cgroup 资源限制 / 沙箱事件入 trace + ExecutionBackend 2 个新 scenario），workflow-events.jsonl seq 3 记录

## 8. config→BashTool 后端接线修复（第二批，batch 1 遗漏）

- [x] 8.1 `build_default_tool_registry`/`build_coding_tool_registry`/`get_default_tools`/`get_coding_tools` 增加 `sandbox: ExecutionBackend | None` 参数并透传给 `BashTool`；预构建 `tools` 列表 + sandbox 同时传入时对列表内 BashTool 回填（`_apply_sandbox_to_tools`）
- [x] 8.2 `main.py`：sandbox 构建提前到 SubAgentManager/registry 之前；传给 registry/BackgroundTaskManager/SubAgentManager；新增 `build_sandbox_from_config()`（is_available 启动门禁，fail-fast 不静默回退）
- [x] 8.3 `SubAgentManager`：可选 `sandbox` 参数 + `_resolve_sandbox()` 自愈默认（未传时按 `config.sandbox` 懒构建并缓存）
- [x] 8.4 `web/session.py`、`benchmarks/agent_runner.py`：`build_sandbox_from_config` 构建后端并传入 registry + SubAgentManager
- [x] 8.5 config YAML 解析：新增 `_parse_sandbox_config` 接入 `_load_yaml_config`（`backend/image/memory_mb/cpus/timeout_seconds` 可配置，含校验）
- [x] 8.6 Docker 后端后台执行优雅报错：`BackgroundTaskManager.start` 捕获 NotImplementedError → 明确 RuntimeError（loop 转为 [Error: ...]，不崩溃）
- [x] 8.7 回归测试：`tests/agent/tools/test_factory_sandbox_wiring.py`（registry 接线 / tools 回填 / build_sandbox_from_config fail-fast / 后台优雅报错）+ `tests/agent/test_config.py`（sandbox YAML 解析 4 个用例）

## 9. 审阅修复（Round 1，issue #90 强制审阅闭环）

独立零记忆审阅 agent 返回 CHANGES_REQUESTED（1 个中等 + 4 个 minor），逐条修复：

- [x] 9.1 **`sandbox.timeout_seconds` 主路径不生效（中等）**：`BashTool.execute` 的 `timeout or 30.0` 恒为 30.0，覆盖后端配置默认值。修复：直接透传 `timeout`（None → 后端默认）。回归测试 `test_backend_default_timeout_used_when_none_passed`
- [x] 9.2 **cgroup 遗留目录清扫**：`CgroupV2Controller.sweep_stale`（dead pid 的 `asterwynd-*` 目录 best-effort 清理，live pid 不动），`create()` 时触发。测试 `TestSweepStale`（4 个用例）
- [x] 9.3 **`_setup_cgroup` 仅 catch OSError**：非 OSError（如控制器 RuntimeError）会丢 degraded 标志。修复：catch Exception。回归测试 `test_non_oserror_setup_failure_still_degrades`
- [x] 9.4 **Docker 超时容器残留**：kill CLI 客户端后容器在 daemon 残留（--rm 只在容器退出后触发）。修复：`--cidfile` + 超时后 `docker rm -f`。Docker 契约测试验证
- [x] 9.5 **attach 语义**：进程先于 attach 退出（快命令）不视为 degraded（`_attach` 返回 None=skip），仅 attach 失败才 degraded
