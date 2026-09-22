# Proposal: 受保护路径门禁边界如实记录（fix-issue-229-231-debt-wording）

关联跟踪 issue：[#229](https://github.com/Xingkai98/asterwynd/issues/229)（受保护路径解释门禁可被伪造 change 目录糊过）、[#231](https://github.com/Xingkai98/asterwynd/issues/231)（受保护写通道的 change id 前置未专门拒绝 `..`）。

## Change Type

primary: docs

## 需求

1. 改写 `docs/known-debt.md` 的 #229 条目：把「属门禁加固的独立 effort」改为**「机械加固不可行、定位为已知边界」**，附三条设想加固路径的实测排除结论，以及黑盒复现表（裸目录 exit 1 vs 完整伪造 change exit 0）。
2. 复核并改写 #231 条目：`--change ..` 现被**锚点兜底**拦下（非专门规则），「未专门拒绝 `..`」在实现层仍成立但当前不可利用。
3. 把该定位写成规格（`change-documentation` 新增「机械门禁的信任边界」Requirement），使边界不只是一条 debt 备注。
4. 均为**如实记录边界，零代码改动**。

## 背景

`docs/known-debt.md:111` 与 `:125` 的两条债务条目，措辞暗示「以后加固即可」，与实测不符。fix-issue-229 在 master 隔离 worktree 复核后确认：三条加固路径均不可行，门禁定位是「防误改」而非「防伪造」，信任边界在仓库 push 权限。本 change 只改措辞使其如实。

## 非目标

- 不改任何代码（`check_openspec_artifacts.py` / `workflow_state.py` 均不动）。
- 不引入新的门禁机制。
- 不动 `flow-policy.json`。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `docs/known-debt.md` | 两条债务条目改写为如实的边界记录（受保护路径，配 `protected_artifact_explained` 事件） |
| 代码 | 无改动 |
| Specs | `openspec/specs/change-documentation/spec.md`（ADDED「机械门禁的信任边界」——把「防误改而非防伪造」定位与边界记录写成规格） |
| Tests | 无（零代码改动） |

## 测试计划

- 无代码改动，无新增测试。
- 门禁：`check_openspec_artifacts.py`（含 `--base-ref --require-base`）通过；OpenSpec strict validate 通过。
