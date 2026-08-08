# W06 · 3 层纵深防御安全体系

**对应简历 bullet 6**：*"实现 3 层纵深防御安全体系：工作区路径边界 + 敏感文件 deny 与 mode 权限 fail-closed → CommandGuard 语义级命令检查覆盖绕过变体 → 进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端，配合细粒度工具权限、受控浏览器沙箱和人工审批链路"*

## 代码入口与分层

```
第 1 层：WorkspacePolicy（agent/workspace_policy.py）
  ├─ 路径边界：is_within_workspace / assert_within_workspace / add_root
  ├─ 敏感文件 deny：DEFAULT_DENIED_PATTERNS（.git/.env/*.pem/id_rsa/...）
  └─ 命令拒绝列表：DEFAULT_DENYLIST（58 个危险模式）

第 2 层：CommandGuard（agent/tools/command_guard.py）
  └─ 语义级命令校验（tokenize + argv 语义检查 + 高危句式）

第 3 层：沙箱 ExecutionBackend（agent/tools/sandbox/）
  ├─ ProcessBackend（子进程 + cgroup v2 资源限制）
  └─ DockerBackend（容器隔离，--network none）

配套：
  ├─ 细粒度工具权限：tool_permissions.py（8 能力 + 3 风险 + 5 profile）
  ├─ 审批链：approval.py（3 种 handler + 脱敏）+ run_config.py ModePolicy（5 级决策链）
  └─ 浏览器沙箱：browser/policy.py（受控导航策略）
```

## 核心逻辑

### 第 1 层 · WorkspacePolicy

**核心心智：路径是边界，命令是最后防线。**

