# Bullet 6: 3 层纵深防御安全体系 — 代码走读

> 简历原文：实现 3 层纵深防御安全体系：工作区路径边界 + 敏感文件 deny 与 mode 权限 fail-closed → CommandGuard 语义级命令检查覆盖绕过变体 → 进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端，配合细粒度工具权限、受控只读浏览器（URL 白名单 + 只读工具集）和人工审批链路

---

## 整体架构

安全体系的 3 层纵深防御，按执行链路从前到后排列：

```
用户指令
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 1: 工作区路径边界 + 敏感文件 deny + mode 权限 fail-closed │
│   WorkspacePolicy  (路径边界 + deny 模式 + 命令黑名单)         │
│   ModePolicy + PermissionProfile  (权限决策 fail-closed)       │
└──────────────────────────┬───────────────────────────────┘
                           │ 通过
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2: CommandGuard 语义级命令检查（覆盖绕过变体）           │
│   正则黑名单扩展 + argv 语义检查 + 高危句式检测                │
│   被 CommandGuard 文档自身定性为 "guardrail, not boundary"     │
└──────────────────────────┬───────────────────────────────┘
                           │ 通过
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 3: 进程沙箱 / Docker 容器隔离（真正的执行边界）          │
│   ProcessBackend + cgroup v2 (CPU/memory 限制 + OOM 检测)    │
│   DockerBackend (网络隔离 + 文件系统隔离 + 资源限制)            │
└──────────────────────────────────────────────────────────┘
```

**旁路防线**（与执行链路正交）：

| 防线 | 文件 | 说明 |
|------|------|------|
| 细粒度工具权限 | `tool_permissions.py` + `run_config.py` | 8 种 Capability + 3 级 Risk + 4 种 Mode |
| 受控只读浏览器 | `browser/policy.py` + `browser/service.py` | URL 白名单 + 默认关闭 + 7 个浏览器工具 |
| 人工审批链路 | `approval.py` + `loop.py:780-853` | 审批请求/响应 + 敏感数据脱敏 |

---

## 第 1 层：工作区路径边界 + 敏感文件 deny + mode 权限 fail-closed

### 1.1 WorkspacePolicy — 路径边界

**文件**：`agent/workspace_policy.py`

核心类 `WorkspacePolicy`（line 140），构造时接受 3 个参数：

```python
def __init__(
    self,
    workspace_root: str | Path | None = None,
    denied_patterns: tuple[str, ...] | list[str] | None = None,
    command_denylist: tuple[str, ...] | list[str] | None = None,
):  # :141-145
```

**路径边界**：`is_within_workspace()`（`:164-168`）检查 path 是否在 `workspace_root` 或 `additional_roots` 内。`assert_within_workspace()`（`:207-211`）若越界则直接抛出 `PermissionError`。

**多根目录支持**：`add_root()`（`:170-190`）允许注册额外工作区根目录，但有 3 层防护：
1. 禁止重复注册已在主 workspace 内的目录（`:173`）
2. 禁止添加主 workspace 的祖先目录，防止开放主 workspace 外的所有文件（`:174-175`）
3. 禁止添加系统敏感目录（`/etc`, `/proc`, `/sys`, `/dev`, `/root`, `/boot`）（`:176-178`）

```python
_DENY_ROOTS = {Path(p) for p in ("/etc", "/proc", "/sys", "/dev", "/root", "/boot")}  # :137
```

### 1.2 敏感文件 deny 模式

**文件**：`agent/workspace_policy.py:9-45`

`DEFAULT_DENIED_PATTERNS` 定义了 **35 条** 默认拒绝的 glob 模式，按类别分：

| 类别 | 模式 | 数量 |
|------|------|------|
| Git 仓库 | `.git`, `.git/**` | 2 |
| 环境变量文件 | `.env`, `.env.*`, `**/.env`, `**/.env.*` | 4 |
| 私钥/Cert | `*.pem`, `*.key`, `*.p12`, `*.pfx` | 4 |
| SSH 密钥 | `id_rsa`, `id_ed25519`, `id_ecdsa`, `**/id_rsa`, `**/id_ed25519`, `**/id_ecdsa` | 6 |
| Python 缓存 | `__pycache__`, `__pycache__/**`, `**/__pycache__/**`, `*.pyc` | 4 |
| Node 依赖 | `node_modules`, `node_modules/**`, `**/node_modules/**` | 3 |
| Python 虚拟环境 | `.venv`, `.venv/**`, `venv`, `venv/**` | 4 |
| 类型/Lint 缓存 | `.mypy_cache`, `.mypy_cache/**`, `.pytest_cache`, `.pytest_cache/**`, `.ruff_cache`, `.ruff_cache/**` | 6 |
| Benchmark 产物 | `benchmarks/runs`, `benchmarks/runs/**` | 2 |

