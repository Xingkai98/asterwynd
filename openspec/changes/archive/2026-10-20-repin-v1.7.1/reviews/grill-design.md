# Grill: repin-v1.7.1 设计追问

## Reviewer

- run id: `grill-repin-v1.7.1-2026-10-20`
- 时间: 2026-10-20
- 零记忆: 是（未参与 proposal / design 编写；只依据本仓文档、git/gh 事实与 witnessloop v1.7.1 源码逐项核验）

## Confirmed Decisions

- **决策**：caller 回钉到 annotated tag `@v1.7.1`，不继续钉 hotfix commit，也不用滚动 tag 或分支名。 理由：v1.7.1 的 `gate.yml` 已按 ref 形态解析包 ref，tag 走 `job.workflow_ref` 的 `refs/tags/<tag>`；当前规格要求「具体发版 ref」；commit pin 只是故障期应急形态。 来源: `gh api repos/Xingkai98/witnessloop/git/refs/tags/v1.7.1` 返回 `{"type":"tag","sha":"c4f681a7e899b5958dd51e8823b7a6dc9260c187"}`，其 tag object 指向 commit `07bf23b38dfe19c1e0b9590732e6c5699f3b5e79`（同一 API 的 tags 端点）；`/tmp/wl171/.github/workflows/gate.yml:114-118`；`openspec/specs/dev-workflow-gate/spec.md:225`。
- **决策**：用 `witnessloop init --gate-ref "<...@v1.7.1>" --policy .witnessloop/policy.json` 原子重写 caller 并同步台账，不手改 `.witnessloop/init-manifest.json`。 理由：`sync_caller_gate_ref` 在同一个函数里重写 caller、更新 `gate_ref` 与 caller 条目 `sha256`；只改一边会让后续 plain `init` 走漂移分支、`uninit` 半回滚。 来源: `/tmp/wl171/src/witnessloop/initcmd.py:149-215`、`301-326`；当前盘上 caller `sha256=7d028a644f907e34fbf64ceb74229572eedbeb4608d551c38b9e67cf7ea2fe70` 而台账记为 `cd4e45b8ef7e180adc9a445f851ab9a4d8782fbe2615d824525054378540e059`（`sha256sum .github/workflows/witnessloop.yml`；`.witnessloop/init-manifest.json:8-22`），确实处于台账漂移态。
- **决策**：必须使用 v1.7.1 的 CLI；本机 PATH 上的 witnessloop 0.1.0 不能用于 `init` / `check` / `manifest build`。 理由：0.1.0 的 `init` 不接受 `--policy`、也没有「显式 `--gate-ref` 重写已接入仓」的语义；`__version__` 恒为 0.1.0，不能用 `--version` 判版本。 来源: `/tmp/wl171/src/witnessloop/__init__.py:22`（`__version__ = "0.1.0"`）；`/tmp/wl171/src/witnessloop/cli.py:36-70`（v1.7.1 的 init 参数含 `--policy` / `--gate-ref`）；`/tmp/wl171/docs/gate.md` §1.2 的「升级动作」。
- **决策**：本 change 的受保护写入解释事件写在本 change 的 `workflow-events.jsonl`，`artifact_path` 逐字精确、不带通配。 理由：`.witnessloop/**` 与 `openspec/specs/**` 都是 policy 的受保护路径，`events.covers` 只认精确路径且拒绝 `*` / `?`。 来源: `.witnessloop/policy.json` 的 `protected_paths` 与 `protected_write_event_types`；`/tmp/wl171/src/witnessloop/events.py:106-121`；现有事件文件 seq=3 已按精确路径覆盖 `.witnessloop/init-manifest.json`（`openspec/changes/repin-v1.7.1/workflow-events.jsonl:3`）。
- **决策**：规格只改「阶段 C 翻开关后的 required 形态」及 Purpose 中的当前版本事实，不重写 required 集合 / 降级不关闭等边界。 理由：required 集合与平台行为属 platform-gate 能力域；同一条规范两处写会漂移。 来源: `openspec/specs/dev-workflow-gate/spec.md:7`、`:225-240`（当前 `@v1.7.0` 与 `job.workflow_sha` 推导句）；change delta `openspec/changes/repin-v1.7.1/specs/dev-workflow-gate/spec.md:7`、`:21`、`:24`。
- **决策**：本 change 属于「出生即归档」（base 树里没有该 change 目录），最终 manifest 必须在归档 move 之后用归档目录名重建。 理由：base...head diff 里没有 rename 记录，归档 target 的 `accepted_change_ids` 只含归档目录名；归档前用源 id 产出的 manifest 会被判「与目录不符」。 来源: `git status --short` 输出 `?? openspec/changes/repin-v1.7.1/`；`git ls-tree -d --name-only origin/master openspec/changes/` 无 repin 目录；`/tmp/wl171/docs/gate.md:503-517`；`/tmp/wl171/src/witnessloop/contract.py:495-508`、`:702-715`。
- **决策**：PR 用 merge commit 合入，禁止 squash。 理由：review manifest 的 `head_sha` 必须是被检 head 的祖先；squash 会把被绑定的 revision 从 master 历史中抹掉。 来源: `/tmp/wl171/src/witnessloop/contract.py:783-815`（`_check_git_span` 的祖先判定）；`docs/development-guide.md` 的 Review evidence 纪律；仓库近期合入形态为 merge commit（`git log --oneline -3`）。
- **决策**：proposal / design 引用的外部事实成立：v1.7.1 是 annotated tag；上游 issue #42 已关闭；hotfix PR #327 已合入（merge `6808fcd9f40384148fa3eebee0ad568bfc5cfecc`）。 理由：这些是本次回钉的前提事实，已由外部系统核对而非凭记忆。 来源: `gh api repos/Xingkai98/witnessloop/git/tags/c4f681a7e899b5958dd51e8823b7a6dc9260c187` 返回 `{"tag":"v1.7.1","object_type":"commit","object_sha":"07bf23b3..."}`；`gh issue view 42 --repo Xingkai98/witnessloop` 返回 `CLOSED`（closedAt `2026-10-20T10:09:41Z`）；`gh pr view 327 --repo Xingkai98/asterwynd` 返回 `MERGED`。

