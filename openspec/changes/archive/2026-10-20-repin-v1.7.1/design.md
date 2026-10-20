# Design: witnessloop caller 回钉 v1.7.1 并同步 init 台账

## Context

本 change 是上游 witnessloop #42 修复后的接入方收尾动作，不是一次新的门禁设计。现状由三份事实构成：

1. 上游 v1.7.1 已发布（annotated tag object `c4f681a7…` → commit `07bf23b3…`），`gate.yml` 对 tag 用 `job.workflow_ref` 的 `refs/tags/<tag>` 作为包 ref；
2. 本仓 caller 在 hotfix PR #327 后钉的是 commit `c9b2811…`，`init-manifest.json` 的 `gate_ref` 仍是 `@v1.7.0`；
3. 本仓 `dev-workflow-gate` 规格要求 caller 钉「具体发版 ref」，并把升级定义为 `witnessloop init --gate-ref <新 ref>` 一处动作。

## Decisions

### Decision 1: 回钉到 annotated tag `v1.7.1`，而不是继续钉 commit

**选择**：caller `uses: Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1`。

**理由**：commit pin 是上游故障期的应急手段，不是规格要求的稳态；v1.7.1 已把 annotated tag 作为受支持形态处理。继续钉 commit 会让「caller ref 同时决定 workflow 与包版本」这一单一入口重新分裂成两个需要人工维护的 ref，也违反当前规格的「具体发版 ref」断言。

**来源**：witnessloop issue #42（已关闭）；v1.7.1 的 `gate.yml` 解析分支与 `docs/gate.md` §1.2；`openspec/specs/dev-workflow-gate/spec.md` 的「阶段 C 翻开关后的 required 形态」。

### Decision 2: 用 `witnessloop init` 重写，不手改 caller / 台账

**选择**：执行 `witnessloop init --root . --gate-ref "Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1" --policy .witnessloop/policy.json`，由工具同时重写 caller 与台账；不使用 `Write`/`Edit` 手改 `.witnessloop/init-manifest.json`。

**理由**：`sync_caller_gate_ref` 把「重写 caller」与「更新台账 `gate_ref` + caller 条目 `sha256`」放在同一个函数里；只改一边会让台账与磁盘不一致，后续 plain `init` 走漂移分支、`uninit` 也可能半回滚。`--policy` 必须显式传入本仓已落地的 policy。grill 实测（读 `initcmd.py`）不传时的失败模式**不是**「静默丢掉受管面」，而是：带 `--gate-ref` 时先重写 caller 与台账（写操作**不回滚**），随后因出厂 policy 与盘上定制 policy 冲突而 exit 1——属于「半完成 + 响亮失败」，恢复动作也不同。另：`init` 在 `.github/witnessloop-tests.txt` 不存在时会种下哨兵 `<<REPLACE-ME>>`，而哨兵会让 `check` 判红；本仓该文件已存在（内容 `uv run --extra dev pytest -q`），运行前必须确认它不是哨兵。

**来源**：witnessloop v1.7.1 `src/witnessloop/initcmd.py` 的 `sync_caller_gate_ref` / `load_policy_override` / `run`；`docs/gate.md` §1.2（定制 policy 仓 plain `init` 退 1）；本仓 `.witnessloop/init-manifest.json` 的 `created_files` 台账形态与 `.github/witnessloop-tests.txt`。

### Decision 3: 使用 v1.7.1 源码运行 CLI，不用 PATH 上的 0.1.0

**选择**：`uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop ...`，与 CI 的 `gate.yml` 安装方式同源。

