# Building Review: fix-issue-235-completion-gate (Round 3)

## Reviewer

- run id: `d4524b50-50b8-4c85-b606-cea8ca2bb854`（独立零记忆 subagent，未继承开发上下文；结论仅来自实读代码 / 实跑输出 / change 文档）
- 时间: 2026-09-23
- base: `4424f54882179ef1ec53d2eaa1a7d373280b91fb`（origin/master，merge-base） head: `bdfd9fade48d191bb9833e7a999d66e17b18e3ce`
- 本轮针对: R2（run `7c72c707`）的 3 个 issue（M1′ landmine / M2 零勾选 / low docs 对称性）
- 审阅方法（全部实跑，作者自述一律不作依据）：
  - **6 个真实 clone**（`git clone`，非 `cp -a`）：`/tmp/r3-clone`（M1′ 四态）、`/tmp/r3-b`（归档态 checker）、`/tmp/r3-c`（AR 判别性）、`/tmp/r3-d`（M1′ 变异）、`/tmp/r3-e`（最终归档模拟）、`/tmp/r3-h`（可满足性端到端）
  - M1′ 四态实跑：active 态 / `git mv` 归档后 / 模拟未来无关 PR 触碰 `docs/known-debt.md` / change 整个移出树；另加 `git remote remove origin` 下的两态（change 在 / 不在）
  - 93 个历史归档的 tasks.md 证据形态全量扫描（零勾选、缺 tasks.md、无 checkbox 行、post-merge 语义计数）
  - 变异 4 条（M2 下限回退 / docs 豁免回退 / AR→A / **M1′ landmine 重引入**），`cp` 备份 + `diff -q` 核对还原，`git status` 干净
  - 实跑 `pytest tests/test_openspec_artifact_checker.py`（121 passed）、`tests/agent/workflow/ + test_workflow_guard.py + test_flow_policy.py`（165 passed）、全量 `uv run pytest -q`（4 failed，全为已知环境失败）、OpenSpec strict validate（30/30）、checker 三种模式
  - 逐条核对 `tasks.md` 的 `[x]`（含 R1/R2 两节）与实现位置

## Verdict

**PASS**

R2 的三条 issue **全部确已修复**，且修复本身**没有引入新的 landmine、误红或 fail-open**——这一点是我本轮最重点验的：R1→R2 之间发生过「修复即新缺陷」，所以我对每条修复都做了「最小回退后判别性归零」的变异验证（4/4 转红），并专门复现了 R2 亲手抓到的那个 `FileNotFoundError` 形态以确认新测试仍有真实判别力、不是空过。全部实跑证据见下。

发现的 3 条 low + 1 条 info 均不阻塞（文档措辞、测试 helper 的边界、以及一条 R2 报告自身的口径误差）。核心功能（issue #235 的两条绕开路径）与 R1/R2 已确认的结论均未被破坏。

## R2 Issues 复核

### **M1′（medium，landmine）— 已修复**

`tests/test_openspec_artifact_checker.py:2661`（`_change_dir_in_any_form`）+ `:2682`（测试体）。触发条件已从 `origin/master...HEAD` 的 diff 改为「本树存在本 change 的事件日志」，路径解析改为 active→archive 双形态 + 存在性保护。**六态实跑**（真实 clone）：

| 状态 | 命令 | 结果 |
|---|---|---|
| active 形态 | `/tmp/r3-clone`（HEAD） | `1 passed` |
| **`git mv` 归档后** | `git mv … archive/2026-09-23-fix-issue-235-completion-gate` + commit | **`1 passed`** ✅（这正是 R2 在旧 HEAD 上抓到 `FileNotFoundError` 的那一态） |
| 模拟未来无关 PR 触碰 `docs/known-debt.md` | 归档态上 `echo >> docs/known-debt.md` + commit | `1 passed` ✅ |
| change 整个移出树 | `mv <archive-dir> /tmp/…` + commit | `1 skipped`（`本 change 不在本树（active/archive 均无）`）✅ 非 error |
| `origin/master` 不可解析 ∧ change 在树 | `git remote remove origin` | `1 passed` ✅ 不报错 |
| `origin/master` 不可解析 ∧ change 不在树 | 同上 | `1 skipped` ✅ 不报错 |