## 需要修改的设计点

1. **[medium] 本地 `check` 的验收时机不可满足，且「通过」本身不足以证明检查发生过。** `design.md:63` 与 `tasks.md:37` 要求「内容提交后」跑 `check` 必须通过，但 `check` 对每个被触达的 change 都要求 `reviews/`（`/tmp/wl171/src/witnessloop/contract.py:533-535`）、至少一份 review manifest（同文件 `:573-581`）以及 `stage=grill` 的 manifest 及其报告正文（`/tmp/wl171/src/witnessloop/evidence.py:353-371`）。在 3.4 那个时点，本 change 还没有任何 manifest，`check` 必然报「缺少 review manifest / 无 stage=grill 的 manifest」。反向陷阱同样存在：`changed_files` 走 `git diff base...head`（`/tmp/wl171/src/witnessloop/gitutil.py:99-111`），未提交 / 未跟踪的 change 目录不会进 diff，targets 为 0，`check` 会直接打印「check：通过 ✓」（`/tmp/wl171/src/witnessloop/checkcmd.py:208-213`）——那是假绿。**改法**：把本地 `check` 移到 6.4 归档 move、6.5 manifest 重建并提交证据之后；验收断言改为同时匹配 `1 个 change 目录`、`change：2026-10-20-repin-v1.7.1（归档）` 与 `check：通过 ✓`，不能只看 exit 0；运行前先 `git fetch origin master`。同步修改 `design.md:63`、`design.md:96`、`tasks.md:37`。

