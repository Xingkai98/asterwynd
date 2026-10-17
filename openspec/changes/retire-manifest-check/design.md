# Design: 下掉与 witnessloop 重复的本仓 review manifest 校验（第一刀）

## Context

#316 的探索结论（issue comment，2026-10-17）把两套 manifest 的字段、消费方与哈希口径逐项
对照后指出：asterwynd 形态与 witnessloop 形态不是同一份内容的两个文件名，而是两套修订绑定
语义；让 witnessloop 吃 asterwynd schema 或反向迁移历史都不可行。真正的收敛路径是**下掉
本仓 checker 里与 witnessloop 重复的校验**，让 witnessloop 形态成为唯一被要求的 manifest。

本 change 是第一刀，范围严格限定为：

- 删除 `scripts/check_openspec_artifacts.py` 的 `_check_review_manifests` 及其两个调用点；
- 停止产出 asterwynd 形态 manifest（本地 review-loop 入口与仓内文档）；
- 用极小的本地检查保留旧校验里**唯一不被 witnessloop 覆盖**的判据：`verdict == PASS`；
- 其它检查一律不动。

实测依据：

- witnessloop v1.7.0 的 `check` 不读 `schema` / `verdict`（`src/witnessloop/constants.py:79,90,110-120`；
  `checkcmd.py:188-192`）；
- witnessloop 对 manifest 字段、`report_path`、`reviewer != author`、git span、
  `report_hash` / `tasks_hash` / `spec_hash` 与孤儿报告的校验比 asterwynd 更严
  （`contract.py:638-671,679-...764-803`）；
- 80 份历史 ast manifest 无法干净迁移（27 份 `tasks_hash` 漂移、8 份提交不可解析、全部缺
  `author_run_id`、`spec_hash` 算法 79/80 不同），历史报告格式也不统一（79 份中仅 1 份有
  `## 闭环出口`）。

## Goals / Non-Goals

**Goals:**

- 删除与 witnessloop 重复的 manifest 校验，回到**一套** review manifest（witnessloop 形态）。
- 保留「只有 PASS 的 building review 才算数」这条判据，且不引入第二套 manifest。
- 保证 RIR、Impact Analysis、benchmark smoke、归档点完成度、backlog 一致性、受保护路径
  事件、grill / grill-adversarial 证据等检查行为不变。
- 让历史归档保持冻结：不追溯、不重写、不新增历史正文门槛。
- 同步规则文档、当前规格与本地 review-loop 入口。

**Non-Goals:**

- 不改 `agent/workflow/review_manifest.py`、它的测试、`workflow_state.py review-manifest`
  写通道与 `flow-policy.json` 的受保护路径规则（第二刀）。
- 不动 80 份历史 ast manifest，不迁移、不删除、不重算。
- 不改 witnessloop 仓、`v1` / `v1.7.0` tag 或 `review_manifest_glob`。
- 不统一 schema，不定义公共超集格式。
- 不改变 `platform_gate.py` 行为、required 集合或 CI 的 job 组成。

## Decisions

### Decision 1: 只删 manifest 校验，不删 building-review 存在性门

**选择**：删除 `_check_review_manifests` 中所有 `verify_review_manifest` 调用与
`--check-archived` 的 manifest 漂移检测；保留 active/归档点「非 docs + 有 spec delta 的
change 必须有 `reviews/building-review.md`」这条存在性判据。

**理由**：存在性判据与 manifest 无关，是「独立审阅跑过没有」的最小证据；归档点完成度门本就
单独要求它（`_check_archived_completion_gate`）。把它一并删掉会削弱判据，超出「下掉重复面」
的范围。

**备选**：整函数删除并依赖 witnessloop 的 `building` stage 证据。否——witnessloop 只覆盖
本次 diff 触及的 change，且本地 checker 是独立于 required 的第二道项目自检；保留存在性门
成本极低。

### Decision 2: verdict 判据保留（方案 i，本地极小等价检查）

**选择**：新增 `_check_building_review` / `_review_exit_verdict`：

