# Design: 安全沙箱做深 — AST 命令校验 + cgroup 资源限制 + 攻击测试集

## Context

当前安全是"正则 denylist + 前缀 allowlist + subprocess"两层防线：`WorkspacePolicy.assert_command_allowed()` 用字符串前缀匹配，`SandboxExecutor` 用 `subprocess(shell=True)`，`max_memory_mb` 存而不用。已知绕过面（cat /etc/passwd 被 allowlist 放行、rm -rf . 未命中 denylist）在 `2026-06-21-tighten-bash-command-policy/design.md` 中被记为"完整 parser 或沙箱隔离另立 change"。5/8 场面试直接问到安全沙箱。

## Goals / Non-Goals

**Goals:**

- 把 `assert_command_allowed` 从字符串前缀升级为 bash AST 句型校验（参数类型+范围约束）。
- 建立 cgroup v2 资源限制（CPU/内存），超限自动 kill + 记录入 trace。
- 建立 50+ 恶意 prompt 攻击回归测试集。
- 沙箱 deny/kill/oom 事件结构化入 trace（与 #78 事件 schema 对齐）。
- 容器隔离（Docker/gVisor）作可选后端而非默认。

**Non-Goals:**

- 不把容器隔离设为默认后端（分阶段：AST + cgroup + 攻击集先行）。
- 不重做 WorkspacePolicy 路径边界（additional_roots 已合入）。
- seccomp 兜底若平台差异大，作为后续项记录。

## Decisions

### Decision 1: 分阶段交付，容器隔离作可选后端

**方案**：本 change 先交付 bash AST 句型校验 + cgroup v2 资源限制 + 50+ 恶意 prompt 攻击回归集；容器隔离（Docker/gVisor）作为可选后端（`config.sandbox.backend` 可切 process/docker/gvisor），不作默认。

**备选**：一步到位默认容器化。被拒：改变 worktree 隔离、交互开发体验与 benchmark 一致性；且与 add-workspace-param 刚扩展的 additional_roots 语义交织，风险高。

**理由**：AST 校验 + cgroup 已能实质提升安全面，容器化作为增量演进。

### Decision 2: `assert_command_allowed` 升级为 AST 句型校验

**方案**：用 shell AST parser 解析命令，只允许预定义句型（如 `git status`、`git diff HEAD~N`、`pytest -k PATTERN`），参数做类型+范围约束（timeout 必须 int 且在 [1,600]、路径参数必须落在 workspace 内、禁止通配符/重定向/管道组合）。`assert_command_allowed` 契约不变（仍返回 bool/抛错），但校验逻辑升级。

**备选**：仅扩充字符串正则。被拒：正则无法覆盖"cat /etc/passwd 被 allowlist 放行"等绕过面。

**理由**：AST 校验能捕获字符串匹配漏掉的语义绕过，是工业级安全边界。

### Decision 3: cgroup v2 资源限制 + 超限 kill 入 trace

**方案**：`max_memory_mb` 从存而不用改为生效：cgroup v2 限制 CPU/内存，超限自动 kill + 记录结构化 sandbox 事件（denied/reason/kill/oom）入 trace_recorder。低资源环境降级（无 cgroup 时退化为超时/内存警告）。

**备选**：仅保留字段。被拒：无法提供"资源超限 kill"的面试证据。

**理由**：资源限制是沙箱完整性的必要部分。

### Decision 4: 50+ 恶意 prompt 攻击回归集

**方案**：构建 50+ 恶意 prompt → tool-call → sandbox 拒绝 的端到端回归集（fork bomb、`curl|sh`、`python -c`、`rm -rf /`、`dd if=`、chmod 777、exfil、无限内存 malloc、`/etc/passwd` 读取、`git reset --hard` 等），断言全部拦截。

**备选**：仅单元测试命令拒绝。被拒：无法覆盖 prompt → tool-call → sandbox 的端到端链路。

**理由**：端到端攻击集是可测试、可面试引用的安全面证据。

## Pre-Implementation Review

经 batch-grill-me（设计树逐轮确认）已定稿以下决策：

