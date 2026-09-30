# Building Review: bash-command-guard-redesign (Round 3 — 终轮)

> 独立零记忆审阅者，未参与实现。HEAD = `752dcd5`，base = `origin/master`（`merge-base` = `e0e3c87`）。
> 本报告覆盖 Round 3 独立复核；Round 1/2 的结论摘要保留在「Round 1/2 修复复核」节（其完整原文见 git 历史 `752dcd5`）。

## Verdict

**CHANGES_REQUESTED**

Round 2 的 6 项复核清单**逐条实测全部到位**（重复 `-c` DENY、`-c` 作用域收窄、源位置跳过 flag、`redirects[]` 已消费、`uv run python -m pytest` ALLOW、tasks 58/61），Round 1 的必须成立项全部保持，且**端到端（policy+guard 两层）不存在任何「master 拦得住、HEAD 放行」的安全回归**（2683 条语料实测，放宽项全部是本 change 既定收口）。

但本轮发现 **两处 guard 层的真实回归（fail-open）**，都落在本 change 改动过的代码路径上、且**零测试覆盖**：

1. **（中高，回归）`launcher + script -c '<payload>'` 整族失明**——`nice script -c 'cp .env /tmp/leak'` 等 Round 1（`8e92640`）为 `DENY(launcher_payload)`，HEAD 变 `ALLOW`；由 Round 2 的 `c64dfe8` 删除 `_check_launcher_payload` 引入。master 的 guard 同样 `DENY`，属**本轮新引入的 guard 回归**。
2. **（中，回归）`watch -d cp .env ...` 类被 launcher 剥离器吞掉真实命令**——`watch -d cp .env /tmp/leak` 实测真实执行（已用 `script -qec` + 文件落盘证明），master guard `DENY`、HEAD `ALLOW`；由 Round 1（`8e92640`）从字面通道移除 `.env`/`.git` 源位置正则引入，`_LAUNCHER_OPTS_WITH_VALUE["watch"]` 把**不取值**的 `-d`（`--differences[=permanent]`，值为可选）当成取值选项，`-d` 吃掉了 `cp`。

两者当前都被 `workspace_policy` 通道的 `_env_source_is_credential` 兜住（所以端到端仍未放行），但：① 它们是 guard 自身契约的退化，② `_env_source_is_credential` 正是 D9 / task 2.7 计划移除的「第三处重复实现」，移除后两者即变成可利用的 fail-open，③ 全族无测试。

另有 1 项证据完整性问题（对拍报告口径）与若干可记债项，见 Issues。

## Round 1/2 修复复核（逐条实测）

`CommandGuard(workspace="/tmp/ws")`，HEAD=`752dcd5`。

### 清单 1：重复 `-c` 取最后一个 ⇒ DENY —— 已修好
```
deny(launcher_payload) | "script -c 'ls' -c 'cp x .env'"
deny(launcher_payload) | "script -c 'cp x .env' -c 'ls'"
deny(launcher_payload) | "script -c 'echo' -c 'cp x .env'"
deny(launcher_payload) | "script --command 'ls' --command 'cp x .env'"
```
对照组 `script -c 'echo hi'` → ALLOW 保持。

### 清单 2：`-c` 作用域按 launcher 收窄 —— 已修好
```
allow | "grep -c 'cp x .env' f"      allow | "grep -rn 'cp x .env' docs/"
allow | "cut -c 'cp x .env' f"       allow | "head -c 'cp x .env' f"
deny(cp_target) | 'ionice -c 2 cp x .env'      allow | 'ionice -c 2 cp x y'
```
（`grep -rn` 与 `grep -c` 同语义已一致放行，R2-2 已消。）

### 清单 3：敏感源躲在 flag 后 ⇒ DENY —— 已修好（仅裸 `cp/mv/install` 形态）
```
deny(cp_source)      | 'cp -r .env /tmp/x'      deny(cp_source) | 'cp -a .env /tmp/x'
deny(cp_source)      | 'cp -p .env /tmp/x'      deny(cp_source) | 'cp --preserve=all .env /tmp/x'
deny(mv_source)      | 'mv -f .env /tmp/x'      deny(install_source) | 'install -m 600 .env /tmp/x'
deny(cp_source)      | 'cp -r .git/config /tmp/x'
allow | 'cp -r src/ /tmp/x'   allow | 'mv -f old.txt new.txt'   allow | 'install -m 600 app.py /tmp/x'
```
（**但**：这一修法只覆盖「`cp/mv/install` 居段首」的形态；被 launcher 吞掉/包住的同类形态未被覆盖——见 Issue R3-2。）

