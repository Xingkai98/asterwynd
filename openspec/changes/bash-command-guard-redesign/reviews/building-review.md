# Building Review: bash-command-guard-redesign (Round 2)

## Verdict
CHANGES_REQUESTED

Round 1 的四个修复点**逐条实测确认已修好**（`script -c '<cmd>'` 单 c → DENY、`weird a b c d cp x .env` → ASK、`cp ~/.ssh/id_rsa /tmp/x` → DENY、`cp .env.example /tmp/backup.txt` → ALLOW），且 round-1 点名的回归对照组全部保持。安全底线成立：攻击集 73/73 DENY、迁移对拍零违规、全量 pytest 仅 2 条已知环境失败。

但本轮**新发现两处由 round-1 修复自身引入的问题**，外加一处修复未覆盖的 fail-open：

1. **（高，fail-open）重复 `-c` 未被判**：`script -c 'benign' -c 'cp x .env'` 端到端 **ALLOW**。真实 `script` 执行**最后一个** `-c`（已用 util-linux 2.39.3 实测：`script -q -c 'echo FIRST' -c 'echo SECOND' /dev/null` 只输出 SECOND），护栏只判**第一个** `-c` 的值。修复的 `_concealed_command_text` / `_strip_to_fixpoint` 对单 `-c` 生效，对重复形式失明。
2. **（中，误报）`-c` 被全局当作「值是命令」**：`_LAUNCHER_OPTIONS_WHOSE_VALUE_IS_THE_COMMAND` 在**每条命令**的 argv 上被咨询，于是 `grep -c 'cp x .env' f`、`cut -c`、`head -c`、`tail -c`、`sort -c`、`ls -c`、`git log -c` 一类「`-c` 的值是数据」的形态一律被 DENY——与本修复自己的 docstring（「quoting a command as data must not match」）和 round-1 必须成立项 `grep -rn "cp x .env" docs/` → ALLOW 的「引号内是数据」原则直接冲突（同一语义 `grep -rn` 放行、`grep -c` 拒绝）。
3. **（中，覆盖缺口）新增的源位置判定被一个前导 flag 击穿**：`cp -r .env /tmp/x`、`cp -a .env`、`cp -p .env.local`、`mv -f .env`、`install -m 600 .env` → 端到端 **ALLOW**。新源判定只取 `rest[1]`，`rest[1]` 以 `-` 开头即整条跳过。

任务勾选仍是 4/61，归档点完成度门禁必红（与 round-1 Issue 7 相同）。

## Round 1 修复复核

逐条复跑（HEAD = `8e92640`，`CommandGuard(workspace="/tmp/ws")`）：

### 修复点 1：`script -c '<cmd>'` 仍 allow → 应为 DENY
**已修好（单 `-c`）。**
```
$ uv run python /tmp/r2_check.py
1a script -c                                  -> deny  reason=launcher_payload   | script -c "cp x .env"
1b script -q -c                               -> deny  reason=launcher_payload   | script -q -c "cp x .env" /dev/null
1c script -c sh                               -> deny  reason=launcher_payload   | script -c "sh -c 'cp x .env'"
1d ctrl script -c echo                        -> allow reason=None               | script -c "echo hi"
script --command                              -> deny  reason=launcher_payload   | script --command 'cp x .env'
```
对照组 `script -c 'echo hi'` → ALLOW 保持。
**但重复 `-c` 仍 fail-open（见 Issue R2-1，本轮的阻塞项）**：
```
multi -c script              allow | script -c 'ls' -c 'cp x .env'
multi -c script2             allow | script -c 'cp x .env' -c 'ls'
multi -c script3             allow | script -c 'echo' -c 'cp x .env'
$ script -q -c 'echo FIRST' -c 'echo SECOND' /dev/null   # 实测真实语义
SECOND^M                                                  # 只有最后一条 -c 被执行
```
（注意 `script -c 'cp x .env' -c 'ls'` 被 DENY 是**判了第一个 `-c`** 的偶然结果；真实执行的是 `ls`，判定与执行错位，方向恰好安全，但同样说明「判第一个、执行最后一个」。）

### 修复点 2：`weird a b c d cp x .env` 仍 allow → 不应 allow
**已修好。**
```
2  weird a b c d cp x .env        -> ask  reason=launcher_prefix
2b weird cp x .env                -> ask
2c weird a b c cp x .env          -> ask
2d nohup weird a b c d e cp x .env -> ask
```
滑窗已扫描整个 remainder，且只认未加引号 token。变异 B（把 `_conceals_judged_command` 还原成 `rest[1:5]` 窗口）→ 2 条测试变红，确认断言非恒真。