> 每个 `**` 变体单独计数，合计 35 条 glob pattern（9 大类）。benchmark runs 中的 `.env` / `.maestro-ci` 等也会被独立 `.env.*` pattern 覆盖。

`is_denied()`（`:222-239`）执行两层匹配：
1. 对 workspace 内的路径，取相对路径 + 每一级目录名 + 绝对路径名作为候选，逐一 fnmatch 比较（`:231-238`）
2. 对 additional_roots 下的路径，用 basename 匹配（`:225-229`）

`assert_read_allowed()`（`:241-245`）和 `assert_write_allowed()`（`:247-251`）在 is_within_workspace 和 is_denied 两道检查都通过后才放行，拒绝时抛出 `PermissionError`。

### 1.3 命令白名单 + 黑名单

**文件**：`agent/workspace_policy.py:47-134`

`_match_allowlist()`（`:47-72`）定义了 **46 个** 安全命令前缀，按类别：

| 类别 | 前缀 | 数量 |
|------|------|------|
| 版本控制（只读） | `git status`, `git log`, `git diff`, `git show`, `git branch`, `git stash list`, `git stash show` | 7 |
| 测试和构建 | `pytest`, `python -m pytest`, `python3 -m pytest`, `uv run pytest`, `uv run python -m pytest`, `uv run python3 -m pytest`, `uv`, `pip`, `npm test`, `npm run`, `npx`, `yarn`, `cargo`, `make` | 14 |
| 文件查看 | `cat`, `head`, `tail`, `wc`, `sort`, `uniq`, `ls`, `tree`, `find`, `fd`, `rg`, `grep` | 12 |
| 基本工具 | `echo`, `pwd`, `which`, `env`, `df`, `du`, `ps` | 7 |
| 文件操作（低风险） | `mkdir`, `touch` | 2 |
| 包管理 | `pip install`, `pip list`, `pip show`, `pip freeze` | 4 |

> 设计为 **默认关闭**：`_match_allowlist()` 只在 `assert_command_allowed()` 的 denylist 未命中时调用（`:258-259`），作为"黑名单未命中 + 白名单通过 = 放行"的最后一道正面检查。代码注释说明这是一个"软 guardrail，不是硬边界"——真正边界在 sandbox backend。

`DEFAULT_DENYLIST`（`:74-134`）定义了 **59 个** 危险命令正则模式，覆盖：

| 危险类别 | 代表模式 | 数量 |
|------|------|------|
| 递归删除根目录 | `rm -rf /`, `rm -r[f] /`, `rm --recursive /`, `del /[fF] /`, `rmdir /[sS] /` | 5 |
| 格式化/擦除磁盘 | `format`, `mkfs.`, `dd if=`, `dd of=/dev/`, `> /dev/sd[a-z]` | 5 |
| 系统关停 | `shutdown`, `reboot`, `halt`, `poweroff`, `init [06]` | 5 |
| 服务管理破坏 | `systemctl (stop|restart|disable)`, `service ... (stop|restart)` | 2 |
| 进程终止 | `kill -9`, `killall`, `pkill` | 3 |
| Fork bomb | `:(){ :|:& };:` pattern | 1 |
| 任意代码执行 | `perl -e`, `ruby -e`, `php -r`, `python[3] -c`, `python[3] -<<` | 5 |
| 管道到 Shell | `curl\|sh`, `wget\|sh`, `curl\|bash` | 3 |
| 批量文件删除 | `find ... -exec rm`, `find ... -delete`, `xargs rm` | 3 |
| 危险 Git 操作 | `git reset --hard`, `git push --force`, `git branch -D` | 3 |
| 权限修改 | `chmod 777 /`, `chmod -R 777`, `chown -R root` | 3 |
| 写入系统目录 | `> /etc/`, `> /proc/`, `> /sys/`, `tee /etc/`, `tee /proc/`, `sed -i ... /etc\|proc\|sys/` | 6 |
| 移动/复制系统文件 | `cp (etc\|proc\|sys\|.env\|.git/)`, `mv (etc\|proc\|sys\|.env\|.git/)` | 2 |
| 权限提升 | `sudo`, `su -` | 2 |
| 网络/文件系统 | `mount`, `umount`, `iptables`, `nft` | 4 |
| 容器/编排破坏 | `docker rm`, `docker system prune`, `kubectl delete` | 3 |
| SQL 破坏 | `DROP TABLE|DATABASE`, `DELETE FROM ... ;` (无 WHERE) | 2 |
| 命令替换 | `$(...)`, `` `cmd` `` | 2 |

