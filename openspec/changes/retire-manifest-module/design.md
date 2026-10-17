# Design: 删除 legacy asterwynd 形态 review manifest 生成模块与写通道（第二刀）

## Context

第一刀（`retire-manifest-check`，PR #317 / merge `5225207`）删除了 checker 的
`_check_review_manifests` 与两个调用点，并在
`openspec/specs/dev-workflow-gate/spec.md` 中明确规定：`agent/workflow/review_manifest.py`
与 `workflow_state.py review-manifest` **由第二刀处置**。第一刀还保留了：

- 80 份历史 `reviews/<phase>-review-manifest.json`（冻结，不迁移）；
- `scripts/flow-policy.json` 的 `-review-manifest.json` 受保护规则；
- 模块单测 `tests/agent/workflow/test_review_manifest.py` 与三处 CLI 正向测试。

本 change 的输入不是「再设计一套 manifest」，而是把上述生产面与配置面删除干净，同时保证
**唯一活消费者**——`workflow_state.py artifact-event` 的归档目标回退——不随模块删除而回退。

实测事实：

- `grep -rn "review_manifest"` 的生产消费者只有 `scripts/workflow_state.py:41`（import
  `change_dir_for` / `write_review_manifest`）与 `:384`（归档回退）；其余命中是测试、策略、
  文档与 `resume_audit` 的忽略项。
- `change_dir_for` 在 `archived=True` 时用 `re.match(rf"\d{{4}}-\d{{2}}-\d{{2}}-{id}")`
  且无 `$` 锚点（模块 `:47`），已知会把 `alpha` 命中 `2026-09-22-alpha-beta`；调用侧
  `_archive_dir_matches_change_id` 已用 `re.fullmatch` 做 fail-closed 断言
  （`docs/known-debt.md` 的 A-遗留 2）。
- `scripts/workflow_guard.py:271` 的 privileged CLI 豁免正则包含 `review-manifest`；
  `scripts/flow-policy.json:55-59` 与 guard 内嵌默认表把 `-review-manifest.json` 当
  `manifest_verified` 受保护路径。
- `agent/workflow/resume_audit.py:340` 把 `-review-manifest.json` 当 workflow 管理文件忽略。
- 历史 80 份 manifest 全部位于 `openspec/changes/archive/**`，已被归档前缀规则覆盖。

## Goals / Non-Goals

**Goals:**

- 删除模块、CLI 子命令、保护规则、忽略规则与所有活引用。
- 保留 `artifact-event` 的归档写入能力与 fail-closed 目标解析。
- 历史文件冻结；witnessloop 形态证据与 `## 闭环出口` 判据不受影响。
- 规格与文档只描述一套 manifest（witnessloop 形态）。

**Non-Goals:**

- 不改 witnessloop 仓、tag、`.witnessloop/**` 或 `review_manifest_glob`。
- 不迁移、不重算、不删除历史 manifest。
- 不统一 schema，不新增能力。
- 不动 `artifact-event` 的其它语义、投影刷新或其它受保护写通道。

## Decisions

### Decision 1: 直接删除模块，不为 `artifact-event` 保留薄壳

**选择**：删除 `agent/workflow/review_manifest.py`。把 `artifact-event` 唯一需要的归档目录
解析内联为 `scripts/workflow_state.py` 的私有 helper。

**理由**：删除 CLI 后模块没有生产消费者。保留薄壳会让「已退役」的代码继续以 import 路径存在，
与第一刀规格的「由第二刀处置」相矛盾；也会让后续读者误以为仍有一条活通道。内联只涉及一个
约 12 行的解析函数，且它天然属于「受保护写通道的目标解析」，放在 `workflow_state.py` 比放在
manifest 模块更贴切。

**备选**：

- (a) 保留模块，只删 CLI：否。模块仍被测试与文档引用，退役不彻底。
- (b) 把 `change_dir_for` 抽到新的 `agent/workflow/change_paths.py`：否。为一个函数新增模块，
  增加 import 面而没有复用价值；`artifact-event` 是唯一调用方。

