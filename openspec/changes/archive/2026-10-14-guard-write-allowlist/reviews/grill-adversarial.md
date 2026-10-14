# 对抗验证：guard-write-allowlist（grill 整合稿）

## Reviewer

- **run id**: `grill-adversarial-guard-write-allowlist-20261014`（独立零记忆对抗验证 subagent；默认上游两组主张都有错，逐条证伪；能实测的必须实测，全称否定一律用计数口径）
- **被审 revision**: `11f744e`（分支 `guard-write-allowlist/2026-10-14`，`origin/master` = `fd6d581`）；对照基线 `f09fa77`（立项稿）
- **上游**: `reviews/grill-design.md`（run `grill-guard-write-allowlist-20261014`，被审 `f09fa77`）+ 作者的整合 commit `11f744e`
- **约束遵守**: 被审 worktree 只读；唯一写入 = 本文件。全部实验在 `/tmp/gwa-adv`（`git archive HEAD | tar -x` 重建的隔离副本，无 `.git`，未在被审树跑任何改状态命令）；探针脚本落在 `/tmp/gwa-adv/probe_*.py`；`PYTHONDONTWRITEBYTECODE=1`。
- **方法**: ① 逐条实读被审文档（proposal/design/tasks/两份 spec delta/grill-design.md）与 `git show 11f744e` / `git diff f09fa77..11f744e`；② 隔离副本里直跑 `WorkspacePolicy` / `CommandGuard` 六组探针（命令判定 + `last_reason`、两层同向性、deny 表计数与分类、读写判定、附加根、`assert_command_allowed`）；③ 用 witnessloop 自己的 `grill_evidence_findings`（`/home/happy/witnessloop/src/witnessloop/evidence.py`）跑全部 63 份归档 `grill-design.md` 复算 Decision 8 的每一个数字；④ 用脚本把两份 spec delta 的全部 `文件:行号` 引用在**当前树**上重放（45 个 distinct 引用 + 逐个人工复核）；⑤ 跑 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（30 passed）。

---

## Verdict

**CHANGES_REQUESTED**

- **A 组（grill 三条阻塞的修复）三条全部成立**，且我做了作者没做的**计数级复核**（`is_denied` / `assert_read_allowed` / `assert_write_allowed` 的全部生产调用点）确认「不受影响清单」无遗漏；没有把矛盾挪到别处。
- **B 组三条订正里，①不成立、②成立、③成立但补全后仍不完整**。① 的方向是反的（详见下）：作者**没有**声称那四条 DENY，实测它们也**不是** DENY 类结构，Decision 9 的表是对的。
- **但有 6 条必须修改项**，其中 **B1（Q 编号冲突使确认门对 build 之前的阻塞项不可靠）** 与 **B2（Q12 例子与 Decision 3 的精确路径语义自相矛盾）** 直接落在本轮要「停轮拍板」的材料上——用户会照着错的例子做决定。

---

## 一、A 组：grill 判定的三条阻塞（作者声称已修好）

| # | grill 的阻塞判定 | 对抗结果 | 关键证据（当前树实测） |
|---|---|---|---|
| A1 | 读侧泄漏：`is_denied` 是读/写同一实现，`repo_map.py` 直接调它 ⇒ 照原稿写会连读侧与符号索引面一起打开 | **成立**（grill 对，作者修复有效且无遗漏） | `agent/workspace_policy.py:352` `assert_read_allowed` 与 `:358` `assert_write_allowed` **都**调 `self.is_denied(resolved)`（def 在 `:316-338`）；`agent/code_intelligence/repo_map.py:173` 直接 `if policy.is_denied(path)`（tree-sitter 跳过）。**计数复核**——非测试调用点：`is_denied` 恰 4 处（def + `:352` + `:358` + `repo_map.py:173`）、`assert_read_allowed` 恰 11 处（def + 7 个读工具 `read/grep/list_files/find/read_doc/inspect_git_diff/lsp.py` + `repo_map.py:81,96`）、`assert_write_allowed` 恰 4 处（def + `edit.py:55` + `write.py:48` + `browser/policy.py:121`）⇒ design.md:82/320-321 的「不受影响」与「受影响但属正确」清单**逐条覆盖无遗漏**。改法（`design.md:67-84` Decision 2「共享**谓词函数**、不共享**调用点**；allow 只在写路径求值」+ spec.md:9）结构上不可能打开读侧：allow 是独立谓词、只在 `assert_write_allowed` 与命令护栏写目标处求值，`is_denied` 一行不动。规格新表述（spec.md:9「`is_denied` 与其读侧调用方 SHALL NOT 感知 allowlist」）**可机械判定**：对同一份 policy 换 allowlist、断言 `is_denied` / `assert_read_allowed` 结论不变即可（我今天实测 `is_denied` 与 allowlist 无任何耦合）。 |
| A2 | 嵌套 `.env` 的 Bash **写**被 `_EXTRA_DENYLIST` 前置拦下 ⇒ proposal 示例只兑现一半 | **成立**（grill 对，作者新增 Decision 9 的处置正确，三处口径已对齐） | 实测（隔离副本）：`cp x config/.env` / `mv x config/.env` / `cp x ./config/.env` / `cp x 'config/.env'` / `cp x /tmp/../config/.env` **五变体全 DENY 且 `last_reason=denylist`**（我另加 `cp x ../config/.env` 也 `denylist`）——拦它的是 `agent/tools/command_guard.py:609` 的正则、由 `:737-741` 在**任何 IR 判定之前**对整句执行。裸名 `cp x .env` 走 `mv_cp_dest`（可挂钩）。⇒ 与 allow 挂钩点结构不相交。作者的处置：`design.md:119-134`（Decision 9 兑现面表）+ `design.md:214-219`（Q7）+ `proposal.md:27,45,75,114` + **规格新增第五条 Requirement**（`specs/workspace-safety/spec.md:119-134`）。我把 proposal/spec/design 三处口径**逐处比对**：一致，没有半真承诺残留；示例已从 `['.env','config/.env']` 改为两个裸名（`proposal.md:27`）。规格新表述可机械判定（`spec.md:127` 断言 `last_reason=="denylist"`）。 |
| A3 | 规格「两层结论同向」不可满足 ⇒ 照写回归测试一写即红 | **成立**（grill 对；改成增量表述后可满足） | 实测 14 条被拒路径里 **9 条**文件层 `assert_write_allowed` DENY、Bash `cp x <path>` ALLOW 且 `last_reason=None`（`deploy.pem` / `srv.key` / `id_rsa` / `id_ed25519` / `node_modules/x.js` / `benchmarks/runs/r.json` / `.venv/y.py` / `__pycache__/z.pyc` / `.ruff_cache/x`）——design.md:30 点名的 8 条**全部在内**（另加 `id_ed25519`）。根因属实：护栏的目标判定只按段级敏感名 + 固定 `_DENY_PATHS`（`command_guard.py:935`），**不读** `DEFAULT_DENIED_PATTERNS`。改写后的两条 Requirement（`spec.md:103-117`「不使任何一层比引入前更宽」+「被命中的路径两层同向变化」）**可机械判定**——比较引入前后逐条结论即可，且规格明写不承诺「恒同向」。**残留见 B5**。 |

---

## 二、B 组：作者对 grill 的三处订正