> 第 59 个正则（`` `[^`]*` ``）匹配反引号命令替换。注意第 101 行与第 103 行的 `curl.*\|\s*(ba)?sh` 是重复模式。

### 1.4 mode 权限 fail-closed

**文件**：`agent/tool_permissions.py:179-185` + `agent/run_config.py`

`fail_closed` 是一个内置 `PermissionProfile`：

```python
"fail_closed": PermissionProfile(
    name="fail_closed",
    allowed_capabilities=frozenset(),       # 不放行任何 Capability
    auto_approve_max_risk=ToolRiskLevel.LOW,       # 自动放行 LOW
    approval_required_max_risk=ToolRiskLevel.LOW,  # 审批仅覆盖 LOW
),  # :179-185
```

**fail-closed 含义**：
- `allowed_capabilities=frozenset()` -- 空集合，任何需要 Capability 的工具都会被 DENY。只有无 Capability 要求的工具（如果有的话）才能存活。
- `approval_required_max_risk=ToolRiskLevel.LOW` -- 审批阈值仅到 LOW，MEDIUM 和 HIGH 都直接 DENY。
- 当 mode 没有配置对应 profile 时，`ModePolicy.permission_profile` 属性（`run_config.py:173-182`）**默认返回 `fail_closed`**，即"配置缺失则拒绝一切"。

```python
@property
def permission_profile(self) -> PermissionProfile:
    profile = self.permission_profiles_by_mode.get(
        self.mode,
        BUILTIN_PERMISSION_PROFILES["fail_closed"],  # 默认 fail_closed
    )
    return merge_denied_tools(profile, self.deny_tools_by_mode.get(self.mode, ()))
```

**4 种 Agent Mode**（`run_config.py:18-23`）：

| Mode | Profile | 行为 |
|------|---------|------|
| `BUILD` | `build_default` | 全部 Capability，LOW+MEDIUM 自动放行，HIGH 需审批 |
| `READ_ONLY` | `read_only_default` | 仅 WORKSPACE_READ + NETWORK_READ + AGENT_STATE，LOW 自动放行，MEDIUM 需审批 |
| `PLAN` | `plan_default` | 同上（WORKSPACE_READ + NETWORK_READ + AGENT_STATE），MEDIUM 自动放行 + 审批 |
| `BYPASS` | `bypass_default` | 全部 Capability 全部自动放行（含 HIGH），不产生审批 |

**权限决策链**（`run_config.py:97-171` `decide_tool()`），按优先级：

```
① mode 限制 → tool.allowed_modes 不含当前 mode → DENY
② mode deny_tools 配置 → tool 被显式拒绝 → DENY
③ profile denied_tools → tool 被显式拒绝 → DENY
④ Capability 不在 profile.allowed_capabilities → DENY
⑤ risk <= auto_approve_max_risk → ALLOW
⑥ risk <= approval_required_max_risk → REQUIRE_APPROVAL
⑦ 都不满足 → DENY
```

---

## 第 2 层：CommandGuard 语义级命令检查覆盖绕过变体

**文件**：`agent/tools/command_guard.py`

该文件在设计上被文档自身明确定性（`:2-8`）：

> "This is a **guardrail, not a boundary** (per industry consensus: Claude Code's 2025 CVEs demonstrated that regex command validation is fundamentally bypassable). The real boundary is the execution backend (ProcessBackend / DockerBackend)."

### 2.1 调用链

CommandGuard 在 `BashTool.execute()` 中调用（`agent/tools/builtin/bash.py:73-79`）：

```python
if self._guard.check(cmd) is CommandVerdict.DENY:
    reason = f"command_guard:{self._guard.last_reason or 'denied'}"
    emit_sandbox_event("denied", reason=reason, command=cmd, tool="Bash")
    return ToolResult(text="Error: Command denied by sandbox command guard", error_type="permission_denied")