### 清单 4：`redirects[]` 死字段已消除 —— 已修好
`_has_protected_redirect`（`:871-888`）现读 `analysis.redirects`，**不再调 `tokenize_command`**：
```
$ grep -n "tokenize_command" agent/tools/command_guard.py
155:（docstring）  190:_check_command_text（legacy `_check_argv` 通道）  542:def  660:（legacy 通道 `check()`）
```
即仅剩 legacy 通道两处（任务书要求允许保留），evaluator 路径已无重新切分。`cat payload > ~/.ssh/authorized_keys`、`echo X >> .env` 现由 `protected_redirect` 拦下（master 为 ALLOW），D2/D9 目标达成。

### 清单 5：`uv run python -m pytest tests/ -q` ⇒ ALLOW —— 已修好
```
allow | 'uv run python -m pytest tests/ -q'   allow | 'python3 -m pytest tests/'
allow | 'uv run python scripts/check_openspec_artifacts.py'
ask(launcher_prefix) | "weird sh -c 'cp x .env'"   ✅ 对照组仍在
```

### 清单 6：tasks 58/61，3 项 `⛔` 有处置 —— 已对齐
`grep -c '^- \[x\]'` = 58，`^- \[ \]` = 3（`3.4`/`4.6`/`4.8`，行 45/58/60），每项带 `⛔` 与文末「实现完成度」表格说明处置。

### Round 1 必须成立项（回归对照组）全部保持
```
allow | grep -rn "cp x .env" docs/   allow | echo "cp x .env"      allow | ls -la / git status / pytest -q
deny  | cp .env backup.env           deny  | mv .git/config config.backup   deny | cp /etc/passwd ./passwd.copy
deny  | cp .env /tmp/x               deny  | cp ~/.ssh/id_rsa /tmp/x
ask   | weird a b c d cp x .env      allow | cp .env.example /tmp/backup.txt
allow | cat <<'EOF'\ncp x .env\nEOF
```

## 独立复跑证据

### 1. attack suite（预期：未被 DENY 的 case 为空）
```
$ uv run python <probe>
total cases: 73
guard-deny cases NOT denied: []
sensitive-read NOT allow: []
```
`benchmarks/attacks/attacks.json` **只增不减**：`54 → 73`，`REMOVED ids: []`、`CHANGED ids: []`、`ADDED 19`（按 id 逐条比对 `git show origin/master:...`）。`test_attack_suite.py` 的 `is DENY` 未放宽；ASK 形态另立 `test_ask_suite.py`（两集经 `test_ask_cases_are_not_attack_cases` 断言不相交）。

### 2. 迁移对拍（旧 DENY ⊆ 新 DENY ∪ 新 ASK）
旧侧取自独立 worktree `git worktree add --detach /tmp/r3-old e0e3c87`（真实旧代码，非回退开关近似）。

- **本报告语料（attacks.json + 全部 4 个 change 测试文件的命令串 + 手工矩阵 + launcher 穷举，去重 2683 条）**：`旧 DENY → 新非(DENY|ASK)` 命中 29 条，**全部是既定收口**（28 条 `.env` 模板作源、1 条数据 heredoc），无一条是意外放宽。
- **端到端（`policy.assert_command_allowed` 先跑，再 `guard.check`）**：`master BLOCKED/ASK → HEAD EXECUTE` = **29 条，全部同上（既定收口）**。**未发现任何端到端安全回归**。
- 报告声明的对拍语料（355 条）复现：`violations: 0`（与 `migration-comparison.md` 一致）——但该语料**恰好不含**被放宽的模板源字符串，故其「新放宽 0 条」是语料选择产物（见 Issue R3-3）。