### Decision 2: 内联解析用 `fullmatch`，顺带关闭已知的前缀碰撞债

**选择**：内联 helper 以 `CHANGES_ROOT / "archive"` 为根（与 `_require_change_target` 的
CWD 相对口径一致，不用 `_PROJECT_ROOT`），按目录名排序扫描；按 `name == change_id` 或
`re.fullmatch(r"\d{4}-\d{2}-\d{2}-<escaped id>", name)` 匹配。命中多个目录（同一 id 有两个
日期前缀）时以明确错误 fail-closed，不依赖 `iterdir()` 顺序。删除已不可达的
`_archive_dir_matches_change_id` 调用侧断言——resolver 自身保证返回目录名一致。

**理由**：这是被移动的代码，不是新功能。把已知 bug 原样搬进新位置会让
`docs/known-debt.md` 的「A-遗留 2」永远无法关闭；而调用侧断言本来就用 `fullmatch`，内联后
两端口径一致，行为对合法输入不变、对兄弟前缀碰撞从「解析到错误目录后拒绝」变为「直接判不存在」。
既有回归 `test_archived_resolution_rejects_longer_prefixed_sibling` 继续锁定「不得写入兄弟
change」，并额外断言错误为「不存在」（旧 `re.match` 路径产出的是「目录名与 change id 不匹配」，
两句可区分）；新增同 id 多日期目录用例锁定 fail-closed。

**备选**：保留 `re.match` 语义，把债继续留在新 helper 上。否——这等于在删除 legacy 的同一
change 里主动复制一个已知缺陷。

### Decision 3: 删除子命令，不保留 deprecation 提示

**选择**：从 argparse 删除 `review-manifest`；调用它得到 `invalid choice`（非零退出）。
在 `tests/test_workflow_state_cli.py` 的 `REMOVED_SUBCOMMANDS` 加入该命令，并断言无副作用。

**理由**：仓库已有「已删子命令必须未知、非零、无副作用」的负向回归惯例
（`TestRemovedSubcommands`）。保留一个「友好报错」的占位子命令会让 CLI surface 与文档继续
承认这个通道存在，违背单一活通道的目标。

**备选**：保留子命令但打印「已退役」。否——多一个需要维护与测试的命令面，且用户仍可能误以为
它还有用途。

### Decision 4: 删除受保护路径规则，保留 `manifest_verified` 词汇

**选择**：从 `scripts/flow-policy.json` 与 guard 内嵌默认表删除
`{"path": "-review-manifest.json", governance: "manifest_verified"}`；从 privileged CLI
豁免正则删除 `review-manifest`。`_ALLOWED_GOVERNANCE` 与 `policy-set --governance` 继续
接受 `manifest_verified`；`flow-policy.json` 的 `_description` **不改**（该文件是
`cli_written`，`policy-set` 没有修改顶层说明的入口），“当前无规则使用”只记录在
`docs/known-debt.md`。

**理由**：

- 没有生产者之后，active change 里不应再出现这种文件；如果人工创建，它不是任何流程承认的
  artifact，保护它没有意义。
- 唯一仍存在的历史文件在 `openspec/changes/archive/**` 下，已被 `event_explained` 前缀规则
  覆盖，删除规则不会让历史文件失去保护。
- `manifest_verified` 是通用 governance 枚举值，删除它会扩大策略 schema 变更面并影响
  `policy-set` 的 choices；当前无规则使用，保留但不宣传即可。策略文件的顶层说明不在合法
  CLI 写通道内，因此不要求改它。

**备选**：保留规则，理由「历史文件仍在」。否——历史文件已有归档规则；保留只会让 guard 继续
拦截一个不再存在的流程产物，并让 policy 读者误判。

### Decision 5: 删除 resume audit 的 manifest 忽略项

**选择**：从 `_is_resume_audit_ignored` 删除 `normalized.endswith("-review-manifest.json")`。

