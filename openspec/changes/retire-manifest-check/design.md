# Design: 下掉与 witnessloop 重复的本仓 review manifest 校验（第一刀）

## Context

#316 的探索 comment（2026-10-17）把两套 manifest 的字段、消费方与哈希口径逐项对照后，
§5 **推荐 (d)**：保留两套，在收尾时从 witnessloop 形态确定性派生 asterwynd 形态；同一
comment 的 §4.4 与 issue body 明确「不放宽任何判据」。**本 change 不采用 (d)，而是按用户
在探索之后的裁决做第一刀：下掉本仓 checker 里与 witnessloop 重复的校验**，让 witnessloop
形态成为唯一被要求的 manifest。因此本设计必须逐条回答「哪些判据会消失、如何保留」，不能
把「下掉」写成 #316 的原始推荐。

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
  `author_run_id`、`spec_hash` 算法 79/80 不同）。历史报告格式也不统一：79 份归档
  `building-review.md` 中仅 1 份有 `## 闭环出口`；67 份有 `## Verdict` 前缀标题、12 份
  没有；按「最后一个 `## Verdict` 小节的首个 verdict token」统计为 61 PASS /
  5 CHANGES_REQUESTED / 1 无 token，其中 15 份该小节混有多个 token。

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

**选择**：新增 `_check_building_review` / `_review_exit_verdict`。解析规则必须先钉死为四条
可执行规则（否则实现会在假红 / 假绿之间摇摆）：

1. **标题前缀匹配**：二级标题以 `闭环出口` 为前缀即命中（容忍 witnessloop 模板实际使用的
   `## 闭环出口（仅在终结时填写；轮内写「未定」）`）。`###` 级不匹配。
2. **忽略 fenced code**：` ``` ` / `~~~` 围栏内的标题与 token 不参与匹配，避免报告里引用
   模板示例时误判。
3. **只认首个非空行**：取该小节第一个非空行，剥掉行首的 list/bold 标记后，该行必须以
   `PASS` / `BLOCKED` / `CHANGES_REQUESTED` 之一**开头**；`PASS（此前 CHANGES_REQUESTED
   已收口）` 合法，`不是 PASS` 不合法（不以 token 开头），`未定` 不合法。行内后续说明不
   参与判定。
4. **小节唯一**：报告中出现多个 `## 闭环出口` 后缀标题 ⇒ 直接报错（不做「最后一个赢」）。

判定结果必须是 `PASS`；标题缺失、小节为空 / 未定、出现多个小节或首个非空行不是 `PASS`
开头 ⇒ checker 报错。该检查**只覆盖 `reviews/building-review.md`**；历史上
`design-review.md` 的 PASS 门随旧 manifest 校验一起退役（见 Decision 5 与 known-debt）。

**理由**：

1. witnessloop 明确不读 verdict（证据见 Context），所以它不是重复判据；删除 manifest 校验
   不能顺带放弃它。
2. #316 的非目标写明「不放宽任何判据」；issue 发起人也把该风险列为第一刀必须正面回答的问题。
3. `## 闭环出口` 是 witnessloop `templates/review-loop.md` 已经规定的报告形态（只在终结时
   填三种出口之一），本仓 `/review-loop` 也已采用；把它机械化的边际成本最小。
4. 旧 manifest 的 `verdict` 字段同样是生产者自报；读报告正文没有降低证据强度。
5. 规则 1–4 同时消掉两类已证实的错误：逐字 `\bPASS\b` 会把「不是 PASS」判绿；把小节内所有
   token 一起统计会把 `PASS（此前 CHANGES_REQUESTED 已收口）` 判红（历史 15 份
   `## Verdict` 小节正是多 token 形态）。

**为什么不需要用户拍板**：方案 (i) 是 standing 规则（不放宽判据）在代码/实测证据下的直接
推论，不是新的产品取舍；方案 (ii)（接受 PASS 门消失）会与该规则冲突。若用户要选择 (ii)，
那才是需要裁决的例外——本设计采用默认不放宽。