**判别力未退化为空过**（这是「拆 landmine」最容易踩的坑）：变异 4 把 `_change_dir_in_any_form` 退回硬编码 active 路径 `return repo_root/"openspec"/"changes"/change_id`，在归档态下实跑 → `FileNotFoundError: /tmp/r3-d/openspec/changes/fix-issue-235-completion-gate/workflow-events.jsonl`，`1 failed`。即新测试在归档态**仍然真的在断言**，不是靠 skip 蒙混。

边界（low，见 Issues L1）：glob `*-<change_id>` 是**后缀匹配**，实跑确认 `2026-01-01-x-fix-issue-235-completion-gate` 这样的诱饵目录会被选中（`sorted()` 下 `2026-01-01` 排在真目录前）。

### **M2（medium，fail-open 边界）— 已修复**

`scripts/check_openspec_artifacts.py:1063`（`_tasks_missing_evidence`）下限已提到「≥1 条被勾选」（`return not any(match.group(1).lower() == "x" …)`），与 `_tasks_all_complete` 的 `checked > 0` 对齐。实跑三态：

- 零勾选（全 `(post-merge)`）→ **报错**：`tasks.md 缺失或无任何 checkbox 行 —— 归档点无法评估完成度 …` ✅
- 一条 `- [x]` + 一条 `- [ ] (post-merge)` → `[]`（**不误红**）✅
- 变异 1（下限回退为 `return False`）→ `test_archived_gate_flags_all_post_merge_zero_checked` **1 failed** ✅

**作者称「历史归档真实存在 8/93」——实跑复核完全吻合**，且清单逐条对上：

```
2026-07-08-multi-agent-dev-workflow          2026-07-12-add-context-builder-architecture
2026-07-09-add-persistent-cross-session-memory 2026-07-12-add-context-compression-strategies
2026-07-09-add-semantic-code-search          2026-07-12-implement-context-injection-pipeline
2026-07-09-improve-agent-execution-foundation 2026-07-12-improve-system-prompt-architecture
```

（全量扫描：93 个归档中「有 checkbox 行但零勾选」恰为 8 个；「无 tasks.md」0 个；「有 tasks.md 但无 checkbox 行」0 个。）

### **low（对称性）— 已修复**

归档门对 docs 也要求 `tasks.md` 证据（`scripts/check_openspec_artifacts.py:1617`，统一口径不再按 `primary != "docs"` 分流）。实跑四态：

- docs-only 归档**缺** tasks.md → **报错** ✅
- docs-only 归档**有** tasks.md（一条勾选 + 一条 `(post-merge)`）→ `[]` ✅
- 变异 2（把文档豁免加回 `change_type.primary != "docs" and _tasks_missing_evidence(...)`）→ `test_archived_gate_docs_only_missing_tasks_md_is_flagged` **1 failed** ✅
- **语料 0 假阳性**：93 个归档中 `primary == "docs"` 的只有 2 个（`2026-08-03-interview-script`、`2026-09-22-fix-issue-229-231-debt-wording`），**两个都有 tasks.md** ⇒ 统一口径零假阳性。作者「0/93」的分母写法偏松（93 是全部归档数、非 docs 数），实质结论成立。

## Tasks Verification

### R1 修复小节（`tasks.md:65-85`）——4 条 `[x]` 真实落地

- [x] `tasks.md:69` **M1**：`_tasks_missing_evidence`（`scripts/check_openspec_artifacts.py:1063`）+ 归档门接线（`:1617`）；测试 `:2509` / `:2528` 存在且判别（变异 1 波及）。
- [x] `tasks.md:74` **low-1**：`ARCHIVE_DIR_SEGMENT_RE`（`:108`）+ 收敛守卫（`:1512`）；测试 `:2607` / `:2629` 存在。
- [x] `tasks.md:79` **low-3**：本 change 自己的事件存在——实读 `workflow-events.jsonl` 第 2 条 = `seq 2 / protected_artifact_explained / artifact_path=docs/known-debt.md / change_id=fix-issue-235-completion-gate`，含 `reason` + `approved_by` ✅；测试 `:2682`。
- [x] `tasks.md:84` **info**：`docs/development-guide.md:269` / `:271` 两段存在 ✅（**但 `:269` 的 ✓ 例写错，见 L2**）。