**理由**：该忽略项存在的目的是不把 workflow 自己写的 manifest 当成「禁用期间的未归类改动」。
写通道删除后，任何对历史 manifest 的修改都不再由 workflow 产生，应当作为普通文件改动被
resume audit 发现。新增回归测试锁定该行为。

**备选**：保留忽略。否——它会让历史证据文件的改动继续隐形。

### Decision 6: 测试按「删除面 / 保留面」成对处置

**选择**：

- 删除 `tests/agent/workflow/test_review_manifest.py`；
- 删除/改写所有正向 manifest 用例；在 CLI 测试中加入负向回归；
- 保留 `test_check_archived_ignores_retired_manifest_drift`（历史文件不被 checker 消费的证据）；
- 保留 `artifact-event` 的归档、投影、非法 id、兄弟前缀碰撞用例；
- 新增：模块文件不存在、`review-manifest` 未知子命令、策略表无该规则、guard 默认表 parity、
  resume audit 能发现 manifest 改动、规范文档不再指示使用该通道。

**理由**：删除生产代码必须同时删除「它还能工作」的正向断言，否则测试会永久红；但删除正向
覆盖不等于丢失能力覆盖——`artifact-event` 的归档能力仍由原有用例覆盖。历史冻结与 checker
忽略行为保留原测试。

### Decision 7: 历史 80 份文件保持冻结，不做任何迁移

**选择**：不删除、不改写、不重算；不新增「历史 manifest 数量」门禁。

**理由**：第一刀已确认 80 份无法干净迁移（缺 `author_run_id`、27 份 `tasks_hash` 漂移、
8 份提交不可解析），且 checker 已不消费它们。删除文件会破坏归档历史；迁移会产生无消费者的
新文件。保持原位是最小且可审计的处置。

### Decision 8: 规格与文档改成「一套 manifest」的完成态

**选择**：

- `dev-workflow-gate`：MODIFIED「review manifest 单套承载：本仓形态退役」，删除「保留到第二刀」
  的句子；Scenario 改为「模块与 CLI 已删除、调用为未知子命令」。
- `dev-workflow-state-machine`：MODIFIED 受保护写通道相关 Requirement / Scenario，移除
  `review-manifest`。
- `change-documentation`：MODIFIED 受保护 artifact 写通道清单。
- `AGENTS.md`、`docs/development-guide.md`、`docs/requirements-process.md`、
  `interview-script/Q14`、`known-debt`、`ADR-0004` 同步；新增 `ADR-0005` 记录本次删除的
  备选与理由（AGENTS ADR 规则）。

## Testing Strategy

- **TDD 红→绿**：先写/改 6 组测试（CLI 未知子命令、模块不存在、策略表无规则、resume audit
  不忽略、write-channel 用例改写、文档守卫），在删除前运行确认**红**；删除后转绿。
- **单元层**：
  - `tests/test_workflow_state_cli.py`：`review-manifest` 未知、非零、无副作用；另用合法
    target + 完整参数证明「删除前会写 manifest」（避免 `_seed_gen2_change` 无锚点导致平凡通过）；
  - `tests/test_flow_policy.py`：策略表 / guard 默认表 parity 且无该规则；
    `_is_privileged_cli` 对 `review-manifest` 为 False、对 `artifact-event` 为 True；
  - `tests/agent/workflow/test_resume_audit.py`：历史 manifest 改动被发现；
  - `tests/test_retire_manifest_check.py`：模块不存在 + 文档守卫；守卫用「调用/导入形态」判据，
    并允许同句含「已删除 / 已退役 / 不存在」的退役说明；带阳性/阴性对照，确保 marker 有判别力；
- **集成层**：`tests/test_workflow_archive_write_channel.py` /
  `tests/test_workflow_protected_write_channel.py` 保留 `artifact-event` 的 active / 归档 /
  gen-1 / 非法 id / 同前缀兄弟目录场景；用 subprocess 跑真实 CLI，避免只在函数层自证。
