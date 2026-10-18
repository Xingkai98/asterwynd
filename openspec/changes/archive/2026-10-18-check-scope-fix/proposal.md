# Proposal: 收窄「闭环出口」检查到本 PR 新归档（默认 base 解析修复）

关联 issue：[#319](https://github.com/Xingkai98/asterwynd/issues/319)（本 change 跟踪入口；
本 PR 只承接其中「收窄闭环出口检查」一件，TUI 退役另立 PR）；
关联 [#235](https://github.com/Xingkai98/asterwynd/issues/235)（归档点完成度门）与
[#316](https://github.com/Xingkai98/asterwynd/issues/316)（`## 闭环出口` 判据来源）。

## Change Type

- primary: process
- secondary: []

## Why

`retire-manifest-check`（PR #317）把 `## 闭环出口` 的本地 PASS 检查接进归档点完成度门。
该检查**只对本 PR 新归档**求值，设计意图是「历史报告不追溯」；但 `--base-ref` 的缺省值是
字符串 `master`。在本地 `master` 落后 `origin/master` 的 worktree 里：

- 裸跑 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 会把 8 个历史归档目录
  当成「本 PR 新归档」，其中 5 个缺 `## 闭环出口` 而报错，EXIT=1；
- 本工作区实测 `master=3c7196b`（落后 `origin/master` 103 个提交）、
  `origin/master=b0469cb`；
- AGENTS.md 的标准命令（显式 `--base-ref origin/master --require-base`）与 CI
  （显式 PR base sha）都是绿的，缺陷只在「不传参数」的本地入口。

此外，分支落后于 `origin/master` 时，两点 diff 会把上游已合入的受保护路径改动反向列为
本分支改动，造成新的误红。修法需要让裸跑的 base 真正代表**本 PR**。

## What Changes

1. **默认 base 解析**：`--base-ref` 改为可选；显式给出时保留两点 diff 语义；未给出时
   优先以 `origin/master` 与 `HEAD` 的 merge-base 作为 diff base（三点语义），
   merge-base 不可用则退回候选 ref，再否则回退 `master`。解析结果同时用于归档点门与
   受保护路径 diff；隐式解析命中时向 stderr 打 INFO。
2. **归档点门不放宽**：`_new_archive_dirs_since_base` 的 `--diff-filter=AR` +
   「base 树不存在」双重过滤、`_check_archived_completion_gate` 与
   `_review_exit_*` 判据逐行不变；新建归档缺 `## 闭环出口` 仍必须报错。
3. **测试**：新增 7 条（`_resolve_base_ref` 单元、裸跑不追溯历史归档、新建归档仍红、
   显式 base 优先、解析结果传给受保护路径 diff、落后分支不误红、空 `--base-ref` 不跳过
   检查），含红/绿与两种变异验证。
4. **规格与文档**：`dev-workflow-state-machine` 的归档点 Requirement 补充默认 base
   解析口径；`AGENTS.md` / `development-guide` / `requirements-process` / `known-debt` /
   CI 注释同步；新增 ADR-0007 记录 merge-base 选择与备选。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `dev-workflow-state-machine`：归档点审阅门的 base 解析口径。未显式提供 `--base-ref`
  时，checker SHALL 优先以 `origin/master` 与 `HEAD` 的 merge-base 作为 base，否则回退
  到与 `master` 的 merge-base；该解析结果 SHALL 同时用于归档点 diff 与受保护路径 diff；
  历史归档 SHALL NOT 因本地默认分支陈旧而被追溯求值，落后分支的上游改动 SHALL NOT 被
  反向误判。

## 需求

1. **默认 base 解析**：`scripts/check_openspec_artifacts.py` 未显式收到 `--base-ref` 时，
   SHALL 优先使用 `origin/master` 与 `HEAD` 的 merge-base（三点语义），不可解析时回退到
   与 `master` 的 merge-base；非空显式参数 SHALL 保持原有两点 diff 语义、不被覆盖；
   空/纯空白显式值 SHALL 按未提供处理（不得静默跳过 diff 检查）。
2. **归档点门不放宽**：新建归档目录的判定 SHALL 继续使用 `--diff-filter=AR` 且
   「该归档子目录在 base 树不存在」；新建归档缺 `## 闭环出口` SHALL 仍报错。
3. **历史不追溯**：在 HEAD 与 `origin/master` 一致的干净检出上裸跑 checker SHALL 返回 0；
   本项目 5 个缺 `## 闭环出口` 的历史归档 SHALL NOT 被重新求值。
4. **回归测试**：SHALL 覆盖 `_resolve_base_ref` 单元、裸跑不追溯、新建归档仍红、显式
   base 优先、受保护路径接线、落后分支不误红、空 base 不跳过检查。
5. **其它门禁不动**：RIR、Impact Analysis、benchmark smoke、building review 存在性与
   出口判据、grill / grill-adversarial 证据、tasks 完成度、受保护路径解释事件 SHALL
   一律保持不变。
6. **设计决策留痕**：默认 base 解析有 ≥2 个备选，SHALL 有 ADR（ADR-0007）记录选择与
   被拒备选。

## Non-Goals

- **不处理** TUI proposal 退役；那件事另立 PR（issue #319 的另一半）。
- **不**改写历史归档报告；不为 5 份历史报告补 `## 闭环出口`。
- **不**改 `--check-archived` / `--change` / `--skip-*` 的既有语义；默认 base 变更同样作用于它们的受保护路径检查，`--check-archived` 只关闭归档点门。
- **不放宽**任何其它判据；不修改 witnessloop 仓、`v1` / `v1.7.0` tag 或 `.witnessloop/**`。

## Impact Analysis

- 影响代码：
  - `scripts/check_openspec_artifacts.py`：`--base-ref` 参数、`_resolve_base_ref` helper、
    `main` 接线、help 文案。归档点/保护路径/backlog 判据逻辑本身不变。
- 影响测试：
  - `tests/test_openspec_artifact_checker.py`：新增 7 条测试；既有归档点门单测不受影响。
  - `tests/test_retire_manifest_check.py`：更新过期 docstring。
- 影响文档：
  - `AGENTS.md`、`docs/development-guide.md`、`docs/requirements-process.md` 的 base 解析说明；
  - `docs/known-debt.md` 的 CI `--skip-*` 备注；
  - `docs/adr/ADR-0007-default-base-resolution-for-archive-gate.md`（新增）；
  - `docs/openspec-change-backlog.md`（登记/移除本 change）；
  - `openspec/specs/dev-workflow-state-machine/spec.md`（delta 同步）。
- 风险面：默认 base 改用 merge-base 后，`origin/master` 自身陈旧（未 fetch）时仍可能误判，
  属 fail-loud；显式 `--base-ref` 仍是逃生口。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 上游决策锁定：issue #319 已写明「让检查只作用于本次 diff 内 / 新建归档」的处置，
  并引用已关闭的 #316（manifest 退役）与 #235（归档点完成度门）作为决策依据；本 change
  无新增能力面，是有回归测试的 bugfix，不涉及产品/方案取舍，无需横向调研。

## 用户故事

- 作为本地开发者，我在干净检出上裸跑 artifact checker 时看到 0 个错误，而不是 5 条历史
  归档的误红。
- 作为审阅者，新建归档仍然必须提供 `## 闭环出口` PASS，判据没有被这次收窄放宽。
- 作为分支落后的开发者，我不会因为上游改动受保护路径而被要求解释本分支没碰过的文件。