**备选**：

- (ii) 接受损失并登记：不采用。它会让「BLOCKED 的审阅也能合入」，与「不放宽判据」冲突。
- 解析 `## Verdict` 等历史标题：不采用。79 份历史报告里只有 1 份有 `## 闭环出口`；按
  「最后一个 `## Verdict` 小节的首个 token」统计仍有 12 份无标题、15 份混有多个 token，
  对历史做统一解析会产生大量假红。
- 读取 witnessloop manifest 或新增字段：不采用。那会重新引入第二套语义，或要求改 witnessloop。

### Decision 3: verdict 检查的落点是 active 触发面 + 归档点，不做历史追溯

**选择**：

- **active**：在 `check_change` 中原 `_check_review_manifests` 的位置调用新函数，触发条件为
  「非 docs + `_changed_capabilities` + `_tasks_all_complete`」。**这是 building-review
  存在性门的触发条件，保持不变**；旧 manifest 校验的隐式宽触发（只要 `reviews/` 存在就校验
  其中的 `*-review.md`，与类型 / tasks 完成度无关）被**有意收窄**到完成面，避免 partial
  review 被误伤。
- **归档点**：在 `_check_archived_completion_gate` 的 building-review 存在性判据之后调用
  同一个 verdict 解析器；触发条件与存在性门相同（非 docs + `_changed_capabilities`），只对
  本 PR `--diff-filter=AR` 新建的归档目录生效。
- **`--check-archived`**：只保留 `_check_archived_projectable`；不扫描历史报告，
  不要求历史 manifest。

**理由**：旧行为在新归档上最终由 `--check-archived`（全量）验证 PASS；把等价检查放到归档点
后，新归档仍有 PASS 门，而历史归档（其中 78 份没有新出口标题）不会被追溯打红。在途 change
不受影响（当前唯一 active change `add-minimal-tui-runtime-view` 有 18 条未勾任务且无
`reviews/`）。收窄后的边界必须由测试锁定：partial change 即使有 `building-review.md` 也不
报错；历史归档无 `## 闭环出口` 在 `--check-archived` 下仍 exit 0。

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

### Decision 5: 残余损失的登记

**选择**：不在本仓新增 `diff_hash` 等价检查；在 `docs/known-debt.md` 完整登记三项残余损失：

1. `diff_hash` 强校验消失。witnessloop 把 `diff_hash` 当 informational 不校验，但其 git span
   判据（`head_sha` 必须是祖先、`head_sha..被检 head` 之间只允许证据文件）在「审阅后是否
   又改代码」这一维度上更严格。真正失去的是「manifest 记录的 diff 字节与当前 git diff 完全
   一致」这一自洽检查；它检测的是 manifest 生产后 base 移动或 diff 口径变化，不是审阅结论
   本身。
2. `--check-archived` 不再检测历史归档的 manifest / report / spec 漂移。这是有意收窄：历史
   79 份报告只有 1 份符合新出口格式，无法做统一追溯；失去的是「检测能力」本身，不只是
   「历史文件可能 stale」。
3. 非 building 的 `*-review.md` 不再有本仓 PASS 门。旧校验对 `reviews/` 下每份
   `*-review.md` 都要求同名 manifest 且 `verdict == PASS`；新检查只读
   `reviews/building-review.md`。当前流程不要求 `design-review.md`，历史上只有 1 份 design
   形态 ast manifest，影响面窄，但必须如实登记。

**理由**：这三项都不是 witnessloop required 面能自动补齐的，也不是本刀应该顺手扩大范围去
处理的；登记为第二刀的输入，避免「静默接受损失」。

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

**Grill（独立零记忆，2026-10-17）**：产出 8 条 Confirmed Decisions、0 条 Open Questions、
13 条 Code-Resolved Questions（记录见 `reviews/grill-design.md`）。关键结论：