- **checker / 解析层**：保留 `test_check_archived_ignores_retired_manifest_drift`；兄弟前缀
  用例断言错误为「不存在」并与旧「不匹配」路径区分；新增同 id 多日期目录 fail-closed 用例；
  全量 checker 用 `--base-ref origin/master --require-base` 跑。
- **变异验证**：临时恢复任一删除面（CLI 子命令 / 保护规则 / resume audit 忽略项），对应
  测试必须变红；恢复后转绿。
- **全量回归**：删除前先记录 `uv run pytest -q` 基线（已知 2 条本机 `/tmp` 环境失败与
  Playwright 偶发）；删除后逐条对账，不得新增失败。
- **人工探针**：在临时仓库外实测 `workflow_state.py review-manifest` 退出码与文件副作用；
  对真实归档 change 跑 `artifact-event`，确认事件仍落归档目录。
- **README 双语**：`README.md:264` 与 `README_EN.md:264` 的目录树用词在同一变更内同步，
  grep 复核同时覆盖 `review manifest`（空格）与 `review[-_]manifest`。

## Risks / Trade-offs

- **受保护面收窄**：active change 中手写 `*-review-manifest.json` 不再被 guard 立即拦截。
  代价可接受：它不是任何流程的合法产物，也没有消费者；归档内的历史文件仍在保护范围。
- **`manifest_verified` 成为未使用词汇**：保留在 schema 中，避免扩大策略变更；只在
  known-debt 中标注「当前无规则使用」（策略文件顶层说明不在 agent 合法写通道内）。
- **删除测试导致用例数下降**：模块单测约 300 行被删除，但对应能力已不存在；CLI 负向回归
  与原 `artifact-event` 覆盖补足「删除后不静默成功」与「归档写通道不回退」。
- **内联解析修正了已知 bug**：`alpha` 与 `alpha-beta` 的碰撞从「解析到错误目录后拒绝」
  变为「解析不存在」；同 id 多日期目录从「依赖 `iterdir()` 顺序取第一个」变为「明确错误」。
  错误文案变化，但 fail-closed 结论不变，既有回归继续覆盖。
- **文档守卫的 marker 选择**：规范文档会写「模块已删除」，裸文件名 marker 会把退役说明
  自判红；守卫只匹配调用/导入形态（`workflow_state.py review-manifest` 带参数、
  `agent.workflow.review_manifest`），同句含「已删除 / 已退役 / 不存在」时放行，并排除守卫
  自身文件；用阳性/阴性对照锁定判别力。
- **历史文件的 future 修改不再被 resume audit 忽略**：这是有意暴露，不是回退。

## Pre-Implementation Review

**Grill（独立零记忆，2026-10-17）**：产出 7 条 Confirmed Decisions、0 条 Open Questions、
13 条 Code-Resolved Questions（记录见 `reviews/grill-design.md`）。关键结论：

- 删除面与保留面成立：生产侧唯一消费者是 `scripts/workflow_state.py:41,384`；删模块 +
  内联 12 行归档解析足够，不需要薄壳或新模块；80 份历史 manifest 全在 archive 下。
- 7 条 medium 风险已整合进本设计与 tasks：文档守卫 marker 钉成调用/导入形态、全仓 import
  守卫用正则并排除自身、CLI 负向用例构造合法 target、补「归档内 manifest 仍受 guard 保护」
  回归、known-debt 更新面扩到 `:25,:168-177,:229`、grep 同时覆盖连字符/下划线、
  `policy-set` 用 `--path=` 形式。
- 低风险也一并处置：内联 helper 钉死 base 与排序、同 id 多日期目录 fail-closed；
  `subprocess` import 清理、行号与模块行数订正。

**设计阶段对抗环（`reviews/grill-adversarial.md`）**：第 1 轮开批 4 条 medium（A1 README
双语漏项、A2 解析新行为缺判别测试、A3 文档守卫无红点/无阳性对照、A4 `_description`
不可由合法通道修改），全部修复并复核通过；批次为空，出口 **PASS**。验证期新增 3 条
low 已登记并落齐。