**理由**：本机 PATH 上的 `witnessloop 0.1.0` 的 `init` 不接受 `--policy`，也没有「显式 `--gate-ref` 重写已接入仓」的语义；用它会在第一步就报 `unrecognized arguments`。上游 `docs/gate.md` 的升级动作也明确要求「先把 CLI 升上去，再 `init --gate-ref`」。不要用本地源码 / editable 安装做验收：没有 PEP 610 `vcs_info` 时 `check` 只会打印 `requested_revision=<未知>`，无法证明跑的是 tag 对应的那份代码。uvx 从 tag 安装可复现，实测 `check` 第一行为 `requested_revision=refs/tags/v1.7.1，commit_id=07bf23b3…`；而 `__version__` 恒为 0.1.0，不能靠 `--version` 判版本。

**来源**：本机 `witnessloop init --help` 实测（无 `--policy`）；witnessloop v1.7.1 `cli.py` / `docs/gate.md` §1.2 的升级步骤；`uvx --from git+…@refs/tags/v1.7.1 witnessloop check` 实测输出。

### Decision 4: 受保护写入事件与规格同步事件都写在本 change 的事件文件

**选择**：`openspec/changes/repin-v1.7.1/workflow-events.jsonl` 包含三条**必需**的精确路径事件：

- `protected_artifact_explained`，`artifact_path: ".witnessloop/init-manifest.json"`；
- `current_spec_synced`，`artifact_path: "openspec/specs/dev-workflow-gate/spec.md"`；
- `backlog_updated`，`artifact_path: "docs/openspec-change-backlog.md"`。

`change_archived` 可以保留为簿记，但**不列为门禁依赖**：witnessloop 的 `covers` 只按精确文件路径匹配，目录路径不会豁免任何受保护文件；归档 move 本身另由 `_archive_move_exempt` 豁免。

**理由**：witnessloop 的事件匹配只看 `event_type` / `artifact_path` / `reason` / `approved_by`，并且事件文件只从 change 目录读取；`.witnessloop/**` 与 `openspec/specs/**` 都是受保护路径，必须有精确路径的解释事件。事件不能写到历史 change 目录（会把红转移到那个文件）。

**来源**：`.witnessloop/policy.json` 的 `protected_paths` / `protected_write_event_types`；witnessloop v1.7.1 `events.py` 的 `load_all` / `covers`。

### Decision 5: 规格只改「当前发版 ref / 包 ref 推导」这一条，不重写门禁边界

**选择**：MODIFIED `阶段 C 翻开关后的 required 形态`：当前 ref 改 `v1.7.1`；把「包 ref 由 `job.workflow_sha` 推导」订正为「tag 由 `job.workflow_ref` 的 tag ref 推导，分支 / commit pin 才用 `job.workflow_sha`」；升级命令补上本仓必需的 `--policy .witnessloop/policy.json`；补一条「应急 commit pin SHALL 在同一收尾批内回钉并发版 ref，不构成稳态」。MODIFIED 块 SHALL 携带该 Requirement 的**全部存活 Scenario**（现有 4 个 + 新增 1 个 = 5 个）——OpenSpec 1.4.1 的 MODIFIED 是整块替换，漏抄现有 Scenario 会被 apply 拒绝或静默丢失；`openspec validate` 不比对主 spec 的 Scenario 集合，必须显式断言标题集合。

**理由**：required 集合、降级不关闭、平台闸门等边界不因这次回钉改变；把改动面控制在这一条 Requirement 与 Purpose 的事实行，避免制造新的漂移点。`v1.7.0` 在历史 ADR / 归档里的行为记录是历史证据，不当作现状改写；只改仍以现在时描述当前接入版本的文档。规格的 normative 句**不钉精确 uv minor 版本**：上游 issue #42 记录的是 0.13.1 绿 / 0.13.3 红，`gate.yml` 注释写 0.13.2 起；正文只写「uv 新版本会拒绝 annotated tag object sha」，把精确阈值留给上游记录。

**来源**：`openspec/specs/dev-workflow-gate/spec.md:225/:238/:239`；witnessloop v1.7.1 `gate.yml` 的解析注释；witnessloop issue #42 正文。

### Decision 6: 验证次序：先归档/move/结算，再 build manifest，再本地 check，最后 CI

**选择**：