- 删除面与落点成立：归档点门会在最终归档 commit 执行（CI 第一步带 `--base-ref`、
  `--diff-filter=AR` + base 树过滤）；保留 building-review 存在性门、只删 manifest 循环是
  正确拆分。
- `## 闭环出口` 解析必须先钉死四条规则（前缀标题、忽略 fenced code、只认首个非空行、
  小节唯一），否则「不是 PASS」会假绿、`PASS（此前 CHANGES_REQUESTED 已收口）` 会假红。
- 回写本设计的四项：① 修正对 #316 的归属（#316 §5 推荐 (d)，本 change 按用户后续裁决偏离）；
  ② 修正历史统计（79 份中 1 份有新出口；61 PASS / 5 CHANGES_REQUESTED / 1 无 token /
  12 无 `## Verdict` 标题；15 份多 token）；③ 承认 active 触发面由「reviews/ 存在即校验」
  收窄为「完成面」；④ verdict 判据只保留 building review，非 building 的 PASS 门登记
  known-debt。
- 设计对抗闭环：待跑（本轮实现后回填出口与轮次）。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| `## 闭环出口` 解析过严导致误伤 | 新 change 的报告格式不合规会被红 | 四条解析规则 + 报告模板与本地入口明确要求；对加粗 / 中文括号 / 行内说明容忍；新增正反单测 |
| 解析过松导致 BLOCKED / 未定被读成 PASS | PASS 门失效 | 只认首个非空行且必须以 token 开头；`不是 PASS` 不以 token 开头；多小节直接报错 |
| active 触发面收窄导致 partial review 不再被检查 | 未完成 change 的评审报告没有出口/存在性门 | 有意为之（避免误伤在途 change）；由 partial-change 回归测试锁定；完成面与归档点仍强校验 |
| 删除 manifest 校验后历史漂移无人检测 | 历史 manifest / report / spec 的漂移不再被检测 | 接受：历史只读；known-debt 明确登记「检测能力消失」；第二刀决定归档处置 |
| `diff_hash` 自洽检查消失 | manifest 记录的 diff 不再被本仓校验 | witnessloop 严格 git span 部分补偿；known-debt 登记 |
| 非 building 的 `*-review.md` PASS 门消失 | `design-review.md` 即使存在也不再被本仓校验 | 当前流程不要求该文件；known-debt 登记；若未来恢复设计评审报告则另立检查 |
| 在途 change 被新检查误伤 | 开发被阻断 | 触发条件为完成面；当前唯一 active change 无 `reviews/` 且有 18 条未勾任务 |
| 文档漏改导致仍在产 ast manifest | 两套并存继续 | 测试中加文档守卫；grep 全仓校验；本地入口**全文件**同步 |
| 归档点新增 verdict 检查导致历史归档红 | 归档 PR 无法通过 | verdict 检查只在**新归档目录**（`_check_archived_completion_gate`）执行；`--check-archived` 不扫描历史 |

## Testing Strategy

- **先红**：
  - parser 单测：标题带中文括号后缀命中；fenced code 内的标题 / token 忽略；`**PASS**（...）`
    通过；`PASS（此前 CHANGES_REQUESTED 已收口）` 通过；`不是 PASS` / `未定` 报错；
    多小节报错。
  - active gate：PASS 通过、BLOCKED / CHANGES_REQUESTED / 缺失 / 未定报错；partial change
    即使有 `building-review.md` 也不报错（锁定收窄后的触发面）。
  - `--check-archived`：不再因 `spec_hash` / `tasks_hash` / 缺失 manifest 报错；历史归档
    （无 `## 闭环出口`）仍 exit 0；归档事件日志不可投影仍报错。
  - 归档点门：新建归档的 PASS 出口通过、非 PASS / 缺失报错；docs / 无 spec delta 的归档不
    触发 verdict 检查。
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
