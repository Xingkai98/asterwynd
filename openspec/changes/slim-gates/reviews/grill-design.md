# Grill: slim-gates 设计追问

## Reviewer
- run id: grill-slim-gates-20261018-r1
- 时间: 2026-10-18

## Confirmed Decisions
- **决策**: 瘦 checker 保留 `scripts/check_openspec_artifacts.py` 路径与 `0/1/2` exit 语义，删除 `--current-specs-root` / `--skip-protected-paths` / `--check-archived`，只保留 `--changes-root` / `--change` / `--backlog` / `--base-ref` / `--skip-backlog` / `--require-base`；理由: CI 与文档已按该命令书写，旧 flag 的唯一消费者（第二次 `--check-archived` 步骤、旧测试）随本 change 一并删除，保留会暗示仍有受保护路径/投影检查；来源: grill-slim-gates-20261018-r1
- **决策**: 六条规则应按旧实现的函数与边界逐字搬运，而不是重写判据；理由: `design.md:51-58` 的行号锚点与 `528d02f` 实际实现逐一吻合（RIR `:524`、Impact `:451`、benchmark `:903`、tasks `:1027/:1051`、backlog `:1490`、building review `:1192/:1678`），且本 change 自身在旧 checker 下 `--change slim-gates` 与 `assume_implemented=True` 均 0 错误；来源: grill-slim-gates-20261018-r1
- **决策**: 事件投影退役是安全的：`workflow_state.py`、`agent/workflow/*`、`flow-policy.json`、`workflow_methods.json` 的仓内消费者只有旧 checker/guard/测试与文档；产品代码中的 `agent.subagent.*` 是另一套模块；历史 `workflow-events.jsonl` 只作为 witnessloop 匹配与审计数据只读保留；理由: 全仓 `rg` 与 SPIKE 的 `pytest --collect-only` 实测均无产品依赖；来源: grill-slim-gates-20261018-r1
- **决策**: platform gate 应按「脚本 + JSON + 测试 + 规格」四项原样保留，且本 change 只跑 `--verify`；理由: `scripts/platform_gate.py:38-45` 只依赖 stdlib，`tests/test_platform_gate.py` 不引用任何被删模块，witnessloop 不覆盖 branch protection；来源: grill-slim-gates-20261018-r1
- **决策**: Bash guard 只处理 `Bash`，`Write|Edit` 交给 witnessloop plugin guard；hook 用 `exit 2` 阻断，解析器内部异常 fail-open、policy 缺失/损坏用内嵌表继续判定；理由: 与 witnessloop `guardcmd.py:16-18` 自述的「防遗忘不是防对抗」定位一致，避免把本地 checkpoint 写成防对抗保证；来源: grill-slim-gates-20261018-r1
- **决策**: 规格 delta 采用 MODIFIED / ADDED 覆盖两个 capability，并删除 `dev-workflow-state-machine` 规格；理由: 当前 master 上 delta 的 MODIFIED 标题逐字命中现行规格（`npx @fission-ai/openspec@1.4.1 validate --all --strict` 实测 30 passed），且 `tests/test_round_model_alignment.py:29,69,141` 与 `tests/agent/tools/test_guard_three_state.py:516` 的适配点在设计中已列出；来源: grill-slim-gates-20261018-r1
- **决策**: `tests/test_round_model_alignment.py` 保留「非空 medium+ 批次 / 20 个已收口轮 / 建议推倒重开」三处 checker 提示断言，移除状态机规格条目与对应单测；`tests/agent/tools/test_guard_three_state.py` 的示例命令替换不改变测试意图；理由: 前者锁的是现行文档模型而非旧实现（`tests/test_round_model_alignment.py:155-166`），后者只是「解释器参数不是隐藏命令」的示例（`tests/agent/tools/test_guard_three_state.py:516`）；来源: grill-slim-gates-20261018-r1