1. **工具层**：用**完整命令**（带 `--gate-ref` 与 `--policy`）跑第二次 `init`，必须幂等（exit 0、`init：已接入 witnessloop（幂等，无改动）。`）；盘上 caller 与台账 `gate_ref` 一致。plain `init` 在定制 policy 仓会 exit 1，这是既有预期，不作为判据。
2. **内容与证据次序**：所有内容（含 spec / backlog / tasks 结算）落定 → 归档 move → 在**归档目录**用**归档目录名** build 三份 manifest → 单独提交证据 → 本地 `check`（同时断言 `1 个 change 目录`、`change：2026-10-20-repin-v1.7.1（归档）`、`check：通过 ✓` 与 `requested_revision=refs/tags/v1.7.1`）。
3. **CI 层**：本 PR 的 `gate / check` 日志里必须出现包 ref `refs/tags/v1.7.1`（来源 `job.workflow_ref` 的 tag ref），且该 check pass；合入后在 `master` 上复核 caller / 台账 / 幂等。

**理由**：`init` 成功只证明文件写对；本地 `check` 证明 change 契约与证据形态；CI 日志证明「annotated tag 修复真的生效」——这是本 change 的核心验收，不能用「文件看起来对」代替实测。grill 实测指出两处陷阱：① 未提交 / 未跟踪的 change 目录不进 `git diff`，`check` 会以 0 target 打印「通过 ✓」（假绿）；② `check` 对每个 target 要求 `reviews/` + manifest + grill stage，因此在 manifest 产出前跑必然红。⇒ 本地 check 只能放在归档 + manifest + 证据提交之后，且必须断言「确实检到了目标」。

**来源**：witnessloop v1.7.1 `checkcmd.py` 的 target 求值与 `contract.validate_change_dir` / `validate_review_manifests`；`gitutil.changed_files` 的 `base...head` 语义；witnessloop issue #42 的期望第 1、3 条；本仓 `AGENTS.md` 的验证命令速查。

### Decision 7: 本 change「出生即归档」，manifest 只在归档后构建

**选择**：本 change 的目录在 base 树里不存在（立项与归档在同一 PR）⇒ 相对 base 的最终 PR diff **恒为 `A`**（即使分支内部先提交 active 再 move，base 树没有源路径，最终 diff 也不出现 rename）。**唯一**的 `manifest build` 时机是归档 move 之后、在已提交的「内容 + move」HEAD 上，用 `--change 2026-10-20-repin-v1.7.1` 构建三份 manifest。归档前用源 id 产出的 manifest 不作数：归档 target 的别名集合只含归档目录名，且不满足本规格「归档后用归档目录名重建」的要求。

**理由**：witnessloop 的归档别名来自「本次 diff 里的 rename 源」；出生即归档没有源 id。对抗轮在临时仓库实测：若分支内部先提交 active 再 move，source alias 可能让旧 manifest 过 `check`，但最终 PR diff 仍是 `A`、且不满足规格；把唯一 build 点固定在归档后即可覆盖所有次序。

**来源**：`git status --short` 显示 `?? openspec/changes/repin-v1.7.1/`；`git ls-tree -d --name-only origin/master openspec/changes/` 无该目录；witnessloop v1.7.1 `docs/gate.md` 的「出生即归档」段；`contract.py` 的 `accepted_change_ids` / source alias。

### Decision 8: 合入必须用 `--merge`，不用 squash

**选择**：PR 以 merge commit 合入。

**理由**：witnessloop 的 review manifest 绑定 `head_sha`，并要求它是被检 head 的祖先；squash 会把 manifest 绑定的 revision 从 `master` 历史抹掉，日后任何触及该 change 目录的 PR 都会因此判红。本仓已有实测先例。

**来源**：`docs/development-guide.md` 的 Review evidence 纪律；`openspec/changes/archive/2026-10-17-stage-c-required-switch/tasks.md` 的 5.6。

## Risks