| # | 待验的「作者订正」 | 对抗结果 | 关键证据 |
|---|---|---|---|
| B1 | grill 称 `echo K >> config/.env` / `tee config/.env` / `dd of=config/.env` / `install x config/.env` 是 **ALLOW**，**作者实测四条全 DENY** | **不成立（方向是反的）** | (a) **被审 revision 里不存在这个订正**——`grep -rn "四条\|全 DENY"` 全 change 目录只有 `tasks.md:73`（测试执行点四条，无关）、`design.md:39`（四条硬约束）、`design.md:188`（四条路径）。相反，`design.md:126` 的兑现面表与 `design.md:217`（Q7 例 (a)）**明写这四个形态 ✅ 可兑现**（`protected_redirect` / `tee_target` / `dd_target` / `install_target`，均可挂钩），与 grill 的 Q1 一致；`proposal.md:114` 同口径。(b) **实测支持设计、不支持「四条全 DENY」这一说法**：这四个形态今天**确实**全 DENY，但原因分别是 `protected_redirect` / `tee_target` / `dd_target` / `install_target`——**没有一条是 `denylist`** ⇒ 拒绝点都在 IR 的写目标判定面上、**结构上可挂钩**，与 `cp`/`mv` 的 `denylist`（pre-IR、不可挂钩）**不同类**。⇒ 作者未作此订正，且该订正若作出即为错；`Design Decision 9` 的表是对的，Q7 的推荐值 (a) 成立。**另**：`design.md:24` 的「第 6 条由独立 grill 证伪后订正」措辞悬空——`f09fa77` 的「实现要点复核」只有 4 条、没有第 6 条可被订正，建议改为「第 6 条为整合时新增」。 |
| B2 | grill 按「含 `/`」**单源**推导结构性 deny 会误分类 11 条，作者改为**两源**推导 | **成立** | 实测计数（`agent/workspace_policy.py:9-43`）：`DEFAULT_DENIED_PATTERNS` **32** 条；含 `/` **16** 条、不含 `/` **16** 条——与 `design.md:241` 逐字相符。单源（含 `/` ⇒ 目录级）误分类 = **11**：8 条**裸目录名**（`.git`/`__pycache__`/`node_modules`/`.venv`/`venv`/`.mypy_cache`/`.pytest_cache`/`.ruff_cache`）被划成文件级 + 3 条 `**/id_rsa`/`**/id_ed25519`/`**/id_ecdsa`（文件模式）被划成目录级——与 `design.md:244` 逐条相符。两源规则（`含 '/' 的条目` ∪ `任一路径段命中 SENSITIVE_DOTDIRS`）与读码一致：`SENSITIVE_DOTDIRS` 9 项在 `:66-68` ✓。 |
| B3 | grill 引的行号 `W06-security.md:36` 实为 `:35` | **成立，但补全后仍不完整** | `grep -n "58" docs/interview-script/walkthrough/W06-security.md` ⇒ **:11** 与 **:35** 两处都写「58 个模式」（:36 是别的段落）。整合把 `design.md:324` 与 `tasks.md:79` 都改成 `:35` ⇒ 指向正确，但**漏了 :11**（同一问题的第二处命中），照 7.1 执行会留下 :11 不改。另 grill 原报告写的 `:10` 也是错的（应为 `:11`）。 |

---

## 三、Open Questions 的例子抽查（Q1–Q12）

12 条**全部**配了用本 change 真实场景构造的具体例子（参数 + 前后对比），这一条 grills 的要求满足。抽查正确性：

- **Q1 / Q2 / Q3 / Q5 / Q6 / Q7 / Q8 / Q9 / Q11 的例子经实测或读码核对，无实质错误。** 其中 Q3 的 `cp .env.example .env.local` ⇒ DENY `mv_cp_dest` ✓、Q6 的 `cat .env` / `grep API_KEY .env` / `head -5 .env` / `source .env` / `. .env` 两层全 ALLOW ✓、`python -c '...'` 被 denylist 拦 ✓、Q5 的 `edit.py:55,67`（先 `assert_write_allowed` 再自己 `read_text`）与 `write.py:52-56` 的「已存在」文案 ✓、Q7 的五个 cp/mv 变体与四个非 cp/mv 形态 ✓ —— **均逐条实测复现**。
- **Q10 的例子写错了**（见 B3'）。
- **Q12 的例子与 Decision 3 自相矛盾**（见 B2'）。
- **Q9 例子的机制描述不准**（见 B7），结论不变。
- Q4（配置发现）与 Q10（先后顺序）引用的迁移目标存在：`openspec/specs/configuration/spec.md:42`「配置文件发现受工作区边界约束」✓、`tasks.md:27/30`（2.2④ / 2.5）✓。

---

## 四、`文件:行号` 锚点复核（本轮重点，作者自称全部现测）

脚本重放了 5 份文档里的 **45 个 distinct `文件:行号` 引用**（含范围），**零越界、零指向不存在的文件**；我又人工复核了 25 处 load-bearing 锚点，**全部逐字命中**：

- `agent/tools/builtin/bash.py:87` = `CommandGuard(workspace=self.policy.workspace_root)` ✓（且全仓非测试 `CommandGuard(` 构造**恰 1 处** ✓）
- `agent/main.py:251-254` / `web/session.py:1728-1731` / `benchmarks/agent_runner.py:349-352` = 三个 `WorkspacePolicy(...)` 构造点 ✓（逐行对上）
- `agent/tools/builtin/subagents.py:2005` = `workspace_policy=WorkspacePolicy(workspace_root=sandbox)`，`dry_run_workflow` 定义在 `:1979` ✓；`agent/tools/factory.py:316,422` 才是 `policy or WorkspacePolicy()` 兜底、`:335,457` 是 `BashTool(policy=policy, ...)` ✓
- `agent/browser/policy.py:121` ✓、`agent/config.py:151-161`（`ToolsConfig`）与 `:875-897`（`_parse_tools_config`）✓、`asterwynd.example.yaml:35`（`command_denylist: []`）✓、`web/session.py:1516`（`register_workspace`）✓、`agent/commands/registry.py:507` ✓
- `agent/tools/command_guard.py:565-574` / `:609` / `:737-741` / `:872-878` / `:930-938` / `:940-960` / `:976-993` / `:1077-1103` 全部命中 ✓
- `agent/workspace_policy.py:239` / `:307-314` / `:316-338` / `:323-324` / `:326-330` / `:331-337` / `:350-354` / `:352` / `:356-360` / `:358` / `:9-43` / `:66-68` / `:91-102` 全部命中 ✓
- witnessloop 侧 `src/witnessloop/evidence.py:33`（`_SOURCE_RE`）、`contract.py:148`/`:185-206`、`constants.py:65-76`、`evidence.py:197-210` 全部命中 ✓

⇒ **本轮没有发现新的行号漂移**；唯一与行号相关的问题是 B3（W06 的 `:11` 漏列，非漂移）。
`openspec validate --all --strict` 在隔离副本上 **30 passed**；两份 delta 的六条 Requirement 正文首行**均含 `SHALL`**（`specs/workspace-safety/spec.md:7,51,74,105,121,140`、`specs/configuration/spec.md:7`），无硬换行误报。

---

## 新发现

### B1（中危，阻塞）— Q 编号冲突使「停轮确认门」对 build 之前的阻塞项不可靠