2. **[medium] 「出生即归档」与 5.1 的归档前 manifest build 冲突。** `tasks.md:47` 要求在所有内容提交之后、归档 move 之前产三份 manifest；但本 change 的目录在 base 树里不存在（`git status --short` → `?? openspec/changes/repin-v1.7.1/`），PR diff 里全为 `A`、没有 rename，归档 target 的名字接受集合只有归档目录名（`/tmp/wl171/src/witnessloop/contract.py:495-508`、`:702-715`）。因此归档前产出的 `change_id=repin-v1.7.1` 会被逐份判「与目录不符」。上游文档写明出生即归档必须在归档之后用归档目录名重建（`/tmp/wl171/docs/gate.md:503-517`），`manifest build` 也按名字精确解析归档目录（`/tmp/wl171/src/witnessloop/manifestcmd.py:33-48`）。**改法**：删除或改写 5.1 为「内容与归档提交完成后，在 6.4 之后统一用 `--change 2026-10-20-repin-v1.7.1` 产三份 manifest」，让 6.5 成为唯一 build 点，并在 `design.md` 明写本 change 是出生即归档。

3. **[medium] 5.2 / 5.3 / 6.6 在归档时刻结构上无法完成，却没有 `(post-merge)` 标记，归档点完成度会红。** `tasks.md:48-49` 的「PR 的 gate / check 判绿」「记录三个降级 job 结论」要等 PR 存在并有 CI run 才能发生；`tasks.md:58` 的「本 PR 用 `--merge` 合入」更是只能在合入后成立。瘦 checker 对归档目录里任何未勾且未标 `(post-merge)` 的任务直接报错（`scripts/check_openspec_artifacts.py:1137-1145`，标记正则见 `:111-114`）。**改法**：把 5.2 / 5.3 / 6.6 移入第 7 节并标 `(post-merge)`（6.6 可改为「合入方式：merge commit，禁止 squash」的 post-merge 复核项），保留 6.4 / 6.5 在归档前完成。

4. **[medium] Decision 2 写错了不带 `--policy` 的失败模式，并缺少 tests 执行点前置检查。** `design.md:25` 说否则工具会「静默丢掉」受管面；实际行为是：带 `--gate-ref` 时先重写 caller 与台账（不回滚），随后因出厂 policy 与盘上定制 policy 冲突而 exit 1（`/tmp/wl171/src/witnessloop/initcmd.py:414-441`、`:594-626`；`/tmp/wl171/docs/gate.md:142-165` 明确记录定制 policy 仓的 plain init 退 1）。这是「半完成 + 响亮失败」，不是静默丢配置，恢复动作也不同。另外，`init` 在 `.github/witnessloop-tests.txt` 不存在时会种下哨兵 `<<REPLACE-ME>>`（`/tmp/wl171/src/witnessloop/initcmd.py:380-383`；`/tmp/wl171/src/witnessloop/constants.py:44-49`），而哨兵会让 `check` 判红（`/tmp/wl171/src/witnessloop/checkcmd.py:255-262`）。**改法**：按实际失败模式重写理由；在 T1/T2 增加前置条件「`.github/witnessloop-tests.txt` 存在且内容非哨兵」（本仓现为 `uv run --extra dev pytest -q`），并把「policy 逐字节不变」的依据写实（已核验：policy 经 `json.dumps(indent=2, sort_keys=False)` 往返完全一致）。

5. **[medium] Decision 3 指定的本地源码运行方式，反而让「靠 check 包来源行判版本」失效。** `design.md:31-33` 选择 `uv run --project <源码目录>`；本地源码 / editable 安装没有 PEP 610 `vcs_info`，`check` 会打印 `requested_revision=<未知>`（`/tmp/wl171/src/witnessloop/checkcmd.py:55-91`），无法验证跑的是不是 tag 对应的那份代码。同时 `<witnessloop-v1.7.1-源码目录>` 在仓外、不可复现。**改法**：改用与 CI 同源的安装命令 `uvx --from git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1 witnessloop ...`（`/tmp/wl171/.github/workflows/gate.yml:195-197`），并让 T5 断言 `check` 第一行为 `requested_revision=refs/tags/v1.7.1`；`docs/development-guide.md:389-395` 的本地锚点也改为这条可复现命令，而不是某个本机路径。