## Code-Resolved Questions
- v1.7.0 的 `manifest build` 能否在归档目录上重建 manifest？ → 能：v1.7.0 的 `manifestcmd.py:33-67` 有 `resolve_change_dir`，先查 `changes_root/<id>`，再精确查 `archive/<归档目录名>`；因此 `tasks.md:94` 的「归档后重建」可执行（但必须钉 v1.7.0/`00192ab`，见风险）。
- SPIKE 提交在本工作区可用吗？ → 可用且未 push：`git cat-file -t e9d23af` / `d48fd93` 均返回 commit，分支 `retire-old-gates-spike/2026-10-18` 存在；新 clone / 其他机器不可复现。
- `git cherry-pick -n e9d23af` 与当前工作区是否冲突？ → 冲突：backlog 已登记 slim-gates（未提交时 cherry-pick 直接 abort；提交后仍产生 `UU docs/openspec-change-backlog.md`，已在临时 worktree 实测）。
- cherry-pick 之后再把 delta 施加到 current spec 会发生什么？ → `openspec archive slim-gates` 实测中止：`change-documentation MODIFIED failed for header "### Requirement: Mechanical artifact checks" - not found`（SPIKE 把该 Requirement 改名为 `Mechanical artifact checks removed`，并把 `dev-workflow-gate` 重写为 5 个不同标题的 Requirement）。
- 当前 delta 的 MODIFIED 标题与 master 现行规格是否逐字匹配？ → 匹配：`openspec/specs/dev-workflow-gate/spec.md:15,32,89,121,137,194` 与 `openspec/specs/change-documentation/spec.md:30,194,210,258,396,425`；当前 `validate --all --strict` 30 passed。
- 本 change 自身在旧 6 条规则下能过归档点吗？ → RIR 内容门槛（`assume_implemented=True`）、Impact、benchmark smoke、building review 断言当前均返回空错误；唯一会红的是任务结算（`tasks.md:95` 的 6.7）与缺失的 review 证据（待产出）。
- 旧 checker 还有哪些不在「六条」里的检查？ → `check_change`（`scripts/check_openspec_artifacts.py:1372-1447`）还查 `design.md` / `diagnosis.md` 必填章节、Change Type 合法性与 docs 组合、`_check_current_spec_mapping`、`_check_current_spec_sync_task`、`_check_design_review_task`、`handoff.json`；SPIKE 报告 144-153 行也列了这批「现在也没了」的规则。
- 本 change 的本地 Bash guard 现在会生效吗？ → 不会：工作区没有 `.claude/`，`.gitignore:9` 忽略 `.claude/`；building worktree 同样不会自动带 hook。
- 归档目录命名检查的旧触发面是什么？ → `_new_archive_dirs_since_base` 对 **任何** `--diff-filter=AR` 下 `archive/<段>/...` 且段非日期的路径报错（`scripts/check_openspec_artifacts.py:1640-1657`），不只是「新建归档目录」。
- e9d23af 是否改动了未在 Impact Analysis 中登记的 current spec？ → 是：`openspec/specs/multi-agent-collaboration/spec.md:83` 被改为指向 `agent/subagent/workflow_store.py`；proposal 的 Impact Analysis（`proposal.md:113-137`）与 design Decision 9（`design.md:151-158`）均未列出该 capability。
- v1.7.0 的 `check` 是否会为本次删除/修改 `openspec/specs/**` 要求解释事件？ → 会：受保护路径规则来自 `.witnessloop/policy.json`；SPIKE 实测的「全局历史事件覆盖」只是既有偏差，不能当作本 change 的合法依据。
- `witnessloop manifest build` 绑定哪些 artifact？ → `tasks_hash`（`tasks.md`）与 `spec_hash`（`specs/`），加上 `head_sha` 祖先约束（v1.7.0 `constants.py:87-90`、`manifestcmd.py:101-107`、`contract.py:277-291`）；因此 tasks 结算必须发生在 manifest build 之前。

## Open Questions
无