### R2 修复小节（`tasks.md:92-108`）——3 条 `[x]` 真实落地

- [x] `tasks.md:96` **M1′**：`_change_dir_in_any_form`（`tests/test_openspec_artifact_checker.py:2661`）+ 测试重写（`:2682`）✅ 六态实跑通过。
- [x] `tasks.md:99` **M2**：`_tasks_missing_evidence` 下限（`scripts/check_openspec_artifacts.py:1063`）；正向测试 `:2566` + 反向测试 `:2588`（防误红）✅。
- [x] `tasks.md:104` **low（对称性）**：归档门 docs 口径统一（`scripts/check_openspec_artifacts.py:1617`）；测试 `:2605` ✅。
- [ ] `tasks.md:107` **low（记录待办）**：`archive/unknown-1.0/file.md` 类非 change 目录仍评命名——作者有意接受的严格化，语料 0 命中，**不阻塞**（符合本轮审阅说明）。

### 前序实现/测试/文档任务（`tasks.md:17-58`，仍未勾，属收尾前正常）

逐条抽查**实现均存在**，无「`[x]` 无实现」：

- 归档点求值在 `--skip-protected-paths` 块**之外**且用 `not args.check_archived and not args.change` 显式守卫 — `scripts/check_openspec_artifacts.py:1735-1748` ✅
- `_new_archive_dirs_since_base`（`:1477`）：`--diff-filter=AR`（`:1504`）+ 「base 树不存在」判定（`_archive_dir_names_in_base` `:1540`）✅
- 非规范归档目录进 `errors`（`:1653-1657`）；`--require-base` 语义（`:1648-1652`）✅
- 四道门复用现有判定函数；A′ 参数 `assume_implemented` 在 `:529` / `:739`，三处判据 `:612` / `:763` / `:782` ✅
- **`check_change` 一行未动**：`git diff origin/master...HEAD -- scripts/check_openspec_artifacts.py | grep "def check_change"` 无命中 ✅
- 新增测试全部存在于 `tests/test_openspec_artifact_checker.py`（121 passed）✅
- `AGENTS.md` 触发点改挂归档点 + `(post-merge)` 段；`docs/development-guide.md` 新节；`docs/known-debt.md` 残余面；spec delta（`## MODIFIED Requirements` 103 行）✅

## Issues

