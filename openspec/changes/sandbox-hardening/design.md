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

- 待 planning 阶段（batch-grill-me）确认本设计，并补齐 Reference Implementation Research 实质 findings 与 design impact。

## Reference Implementation Research

- status: enabled
- reason: 安全沙箱是成熟工程领域，需参考主流 coding agent（Claude Code/Codex）与安全工具（Docker/gVisor、bubblewrap、nsjail）的 AST 校验、cgroup、seccomp、攻击测试集实现。
- research questions:
  - 主流 coding agent 如何做命令 AST 校验与沙箱隔离？
  - cgroup v2 限制 CPU/内存的典型实现与超限 kill 语义？
  - seccomp 白名单的 syscall 面与平台差异？
  - 攻击测试集的最小覆盖集？
- findings: 待 planning 阶段补充（proposal 阶段已登记；实质调研在本 change planning 阶段完成）。
- design impact: 待 planning 阶段补充；先决条件：AST 校验契约变更需与既有测试同步，多 workspace 边界为基准。

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