### 修复点 3：`cp ~/.ssh/id_rsa /tmp/x` 应 ask → 应为 DENY
**已修好。**
```
3  cp ~/.ssh/id_rsa /tmp/x   -> deny  reason=denylist
   cp ~/.aws/credentials /tmp/x -> deny
```
`~` 已移出动态标记集（`bash_ir._is_dynamic`），静态可判的敏感路径回到 DENY 通道。变异验证（改动 `bash_ir` 的 `~` 处理）由 test_bash_ir 覆盖。

### 修复点 4：`cp .env.example /tmp/backup.txt` 应 ALLOW
**已修好。**
```
4  cp .env.example /tmp/backup.txt -> allow reason=None
5f cp x .env.example               -> allow reason=None
   cp .env.sample docs/            -> allow
   mv .env.template /tmp/x         -> allow
```
两条 `cp <任何 .env*>` 源位置正则已收窄；`.env` 家族的源改走共享谓词 `_env_source_is_credential`。
**但源位置判定仍是「regex on raw text」+「IR argv[1]」两份实现，且 IR 那份有一个前导 flag 的洞（Issue R2-3）。**

### 修复点 5（回归检查）：修复 1–4 有没有引入别的问题
**必须成立的行为全部保持：**
```
5a grep -rn "cp x .env" docs/  -> allow   5b echo "cp x .env"        -> allow
5c cp .env backup.env          -> deny (cp_source)   5d mv .git/config config.backup -> deny (mv_source)
5e cp /etc/passwd ./passwd.copy-> deny (denylist)    5g cp .env /tmp/x        -> deny (cp_source)
5h ls -la                      -> allow   5i git status -> allow   5j pytest -q -> allow
```
**但修复引入了两处新问题**（round-1 未覆盖的相邻形态），即 Issue R2-2（`grep -c` 类误报）与 Issue R2-3（前导 flag 击穿源判定）：
```
grep -c 'cp x .env' docs/   -> deny  (旧的必须成立项是 grep -rn → allow；同一语义两种答案)
cut -c 'cp x .env' f        -> deny
head -c 'cp x .env' f       -> deny
git log -c 'cp x .env'      -> deny
```
```
cp -r .env /tmp/x   -> allow (端到端 allow)    cp -a .env /tmp/x -> allow
cp -p .env.local /tmp/x -> allow              mv -f .env /tmp/x -> allow
install -m 600 .env /tmp/x -> allow
```
两者均由**本轮新加的代码路径**触发，且旧实现（`6153d8f` / `e0e3c87`）在这些输入上同为 allow——属「新机制宣称覆盖但实际未覆盖/误覆盖」，不是回归到更差，但与本 change 自订目标不符。

## 独立复跑的证据

### 1. 攻击集拦截数（预期：空）
```
$ uv run python /tmp/r2_check.py
total cases: 73
NOT DENIED: []
sensitive-read NOT ALLOW: []
```
既有 54 条**只增不减**（逐 id 比对）：
```
$ python3 <attacks.json diff>
old: 54 new: 73
REMOVED ids: []   CHANGED ids: []   ADDED count: 19
```

### 2. 迁移对拍 `旧 DENY ⊆ 新 DENY ∪ 新 ASK`
在 `git worktree add --detach /tmp/r2-old e0e3c87` 的独立旧代码 worktree 上跑同一批命令（attacks.json 全量 + `test_command_guard.py` 命令串 + 迁移用例，共 80 条），与本 HEAD 逐条比较：
```
$ uv run python /tmp/r2_corpus.py ...（旧/新两侧）+ diff
common commands: 61 | old-only: []
VIOLATIONS 旧DENY -> 新非(DENY|ASK): 0
TIGHTENED 旧ALLOW -> 新DENY/ASK: 7   # 全部是本 change 既定收口（动态目标/解析错误 → ask）
```
**违反项：空。** 富语料（61 条 .env/launcher/heredoc 组合）同样 0 违规；新收口的 9 处与 design 的收紧集合一致。

### 3. `.env` 三方矩阵
```
name                   read   write  guard(cp->tgt) guard(cp src->)
.env                   DENY   DENY   deny           deny
.env.local             DENY   DENY   deny           deny
.env.example           allow  allow  allow          allow
.env.sample            allow  allow  allow          allow
.env.example.local     DENY   DENY   deny           deny
.env.j2                DENY   DENY   deny           deny
.envrc                 allow  allow  allow          allow
app.env                allow  allow  allow          allow
```
凭据变体两侧全拒、模板放行、`.env.example.local` 未被模板豁免误放。文件工具读/写与护栏写目标判定**三者一致**。
（残留：`cat .env.local` 经护栏 → allow，读经 Bash 仍不覆盖凭据变体读位——round-1 Issue 6，spec 未声明该分工。）