`design.md:177` 明写 **design 的 Q7–Q12 = grill 的 Q1–Q6**；而 `reviews/grill-design.md` 的 `## Open Questions` 里列的正是 **Q1–Q6**（`reviews/grill-design.md:22-27`）。两侧消费者（`scripts/check_openspec_artifacts.py:750,765` 与 `scripts/workflow_guard.py:391`）**都只读 `reviews/grill-design.md`** 来判「未确认的 Open Question」。后果两条：

1. **门覆盖的与我以为的相反**：机械门强制的其实是 **design 的 Q7–Q12**，而 design 立项原提的 **Q1–Q6**（allow 覆盖面 / 粒度 / 变体是否跟随 / 配置级别 / 读写是否区分 / Bash 读侧）**完全不在门里**——只答 grill 那六条即可过门。
2. **编号命名空间碰撞**：`tasks.md:12-13`（0.2/0.3）要求把 **design 的十二条（Q1–Q12）** 逐条抛给用户、逐条记进 `reviews/grill-design.md` 的 `## User Confirmation`（格式 `- **Q<n>**: 用户答复：…`）。按此执行，`- **Q1**: 用户答复：<design Q1 的答复>` 会被门当作 **grill 的 Q1（= design 的 Q7，嵌套 `.env` 的 Bash 写是否扩范围）** 已确认——**门判绿，但确认的是另一个问题**。实测复现口径：`_extract_open_question_indexes` 从 grill-design.md 取 `{Q1..Q6}`，`_extract_user_confirmation_indexes` 取记入的 `Q1..Q12` ⇒ 差集为空 ⇒ 过门。

⇒ 用户答完 12 条会「碰巧」过门，但只要有人只记 6 条（或把 Q1 的答案记成 design Q1 的内容），门就给出**语义错误**的绿。这是整合新增 Q7–Q12 时引入的编号冲突。

### B2（中危，阻塞）— Q12 的例子与 Decision 3 的「精确路径」语义自相矛盾

`design.md:242` 的例子配置是 `allowed_write_paths: ['.ruff_cache', '.git']`（**目录名**），而 (i) 分支断言 `Write .ruff_cache/CACHEDIR.TAG` ⇒ **ALLOW**（`design.md:243`）、`.ruff_cache/x.pyc` ⇒ 仍 DENY（被 `*.pyc` 命中）。要让「条目 `.ruff_cache` 覆盖目录内文件」成立，allow 必须是**按 deny 规则名**（pattern 级）生效；但 `design.md:86-97` 的 Decision 3 与 `spec.md:49-51` 明写条目是「workspace 相对路径的**字面值**（精确匹配）」、并**拒绝以 `/` 结尾的目录形式**——即 path 级。Q12 自己的「残余」段（`design.md:246`）也用的是 path 级（「`.venv` 即便被归为文件级，也只能放行一个**恰好叫 `.venv` 的文件**」）⇒ **同一个 Q 内部两种语义**。实测：`Write .ruff_cache/CACHEDIR.TAG` 今天 `is_denied=True`（裸 `.ruff_cache` 段命中 + `.ruff_cache/**`），在 path 级语义下，条目 `.ruff_cache` **不覆盖**该路径，(i) 的「⇒ ALLOW」不成立。

⇒ 用户会被一个站不住的 (i)-vs-(ii) 对照说服。修法很小：把例子的配置改成 `['.ruff_cache/CACHEDIR.TAG', '.git/config']`（path 级），(i) 的「同一目录两种结论」仍然成立。

### B3（低-中，阻塞）— Q10 的例子引用了已不存在的计数

`design.md:234` 写「…1.1 的「**三条 Requirement**」变两条」，但这是 `f09fa77` 时期 `tasks.md:19` 的原文；整合后 `tasks.md:19` 已改成「新增**五条** Requirement」（与 `spec.md` 实际的 5 条 ADDED 相符，我逐条数过）。⇒ 引号里的字串在当前树里不存在，且「变两条」在新计数下应为「五条减一 = 四条」。另 `design.md:233` 的「（`specs/workspace-safety/spec.md` 的三条新 Requirement + …一条）」与实际的 5 条也不一致（若此处「三条」是刻意只指编码 Q1/Q2/Q3/Q5 推荐值的那三条，请写明，否则会被读成笔误）。

### B4（低，非阻塞）— Decision 8 / Q11 / tasks 6.8 的「加粗独占行只有 1 份」是错的

我用 witnessloop 自己的 `grill_evidence_findings` 复算全部 **63** 份归档 `grill-design.md`：

| 口径 | grill 报告说 | 作者整合说 | **我实测** |
|---|---|---|---|
| 零 finding（判绿） | 39 | 39 | **39** ✓ |
| 只缺 `来源:` | 14 | 9 | **9** ✓（作者对，grill 错） |
| 其它 | 10 | 15 | **15** ✓（作者对，grill 错） |
| 用 `- **来源**:` 独占加粗行 | 2 | 1 | **2**（grill 对，作者错） |

加粗独占行的两份是 `openspec/changes/archive/2026-08-03-grill-confirmation-gate/...`（16 条决策全用）与 `openspec/changes/archive/2026-10-13-witnessloop-adoption/...`（7 条决策，12 行加粗 `来源`）——两份都被判 **src-only**（红），正好是「格式选择导致的红」的实例。（`design.md:169,237`、`tasks.md:74` 三处都要改。另 `design.md:239` 的「本仓多数归档用加粗写法也照样判绿」与实测 2/63 不符，建议删。）

### B5（中，阻塞）— Req4 的「两层同向变化」与 Req5 的刻意例外口径重叠

`spec.md:113-117` 的 Scenario「被命中的路径两层同向变化」对**任意** allow 命中路径断言「两处 SHALL 都从拒变为放行（SHALL NOT 出现只放宽一层的形态）」；`spec.md:123-128`（Req5）又要求嵌套路径的 Bash `cp`/`mv` **保持 DENY**。对 `allowed_write_paths: ['.config/.env']` 这类嵌套命中，`cp x config/.env` 按 Req5 必须仍 DENY ⇒ 与 Req4 的字面读法冲突。判据落在「命令护栏的**写目标判定**」这个**规格 delta 里未定义**的术语上（`design.md:73` 把它定义为 `_check_target` / `_has_protected_redirect` / `_check_dynamic_target` 三个面，但该定义**没有进 delta**）。⇒ 严格说这条 Scenario **不是可机械判定的**（照字面写 `tasks.md:32` 的 2.7 测试会红）。修法：在 Req4 写死「写目标判定指命令护栏的写目标判定面（不含命令 denylist 的整句前置扫描）」，或给 Scenario 加「路径的拒绝来源可被 allow 挂钩」这一前提。

### B6（低，非阻塞，**变更前就存在**）— proposal 表与 design 表对同一行给出相反结论

`proposal.md:18`：`| cp .env.example .env | ❌ DENY（mv_cp_dest） | ❌ DENY |`；`design.md:17`：`| cp .env.example .env | ALLOW | DENY（last_reason=mv_cp_dest） |`。两处都自称「实测探针」结果，同一动作同一格相反。实测裁决：`WorkspacePolicy.assert_command_allowed('cp .env.example .env')` ⇒ **ALLOW**（`_env_source_is_credential` 放行模板源、`_match_allowlist` 不命中也不抛）⇒ **design 对、proposal 错**（且 `mv_cp_dest` 是 `CommandGuard` 的 reason，放在「文件工具层」列本就错位）。`git show f09fa77` 确认该行在立项稿里就是这样，属**遗留**而非整合新引入，但既然本轮在改 proposal（:27/:45/:75/:114），顺手修掉成本为零。