### 3. `.env` 三方矩阵（read / write / guard 目标位 / guard 源位）
```
name                     read   write  guard-tgt  guard-src
.env                     DENY   DENY   deny       deny
.env.local               DENY   DENY   deny       deny
.env.example             allow  allow  allow      allow
.env.sample              allow  allow  allow      allow
.env.example.local       DENY   DENY   deny       deny
.env.j2                  DENY   DENY   deny       deny
.env.example.bak         DENY   DENY   deny       deny
.env.production.sample   DENY   DENY   deny       deny
.envrc                   allow  allow  allow      allow
app.env                  allow  allow  allow      allow
```
四个通道一致；模板豁免未误放 `.env.example.local`。

### 4. 变异验证（改坏 → 变红 → 还原）
每项均 `cp` 备份还原，还原后 `git status --short` 干净。
- **变异 A（轮 2 改动路径）**：`_concealed_command_texts` 首行插 `return []`（`command_guard.py:331`）：
  `5 failed, 104 passed`（`test_script_dash_c_payload_is_judged`×3 + `test_repeated_command_option_judged`×2）。
- **变异 B（轮 2 改动路径，752dcd5）**：`_conceals_judged_command` 的解释器分支还原成 `if name in INTERPRETERS: return True`（`:364-367`）：
  `3 failed, 106 passed`（`test_python_dash_m_is_not_concealment`×3）。
- **变异 C（轮 2 改动路径）**：`_source_of`（`:400-424`）整体换成 `return args[0] if args else None`：
  `8 failed, 101 passed`（`test_flagged_sensitive_source_denied`×8）。
三次均确认断言非恒真、关键分支有真实测试锁定。

### 5. 全量 pytest
```
$ uv run pytest -q
2 failed, 3752 passed, 9 skipped, 80 warnings in 358.78s (0:05:58)
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
```
恰为任务书声明的两条已知本机环境失败（`/tmp` 是 git 仓库）。无其他失败。

### 6. 门禁
```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed (29 items)
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: bash-command-guard-redesign: review manifest missing: .../reviews/building-review-manifest.json   # exit=1
```
strict validate 绿。artifact checker 仅卡在 review manifest 缺失（须在 tasks.md 最终化后生成，属审阅闭环后续步骤）；tasks 58/61 中 3 项无 `(post-merge)` 标记的未勾项会在归档点被完成度门禁拦下（同 Round 1/2 Issue 7）。

## Tasks Verification

| 任务 | 状态 | 证据 / 差异 |
|---|---|---|
| 0.1–0.3, 1.1–1.9 | ✅ 真实实现 | grill 证据、IR 契约测试、`bash_ir.py` 非递归 `QueryCursor` 路径均在；`tests/agent/tools/test_bash_ir.py` 176 行。 |
| 2.1–2.6, 2.8, 2.10–2.12 | ✅ 真实实现 | 重定向 evaluator 读 `redirects[]`（`:871-888`）；`dd`/`tee` evaluator 在；`.env` 模板/凭据谓词单点定义（`workspace_policy.py:74-109`）；测试齐全。 |
| 2.7, 2.9（源位置/谓词迁移） | ⚠️ 部分 | 谓词单点已达成（`is_sensitive_dot_name`，三处消费）。但「源位置判定迁往 evaluator 并**移除** policy 侧正则」未达成：`8e92640` 删了旧两条正则、**又新增** `_env_source_is_credential`（`workspace_policy.py:116-127`，raw regex），构成「mv/cp 源是否敏感」的第 **3** 处实现（Issue R3-4，债务）。 |
| 3.1–3.3, 3.5–3.8 | ✅ 真实实现 | 三态裁决、`BashTool` 审批接线（`bash.py:151-170`）、`loop.py:180` 注入 handler；`test_bash_tool_ask.py` 覆盖 approved/denied/unavailable/no-handler/deny/allow 六路。 |
| 3.4 | ⛔ 未实现 | 执行中审批的 trace/quality 事件未进 trace；处置说明合理（可观测性增量，不改裁决）。 |
| 4.1–4.5, 4.7 | ✅ 真实实现 | 解析错误禁用 argv、命令替换递归、heredoc 绑定分流、动态写目标 deny/ask 分层；测试齐。 |
| 4.6 | ⛔ 降级 | `has_errors`/零宽 MISSING 已覆盖「解析不出」；说明合理。 |
| 4.8 | ⛔ 未实现 | 后端不可用语义属 `ExecutionBackend`，非护栏层；说明合理。 |
| 5.1–5.5 | ✅/⚠️ | 剥离到不动点、限定 ask、混淆归一化均在。但 5.2/5.6 的「launcher 族」覆盖面有盲点（Issue R3-1/R3-2）：`launcher+script -c` 与 `watch -d` 未被判定。 |
| 6.1–6.8 | ✅/⚠️ | 6.7 对拍报告已落盘（`reviews/migration-comparison.md`）；但报告语料过窄致「新放宽 0 条」结论失真（Issue R3-3）。6.1 的「矩阵每行测试名可被 `pytest --collect-only` 解析」无机械实现（Round 1 Issue 8，仍为债务）。 |
| 7.1–7.5 | ✅ | 7.3 本报告；7.4 门禁已跑；7.5 smoke 未在本轮复跑（非本轮范围）。 |
| 7.6, 7.7 | 未做（7.7 已标 post-merge） | 归档/backlog 收尾未执行（本报告在 working tree，`git status` 仅 `reviews/building-review.md`）。 |