**第一轮已确认（根决策）：**
- **执行抽象为可插拔 `ExecutionBackend` 接口，Docker 是第一个真沙箱后端**：命令执行抽象为 `ExecutionBackend.run(cmd) -> SandboxResult`，含 `run_background`/`kill`（`SandboxResult`/`BackgroundProcessHandle` 已是现成返回类型，代码已预留"换容器只需改适配器"）。实现：`ProcessBackend`（现有 subprocess，默认）+ `DockerBackend`（`docker run` 容器隔离，`--network none` 限制网络，超时 kill）。命令护栏在前置层。
- **业界调研（Reference Research findings）确认方向**：正则/模式匹配的命令校验"根本性可绕过"（Claude Code 2025 三次 CVE：CVE-2025-64755 sed 绕过写任意文件、CVE-2025-66032 $IFS/短 flag 绕过任意代码执行、CVE-2025-59041 git config 注入），业界共识是真正边界 = 沙箱隔离 + 无 shell 直接执行；命令校验是"护栏不是边界"。故本 change 核心是**沙箱后端抽象**，命令校验作前置护栏。
- **命令护栏（轻量，不追求完整 bash AST）**：轻量命令分词 + argv 语义校验（识别 `rm -rf` 目标越界、`> /etc/`、`mv` 目标敏感、`timeout` 范围）+ 现有 denylist 增强（补 `rm -fr`/`chmod 0777`/`kill -SIGKILL`/`node -e`/`base64|bash` 等绕过面）。定位为"护栏不是边界"。
- **50+ 恶意 prompt 攻击回归集（数据驱动）**：JSON/YAML case 清单（id/prompt/expected_command/reason），测试读取 → 模拟 LLM 生成 tool-call → 走命令护栏 + 后端执行 → 断言拦截。可扩展、可接 benchmark。
- **cgroup v2 降为后续批**：Docker 后端自带 `--memory` 资源限制（容器级），本地 ProcessBackend 的 cgroup 限制后置。

**第二轮已确认（细节层）：**
- **`ExecutionBackend` 接口签名**（复用现有类型，最小侵入）：
  ```python
  class ExecutionBackend(Protocol):
      async def run(self, command: str, *, timeout: float, cwd: Path | None = None) -> SandboxResult: ...
      async def run_background(self, command: str, *, cwd: Path | None = None) -> BackgroundProcessHandle: ...
      def is_available(self) -> bool: ...  # 后端可用性探测
  ```
  `SandboxResult`/`BackgroundProcessHandle` 已是现成类型（代码已预留"换容器只需改适配器"）。`ProcessBackend` 包现有 `SandboxExecutor`；`DockerBackend` 新实现。
- **`DockerBackend` 具体命令**：`docker run --rm --network none --memory 512m --cpus 2 -v <workspace>:/workspace -w /workspace <image> sh -c "<command>"`。`--network none` 隔离网络（防外传）、`--memory/--cpus` 资源限制（容器级，替代 cgroup）、`-v` 只挂 workspace（FS 隔离）、超时用等待 + `docker kill`。镜像可配置（默认 `alpine:latest` 本地已有；`python:3.10-slim` 可选）。
- **命令护栏规则集（轻量分词 + argv 语义校验）**：
  - 保留现有 denylist，**增强覆盖绕过面**：`rm -fr`/`rm -r -f`/`rm -rf --`、`chmod 0777`/`chmod a+rwx`/`chmod -R 777 /tmp`、`kill -SIGKILL`/`kill -KILL`、`node -e`/`deno eval`/`awk system()`、`base64 -d | bash`、`mv` 目标越界、`> /etc/`（已有）等。
  - **新增 argv 语义校验**（轻量分词）：对命令分词（命令名/参数/重定向/管道/子 shell），对危险命令做参数级判断——`rm` 目标是否越界（/、$HOME、workspace 外）、`cp/mv` 目标是否敏感、`chmod` 权限位、`timeout` 范围、路径参数是否落 workspace。
  - **保持 default-allow**（不 deny-by-default，避免破坏合法命令），但**高危句型（管道到 sh、重定向到 /etc 等）命中即拒**。
  - 分词器**轻量自研**（识别引号/转义/重定向/管道/子 shell/通配符），不引入 bashlex。