### 4. 变异验证（改坏 → 变红 → 还原）
- **变异 A（本轮新修逻辑）**：把 `_concealed_command_text` 改成恒返回 `None`（`command_guard.py:320-334`）：
  ```
  FAILED TestLauncherNoFailOpen::test_script_dash_c_payload_is_judged[script -c "cp x .env"]
  FAILED ... [script -c 'cp x .env'] / [script -q -c 'cp x .env' /dev/null]
  3 failed, 156 passed
  ```
- **变异 B（本轮新修逻辑）**：把 `_concealed_command_text` 的「整段扫描」还原成 round-1 的 `rest[1:5]` 滑窗：
  ```
  FAILED TestLauncherNoFailOpen::test_filler_tokens_do_not_hide_the_command[weird a b c d cp x .env]
  FAILED ... [weird a b c d e f g mv x .env]
  2 failed, 82 passed
  ```
- **变异 C（round-1 既有谓词，附加）**：`_env_source_is_credential` 首行插入 `return False`：
  ```
  FAILED test_workspace_policy.py::TestCommandPolicy::test_denylist_rejects_sensitive_file_copy_or_move[cp .env backup.env]
  FAILED ... [mv .env backup.env] / [mv .git/config config.backup]
  5 failed, 2511 passed
  ```
三次均 `git checkout --`（用备份还原）后重跑全绿，`git status --short` 仅剩未跟踪的 `reviews/building-review.md`。**断言非恒真、关键分支有真实测试锁定。**

### 5. 全量 pytest
```
$ uv run pytest -q
2 failed, 3727 passed, 9 skipped, 80 warnings in 348.65s (0:05:48)
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
```
恰为任务书声明的两条已知本机环境失败。/tmp 是 git 仓库干扰，无其他失败。
change 专属测试文件：`573 passed`（test_command_guard / test_bash_ir / test_guard_three_state / test_bash_tool_ask / test_workspace_policy / test_ask_suite / test_attack_suite）。

### 6. 门禁
```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed (29 items)
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: bash-command-guard-redesign: review manifest missing: .../reviews/building-review-manifest.json   # exit=1
```
strict validate 绿。artifact checker 仅卡在 **review manifest 缺失**——按 AGENTS.md 该 manifest 须在 tasks.md 最终化（含归档 move）之后生成、绑定 PASS verdict，属审阅闭环后续步骤；但注意 tasks.md 现仅 4/61 勾选，**归档点完成度门禁会先红**（Issue R2-7）。

## Tasks Verification

tasks.md **仍仅 4 条勾选**（0.1/0.2/0.3/1.1），其余 57 条为 `[ ]`，但绝大多数 `[ ]` 任务实际已实现（round-1 逐条核对结论仍然成立，未因本轮修复而变化）。关键差异点：

| 任务 | 状态 | 证据 / 差异 |
|---|---|---|
| 2.7 | **仍未完全落地** | 源位置判定仍是「workspace_policy regex + evaluator argv」两份实现（`workspace_policy.py:116-127` 新增 `_env_source_is_credential`，属**新增的第三处**判定），未按 D9/task 2.7 迁往 evaluator；且 evaluator 那份只判 `rest[1]`，被前导 flag 击穿（Issue R2-3）。具体误伤 `cp .env.example /tmp/backup.txt` 已修复（Q 要求达成），但实现路径与 D9「同一语义单实现」相悖。 |
| 2.1 | 仍未完成 | 重定向判定仍走 `_has_protected_redirect` + `tokenize_command`（`command_guard.py:859-878`，tokenize 在 `:868`），IR 的 `redirects[]` 仍**零消费者**（`grep -rn "\.redirects" agent/` 无命中）。数据 heredoc 正文含字面 `>` 仍误报 DENY（详见 Issue R2-5）。 |
| 6.6 | 未完成 | 无「从原文重推 argv 的入口数 == 1」断言；`tokenize_command` 在 `:188/:619/:868` 仍被调用。 |
| 6.1 | 未完成 | 无 `pytest --collect-only` 矩阵自校验测试。 |
| 6.7 | 部分 | 回退开关在；对拍报告仍无落盘文件（round-1 Issue 5 未清）。 |
| 5.2 | 部分（新增缺口） | 单 `-c` 覆盖；重复 `-c` 未覆盖（Issue R2-1），且 `-c` 全局拦截引入误报（Issue R2-2）。 |
| 7.3 | 本报告 | — |
| 7.4–7.6 | 未做 | 归档/backlog 收尾未执行。 |