## Issues

### R3-1（中高，回归 / fail-open）`launcher + script -c '<payload>'` 整族未被判定
- **证据**：`nice script -c 'cp .env /tmp/leak'` 端到端**真实执行并落盘**（`script -qec` 实测：`/tmp/leak_ns` 写入 `SECRET=leaked`）。判定历史：
  ```
                   master            ROUND1(8e92640)        HEAD(752dcd5)
  nice script -c 'cp .env /tmp/leak'   deny(denylist)   ->  deny(launcher_payload) -> allow
  env -i script -c 'cp .env /tmp/leak' deny(denylist)   ->  deny(launcher_payload) -> allow
  timeout 5 script -c 'cp .env /tmp/leak' deny(denylist)->  deny(launcher_payload) -> allow
  ```
  即 **Round 1 已修好、Round 2 又改坏**（对拍 753 条 launcher 语料：`ROUND1 DENY → HEAD 非(DENY/ASK)` 命中 36 条，全为此族）。
- **机制**：`c64dfe8` 删除 `_check_launcher_payload` 及其两处调用点，新逻辑只保留 `_concealed_command_texts`（`command_guard.py:730`），而它在 `:333` 取 `argv[0]` 作用域——`argv[0]='nice'/'env'/'timeout'` 时 `_LAUNCHER_COMMAND_OPTION.get(name)` 为空 → 整族返回 `[]`。随后 `_strip_to_fixpoint`（`:291-311`）把 `script` 的 `-c` 值推为**带引号的新 head**（`["'cp .env /tmp/leak'"]`），而 `_conceals_judged_command`（`:356`）跳过引号 token、`name = rest[0].rsplit(...)` 因引号不匹配任何受判命令 → ALLOW。Round 1 的 post-strip `_check_launcher_payload` 正是补这个洞的。
- **性质**：**本 change 引入的 guard 回归**（master guard 也 DENY）。端到端目前被 `workspace_policy._env_source_is_credential` 兜住（`.env` 源恰好被其正则命中），故暂不可直接利用；但该兜底正是 D9/task 2.7 计划移除的实现，且 `cp -r .env`（flag 前置，policy 正则捕获到 `-r` 不敏感）在该族下 master/HEAD 同为 EXECUTE——即移除 policy 兜底后即变可利用。全族**零测试覆盖**（`tests/` 无 `nice script`/launcher+script 用例；diff 确认 Round 1 亦未覆盖，故 Round 2 静默丢失）。
- **建议**：恢复「剥离后若 head 是 launcher 命令选项的值则 dequote 后按命令行判定」（即 Round 1 的 post-strip 路径），或让 `_strip_to_fixpoint` 在把命令选项值推为 head 时直接 dequote，并补该族回归测试。