### B7（低，非阻塞）— Q9 把 Bash 层恒定 DENY 的机制归错了面

`design.md:227` 说 Bash 层「`_dest_is_sensitive` 只按段名」⇒ `cp x /srv/other/.env` 恒定 DENY。实测该命令 `last_reason=**denylist**`——因为附加根必然是绝对路径、含 `/`，先命中 `command_guard.py:609` 的整句正则（pre-IR、**不可挂钩**），`_dest_is_sensitive` 根本没轮到。结论（恒定 DENY）不变，但机制归属影响后续解读（`denylist` 拦下的是不可挂钩的那一面，反而与 Decision 9 同源），建议改写。

### B8（低，非阻塞）— 文档债务扫描漏一处

见 B3（表格里的「作者订正 ③」）：`docs/interview-script/walkthrough/W06-security.md` 的「58 个模式」在 **:11** 与 **:35** 两处，`design.md:324` / `tasks.md:79` 只列了 `:35`。同一处 passage 里 `docs/interview-bullets/walkthrough.md:2481`（`agent/workspace_policy.py:9-45`，现为 `9-43`）与 `:2499`（`is_denied()`（`:222-239`），现为 `316-338`）也是陈旧锚点，设计只点了 `:2483`/`:2497`。建议 7.1 的扫描把这几处一并列出再给「改 / 不改 / 记债」结论。

---

## 必须修改项

1. **修 B1（门与编号）**：把 design 的 Q1–Q6 也纳入机械门——最小改法是在 `reviews/grill-design.md` 的 `## Open Questions` 补 Q1–Q6（或把 design 的十二条重编号为 grill-design.md 的编号并同步 `design.md:177` 的映射说明），并在 `tasks.md:12-13`（0.2/0.3）写明「记进 `## User Confirmation` 的编号必须是 `reviews/grill-design.md` 的编号，否则门判的是另一个问题」。
2. **修 B2（Q12 例子）**：`design.md:242` 的配置改为精确路径（如 `['.ruff_cache/CACHEDIR.TAG', '.git/config']`），使 (i)/(ii-a)/(ii) 三支的对照在 Decision 3 的 path 级语义下成立。
3. **修 B3（Q10 例子）**：`design.md:234` 的「三条 Requirement / 变两条」按当前 `tasks.md:19`（五条）改正；`design.md:233` 的「三条新 Requirement」或改数、或写明是哪三条。
4. **修 B4（数字）**：`design.md:169`、`design.md:237`、`tasks.md:74` 的「1 份」改为 **2 份**；`design.md:239` 的「本仓多数归档用加粗写法」删除或改为「2/63」。
5. **修 B5（规格可判定性）**：在 `specs/workspace-safety/spec.md` 的「不使任何一层更宽」Requirement 或 Scenario 里钉死「命令护栏的写目标判定」= 不含命令 denylist 整句前置扫描的写目标面（与 Req5 的刻意例外对齐）。
6. **修 B6（proposal 表）**：`proposal.md:18` 的第一格改为 `✅ ALLOW`、第二格改为 `❌ DENY（mv_cp_dest）`（或注明该列口径）。

> B7（Q9 机制）与 B8（`:11` 及同 passage 的陈旧锚点）建议一并修，但属可读性/完整性，不单独阻塞。

---

# R2 复审（revision 33c512a）

## Reviewer

- **run id**: `grill-adversarial-r2-guard-write-allowlist-20261014`（独立零记忆对抗验证 subagent，第 2 轮复审；上游两组主张默认有错，逐条证伪；能实测的必须实测；全称/否定一律计数口径）
- **被审 revision**: `33c512a`（作者修 R1 的 6 条必须修改项）；对照基线 `11f744e`（R1 被审稿）与 R1 报告 `reviews/grill-adversarial.md`
- **约束遵守**: 被审 worktree 只读（仅一次只读跑 `check_openspec_artifacts.py`，跑后 `git status --porcelain` 为空）；全部探针在 `/tmp/gwa-r2`（`git archive HEAD | tar -x`，无 `.git`）内跑，用项目 venv 解释器 `/home/happy/ax-wt/guard-write-allowlist/.venv/bin/python`（**系统 python3 缺 bash_ir 依赖 ⇒ 命令判定会退化成 `ASK/unanalyzable` 假结论，第一轮探针已踩到并改用 venv 复测**）；`PYTHONDONTWRITEBYTECODE=1`。
- **方法**: ① 实读 `git show 33c512a` 全 diff 与两份 Q 清单；② 隔离副本里**直跑两侧消费者自己的函数**（checker `_extract_open_question_indexes` / `_extract_user_confirmation_indexes` / `_unconfirmed_open_questions` / `_extract_grill_decisions`，guard `_extract_open_question_indexes` / `_extract_user_confirmation_indexes` / `_grill_evidence_missing`）取原始输出；③ 用 witnessloop 自己的 `grill_evidence_findings`（`/home/happy/witnessloop/src/witnessloop/evidence.py`，`uv run`）复算 63 份归档与本 change 的 finding 构成；④ 隔离副本里跑 `WorkspacePolicy` / `CommandGuard` 探针复测 B2/B5/B6/B7 的每一条命令级断言；⑤ 脚本重放 6 份文档的全部 `文件:行号` 引用；⑥ 隔离副本跑 `openspec validate --all --strict`。

## Verdict

**CHANGES_REQUESTED**

- **B1 的机械面是**真收敛**：两份文件的 Q 集合已实测对齐为同一套 Q1–Q12（无重号、无缺号、无张冠李戴），两侧消费者输出一致，写码仍被正确拦下。**
- **但修得不完整**：R2 把 `grill-design.md` 的问题数从 6 条改成 12 条后，**三处陈述同一事实的地方留在旧值**（`design.md:238`、`design.md:289`、`tasks.md:69`），其中 `design.md:238` 与 `design.md:289` 都在**停轮拍板材料**（Q11）里，与同一文件的 `design.md:169` 直接矛盾。
- **B5 的方向对但没修干净**：`spec.md` 新增的例外 Scenario（`:120-125`）的 GIVEN 过宽，照字面写测试会红（实测反例 `cp x config/notes.txt` ⇒ ALLOW），与 R1 判它阻塞时的理由同类。

## 一、B1 复核：Q 编号映射表（逐条核对，非抽样）

`reviews/grill-design.md:26-37`（新 Q1–Q12）对 `design.md:179-246`（Q1–Q12），语义逐条比对；左列括号是**重编号前**的 grill 编号（`git show 11f744e:.../reviews/grill-design.md` 的 `## Open Questions` 顺序 Q1–Q6）：

