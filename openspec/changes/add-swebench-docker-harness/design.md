## Context

当前 benchmark 系统同时承载两类任务：

- `myagent-*`：针对本仓库的本地 worktree 任务
- `swebench-*`：针对外部仓库的 SWE-bench 风格任务

这两类任务的隔离需求不同。`myagent-*` 任务本身依赖当前仓库工作树和隐藏测试补丁，现有本地 worktree 路径已经足够清晰；`swebench-*` 则更接近官方 SWE-bench 的外部仓库问题修复场景，需要更强的环境隔离与可复现性。

当前实现中，外部任务通过 clone 仓库、读取 `swebench` Python 包常量并在本地创建 `.venv` 安装依赖来运行。它既没有获得官方 Docker harness 的清晰环境边界，也没有在 Docker 不可用时提供明确定义的降级语义。

## Goals / Non-Goals

**Goals:**

- 将 `swebench-*` 外部任务切换到 Docker harness。
- 在 runner 层增加 Docker preflight。
- 当 Docker 不可用时，以显式 `skipped` / `unsupported` 语义结束任务，而不是报 agent 失败。
- 保持 `myagent-*` 任务继续走现有本地 worktree runner。
- 为当前容器开发环境补充文档和备用脚本，但不把这类环境细节写入 benchmark 核心行为规格。

**Non-Goals:**

- 不让 benchmark CLI 自动启动 `dockerd`。
- 不要求所有 benchmark 任务统一 Docker 化。
- 不在本 change 中重做 benchmark 总体 schema 或比较报告系统。
- 不把“当前容器里没有 systemd”当成产品行为的一部分。

## Decisions

### Decision 1: 外部 SWE-bench 风格任务与本地任务继续分流

本 change SHALL 保持两条执行路径：

- 本地 `myagent-*` 任务：继续使用 worktree runner。
- Docker-based 外部任务：使用 SWE-bench Docker harness。

理由：这两类任务的目标和环境边界不同，强行统一只会把本仓库 smoke 和外部仓库评测耦合在一起。

### Decision 2: Docker 不可用时显式 skip，不回退到本地 venv

runner 在执行 Docker-based 任务前 SHALL 做 Docker preflight。若当前环境无法连接 Docker daemon，任务 SHALL 标记为 `skipped` 或等价 `unsupported` 状态，并在 artifact 中记录原因；系统 SHALL NOT 回退到“clone + uv venv + pip install”的旧路径。

理由：环境前置条件缺失不等于 agent 失败；但静默回退会让 benchmark 语义再次混乱。

### Decision 3: skip 是 benchmark 结果模型中的一等状态

benchmark 结果模型 SHALL 增加 `skipped` 或等价显式状态，并允许记录类似 `environment_unavailable` 的原因分类。`summary.md` 和 run-level 统计 SHALL 将其与 `failed`、`error`、`passed_with_warnings` 区分开。

理由：如果把环境不满足塞进 `error` 或 `failed`，就无法正确解释 benchmark 结果，也不利于跨环境比较。

### Decision 4: 核心 spec 只要求 preflight，不要求自动起 Docker

benchmark 核心行为只要求“检测 Docker 并使用 Docker”。在某些开发环境下，如果缺少 systemd 或默认 DinD 配置失效，可以通过开发文档和备用脚本提供启动说明，但 benchmark CLI SHALL NOT 对宿主环境负责。

理由：自动起 daemon 会把 benchmark runner 与宿主 init、权限模型和容器能力耦合，失败面过大。

### Decision 5: 环境适配脚本是开发辅助，不是运行时依赖

可以增加一个仅供开发和验证使用的辅助脚本，例如在无 systemd 容器中手动启动 `containerd + dockerd` 的脚本；该脚本 SHALL 作为开发辅助存在，并在文档中明确其适用场景，不得成为 benchmark 正常运行的唯一生产路径。

理由：这是当前工作环境的特殊约束，不应污染 benchmark 对外规格。

## Risks / Trade-offs

- [Risk] Docker harness 接入后，CI 或某些本地环境没有 Docker daemon。
  Mitigation: preflight + skipped/unsupported artifact，不把环境问题误计为 agent 失败。

- [Risk] 当前 `swebench-*` 任务 schema 与官方 harness 输入格式之间存在映射差异。
  Mitigation: 先定义清晰的 task metadata 和 adapter 层，不把 task.json 直接绑死到某个三方 API。

- [Risk] 引入 `skipped` 状态会影响 summary、统计和比较脚本。
  Mitigation: 在 result model、summary renderer 和 CLI 测试中同时覆盖。

- [Risk] 开发者误以为 helper script 是 benchmark 的一部分。
  Mitigation: 在 design、tasks 和开发文档中明确“辅助脚本 != 核心行为”。

## Testing Strategy

- task schema / runner 测试覆盖 Docker-based 任务分流。
- preflight 测试覆盖 Docker 可用与不可用两条路径。
- result model / summary 测试覆盖 `skipped` 或等价状态的统计与展示。
- CLI benchmark 测试覆盖混合任务集：本地任务继续执行，Docker-based 任务在 Docker 不可用时显式 skip。
- 如环境允许，跑一个最小 `swebench-*` smoke 验证 Docker harness 闭环；如环境不允许，至少用 mock/fake preflight 和 runner 测试覆盖 skip 语义，并在交付说明中注明。