## Issues

### R2-1（高，fail-open）重复 `-c` launcher payload 未被判定 — 真实 `script` 执行最后一个 `-c`
- 证据：`script -c 'ls' -c 'cp x .env'` → **ALLOW**（`reason=None`），端到端也 ALLOW；`script -q -c 'echo FIRST' -c 'echo SECOND' /dev/null` 实测只执行 SECOND（util-linux 2.39.3）。
- 机制：`_concealed_command_text`（`command_guard.py:320-334`）与 `_strip_to_fixpoint` 的 `-c` 分支（`:296-302`）都只处理**第一个** `-c`；第一个值经 strip 后成为新 head（带引号 → 被判为 unknown token），第二个 `-c` 及其值被推到 head 之后，`_conceals_judged_command` 因该值带引号而跳过，最终 ALLOW。
- 与修复自陈矛盾：`_check_launcher_payload` docstring 写「Any such option left in the stream is judged」，此处即为反例。
- 性质：旧实现同样 allow（甲类），但**这正是本轮修复宣称收口的机制**，且无测试覆盖重复形式。属安全模块的 fail-open，应修。

### R2-2（中，误报）`-c`/`--command` 在**所有**命令上被当作「值即命令」
- 证据：`grep -c 'cp x .env' docs/` → **DENY(launcher_payload)**；`cut -c`、`head -c`、`tail -c`、`sort -c`、`ls -c`、`git log -c`、`echo -c` 同；而 round-1 必须成立项 `grep -rn "cp x .env" docs/` → ALLOW。
- 机制：`_concealed_command_text` 在 `_check_ir_segment`（`:689-694`）对**每个** segment 调用，只看 token 是否等于 `-c`/`--command`，不校验 `rest[0]` 是否为 launcher。因此 `grep -c` / `cut -c` / `sort -c` 这类「`-c` 的值是数据」的普通选项全部命中。
- 与修复自陈矛盾：同一 docstring 明写「quoting a command as data (`grep -rn "cp x .env" docs/`) must not match」——但 `grep -c` 的引号值**会**被匹配。同一「在文档里搜命令字面量」的语义，`-rn` 放行、`-c` 拒绝。
- 建议：把该拦截限定在 `rest[0]` 属于 `_LAUNCHERS`（或 `script` 专属）时，或改为「只有当 `-c` 的值**本身**能被解析出受判命令且选项在 launcher 上」。

### R2-3（中，覆盖缺口）新增的源位置判定被一个前导 flag 击穿
- 证据：`cp -r .env /tmp/x`、`cp -a .env /tmp/x`、`cp -p .env.local /tmp/x`、`mv -f .env /tmp/x`、`install -m 600 .env /tmp/x` → 端到端 **ALLOW**（护栏 `cp_source` 未触发、policy 的 `_env_source_is_credential` 取到 `-r` 也放行）。
- 机制：`_check_ir_segment`（`:733-739`）只对 `rest[1]` 判源，且 `if not source.startswith("-")` 直接跳过——只要源前面有任一 flag 就跳过源判定；目标判定取最后一个 positional（`/tmp/x`）也不敏感。
- 关系：旧实现同为 allow（甲类，非回归），但 task 2.7 / spec「`.env` 凭据变体…`mv`/`cp`/`dd`/`tee`/重定向的目标位 SHALL 被拒绝」把源位置纳入本 change 范围，且 fix 的 commit message 声称「源位置改由 evaluator 判定」——该判定不完整。
- 建议：从 IR 的 argv 里取「第一个非选项 positional」作源（而非固定 `rest[1]`），或直接读 `write_targets[]` 的源字段。

### R2-4（中，DENY→ASK 弱化）`ionice -c <n> cp x .env` 被本轮修复由 DENY 降为 ASK
- 证据：`6153d8f`（修复前）`ionice -c 2 cp x .env` → DENY；HEAD → **ASK**（`launcher_prefix`）。`ionice -c 3 cp x y`（无害目标）也由 allow 变 ask。
- 机制：`ionice -c` 本是 `_LAUNCHER_OPTS_WITH_VALUE`（跳过其值），被新加的「`-c` 值是命令」拦截抢先，`rest = rest[2:]` 后剩 `['2','cp',...]`，`2` 成未知 head → `_conceals_judged_command` 命中 → ASK。
- 仍在文档化谓词 `旧 DENY ⊆ 新 DENY ∪ 新 ASK` 的允许范围内（ASK 在无 UI = 拒绝），但交互环境下是真实弱化（人可点 y），且由本轮修复引入。