- **low** `docs/development-guide.md:269` — **文档的 ✓ 例子是错的**。该行写「行尾追加的写法**不**被识别，例如 `- [ ] 收尾：关 issue。(post-merge)` ✗、`- [ ] 5.5 收尾 (post-merge)` ✓」，但实跑 `POST_MERGE_TAG_RE` 对这两个串**都是 FLAGGED**（`(?:\d+(?:\.\d+)*)?` 之后必须紧跟 `[（(]`，故 `5.5 收尾` 里的「收尾」把它顶掉）。读者会把 ✓ 理解成「这种写法可以」，照着写就会在归档点吃一条红。方向是 fail-closed（报错不静默），但这段文字的全部目的就是防这条红，写着 ✓ 反把坑指反了。**期望**：把 ✓ 例改成真正被豁免的形态 `- [ ] 5.5 (post-merge) 收尾`（编号在前、tag 紧邻复选框），或删掉 ✓ 以免误导。
- **low** `scripts/check_openspec_artifacts.py:1622` — **零勾选形态的错误文案误导**。`_tasks_missing_evidence` 现在覆盖「有 checkbox 行但零勾选」，但复用同一句 `tasks.md 缺失或无任何 checkbox 行`。实跑一个 tasks.md 内容为 `- [ ] (post-merge) 关 issue。` 的归档，报的是「**缺失或无任何 checkbox 行**」——文件在、checkbox 行也在，唯事实是「一个都没勾」。按文案排查会往「文件是不是丢了」的方向走，而真因是「把所有任务都标成 closeout」。**期望**：文案拆成两支（缺失/无行 vs 有行但零勾选），或改为「tasks.md 缺失、无 checkbox 行、或零勾选」。
- **low** `tests/test_openspec_artifact_checker.py:2676` — `_change_dir_in_any_form` 的 `archive_root.glob(f"*-{change_id}")` 是**后缀匹配**，实跑确认诱饵目录 `2026-01-01-x-fix-issue-235-completion-gate` 会被 `sorted()` 选中（排在 `2026-09-23-…` 之前）。当前语料无此类诱饵、且该 helper 只服务一条一次性证据测试，影响面窄；但若诱饵恰好含 `protected_artifact_explained` 而真 change 不含，该测试会**假绿**（判据落到了别的目录上）。**期望**：`glob(f"*-{change_id}")` 收成日期前缀精确式（如 `re.fullmatch(r"\d{4}-\d{2}-\d{2}-" + re.escape(change_id), candidate.name)`），与生产代码 `ARCHIVE_PATH_RE` 的口径一致。
- **info** R2 报告称「把 active 目录移出后**归档段 exit 0**」——**在 `396bd44` 与 `bdfd9fa` 两个 HEAD 上都不复现**：实跑 `--check-archived --skip-protected-paths --skip-backlog`（真实 clone，active 已 `git mv` 走）两边都是 `exit 1`，唯一错因是 `review manifest missing: …/reviews/building-review-manifest.json`（该 change 有 `building-review.md` 而无 manifest）。这是 `_check_review_manifests(archived=True)` 的**既有**行为（`#232 B`），非本 change 引入，也非缺陷——对应 `tasks.md:63` 那条**显式未勾**的「生成 review manifest」。记此仅为纠正 R2 报告的口径，不影响 verdict。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/test_openspec_artifact_checker.py` | **121 passed** in 2.07s |
| `uv run pytest -q tests/agent/workflow/ tests/test_workflow_guard.py tests/test_flow_policy.py` | **165 passed** in 20.45s |
| `uv run pytest -q`（全量） | **4 failed, 2962 passed, 10 skipped** in 505s → 4 条**全为已知环境失败** |
| `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed** |
| `check_openspec_artifacts.py`（`--base-ref <base> --require-base`，归档态终局模拟） | **exit 0**（`OpenSpec artifact checks passed`） |
| `check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog`（active 移出后） | exit 1：`review manifest missing`（**既有**行为，对应未勾任务 `tasks.md:63`；见 Issues info） |
| `R1 关注测试`：`test_partial_change_does_not_require_building_review` | **1 passed**（未反转 `f4a4272`） |

**已知环境失败（非本 change 引入，如实记录）**——与给定清单吻合：

- `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir, test_malformed_git_file_falls_back_to_scan}`
- `tests/agent/tools/test_factory_sandbox_wiring.py::TestBuildSandboxFromConfig::test_docker_backend`
- `tests/agent/tools/test_sandbox_backends.py::TestBackendSelection::test_docker_backend_available`（无 docker）

本次 tree-sitter Java/Kotlin 用例**未**失败（skip），浏览器用例本次未失败。

**变异测试 4/4**（`cp` 备份 → 改码 → 跑测试 → 还原，`diff -q` 核对，`git status --porcelain` 干净）：

| 变异 | 结果 |
|---|---|
| 回退 M2 下限（`_tasks_missing_evidence` 零勾选不再 True） | `test_archived_gate_flags_all_post_merge_zero_checked` 红（1 failed / 5 passed） |
| 回退 docs 对称性（`change_type.primary != "docs" and …`） | `test_archived_gate_docs_only_missing_tasks_md_is_flagged` 红（1 failed / 3 passed） |
| `--diff-filter=AR` → `A` | `test_archived_gate_ar_catches_pure_rename_where_a_only_misses` 红（1 failed / 2 passed） |
| **M1′ landmine 重引入**（helper 退回硬编码 active 路径） | 归档态下 `FileNotFoundError` **1 failed**（新测试仍有真实判别力） |

**AR 判别性单测**（真实 clone `/tmp/r3-c`，`git mv` 归档本 change）：`--diff-filter=A` 命中 **0** 个路径、`--diff-filter=AR` 命中 **8** 个，`--name-status -M` 显示 `R100` ——两个字母确实缺一不可。

