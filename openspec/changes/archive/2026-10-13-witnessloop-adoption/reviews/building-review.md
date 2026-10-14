# building-review：witnessloop-adoption（阶段 A 影子接入）

- **change**: `witnessloop-adoption`（issue [#305](https://github.com/Xingkai98/asterwynd/issues/305)）
- **branch**: `witnessloop-adoption/2026-10-13`
- **审阅对象**: `da3fd4f`（`git merge-base HEAD origin/master`）`..a1a8444`（HEAD），17 个变更文件，1 个 change 目录
- **审阅者**: 独立零记忆 subagent（不继承任何开发上下文；本机被审 worktree 只读，唯一写入 = 本文件）
- **方法**: ① 逐条读产物**内容**（不是只看文件名）并与 `design.md` 定稿值做**程序化逐字段比对**；② 用 witnessloop 仓**本尊**（`uv run witnessloop`，非 PATH 上那份 0.1.0）在 `git archive | tar -x` 重建的**隔离副本**里独立复跑验收判据（含探针 diff 与负向对照）；③ 独立拉 CI 原始日志、`gh api` 保护规则、全量 pytest 与两处机械校验；④ 对外部实验结论（双守卫）**另搭一套 harness 重做**，不采信自述。

## Verdict

**PASS**

- 8 个审阅维度全部通过；`tasks.md` 中本 PR 范围内的**每一个** `[x]` 都有可复核的实体产物或可复现实测，**未发现虚勾**。
- 验收报告 `reviews/acceptance-stage-a.md` 的关键数字**逐条独立复现**（含判据 ①③④⑤⑦、CI `gate / check` 的 findings 原文、干净 runner 的 pytest 汇总、双守卫的三项结论）。
- 唯二 Issues 是两条**低危文档时态陈旧**（正文列出），不改变任何裁定、产物、判据或门禁行为，建议在 Z.5 归档收尾时顺手清；按本仓既有校准（`archive/2026-10-13-web-agent-group-chat/reviews/building-review.md` 的 R2 以「4 条 Low + 1 条 trivial 未修」判 PASS；本 change 的 `grill-adversarial.md` §五对同一「时态陈旧」类亦判非阻塞）**不构成阻塞**。

## 任务逐项验证

判据：本 change 的可实施范围 = `0.x` / `A.1–A.5` / `Z.1`、`Z.2`、`Z.4`。`B.*` / `C.*` / `N.*` / `Z.6` 全部标 `(post-merge)`、`Z.3`=本审阅、`Z.5`/`Z.7`=本审阅之后执行 ⇒ 均**不在**本轮判定范围，不计未完成。

| 任务 | 判定 | 独立核验依据 |
|---|---|---|
| 0.1 grill 决策记录（≥3 条） | ✅ | `reviews/grill-design.md` 存在；直接调用 `check_openspec_artifacts._extract_grill_decisions` ⇒ **7 条** `- **决策**:` |
| 0.2 七条 Open Question 停轮 | ✅ | 同文件 `_extract_open_question_indexes` ⇒ `['Q4','Q5','Q6']`（+ design 既有 Q1–Q3，导语注明连续不重号） |
| 0.3 逐条答复入 `## User Confirmation` | ✅ | `_extract_user_confirmation_indexes` ⇒ `['Q1'…'Q7']`；`_unconfirmed_open_questions` ⇒ **`[]`**（Q5 未漏） |
| 0.4 设计阶段审阅闭环 | ✅ | `reviews/grill-adversarial.md`（R3，PASS）+ `grill-adversarial-v1.md`（R1/R2 原记录）俱在；`tasks.md:12` 的 R3 结论与被审 revision `85bd816` 可查 |
| 0.5 七条落进 `## User Rulings` | ✅ | `design.md:250` 起 U1–U7 齐备；四项 policy 定案值与 `.witnessloop/policy.json` **逐字段相等**（见下） |
| A.1.1 判据 7 条 | ✅ | `acceptance-stage-a.md` §1 表；「原判据⑦ 已被证伪删去」的处置与 `design.md` Decision 7 同口径 |
| A.1.2 基线四项 | ✅ | 报告 §2；本轮 `gh api …/protection` 实况 = `contexts ["validate","benchmark-gate"]` / `strict true` / `approving 0` / `conv_resolution true` / `enforce_admins true` **逐项相同** |
| A.2.1 seed 仓外完整 policy | ✅ | `/tmp/witnessloop-asterwynd-policy.json` 存在（619B，21:16），**与入库 `.witnessloop/policy.json` 解析后完全相等** |
| A.2.2 四项自查 | ✅ | policy 内容逐项核对：无 `openspec/changes/archive/**`、glob = `reviews/*.manifest.json`、`changes_root` = `openspec/changes`、`required_artifacts` 五项、`require_change_for` 三条 |
| A.2.3 seed 不入库 | ✅ | `git ls-files \| grep -c witnessloop-asterwynd-policy` ⇒ **0**；worktree `git status --porcelain` 为空 |
| A.3.1 `init` + 真实可跑命令 | ✅ | `.github/witnessloop-tests.txt` = `uv run --extra dev pytest -q\n`（29 字节，`od` 逐字节核，**无 `<<REPLACE-ME>>`**，`grep -c` = 0）；该命令在干净 runner 上实跑过（CI 日志 4241 passed） |
| A.3.2 四产物 + `ci.yml` 未动 | ✅ | diff 恰为 4 个新文件 + 文档；`sha256(.github/workflows/ci.yml)` = `b5417b87…`，**与基线一致**（diff 中该文件不出现） |
| A.3.3 本地 `check` | ✅ | 本轮独立复跑：**2 项** findings，原文见下「复跑原始行」 |
| A.3.4 探针触发面 + 负向对照 | ✅ | 隔离副本独立重做三态：定制 policy **4 项**（含 `grill-adversarial` / `building` 两条）→ 换出厂 policy **2 项**（两条消失，与无探针基线逐字一致）。同时复现「只改 `agent/**`、无 change 目录」时的单条 `require_change_for` 报错形态 |
| A.4.1 plugin 装（本地） | ✅ | 上游 `plugin/` 四件俱在、仓根无 `.claude-plugin/marketplace.json`（`--plugin-dir` 是唯一路径）；本轮以 `--plugin-dir` 真跑一次，**plugin 的 hook 确实被加载并执行**（报错原文含 `${CLAUDE_PLUGIN_ROOT}/hooks/guard.sh`） |
| A.4.2 本地动作不进 diff | ✅ | `.gitignore:9` = `.claude/`；diff 无 `.claude/**` |
| A.4.3 装/卸/升级写进 guide | ✅ | `docs/development-guide.md` 新增节含安装（`--plugin-dir`）、升级、卸载三条与「没有落盘残留」的说明 |
| A.4.4 两层独立 | ✅ | `.github/workflows/witnessloop.yml` 全文 15 行，只 `uses: …gate.yml@v1`，**零 plugin 引用**；required 由 `platform_gate.py` 独占（本轮 `gh api` 复核未变） |
| A.4.5.1 前置核验 | ✅ | 独立复跑：`command -v witnessloop` ⇒ `/home/happy/.local/bin/witnessloop`、`--version` ⇒ `0.1.0`、`--help \| grep -c guard` ⇒ **0**、`witnessloop guard …` ⇒ **exit 2**（→ `guard.sh` 映射为放行 ⇒ 静默空转）；`guard.sh` 硬编码裸命令、退出码映射「1→2，其余→0」逐行核对属实 |
| A.4.5.2 合并语义与归属（实测） | ✅ | **本轮另搭 harness 重做**（`claude -p` 2.1.231 + `--plugin-dir` + `--permission-mode bypassPermissions`，plugin 侧用记录并可控退出的 `witnessloop` shim、settings 侧用可控 hook）：三次运行实测结论与报告一致 —— 两侧 hook **都执行**（断言 0 / 允许 0 三次都出现两条日志）、**并行**（settings 侧睡 4s 时 plugin 侧 0.200s 后就启动）、**任一 exit 2 即拦**（只允许侧通过时 Write 落盘成功，任一侧 exit 2 时文件未落盘）、报错只出阻断那一条 |
| A.4.5.3 两棵树各一次 | ✅（结构面） | `.claude` 在 building worktree **不存在**（`ls -d .claude` 报 No such file）；主 checkout `/home/happy/my-agent/.claude/settings.json` 的 `PreToolUse` matcher = `Write\|Edit\|Bash` → `scripts/workflow_guard.py`。主 checkout 上那一次真实运行的**逐字输出**未独立重跑（属报告自述），但两侧形态与工作树差异已静态核实，且本轮双 hook 并发行为已独立复现 |
| A.4.5.4 命名空间静态判定 | ✅ | `plugin/.claude-plugin/plugin.json` 的 `"name": "witnessloop"` ⇒ `witnessloop:grill` / `witnessloop:review-loop`，与仓内 `.claude/commands/` 不撞名 |
| A.5.1 PR 出现 `gate / check` | ✅ | PR [#308](https://github.com/Xingkai98/asterwynd/pull/308)（open，head = 本 HEAD `a1a8444`）；`gh api …/commits/a1a8444/check-runs` ⇒ `gate / check` 存在并跑出 `failure`（=K2 预期），`validate` / `benchmark-gate` / `windows-platform` 全 `success` |
| A.5.2 未进 required | ✅ | 本轮 `gh api …/protection` ⇒ `contexts` 仍为 `["validate","benchmark-gate"]` |
| A.5.3 逐项比对未变 | ✅ | 见 A.1.2 行；另 `ci.yml` sha256 前后同为 `b5417b87…` |
| A.5.4 guide 新增节 | ✅ | 含「不 required、只跑不拦」明写、本地 `check` 命令、`guard` 前置核验、装卸路径 |
| A.5.5 验收报告落盘 | ✅ | `reviews/acceptance-stage-a.md`（340 行）含 findings 原文、探针两次输出、基线比对表、双守卫三项结论、K1/K2 清单 |
| A.5.6 `reviews/` 一致状态 | ✅ | **计数口径**：`find …/reviews -name '*.manifest.json' \| wc -l` ⇒ **0**；`find … -name '*manifest*' -type f \| wc -l` ⇒ **0**。「一份都不落」与实际一致，K2 保持 2 条红 |
| A.5.6.1 条件式样板 | ✅ | 未启用（阶段 A 不验证 `manifest build` 通路），与默认处置一致 |
| A.5.6.2 执行者＝人在本地 | ✅ | `guard`/`check` 的产出均为本地命令；caller workflow 无产证据步骤 |
| A.5.6.3 中间轮产物处置 | ✅ | 走「最终版落规范名 `grill-adversarial.md`」这一支（`grill-adversarial-v1.md` 保留为 R1 原始证伪记录）；在当前「零 manifest」状态下孤儿规则不激活，理由成立 |
| Z.1 文档影响面 | ⚠️ 已做但**漏一处**（见 I1） | `docs/development-guide.md` / `docs/openspec-change-backlog.md` 已更新、`AGENTS.md` 未出现在 diff（符合「本 change 不改流程段」）；但**本 change 自己的 `README.md` 状态行未随之更新** |
| Z.2 覆盖重写当前规格 | ✅ | 程序化比对：占位 Requirement「dev-workflow-gate 当前为预留能力域」在 `openspec/specs/dev-workflow-gate/spec.md` **已不存在**（`'预留能力域' in text` ⇒ False，`'尚未接入'` ⇒ False）；delta 的 **10 条 ADDED 全部在位**且**正文逐字相同**（唯一差异是跨文件回指由「见 ADDED 的『…』Requirement」改为「见『…』Requirement」，属正确改写）；原「流程骨架与项目规则的承载分工」Requirement 保留 |
| Z.4 三处机械校验 | ✅ | 本轮独立复跑：`openspec validate --all --strict` ⇒ **30 passed, 0 failed**；`check_openspec_artifacts.py` ⇒ **`OpenSpec artifact checks passed`（exit 0）**；全量 pytest 见下「Test Results」（数字与报告不同但**原因已定位到环境**） |

**虚勾检查结论**：**0 条虚勾**。所有 `[x]` 都对应到磁盘上的实体（文件内容而非文件名）或本轮可复现的实测。

## 我独立复跑的原始关键行

**1. `check`（witnessloop 仓源码版，被审 worktree）**

```
$ cd /home/happy/witnessloop && uv run witnessloop check --root /home/happy/ax-wt/witnessloop-adoption
check：基线 origin/master...HEAD，17 个变更文件，1 个 change 目录
  change：witnessloop-adoption
check：未通过 ✗（2 项）
  1. openspec/changes/witnessloop-adoption：缺少 review manifest（审阅证据必须「报告 + manifest」成对，glob=reviews/*.manifest.json）
  2. openspec/changes/witnessloop-adoption：无 stage=grill 的 manifest（现有 stage：（无））——grill 决策记录必须有对应的审阅证据
EXIT=1
```

**2. 探针 + 定制 policy（隔离副本 `/home/happy/wl-review-a`，`origin/master` = base）**

```
check：基线 origin/master...HEAD，2 个变更文件，1 个 change 目录
check：未通过 ✗（4 项）
  3. openspec/changes/witnessloop-adoption：无 stage=grill-adversarial 的 manifest（现有 stage：（无））…
  4. openspec/changes/witnessloop-adoption：无 stage=building 的 manifest（现有 stage：（无））…
```

**3. 负向对照（同一副本、逐字覆盖为 `policy.default_policy_doc()`）**

```
check：未通过 ✗（2 项）      ← 第 3、4 条消失，与「无探针基线」逐字一致
```

**4. `init --dry-run`（`git archive origin/master` 副本 = 接入前状态）**

```
[dry-run] init 将创建（不落盘、不 commit）：
  + .witnessloop/policy.json
  + .github/workflows/witnessloop.yml
  + .witnessloop/init-manifest.json
  + .github/witnessloop-tests.txt        EXIT=0     ← 4 个、全为新增、零冲突
```

**5. CI 原始日志（`gh api …/actions/jobs/<id>/logs`，commit `691064c`）**

```
witnessloop check --root . --base "$BASE" --head HEAD
   Building witnessloop @ git+https://github.com/Xingkai98/witnessloop@ae992565ee2162e5b272af471e9adf895e7f83fb
check：未通过 ✗（2 项）
check：基线 origin/master...HEAD，17 个变更文件，1 个 change 目录
  1. …：缺少 review manifest（…glob=reviews/*.manifest.json）
  2. …：无 stage=grill 的 manifest（现有 stage：（无））…
##[error]Process completed with exit code 1.
4241 passed, 101 skipped, 30 warnings in 203.42s (0:03:23)      ← adopter tests 步照跑、未红
```

**6. 双守卫（本轮自建 harness，非引用报告）**

```
Run A（settings 放行 / plugin 拦）：shim.log 1 行 + settings.log 1 行 → 两侧都执行；文件未落盘；报错指名 [bash "${CLAUDE_PLUGIN_ROOT}/hooks/guard.sh"}]
Run C（两侧都拦）：两条日志俱在；文件未落盘（并集：任一 exit 2 即拦）
Run D（两侧放行 + settings 侧 sleep 4s）：settings_start=…087.3038，shim_start=…087.5035 ⇒ delta=0.200s ≪ 4s ⇒ 并行；文件落盘成功（x = 1）
```

**7. 计数口径（全称否定用计数）**

```
$ find openspec/changes/witnessloop-adoption/reviews -name '*.manifest.json' | wc -l   → 0
$ find openspec/changes/witnessloop-adoption -name '*manifest*' -type f | wc -l          → 0
$ ls openspec/changes/add-minimal-tui-runtime-view/reviews                               → No such file or directory（K1 无 reviews/）
```

**8. K1 事实口径复核**（在隔离副本里让 K1 进入 diff）⇒ 报 `缺少必需件 reviews` + `缺少 review manifest` + `无 stage=grill 的 manifest` ⇒ 报告 K1 行的描述成立。

## Issues

### I1 — [Low] change 入口文档 `README.md` 的状态行与实现现状矛盾（建议收尾顺手清）

- `openspec/changes/witnessloop-adoption/README.md:8` 现为「**状态：立项文档，未开始实现**；…待 tasks 0.4「设计阶段审阅闭环复跑确认」后开工」——而 `tasks.md:3` 已写「前置门（第 0 节）已完成…阶段 A 的写操作已落地」，`tasks.md:12` 的 0.4 已勾（R3 判 PASS），4 个接入产物 + 验收报告 + PR #308 均已存在。
- **成因**：`A.3.1`/`A.5.5` 等实现提交更新了 `tasks.md` 表头，未同步 change 自己的 `README.md`；`Z.1` 的文档影响面清单（guide / backlog / AGENTS.md）**不含 change 自身的 README**，故未被覆盖。
- **影响**：仅误导性描述（读者打开 change 目录看到的第一句话是「未开始实现」）；**不影响**任何门禁、产物、判据或 CI。归档后该行会与同目录 `tasks.md:3` 长期自相矛盾。
- **建议**：把状态行改为「阶段 A 已落地、待 PR 审阅（PR #308）」，与本 change `tasks.md:3` 同口径；一行改动。

### I2 — [Low] `design.md` 的 `Final confirmations` 仍写「待复跑」设计阶段审阅闭环（建议同批清）

- `openspec/changes/witnessloop-adoption/design.md:244` 现为「设计阶段审阅闭环已跑出**首轮** `reviews/grill-adversarial-v1.md`（CHANGES_REQUESTED…）；**待复跑**一轮确认收敛，最终版落到规范名 `reviews/grill-adversarial.md`」——而 `reviews/grill-adversarial.md` **已经是最终版且判 PASS**（`tasks.md:12` 的 0.4 记录 R3 PASS、被审 revision `85bd816`）。
- **成因**：与 `grill-adversarial.md` §五 R3-O1 同类（时态陈旧），但该处与 R3 点名的 `design.md:113/226/233/334`、`proposal.md:80` **不在同一批**——O1/O2 已由 `4e32bd9` 清理，`design.md:244` 因当时尚未跑完 R3 而未被列入。
- **影响**：同上，文档口径陈旧、不改变裁定；`design.md:243` 紧邻一行已写「确认门槛已满足」，两行互相打架。
- **建议**：改为「设计阶段审阅闭环已收敛并判 PASS（最终版 `reviews/grill-adversarial.md`；R1/R2 过程记录见 `grill-adversarial-v1.md`）」。

### 非阻塞观察（**不是**缺陷，供阶段 B/C 引用）

- **O1 `change_archived` 在 witnessloop 侧是死配置**：`policy.evidence.protected_write_event_types` 含 `change_archived`，而它在本仓 `scripts/flow-policy.json:38-42` 绑的是 `openspec/changes/archive/`，该路径按 Decision 3 **不在** `protected_paths` 里 ⇒ witnessloop 侧无消费方。属**白名单语义**（多余项不产生假红/漏报），本 change 的 `reviews/grill-adversarial.md` §五 R3-O3 已记录并判良性。**本轮核对属实**，无需改动。
- **O2 两个环境耦合的测试**（与本 change 无关，`git diff origin/master...HEAD -- tests/ web/ agent/` 计数 = **0**）：① `TestFindScopeRoot` 两条依赖「`/tmp` 不是 git 目录」，本机 `/tmp/.git` 是空目录（`ls -ld` 实测）⇒ 默认 basetemp 下红，`--basetemp` 移出 `/tmp` 后 5 passed（本轮复现）；② 反向的一条 `tests/agent/commands/test_session_workspace.py::test_session_workspace_add_nonexistent_path` **硬编码 `/tmp` 是 tmp_path 的祖先**，一旦把 basetemp 移出 `/tmp` 就必红（本轮实测 `已添加 workspace: /tmp`）——即两种 basetemp 取值各会红一批，**全量 pytest 的数字因此随 basetemp 取值变化**。建议另立 issue 让这两组用例与环境解耦，别在本 change 内动。
- **O3 浏览器用例 flake**：`tests/web_tests/test_reconnect_pending_interaction_browser.py::test_question_submit_when_ws_down_shows_feedback` 本轮在全量跑与单跑各红一次、第三次单跑通过（6.36s）。同 tree 在 CI（`691064c` 的 `validate` = success）绿 ⇒ **flake，不是本 change 引入**。
- **O4 `@v1` 是移动 tag**（R6，本 change 已登记）：CI 日志实测本次 `@v1` 解析到 `ae99256`（= witnessloop 仓当时 HEAD）。若日后要钉死，走 `--gate-ref`，属阶段 B/C 决策项。

## Test Results

| 项 | 本轮实测（独立复跑） | 与验收报告 |
|---|---|---|
| 全量 pytest（`uv run --extra dev pytest -q --basetemp=/home/happy/wl-basetemp-full`） | `2 failed, 4332 passed, 8 skipped, 109 warnings in 526.99s` | 报告为 `2 failed, 4331 passed, 9 skipped`（默认 basetemp）；**失败用例名不同**，两条均属环境：`test_session_workspace_add_nonexistent_path`（**由我搬 basetemp 引起**，默认 basetemp 下 1 passed）+ 上述 O3 的浏览器 flake（第三次跑通过）。⇒ 结论一致：**本 change 未引入失败** |
| 干净 runner 的 pytest（CI 原始日志，非自述） | `4241 passed, 101 skipped, 30 warnings in 203.42s`，exit 0 | 逐字一致 ✓ |
| OpenSpec strict validate | `Totals: 30 passed, 0 failed (30 items)` | 逐字一致 ✓ |
| artifact checker | `OpenSpec artifact checks passed`（exit 0） | 逐字一致 ✓ |
| `check`（本 change 自身） | 2 项（均为「缺 manifest」类，`EXIT=1`） | 逐字一致 ✓ |
| 探针触发面 / 负向对照 | 4 项 / 2 项 | 逐字一致 ✓ |
| CI（HEAD `a1a8444`） | `gate / check` failure（K2 预期）、`validate` success、`benchmark-gate` success、`windows-platform` success | 比报告更进一步：**在当前 HEAD 上复核**，不只 `691064c` |
| branch protection | `["validate","benchmark-gate"]` / strict true / approving 0 / conv_resolution true | 逐字一致 ✓；**`gate / check` 未进 required** |

## 结论

1. **Verdict = PASS。** 8 个维度逐条通过；`tasks.md` 本 PR 范围内所有 `[x]` **无虚勾**；验收报告的关键主张（判据 ①③④⑤⑦、CI 原文、干净 runner 数字、双守卫三项结论）**逐条独立复现**，唯一有出入的是全量 pytest 的计数，原因已定位到「basetemp 取值 × 两个环境耦合用例 + 一个 flake」，**与本 change 无关**。
2. **红线项全部成立**：`.github/workflows/ci.yml` sha256 = `b5417b87…` 逐字节未变；`validate` / `benchmark-gate` 未弱化；`gate / check` **未进 required**；`agent/**` / `scripts/**` / `web/**` 的改动计数 = **0**（故 `code_hits` 为空，两条 stage 判定本就不触发）；seed 未入库、无 `.dev/`/日志等仓外物混入。
3. **Security 面**：`protected_paths` 与事件类型表基本配套（唯一 `change_archived` 为白名单式良性死配置，见 O1）；policy 与 `design.md` Decision 1 的定稿 JSON **逐字段相等**；caller workflow 与 `init` 模板函数输出**逐字节相等**；测试执行点无哨兵残留。
4. **Issues 两条（均 Low、纯文档时态陈旧、建议 Z.5 收尾顺手清）**：I1 `README.md:8`、I2 `design.md:244`。二者都不改变任何裁定、产物、判据或门禁行为。
5. 本报告的审阅对象 = `da3fd4f..a1a8444`；被审 worktree 除本文件外**零写入**（实验全部在 `/home/happy/wl-*` 隔离副本与仓外路径内完成）。

## 后续（审后处置，由主 session 记录）

- I1 / I2 已在 **`75166de`** 修复：纯文档两条（`README.md:8` 的状态行、「未开始实现」→「阶段 A 已实现」；`design.md:244` 的「待复跑」→「已收敛」）。`git show 75166de` 可逐字复核，改动不触及任何产物、判据或门禁行为。
- 本报告的审阅对象是 `da3fd4f..a1a8444`；`75166de` 之后 manifest **已重建**，其 `head_sha` 因而是 `75166de`。⇒ 报告与 manifest 之间存在**一次纯文档 delta**，如实记此，不假装审阅覆盖了它。