- **路径边界**（is_within_workspace，workspace_policy.py:164）：resolve 后 relative_to 校验，所有文件工具过 assert_within_workspace。
- **add_root 祖先守卫**（workspace_policy.py:170-190）：禁止添加 workspace 祖先目录（"会开放主 workspace 外的所有文件访问"），禁止添加 /etc、/proc、/sys 等系统敏感目录。
- **敏感文件 deny**（DEFAULT_DENIED_PATTERNS）：.git/**、.env*、*.pem、id_rsa、__pycache__ 等，读写都拒。
- **命令拒绝列表**（DEFAULT_DENYLIST）：rm -rf /、chmod 777 /、curl|sh、$(cmd)、sudo、git reset --hard、git push --force 等 58 个模式。

**面试澄清**：简历"mode 权限 fail-closed"——`fail_closed` profile 是 `allowed_capabilities=∅`（tool_permissions.py:179-184），无任何能力 → 全部工具 DENY。它不直接是默认行为，而是兜底：某 mode 无匹配 profile 时落到 fail_closed（run_config.py:177）。

### 第 2 层 · CommandGuard

**核心心智：guardrail 不是 boundary**（docstring 引用 Claude Code 2025 CVEs：正则命令校验根本可绕过）。

- **默认放行 + 拒绝列表扩展**：基础 denylist + _EXTRA_DENYLIST 覆盖已知绕过变体：
  - rm flag 重排/拆开/`--` 分隔（rm -fr vs rm -rf）
  - chmod 八进制/符号变体
  - kill -SIGKILL、base64 -d | bash、node -e、nc、/dev/tcp/、fork bomb `:(){`、$IFS 变量绕过、反斜杠转义命令名
- **argv 语义检查**（_check_argv）：rm -rf 目标在受保护路径/workspace 外 → DENY；mv/cp 目标进受保护路径 → DENY；`timeout` 递归检查被包命令（timeout 5 rm -rf / 逃不掉）；curl @/etc/passwd 数据外传 → DENY。
- **高危句式**：pipe-to-shell（<cmd> | sh）、redirect 进受保护路径（> /etc/）。

### 第 3 层 · 沙箱双后端

**真正隔离边界（boundary），前两层是 guardrail。**

| | ProcessBackend | DockerBackend |
|---|---|---|
| 隔离 | 子进程（host） | 一次性容器 |
| 网络 | host 网络（无隔离） | --network none（不能外传/连外网） |
| 资源限制 | cgroup v2（memory.max + swap.max=0 + cpu.max + cpuset） | --memory/--cpus |
| 文件系统 | host（受 WorkspacePolicy 管） | 只挂载 workspace：-v <ws>:/workspace |
| 超时 | wait_for + kill 进程组 | wait_for + docker kill + 清孤儿容器 |

**ProcessBackend + cgroup v2 细节（process_backend.py + cgroup.py）**：
- **每个 run 独立子 cgroup**（cgroup.py:165）：并发 run 不共享内存预算、不互相 OOM-kill。
- **memory.swap.max=0 硬禁 swap**（cgroup.py:237）：malloc 炸弹不能靠 swap 绕过 OOM killer。
- **pid-reuse 守卫**（cgroup.py:204-207）：cleanup 用 starttime 校验 pid 还是我们的进程才 cgroup.kill。
- **degrade-first**（process_backend.py:8-13）：host 不支持 cgroup 时降级为纯 timeout，SandboxResult.degraded=True + 一次性 degraded 事件——**绝不静默声称限制了**。
- **start_new_session=True + killpg 杀整组**（process_backend.py:40-54）：超时后杀 shell 及全部后代，防孤儿进程占管道。

**DockerBackend 细节（docker_backend.py）**：
- --cidfile 处理超时后 CLI 被杀留下的孤儿容器（SIGKILL docker client 不会停容器）。
- 当前用户须在 docker 组；_needs_sg() 处理 shell 补充组过期。

### 细粒度工具权限（tool_permissions.py + run_config.py）

**8 能力**：workspace_read/write、command_execute、network_read、external_side_effect、agent_state、subagent_control、browser_control。
**3 风险**：low/medium/high。
**5 profile**（tool_permissions.py:144-185）：build_default（auto MEDIUM）、build_legacy_auto_high_risk（auto HIGH）、bypass_default（auto HIGH）、read_only_default（只读 LOW）、plan_default（只读 MEDIUM）、fail_closed（∅ 能力 LOW）。

**5 级决策链**（run_config.py:97-171 decide_tool）：allowed_modes → deny_tools_by_mode → profile.denied_tools → capabilities ⊆ allowed → risk ≤ auto_approve → risk ≤ approval_required → 否则 DENY。

**执行时二次校验**（registry.py:137-156 execute）：审批通过后执行前再跑 decide_tool，防绕过。

### 审批链（approval.py + web/session.py:75）

- 3 种 handler：CliApprovalHandler（交互终端）、WebApprovalHandler（web/session.py:75，WebSocket + asyncio.Future 桥接）、FailClosedApprovalHandler（无交互直接拒）。
- **WebApprovalHandler 细节**（web/session.py:86-134）：`request_approval` 创建 Future 并 await（阻塞直到浏览器响应）；`submit_response` 归一化 decision（approved/approve/allow/yes/y → APPROVED）；`fail_pending` 在 session reset 时把挂起审批置 UNAVAILABLE（web/server.py:399）；**单槽**——同一时刻只允许一个 pending，重复请求直接返回 UNAVAILABLE。
- **参数脱敏**（redact_value，approval.py:160）：SENSITIVE_KEY_PATTERN（key/token/secret/password/credential/authorization/api_key）key 脱敏 + 字符串模式（Bearer/sk-/api_key=）+ ImageBlock 降级为文件引用。**审批时 LLM 看到的 args 已脱敏**（loop.py:786-790）。

### 受控浏览器沙箱（browser/policy.py）

BrowserPolicy 做浏览器安全策略，核心是 **URL 白名单**（policy.py:38-111）：
- **空白名单拒绝所有 URL**（fail-closed）。
- **默认只放 https**；http 必须白名单中有显式 `http://` 条目才放行。
- 域名匹配支持精确（`docs.python.org`）+ 通配子域名（`*.example.com` 匹配 `sub.example.com` 不匹配 `example.com`）。
- 产物路径 `<workspace>/.asterwynd/browser-artifacts/` 委托 WorkspacePolicy 校验写入。
- 配合 `BROWSER_READ_PERMISSION`（tool_permissions.py:137，BROWSER_CONTROL/MEDIUM）。

## 简历核实

| 简历 | 核实 | 结论 |
|------|------|------|
| "3 层纵深防御" | policy → guard → sandbox 三层 | ✅ |
| "工作区路径边界 + 敏感文件 deny" | workspace_policy 吻合 | ✅ |
| "mode 权限 fail-closed" | fail_closed profile（∅ 能力） | ✅（注意表述） |
| "CommandGuard 语义级命令检查覆盖绕过变体" | _EXTRA_DENYLIST + argv 语义检查 | ✅ |
| "进程沙箱 + cgroup v2 / Docker 容器隔离双后端" | ProcessBackend+cgroup / DockerBackend | ✅（双后端二选一，非叠加） |
| "细粒度工具权限、受控浏览器沙箱、人工审批链路" | tool_permissions + browser/policy + approval | ✅ |

## 面试加分点

1. **"guardrail 不是 boundary"**——引用 Claude Code 2025 CVE，真正的边界是执行后端。
2. **degrade-first 绝不静默**——cgroup 不可用降级 + degraded=True + 事件。
3. **pid-reuse 守卫 + swap 硬禁**——深挖级证据。
4. **timeout 递归检查被包命令**——timeout 5 rm -rf / 逃不掉。