```

执行顺序：**WorkspacePolicy.assert_command_allowed() 先于 CommandGuard.check()**（bash.py:68-72），WorkspacePolicy 的 blacklist/allowlist 是第一道防线，CommandGuard 是第二道。再之后才是 sandbox backend 执行。

### 2.2 轻量级命令分词器

`tokenize_command()`（`:68-113`）是一个**非完整 Bash 解析器**——支持单/双引号、管道、重定向、分号的 token 分割，但不解析 heredoc、进程替换 `<(cmd)`、brace expansion 等复杂语法。设计目标是足够的 argv 级精度，用于后续语义检查。

### 2.3 扩展黑名单——绕过变体覆盖

`_EXTRA_DENYLIST`（`:32-60`）定义了 **18 个** 额外正则模式，专门覆盖基础 denylist（`workspace_policy.py` 的 `DEFAULT_DENYLIST` 42 个）未能捕获的绕过变体：

| 绕过类别 | 原始变体能被绕过的原因 | 扩展覆盖 | 行号 |
|------|------|------|------|
| `rm` flag 重排 | `rm -fr /` vs `rm -rf /`（原只匹配 `rm -rf`） | `rm -[a-z]*f[a-z]*r[a-z]*` + `rm` with `--` | `:33-35` |
| `chmod` 八进制/符号变体 | 原只匹配 `chmod 777 /` | 0?[0-7]{3,4} (前导零), 符号模式 `[a-z+=]+` 组合 | `:37-38` |
| `kill` 信号名变体 | 原只匹配 `kill -9` | `kill -(SIGKILL\|KILL\|9)\s+\d+` | `:40` |
| 任意代码执行 | 原缺 `node -e`, `deno eval`, `awk ... system()` | 新增 node/deno/awk 模式 | `:42-44` |
| base64 管道到 shell | 原 `curl\|sh` 没覆盖 base64 | `base64 -d \| (ba)?sh` | `:46` |
| mv/cp 目标落在保护路径 | 原只匹配 "移动文件到 /etc" 不精确 | 完整保护路径 + 隐藏文件后缀 | `:48` |
| nc 数据外泄 | 原缺 | `nc` + `/dev/tcp/` 反向 shell | `:50-51` |
| fork bomb | 原缺 | `:(){ :` pattern | `:53` |
| `$IFS` 变量空格绕过 | `rm$IFS/` 等价于 `rm /` | `\$IFS` literal | `:55` |
| 反斜杠逃逸命令名 | `r\m` 在某些 shell 中等价于 `rm` | `\\[a-z]\s` | `:57` |
| 资源耗尽 | 原缺 | `yes > /dev/null` (无限写 null) | `:59` |

### 2.4 argv 语义检查

`_check_argv()`（`:190-211`）对 7 个危险命令做逐 token 语义级检查：

| 命令 | 检查方法 | 逻辑 | 行号 |
|------|------|------|------|
| `rm` | `_check_rm()` | 仅当 `-r` + `-f` 同时存在时检查目标是否命中 `_DENY_PATHS` 或 workspace 外路径。`$IFS` 变体归一化后再判断 | `:213-231` |
| `mv` / `cp` | `_check_mv_cp()` | 目标以 `_DENY_PATHS` 前缀开头 → DENY | `:233-242` |
| `chmod` | `_check_chmod()` | 目标以 `_DENY_PATHS` 前缀开头 → DENY。0777/777/a+rwx/a=rwx 在 `/` 或 `/tmp` → DENY | `:244-257` |
| `timeout` | `_check_timeout()` | 超时值 0 < t <= 600 秒；然后**递归检查被包装的命令**（`timeout 5 rm -rf /` 不能绕过） | `:269-287` |
| `curl` / `wget` | `_check_curl_wget()` | `@<protected-path>` 数据外泄参数 → DENY | `:259-267` |

**`rm` 的特殊处理**（`:139`）：denylist 中的 `rm` 模式被排除（因为 `rm -rf /` 正则会匹配任何包含 `/` 的 workspace 内路径导致误杀），rm 的判断完全交给 argv 语义检查。

### 2.5 高危句式检测

两个独立的高危句式检测方法，不依赖 denylist：

**`_has_pipe_to_shell()`**（`:166-176`）：检测 `| sh` / `| bash` 以及 `/usr/bin/env sh -c` 链路。支持 6 种 shell（`":27": _SHELL_INTERPRETERS = {"sh", "bash", "zsh", "ksh", "dash", "fish"}`）。

**`_has_protected_redirect()`**（`:178-186`）：对 tokenized 命令流检测 `>` / `>>` 后接 `_DENY_PATHS`（`/etc`, `/proc`, `/sys`, `/dev`, `/root`, `/boot`, `/var`——共 7 个，`:25`）。

### 2.6 默认放行设计

`check()`（`:128-162`）的核心逻辑：

```
① rm 以外 → 扩展 denylist 正则扫描 → 命中 → DENY
② 管道到 shell / 重定向到保护路径 → DENY
③ 7 个危险命令 → argv 语义检查 → DENY
④ 未命中 → ALLOW（默认放行）
```

**default-allow 设计**：未知命令默认通过（`:162`），不阻塞合法工作流。防御重心落在**已知危险模式**和**argv 级精确判断**上。

---

## 第 3 层：进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端

### 3.1 可插拔后端抽象

**文件**：`agent/tools/sandbox/base.py`

`ExecutionBackend` Protocol（`:122-156`）定义统一接口：

```python
class ExecutionBackend(Protocol):
    def is_available(self) -> bool: ...
    async def run(self, command: str, *, timeout: float | None = None, cwd: Path | None = None) -> SandboxResult: ...
    async def run_background(self, command: str, *, cwd: Path | None = None) -> BackgroundProcessHandle: ...
```

`SandboxResult`（`:99-107`）携带 7 个字段（`:99-118` 含 `__str__`/`to_json` 方法）：`exit_code`, `stdout`, `stderr`, `duration_ms`, `timed_out`, `oom_killed`, `degraded`。后三个字段是安全关注点。

### 3.2 后端工厂

**文件**：`agent/tools/sandbox/factory.py`

双后端注册表（`:15-18`）：

```python
_BACKENDS: dict[str, type[ExecutionBackend]] = {
    "process": ProcessBackend,
    "docker": DockerBackend,
}
```

`build_execution_backend()`（`:27-38`）根据 `name` 反射构造，自动过滤各后端接收的 kwargs：

| 后端 | 接收参数 |
|------|------|
| `process` | `timeout`, `memory_mb`, `cpus` |
| `docker` | `image`, `memory_mb`, `cpus`, `timeout` |

### 3.3 ProcessBackend + cgroup v2 资源限制

**文件**：`agent/tools/sandbox/process_backend.py`

#### 3.3.1 进程沙箱——进程组隔离

`run()`（`:154-238`）使用 `asyncio.create_subprocess_shell(command, start_new_session=True)`（`:166-173`）创建独立**进程组**（pgid == pid）。超时终止时调用 `_kill_process_tree()`（`:40-54`）：

```python
os.killpg(proc.pid, signal.SIGKILL)  # 杀整个进程组，不留孤儿
```

这确保 `sh -c "sleep 60"` 超时后 shell 和 sleep 都被回收，不会持有管道不释放。

#### 3.3.2 cgroup v2 资源限制

**文件**：`agent/tools/sandbox/cgroup.py`

设计文档注释声明（`:3-10`，引用 design.md Decision 5）：
- 每个 `run()` 创建自己的临时子 cgroup（`asterwynd-{pid}-{counter}`），并发 run 之间不共享 memory budget，不会互相 OOM kill
- `memory.max` + `memory.swap.max=0`（hard no-swap cap），防止 malloc bomb 通过 swap 绕过 OOM killer
- `cpu.max` 配额：`quota = max(1000, round(cpus * 100000))`，period 固定 100ms（`:242-245`）
- cpuset 初始化从父 cgroup 继承（`:248-254`），避免空 cpuset 导致 pid attach 失败（cgroup v2 known gotcha）

**degrade-first 策略**（`:108-130`）：

```python
def _setup_cgroup(self) -> tuple[CgroupController | None, bool]:
    needs_limits = self.memory_mb is not None or self.cpus is not None
    if not needs_limits:
        return None, False                            # 没配置限制 → 跳过
    if not self._cgroup_available():
        self._emit_degraded_once()                    # cgroup 不可用 → degraded
        return None, True
    try:
        controller = self._controller_factory()
        controller.create()
        return controller, False
    except Exception:
        self._emit_degraded_once()                    # 创建失败 → degraded
        return None, True
```

- `_cgroup_available()` 首次调用时 probe：通过 `CgroupV2Controller.is_supported()` 尝试在 `/sys/fs/cgroup` 下创建 + 删除测试 cgroup（`:110-126`），probe 结果缓存。
- 降级时 `degraded` 事件**每 ProcessBackend 实例最多 emit 一次**（`:132-135`），避免日志风暴。
- 每个 `run()` 的 `SandboxResult.degraded` 仍会准确标记该次执行的降级状态（`:118-131`）。

**OOM 检测**（`cgroup.py:256-264`）：`oom_killed()` 比较 `memory.events` 中 `oom_kill` 计数器的**累积值 vs 创建时基线**（counter 永不递减），因此能精确判断是否有进程被 OOM 杀死。

**pid 复用防护**（`cgroup.py:197-212`）：`cleanup()` 在发出 `cgroup.kill` 前验证 `_pid_starttime()`（读取 `/proc/{pid}/stat` 中的 starttime 字段——`:66-85`）与创建时记录的基线一致，避免 pid 被复用后误杀无关进程。

#### 3.3.3 注意：cgroup 需要配置启用

`memory_mb` / `cpus` 在 `SandboxConfig`（`config.py:235-236`）中**默认 `None`**，即默认不启用资源限制。需要通过 `asterwynd.yaml` 的 `sandbox.memory_mb` 和 `sandbox.cpus` 配置才会生效：

```yaml
sandbox:
  memory_mb: 512    # 需显式配置
  cpus: 1.0         # 需显式配置
```

### 3.4 DockerBackend — 容器隔离

**文件**：`agent/tools/sandbox/docker_backend.py`

DockerBackend 提供真正的容器级安全边界：

| 隔离维度 | 机制 | Docker flag | 代码行 |
|------|------|------|------|
| 网络 | 无网络，不能外泄数据或访问外部 | `--network none` | `:103` |
| 文件系统 | 仅挂载 workspace 目录 | `-v <workspace>:/workspace -w /workspace` | `:115` |
| 资源 | CPU/内存限制（同 cgroup，需要 Docker daemon 启用 cgroup v2 domain controller） | `--memory` / `--cpus` | `:110-113` |
| 生命周期 | 运行后自动删除容器 | `--rm` | `:102` |
| 超时 | `docker kill` 杀掉超时容器 | asyncio.wait_for + proc.kill + rm orphan | `:143-169` |

**资源限制默认关闭**（`:80`）：`memory_mb: int | None = None`, `cpus: float | None = None`。注释说明原因（`:77-79`）："Some hosts (incl. this dev environment) do not configure cgroup v2 domain controllers, causing docker run to fail."

**sg docker 适配**（`:32-64`）：`_needs_sg()` 检测 `docker info` 能否直接连接 daemon；如果不能，通过 `sg docker -c "<command>"` 方式包装——适配宿主机 supplementary group 不包含 `docker` 的场景。

**超时孤儿容器清理**（`:185-202`）：通过 `--cidfile` 机制记录容器 ID，超时后 `docker rm -f` 清理因 `docker client` 被 SIGKILL 而残留 daemon 中的容器。

### 3.5 双后端切换

**文件**：`agent/config.py:224-237`

```python
class SandboxConfig:
    backend: str = "process"        # "process" 或 "docker"
    image: str = "alpine:latest"    # docker 后端用的镜像
    memory_mb: int | None = None    # 可选，需 cgroup v2
    cpus: float | None = None       # 可选，需 cgroup v2
    timeout_seconds: float = 30.0
```

默认为 `process` 后端。切换到 docker 需在 `asterwynd.yaml` 中配置 `sandbox.backend: docker`。

**后端不可用时的 fail-fast**（`factory.py:48-68`）：`build_sandbox_from_config()` 在构建后端后检查 `is_available()`，Docker 不可用时 **抛出 RuntimeError 而不是静默退回 ProcessBackend**——静默降级会丢失用户期望的容器隔离。

### 3.6 Sandbox 事件可观测

**文件**：`agent/sandbox_events.py`

所有 sandbox 组件通过 `emit_sandbox_event()`（`:64-81`）发送 4 类结构化事件到 trace 层：

| 事件 | 含义 | 触发位置 |
|------|------|------|
| `denied` | 命令被 workspace policy 或 command guard 拒绝 | `bash.py:70,75` |
| `kill` | 超时后被 kill | `process_backend.py:203`, `docker_backend.py:157` |
| `oom` | OOM killer 介入 | `process_backend.py:186,210` |
| `degraded` | cgroup 不可用，降级为无限制 | `process_backend.py:135` |

事件经 `contextvars.ContextVar` 传递到每次 run 的 trace recorder（`:37-38`），支持并行+后台执行的 trace 关联（通过 `tool_call_id` contextvar）。

---

## 防线 A：细粒度工具权限

**文件**：`agent/tool_permissions.py` + `agent/run_config.py`

### A.1 权限模型

**8 种 ToolCapability**（`:7-15`）：

```python
class ToolCapability(str, Enum):
    WORKSPACE_READ = "workspace_read"
    WORKSPACE_WRITE = "workspace_write"
    COMMAND_EXECUTE = "command_execute"
    NETWORK_READ = "network_read"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    AGENT_STATE = "agent_state"
    SUBAGENT_CONTROL = "subagent_control"
    BROWSER_CONTROL = "browser_control"
```

**3 级 ToolRiskLevel**（`:18-21`）：`LOW`, `MEDIUM`, `HIGH`。

**4 种 ToolOrigin**（`:24-29`）：`BUILTIN`, `MCP`, `PLUGIN`, `SUBAGENT`, `BROWSER`。

**预定义权限常量**（`:109-141`）为各常见能力组合绑定了风险等级：

| 常量 | Capability | Risk |
|------|------|------|
| `WORKSPACE_READ_PERMISSION` | WORKSPACE_READ | LOW |
| `WORKSPACE_WRITE_PERMISSION` | WORKSPACE_WRITE | MEDIUM |
| `COMMAND_EXECUTE_PERMISSION` | COMMAND_EXECUTE | HIGH |
| `NETWORK_READ_PERMISSION` | NETWORK_READ | LOW |
| `AGENT_STATE_PERMISSION` | AGENT_STATE | MEDIUM |
| `SUBAGENT_CONTROL_PERMISSION` | SUBAGENT_CONTROL | MEDIUM |
| `BROWSER_READ_PERMISSION` | BROWSER_CONTROL | MEDIUM |

### A.2 只读能力集

**文件**：`agent/tool_permissions.py:98-102`

```python
READ_ONLY_CAPABILITIES = frozenset({
    ToolCapability.WORKSPACE_READ,
    ToolCapability.NETWORK_READ,
    ToolCapability.AGENT_STATE,
})
```

**3 种 Capability**，不含 WORKSPACE_WRITE、COMMAND_EXECUTE、EXTERNAL_SIDE_EFFECT。READ_ONLY / PLAN mode 共用此集。

### A.3 6 个内置 PermissionProfile

**文件**：`agent/tool_permissions.py:144-185`

| Profile | allowed_capabilities | auto_approve | approval_required |
|------|------|------|------|
| `build_default` | 全部 8 种 | MEDIUM | HIGH |
| `build_legacy_auto_high_risk` | 全部 8 种 | HIGH | HIGH |
| `bypass_default` | 全部 8 种 | HIGH | HIGH |
| `read_only_default` | 3 种（只读） | LOW | MEDIUM |
| `plan_default` | 3 种（只读） | MEDIUM | MEDIUM |
| `fail_closed` | 0 种（空） | LOW | LOW |

---

## 防线 B：受控只读浏览器

### B.1 浏览器工具默认关闭

**文件**：`agent/config.py:67-79`

```python
class BrowserConfig:
    enabled: bool = False                    # 默认关闭
    url_allowlist: tuple[str, ...] = ()      # 空白名单 = 拒绝所有
    idle_timeout: int = 300
    navigation_timeout: int = 30
    read_timeout: int = 15
    screenshot_timeout: int = 10
```

浏览器工具只在 `enabled=True` 且 playwright 已安装时才注册（`factory.py:357-358`），否则不暴露给 Agent。

### B.2 URL 白名单

**文件**：`agent/browser/policy.py`

`BrowserPolicy.is_url_allowed()`（`:38-61`）实现 3 层检查：

```
① 空白名单 → 拒绝所有 URL                             (:46-47)
② 非 http/https scheme → 拒绝                         (:53-54)
③ http:// 只能由白名单中显式 http 条目放行               (:57-58)
④ https:// 匹配 bare domain 或 https 条目               (:61)
```

**域名匹配**（`_host_matches()`, `:98-111`）：

| 白名单模式 | 匹配 | 不匹配 |
|------|------|------|
| `docs.python.org` | `docs.python.org` | `sub.docs.python.org` |
| `*.example.com` | `sub.example.com` | `example.com`（缺少前导 `.`） |

### B.3 只读工具集

**文件**：`agent/tools/builtin/browser_tools.py:14-22`

`BROWSER_TOOL_CLASSES` 包含 **7 个**工具：

| 工具 | 类 | 能力 |
|------|------|------|
| WebNavigate | `BrowserNavigateTool` | 导航到 URL（受 is_url_allowed 约束） |
| WebGetContent | `BrowserGetContentTool` | 读取页面文本 |
| WebScreenshot | `BrowserScreenshotTool` | 截取页面截图 |
| WebScroll | `BrowserScrollTool` | 滚动页面 |
| WebListTabs | `BrowserListTabsTool` | 列出标签页 |
| WebSwitchTab | `BrowserSwitchTabTool` | 切换标签页 |
| WebCloseTab | `BrowserCloseTabTool` | 关闭标签页 |

全部 7 个工具共享 `BROWSER_READ_PERMISSION`（`ToolCapability.BROWSER_CONTROL`, `ToolRiskLevel.MEDIUM`）——MEDIUM 风险在 read_only mode 下需要审批。

**没有写入/提交/下载工具**：浏览器工具集中不包含表单填写、文件上传、数据提交等能力。所有导航操作在 `BrowserSession.navigate()` 处被 `assert_url_allowed()` 拦截（`session.py:32`），超时不抛异常而是返回 error 字典（`:39-51`）。

### B.4 浏览器架构安全性

**惰性启动**（`service.py:53`）：浏览器仅在首次工具调用时才启动，不预启动；Playwright 导入也延迟到启动时（`:58-65`），避免在只做代码分析的 session 中引入不必要的浏览器运行时。

**产物隔离**（`policy.py:115-117`）：浏览器产物目录仅限于 `<workspace_root>/.asterwynd/browser-artifacts/`，由 `WorkspacePolicy.assert_write_allowed()` 守卫。

---

## 防线 C：人工审批链路

**文件**：`agent/approval.py`

### C.1 审批请求/响应模型

`ApprovalRequest`（`:34-68`）携带完整决策上下文：

```python
@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str       # UUID
    tool_call_id: str
    tool_name: str
    mode: str              # BUILD / READ_ONLY / PLAN / BYPASS
    capability: list[str]  # 工具所需 Capability 列表
    risk: str              # LOW / MEDIUM / HIGH
    origin: str            # BUILTIN / MCP / PLUGIN / SUBAGENT / BROWSER
    reason: str            # 审批原因（来自 PermissionDecision）
    profile_name: str      # 当前生效的 profile 名
    redacted_args: dict    # 已脱敏的参数
    args_summary: str      # 参数摘要（限 2000 字符）
```

`ApprovalResponse`（`:71-79`）三种状态：`APPROVED`, `DENIED`, `UNAVAILABLE`。

### C.2 Fail-Closed 审批处理器

**文件**：`agent/approval.py:87-93`

```python
class FailClosedApprovalHandler:
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        return ApprovalResponse(
            approval_id=request.approval_id,
            status=ApprovalDecisionStatus.UNAVAILABLE,  # 永远 UNAVAILABLE
            reason="approval is unavailable in this runtime",
        )
```

`UNAVAILABLE` 在 AgentLoop 的处理中（`loop.py:831-853`）等价于**拒绝**：`pre_denied_error_type = "approval_unavailable"`，工具不执行。这是在非交互式环境（如 benchmark / CI / 无 TTY）下的 fail-closed 行为。

### C.3 CLI 交互式审批

**文件**：`agent/approval.py:96-120`

```python
class CliApprovalHandler:
    def __init__(self, *, interactive: bool):
        self.interactive = interactive

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        if not self.interactive or not sys.stdin.isatty():
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.UNAVAILABLE,  # 非交互 → fail-closed
            )
        print(_render_cli_prompt(request), file=sys.stderr)
        answer = input("Approve? [y/N] ").strip().lower()
        if answer in {"y", "yes"}: ...