| 新编号 | `grill-design.md` 问的是 | `design.md` 同名编号问的是 | 同一件事？ | 原 grill 编号 |
|---|---|---|---|---|
| Q1 | allow 覆盖哪些 deny 来源（文件级 vs 结构性目录） | 同 | ✓ | —（立项期） |
| Q2 | 粒度：精确路径 / 目录前缀 / glob | 同 | ✓ | — |
| Q3 | `.env.local` / `.env.production` 是否跟随 | 同 | ✓ | — |
| Q4 | 配置住哪一级 | 同 | ✓ | — |
| Q5 | 只放行写 vs 读写都放 | 同 | ✓ | — |
| Q6 | 要不要顺手堵 Bash 读侧 | 同 | ✓ | — |
| Q7 | 嵌套 `.env` 的 Bash `cp`/`mv` 要不要兑现（动不动 denylist 扫描顺序） | 嵌套路径（`config/.env`）的 Bash `cp`/`mv` 写要不要一并兑现 | ✓ | 原 Q1 |
| Q8 | allow 判定面接在哪才既同源又不放行读 | 同 | ✓ | 原 Q2 |
| Q9 | allow 条目是否覆盖附加根 | 同 | ✓ | 原 Q3 |
| Q10 | 推荐值已写进规格 vs design 声称「不等于确认」，改的先后顺序 | 用户裁定与规格 delta 已写文本冲突时，改的先后顺序 | ✓（同一取舍，措辞重心不同） | 原 Q4 |
| Q11 | 阶段 B「全红」是结构性不兼容还是取决于写法；(a) 报告格式 (b) 归因表加不加第三类 | 本 change 的 `来源:` 按哪种写法定稿（含同一组 (a)/(b) 子裁定） | ✓（同上） | 原 Q5 |
| Q12 | Q1(b) 的「结构性 deny」判定口径：封闭列举 vs 推导 | 同 | ✓ | 原 Q6 |

- **张冠李戴？没有。** 重编号是**保序**的：原 Q1→Q7、Q2→Q8、Q3→Q9、Q4→Q10、Q5→Q11、Q6→Q12，语义与 `design.md` 的 Q7–Q12 逐条对上（Q7/Q9 的正文连"已按 R1 的 B7 订正"都同步改了）。
- **丢问题 / 重号？没有。** 机械口径（隔离副本实测，原始输出）：
  - `scripts/check_openspec_artifacts.py:816` `_extract_open_question_indexes(grill-design.md)` = `['Q1','Q2','Q3','Q4','Q5','Q6','Q7','Q8','Q9','Q10','Q11','Q12']`（恰 12 个、无重复）；`design.md` 同。
  - `:845` `_extract_user_confirmation_indexes(...)` = `[]`（尚无 `## User Confirmation`）；`:874` `_unconfirmed_open_questions(...)` = 全部 12 条。
  - `scripts/workflow_guard.py:434/459` 两个同名函数输出**逐字相同**；`:398-402` `_grill_evidence_missing('guard-write-allowlist')` = `True`（= 写码仍被拦，符合 0.3 未完成的状态）。
  - `:883` `_extract_grill_decisions` = **7** 条（≥3 门槛 ✓）。
- **R1 指出的两条后果已消除**：① 门现在覆盖**全部 12 条**（不再是「只强制 grill 那 6 条」）；② `tasks.md:13` 写死了编号纪律（「`n` 必须用 `reviews/grill-design.md` 的编号」），且两份文件编号已同构，撞号张冠李戴的路径不复存在。
- **残留（阻塞）**：同一次事实变更没有传导到三处——
  - `design.md:238`（Q11 的「具体例子」）：仍写「实测 findings 只有「缺 `## User Confirmation` 小节」+「**Q1–Q6** 未经确认」共 **7 条**」。实测（witnessloop `grill_evidence_findings`，隔离副本）：**13 条** = 1 条缺小节 + **Q1–Q12** 各 1 条。同文件 `design.md:169` 已改成 13 条/Q1–Q12 ⇒ **同一文档自相矛盾**，且这条正是用户拍 Q11 时要读的材料。
  - `tasks.md:69`（6.3）：同样写「当前 **7 条**：1 条「缺 `## User Confirmation` 小节」+ 6 条「**Q1–Q6** 未经确认」」，与同文件 `tasks.md:13`（13 条 / Q1–Q12）矛盾。
  - `tasks.md:3`（文件头状态块）：「`design.md` 的 `## Open Questions` **六条**必须停轮抛给用户」——`git show 11f744e` 显示这句在 R2 之前就是「六条」（属遗留），但本轮既已钉死「两份都列 12 条」，这句不一起改就是新增的第三处矛盾。

## 二、B2–B8 逐条结论

| # | R1 要求 | R2 结论 | 证据（当前树实测） |
|---|---|---|---|
| B1 | 修门与编号 | **成立（真收敛）**，但三处计数未传导 | 见上节 |
| B2 | Q12 例子改精确路径 | **成立** | `design.md:242` 已为 `['.ruff_cache/CACHEDIR.TAG', '.git/config']`；隔离副本探针 `is_denied` 两者皆 `True`；(i)「不在原稿 6 条列举里 ⇒ ALLOW」/(ii-a)「`.ruff_cache/**` 含 `/` ⇒ 结构性 ⇒ 仍 DENY」/(ii)「两源 ∪ ⇒ 仍 DENY」三支在同一条目上自洽；`:246` 残余段仍用 path 级（`.venv` 只能放行一个恰好叫 `.venv` 的文件），不再有两种语义 |
| B3 | Q10 的「三条」改计数 | **成立** | `design.md:233` 改「五条新 Requirement 里的第 1–3 条与第 5 条 + configuration 一条（第 4 条为硬约束）」；`:234` 改「五条 Requirement 变四条」。我数过 delta：`specs/workspace-safety/spec.md` 的 `## ADDED Requirements` **5 条**（`:5,:49,:72,:103,:127`）+ `specs/configuration/spec.md` 1 条（`:5`）⇒ 与 `tasks.md:19` 的「五条」一致 |
| B4 | 「加粗来源 1 份」改 2 份 | **部分成立：四改三，漏 R7** | 已改：`design.md:169`、`:237`、`:239`（2/63）、`tasks.md:74`。**未改**：`design.md:289`（R7）仍写「用加粗独占行的只有 **1 份**」+「当前 **7 条** finding」⇒ 与 `:169` 自相矛盾。我复算：bullet 形式 `- **来源**:` 恰 **2** 份（`2026-08-03-grill-confirmation-gate` 4 行行首、`2026-10-13-witnessloop-adoption` 12 行缩进），两份都 src-only 红 ✓。**口径提醒**：`2026-09-29-workflow-recursion-limit-default` 用**同行内联**加粗 `**来源**：`（5 条决策），同样被判 src-only 红——`design.md:239` 的「使用加粗写法…只有 2/63」在宽口径下应为 **3/63**（`_SOURCE_RE` 是 `re.search`，加粗不论独占还是内联都不命中）；`design.md:169/237/tasks.md:74` 用的「含加粗 `- **来源**:` 行」口径下 2 正确 |
| B5 | 钉死「写目标判定」、与 Req5 对齐 | **成立但新增 Scenario 的 GIVEN 仍过宽** | `specs/workspace-safety/spec.md:105` 已写死「在命令护栏的『可挂钩写目标判定面』上（… **不含**在命令 IR 判定之前执行的**整句 denylist 正则扫描**）」；`:116` 给 Scenario 加前提；`:120-125` 新增例外 Scenario。**但** `:122` 的 GIVEN「一个被它命中的**嵌套**路径（如 `config/.env`）」+ `:124`「命令护栏 SHALL 仍判 `deny`（`last_reason` 为 `denylist`）」对一般的嵌套路径为**假**：隔离副本实测 `cp x config/notes.txt` ⇒ `ALLOW` / `last_reason=None`（同理 `cp x config/deploy.pem` ⇒ ALLOW），而 `config/notes.txt` 完全可能是被 allow 命中的嵌套路径 ⇒ 照字面写测试必红。修法一个从句：GIVEN 收窄为「被**整句 denylist 正则**命中的嵌套敏感路径（如 `config/.env`）」 |
| B6 | proposal 表订正 | **成立** | `proposal.md:18` 已为 `✅ ALLOW` / `❌ DENY（mv_cp_dest）`；实测 `WorkspacePolicy.assert_command_allowed('cp .env.example .env')` ⇒ ALLOW，`CommandGuard.check` ⇒ `DENY` / `last_reason='mv_cp_dest'`（两层各归其位，无错位） |
| B7 | Q9 机制归正 | **成立** | `design.md:231` 与 `reviews/grill-design.md:34` 均改为「附加根必然绝对路径、含 `/`，先命中 `command_guard.py:609` 的**整句正则**（pre-IR、`last_reason=denylist`、**不可被 allow 挂钩**），`_dest_is_sensitive` 根本没轮到」；实测 `cp x /srv/other/.env` ⇒ `DENY`/`denylist` ✓、`cp x ../config/.env` ⇒ `denylist` ✓ |
| B8 | 补 `W06:11` 等锚点 | **成立** | `design.md:324` 已列 ① `W06-security.md` 的 `:11` 与 `:35` **两处**（实测两行都写「58 个模式」，且 `DEFAULT_DENYLIST` 实测 **59**）、③ `interview-bullets/walkthrough.md:2481`（实测 = ``**文件**：`agent/workspace_policy.py:9-45` ``，现 `agent/workspace_policy.py:9-43`）、④ `:2499`（实测 = `` `is_denied()`（`:222-239`）执行两层匹配：``，现 `:316-338`）；`tasks.md:79` 同步为「五处」 |