### R2-5（中）round-1 Issue 1 未修：`redirects[]` 死字段 + 数据 heredoc 正文误报
- `agent/tools/bash_ir.py:142/:274` 构造 `redirects[]`，`agent/` 下**零消费者**；重定向判定仍走 `_has_protected_redirect` 的 `tokenize_command`（`command_guard.py:868`）——违反 spec「判定器 SHALL NOT 绕过 IR 重新切分 token」与 D2「redirects[] 由重定向 evaluator 消费」。
- 附带（round-1 已指出，未修）：`_has_protected_redirect` 扫未 mask 的原始 cmd，数据 heredoc 正文字面 `>` 被当重定向——实测 `cat <<'EOF'\ntext > /etc/passwd here\nEOF` → **DENY（protected_redirect）**，与 D4「数据 heredoc 正文不是命令」矛盾。

### R2-6（低）新增 `_env_source_is_credential` 与 evaluator 源检查构成同一语义的第二实现（D9）
- `agent/workspace_policy.py:116-127` 新增 `_ENV_SOURCE` 正则 + `_env_source_is_credential`，与 `command_guard._check_ir_segment` 的 `rest[1]` 源判定、以及新收窄的两条 `\b(mv|cp)\s+…` 正则，是「mv/cp 源是否敏感」的**三处**实现。task 2.7/D9 的目标是把源位置判定迁往 evaluator、消除双实现；本轮修复是「再加一处窄正则 + 消费共享谓词」，方向与 D9 相反（虽避免了模板误伤这一具体症状）。
- 另注：`_env_source_is_credential` 是 raw-text regex，`grep -rn "cp .env" docs/`（数据）在 policy 通道被拒——该误报为 round-1 前既有（旧两条正则同样命中），非本轮引入，但与本 change 的「引号内是数据」原则不符，建议登记。

### R2-7（中）其余 round-1 未清项（复核确认仍在）
- **Issue 7**：tasks.md 仍 4/61 勾选，归档点完成度门禁必红（`(post-merge)` 只豁免 7.7）。
- **Issue 6**：护栏不覆盖凭据变体的 Bash **读**位——`cat .env.local` → allow，而 `assert_read_allowed(".env.local")` → DENY；spec「`.env` 系列 SHALL 被拒绝——读、写…」文字未声明该分工。
- **Issue 8**：6.6 的「argv 入口数 == 1」与 6.1 的矩阵 `--collect-only` 自校验均无机械实现。
- **Issue 9**：`command_guard.py:40-41` 导入 `SENSITIVE_DOTDIRS/SENSITIVE_DOTFILES as _…` 全文件无引用（死导入）。

## Test Results

```
$ uv run pytest -q
2 failed, 3727 passed, 9 skipped, 80 warnings in 348.65s (0:05:48)
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
```
= 已知本机环境失败（`/tmp` 为 git 仓库），无其他失败。
change 专属：`573 passed`。
对照/变异健全性：变异 A（`_concealed_command_text` 置空）3 红；变异 B（还原 `rest[1:5]` 窗口）2 红；变异 C（`_env_source_is_credential` 短路）5 红；三次均还原。
覆盖弱化检查：`benchmarks/attacks/attacks.json` 只增不减（+19）；`test_attack_suite.py` 的 `is DENY` 未放宽；ASK 用例另立 `test_ask_suite.py`（与攻击集不重叠）。**未发现为过测试而放宽断言**。

## 结论

- **round-1 的四个修复点经独立复跑确认到位**（单 `-c`、填充 token、`~` 敏感路径、模板源），round-1 必须成立的回归对照组全部保持，安全底线（73/73、零迁移违规、全量 pytest）成立。
- **但修复把「`-c` 的值可能是命令」这一判断做成了全局拦截**，同时带来：(a) 重复 `-c` 的真 fail-open（R2-1，(b) `grep -c`/`cut -c` 一类的误报（R2-2）；并且新增的源位置判定只判 `rest[1]`、被一个前导 flag 击穿（R2-3）。三者都处在本轮**新改动的代码路径**上，建议合并前修 R2-1/R2-2/R2-3。
- **round-1 的 Issue 1（`redirects[]` 死字段 + 重定向仍走 tokenizer + 数据 heredoc 误报）与 Issue 5/6/7/8/9 仍未清**；其中 Issue 7（tasks 4/61）会直接卡归档门禁。
- 综合判 **CHANGES_REQUESTED**：无「护栏整体可被无保护绕过」级别的阻塞缺陷，但 R2-1 是安全模块内的真实 fail-open（机制被修复宣称覆盖却未覆盖），R2-2/R2-3 是同一修复引入的误报/缺口，应修复后再判 PASS。