6. **[medium] T3 / T10 / 7.2 的「init 幂等」没有钉死命令，在本仓会误判。** 本仓是定制 policy 仓，**plain** `init`（不带 `--policy`）会因出厂 policy ≠ 盘上 policy 而 exit 1（`/tmp/wl171/src/witnessloop/initcmd.py:594-626`；`/tmp/wl171/docs/gate.md:152-155` 明写「定制 policy 的仓即使升级成功，plain init 也照旧退 1」）。`design.md:62/94/101` 与 `tasks.md:63` 只写「再跑一次 init」「init 幂等」，会给执行者留下一个必然失败或误判的检查。**改法**：所有幂等验收都写全命令 `witnessloop init --root . --gate-ref "Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1" --policy .witnessloop/policy.json`，期望 `init：已接入 witnessloop（幂等，无改动）。` 且 exit 0；并注明 plain `init` 退 1 是本仓的既有预期，不是回钉失败。

7. **[low] T4 / T10 的 grep 验收缺历史命中 allowlist。** `design.md:95` 期望当前态不再出现 `@v1.7.0` 现状句，但只读扫描会命中历史证据：`docs/adr/ADR-0006-retire-minimal-tui-runtime-view-proposal.md:30`、`:68`，`openspec/specs/dev-workflow-gate/spec.md:191`、`:195`（「v1.7.0 实测」），`docs/development-guide.md:385`（「v1.7.0 实测，2026-10-17 补记」）。**改法**：在 tasks 2.5 列出允许保留的历史命中清单，只对当前态文件（caller、台账、spec Purpose、spec 225/238/239、development-guide 381/389-395、Q12:28）做零命中断言，避免执行者为了「grep 干净」误改 ADR 或历史实测记录。

8. **[low] uv 阈值口径在仓内与上游不一致。** `proposal.md:16` 与 delta `specs/dev-workflow-gate/spec.md:7` 写「uv ≥0.13.2 拒绝」，上游 issue #42 的标题与正文写的是 0.13.1 绿、0.13.3 红，`/tmp/wl171/.github/workflows/gate.yml:42` 注释写 0.13.2。**改法**：规格里避免钉精确 minor 版本，或明确引用 gate.yml 注释为来源；不要在 normative 句里留下一个无出处的版本号。

9. **[low] 回滚目标没有写死。** `proposal.md:51` 写「`init --gate-ref <旧 ref>`」，但回滚到 `@v1.7.0` 会在 uv ≥0.13.3 下重新触发 issue #42 的硬红。**改法**：把回滚目标写成 hotfix 的 commit pin `c9b281167ad20b63e4832ad9ab8510964a2adc60`，并提示 `init` 在 caller/台账轴上先写不回滚，回滚时要一并补新的解释事件。

10. **[low] `change_archived` 事件对 witnessloop 是惰性的，不要当作门禁依赖。** `design.md:44` 要求写 `change_archived`，但 `covers` 只按精确文件路径匹配，目录路径不会豁免任何受保护文件（`/tmp/wl171/src/witnessloop/events.py:106-121`；`/tmp/wl171/src/witnessloop/checkcmd.py:346-410` 的归档 move 本身已豁免）。**改法**：保留它作为簿记可以，但不要把它列成「必需事件」；真正必需的是 init-manifest、主 spec、backlog 三条精确路径事件。

11. **[low] manifest build 未指定 reviewer / author run id 的来源。** `tasks.md:47` 只写产三份 manifest。若环境里设置了共享的 `WITNESSLOOP_RUN_ID`，两个角色会拿到同一个值，`manifest build` 直接拒绝写出（`/tmp/wl171/src/witnessloop/manifestcmd.py:167-179`；`/tmp/wl171/src/witnessloop/agentenv.py:66-78`）。**改法**：在 5.1 明确「不设共享 `WITNESSLOOP_RUN_ID`，或显式传不同的 `--reviewer-run-id` / `--author-run-id`」。

