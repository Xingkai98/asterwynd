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

runner 在执行 Docker-based 任务前 SHALL 做 Docker preflight。若当前环境无法连接 Docker daemon，任务 SHALL 标记为 `unsupported` 状态，并在 artifact 中记录原因；系统 SHALL NOT 回退到“clone + uv venv + pip install”的旧路径。

理由：环境前置条件缺失不等于 agent 失败；但静默回退会让 benchmark 语义再次混乱。

### Decision 3: benchmark 结果模型统一使用 status + reason

benchmark 结果模型 SHALL 使用顶层 `status` 表示结果状态，并使用统一 `reason` 字段表达细节原因。首版至少支持：

- `status=passed`
- `status=passed_with_warnings`
- `status=failed`
- `status=error`
- `status=unsupported`

其中：

- Docker preflight 失败时使用 `status=unsupported`、`reason=docker_unavailable`
- preflight 成功后运行期 Docker 调用失败时使用 `status=error`、`reason=docker_runtime_error`
- 现有 `max_iterations`、`test_failure`、`setup_error` 等归因也统一迁移到 `reason`

`summary.md`、比较报告和分析脚本 SHALL 以 `status` 为主做分类统计，以 `reason` 展示细节；旧的 `failure_category` SHALL 被替换，而不是长期双写兼容。

理由：状态和原因需要解耦；如果继续复用 `failure_category`，会把失败归因和环境不支持混在一起。

### Decision 4: Docker task 通过显式 task metadata 声明

`task.json` SHALL 新增显式字段 `execution_environment`。首版只支持：

- `local`
- `docker`

未显式填写时默认 `local`。当前 `swebench-*` 任务 SHALL 在迁移时统一补为 `docker`；系统 SHALL NOT 依赖 `task_id` 前缀做隐式判断。

理由：任务命名只是约定，不足以作为长期执行语义。

### Decision 5: Docker preflight 结果按 run 缓存

同一次 benchmark run 中，runner 首次遇到 `execution_environment=docker` 的任务时做一次 Docker preflight，并缓存结果供后续 Docker 任务复用。

- 若 preflight 失败，该 run 中全部 Docker 任务都标记为 `unsupported`
- 若 preflight 成功，后续 Docker 任务直接执行，不重复探测

系统首版 SHALL NOT 支持“每个任务重新判断 Docker 当前是否恢复”。

理由：benchmark 更强调同一轮结果的稳定可解释性，而不是环境抖动下的动态重判。

### Decision 6: 薄封装官方 SWE-bench harness

首版 SHALL 对官方 SWE-bench Docker harness 做薄封装，由本仓库 benchmark runner 负责：

- task metadata 映射
- Docker preflight
- patch / artifact 管理
- 状态和原因翻译

系统 SHALL NOT 在本 change 中自研另一套独立 Docker benchmark runner。

理由：避免再次演化出“看起来像 SWE-bench，但与官方语义并不一致”的中间层。

### Decision 7: agent 继续产出 patch，harness 只负责验证

首版仍沿用当前 benchmark 架构：agent runner 在工作区内完成修改，benchmark runner 抓取最终 diff / patch，再交给 SWE-bench Docker harness 做标准容器环境下的验证。

理由：这样可以保留现有多 agent 适配器和 trace / diff / artifact 闭环，不把 agent 调度权交给第三方 harness。

### Decision 8: unsupported 任务仍写核心 artifact 与显式 preflight trace

当任务因 Docker preflight 失败而结束为 `unsupported` 时，系统 SHALL 继续写：

- `result.json`
- `trace.json`
- `runner.log`

但不要求生成：

- `final.diff`
- `test_output.txt`

`trace.json` 中 SHALL 记录显式 `benchmark_preflight` 事件，并最终记录 `completion(status=unsupported)`。

理由：既保留 benchmark 闭环所需的最小诊断 artifact，又不伪造实际上并未发生的 diff / test 阶段输出。

### Decision 9: Docker preflight 缓存挂在 runner，artifact 由 run_task 负责

Docker preflight 的探测结果 SHALL 作为 `BenchmarkRunner` 实例上的 run 级共享状态缓存；`run_task()` 在处理 `execution_environment=docker` 的任务时读取该缓存，并在 preflight 不可用时为当前任务正常写出 `unsupported` artifact。

理由：run 级共享状态和任务级 artifact 各归其位，既方便复用探测结果，也保持 `run_task()` 的闭环职责。

### Decision 10: 首版不容器化 agent 工作环境

对于 `execution_environment=docker` 的任务，agent 仍在当前 benchmark 控制的普通 workspace 内工作；容器只负责标准验证环境。

理由：如果连 agent 工作环境一起 Docker 化，就会同时改动 agent runner、workspace policy、trace、diff 抓取和多 agent 适配器，scope 会显著膨胀。

### Decision 11: 复用现有 git patch / final diff 语义

首版 SHALL 复用现有 `final.diff` / git patch 语义，将 agent 最终修改转成 patch 后交给 Docker harness 验证，而不是发明新的 patch 表达格式。

理由：可以最小侵入地复用现有 artifact 和验证闭环。

### Decision 12: Docker 任务首版保留现有 task schema 字段

对 `execution_environment=docker` 的任务，现有 `external_repo` 和 `version` 字段继续保留。`test_command` 字段首版也继续保留，但不再作为 Docker 任务的主验证入口；最终验证以 Docker harness 结果为准。

理由：避免首版同时做大规模 schema 清理；先把执行语义切对，再决定是否收缩旧字段。

### Decision 13: run-level 统计单独记录 unsupported

`RunMetadata` 和相关 summary / compare / analyze 路径 SHALL 单独统计 `unsupported`，而不是把它并入 `failed`。

理由：否则 task 级已经区分出的环境不支持语义，会在 run 级再次被抹平。

### Decision 14: summary 与 compare 的状态展示顺序

首版展示顺序 SHALL 为：

- `passed`
- `passed_with_warnings`
- `unsupported`
- `failed`
- `error`

理由：`unsupported` 既不是成功，也不是运行失败，放在成功与失败之间最易读。

### Decision 15: Docker preflight 首版只做最小只读探测

Docker preflight 首版只回答“当前 run 是否存在可用的 Docker daemon 接口”，等价于一次最小只读 Docker API 调用是否成功，例如 `docker info`。

首版 SHALL NOT 在 preflight 中额外检查：

- 镜像是否预拉取
- 是否能 build image
- registry 可达性
- 每个任务的磁盘空间充足性

这些问题如果在真实执行阶段出现，统一视为运行期 `docker_runtime_error`。

理由：保持 preflight 语义简单、可解释、可缓存。

### Decision 16: 核心 spec 只要求 preflight，不要求自动起 Docker

benchmark 核心行为只要求“检测 Docker 并使用 Docker”。在某些开发环境下，如果缺少 systemd 或默认 DinD 配置失效，可以通过开发文档和备用脚本提供启动说明，但 benchmark CLI SHALL NOT 对宿主环境负责。

理由：自动起 daemon 会把 benchmark runner 与宿主 init、权限模型和容器能力耦合，失败面过大。

### Decision 17: 环境适配脚本是开发辅助，不是运行时依赖

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