- **攻击集分类（数据驱动 JSON）**：按 8 类组织（每类 ≥ 若干 case）——文件破坏（rm -rf /、dd if=、mkfs）、敏感读取（cat /etc/passwd、.env）、提权/系统控制（chmod 777 /、sudo、shutdown、kill -9 1）、任意代码执行（python -c、node -e、curl|sh、base64|bash、heredoc）、外传/网络（curl 外传、/dev/tcp、wget）、资源耗尽（fork bomb、无限内存）、绕过变体（$IFS、反引号、$()、引号混淆、unicode）、git 破坏（reset --hard、push --force、branch -D）。每个 case `{id, category, command, reason, expected: "deny"}`。

**第三轮已确认（实现结构）：**
- **模块划分**：`agent/tools/sandbox/` 从 `sandbox.py` 升级为包 = `base.py`（ExecutionBackend Protocol + SandboxResult + BackgroundProcessHandle，从 sandbox.py 迁移）+ `process_backend.py`（ProcessBackend，现有 subprocess 实现重构）+ `docker_backend.py`（DockerBackend，docker run 容器执行）+ `factory.py`（`build_execution_backend(name)`）；`agent/tools/command_guard.py`（命令护栏：轻量分词 + argv 语义校验 + denylist 增强）；`benchmarks/attacks/`（攻击集数据 attacks.json + 分类）。
- **彻底迁移，不留 SandboxExecutor 别名**：所有调用方（`agent/main.py`、`agent/background.py`、`agent/tools/builtin/bash.py`、`agent/tools/__init__.py`）改用 `factory.build_execution_backend()` 构建，删除 `SandboxExecutor` 类。benchmark gold.patch 是历史任务数据不改。引用点已确认仅 4 处，迁移成本可控。
- **TDD 实现顺序**：1) `command_guard.py`（轻量分词 + argv 语义校验 + denylist 增强）→ 单测（含绕过面回归）2) `sandbox/` 包重构（base.py + process_backend.py）→ 后端契约测试 3) `docker_backend.py` → 契约测试（真实 Docker，`sg docker` 访问）4) `factory.py` + `config.py` sandbox 段 + 调用方接线（main/background/bash/__init__）→ 集成测试 5) 攻击集数据 + 测试 → 全量验证。

**实现中发现并修复（端到端验证）：**
- **Docker `--memory`/`--cpus` 默认不加（cgroup 环境限制）**：实测本环境 `docker run --memory 512m` 报 `cannot enter cgroupv2 "/sys/fs/cgroup/docker" with domain controllers -- it is in threaded mode`（宿主 cgroup v2 未配置 domain controllers）。Docker 基础执行 + `--network none` 正常。故 `memory_mb`/`cpus` 默认为 None（不加 flag），作为可配置项（支持 cgroup 的环境可开启）。
- **`ExecutionBackend.run` 的 `timeout` 可缺省**：缺省用 backend 默认（`timeout: float | None = None`），兼容旧 `SandboxExecutor.run(cmd)` 调用。

## Batch 2 设计定稿（2026-08-02，batch-grill-me 等价审阅）

> 进入 building 前按 AGENTS.md 执行设计追问。当前环境无 `batch-grill-me` skill，按同等标准改用 **3 个独立零记忆审阅 agent（cgroup 工程 / 可观测性 schema / 集成接线）** 对 tasks 5-7 的推荐方案做对抗式审阅，三者均返回 `changes_requested` 并给出可执行改进。以下为综合后定稿，逐项覆盖审阅发现的 blocker/major。

### Decision 5: cgroup v2 资源限制（任务 5）——per-run 临时 cgroup，degrade-first

**方案**：新增 `agent/tools/sandbox/cgroup.py`：