**可满足性**（本轮新增，证明门不是「必然红」）：在真实 clone 里把本 change 按收尾要求终局化（未实现项全部完成并勾选、纯 closeout 项标 `(post-merge)`、backlog 移除、补 `change_archived` 事件、`git mv` 归档）→ CI 第一步真实参数 `--base-ref <base> --require-base` **exit 0**。

## 结论

**PASS**。R2 的三条 issue 我用实跑逐条确认**真的修复**，且修复没有把 R1→R2 的覆辙再走一遍：M1′ 在六种树态下全部给出预期结果（归档 pass / 未来 PR pass / 移出树 skip / 无 remote 不报错），并且我用「回退成硬编码路径」的变异证明这条测试在归档态**仍有真实判别力、不是靠 skip 空过**——这才是「拆 landmine」与「把测试改成永远绿」的分界线；M2 的下限提升既堵住了零勾选（8/93 语料形态真实存在，清单逐条对上）又没误红「一条勾选 + 一条 post-merge」；docs 对称性统一口径后语料零假阳性（2 个 docs 归档都带 tasks.md）。R1/R2 已确认的结论（`f4a4272` 未反转、AR 判别性、`--check-archived` 的既有时序、OpenSpec 30/30、全量 pytest 仅 4 条已知环境失败）均未被破坏，全部变异各自只让对应用例转红并已还原。

留下 3 条 low 与 1 条 info，都不阻塞合入：开发指南的 ✓ 例子把「行尾追加」标成了可用（实为 FLAGGED，照着写会吃红）、零勾选形态复用了「缺失或无 checkbox 行」的误导文案、测试 helper 的 glob 后缀匹配存在诱饵目录面，以及 R2 报告里「归档段 exit 0」的一句口径误差（两 HEAD 上实为 exit 1，错因是既有的 manifest 缺席、对应显式未勾任务）。这些是「更好」，不是「不能合」。

---

# Building Review: fix-issue-235-completion-gate (Round 4)

## Reviewer

- run id: `a5f8b3e1-c854-4d33-b999-28fff1f98400`（独立零记忆 subagent，未继承开发上下文；结论仅来自实读代码 / 实跑输出 / change 文档）
- 时间: 2026-09-23
- base: `4424f54882179ef1ec53d2eaa1a7d373280b91fb`（origin/master，merge-base） head: `f4fcb1ef71ee99caf6d01a674865c7e4417867c7`
- 本轮针对: R3（run `d4524b50`）判 PASS 后作者追加提交 `f4fcb1e` 修的三条 low（非阻塞）
- 审阅方法（全部实跑，作者自述一律不作依据）：
  - **low-1**：`import scripts.check_openspec_artifacts as mod` 取 `POST_MERGE_TAG_RE`，把 `docs/development-guide.md:270-276` 表格里 5 个例子**逐条**喂给正则，比对文档 ✓/✗ 标注
  - **low-2**：造三个归档目录（缺 `tasks.md` / 散文体零 checkbox / 有 checkbox 全未勾选），用 **CI 第一步真实参数** `--base-ref <sha> --require-base` 端到端跑 CLI，并单独直接调用 `_check_archived_completion_gate`
  - **low-3**：`git worktree add --detach`（**避免 `cp -a` 共享 `.git`**）造「真身 active + `2026-01-01-add-<id>` 诱饵」，跑 helper；再做一次**去掉精确名校验**的变异验证判别性；另模拟「真身已归档」态对照旧后缀匹配
  - **回归**：三套 pytest、OpenSpec strict validate、`--check-archived`、纯 rename 归档形态 + `--diff-filter=AR → A` 变异
  - **断言强度**：把「三形态」相关测试放在**四组变异 checker**上跑判别力探针（含把散文消息塌回「缺失」），`cp` 备份 + `diff -q` 核对还原

## Verdict

**PASS**

