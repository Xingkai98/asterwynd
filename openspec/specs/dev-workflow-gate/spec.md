# dev-workflow-gate 规格

## Purpose

定义开发流程门禁的**承载边界**：哪些门禁由本仓自建脚本承载、哪些由外部工具 witnessloop 承载、以及从自建切换到接入 witnessloop 的约束。

当前仓库尚未接入 witnessloop：门禁**全部**由本仓自建脚本承载——`scripts/check_openspec_artifacts.py`（change 契约、review manifest 绑定、grill / grill-adversarial / building 证据、受保护写入解释事件、tasks 与归档点完成度）、`scripts/workflow_guard.py`（本地写码前守卫，含 Bash 命令解析）、`scripts/workflow_state.py` 与 `agent/workflow/*`（流程事件投影）、`scripts/platform_gate.py`（合入平台闸门，见 `platform-gate` 能力域）。`master` 的 required status checks 为 `["validate", "benchmark-gate"]`，分支保护语义由 `platform-gate` 能力域描述，本规格不重复。

本规格用规范性语言描述**目标**，不把「尚未接入」写成已落地。

> **退休预告**：本规格在 `witnessloop-adoption` 的**阶段 A 结束时会被覆盖重写**——上面「尚未接入」的占位 Requirement 会被删除，Purpose 段改写为接入后的实际承载形态。先例：`platform-gate` 的实现 commit `f7e912b` 同样覆盖了它自己的占位规格。该 change 的 spec delta 已用 `## REMOVED Requirements` 登记这条退休，并在 `tasks.md` 的 Z.2 规定用**覆盖重写**（而不是只合并 `## ADDED`）的方式同步。

## Requirements

### Requirement: dev-workflow-gate 当前为预留能力域

系统 SHALL NOT 声称已经接入 witnessloop：仓库中 SHALL NOT 存在 `.witnessloop/policy.json`、`.witnessloop/init-manifest.json`、`.github/workflows/witnessloop.yml` 或 `.github/witnessloop-tests.txt`，`master` 的 required status checks SHALL NOT 包含 witnessloop 的 `gate / check`。

#### Scenario: 当前门禁承载方式

- **GIVEN** 用户使用当前仓库
- **WHEN** 查看 CI 与本地守卫
- **THEN** 系统 SHALL 只提供自建门禁（`validate` / `benchmark-gate` 两个 required job + `scripts/` 下的 checker 与守卫）
- **AND** `.github/workflows/` 下 SHALL 只有 `ci.yml`

#### Scenario: 尚未接入时的受保护写入判定

- **WHEN** 某 change 写入 `openspec/specs/**` 或 `docs/openspec-change-backlog.md`
- **THEN** 该写入 SHALL 由本仓 `scripts/flow-policy.json` 的规则表与 `scripts/check_openspec_artifacts.py` 判定
- **AND** 判定依据 SHALL 是 change 目录 `workflow-events.jsonl` 中的 `current_spec_synced` / `backlog_updated` 等结构化解释事件

### Requirement: 流程骨架与项目规则的承载分工

接入 witnessloop 后，**流程骨架**（change 契约、review manifest 的证据绑定、grill / grill-adversarial / building 三类审阅证据、受保护路径的写入解释、本地写码前 guard、CI required check 形态、测试执行点）SHALL 由 witnessloop 承载；**项目规则**（Reference Implementation Research、Impact Analysis、benchmark 门禁、设计审阅任务、tasks 完成度、归档点完成度门、合入平台闸门、流程事件投影）SHALL 保留在本仓，SHALL NOT 迁入 witnessloop。

#### Scenario: 项目规则不随接入外迁

- **WHEN** 完成 witnessloop 接入
- **THEN** 本仓 SHALL 继续维护 `Reference Implementation Research` 与 `Impact Analysis` 的检查
- **AND** 归档点完成度门与 `platform-gate` 平台闸门 SHALL 仍由本仓脚本承载
- **AND** 缺什么能力 SHALL 去 witnessloop 仓库立 issue，而不是在本仓另起一套

#### Scenario: 局部应用成熟模式而非另立协议

- **WHEN** 决定让某个自建检查改由 witnessloop 承载
- **THEN** 该检查 SHALL 映射到 witnessloop 既有的 stage 名与事件语义（`grill` / `grill-adversarial` / `building`；`event_type` / `artifact_path` / `reason` / `approved_by`）
- **AND** SHALL NOT 引入与 witnessloop 不兼容的第二套门禁协议