- `CgroupController` Protocol（`create/attach/oom_killed/cleanup`）+ `CgroupV2Controller` 实现；所有文件操作经可注入的 `fs_root`（默认 `/sys/fs/cgroup`）便于单测 mock。
- **每次 `run()` 调用创建独立临时 cgroup**，目录名唯一 `asterwynd-<procpid>-<seq>`，互斥于后端实例共享（后端是 main.py 构建的单例，同时被 Bash 工具/后台管理/子 agent 使用）。并发 `run()` 不共享可变状态，各自独立 controller + 基线。
- `create()`：mkdir 子 cgroup → 写 `memory.max`（字节）、`memory.swap.max=0`（防 malloc 溢出 swap；`ENOENT` 视为 per-dimension degrade）、`cpus` 设置时写 `cpu.max = "round(cpus*100000) 100000"`；若父 `subtree_control` 含 `cpuset`，先复制父 `cpuset.cpus/cpuset.mems` 到子级再 attach（cgroup v2 已知坑）。
- `attach(pid)`：仅当进程仍存活（`returncode is None`）时写 `cgroup.procs`；捕获 `/proc/<pid>/stat` starttime 防 pid 复用误杀。
- `oom_killed()`：基线对比 `memory.events` 的 `oom_kill` 计数（create 时记基线，退出后最终校验）。
- `cleanup()`：中止路径（超时）先校验 starttime 匹配再 `cgroup.kill=1`；正常退出后 `rmdir`（EBUSY 短暂重试）；`finally` 保证清理；`is_supported()`/构造时清扫遗留 `asterwynd-*` 目录。
- `is_supported()`：仅作廉价预过滤（controllers 存在 + 可写探针），**`create()/attach()` 失败才是权威的"不支持"信号**。

**ProcessBackend 接线**：新增 `memory_mb`/`cpus`/`controller_factory`/`cgroup_supported` 参数；`_BACKEND_KWARGS["process"]` 增加 `memory_mb/cpus`。`run()` 中：配置了限制且 cgroup 可用 → per-run controller + attach + 分段等待（poll `memory.events` + 退出后最终检查）→ OOM 时 kill + `result.oom_killed=True` + `oom` 事件；cgroup 不可用/设置失败 → `result.degraded=True` + `degraded` 事件（每实例限流一次）+ 退回纯超时。超时 kill 发 `kill` 事件。

**`SandboxResult`** 增加 `oom_killed: bool = False`、`degraded: bool = False`（dataclass 默认值向后兼容；`to_json` 输出会多字段，无反向反序列化路径）。

**degrade-first 语义**：配置了 `memory_mb/cpus` 但环境不支持 cgroup 时**必须可见地降级**（本环境即此路径：`/proc/self/cgroup=0::/`、`/sys/fs/cgroup` root-owned 755、memory 不在 subtree_control）——`degraded` 标志 + 事件 + warning，绝不允许"配置了等于没配置"的静默失效。

**范围边界**：cgroup 仅作用于前台 `run()`；`run_background` 的 cgroup 限制记为 follow-up（见决策 8）。Docker 后端已用容器级 `--memory/--cpus`（可选开启）。

**配置**：`SandboxConfig` 已存在但 YAML 段从未解析（batch 1 遗漏，审阅确认无 `_parse_sandbox_config`）——新增 `_parse_sandbox_config` 并接入 `_load_yaml_config`，使 `backend/image/memory_mb/cpus/timeout_seconds` 可从 `asterwynd.yaml` 生效。

### Decision 6: 沙箱事件入 trace（任务 6）——contextvar sink + tool_call_id

**方案**：

- `TraceRecorder.record_sandbox_event(event: str, **data)` → `self.record("sandbox", event=event, **data)`。**向后兼容**：新 step type 开放扩展；`timestamp` 仍是 TraceStep 字段；data 负载干净；`schema_version` 保持 `"1.1"`（策略：仅既有 step payload 结构性变更才 bump，新 step type 不 bump——已在 spec 文档化）。
- 新模块 `agent/sandbox_events.py`：`SandboxEventSink` Protocol（`emit` 必须非阻塞）+ `_NoopSink` 默认 + `current_sandbox_sink: ContextVar` + `emit_sandbox_event(event, **data)`。emit 自动附加 `tool_call_id`（读既有 `current_tool_call_id` contextvar，loop.py:1023 设置）并把 `command` 截断到 300 字符（折叠换行）。
- `TraceRecorderSandboxSink` 适配器放 `agent/trace_recorder.py`（避免 sandbox 包反向依赖 trace 层）。
- `loop.run()`：镜像现有 `_active_trace_recorder` 的 **save/restore** 模式（loop.py:468-490）——run 开始 set sink，`finally` 恢复，保证嵌套 run（子 agent）与无 recorder 的 run 不会串/漏。
- 事件产生点：BashTool（workspace_policy 拒绝→`denied` reason=workspace_policy；guard 拒绝→`denied` reason="command_guard:"+`CommandGuard.last_reason`）；ProcessBackend（超时→`kill` reason=timeout；OOM→`oom` reason=memory_limit；降级→`degraded`）；DockerBackend（超时→`kill` reason=timeout）；`BackgroundTaskManager._monitor`（超时→`kill` reason=timeout；TaskStop→`kill` reason=user_stop；cleanup→`kill` reason=cleanup）。
- `CommandGuard.check()` 保持返回 `CommandVerdict`，**新增 `last_reason` 属性**（denylist/pipe_to_shell/protected_redirect/rm_target_escape/mv_cp_dest/chmod_bits/timeout_range/curl_exfil），向后兼容。