三条 low 全部**确已修复**，且逐一实跑确认；回归面无新增中等以上问题（R3 的 PASS 结论仍成立）。发现一条**新的 low（维护性）**：low-2 引入的「散文形态」消息串未被任何断言钉住（变异可塌回「缺失」而 122 条全绿），属判别力缺口而非功能缺陷——不影响 verdict，建议顺手补一条断言。

## R3 low Issues 复核

- **low-1（文档示例指向红）— 已修复**。
  证据（`POST_MERGE_TAG_RE` 实跑，`scripts/check_openspec_artifacts.py:114`）——表格 5 行与文档标注**逐条一致**：
  | 文档例子 | 标注 | 实跑 |
  |---|---|---|
  | `- [ ] (post-merge) 收尾：关 issue` | ✓ | True ✓ |
  | `- [ ] 5.5 (post-merge) 收尾：关 issue` | ✓ | True ✓ |
  | `- [ ] **6.9** (post-merge) 收尾` | ✓ | True ✓ |
  | `- [ ] 收尾：关 issue。(post-merge)` | ✗ 行尾 | False ✓ |
  | `- [ ] 5.5 收尾：关 issue (post-merge)` | ✗ 正文插中间 | False ✓ |
  额外探针：全角 `（post-merge）`、`(POST-MERGE)`、`* [ ]`、`+ [ ]`、缩进子项、无空格 `(post-merge)收尾` 均识别。**端到端**也验了：把文档 ✓ 的三条作为**唯一 closeout 项**（配一条 `[x]`）跑 `_check_archived_completion_gate` → 全部放行；文档 ✗ 的两条 → 全部报「未勾且未标 (post-merge)」（fail-closed 方向正确）。原缺陷（把本要防的红标成 ✓）已消除。

- **low-2（错误消息误述）— 已修复**。
  `_tasks_missing_evidence` 由 `bool` 改返回**原因串**（`scripts/check_openspec_artifacts.py:1065-1100`），CLI 侧 `:1628-1633` 用 `missing_evidence is not None` 分流。**CI 第一步真实参数**（`--base-ref <sha> --require-base`，探针仓库）三形态消息**各不相同且准确**：
  - `… 归档点无法评估完成度`，前置串分别为：
    - `2026-09-23-shape-one-no-tasks: ` **`tasks.md 缺失`**
    - `2026-09-23-shape-two-prose-only: ` **`tasks.md 无任何 checkbox 行`**
    - `2026-09-23-shape-three-all-unchecked: ` **`tasks.md 的 checkbox 行全部未勾选`**
  - 三例 **EXIT=1**（fail-closed 未变）。散文/零勾选两例不再被描述成「缺失」，误述已消。单测侧调用同形同文。

- **low-3（诱饵 glob 假绿）— 已修复且判别**。
  `_change_dir_in_any_form`（`tests/test_openspec_artifact_checker.py:2662-2687`）新增 `_strip_archive_date_prefix(candidate.name) != change_id → continue` 精确名校验。
  - **只有诱饵**（`archive/2026-01-01-add-<id>/workflow-events.jsonl`）→ helper 返回 **None** ✓
  - **诱饵 + 真身**（含真身已归档态）→ 返回**真身** `2026-09-23-fix-issue-235-completion-gate` ✓
  - **回退 low-3 修复**（还原成旧后缀匹配）在同一「真身已归档 + 诱饵」态 → 返回**诱饵** `2026-01-01-add-…`（字典序在真身之前）——证明 R3 的担忧是**真实的潜在假绿**，修复是承重的，不是纯净化。
  - **变异判别性**：去掉精确名校验 → `test_change_dir_in_any_form_rejects_suffix_decoy` **1 failed** ✓，还原后 `diff -q` 一致。
  - 附带说明：该缺口在**当前** HEAD（真身 active）不会显形，因为 `:2673` 的 active 分支先命中；真正暴露是在**归档后**（恰是本 change 下一步要做的）。测试用「真身已归档」形态覆盖了它，正确。

## 回归确认

R3 已 PASS 的结论**仍成立**，本轮的 66 行改动（仅 3 文件：`docs/development-guide.md` / `scripts/check_openspec_artifacts.py` / `tests/test_openspec_artifact_checker.py`）未破坏任何既有面：