### R3-2（中，回归 / fail-open）launcher 剥离器把「不取值的选项」当取值，吞掉真实命令
- **证据**：`watch -d cp .env /tmp/leak` **真实执行并落盘**（`script -qec "timeout 3 watch -d cp .env /tmp/leak"` 实测 `/tmp/leak1` 写入 `SECRET=leaked`；`watch --help` 确认 `-d, --differences[=<permanent>]` **值可选**）。判定：`master guard=DENY(denylist)` → `HEAD guard=ALLOW`；同族 `chrt -p cp .env /tmp/x`、`strace -o cp .env /tmp/x`、`stdbuf -i cp .env /tmp/x`、`flock -w cp .env /tmp/x`、`unshare --propagation cp .env /tmp/x`、`xargs -I cp .env /tmp/x`、`ltrace -o/-s cp .env /tmp/x` 等 **30 条** master-DENY → HEAD-ALLOW（974 条 launcher×写命令语料）。其中真正可执行的是 `watch -d`（其余选项确需数值，误吃后程序报错不执行）。
- **机制**：`_LAUNCHER_OPTS_WITH_VALUE["watch"] = {"-n", "-d"}`（`command_guard.py:69`）把**不取值**的 `-d` 列为取值选项 → `_strip_to_fixpoint`（`:296-306`）对 `watch -d cp x .env` 的 index 多加一跳，`cp` 被当 `-d` 的值跳过，`rest` 剩 `['x','.env']` → head 未知且其后无受判命令 → ALLOW。该文件 `:59-61` 的注释本就写明「over-stripping can swallow the real command (unsafe)」——此处即反例。
- **性质**：**本 change 引入的 guard 回归**（`8e92640` 从字面通道移除 `.env`/`.git` 源位置正则后，IR evaluator 成为唯一防线，而它在此形态失明）。端到端被 policy 兜住，同 R3-1。
- **建议**：把 `-d` 移出 `watch` 的取值集（只留 `-n`）；并复核各 launcher 是否存在同类「值为可选/可附着」的选项。补 `watch -d cp <敏感>` 回归测试。

### R3-3（中，证据完整性）对拍报告「新放宽 0 条」是语料选择产物，断言口径强于实测
- **证据**：`reviews/migration-comparison.md:9-16` 声明语料 = attacks.json + `test_command_guard.py` + `test_workspace_policy.py`（355 条），结论 `旧 DENY ⊆ 新 DENY ∪ 新 ASK : PASS (violations: 0)`。复现该语料得同样结果，但该语料**不含**被放宽的模板源字符串。改用「attacks.json + 全部 4 个 change 测试文件」语料（630 条）后，属性出现 **3 条违反**：`cp .env.example /tmp/backup.txt`、`cp .env.sample docs/`、`mv .env.template /tmp/x`（旧 DENY → 新 ALLOW）。
- **机制**：task 6.7 / spec 把断言写成「旧 DENY ⊆ 新 DENY ∪ 新 ASK」，但本 change 的既定目标是**放宽**模板源（Q3 拍板），该属性字面上不可能对全语料成立。报告用窄语料规避了这一点。
- **性质**：非安全缺陷（这 3 条是 Q3 的既定收口），但**验收证据的口径不诚实**：`PASS (violations: 0)` 会让人以为不存在任何旧 DENY→新 ALLOW 转变。
- **建议**：在报告中显式列出「既定放宽清单」（模板源/数据 heredoc）并声明断言为「旧 DENY ⊆ 新 DENY ∪ 新 ASK ∪ 既定放宽」，或把语料扩到含模板源形态。属归档前应修正的证据问题。

### R3-4（低，债务）`mv/cp 源是否敏感` 存在第 3 处实现（D9 未达成）
`workspace_policy.py:116-127` 的 `_ENV_SOURCE` + `_env_source_is_credential`（raw regex，仅 policy 通道）+ `command_guard._source_of`（IR argv，:400-424）+ `:212-213` 两条窄正则。task 2.7/2.9 的目标是迁往 evaluator 消除双实现，本轮方向上相反（新增一处）。已由 Round 2 记入（R2-6）；建议登记 `docs/known-debt.md`，不阻塞。附注：`_env_source_is_credential` 在 `grep -rn "cp .env" docs/`、`echo "cp .env"`（数据）上仍误拒（POLICY-DENY vs guard allow），与本 change「引号内是数据」原则不符，属既有债务。