| 风险 | 触发迹象 | 处置 |
| --- | --- | --- |
| v1.7.1 仍无法从 tag ref 安装 | 本 PR `gate / check` 的 resolve step 输出 fallback / 安装失败 | 停止，保留现状为 commit pin，把上游失败证据写回 issue #331；不擅自改上游仓或 tag，不降级门禁 |
| `init` 误用出厂 policy | 先写 caller/台账后 exit 1（写操作不回滚），或 `git diff .witnessloop/policy.json` 非空 | 运行前核对 `--policy .witnessloop/policy.json` 与 tests 文件非哨兵；失败后按 `init` 的「半完成」状态人工核对 caller/台账 |
| 台账与 caller 只改一边 | `init` 重跑报漂移、或 `uninit` 预演拒绝 | 只使用工具写入；跑第二次幂等作为结构检查 |
| 事件路径写错 / 用通配 | `gate / check` 报「受保护路径被写入，但没有结构化解释事件」 | 三条必需事件写精确路径，不加 `*`；本地 `witnessloop check` 先行验证 |
| 证据晚到导致 stale | `check` 报「审阅的是旧 revision」 | 固定次序：内容 → 归档 move → manifest → 证据提交；之后不再改内容 |
| `origin/master` 在 worktree 过期 | 本地 check 的 base 不对、或列出别的 PR 的 diff | check 前 `git fetch origin master`，记录 `git rev-parse origin/master` |
| 规格/文档仍有旧版本口径 | grep 仍命中 `v1.7.0` 的现状句 | 只对当前态文件做零命中断言；历史 ADR / 「v1.7.0 实测」记录列入 allowlist，不误改 |
| 回滚到 @v1.7.0 会复发 #42 | 回滚后 gate 再次硬红 | 回滚目标写死 hotfix commit `c9b2811…`；回滚同样要用 `init` 并补新事件 |

## Testing Strategy

| 编号 | 动作 | 期望 |
| --- | --- | --- |
| T1 | 前置：`.github/witnessloop-tests.txt` 存在且非 `<<REPLACE-ME>>`；`uvx --from git+…@refs/tags/v1.7.1 witnessloop init --dry-run --root . --gate-ref "...@v1.7.1" --policy .witnessloop/policy.json` | 报告将重写 caller 并同步台账；不改 policy |
| T2 | 真跑同一条 `init`（去掉 `--dry-run`） | caller `uses:` 为 `@v1.7.1`；台账 `gate_ref` 同步；policy 逐字节不变（sha256 前后一致） |
| T3 | 同一条完整 `init` 再跑一次 | `init：已接入 witnessloop（幂等，无改动）。`，exit 0 |
| T4 | grep caller / 台账 / 当前态文档 | 当前态不再出现 commit pin 或 `@v1.7.0` 现状句；历史 allowlist 保留 |
| T5 | 内容 + spec/backlog + tasks 结算 → 归档 move | 归档目录 `2026-10-20-repin-v1.7.1` 含全部必需件；active 目录不存在 |
| T6 | 归档后 `manifest build --change 2026-10-20-repin-v1.7.1` 三份（不同 reviewer/author run id） | grill / grill-adversarial / building 三份 manifest；绑定 reviews 下全部 `.md` |
| T7 | 证据提交后 `uvx --from git+…@refs/tags/v1.7.1 witnessloop check --root . --base origin/master --head HEAD` | 首行 `requested_revision=refs/tags/v1.7.1`；`1 个 change 目录`、归档 target、`check：通过 ✓` |
| T8 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`，并显式比对主 spec 该 Requirement 块与 delta 的 MODIFIED 块逐字节一致 | 全部通过；主 spec 该 Requirement = delta 块（5 个 Scenario，4 个现有 + 1 个新增）；`validate` 单独不检查这一项 |
| T9 | `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | exit 0 |
| T10 | `uv run pytest -q` | 全量通过 |
| T11 | PR 的 `gate / check` 日志 | 包 ref = `refs/tags/v1.7.1`，来源 `job.workflow_ref`；check pass |
| T12 | 合入后 master 复核 | caller / 台账为 v1.7.1；完整 `init` 幂等；归档目录存在、backlog 干净 |