```

**默认答案 `N`**（`:109`）：用户输入回车不做明确选择时，行为等同拒绝。

### C.4 敏感数据脱敏

**文件**：`agent/approval.py:15-23, :160-189`

审批请求展示前自动脱敏 3 层：

| 层级 | 机制 | 代码位置 |
|------|------|------|
| Key 名检测 | 参数 key 含 `key\|token\|secret\|password\|credential\|authorization\|api_key` → 整个 value 替换为 `[redacted]` | `:15-18` + `:165-167` |
| 字符串模式 | `Authorization: Bearer ...` / `sk-...` / `api_key=...` → 匹配部分替换为 `[redacted]` | `:19-23` + `:176-178` |
| 参数长度限制 | JSON 序列化超过 2000 字符时截断 | `:25` + `:152-157` |

### C.5 审批在 AgentLoop 中的接线

**文件**：`agent/loop.py:780-853`

审批决策仅在 `PermissionDecision.type == REQUIRE_APPROVAL` 时触发（`:788`）。审批被拒/不可用时工具不执行，`pre_denied_result` 注入 messages 供模型观察（`:833-853`）。审批成功（`approval_granted=True`）则工具正常进入 Phase 2 执行（`:858`）。

---

## 关键文件索引

| 文件 | 内容 | 防御层 |
|------|------|------|
| `agent/workspace_policy.py` | WorkspacePolicy: 路径边界 + deny 模式 + 命令黑白名单 | Layer 1 |
| `agent/tool_permissions.py` | ToolCapability (8) / ToolRiskLevel (3) / PermissionProfile (6) / 预定义权限 | 防线 A |
| `agent/run_config.py` | AgentMode (4) / ModePolicy / fail_closed 默认 / 权限决策链 | Layer 1 + 防线 A |
| `agent/tools/command_guard.py` | CommandGuard: tokenizer + 扩展黑名单 (18) + argv 语义检查 (7 命令) + 高危句式 | Layer 2 |
| `agent/tools/sandbox/base.py` | ExecutionBackend Protocol + SandboxResult + BackgroundProcessHandle | Layer 3 |
| `agent/tools/sandbox/process_backend.py` | ProcessBackend: 进程组隔离 + cgroup v2 集成 + degrade-first | Layer 3 |
| `agent/tools/sandbox/cgroup.py` | CgroupV2Controller: memory.max + swap.max + cpu.max + cpuset + cleanup pid-reuse guard | Layer 3 |
| `agent/tools/sandbox/docker_backend.py` | DockerBackend: --network none + -v mount + --rm + orphan cleanup | Layer 3 |
| `agent/tools/sandbox/factory.py` | build_execution_backend: process/docker 双后端工厂 + fail-fast | Layer 3 |
| `agent/sandbox_events.py` | SandboxEventSink: denied/kill/oom/degraded 事件 + contextvars | Layer 3 (可观测) |
| `agent/config.py` | SandboxConfig / BrowserConfig / PermissionsConfig / ToolsConfig | 配置入口 |
| `agent/tools/builtin/bash.py` | BashTool: 三层检查调用链（policy → guard → sandbox） | 接线点 |
| `agent/browser/policy.py` | BrowserPolicy: URL 白名单 + host_matches（精确 / 通配符） | 防线 B |
| `agent/browser/service.py` | BrowserService: 惰性启动 + 标签页生命周期 | 防线 B |
| `agent/browser/session.py` | BrowserSession: 策略约束的页面操作 + 超时容错 | 防线 B |
| `agent/tools/builtin/browser_tools.py` | BROWSER_TOOL_CLASSES: 7 个只读浏览器工具 | 防线 B |
| `agent/approval.py` | ApprovalRequest/Response + FailClosedApprovalHandler + CliApprovalHandler + 脱敏 | 防线 C |
| `agent/loop.py:780-853` | Phase 1 审批接线：审批请求 → 响应 → 预拒绝结果回填 | 防线 C |