- `uv run pytest -q tests/test_openspec_artifact_checker.py` → **122 passed**（与作者自述一致；未新增 xfail/skip/monkeypatch）
- `uv run pytest -q tests/agent/workflow/ tests/test_workflow_guard.py tests/test_flow_policy.py` → **165 passed**
- `test_partial_change_does_not_require_building_review` → **1 passed**（active 门不被降级，R2 M1′ 的修复未被回退）
- `npx @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**
- 归档点门核心判别性（纯 rename 形态，`git init` 探针）：`git mv` 字节相同的归档 move 被 `--diff-filter=AR` 取到，`_new_archive_dirs_since_base` → `['2026-09-23-demo-change']` ✓；变异 `AR → A` → `new_dirs=[]`（纯 rename 漏检 ⇒ 门静默通过），证明 AR 的 `R` 是承重的 ✓（已还原核对）
- 全量 `uv run pytest -q` → **4 failed, 2963 passed, 10 skipped**，4 条**全为已知环境失败**（`TestFindScopeRoot`×2、docker×2），在 `/tmp/pristine-235` 上逐条复现，非本 change 引入

## Tasks Verification

- [x] `docs/development-guide.md:268-276` **low-1**：把「行尾追加 ✗ / 紧邻 ✓」的口径换成 ✓/✗ 对照表 —— 表格与 `POST_MERGE_TAG_RE` 逐条实跑一致（见上）
- [x] `docs/development-guide.md:278-281` **low-2 文档侧**：「以下**三种**形态都会被归档点报错——缺文件；写成散文或空文件（零 checkbox 行）；**有 checkbox 行但一条都没勾**……下限是**至少勾选一条**」—— 与实现三形态一一对应，措辞准确
- [x] `scripts/check_openspec_artifacts.py:1065-1100` **low-2 实现侧**：`_tasks_missing_evidence` 返回三态原因串（`:1087` 缺失 / `:1097` 无 checkbox / `:1099` 全未勾选），`return None` 收敛为「有证据」
- [x] `scripts/check_openspec_artifacts.py:1628-1633` **接线**：`missing_evidence = …; if missing_evidence is not None:` —— 三态消息进各自的 `errors`
- [x] `tests/test_openspec_artifact_checker.py:2662-2687` **low-3 实现侧**：精确名校验 + `_strip_archive_date_prefix`
- [x] `tests/test_openspec_artifact_checker.py:2694-2713` **low-3 测试侧**：`test_change_dir_in_any_form_rejects_suffix_decoy` 双向断言（只诱饵→None；诱饵+真身→真身），变异转红
- [ ] `tasks.md:17-28 / 32-47 / 52-58`（仍未勾）—— 属收尾前正常；抽查确认**无「`[x]` 无实现」**，亦**无「未勾但未实现」**：例如 `tasks.md:36` 的 `test_partial_change_does_not_require_building_review` 虽未勾，本轮实跑**通过**，属已实现未勾

## Issues

- **low（维护性 / 判别力缺口）** `tests/test_openspec_artifact_checker.py:2565` — low-2 新增的三条消息里，**散文形态那条没被任何断言钉住**。`:2557` 只在 **docstring** 里写了「无任何 checkbox 行」，实际断言是 `assert any("tasks.md" in e and "归档点无法评估完成度" in e …)`，其合取项 `"tasks.md" in e` 因错误模板**恒定包含** `tasks.md` 而**恒真**（探针证实：把原因串换成任意胡话，该合取项仍为真）。**实测**：变异 `scripts/check_openspec_artifacts.py:1097` 的 `"tasks.md 无任何 checkbox 行"` → `"tasks.md 缺失"`（正是 low-2 要防的「把存在的文件误述成缺失」），`pytest tests/test_openspec_artifact_checker.py` 仍 **122 passed**。
  **期望**：把该断言钉到新增的区分串上（如 `:2565` 改为 `any("无任何 checkbox 行" in e for e in errors)`），并把恒真的 `"tasks.md" in e` 合取项去掉。属**非阻塞**（归档点门本身不是 fail-open，方向 fail-closed，且「全部未勾选」「缺失」两条已被 `:2585` / `:2552` 钉住）；仅建议顺手补，不影响 verdict。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/test_openspec_artifact_checker.py` | **122 passed** in 14.98s |
