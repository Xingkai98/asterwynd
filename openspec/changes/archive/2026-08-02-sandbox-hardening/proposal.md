# Proposal: 安全沙箱做深 — AST 命令校验 + cgroup 资源限制 + 攻击测试集

## Change Type

primary: feature
secondary:
  - security
  - tools
  - agent-runtime

## 需求

1. bash 命令 AST 校验：先解析 shell AST，只允许预定义句型（如"复制文件 A 到 B"），参数做类型+范围约束
2. cgroup v2 资源限制：限制 CPU/内存，超限自动 kill + 记录
3. 攻击测试集：构建 50+ 恶意 prompt 回归用例（rm -rf /、读取 /etc/passwd、curl 外传数据等）
4. （后置，非本 change 必交付）容器隔离：Docker/gVisor 替换子进程，作可选后端而非默认

## 背景

当前安全是"正则 denylist + 前缀 allowlist + subprocess"两层防线，无内核级隔离。`WorkspacePolicy.assert_command_allowed()` 用字符串前缀匹配，`SandboxExecutor` 用 `subprocess(shell=True)`，`max_memory_mb` 存而不用。已知绕过面在 `2026-06-21-tighten-bash-command-policy/design.md` 中被记为"完整 parser 或沙箱隔离另立 change"（即本 issue）。

5/8 场面试直接问到安全沙箱实现。

## 非目标

- 不把容器隔离（Docker/gVisor）设为默认后端（分阶段：本 change 先做 AST + cgroup + 攻击集，容器作可选后端）。
- 不重做 WorkspacePolicy 路径边界（`additional_roots` 多 workspace 已由 add-workspace-param 合入）。
- seccomp 兜底（内核 syscall 白名单）若涉及平台差异大，作为后续项记录。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/workspace_policy.py` | `assert_command_allowed` 从字符串前缀升级为 AST 校验 |
| `agent/tools/sandbox.py` | cgroup v2 资源限制（max_memory_mb 从存而不用到生效） |
| `agent/tools/builtin/bash.py` | 命令校验 → AST → 执行链 |
| `agent/tool_permissions.py` | 沙箱拒绝事件结构化 |
| `agent/trace_recorder.py` | 沙箱 deny/kill/oom 事件入 trace |
| `agent/config.py` | sandbox 配置段（AST 开关/资源上限/攻击集路径） |
| `agent/background.py` | 后台任务与 Bash 共用沙箱，需同套后端 |
| `agent/subagent/manager.py` | 子 agent Bash 在同一沙箱下 |
| `benchmarks/` | 攻击测试集可接入 benchmark（复用 PR #80 runner） |
| 既有测试 | `assert_command_allowed` 契约变更会波及依赖函数的所有测试 |

## Reference Implementation Research

- status: enabled
- reason: 安全沙箱（bash AST 校验、cgroup v2、seccomp、攻击测试集）是安全工程成熟领域，应参考主流 coding agent 与安全工具的沙箱实现（Docker/gVisor、Claude Code 沙箱、bubblewrap、nsjail）。
- research questions:
  - 主流 coding agent（Claude Code/Codex）如何做命令 AST 校验与沙箱隔离？
  - cgroup v2 限制 CPU/内存的典型实现与超限 kill 语义？
  - seccomp 白名单的 syscall 面与平台差异？
  - 攻击测试集的典型覆盖集与最小化原则？
- findings:
  - 待 planning 阶段补充（本 proposal 阶段完成 status/reason/questions 登记；实质调研在本 change 的 planning 阶段完成）。
- design impact:
  - 待 planning 阶段补充；先决条件：add-workspace-param（已合入）的多 workspace 边界为基准，AST 校验契约变更需与既有测试同步。

## Dependencies

- 依赖 add-workspace-param（已合入）：多 workspace 边界为沙箱基准。
- 与 #77 工具治理共享工具执行链（BashTool.execute → WorkspacePolicy → SandboxExecutor）。
- 攻击测试集可复用 PR #80 的 benchmark runner（已合入）。

## 验收

- 能对 50+ 攻击样例给出拦截结果，且读写/执行的边界可测试。
- 面试可引用阻断率 100%、syscall 面 <60 条、OOM kill 事件 3s 内入 trace 等硬数据。
