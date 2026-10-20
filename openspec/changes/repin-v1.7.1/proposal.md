# Proposal: witnessloop caller 回钉 v1.7.1 并同步 init 台账

关联跟踪 issue：[#331](https://github.com/Xingkai98/asterwynd/issues/331)（【feature】witnessloop caller 回钉 v1.7.1 并同步 init 台账）。

## Change Type

- primary: process
- secondary: []

## Why

2026-10-20，上游 witnessloop issue [#42](https://github.com/Xingkai98/witnessloop/issues/42)（**已修复并关闭**）暴露了 `gate.yml` 的一个硬故障：

- `v1.7.0` 是 **annotated tag**：tag object `00192abe…` 指向 commit `c9b2811…`；
- `gate.yml` 当时把 `job.workflow_sha` 直接当作包 ref；对 annotated tag，这个值是 **tag object sha**，不是 commit；
- uv 的较新版本拒绝「精确 revision ≠ commit」（上游 issue #42 记录 0.13.1 绿 / 0.13.3 红；`gate.yml` 注释写 0.13.2 起）⇒ `gate / check`（唯一 required）对所有 PR 硬红，与 PR 内容无关。

asterwynd 的应急 hotfix 是 PR [#327](https://github.com/Xingkai98/asterwynd/pull/327)（merge `6808fcd9`）：只把 `.github/workflows/witnessloop.yml` 的 `uses:` 钉到 commit `c9b281167ad20b63e4832ad9ab8510964a2adc60`，**故意没有同步** `.witnessloop/init-manifest.json`（受保护路径，等待上游修复后用正规 change 同步）。

上游随后发布 **v1.7.1**：annotated tag object `c4f681a7…` → commit `07bf23b3…`。新的 `gate.yml` 按 ref 形态解析包 ref——**tag 用 `job.workflow_ref` 的 `refs/tags/<tag>`**，分支 / commit pin 才用 `job.workflow_sha`。⇒ annotated tag 重新成为受支持形态。

当前 `master` 因此处于两个都不是稳态的状态：

1. caller 钉在 commit `c9b2811…`（应急形态，规格要求的是「具体发版 ref」）；
2. `.witnessloop/init-manifest.json` 的 `gate_ref` 仍是 `@v1.7.0`，与盘上 caller **不一致**（台账漂移）。

本 change 是这条故障的正规收尾：把 caller 回钉到 `@v1.7.1`，用 `witnessloop init` **原子地**同步台账，补受保护写入解释事件，并把规格 / 文档里仍写 `v1.7.0`、commit 临时钉与「台账待同步」的口径更新为已回钉。

## 需求

1. **回钉 caller**：`.github/workflows/witnessloop.yml` 的 `uses:` 改为 `Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1`，不使用 `with: witnessloop-ref:`，不使用滚动 tag `@v1` 或分支名。
2. **同步台账**：`.witnessloop/init-manifest.json` 的 `gate_ref` 与 caller 条目 `sha256` 由 `witnessloop init --root . --gate-ref "<同上>" --policy .witnessloop/policy.json` 写入，禁止手改台账。
3. **幂等实测**：同一条 `init` 命令再跑一次必须报「幂等 / 无改动」且 exit 0。
4. **受保护写入解释**：`.witnessloop/**` 属 `protected_paths` ⇒ 本 change 的 `workflow-events.jsonl` 必须有一条 `protected_artifact_explained` 事件，`artifact_path` 精确指向 `.witnessloop/init-manifest.json`，`reason` / `approved_by` 非空。
5. **规格与文档同步**：`openspec/specs/dev-workflow-gate/spec.md` 的当前发版 ref 与包 ref 推导语义更新到 v1.7.1（含 annotated tag / `job.workflow_ref` 的口径）；`docs/development-guide.md` 与 `docs/interview-script/questions/Q12-ci-testing.md` 里仍写 `v1.7.0` / commit 临时钉 / 旧推导方式的段落一并订正。
6. **实测验收**：本 PR 的 `gate / check` 日志里包 ref 必须解析为 **`refs/tags/v1.7.1`**（来源为 `job.workflow_ref` 的 tag ref），且 `gate / check` pass；合入后在 `master` 上复核 caller、台账与 `init` 幂等。
7. **回链**：proposal / design / tasks 引用 witnessloop #42（仅引用，不改上游仓与任何 tag）与 asterwynd PR #327（hotfix 背景）；合入后在 issue #331 留完成说明并关闭。

## Impact Analysis

| 影响面 | 内容 | 处置 |
| --- | --- | --- |
| 接入配置 | `.github/workflows/witnessloop.yml` 的 `uses:` 由 commit pin 改为 `@v1.7.1` | `witnessloop init` 重写；不手改 |
| init 台账 | `.witnessloop/init-manifest.json` 的 `gate_ref` / caller `sha256` | `witnessloop init` 原子同步；受保护写入事件 |
| 当前规格 | `openspec/specs/dev-workflow-gate/spec.md` 的 `@v1.7.0` 与包 ref 推导口径 | 本 change 的 spec delta + 就地 Purpose 行；`current_spec_synced` 事件 |
| 开发文档 | `docs/development-guide.md`（caller 版本、本地 `check` 锚点）、`docs/interview-script/questions/Q12-ci-testing.md`（流水线图） | 同步为 v1.7.1；不扩大改动面 |
| backlog | `docs/openspec-change-backlog.md` 登记本 change，收尾时移除 | `backlog_updated` 事件 |
| 代码 / 测试面 | 不触及 `agent/**`、`scripts/**`、`web/**`；不改任何运行时代码 | 无新增单元测试（本 change 无运行时代码）；回归证据 = PR 的 `gate / check` 日志（包 ref 来自 tag）+ `init` 幂等实测；按仓库基线跑全量 pytest / OpenSpec validate / 瘦 checker |
| 门禁行为 | required check 名称仍为 `gate / check`；平台配置（branch protection）不变 | 不改 `scripts/platform-gate.json`，不跑 `--apply` |
| 风险 | v1.7.1 若仍无法从 tag ref 安装，`gate / check` 会继续红 | 以本 PR 的 CI 日志与 `check` 的包来源行实测为准；失败则停止并报告，不擅自改上游或降级门禁 |
| 回滚 | 需要回到上一形态时 | 回滚目标写死 hotfix commit；`--gate-ref` 必须给完整 ref：`Xingkai98/witnessloop/.github/workflows/gate.yml@c9b281167ad20b63e4832ad9ab8510964a2adc60`（回到 `@v1.7.0` 会复发 #42；只给裸 sha 会写出非法 `uses:`）；用同一工具 `init --gate-ref <完整 ref> --policy .witnessloop/policy.json` 重写 caller + 台账（先写不回滚），并补新的解释事件，禁止手改台账 |

## Reference Implementation Research

research_tier: light
status: enabled
reason: 根因修复与发版决策已由上游 witnessloop issue #42 锁定（annotated tag 解析），本 change 不引入新设计；但仍需核对 v1.7.1 的 `gate.yml` 解析规则、`init` 的重写 / 幂等语义与上游升级指南，避免凭旧版本记忆操作。

findings: 直接读取 witnessloop v1.7.1 源码（tag 下载，未改上游仓）：`src/witnessloop/initcmd.py` 的 `sync_caller_gate_ref` 在收到显式 `--gate-ref` 时重写 caller **并同步** `gate_ref` 与 caller 条目 `sha256`；`_already_initialized` 在无差异时报幂等；`desired_files` 的 caller 模板与当前文件逐字节同形。`gate.yml` 的 ref 解析分支明确写着：tag ⇒ `job.workflow_ref` 的 `refs/tags/<tag>`（annotated tag 下 `job.workflow_sha` 是 tag object，uv 新版本拒绝），分支 / commit pin ⇒ `job.workflow_sha`，最终空 ref 直接 `::error::` 退出。`docs/gate.md` 的升级动作是「先升 CLI，再 `init --gate-ref`」，并说明 `--version` 恒为 0.1.0、不能用来判断版本。本机 PATH 上的 `witnessloop` 是 0.1.0，`init` 不认识 `--policy`；本地源码 / editable 安装又没有 PEP 610 `vcs_info`，`check` 只会打印 `<未知>`。因此本次用与 CI 同源的 `uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop ...`；实测 `check` 首行为 `requested_revision=refs/tags/v1.7.1，commit_id=07bf23b3…`。

design impact: caller 只钉 `@v1.7.1` 一处；台账由工具同步，不手改；本地 `check` 必须用 `uvx` 从 tag 安装的 v1.7.1 CLI（旧 0.1.0 与本地源码都不作为判据）；升级动作与文档中的本地锚点统一改为这条可复现命令；验证以「init 幂等 + 归档后 manifest + 本地 check（目标确实被检到）+ PR 的 gate 日志 ref」多层证据收口。