**范围边界**：沙箱事件在 trace_recorder 活跃时记录（子 agent run、benchmark run、web session run）；主 CLI 路径当前不创建 trace（`main.py:609` 不传 trace_recorder），该路径为 no-op——记为 follow-up（见决策 8），设计不over-claim。

### Decision 7: config→BashTool 后端接线修复（batch 1 遗漏）——跨入口一致

**问题**：`main.py` 按 `config.sandbox.backend` 构建后端但只传给 `BackgroundTaskManager`；`BashTool(policy=policy)` 硬编码 `backend_name="process"`。`backend: docker` 对前台 Bash 无效。

**方案**：

- Factory：`build_default_tool_registry`/`build_coding_tool_registry`/`get_default_tools`/`get_coding_tools` 增加 `sandbox: ExecutionBackend | None = None`，透传给 `BashTool(policy=policy, sandbox=sandbox)`；当调用方传预构建 `tools` 列表且 `sandbox` 非空时，对列表内 BashTool 实例回填 sandbox（防静默忽略）。
- `main.py`：sandbox 构建**提前到 SubAgentManager/registry 之前**；传给 `build_default_tool_registry(sandbox=...)`、`BackgroundTaskManager(sandbox=...)`、`SubAgentManager(sandbox=...)`；**新增 `is_available()` 启动门禁**——配置后端不可用时 fail-fast 报错（不静默回退到 process，避免悄悄移除用户要求的隔离）。
- `SubAgentManager`：新增可选 `sandbox` 参数；未显式传时自愈——`_build_subagent_loop` 按 `config.sandbox` 懒构建（缓存），保证 web/benchmark 子 agent 与 CLI 一致。
- `web/session.py`、`benchmarks/agent_runner.py`：同样从 `config.sandbox` 构建后端并传入 registry（消除"CLI 生效、web 不生效"的同类缺口）。
- Docker 后端后台执行：batch 2 不做 `docker run -d` 实现——`BackgroundTaskManager.start` 捕获 `NotImplementedError` 返回用户可读错误（BashTool 已有"不可用"分支），不崩溃；记 follow-up。

### 审阅发现的 blocker/major 覆盖清单

| 审阅发现 | 定稿处置 |
|---|---|
| cgroup 目录名/并发（blocker） | per-run 唯一目录 + 每 run 独立 controller（决策 5） |
| degrade 覆盖不全（blocker） | 限制已配置但 cgroup 不可用也置 `degraded` + 事件（决策 5） |
| `memory.swap.max` 未设 | `memory.swap.max=0`，ENOENT 容忍（决策 5） |
| cpuset 未初始化 | 复制父 cpuset.cpus/mems（决策 5） |
| `is_supported()` 过弱 | 仅预过滤，create/attach 失败为权威信号（决策 5） |
| poll vs communicate | 分段等待 + 退出后最终 oom 检查（决策 5） |
| run_background 无 cgroup | 显式 scope 出批 2，记 follow-up（决策 8） |
| config YAML 未解析 | 新增 `_parse_sandbox_config`（决策 5） |
| 事件发射 seam 未定义 | `agent/sandbox_events.py` sink（决策 6） |
| pid 复用误杀 | starttime 校验 + attach 前存活检查（决策 5） |
| 清理健壮性/遗留 cgroup | finally 清理 + EBUSY 重试 + 清扫（决策 5） |
| 后台 kill 事件缺失 | `BackgroundTaskManager._monitor` 发 kill（决策 6） |
| contextvar save/restore | 镜像 loop.py 既有模式（决策 6） |
| degraded 事件时机 | 首次 run 时懒检测，构造期不发（决策 6） |
| 事件无 tool_call_id | emit 自动附加（决策 6） |
| schema_version 策略 | 保持 1.1 + 文档化"新 step type 不 bump"（决策 6） |
| guard 无子原因 | `CommandGuard.last_reason`（决策 6） |
| 命令截断策略 | 300 字符 + 折叠换行（决策 6） |
| 主 CLI 路径无 trace | 显式 scope，记 follow-up（决策 8） |
| 后端不可用无门禁 | `is_available()` fail-fast（决策 7） |
| 共享后端可重入 | per-run cgroup + contextvar 归因（决策 5/6） |
| docker 后台 NotImplementedError | 优雅报错 + follow-up（决策 7） |
| web/benchmark 未接线 | 同模式接线（决策 7） |
| 回归测试未测真实 bug 点 | main.py monkeypatch 测试（决策 7） |