- 在 `reviews/building-review.md` 中查找唯一的二级标题 `## 闭环出口`；
- 该小节内必须出现**恰好一种**终结 token（`PASS` / `BLOCKED` / `CHANGES_REQUESTED`），
  且必须是 `PASS`；
- 小节缺失、无 token、token 不唯一或非 PASS ⇒ checker 报错。

**理由**：

1. witnessloop 明确不读 verdict（证据见 Context），所以它不是重复判据；删除 manifest 校验
   不能顺带放弃它。
2. #316 的非目标写明「不放宽任何判据」；issue 发起人也把该风险列为第一刀必须正面回答的问题。
3. `## 闭环出口` 是 witnessloop `templates/review-loop.md` 已经规定的报告形态（只在终结时
   填三种出口之一），本仓 `/review-loop` 也已采用；把它机械化的边际成本最小。
4. 旧 manifest 的 `verdict` 字段同样是生产者自报；读报告正文没有降低证据强度。

**为什么不需要用户拍板**：方案 (i) 是 standings 规则（不放宽判据）在代码/实测证据下的直接
推论，不是新的产品取舍；方案 (ii)（接受 PASS 门消失）会与该规则冲突。若用户要选择 (ii)，
那才是需要裁决的例外——本设计采用默认不放宽。

**备选**：

- (ii) 接受损失并登记：不采用。它会让「BLOCKED 的审阅也能合入」，与 #316 的非目标直接冲突。
- 解析 `## Verdict` 等历史标题：不采用。历史报告格式不统一（53 PASS / 13
  CHANGES_REQUESTED / 1 BLOCKED / 12 无标题），且正文含多轮 verdict；对历史做统一解析会
  产生大量假红。
- 读取 witnessloop manifest 或新增字段：不采用。那会重新引入第二套语义，或要求改 witnessloop。

### Decision 3: verdict 检查的落点是 active 触发面 + 归档点，不做历史追溯

**选择**：

- **active**：在 `check_change` 中原 `_check_review_manifests` 的位置调用新函数，触发条件
  保持「非 docs + `_changed_capabilities` + `_tasks_all_complete`」。
- **归档点**：在 `_check_archived_completion_gate` 的 building-review 存在性判据之后调用
  同一个 verdict 解析器；只对本 PR `--diff-filter=AR` 新建的归档目录生效。
- **`--check-archived`**：只保留 `_check_archived_projectable`；不扫描历史报告，
  不要求历史 manifest。

**理由**：旧行为在新归档上最终由 `--check-archived`（全量）验证 PASS；把等价检查放到归档点
后，新归档仍有 PASS 门，而历史归档（其中 78 份格式不同）不会被追溯打红。active 侧的触发
条件与新旧完全一致，在途 change 不受影响（当前唯一 active change
`add-minimal-tui-runtime-view` 有 18 条未勾任务且无 `reviews/`）。

**备选**：在 `--check-archived` 全量解析报告。否——见 Decision 2 的历史假红证据。把 verdict
检查只放 active。否——最终归档 commit 里 change 已不在 active 面，会被漏掉。

### Decision 4: 历史资产与第二刀边界

**选择**：80 份历史 ast manifest、`agent/workflow/review_manifest.py`、其单测与
`workflow_state.py review-manifest` 写通道原样保留；`flow-policy.json` 对
`-review-manifest.json` 的受保护规则原样保留。checker 不再消费它们。

**理由**：第二刀才决定「删模块 / 归档处置 / 受保护路径规则」；本 change 若顺手删模块，会把
`workflow_state` CLI 与大量测试一起卷进来，超出「只做这一刀」的范围。保留模块不会让新 change
再产 ast manifest——产出入口（review-loop 与文档）已改。

**代价**：仓库里存在「保留但不再被 checker 消费」的代码与 80 份历史文件；在 known-debt 中
登记为第二刀输入。

### Decision 5: `diff_hash` 强校验的损失登记

**选择**：不在本仓新增 `diff_hash` 等价检查；在 `docs/known-debt.md` 记录该损失与补偿。