## 三、R1 已判成立的 A 组与锚点：本轮未改坏

- **零代码改动**：`git show --stat 33c512a` = 6 份 `.md`（design / proposal / tasks / 两份 review / spec delta），`agent/**`、`scripts/**` 未动 ⇒ A1/A2/A3 的实现面与「不受影响清单」（`design.md:82`）逐字未变。
- **锚点重放**：对 6 份文档（design / proposal / tasks / 两份 spec delta / grill-design）的全部 `文件:行号` 引用做脚本重放——**138 次出现、71 个 distinct、0 越界、0 指向不存在的文件**。未解析的 3 处是参考仓简写（`policy_transforms.rs:30-35`、`protocol.rs:1077-1087`、`permissionRulesOps.ts:53-64`），R2 的 diff 未新增此类。
- **本 change 的 grill 正文判据**：实测 `grill_evidence_findings(reviews/grill-design.md)` = 13 条，全部是「缺 `## User Confirmation` 小节」+「Q<n> 未经用户确认」，**无任何 `来源:` 类红**（同行裸写法仍然 7/7 命中）✓。
- **新例子抽查（B2/B3 之外）**：Q3 `cp .env.example .env.local` ⇒ DENY `mv_cp_dest` ✓；Q5 `Edit` 路径的 `write.py:52-56` 文案与 `edit.py:55,67` 自读 ✓（读码）；Q6 `cat/grep/head/source/.` 全 ALLOW、`echo API_KEY=x >> .env` ⇒ `protected_redirect` ✓；Q7 四形态 `echo >>`/`tee`/`dd of=`/`install` ⇒ `protected_redirect`/`tee_target`/`dd_target`/`install_target`（**均可挂钩**）✓、五变体 `cp`/`mv` ⇒ `denylist` ✓；Q9 ✓（见 B7）。计数类断言复算：`DEFAULT_DENIED_PATTERNS` **32** 条（含 `/` **16** / 不含 `/` **16**）、`SENSITIVE_DOTDIRS` **9**、`DEFAULT_DENYLIST` **59** ⇒ 与 `design.md:241` 逐字相符。

## 四、规格完整性

- 6 条 Requirement 正文**首行均含 `SHALL`**（`specs/workspace-safety/spec.md:7,51,74,105,129`；`specs/configuration/spec.md:7`），无硬换行误报。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（隔离副本）⇒ **30 passed, 0 failed**。
- `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`（被审 worktree，只读）⇒ **OpenSpec artifact checks passed**，跑后 `git status --porcelain` 为空。

## 新发现

1. **（阻塞，中危）三处陈旧计数与 `design.md:169` 自相矛盾**：`design.md:238`、`design.md:289`、`tasks.md:69`。其中 `design.md:238`（Q11）与 `design.md:289`（R7）都在用户要读的停轮材料里，且 `:289` 还叠了 B4 漏改的「1 份」。**Why 阻塞**：R1 判 B2 阻塞的理由是「用户会照着错的例子做决定」，本条同类；且这是本轮修复自身造成的回归（改动前这三处是对的）。**How to fix**：把三处的「7 条」改「13 条」、「Q1–Q6」改「Q1–Q12」、`:289` 的「1 份」改「2 份」；顺手把 `tasks.md:3` 的「六条」改「十二条」。
2. **（阻塞，低-中危）`specs/workspace-safety/spec.md:122` 的 GIVEN 过宽**（见 B5 行），照字面不可机械判定。
3. **（非阻塞，可读性）`reviews/grill-design.md:32`（Q7 要点）的句子把 5 条命令与 4 个 Bash reason 并列**（「`Write config/.env` / `echo K >> …` / `tee …` / `dd …` / `install …` 实测均 DENY 且 reason 分别是 `mv_cp_dest` 之外的写目标类（`protected_redirect`/`tee_target`/`dd_target`/`install_target`）」）——`Write` 是文件工具层拒（无这几个 reason），读起来像 5 条各有 reason。建议拆成「四条 Bash 形态各有 …；`Write` 由文件工具层拒」。
4. **（非阻塞，观察）`CommandGuard` 的「可挂钩写目标判定面」口径有两种读法**：`design.md:73` 与 `spec.md:105` 用「敏感目标判定 / 重定向目标判定 / 动态目标判定」对应 `_check_target:930-938` / `_has_protected_redirect:976-993` / `_check_dynamic_target:940-960`，而 `tasks.md:39`（3.2）的收敛清单是 **6 个方法**（多 `_check_mv_cp:1106` / `_check_tee:1156` / `_check_dd:1139`），`cp x .env` 的 `mv_cp_dest` 正来自 `_check_mv_cp:1120`——即 `tasks.md:29`（2.4）断言会被 allow 挂钩的那条 reason 不在三面枚举里。`spec.md:105` 的否定从句（「不含整句 denylist 正则扫描」）使该面实际等于「除 pre-IR 扫描外的全部」，故不构成假承诺；但若日后有人按三面字面收敛，2.4 的断言会失去规格依据。建议把 `spec.md:105` 改成正列举（含 `mv`/`cp` 目标、`tee`、`dd of=` 等），或让 `tasks.md:39` 与规格同口径。


---

# R3 复审（revision 39d72c1）

## Reviewer