### Decision 8: 显式 follow-up（不在本批交付）

- `run_background` 的 cgroup 资源限制（fork bomb 经后台逃逸的防护）。
- `DockerBackend.run_background`（`docker run -d` + logs/kill 句柄）。
- 主 CLI 前台 run 路径创建 trace_recorder（当前不产生 trace，沙箱事件在 main 路径为 no-op）。
- seccomp 兜底（内核 syscall 白名单）。

### 第二批实现中发现并修复（端到端验证）

- **ProcessBackend 超时不杀进程树（batch 1 遗留 bug）**：`run()` 超时只 `proc.kill()`（杀 shell），`sleep 60` 等子进程残留为孤儿并握住管道 → 测试实测超时路径要等满 60s。修复：`create_subprocess_shell(start_new_session=True)` + 超时 `os.killpg(pid, SIGKILL)` 杀整个进程组（与 `run_background` 既有 `setsid` 语义一致）。回归测试 `test_sandbox_timeout_kills_process_tree`（超时 0.5s 内返回）。
- **`CommandGuard` 的 `timeout` 是 dead code（batch 1 遗留 bug）**：`_check_argv` 把 `timeout` 当 wrapper 直接递归跳过，`_check_timeout` 不可达 → `timeout 9999 sleep 1` 被放行。修复：从 wrapper 分支移出 `timeout`，`_check_timeout` 校验数值范围后递归检查被包裹命令（`timeout 5 mv x /etc-passwd` 也会被 argv 校验拦截）。新增 `TestCommandGuardTimeoutWrapper` 回归测试。
- **cgroup 不可写环境（本宿主）**：`/proc/self/cgroup=0::/`、`/sys/fs/cgroup` root-owned 755、memory 不在 subtree_control → 实际运行路径是 degrade-first（`degraded=True` + 事件），单元测试用注入 fake controller 覆盖 enforce 路径。
- **`CgroupV2Controller` 的 cleanup 兼容普通文件系统**：真实 cgroup v2 fs 的 control 文件是虚拟的、不阻塞 `rmdir`；普通 fs（测试 fake）会因非空目录阻塞 `rmdir`，cleanup 增加 best-effort 清理子文件再重试。

### 第二批审阅修复（Round 1）

独立审阅 agent 返回 CHANGES_REQUESTED（1 中等 + 4 minor），见 tasks.md 第 9 节。要点：

- **`sandbox.timeout_seconds` 主路径不生效**：`BashTool.execute` 的 `timeout or 30.0` 恒 truthy 覆盖后端配置默认。修复为直接透传 `timeout`（None → 后端默认），配置值真正生效。
- **attach 语义修正**：进程先于 attach 退出（快命令）不是 degradation——`_attach` 返回 `None`（skip），仅 attach 失败返回 `False` 才置 `degraded`。避免"配置了限制的每条快命令都标记 degraded"的噪音。
- **Docker 超时容器残留**：kill CLI 客户端后容器在 daemon 残留。修复为 `--cidfile`（先 `mkstemp` 预留唯一路径再 `unlink`，因 docker 拒绝已存在的 cidfile）+ 超时后 `docker rm -f` 读到的容器 id。
- **cgroup 遗留清扫**：`sweep_stale`（dead pid 目录清理、live pid 不动），`create()` 触发。
- **`_setup_cgroup` catch Exception**：非 OSError 控制器失败也置 degraded。