## Open Questions

本 change 的 Open Question 数为 0。

理由：上述 11 条均可由 witnessloop v1.7.1 源码、本仓 policy/spec、git 与 gh 事实直接判定或给出唯一推荐改法（次序修正、命令钉死、事件路径、验收断言），不涉及需要在多个合理产品/流程价值之间取舍的问题；不需要停轮等待用户拍板。

## User Confirmation

本 change 无 Open Question，故无逐条用户确认记录。该小节的存在性本身是 witnessloop 的机械要求：`## User Confirmation` 必须无条件存在，与是否有 Open Question 无关（`/tmp/wl171/src/witnessloop/evidence.py:295-297`）。

## 风险

1. **v1.7.1 仍无法从 tag ref 安装时，本 PR 无法合入（不是「先合后修」）。** `master` 的唯一 required 是 `gate / check` 且 `enforce_admins` 开启（`AGENTS.md` 的 platform-gate 小节），IPR 的 CI 会用 PR 自己的 caller 跑新 ref；一旦 v1.7.1 安装失败，这个 PR 自身就会红。证据：`/tmp/wl171/.github/workflows/gate.yml:195-197`、`AGENTS.md` 的「platform-gate 平台闸门」。建议：不要在本 PR 夹带其它改动；失败时按 design 的风险处置保留 master 的 commit pin，并关闭本 PR 重新立项。
2. **证据次序是硬约束，任何晚到的非证据提交都会让 manifest 变 stale。** `_check_git_span` 只允许 `head_sha` 之后出现证据路径（`.witnessloop/**`、`change/reviews/**`、`change/workflow-events.jsonl`、`archive/**`），其余文件一律报「审阅的是旧 revision」（`/tmp/wl171/src/witnessloop/contract.py:783-815`；`/tmp/wl171/src/witnessloop/policy.py:76-92`）。建议：固定提交顺序为「内容（含 spec/backlog 结算）→ 归档 move → 结算 tasks → 6.5 产三份 manifest → 证据提交 → check → PR」；之后任何内容改动都重跑 6.5。
3. **`origin/master` 在 worktree 里可能过期或被污染，导致本地 check 的 base 不对。** 本地已知问题（worktree 的 origin 可能被污染）。建议：check 前 `git fetch origin master`，并用 `git rev-parse origin/master` 记录 base sha 写进审阅证据。
4. **本 change 的 events 文件是本次新增，归档后相对 base 仍是 `A`，因此追加事件不会被要求自解释；但一旦有人把它先提交到主干再改，就会变成 `M` 并需要一条覆盖它自身的精确路径事件。** 证据：`checkcmd.py:389-399`（invariant 的 `A` 免事件、`M/D` 要事件）。建议：保持「本 PR 内一次落齐事件」；若后续追加，按 `_move_half_hint` 的规则补自覆盖事件。
5. **`init` 的 policy 字节不变目前依赖现有 policy 的 JSON 排版恰好等于 `policy.dumps` 的规范形态。** 已实测：`.witnessloop/policy.json` 713 字节经 `json.dumps(indent=2, sort_keys=False)` 往返完全一致；但未来若有人重排 policy，`init --policy` 会走冲突分支（`initcmd.py:594-626`）。建议：T2 记录往返一致性检查，而不是只信一次人工 diff。
6. **文档同步面容易漏掉「本地 CLI 锚点」而不是 `@v1.7.0` 字样。** `docs/development-guide.md:389-395` 当前指向 `/home/happy/wl170/bin/witnessloop`，这是比 `uses:` 更隐蔽的过期点；若只改版本字符串、不改锚点，后续本地 check 会继续用 v1.7.0 跑出假结论。建议：tasks 2.3 明确替换为可复现的 v1.7.1 安装命令，并在 T4 把该路径列入零命中检查。