- **run id**: `grill-adversarial-r3-guard-write-allowlist-20261014`（独立零记忆对抗验证 subagent，**第 3 轮 / 封顶复审**；上游两组主张默认有错，逐条证伪；能实测的必须实测；全称/计数断言一律**计数**口径）
- **被审 revision**: `39d72c1`（作者修 R2 的三条；`git show --stat 39d72c1` = 5 份 `.md`，**零代码改动**）
- **上游**: 本文件上半部的 R1 报告（被审 `11f744e`）与 R2 复审（被审 `33c512a`）
- **约束遵守**: 被审 worktree **只读**（收尾 `git status --porcelain` 为空）；全部探针在 `/tmp/gwa-r3`（`git archive HEAD | tar -x` 重建、无 `.git`；后为跑 checker 才在 `/tmp` 内 `git init`）用项目 venv 解释器 `/home/happy/ax-wt/guard-write-allowlist/.venv/bin/python`；witnessloop 侧用其源码树 `/home/happy/witnessloop`（`uv run`，`PYTHONDONTWRITEBYTECODE=1`）
- **方法**: ① 实读 `git show 39d72c1` 全 diff 与 5 份改动文档；② 用 witnessloop 自己的 `grill_evidence_findings`（`/home/happy/witnessloop/src/witnessloop/evidence.py:109`）复算全部 63 份归档 `grill-design.md` + 本 change 自己那份（**计数口径**）；③ 隔离副本里直跑 `CommandGuard.check` / `WorkspacePolicy` 探针复测 R2 的每条命令级断言；④ 计数口径复核作者的「同类扫描」结论；⑤ 隔离副本跑 `openspec validate --all --strict` 与 `check_openspec_artifacts.py --base-ref origin/master --require-base`；⑥ 复核 R1/R2 已成立项是否被本轮改坏。

## Verdict

**PASS**

- **本轮要核的五条全部成立**。其中 R2 的第一条阻塞（陈旧计数）**已真收敛**：全库再无「7 条 … Q1–Q6」形态，剩余命中经**逐行计数**复核**全部是正确用法**。
- **本轮最重要的一项——作者新增的「前提订正」强断言——我独立复算，五个数逐一对上**：63 / 39 / 9 / 15，加粗 `来源` **3 份**（独占行 2 + 同行内联 1），且那 3 份**全部落在 src-only 桶**。
- **新增的安全缺口（`mv`/`cp` 的源位置与目标位置共用 `_check_target`）属实**，落点（Decision 2 的不受影响清单 + 新任务 2.5b）正确，我用探针复现了它的两个出口（`cp_source` / `mv_source`）。
- **无新的阻塞项**；两条**非阻塞**残留（N1/N2）建议顺手扫掉，但都不改变任何待拍板取舍。

## 一、R2 三条阻塞的复核（逐条）

| # | R2 的阻塞判定 | R3 结论 | 证据（当前树实测 / 计数口径） |
|---|---|---|---|
| ① | `design.md:238`/`:289`、`tasks.md:69` 仍写「7 条 … Q1–Q6」，与 `design.md:169`（13 条 / Q1–Q12）矛盾 | **成立（真收敛）** | 三处已全部改到位：`design.md:240`（原 `:238`）＝「source 判据 7/7 命中 … 共 **13 条**」+「**Q1–Q12** 未经确认」；`design.md:291`（原 `:289`）＝「63 份归档里 **39 份判绿**，含加粗 `来源` 的 **3 份** … 当前 **13 条** finding 全是『未确认』类」（叠的「1 份」也已改）；`tasks.md:70`（原 `:69`）＝「当前 **13 条** = 1 条『缺 `## User Confirmation` 小节』+ **Q1–Q12** 各 1 条」；`tasks.md:3` 的遗留「六条」改「**同一套 Q1–Q12，共十二条**」。**计数复核**：`grep -rn "六条\|7 条\|Q1–Q6\|Q1-Q6"` 全 change 目录 = **23 行命中**，其中 2 行是 `workflow-events.jsonl` 的追加式历史日志（`change_created`/`backlog_updated`，cli_written 通道）⇒ 余 **21 行**；逐行分类后**无一行是陈旧计数**（见第二节）。 |
| ② | `specs/workspace-safety/spec.md:122` 的 GIVEN 过宽（「一个被它命中的嵌套路径」照字面不成立），照字面不可机械判定 | **成立（已收窄到真实成立）** | `spec.md:122` 现为「**GIVEN** 一份 allowlist 与一个被它命中的**嵌套敏感路径**（如 `config/.env`），且该路径的 `cp` / `mv` 写目标**命中整句 denylist 正则扫描**」，并在 `:126` 加 NOTE「例外只适用**命中整句正则**的敏感名：同一 `config/` 下的非敏感目标（如 `config/notes.txt`）今天就是 `allow`」。**实测反例（隔离副本 `CommandGuard`）**：`cp x config/notes.txt` ⇒ **ALLOW** / `last_reason=None`、`cp x config/deploy.pem` ⇒ **ALLOW** / `None` —— 原 GIVEN 确实不成立，收窄后成立：`cp x config/.env` ⇒ **DENY / `denylist`**，我另测 `mv x config/.env` ⇒ **DENY / `denylist`**。 |
| ③ | `reviews/grill-design.md:32` 的 Q7 要点把 5 条命令与 4 个 Bash reason 并列；「可挂钩面」design/spec 三面 vs tasks 六方法口径不一 | **成立** | `reviews/grill-design.md:32` 已拆两组：**第一组（可挂钩，四条 Bash 形态各配各的 reason）** `echo K >> config/.env`⇒`protected_redirect`、`tee config/.env`⇒`tee_target`、`dd of=config/.env`⇒`dd_target`、`install x config/.env`⇒`install_target`，并写明「同组的 `Write config/.env` 由**文件工具层**拒（无上述 reason，属另一个判定层）」；第二组为 `cp`/`mv` 的 `denylist`。**四个 reason 我逐条实测命中**（见下）。口径已统一为**六方法正列举 + 三条排除项**：`design.md:75`（唯一定义）、`specs/workspace-safety/spec.md:105`（正则化改写）、`tasks.md:40`（3.2）。**六方法的 def/body 行号逐个核对全部命中**：`_check_target` `:930-938`、`_check_dynamic_target` `:940-960`、`_has_protected_redirect` `:976-993`、`_check_mv_cp` `:1106-1123` 体内、`_check_dd` `:1139-1155`、`_check_tee` `:1156-1168`。 |

## 二、「同类扫描」结论的计数复核

作者的「还剩 21 处命中、全部是正确用法」＝ 我实测的 **23 行** 减 `workflow-events.jsonl` 的 **2 行**历史日志。逐行分类（非抽样）：

- `reviews/grill-adversarial.md` **11 行** —— R1/R2 的历史正文（`git show` 确认本轮只在其尾部追加，未改已有内容），描述的是当轮被审 revision 的状态，**不得改**；
- `design.md` **7 行**（`:24`「六条结论」= Context 探针表 6 行、`:171`/`:240`「7 条 source 判据」= 7 条 Confirmed Decisions、`:179`/`:272`「立项原提 Q1–Q6」= 子集描述、`:270`「7 条 Confirmed Decisions」、`:274`「6 条新 Open Questions」= grill 补充的那六条）；
- `tasks.md` **2 行**（`:12`「立项原提 Q1–Q6」、`:14`「已移出六条」= 代码判定的六条）；
- `reviews/grill-design.md` **1 行**（`:22` 的编号provenance说明）。