## Reference Implementation Research

- status: enabled
- reason: 安全沙箱是成熟工程领域，需参考主流 coding agent（Claude Code/Codex）与安全工具（Docker/gVisor、bubblewrap、nsjail）的沙箱实现与命令校验。
- research questions:
  - 主流 coding agent 如何做命令校验与沙箱隔离？
  - Docker 容器作为沙箱的典型实践（--network none/资源限制/超时）？
  - 攻击测试集的最小覆盖集？
- findings:
  - **命令校验可绕过（业界实证）**：Claude Code 2025 三次 CVE 证实正则/glob 校验可被绕过（sed 解析错误写任意文件 CVE-2025-64755；$IFS/短 flag 任意代码执行 CVE-2025-66032；git config 注入 CVE-2025-59041）。issue #6046 明确"任何模式匹配方法无法保证任意 shell 安全"，`npm run test <(rm -rf $HOME/*)` 可绕过 `&&`/`;` 禁令。
  - **业界方向 = 沙箱 + 无 shell 执行**：推荐 Exec tool（直接 subprocess 不经 bash，参数按字面传递）+ OS 级沙箱（AppArmor/SELinux/容器）。Codex 用 argv-based 匹配（非 glob）避免子串误报。连 tree-sitter 静态解析都被认为"注定失败"（混淆如 `$'\x65\x76\x61\x6c'` 可绕）。
  - **Docker 沙箱实践**：`docker run --network none --memory <limit> --cpus` 限制网络/资源，超时 kill；本地已有 alpine/python:3.10-slim/sweb 镜像，Docker daemon 可用（当前用户属 docker 组，用 `sg docker` 访问）。
- design impact:
  - 核心从"完整 AST 句型校验"调整为"**ExecutionBackend 可插拔沙箱 + 轻量命令护栏**"：`ExecutionBackend` 抽象（ProcessBackend/DockerBackend）+ 命令分词 argv 语义校验（护栏）+ 50+ 攻击回归集。
  - 与 #78 约定：沙箱 deny/kill/oom 事件入 trace（结构化 schema）。
  - `SandboxResult`/`BackgroundProcessHandle` 复用为接口返回类型，代码已预留可插拔。

## Risks / Trade-offs

- **[AST 校验误伤合法命令] → 句型白名单可配置扩展，误伤以测试用例覆盖并记录。**
- **[cgroup 平台差异] → 无 cgroup 环境降级为超时/内存警告，不阻塞主流程。**
- **[assert_command_allowed 契约变更波及既有测试] → 契约不变（仍返回 bool/抛错），只升级校验逻辑，回归测试同步。**
- **[容器隔离默认化风险] → 分阶段，本 change 容器作可选后端，避免改变 worktree 隔离与 benchmark 一致性。**
- **[seccomp 平台复杂度] → 作为后续项记录，不阻塞本 change。**

## Testing Strategy

- 单元测试：AST 句型校验（参数类型/范围约束）、cgroup 限制逻辑（mock）、攻击集判定。
- 端到端测试：50+ 恶意 prompt → tool-call → sandbox 拒绝。
- 回归测试：既有 `assert_command_allowed` 测试不回归（契约不变，逻辑升级）。
- benchmark 层级：攻击集接入 benchmark runner（复用 PR #80）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/workspace_policy.py` | assert_command_allowed 升级 AST |
| `agent/tools/sandbox.py` | cgroup v2 资源限制 |
| `agent/tools/builtin/bash.py` | 命令校验链 |
| `agent/tool_permissions.py` | 沙箱拒绝事件结构化 |
| `agent/trace_recorder.py` | deny/kill/oom 事件入 trace |
| `agent/config.py` | sandbox 配置段 |
| `agent/background.py` | 后台任务同套后端 |
| `agent/subagent/manager.py` | 子 agent Bash 同沙箱 |
| `benchmarks/` | 攻击集接入 benchmark |
| 既有测试 | assert_command_allowed 契约变更波及 |
