# Proposal: 下掉与 witnessloop 重复的本仓 review manifest 校验（第一刀）

关联 issue：[#316](https://github.com/Xingkai98/asterwynd/issues/316)（探索结论与第一刀范围）；
跟踪总账：[#305](https://github.com/Xingkai98/asterwynd/issues/305)（保持 OPEN）。

## Change Type

- primary: process
- secondary: []

## Why

接入 witnessloop 后，本仓每个 change 要维护**两套审阅 manifest**：

- asterwynd 形态：`reviews/<phase>-review-manifest.json`（schema `review-manifest/v1`），由
  `agent/workflow/review_manifest.py` 产出，`scripts/check_openspec_artifacts.py` 消费；
- witnessloop 形态：`reviews/<stage>.manifest.json`（schema `witnessloop/review-manifest@v1`），
  由 `witnessloop manifest build` 产出，required 的 `gate / check` 消费。

#316 的探索 comment §5 **推荐 (d)**：保留两套 manifest，在收尾时从 witnessloop 形态确定性
派生 asterwynd 形态；该 comment 同时明确「不放宽任何判据」。**本 change 按用户在探索之后的
裁决偏离 (d)，改走第一刀：下掉本仓 checker 里与 witnessloop 重复的那块校验**，让 witnessloop
形态成为唯一被要求的审阅 manifest。本 change 只做**第一刀**：删除
`_check_review_manifests` 的 manifest 校验与它的两个调用点，停止产出 asterwynd 形态
manifest；`agent/workflow/review_manifest.py`、其测试与 80 份历史 ast manifest 留给第二刀。

**关键风险已定位并由本 change 正面处理**：旧 manifest 校验里唯一不被 witnessloop 覆盖的
判据是 `verdict == PASS`（witnessloop 源码明确不解析报告 verdict）。若把整块删掉，「只有
PASS 的审阅才算数」会消失。本 change 采用**方案 (i)**：保留一个极小的本地等价检查——从
`reviews/building-review.md` 的 `## 闭环出口` 读终结 verdict，要求 `PASS`。这是 #316
「不放宽任何判据」非目标的直接落实。

## 需求

1. **删除重复的 manifest 校验**：`scripts/check_openspec_artifacts.py` SHALL 删除
   `_check_review_manifests` 及 `check_change` / `--check-archived` 两处调用；SHALL NOT 再
   校验 asterwynd 形态 manifest 的字段、hash、`change_id`、`phase` 或 git span。
2. **保留 building review 的 verdict 判据（方案 i）**：本仓 checker SHALL 在实现完成的
   active change 与**本 PR 新归档**的 change 上解析 `reviews/building-review.md` 的
   `## 闭环出口`，要求小节**首个非空行以 `PASS` 开头**。解析规则 SHALL 为：标题以
   `闭环出口` 为前缀（容忍中文括号后缀）；忽略 fenced code；只认首个非空行（`不是 PASS`
   不以 token 开头、`未定` 不合法）；出现多个 `## 闭环出口` 小节 SHALL 报错。该判据只覆盖
   building review；非 building 的 `*-review.md` PASS 门随旧校验退役，SHALL 登记 known-debt。
3. **触发条件**：active 侧为「非 docs + 有 spec delta + tasks 全勾选」（这是 building-review
   存在性门原有的触发条件）；旧 manifest 校验的隐式宽触发（`reviews/` 存在即校验）SHALL 被
   收窄到完成面。归档点侧为「本 PR `--diff-filter=AR` 新建、且在 base 树不存在、且有 spec
   delta 的非 docs 归档目录」。在途 change SHALL NOT 被误伤。
4. **不做历史追溯**：80 份历史 ast manifest 与历史 `building-review.md` SHALL 保持原样；
   `--check-archived` SHALL 只保留归档事件日志可投影校验，SHALL NOT 对历史 manifest 做
   漂移检测，SHALL NOT 新增历史报告正文门槛。
5. **停止产出**：本地 `.claude/commands/review-loop.md`（gitignored）与仓内所有指示产出
   ast manifest 的文档 SHALL 改为只产 witnessloop 形态（`grill` / `grill-adversarial` /
   `building` 三份 `reviews/<stage>.manifest.json`），并写明归档 move 之后用归档目录名重建。
6. **其它检查行为不变**：RIR、Impact Analysis、benchmark smoke、归档点完成度（除 verdict
   这一项等价替代外）、backlog 一致性、受保护路径事件、grill / grill-adversarial 证据、
   platform-gate SHALL 一律保留。
7. **规格同步**：把「review manifest 不再是本仓要求、witnessloop 形态是唯一要求」写进
   `dev-workflow-gate`、`dev-workflow-state-machine`、`platform-gate` 的 delta 与当前规格。

## 非目标（第二刀及以后）

- **不动** `agent/workflow/review_manifest.py`、它的测试、`workflow_state.py review-manifest`
  写通道，以及 `scripts/flow-policy.json` 对 `-review-manifest.json` 的受保护路径规则。
- **不动** 80 份历史 ast manifest，也不回填 / 重算 / 删除。
- **不改 witnessloop 仓**，不碰 `v1` / `v1.7.0` tag，不放宽 `review_manifest_glob`。
- **不统一 schema**、不引入公共超集格式。
- **不改** RIR / Impact Analysis / benchmark / backlog / 归档点其它门 / platform-gate 的
  判定逻辑。
- **不新增** 对历史 review 报告的正文解析。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `dev-workflow-gate`：把「review manifest 两套并存，schema 统一延后」改写为「review manifest
  单套承载：本仓形态退役」；把「归档产物的证据形态在本仓并存两套」Scenario 改为只有
  witnessloop 形态，并同步 Purpose 的承载清单。
- `dev-workflow-state-machine`：删除「Review evidence manifest」Requirement，新增
  「Review evidence 与终结 verdict」Requirement（witnessloop 形态唯一要求 + `## 闭环出口`
  的 PASS 判据 + 历史不追溯）；修改「审阅闭环的轮次模型」的机械门禁段，移除本仓 checker
  的 manifest 字段 / hash / verdict 判据描述。
- `platform-gate`：修改「降级为非必过的检查仍须运行」的理由清单，移除「本仓形态的
  review manifest 没有 witnessloop 替代物」这一已不成立的例子。

## Impact Analysis

> 行号基于 `origin/master` = `1d6cfee`（2026-10-17）。

- **代码**：`scripts/check_openspec_artifacts.py`
  - `:1111-1153` 删除 `_check_review_manifests`；`:1353` 的 active 调用替换为新的
    `_check_building_review`（存在性 + `## 闭环出口` PASS）；
  - `:1732-1754` 删除 `--check-archived` 中的 manifest 校验与 `tasks_hash` 汇总，
    保留 `_check_archived_projectable`；`:1715` help 文案同步；
  - `:1573-1578`、`:1626-1640` 的注释 / docstring 同步（grill-adversarial 证据门不变）；
  - `_check_archived_completion_gate` 在 building-review 存在性之后增加同一个 verdict 检查。
- **测试**：`tests/test_openspec_artifact_checker.py`
  - 删除 / 改写断言 `review manifest missing`、`spec hash mismatch` 与
    `tasks_hash 已按归档语境跳过` 的用例；
  - 新增 `## 闭环出口` PASS / BLOCKED / 缺失 / 不唯一、manifest 不再被要求、
    `--check-archived` 不再对 drift manifest 报错等回归测试；
  - `test_verify_review_manifest_archived_path` 等**模块级**测试保留（模块不动）。
- **消息与规则文档**：`AGENTS.md:24,108,112-114,223`、`README.md:153` 与
  `README_EN.md:153`（必须同改）、`docs/development-guide.md:292-298,351`、
  `docs/requirements-process.md:45,54,293`、
  `docs/interview-script/questions/Q12-ci-testing.md:10,44`、
  `docs/interview-script/questions/Q14-dev-process.md:13,15,27,38,44,49,55`。
- **债务登记（受保护路径）**：`docs/known-debt.md` 新增退役记录与剩余第二刀清单；
  `docs/openspec-change-backlog.md` 先登记、收尾移除。
- **规格（受保护路径）**：`openspec/specs/dev-workflow-gate/spec.md`、
  `openspec/specs/dev-workflow-state-machine/spec.md`、`openspec/specs/platform-gate/spec.md`。
- **CI**：`.github/workflows/ci.yml` 只改归档校验步骤的名称 / 注释；命令与 flag 不变，
  仍跑 `--check-archived --skip-protected-paths --skip-backlog`。
- **本地入口（不进版本控制）**：`/home/happy/my-agent/.claude/commands/review-loop.md`
  第 6 步改为 witnessloop manifest build；不混进 PR。
- **明确不变**：`agent/workflow/review_manifest.py` 与 `tests/agent/workflow/test_review_manifest.py`、
  `tests/test_workflow_state_cli.py`、`tests/test_workflow_archive_write_channel.py`、
  `scripts/flow-policy.json`、`.witnessloop/**`、平台 required 配置、80 份历史 manifest。
- **行为变更（用户可见）**：实现完成的 change 不再需要 ast manifest；`## 闭环出口` 成为
  building review 的机械格式要求（只在新触发面上生效）；历史归档不再做 manifest 漂移检测。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 命中判据表「走 grill 的非平凡 change」与「对标上游实现」——本 change 要删除一块
  门禁逻辑，必须逐条确认 witnessloop v1.7.0 是否覆盖被删判据，并与 #316 的探索结论对账。
- research questions:
  1. witnessloop v1.7.0 的 `check` 读取哪些 manifest 字段与报告内容？`verdict` 是否被读取？
  2. asterwynd `_check_review_manifests` 的每个判据（`change_id` / `phase` / `verdict` /
     reviewer / git span / `tasks_hash` / `spec_hash` / `report_hash` / `diff_hash`）在
     witnessloop 侧是否有等价物？哪些会随删除而消失？
  3. 本仓历史 `building-review.md` 的终结 verdict 形态是什么？「极小等价检查」需要兼容哪些
     格式，还是只能对新报告生效？
- findings:
  1. **witnessloop 不读 verdict**：`REVIEW_MANIFEST_REQUIRED_FIELDS`（`src/witnessloop/constants.py:110-120`，
     v1.7.0 与 `main` 同）不含 `verdict` / `schema`；`checkcmd.py:188-192` 明确写「不解析
     报告里的 verdict 文本」；`constants.py:79,90` 同样声明 building 门禁只要求证据存在。
     ⇒ `verdict == PASS` 是 asterwynd 独有判据，删除后必须由本仓保留（方案 i）。
  2. **witnessloop 覆盖大部分其余判据且更严**：`contract.py:638-646` 校验必填字段与
     `report_path`；`:665-671` 强制 `reviewer_run_id != author_run_id`；`:679-...` 做严格
     git span（sha 形状 / 存在 / 祖先 / 审后非证据文件）；`:764-803` 校验 `report_hash`、
     `tasks_hash`（归档也校验）、`spec_hash`；孤儿规则绑定 `reviews/**/*.md`。
     ⇒ 被删的重复面：`change_id`、`phase`、reviewer 非空、`report_hash`、`tasks_hash`
     （active）、`spec_hash`、git span、报告必须绑定 manifest。
  3. **会随删除消失、但不由 witnessloop 补齐的判据**：building review 的
     `verdict == PASS`（由方案 i 保留）、非 building `*-review.md` 的 PASS 门（登记
     known-debt），以及 `diff_hash` 强校验（witnessloop 把它当 informational，
     `manifestcmd.py:181-184`；其严格 span 部分补偿）。剩余损失登记入
     `docs/known-debt.md`。
  4. **历史报告格式不统一**：实测 79 份归档 `building-review.md` 中，仅 1 份有
     `## 闭环出口`（`2026-10-17-round-model-align`）；67 份有 `## Verdict` 前缀标题、12 份
     没有；按「最后一个 `## Verdict` 小节的首个 verdict token」统计为 61 PASS /
     5 CHANGES_REQUESTED / 1 无 token，且 15 份该小节混有多个 token。对历史报告做统一解析
     会产生假红。⇒ verdict 检查只对本 change 之后的 active / 新归档生效，历史不追溯。
  5. **历史 manifest 不可干净迁移**（#316 comment 实测）：80 份 ast manifest 中 27 份
     `tasks_hash` 漂移、8 份 base/head 提交不可解析、全部缺 `author_run_id`、`spec_hash`
     与 witnessloop 算法 79/80 不同。⇒ 不迁移、不双读，留给第二刀决定归档处置。
- design impact:
  - ⇒ 删除 `_check_review_manifests` 的 manifest 校验与两个调用点，保留 building review
    存在性门。
  - ⇒ 新增一个只解析 `## 闭环出口` 的小函数，在 active 与归档点两处复用；不解析轮次、
    severity、deferred，也不读取 manifest。
  - ⇒ `--check-archived` 缩小为事件日志可投影校验；历史归档保持冻结。
  - ⇒ 文档全面改为「witnessloop 形态唯一」，并在 known-debt 登记 `diff_hash` 强校验、
    历史 drift 检测、非 building review PASS 门三项残余边界。

## 用户故事

- 作为本仓开发者，我实现完一个 change 后只需产三份 witnessloop manifest，不再重复维护
  第二套 ast manifest。
- 作为审阅者，我的 `building-review.md` 终态必须写 `## 闭环出口` 且为 PASS，checker 会
  机械检查；BLOCKED/CHANGES_REQUESTED 不会被当成通过。
- 作为维护者，我删除的是重复校验，RIR / Impact / benchmark / 归档完成度 / backlog 等
  项目规则没有被顺手削弱。