⇒ **21 处全部是正确用法，无误判**，作者结论**属实**。**唯一口径缺口**：这条扫描的模式集是「六条 / 7 条 / Q1–Q6」，**不覆盖「加粗份数」家族**，故漏掉了 N1。

## 三、63 / 39 / 9 / 15 / 3 的独立复算（本轮最重要一项）

用 witnessloop 自己的 `grill_evidence_findings` 跑 `openspec/changes/archive/*/reviews/grill-design.md`：

| 量 | `design.md:171` 的断言 | **我的实测** | 判定 |
|---|---|---|---|
| 总份数 | 63 | **63** | ✓ |
| 零 finding（判绿） | 39 | **39** | ✓ |
| 只报「缺 `来源:`」 | 9 | **9** | ✓ |
| 报其它项 | 15 | **15** | ✓（39+9+15=63） |
| 用加粗 `来源` 写法 | 3（独占行 2 + 同行内联 1） | **3** —— 独占行 **2** = `2026-08-03-grill-confirmation-gate`、`2026-10-13-witnessloop-adoption`；同行内联 **1** = `2026-09-29-workflow-recursion-limit-default` | ✓（文件名也逐一对上） |
| 那 3 份是否 src-only | 全部 | **是**（三份都落在「只报缺 `来源:`」桶内） | ✓ |

**五个数逐一命中，这段「前提订正」属实**。另复算本 change 自己的报告：`grill_evidence_findings(reviews/grill-design.md)` = **13 条**（1 条缺 `## User Confirmation` + Q1–Q12 各 1 条），`## Confirmed Decisions` 恰 **7** 个 block、**零** `来源:` 类红 —— 与 `design.md:171`/`:240`、`tasks.md:70` 的陈述逐字相符。

## 四、新增安全缺口（`mv`/`cp` 源位置）的复核

作者断言：`mv`/`cp` 的**源位置**判定与目标位置共用 `_check_target`，若不区分则被豁免的 `.env` 会变成可外泄读源。**成立**，四项证据：

1. `agent/tools/command_guard.py:875`（`_check_ir_segment` 内）`source_verdict = self._check_target(name, source)`，`:878` 写 `last_reason = f"{name}_source"`；`:886` **同一个** `_check_target` 又判 **target**。
2. `:1060`（`_check_argv_segment` 内）对 `mv`/`cp` 的 source 同样调 `_check_target`，`:1062` 写 `f"{cmd_name}_source"`。
3. **隔离副本实测**：`cp .env /tmp/out` ⇒ **DENY / `cp_source`**、`mv .env /tmp/out` ⇒ **DENY / `mv_source`**；`assert_read_allowed('.env')` ⇒ DENY（`PermissionError`）。⇒ 这是「只放行写」在 Bash 层的第二条腿，漏了它 allow 会顺手在 `_check_target` 上打开读侧出口。
4. **落点已在且正确**：`design.md:84` 的「明确不受 allow 影响的面」逐条写明该机制与后果；`tasks.md:31`（新任务 2.5b）把它写成断言（护栏侧 `cp_source`/`mv_source` + 策略侧 `_env_source_is_credential`，后者在 `agent/workspace_policy.py:119`，实测对 `cp .env /tmp/out` 使策略侧 DENY）；`specs/workspace-safety/spec.md:105` 的排除项 ② 同口径。**无遗漏。**

## 五、R1/R2 已成立项未被本轮改坏

- **零代码改动**：`git diff --name-only 33c512a..39d72c1` = 5 份文档（design / tasks / 两份 review / spec delta），`agent/**`、`scripts/**` 未动 ⇒ A1/A2/A3 的实现面与「不受影响清单」逐字未变。
- **门禁全绿（隔离副本）**：`openspec validate --all --strict` ⇒ **30 passed, 0 failed**；`check_openspec_artifacts.py --base-ref origin/master --require-base` ⇒ **OpenSpec artifact checks passed**。
- **规格完整性**：7 条 Requirement（workspace-safety 5 ADDED + 1 MODIFIED，configuration 1）正文**首行均含 `SHALL`**（`specs/workspace-safety/spec.md:7,51,74,105,130`、`specs/configuration/spec.md:7`）。注意第 5 条因 `:120-126` 新增 Scenario 已从 R2 记的 `:129` 移到 **`:130`**，内容仍含 SHALL（无硬换行误报）。
- **R1 B3/B8 的 W06 锚点仍在**：`design.md:326` 与 `tasks.md:80` 均列 `docs/interview-script/walkthrough/W06-security.md` 的 `:11` 与 `:35` **两处**（实测该文件 `:11`/`:35` 都写「58 个模式」）✓。
- **被审 worktree 收尾干净**：`git status --porcelain` 为空。

## 新发现

### N1（非阻塞，低危）— `design.md:241` 的「加粗写法 2/63」未随同组口径统一

同一条 Q11 内三行之隔自相矛盾：`design.md:239` 写「使用**加粗 `来源` 写法**的共 **3 份**」，`design.md:241` 写「使用加粗写法的本仓归档实测只有 **2/63**（见上）」。作者本轮把 169/239/291/Decision 8/tasks:74 统一到「出现加粗 `来源` = **3 份**」口径，**漏了 `:241`**（`git show 39d72c1` 未触及该行）。

- **不判阻塞的理由**：① `design.md:239` 自身给了消歧句（「只数「`- **来源**:` 独占行」会得 2、按「出现加粗 `来源`」数得 3」），`:241` 的「见上」紧邻 `:240` 所描述的**独占行**形态，两个数都是实测值、读者能对上；② Q11 的待拍板取舍（报告用哪种写法 / 归因表是否给「格式选择导致的红」单列一类）**不因 2 或 3 改变**，不构成 R2 判阻塞时的那类「用户照着错材料做决定」。
- **修法**：把 `:241` 的 `2/63` 加口径限定（如「「`- **来源**:` 独占行」写法 **2/63**（宽口径 **3/63**）」），或直接写 3/63。

### N2（非阻塞，观察）— 冻结的 grill 报告里仍留 grill 自己的错数

`reviews/grill-design.md:52`（该报告「必须修改项 4」）写「**39 份零 finding 判绿**、14 份缺 `来源:`、10 份其它；只有 2 份用加粗续行写法」。我复算这组数是 **9 / 15 / 2**（见第三节），即 grill 原始报告自带的错数（R1/R2 已判「grill 错、作者对」，`design.md:171` 现载正确值）。

- **不判阻塞的理由**：`reviews/grill-design.md` 是**审阅者自己的决策记录**，其中「必须修改项」是历史审阅陈述；纠正它正是本对抗报告的职责，且纠正已被 R1/R2 落定。改写它等于重写审阅者结论（与本轮「不改已有 review 内容」的纪律同源）。
- **建议**（若下次触及该文件）：在 `:52` 后追加一句「（本组数已由对抗 R1/R2 订正为 9/15/2，见 `design.md:171`）」，不改原数。

## 必须修改项

**无。** N1 / N2 为非阻塞残留，建议在 `tasks.md` 0.5（把十二条答复落回 design）时顺手扫掉。