## 风险
- **blocker｜SPIKE 规格改写 + delta 施加顺序会互相破坏**：`design.md:128-138` 让实现先 cherry-pick `e9d23af`，但该提交把 `openspec/specs/dev-workflow-gate/spec.md` 重写成 5 个不同标题的 Requirement，并改 `change-documentation` 两个 Requirement 名；而 delta 的 MODIFIED 目标是按 **pre-SPIKE** master 写的。实测 `openspec archive` 直接中止（`Mechanical artifact checks` not found）。必须明确：cherry-pick 时排除 `openspec/specs/**`（或 cherry-pick 后从 `528d02f` 恢复这两个/三个 current spec），再施加 delta；并且把 backlog conflict 的解法写进任务。影响 `design.md:128-138`、`tasks.md:26-28`、`tasks.md:54-55`。
- **blocker｜`tasks.md:95` 的 6.7 会让本 change 自己的归档点判红**：6.7 是未勾且未标 `(post-merge)` 的任务，而归档门只豁免 `(post-merge)`（`scripts/check_openspec_artifacts.py:114-118,1764-1780`）；归档发生时 PR 尚未创建/合入，6.7 无法诚实勾选。必须拆分（「发起 PR」与「合入」分开）或标 `(post-merge)`。
- **high｜witnessloop 证据产出顺序错误**：`tasks.md:86-95` 先 6.2 build manifest，再 6.4 结算 tasks（改变 `tasks_hash`），并在 6.3 归档前跑 check；而 witnessloop 绑定 `tasks_hash` / `head_sha`，仓库既有纪律是「内容 → tasks 最终化 → 归档 move → 用归档目录名重建 manifest → 最终 check」（`AGENTS.md:115`、`docs/development-guide.md:302-316`）。按现顺序 6.3 验的不是最终 revision，6.2 的 manifest 在 6.4 后即 stale。应改为：事件 → 结算 tasks → build → archive move → 重建 → check → PR。
- **high｜Bash guard 会拦掉所有受管路径的删除/改名，却没有合法写通道**：`design.md:90-103` 把 `rm` / `git rm` / `git restore` / `git checkout --` / `git apply` 都当写操作，但 `Write|Edit` 无法删除或改名文件；本 change 自己就要删除 `scripts/*` 与 `agent/workflow/*`。当前唯一能执行删除的路径是未被识别的 `git cherry-pick`（`tasks.md:54`），而它既不在写操作表、也不在 `design.md:99-100` 的残余绕过清单里。必须二选一并写进设计/测试：允许 `git rm`/`git mv` 等 VCS 簿记操作（删除不产生内容写入），或如实登记 cherry-pick/merge/rebase/stash/am 为已知绕过并说明删除面不受本地保护。「所有 Bash 写入受管路径都拦」（`design.md:88-89`）按现状不成立。
- **high｜Bash guard 的误伤面没有测试计划**：T4（`design.md:200`）与 `tasks.md:39-41` 只测简单只读命令。至少缺：读命令参数里出现写样式文本（`rg 'echo > agent/y'`、`git commit -m "cp x agent/y"`）、`cp agent/x /tmp/y`（源在受管路径、目的在仓外，按「目的参数」语义应放行）、`sed -i 's|agent/|x|' docs/y`（写目标是 docs/y）、`2>&1` / `>/dev/null`、here-doc 作为数据（`cat <<EOF`）、`git apply --check`、`git restore --staged`、`rsync` 源/目的。没有这些，guard 会要么误伤日常开发，要么在修复误伤时被改松。
- **high｜本 change 自身的受保护路径事件不齐**：`tasks.md:86-87` 只列事件类型，未列逐路径覆盖；它缺 `protected_artifact_explained`（SPIKE 会改 `docs/known-debt.md`），也未逐一覆盖 `openspec/specs/dev-workflow-state-machine/spec.md`（删除）、`dev-workflow-gate` / `change-documentation`（修改）、`platform-gate`（恢复新增），以及（若补 delta 的）`multi-agent-collaboration`。witnessloop 对这些路径要求 `current_spec_synced` / `protected_artifact_explained` 覆盖；不能依赖 SPIKE 记录的「全局历史事件掩盖」偏差。
- **high｜`multi-agent-collaboration` 的 current spec 改动未登记、无 delta**：`e9d23af` 修改 `openspec/specs/multi-agent-collaboration/spec.md:83`；`proposal.md:113-137` 的 Impact Analysis 与 `design.md:151-158` 均未包含该能力域。删除 `agent/workflow/` 后该 Requirement 必须改指 `agent/subagent/workflow_store.py`，因此应补一条 MODIFIED delta 并登记影响面（或明确排除该 hunk，但那样 spec 会指向已删模块）。
- **high｜`dev-workflow-gate` 的 Purpose 会残留错误事实**：现行 `openspec/specs/dev-workflow-gate/spec.md:7` 说旧 checker/guard/状态机「全部继续照跑」；delta 只覆盖 Requirement，不改 Purpose。若再叠加 SPIKE 版本的 Purpose（「项目特有文档规则不再有机械实现」），两种写法都与最终现实相反。`tasks.md:26-28` 的「同步 current spec」必须显式改写 Purpose。
- **medium-high｜「只丢 6 条规则」的说法不完整**：`proposal.md:25-26` 只承认 6 条损失，但旧 `check_change` 还查必填章节、Change Type 合法性、current spec 映射/同步任务、grill 任务（`scripts/check_openspec_artifacts.py:1372-1447`）。其中只有部分被 witnessloop 覆盖。建议在 design 增加「被丢弃的旧检查 + 处置（witnessloop 覆盖 / 有意退役）」表，并明确 Change Type 解析失败时的退出码与规则适用行为（不留给实现猜测）。
- **medium-high｜旧 checker 测试的搬迁覆盖不足**：删除 2966 行 `tests/test_openspec_artifact_checker.py`，但 `tasks.md:31-38` 只枚举了一部分边界。建议补一张「旧用例 → 新用例」映射，至少覆盖 `_extract_record_field` 续行、`未定` 中途不报警、docs / 无 spec delta 豁免、`--require-base` 不可解析、有序列表前缀的出口 token、非规范归档命名。
- **medium｜归档命名判据被轻微收窄**：旧实现会对任何本次 diff 触及的非日期归档目录报错（`scripts/check_openspec_artifacts.py:1640-1657`），delta 写成「新建的归档目录」（`specs/dev-workflow-gate/spec.md:124`）。应把谓词写成与旧实现一致，或明确记录这是有意收窄并补对应用例。
- **medium｜AGENTS.md 与 policy 对 archive 的受保护口径矛盾**：`AGENTS.md:24,114` 仍把 `openspec/changes/archive/**` 列为需解释事件，而 `.witnessloop/policy.json` 与 delta（`specs/dev-workflow-gate/spec.md:42-43`）明确不包含 archive；`AGENTS.md:196-205` 仍把 `workflow-state.json` / `workflow-events.jsonl` 写成 `flow status` 写通道。`tasks.md:58-61` 需要把这些语义一起改掉，而不只是删旧脚本名。
- **medium｜building worktree 内本地 guard 不生效**：`.gitignore:9` 忽略 `.claude/`，本工作区无 `.claude/`；building 又必须在独立 worktree 进行。应在安装文档中写清「user-level settings + 绝对路径」或「每个 worktree 手动安装」，否则本 change 声称的本地 Bash 保护在它自己的实现阶段是空的。
- **medium｜policy schema 与 glob 语义未钉死**：`flow-policy.json` 的 `match_type` 规则表已删除，新 guard 读的是 `.witnessloop/policy.json` 的 glob 列表（`agent/**`、`openspec/specs/**` 等）。设计未写匹配算法，也无「内嵌默认表 == policy」的 parity 测试；建议补 `**` 嵌套、`.witnessloop/**`、`scriptsfoo/` 不应命中等用例。
- **low-medium｜SPIKE 提交不可复现**：`e9d23af` / `d48fd93` 仅本地存在且未 push；`design.md:130` 的 cherry-pick 步骤在干净 clone 上不可执行。至少要把删除文件清单/对照方式写进 tasks，或把 SPIKE 分支推上远端。
- **low｜事实数字与注释陈旧**：proposal 说删 7028 行测试，但其中 `test_platform_gate.py` 502 行会恢复；`.github/workflows/ci.yml:19-21` 的 `fetch-depth: 0` 注释仍说 protected-path checks；Decision 6 把 4 个产物称作「三件套」。

## User Confirmation
- 本 change 的 Open Question 数为 0（无用户拍板项；上述均为可由代码/仓库事实判定并回写设计的必须修改项）