## Pre-Implementation Review

**Grill（独立零记忆，2026-10-20）**：8 条 Confirmed Decisions、0 条 Open Question。所有追问均由 witnessloop v1.7.1 源码、本仓 policy/spec 与 git/gh 事实判定，没有需要用户拍板的问题。报告见 `reviews/grill-design.md`。

**Medium+ 设计修正（已全部落回本文件与 `tasks.md`）**：

1. 本地 `check` 时机改为「归档 move + manifest + 证据提交之后」，并增加「目标确实被检到」的断言（避免 0 target 假绿）。
2. 本 change 出生即归档：删除归档前 manifest build，唯一 build 点在归档后、用归档目录名（Decision 7）。
3. 归档点无法完成的任务（PR CI 结论 / merge 动作 / post-merge 复核）移入 `(post-merge)` 段。
4. Decision 2 改写 `--policy` 的失败模式为「半完成 + 响亮失败」，并补 tests 文件非哨兵前置。
5. 本地 CLI 改为 `uvx --from git+…@refs/tags/v1.7.1`，`check` 首行可证明包来源。
6. 幂等验收钉死完整 `init` 命令（带 `--gate-ref` 与 `--policy`），并注明 plain `init` 退 1 是既有预期。

**Low 处置**：T4 allowlist、uv 阈值措辞、回滚目标、`change_archived` 惰性、manifest run id 来源均已写入上面的 Decision / Risks / Testing Strategy；无遗留未处置项。

**设计阶段对抗 r1（独立零记忆，2026-10-20）**：verdict `CHANGES_REQUESTED`，1 条 medium —— spec delta 的 MODIFIED 块漏掉主 spec 现有的 2 个 Scenario（`阶段 C 之后的改动受 require_change_for 约束`、`归档产物的证据形态为 witnessloop 单套`）。OpenSpec 1.4.1 的 MODIFIED 是整块替换，`openspec validate` 不比对 Scenario 集合，本 change 的纯 move 归档也绕开 apply 校验 ⇒ 会静默丢失规范性约束。**已修**：delta 补齐为 5 个 Scenario（4 个现有 + 1 个新增）；升级命令补 `--policy .witnessloop/policy.json`；T8 / tasks 2.2 增加 Scenario 标题集合断言。同时落掉 low：allowlist 补 `spec:73` 与 `development-guide:441`；出生即归档的 diff 形态改为条件句（两种提交次序都能过 `check`，唯一 build 点固定在归档后）；5.3 钉全 `manifest build` 的 `--stage/--report/--base`；5.4 只提交 manifest；5.6 只发起 PR；7.2 复述完整 `init` 命令；proposal 明确回归证据口径。报告见 `reviews/grill-adversarial.md`。

**设计阶段对抗 r2（独立零记忆，2026-10-20）**：verdict `PASS`，medium+ = 0。r2 逐字节核对 delta 与主 spec 的 3 个保留 Scenario（标题 + 全部 AND 行），并在临时副本用 OpenSpec 1.4.1 的 `buildUpdatedSpec` 实跑应用（`modified:1`、`warnings:[]`、应用后恰 5 个 scenario）。r2 的 low/nit 也已顺手收口：回滚命令给完整 gate-ref + `--policy`；tasks 2.2/T8 升级为 Requirement 块逐字节一致；Decision 7 校正为「相对 base 的最终 PR diff 恒为 A」；5.3 钉全 build 时机与 `uvx --from`；allowlist 改为带扫描命令、行号以文件为准。报告见 `reviews/grill-adversarial.md`。

**Open Questions**：0（grill 与对抗 r1/r2 均为 0）。停轮队列为空，可以进入实现。

