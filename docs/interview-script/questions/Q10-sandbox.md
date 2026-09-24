# Q10: 安全沙箱——命令护栏、隔离、资源限制

## 讲稿

安全沙箱解决"agent 执行命令时怎么防止它干坏事"。Asterwynd 的安全模型分三层：**工作区策略、命令护栏、执行隔离**（#76）。

**工作区策略**。`WorkspacePolicy` 定义路径/文件/命令安全边界——敏感路径限制、命令 allowlist/denylist。这是第一道闸，任何工具都不能绕过它。

**命令护栏**。`CommandGuard` 做语义级命令校验：扩展 denylist（覆盖常规绕过变体）+ argv 级检查（`rm`、`mv/cp`、`chmod`、`curl/wget`、`timeout` 各自有针对性检查）。比如 `rm -rf /`、`mv` 覆盖 workspace 外文件、`chmod +x` 写 shell、`curl -o` 下载到 workspace 外都会被拦。默认 allow（白名单思维——只拦明确危险的，不拦未知的）。

**执行隔离**。`ExecutionBackend` 可插拔：`process`（subprocess，默认）或 `docker`（容器隔离）。`ProcessBackend` 可用 **cgroup v2** 做 per-run CPU/内存限制——创建子 cgroup、attach pid、超限 oom kill、cleanup。Docker backend 用容器隔离 + 资源限制。

**接线**。`BashTool` 用 CommandGuard 校验 + ExecutionBackend 执行，返回结构化 JSON（exit_code/stdout/stderr/duration_ms/timed_out）。沙箱事件（sandbox_event）入 trace，可观测。

面试重点：这不是"加个 denylist 就完"，而是三层纵深防御——策略层管路径、护栏层管命令语义、隔离层管资源与进程边界，且每层都有攻击回归测试集。

## 代码走读

### 入口与调用链

```
BashTool (agent/tools/builtin/) → CommandGuard.check (agent/tools/command_guard.py:128)
  → ExecutionBackend (agent/tools/sandbox/factory.py:27) → ProcessBackend/DockerBackend
  → cgroup v2 资源限制 (agent/tools/sandbox/cgroup.py)
```

### 关键文件逐段

**`agent/workspace_policy.py` `class WorkspacePolicy`**
- 路径/文件/命令安全边界。
- 定义哪些路径可写、哪些命令可用、哪些是敏感文件。

**`agent/tools/command_guard.py` `class CommandGuard`**
- `check(command)`（128 行）：返回 `CommandVerdict`（allow/deny）。
- 第 1 层：扩展 denylist（`_EXTRA_DENYLIST` 覆盖常规绕过变体，31 行）。
- 第 2 层：argv 级检查——
  - `_check_rm`（213 行）：`rm -rf /` 等危险 rm。
  - `_check_mv_cp`（233 行）：`mv`/`cp` 覆盖 workspace 外文件。
  - `_check_chmod`（244 行）：`chmod +x` 写 shell。
  - `_check_curl_wget`（259 行）：`curl -o`/`wget -O` 下载到 workspace 外。
  - `_check_timeout`（269 行）：`timeout` 命令边界。
- `_has_pipe_to_shell`（166 行）/`_has_protected_redirect`（178 行）：管道/重定向危险检测。
- 默认 allow：只拦明确危险，不拦未知。

**`agent/tools/sandbox/factory.py`**
- `build_execution_backend(name, **kwargs)`（27 行）：按名字构造 ExecutionBackend。
- `_BACKENDS`（15 行）：process / docker 注册表。

**`agent/tools/sandbox/process_backend.py` `class ProcessBackend`**
- subprocess 执行命令，返回结构化结果。
- 支持 cgroup v2 资源限制。

**`agent/tools/sandbox/cgroup.py`**
- `CgroupController`（39 行）：Protocol（create/attach/oom_killed/cleanup）。
- `create`：在当前进程 cgroup 下建子 cgroup（唯一目录名）。
- `attach(pid)`：把子进程 attach 进 cgroup。
- `oom_killed`：检测是否 oom。
- `cleanup`：finally 移除子 cgroup。
- 处理 cgroup v2 细节：cpuset 需显式配置（11 行注释）、`cgroup.kill`（18 行）。

**`agent/tools/sandbox/docker_backend.py` `class DockerBackend`**
- 容器隔离执行 + 资源限制（memory/cpus）。

**`agent/tools/sandbox/base.py` `class ExecutionBackend`**
- 抽象基类，定义执行协议。

**`agent/sandbox_events.py`** — 沙箱事件（sandbox_event）入 trace。

### 设计理由

- **三层纵深防御**：策略层（路径/命令边界）+ 护栏层（命令语义检查）+ 隔离层（进程/容器/cgroup）。单层会被绕过，三层互相补位。
- **默认 allow（白名单思维）**：只拦明确危险的命令模式，不拦未知——避免误伤正常开发命令。这跟"默认 deny"的安全模型权衡，coding agent 场景选择 allow + 精确拦截。
- **命令护栏是语义级而非字符串级**：不只匹配 `rm -rf` 字符串，而是解析 argv 检查语义（`_check_rm` 看 `-rf` 和 `/` 组合），覆盖绕过变体。
- **cgroup v2 资源限制**：进程隔离 + 资源上限，防 agent 命令吃光内存/CPU（`OOM_KILLED` 检测）。
- **可插拔 backend**：process 默认零依赖，docker 需要时启用；`build_execution_backend` 工厂 + 注册表。