### R3-5（低，spec 对齐）spec 声明 launcher 族「SHALL 返回 ask」，实现返回 DENY
`specs/workspace-safety/spec.md:152` 与 `:271` 写 `nsenter -t 1 cp x .env` / `watch -n 1 cp x .env` / `setarch x86_64 cp x .env` / `flock /tmp/l cp x .env` **SHALL 返回 ask**（理由写「未识别前缀」）。实测这 4 条均为 **DENY**（它们是 `_LAUNCHERS` 已知成员，被剥离后直接判定 `cp x .env` → deny）。实现比 spec 更严（更安全），但：① spec 的 SHALL 与实现不符，② 测试仅断言同族**无害目标**（`nsenter -t 1 cp x y`）为 ALLOW（`test_guard_three_state.py:120-121`），没有任何测试锁定「敏感目标 → ask」，故 task 5.6 的「SHALL ask」实际未落实。建议把 spec 该句改为「SHALL 被拒绝或要求审批」，或补 ask 断言。方向安全，不阻塞。

### R3-6（低，残余）Round 1/2 未清项
- 归档点完成度门禁：tasks 58/61，3 项 `⛔` 无 `(post-merge)` 标记，归档点会红（同 Round 1/2 Issue 7）；review manifest 未生成。
- 能力范围矩阵的「测试名可被 `pytest --collect-only` 解析」仍无机械校验（6.1，Round 1 Issue 8）。
- 护栏不覆盖凭据变体的 Bash **读**位（`cat .env.local` 经护栏 → allow，而 `assert_read_allowed(".env.local")` → DENY），spec「读、写…SHALL 被拒绝」未声明该分工（Round 1 Issue 6）。

## Test Results

```
$ uv run pytest -q
2 failed, 3752 passed, 9 skipped, 80 warnings in 358.78s (0:05:58)
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
```
= 已知本机环境失败（`/tmp` 为 git 仓库），无其他失败。

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: ... review manifest missing (exit=1)
```

覆盖弱化检查：攻击集只增不减（54→73，0 修改/删除）；`test_attack_suite.py` 的 `is DENY` 未放宽；ASK 用例另立 `test_ask_suite.py` 且断言与攻击集不相交。变异 A/B/C 各命中 5/3/8 条测试。**未发现为过测试而放宽断言。**

## 结论

- **Round 2 的 6 项复核清单逐条复核到位**（重复 `-c`、`-c` 作用域、flag 后源、`redirects[]` 消费、`python -m pytest`、tasks 58/61），Round 1 必须成立项全部保持。
- **端到端无安全回归**：2683 条语料上 master 拦得住、HEAD 放行的仅 29 条，全部是 Q3/D4 的既定收口（模板源、数据 heredoc）。攻击集 73/73 DENY，全量 pytest仅 2 条已知环境失败，strict validate 绿。
- **但 guard 层新引入两处回归（R3-1 中高、R3-2 中）**：均落在本 change 改动过的代码路径上、零测试覆盖、且被 `_env_source_is_credential` 这层 D9 计划移除的实现兜住——移除兜底后即变可利用。二者修法都很小（恢复 Round 1 的 post-strip payload 判定；`watch` 取值集去掉 `-d`），建议合并前修。
- 另有一项证据口径问题（R3-3：对拍报告「新放宽 0 条」为语料选择产物）建议归档前如实化。
- **R3-4（第 3 处源位置实现）、R3-5（spec ask/deny 措辞）、R3-6（门禁/manifest/读位）可记为债务或后续 issue**，不阻塞实现正确性。
- 综合判 **CHANGES_REQUESTED**：无「护栏整体可被无保护绕过」级别的阻塞缺陷，但 R3-1 是 Round 2 修复自身引入的同族 fail-open 回归，R3-2 是 Round 1 移除字面通道时未覆盖的 launcher 形态，均属本 change 范围内应修项。
