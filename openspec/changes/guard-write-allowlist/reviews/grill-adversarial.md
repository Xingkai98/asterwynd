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