| `uv run pytest -q tests/agent/workflow/ tests/test_workflow_guard.py tests/test_flow_policy.py` | **165 passed** in 56.44s |
| `uv run pytest -q`（全量） | **4 failed, 2963 passed, 10 skipped** in 359.31s |
| `… -k test_partial_change_does_not_require_building_review` | **1 passed** |
| `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed** |
| `--base-ref <sha> --require-base`（三形态探针） | 三条**互异**消息，**EXIT=1** |
| `--check-archived --skip-protected-paths --skip-backlog`（真实仓库） | exit 1：`fix-issue-235-completion-gate: review manifest missing`（在途 change 未生成 manifest 的**预期**红，对应未勾任务 `tasks.md:63`；**非本轮引入**） |
| 4 条已知环境失败在 `/tmp/pristine-235` 复现 | 4 failed —— 与本 change 无关 |

**变异测试 4/4**（`cp` 备份 → 改码 → 跑 → 还原，`diff -q` 核对，`git status --porcelain` 干净；测试代码变异在**独立 `git worktree`**，script 变异直接 `cp` 还原）：

| 变异 | 结果 |
|---|---|
| 去掉 low-3 精确名校验（`_change_dir_in_any_form` 回退后缀匹配） | `test_change_dir_in_any_form_rejects_suffix_decoy` **1 failed** ✓ |
| `--diff-filter=AR` → `--diff-filter=A` | 纯 rename 归档 `new_dirs=[]`（漏检）✓ |
| `_tasks_missing_evidence` 散文消息 `无任何 checkbox 行` → `缺失` | **122 passed（未捕获）** ← 见 Issues low |
| 回退 low-3 后的「真身已归档 + 诱饵」态 | helper 返回**诱饵**（R3 担忧属实的潜证）✓ |

**审阅环境自述（如实说明）**：我在 `/tmp/shape-probe` 用 `cp -a` 建探测仓库，因拷入的 `.git` 是 **gitfile**（指回真实 worktree 的 git object store），探针的 `git add/commit` 意外落在了真实仓库的远端跟踪 ref `refs/remotes/origin/fix-issue-235-completion-gate/2026-09-23` 上。已发现并清理：`git reset --hard f4fcb1e`（分支回到被审阅 HEAD）、`update-ref` 还原远端跟踪 ref、`rm -rf /tmp/shape-probe`、`git worktree prune`。**已核实 GitHub 从未收到该探针 commit**（`git ls-remote` 显示 `refs/heads/fix-issue-235-completion-gate/2026-09-23` = `f4fcb1e`；`d9a9e10` 是全仓 refs 0 命中）。当前 `git status --porcelain` 仅 `M openspec/changes/.../reviews/building-review.md`（即本报告），与会话开始一致；后续 low-3 探针一律改用**独立 `git worktree`**，不再触碰真实仓库。

## 结论

**PASS**。R3 判 PASS 后作者追加的 `f4fcb1e` 三条 low 修复，我逐条实跑复核，**全部成立**：开发指南的 ✓/✗ 对照表与 `POST_MERGE_TAG_RE` 逐条吻合（含端到端 fail-closed 方向验证）；错误消息真的分成三态、经 CI 第一步真实参数在 CLI 上各自准确、不再用「缺失」描述一个存在的文件；诱饵 glob 的精确名校验既拒了诱饵、又没丢真身，且变异与「真身已归档」对照证明该修复是承重的（旧代码确实会选中字典序在前的诱饵 `2026-01-01-add-…`）。回归面干净：三套 pytest、30/30 strict validate、`--check-archived`、纯 rename 的 `AR` 判别性全部复现，4 条失败均为已知环境失败并在 pristine 上复现，R3 的 PASS 结论未被破坏。唯一新发现是一条**非阻塞 low**——low-2 的散文消息串没被断言钉住（可塌回「缺失」而 122 条全绿，且现有断言的 `"tasks.md" in e` 合取项恒真），属判别力缺口而非功能缺陷，建议顺手补一条精确断言即可，不改变 verdict。