**理由**：witnessloop 把 `diff_hash` 当 informational 不校验，但其 git span 判据（`head_sha`
必须是祖先、`head_sha..被检 head` 之间只允许证据文件）在「审阅后是否又改代码」这一维度上
更严格。真正失去的是「manifest 记录的 diff 字节与当前 git diff 完全一致」这一自洽检查；
它检测的是 manifest 生产后 base 移动或 diff 口径变化，不是审阅结论本身。登记为可接受的
残余风险，第二刀再评估是否需要迁移。

### Decision 6: 单一证据形态的规格与文档口径

**选择**：

- 规格明确：`reviews/<phase>-review-manifest.json` **不再是本仓要求**；witnessloop 形态
  `reviews/<stage>.manifest.json` 是唯一 review manifest 要求；
- 三份 stage manifest（`grill` / `grill-adversarial` / `building`）在归档 move 之后用
  归档目录名重建（#29 次序）；
- 本仓 checker 的 verdict 判据写在 specs 与开发指南里，不藏在 gitignored 的 `.claude/` 文件；
- 本地 `.claude/commands/review-loop.md` 只作为入口同步，不是可审计载体。

**理由**：避免「仓库里退役了、实际加载的入口还在产 ast manifest」的双面状态；也避免把机械
格式要求只写进 gitignored 文件。

## Pre-Implementation Review

（本节在 grill 与设计阶段对抗闭环完成后回填：登记 Confirmed Decisions、Open Questions 的
处置、对抗轮次与出口。）

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| `## 闭环出口` 解析过严导致误伤 | 新 change 的报告格式不合规会被红 | 报告模板与本地入口明确要求该小节；解析器对空行/加粗/中文括号容忍；新增正反单测 |
| 解析过松导致 BLOCKED 被读成 PASS | PASS 门失效 | 要求小节内**恰好一种** token；多 token 视为「出口不明确」报错 |
| 删除 manifest 校验后历史漂移无人检测 | 历史 manifest 可能已 stale | 接受：历史只读；本 change 后不再要求维护它；第二刀决定归档处置 |
| `diff_hash` 自洽检查消失 | manifest 记录的 diff 不再被本仓校验 | witnessloop 严格 git span 部分补偿；known-debt 登记 |
| 在途 change 被新检查误伤 | 开发被阻断 | 触发条件保持旧行为；当前唯一 active change 无 `reviews/` 且有未勾任务 |
| 文档漏改导致仍在产 ast manifest | 两套并存继续 | 测试中加文档守卫；grep 全仓校验；本地入口单独同步 |
| 归档点新增 verdict 检查导致历史归档红 | 归档 PR 无法通过 | verdict 检查只在**新归档目录**（`_check_archived_completion_gate`）执行；`--check-archived` 不扫描历史 |

## Testing Strategy

- **先红**：
  - 新测试断言 active gate 读取 `## 闭环出口`：PASS 通过、BLOCKED / CHANGES_REQUESTED /
    缺失 / 多 token 报错；
  - 新测试断言 `--check-archived` 不再因 `spec_hash` / `tasks_hash` / 缺失 manifest 报错，
    但仍校验归档事件日志可投影；
  - 新测试断言归档点门对新建归档要求 PASS 出口；
  - 旧测试中断言 `review manifest missing` / `tasks_hash skip` / `spec hash mismatch` 的
    用例先改红（或删除），实现后转绿。
- **回归**：运行 `tests/test_openspec_artifact_checker.py` 全量；运行
  `tests/agent/workflow/test_review_manifest.py`、`tests/test_workflow_state_cli.py`、
  `tests/test_workflow_archive_write_channel.py`，证明模块与 CLI 未被牵连。
- **文档守卫**：断言 `AGENTS.md` / `README.md` / `README_EN.md` / `docs/**` 的规范面不再
  要求产出 ast manifest（历史归档与 known-debt 历史记录除外）。
- **端到端**：`uv run pytest -q`、`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`、
  OpenSpec strict validate、`witnessloop check`；本 change 自身按新流程产三份 witnessloop
  manifest。
