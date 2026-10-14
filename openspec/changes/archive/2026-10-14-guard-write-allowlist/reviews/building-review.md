# Building Review — guard-write-allowlist

## Verdict

**`PASS`**（第 3 轮 / 3 轮封顶；审阅者独立零记忆，不继承开发上下文）

**一句话**：R2 的两条待修**都真修了，且修法各自可复算**。N-1 选「补测试」并把声明改成可复算形态——新增的 8 条用例逐条**命中各自那条规则**（不是被 YAML 解析错顺带通过），变异探针精确杀死对应 case；N-2 选「显式记录」——我把改动的实际影响面**枚举穷尽**后确认它只有一格：`is_write_allowed` 对「空清单 + 越界路径」从返回 `False` 变抛 `PermissionError`，**默认态下的常规写判定与改动前逐行等价**（W/R/D 三通道 48 行 0 差异，guard 侧 64 条命令 0 差异）。上轮的 I-1/I-3/I-4 **未被改坏**——本提交对 `agent/**` 是**零可执行代码改动**（AST 逐模块证明）。安全面整轮重跑干净（读侧 0 翻转、读源命令 0 翻转、结构性 deny 0 泄漏、反转探针只开出清单内的路径）。**判 `PASS`**；另记三条 nit（`design.md` 两处行号用了与文内声明不同的版本口径、`is_write_allowed` 零测试覆盖、`tasks.md` 状态头未更新），**均不影响结论、不阻塞**。

| 轮次 | revision | verdict |
|---|---|---|
| R1 | `340c90e` | `CHANGES_REQUESTED`（I-1 Must fix + I-2/I-3 + 两条 nit） |
| R2 | `6a43aee` | `CHANGES_REQUESTED`（I-1/I-3/I-4 关闭；I-2 尾部、I-5 边角各一处待修） |
| **R3（本轮，封顶）** | **`4d8e048`** | **`PASS`**（N-1 / N-2 均关闭；三条 nit 见 R3-8） |

---

## R3 复审（revision 4d8e048）

- **Diff span**：`fd6d581`（`git merge-base HEAD origin/master`）.. `4d8e048`（HEAD）；本轮 delta = `git show 4d8e048` = 4 文件 / +340 −3（`agent/workspace_policy.py`、`design.md`、`building-review.md`、`tests/agent/test_config.py`）
- **方法**：隔离副本 `git archive <rev> | tar -x -C`（`base=fd6d581` / `r1=340c90e` / `r2=6a43aee` / `head=4d8e048`，位于 `/tmp/wl3/copies/`），探针脚本单独放在 `/tmp/wl3/probes/`（**不放进副本树**——第一版把探针写在副本同级目录，`sys.path[0]` 指到脚本目录，import 到了错误的 `agent` 包，读数全错；已改正，见 R3-9 的自我更正）；同名 workspace 路径 + 同一份语料喂给两棵树后逐行 `diff`。变异探针在 7 份额外副本上做（`mut-A`…`mut-G`）。**被审 worktree 零改动**：`git status --porcelain` 全程为空。

### R3-1. N-1（上轮唯一阻塞）—— ✅ **关闭：用例真存在、真命中各自规则、声明可复算**

上轮判的是「`design.md:97` 尾句断言 `tests/agent/test_config.py` 有逐条用例，实测计数 0」。作者选「补测试」，我按三层验：

**① 用例真存在且逐条命中自己的规则。** `tests/agent/test_config.py:973-995` = `test_allowed_write_paths_rejects_non_canonical_spelling`（`parametrize` 五条：`./.env` / `a//b` / `a/./b` / `a\b` / `.`），`:998-1006` = `test_allowed_write_paths_strips_surrounding_whitespace`（三条空白形态）。实读文件与声明**逐条对得上**。跑起来 8 passed。但「pass」本身不构成证据——`pytest.raises(ConfigError, match="tools.allowed_write_paths")` 的 `match` 对**任何一条**规则都成立（六条报错文案都以该字段名开头），所以我把每条 entry 的报错**分类打印**出来：

```
  './.env' -> ConfigError[canonical]   './.env' is not a canonical workspace-relative path (drop the leading `./`, `//` or backslashes)
  'a//b'   -> ConfigError[canonical]   'a//b' is not a canonical workspace-relative path ...
  'a/./b'  -> ConfigError[canonical]   'a/./b' is not a canonical workspace-relative path ...
  'a\\b'   -> ConfigError[separator]   'a\\b' must use `/` as the separator
  '.'      -> ConfigError[canonical]   '.' is not a canonical workspace-relative path ...
  ' .env'            -> ACCEPT ('.env',)
  '.env '            -> ACCEPT ('.env',)
  '  config/.env  '  -> ACCEPT ('config/.env',)
```

五条报错分别是 canonical / canonical / canonical / **separator** / canonical——**与提交信息的自述逐字一致**。报错文案里带着 entry 原文，证明进到校验器的是**预期的那个值**（不是 YAML 把 `a\b` 吃成别的东西）：YAML 单引号不做转义，`- 'a\b'` 解析出的就是 `a\b`。

**② 不是空转（变异探针）。** 两个变异体各自只删一条规则分支：

```
MUT-A 删掉 canonical 分支（agent/config.py 的 `if entry != "/".join(parts)` 块）
  -> 4 failed, 480 passed
     FAILED ...::test_allowed_write_paths_rejects_non_canonical_spelling[./.env]
     FAILED ...[a//b]     FAILED ...[a/./b]     FAILED ...[.]
MUT-B 删掉 separator 分支（`if "\\" in entry` 块）
  -> 1 failed, 483 passed
     FAILED ...[a\\b]   E  Failed: DID NOT RAISE <class 'agent.config.ConfigError'>
```

杀伤面**精确到条**：删 canonical 只死那 4 条，删 separator 只死 `a\b` 那 1 条。⇒ 这 5 条各自钉住的是**自己那条规则**，不是「随便抛个 ConfigError 就算过」。同一探针还跑了 U2 既有四类的回归对照（`**/*`→glob、`/etc/.env`→absolute、`config/`→tail_slash、`../outside.env` 与 `config/../.env`→dotdot），四类**未被本轮改动波及**。

**③ 声明现在可复算、与我实读一致。** `design.md:100` 的尾句已从「并有 `tests/agent/test_config.py` 的逐条用例」改为**指名两个函数 + 各自的 `parametrize` 条目**（`test_allowed_write_paths_rejects_non_canonical_spelling` 五条 `./.env` / `a//b` / `a/./b` / `a\b` / `.`；正向对照 `test_allowed_write_paths_strips_surrounding_whitespace` 三条空白形态）。我按这句去文件里数，**一一对上**。⇒ 这条声明从「不可复算的泛指」变成了「按名字与条目可直接点开核对」，正是上轮修法推荐 ① 想要的效果。

### R3-2. 如实披露（没有改写历史）—— ✅ **成立**

三件事分别验：

```
$ git rev-parse HEAD^ == 6a43aee                                    -> YES   （未改写历史）
$ git log -1 --format=%B 6a43aee | grep 逐条测试
    current spec（Requirement + 新 Scenario）+ 逐条测试。            -> 原提交信息仍含该断言
$ git show 6a43aee:openspec/changes/guard-write-allowlist/design.md \
    | grep -c "并有 \`tests/agent/test_config.py\` 的逐条用例"       -> 1     （旧文档字节原样保留）
$ git show --name-only --format="" 6a43aee | grep '^tests/'
    tests/agent/tools/test_command_guard.py                         -> 只此一个（与披露一致）
```

**历史计数我按 6a43aee 的树复算，与披露数字逐条相符**（这是关键——披露若把当时的事实说错，就等于用第二个错误掩盖第一个）：

```
git grep -e 'a//b'   6a43aee -- tests/   -> 0 hits
git grep -e 'a/\./b' 6a43aee -- tests/   -> 0 hits
git grep -e 'a\\b'   6a43aee -- tests/   -> 0 hits
git grep -e '\./\.env' 6a43aee -- tests/ -> 1 hit（tests/agent/test_config.py:950 "config/../.env"，
                                                  U2 既有的 `..` 段用例，非本轮补充）
```

即**当时确实为 0**，披露如实。披露落在三处且互相印证：新提交信息（「如实更正（针对 6a43aee）」段）、`design.md:102`（「本段上一版（`6a43aee`）写…计数为 0…即声明先于落地」）、以及 `design.md:79` 对 N-2 的同类更正（「`6a43aee` 的提交信息把它一并写进『除 I-4 传参外无行为变更』是不准确的」）。措辞是「**新开提交如实更正、不改写历史**」，实际做法也是新开提交（未 amend / 未 force-push，`6a43aee` 是 HEAD 的父提交）。⇒ **没有抹掉痕迹，也没有用新措辞覆盖旧事实。**

### R3-3. N-2 求值顺序改动 —— ✅ **确实只影响那一类边角；默认态逐判定等价**

上轮的争点是「空 allowlist + 越界路径」由返回 `False` 变抛 `PermissionError`，方向 fail-closed 但没写进文档。作者选**显式记录**（R2 修法的 ②），并把理由写成「与 `is_denied` 对称、旧顺序自相矛盾」。我不接受只靠理由，**把影响面枚举穷尽**：

**① 与改动前（`340c90e` 的旧实现）逐通道对拍，48 路径 × 4 通道：**

```
mode=default（allowlist 为空）  r1(340c90e) vs head(4d8e048)
  差异行 = 22（= 11 条路径 × 2 侧），全部落在第 5 列（is_write_allowed），W/R/D 三列 0 差异
  逐条形态：  r1 = A|OK:False     head = A|ERR:PermissionError
  11 条路径： etcpasswd_link / escaper / outside_link / <WS>/etcpasswd_link / <WS>/escaper /
              /etc/passwd / /etc/ssh/sshd_config / <OUT>/.env / <WS>/../outside.env /
              <WS>/../outside/.env / /proc/self/environ      —— 全部是**越界路径**
mode=allow（allowlist 非空）    r1 vs head
  48 行 × 4 通道 **0 差异**（含 is_write_allowed 本人）
```

⇒ 差异**恰是**上轮描述的那一格，不多一分：只要 allowlist 非空，新旧在任何路径上（含越界）都同结论；只有「空清单 + 越界」这一格变了。**在-workspace 路径在两种配置下都与旧实现一致**（空清单时旧/新都返回 `False`）。

**② 默认态（本 change 真正的生产态）的等价性是逐判定测的，不是推的。**

```
① policy 默认态 base(fd6d581) vs head：W/R/D 三通道 48 行，0 行不同
   （唯一差异是 head 多了 is_write_allowed 这一列——base 树里该方法**不存在**）
① guard 默认态 base vs head：64 条命令判定，0 行不同（verdict + last_reason 全等）
```

**③ 相对 origin/master 根本没有回归面**：`git grep -c is_write_allowed fd6d581 -- '*.py'` = **0 命中**——该方法整体是本 change 新引入的，`fd6d581` 上不存在，所以这不可能是「相对基线的行为变更」，只是本 change **内部两个 revision 之间**的差异。

**④ 零调用方（计数口径，不是截断搜索结果）**：`grep -rn 'is_write_allowed' --include=*.py . | wc -l` = **1**，那 1 条就是定义本身（`agent/workspace_policy.py:445`）；全文件类型计数 10，其余 9 条全在 `design.md` / `building-review.md` 的文字里。⇒ `design.md:79` 的「全仓零调用方」为真。

**⑤ `design.md:79` 的声明与实际一致。** 逐条核：现象（空清单 + 越界 → 由 `False` 改抛 `PermissionError`）✔；方向 fail-closed ✔（异常比 `False` 更严，且无调用方承接）；与 `is_denied` 同形 ✔（`is_denied:393-394` 同样先 `assert_within_workspace`）；与本方法 docstring 一致 ✔（docstring 写 boundary checked first and never overridable，新行为正是如此）；「不在 I-4 传参改动里」✔（I-4 动的是 `denied_patterns` 形参）。**我判它是可接受的有意变更，不是缺陷**：新的求值顺序消除了一种自相矛盾（同一问题随配置在布尔与异常间切换），方向更严，且零调用方 ⇒ 无功能后果。

### R3-4. 安全面：**整轮重跑**（本轮改过 `agent/workspace_policy.py`，上轮结论不沿用）

方法同 R2，但**语料更宽**：48 条相对/绝对路径 × {`assert_write_allowed` / `assert_read_allowed` / `is_denied` / `is_write_allowed`} + 64 条命令 + 50 条从 deny 表**逐条派生**的结构性候选 + 216 行反转语料（6 种 allowlist 配置 × 36 种路径写法，含大小写、前后缀、多斜杠、`.` 段、`..` 段、symlink）。

**① 默认态等价** — 见 R3-3②：policy 48 行 0 差异、guard 64 条 0 差异。

**② 精确路径（只放行清单内）** — 翻转全枚举，读侧/deny 侧零翻转：

```
policy flips (default -> allow):  W 13 / R 0 / D 0 / A 13
W flips: .env, sub/.env, config/.env, a/b/c/.env, deploy.pem, id_rsa, .env_link(→.env),
         pem_link(→deploy.pem), <WS>/.env, <WS>/config/.env, <WS>/deploy.pem,
         <WS>/.env_link, <WS>/pem_link
ALLOW->DENY flips: 0
```

13 条全部是**清单内的精确路径**或其**规范化等价拼写**或**解析到清单内目标的 symlink**。未列入的逐条实测仍拒（未出现在翻转集）：`.env.local` `.env.production` `config/.env.bak` `src/.env` `a/b/c/d.env` `xdeploy.pem` `.venv/lib/x.py` `.ssh/id_rsa` `.aws/credentials`。

**③ 读侧未被放宽 → ✅（三重证据）**

```
读通道翻转 R| : 0          is_denied 通道翻转 D| : 0
grep -rn 'allowed_write_paths\|write_allowlist_covers' agent/code_intelligence/  -> 0 命中
AST（含 docstring 全量）base vs head：
  assert_read_allowed / is_denied / assert_within_workspace / relative_path 全部 identical: True
  assert_write_allowed                                                      identical: False（正是本 change）
```

即**读侧四个方法逐字节未改**，且 `repo_map` 所在的 `code_intelligence/` 对 allowlist **零引用**——被豁免的 `.env` 不会被收进符号索引。

**④ `mv`/`cp` 源位置未放行 → ✅**

```
源位置命令（default vs allow）：
  cp .env /tmp/out            deny[cp_source]      -> deny[cp_source]       same
  mv .env /tmp/out            deny[mv_source]      -> deny[mv_source]       same
  install -m 600 .env /tmp/out deny[install_source]-> deny[install_source]  same
  cp .git/config /tmp/out     deny[cp_source]      -> deny[cp_source]       same
  mv config/.env .env         deny[mv_source]      -> deny[mv_source]       same
  cp sub/.env /tmp/out        deny[cp_source]      -> deny[cp_source]       same
  cp .env /tmp/.env           deny[denylist]       -> deny[denylist]        same
源位置命令被 allowlist 造成的翻转：0
```

即被豁免的 `.env` 没有变成可外泄的读源。

**⑤ 结构性 deny 永不翻转 → ✅（0 泄漏，两源枚举）**

从 deny 表与敏感目录表**逐条派生** 50 个候选（精确条目、`<条目>/x.js`、`a/<敏感目录>/b`），把**该候选自身**放进 allowlist，再看它是否被打开：

```
candidates=50  structural=37  nonstructural=13
STRUCTURAL LEAKS: 0 []
  例：.git/config DENY->DENY、.git/HEAD DENY->DENY、node_modules/x.js DENY->DENY、
      .venv/x.js、benchmarks/runs/x.js、.ssh/x、a/.git/b、.aws/x、.npmrc、.pypirc 全 DENY->DENY
  13 条 non-structural（id_rsa / .venv / node_modules / benchmarks/runs 这类**文件级**条目）
      可被自身条目打开 —— 这是本能力的**设计意图**，非泄漏
```

**⑥ 反转/对抗探针 → 只开出清单内的东西**

216 行语料（配置 `bare` / `nested` / `pem` / `linknm` / `dotgit` + 空清单对照）逐配置求「空清单 DENY → 配置后 ALLOW」的开集：

```
bare   ('.env',)                 -> .env, sub/../.env, ./.env, .//.env, .env/., .env_link, <WS>/.env
nested ('.env','sub/.env')       -> 上式 + sub/.env, ./sub/.env, sub/./.env, sub//.env
pem    ('.env','deploy.pem','sub') -> 上式 + deploy.pem, pem_link
linknm ('pem_link',)             -> ∅          （写链接名**不**开，只有解析目标在清单里才开）
dotgit ('.git/config','.git/HEAD') -> ∅        （结构性）
```

开集**完全等于**「清单内路径的规范化等价拼写 + 解析到清单内目标的 symlink」，没有多出任何一格。三位「反向」形态**未开**：`linknm` 写 `pem_link` 仍 DENY、`dotgit` 写 `.git/config` 仍 DENY、`.env.bak` / `xdeploy.pem` / `.ENV` 类的开关状态与空清单态**一致**（两态皆 DENY 或两态皆 ALLOW——后者是变更前既有事实，如 `.ENV` 大小写不敏感判定之外的名字，差分证明与 allowlist 无关）。guard 侧同语料翻转 13 条，**全部**为清单内路径的写目标，无一条读源、无一条结构性路径。

**⑦ 变异探针（证明测试网仍在守门）**

```
MUT-C  write_allowlist_covers 无视结构性 deny（恒 return True）
       -> 12 failed（含 test_write_allowlist_never_overrides_structural_deny ×10、
          TestGuardUsesPolicyDenyTable ×2）                                    ✔ 被杀
```

### R3-5. 上轮已成立的 I-1 / I-3 / I-4 —— ✅ **未被本轮改坏**

**最强的证据是「本轮没有可执行代码改动」**：把 `agent/**` 各模块的 AST 剥掉 docstring 后逐模块比 `6a43aee`（R2 revision）与 `4d8e048`（HEAD）：

```
agent/workspace_policy.py   identical: True
agent/tools/command_guard.py identical: True
agent/config.py             identical: True
agent/tools/builtin/bash.py identical: True
agent/main.py               identical: True
```

`agent/workspace_policy.py` 的 hunk **整段落在三引号 docstring 内**（改的是 `is_write_allowed` 的说明文字）。⇒ I-1/I-3/I-4 的代码面在结构上不可能被动到。仍按要求复跑三者的**回归守门**：

```
I-1: MUT-G（_allow_covers 对越界绝对路径按 basename 回退，模拟「护栏感知附加根」）
     -> FAILED TestAdditionalRootIsRootBlind::test_additional_root_writes_stay_denied_in_guard   ✔ 仍被杀
I-4: MUT-F（忽略注入的 denied_patterns，回退到默认表）
     -> FAILED TestGuardUsesPolicyDenyTable::test_custom_deny_table_is_honoured                  ✔ 仍被杀
I-3: docs/known-debt.md 条目在位；数字逐条复算：
       len(DEFAULT_DENYLIST)=59 ✔（条目写 58→59）
       len(DEFAULT_DENIED_PATTERNS)=32 ✔（条目写 35→32）
       .env 族已不在表：[p for p in DEFAULT_DENIED_PATTERNS if 'env' in p] -> ['.venv','.venv/**','venv','venv/**'] ✔
     受保护写入事件齐：workflow-events.jsonl 全 9 条 dump 后，
       seq=6 与 seq=8 均为 protected_artifact_explained / artifact_path=docs/known-debt.md  ✔
```

### R3-6. 本轮测试与门禁的原始行

```
$ uv run --extra dev pytest -q --basetemp=/home/happy/wl-basetemp-rev3 -p no:randomly
FAILED tests/agent/commands/test_session_workspace.py::test_session_workspace_add_nonexistent_path
1 failed, 4468 passed, 8 skipped, 110 warnings in 505.38s (0:08:25)
   # 与提交信息自述的 4468 / 1 / 8 逐字一致；上轮全量跑到的 test_contract[docker] 本轮未复现

$ <4 个受影响测试文件>   -> 631 passed in 3.37s      （6a43aee 上同 4 文件 = 623 passed，差 +8 = 5+3 条新用例，与自述一致）

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)          # EXIT=0

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
ERROR: guard-write-allowlist: review manifest missing:
  openspec/changes/guard-write-allowlist/reviews/building-review-manifest.json   # EXIT=1（写 manifest 前）
  -> 写完 manifest 后复跑，输出见本节末

$ git diff --name-only fd6d581..HEAD | grep -c '^\.github/'   -> 0
$ git status --porcelain                                       -> 空（被审 worktree 全程零改动）
```

**唯一失败项的独立归因（我自己复现，不照抄简报）**：

```
同一用例，basetemp 在 /tmp 之外 -> 1 failed in 1.97s
同一用例，basetemp 在 /tmp 之内 -> 1 passed in 0.86s
**基线副本 /tmp/wl3/copies/base（fd6d581）**，basetemp 在 /tmp 之外 -> 1 failed in 1.61s
ls -d /tmp/.git -> /tmp/.git EXISTS
```

⇒ 决定性于 `--basetemp` 落点、且在**未改动的基线副本上同样失败**，非本 change 引起（本机 `/tmp` 是 git 仓库，与本仓既知的 tmp 污染一致）。

### R3-7. manifest 与 checker 复跑

```
$ PYTHONPATH=. python3 -c "... write_review_manifest(..., verdict='PASS') ..."
manifest written
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
OpenSpec artifact checks passed                                                   # EXIT=0
```

manifest 绑定：`base_sha=fd6d581…`、`head_sha=4d8e048…`、`report_hash`（本报告终稿字节）、`spec_hash`、`tasks_hash`、`diff_hash`。**次序纪律**：本报告先定稿、manifest 后生成（manifest 要哈希报告字节）。

### R3-8. 本轮新记的 nit（均不阻塞，也不构成「声称与事实不符」）

| # | 位置 | 事实 | 建议 |
|---|---|---|---|
| **N-3** | `design.md:77` | 同一段里 `is_write_allowed`（`:445`）与 `_allowlist_covers_resolved`（`:433`）用的是**变更后**行号；而 `design.md:323` 自述「本文件与 proposal 的引用均在…**前树**上现测」，且同段 `:79` 的 `:317` 用的**正是变更前行号**。实测 `fd6d581` 的 `agent/workspace_policy.py` 只有 **398 行**，`:433`/`:445` 在前树**根本不存在** ⇒ 按文内声明的口径读会落空。**不构成假声明**：两处都点了符号名，且按当前树读是准的（head `:433`/`:445` 正是这两个符号）。 | 去掉这两个数字，或标注「（变更后行号）」。 |
| **N-4** | `agent/workspace_policy.py:445` | `is_write_allowed` **零测试覆盖**：MUT-D（恢复旧顺序）与 MUT-E（恒 `return False`）在 3 个受影响测试文件上都是 **484 passed**，无一被杀。它是本 change 新引入、且在 `design.md` 里作为公开查询入口写进设计的方法。 | 补一条钉住新行为的用例（空清单 + 越界 ⇒ `PermissionError`）。零调用方 ⇒ 不阻塞。 |
| **N-5** | `tasks.md:3` | 状态头仍写「第 1 轮判 CHANGES_REQUESTED，已按 I-1～I-5 修复并复跑」，未反映 R2/R3。措辞不算假（第 1 轮确如此），但归档前应更新为 R3 `PASS`。 | 归档提交里一并更新。 |

### R3-9. 自我更正（本轮我自己的一个读数错误，记录以免后续读者照抄）

第一版探针把脚本放在 `/tmp/wl-r3/probe_rules.py`（与副本目录同级），Python 以**脚本所在目录**为 `sys.path[0]`，脚本 import 到了那个目录下的**另一份陈旧 `agent` 包**（`/tmp/wl-r3/agent`，早于本 change），于是全部条目都读成 `AttributeError: 'ToolsConfig' object has no attribute 'allowed_write_paths'`——**看起来像「测试全是空转」，实为我探针的环境错误**。改用 `assert agent.config.__file__.startswith(副本路径)` 硬断言模块来源、并把探针移出副本树后复跑，才是 R3-1 里那组数据。此处更正以免后续读者照抄那组假读数。

### R3-10. 结论

R2 的两条**都已实质关闭**：N-1 不是「删声明」而是把用例补齐并让声明可复算（五个 entry 各自命中自己的规则，变异探针 4+1 全杀）；N-2 不是「恢复旧顺序」而是把改动如实落进 `design.md`，且该改动的影响面经**穷尽枚举**确认只有「空清单 + 越界」一格，**默认态下与改动前逐判定等价**。上轮 I-1/I-3/I-4 因本轮**零可执行代码改动**而在结构上不可能回归，回归守门探针复跑仍全杀。安全面整轮重跑：默认态 0 差异、读侧 0 翻转、读源 0 翻转、结构性 deny 0 泄漏、反转探针只开出清单内路径。三条新记 nit 均为文档/覆盖面的小项，不影响本判定。⇒ **`PASS`**。

> **写 manifest**：verdict = `PASS`，已按流程生成 `reviews/building-review-manifest.json`（asterwynd 形态；**未**建 witnessloop 形态 manifest，按本轮指示）。

---

## R2 Verdict（revision 6a43aee，已被 R3 取代）

**`CHANGES_REQUESTED`**（第 2 轮 / 3 轮封顶；审阅者独立零记忆，不继承开发上下文）

**一句话**：I-1 / I-3 / I-4 **完全成立**，I-2 的回写已落地但**新增了一句可证伪的测试覆盖声明**，I-5 的抽取等价性成立但**带出一处边角行为差异**、与提交信息「除 I-4 传参外无行为变更」不符。**安全面本轮整轮重跑全部干净**（默认态 217 行判定 0 差异、读侧翻转 0、读源命令翻转 0、结构性 deny 0 泄漏、四个变异探针全被测试杀死）。判 `CHANGES_REQUESTED` 只因上述两处「声称与事实不符」，**均无安全影响、无功能缺陷，修法各为一行**。

| 轮次 | revision | verdict |
|---|---|---|
| R1 | `340c90e` | `CHANGES_REQUESTED`（I-1 Must fix + I-2/I-3 + 两条 nit） |
| **R2（本轮）** | **`6a43aee`** | **`CHANGES_REQUESTED`**（I-1/I-3/I-4 关闭；I-2 尾部、I-5 边角各一处待修） |

---

## R2 复审（revision 6a43aee）

- **Diff span**：`fd6d581`（`git merge-base HEAD origin/master`）.. `6a43aee`（HEAD）
- **本轮修的面**：`git show 6a43aee` = 11 文件 / +485 −17，其中**行为面只动了三处**（`command_guard.py` 加 `denied_patterns` 形参并透传、`builtin/bash.py:92` 构造点传表、`workspace_policy.py` 抽 `_allowlist_covers_resolved`）
- **方法**：隔离副本（`git archive <rev> | tar -x` → `rm -f .git && git init -q`，位于 `/tmp/wl-r2/{base,head}`）+ `PYTHONPATH` 指向副本的差分探针；同名 workspace 路径喂给两棵树，输出逐行 `diff`。变异探针在 `mut`/`mut2`/`mut3` 三份**额外副本**上做，被审 worktree **零改动**（`git status --porcelain` 全程为空）。

### R2-1. I-1（R1 的 Must fix）附加根「两层同向」—— ✅ **成立**

R1 要求三件事：分开归因、spec carve out、补断言。三件都做了，且**归因分类经我实测确认正确**。

**实测（HEAD，附加根 `/tmp/.../other`、`allowed_write_paths=('.env',)`）**：

```
file-tool Write /tmp/wl-r2-i1-*/other/.env -> ALLOW
  guard DENY  [protected_redirect]  echo K >> <extra>/.env
  guard DENY  [tee_target]          tee <extra>/.env
  guard DENY  [dd_target]           dd of=<extra>/.env
  guard DENY  [install_target]      install x <extra>/.env
  guard DENY  [denylist]            cp x <extra>/.env      <- 另叠加整句正则那层
  guard DENY  [denylist]            mv x <extra>/.env
== 主根对照 ==
  guard ALLOW [None]  echo K >> .env      tee .env      dd of=.env      install x .env      cp x .env      mv x .env
  guard DENY  [protected_redirect]  echo K >> config/.env
  guard DENY  [denylist]            cp x config/.env      mv x config/.env
```

即 `>>` / `tee` / `dd of=` / `install` 四形的拒绝**确实**来自「护栏只持有主 workspace」（`command_guard.py:732-757` 的 `_allow_covers` 在 `:744` 要求 `self._workspace`、`:749` 用 `_within` 判主根；`CommandGuard` 接口上根本没有 `additional_roots`），**不是** R1 原先引的整句 denylist 正则；`cp`/`mv` 才叠加后者。**作者的分类正确，R1 的混合归因确实是错的。**

**规格 carve out**：delta 与 current spec 两处都补上了排除项 ④ + Scenario——`openspec/changes/.../specs/workspace-safety/spec.md:121`（④ 全文）/`:144`（Scenario 附加根不同向）、`:157`/`:172`（不同源说明 + Scenario），`openspec/specs/workspace-safety/spec.md:660`/`:683`/`:696`/`:711` 同向。`design.md:134` 与 `:254-267` 的 U9/Decision 9 也改成了两行对照表。

**断言钉住且非空转**：`tests/agent/tools/test_command_guard.py:1104-1166`（`TestAdditionalRootIsRootBlind`，含四形各配 reason + `cp`/`mv` 的 `denylist` 层 + `:1152` 主根对照）。我做了**变异探针**验证它不是空转——把 `_allow_covers` 的 `_within` 分支改成 basename 回退（模拟「护栏变得感知附加根」）：

```
1 failed, 3 passed, 268 deselected
FAILED ...::TestAdditionalRootIsRootBlind::test_additional_root_writes_stay_denied_in_guard
  assert <CommandVerdict.ALLOW: 'allow'> is <CommandVerdict.DENY: 'deny'>
```

⇒ 该测试**真的**钉住了根盲区现状。**I-1 关闭。**

### R2-2. I-2 非规范拼写回写 Decision 3 —— ⚠️ **主体成立，尾句不成立（本轮唯一实质阻塞项）**

回写本身做到了，且口径与我实测一致：

- `design.md:97` 新增一段「实现期补充：还拒绝『非规范拼写』」，归因（防静默 no-op）、代价、报错文案三理由齐；
- 规格 delta `specs/workspace-safety/spec.md:59` + Scenario `:80`，current spec `openspec/specs/workspace-safety/spec.md:598` + Scenario `:619`；
- 行为保留且实测正确：`./.env` / `a//b` / `a/./b` / `a\b` / `.` / `a/` / `a[b]` / `/abs/.env` / `../x` / `a/../b` 全部 `ConfigError`；`.env` / `config/.env` / `' .env'`→`('.env',)` / `'.env '`→`('.env',)` 接受；`['']` → `()`（空串被 `_parse_string_list` 的 `strip()` 提前丢弃，不报错——与「落成空路径」那条措辞略有出入，但 `.` 确实被拒，属措辞而非事实问题）。

**但尾句可证伪**：`design.md:97` 写「并有 `tests/agent/test_config.py` 的逐条用例」，`6a43aee` 的提交信息同样写「…（Requirement + 新 Scenario）**+ 逐条测试**」。实测**计数为 0**：

```
$ git show --name-only --format="" 6a43aee | grep tests/          # 只列出
tests/agent/tools/test_command_guard.py                            # test_config.py 未被本轮触碰
$ git diff 340c90e..6a43aee --stat -- tests/
 tests/agent/tools/test_command_guard.py | 111 +++                  # 只有一个文件
$ grep -rn -- '\./\.env' tests/ | wc -l      -> 1   # 唯一命中是 test_config.py:950 的 "config/../.env"（U2 既有的 `..` 段用例）
$ grep -rn -- 'a//b' tests/ | wc -l          -> 0
$ grep -rn -- 'a/\./b' tests/ | wc -l        -> 0
$ grep -rn -- 'a\\b' tests/ | wc -l          -> 0
$ grep -c "def test_allowed_write_paths" tests/agent/test_config.py   -> 4（defaults / parsed / rejects_invalid_entries / rejects_non_list，全是 U2 四类，不含非规范拼写）
```

`:946-957` 那组 `parametrize` 覆盖的是 **U2 的既有四类**（glob / 绝对路径 / `..` 段 / 尾 `/`），**不含**本轮补充的非规范拼写。⇒ 这是**本轮 fix 新引入的一处事实错误**，且落在本 change 自己最在意的「如实划定兑现面」这一类上（与 R1 的 I-3 同型：结论写了、artifact 没落）。

**修法（二选一，均不涉及行为改动）**：① 在 `tests/agent/test_config.py` 的 `parametrize` 列表里补 `'./.env'` / `'a//b'` / `'a/./b'` / `'a\\b'`（并断言文案指向对应规则）；或 ② 删掉 `design.md:97` 的尾句、把「逐条测试」从提交口径里去掉。**推荐 ①**——它同时把这条规则钉进回归网。

### R2-3. I-3 任务 7.1 的 ②③④⑤ 落盘 —— ✅ **成立**

- `docs/known-debt.md:492` 新增「面试讲稿里四处陈旧的技术口径（guard-write-allowlist 7.1 扫描发现，均为变更前既有）」，四条逐条给出 `文件:行号` + 目标值，并写明「不就地改讲稿」的理由与收敛方向；
- 受保护写入事件齐：`workflow-events.jsonl` seq 8 = `protected_artifact_explained` / `artifact_path=docs/known-debt.md`（我 dump 了全部 9 条事件的 `seq|event_type|artifact_path`）；
- `tasks.md` 7.1 的措辞已从「记债务」改成「**已落盘**」并写清落点，不再是「读起来像已执行」。

**债务条目里的数字我逐条复算，全部为真**：

```
len(DEFAULT_DENYLIST)        = 59      （条目写 58→59）  ✔
len(DEFAULT_DENIED_PATTERNS) = 32      （条目写 35→32）  ✔
.env 族已不在 deny 表: [p for p in DEFAULT_DENIED_PATTERNS if 'env' in p] -> ['.venv', '.venv/**', 'venv', 'venv/**']  ✔
```

**I-3 关闭。**

### R2-4. I-4 `CommandGuard` 吃默认 deny 表 —— ✅ **成立（本轮唯一的行为改动，重点验毕）**

`command_guard.py:701-717` 新增 `denied_patterns` 形参，`:717` 落成 `self._denied_patterns = tuple(denied_patterns or DEFAULT_DENIED_PATTERNS)`，`:757` 把它交给 `write_allowlist_covers`；`agent/tools/builtin/bash.py:92` 的生产构造点传 `self.policy.denied_patterns`。

**实测三分支**（workspace 有 `sub/`，`denied_patterns=('sub/.env',)`，`allowed_write_paths=('sub/.env',)`）：

```
policy.assert_write_allowed('sub/.env')            -> DENY           （含 `/` ⇒ 结构性，豁免覆盖不了）
guard(passed custom table)  echo K >> sub/.env     -> DENY [protected_redirect]
guard(passed custom table)  tee sub/.env           -> DENY [tee_target]
guard(passed custom table)  dd of=sub/.env         -> DENY [dd_target]
guard(no table -> default)  echo K >> sub/.env     -> ALLOW [None]   <- 对照组：证明「传表」不是空转
```

**默认态未被改变**（这是 R1 最担心的反向风险）：不传表 vs 显式传 `DEFAULT_DENIED_PATTERNS`，12 条命令 **0 处不同**：

```
omitted-table vs explicit-default-table: 12 commands, 0 differing
```

**非空转验证（变异探针 MUT-C）**：把 `:717` 改回 `tuple(DEFAULT_DENIED_PATTERNS)`（即回退 I-4 的修法）⇒

```
FAILED ...::TestGuardUsesPolicyDenyTable::test_custom_deny_table_is_honoured
  assert <CommandVerdict.ALLOW> is <CommandVerdict.DENY>   (test_command_guard.py:1200)
1 failed, 1 passed
```

⇒ 两组新测试（`:1168-1213`）确实守住了同源。**I-4 关闭。**

### R2-5. I-5 `is_write_allowed` 抽取 —— ⚠️ **等价性成立，但带出一处边角差异**

`workspace_policy.py:433` 抽出的 `_allowlist_covers_resolved` 与 R1 时的 `is_write_allowed` 旧实现**逐句等价**，我按旧实现原文（`340c90e` 版：空表早返 → `assert_within_workspace` → `relative_path` → `write_allowlist_covers`）重写后对拍：

```
allow=()                                       : 13 paths, 2 mismatches
allow=('.env','deploy.pem','sub/.env','.git/config','id_rsa') : 13 paths, 0 mismatches
  MISMATCH: /etc/passwd                       new=ERR:PermissionError  old=False
  MISMATCH: /tmp/.../../outside.env           new=ERR:PermissionError  old=False
```

**这 2 处是真差异，不是探针假象**：旧实现先判空表、空表直接 `return False`（**不碰** workspace 边界）；新实现 `:450` 无条件先 `assert_within_workspace(path)`。于是**空 allowlist + 越界路径**从「返回 `False`」变成「抛 `PermissionError`」。方向是 **fail-closed（更严）**，且 `:445` 的 docstring 本来就写着「The workspace boundary is checked first and is never overridable」——新行为反而与自己的 docstring 一致。

**但提交信息的「**除 I-4 传参外无行为变更**」在这一点上不成立。** 影响面：`is_write_allowed` 全仓**只有定义、零调用方**（`grep -rn is_write_allowed --include=*.py` 计数 = 1，即 `workspace_policy.py:445` 自身），故无功能后果。

**修法（二选一，推荐 ①）**：① 恢复旧顺序（空表早返放回 `assert_within_workspace` 之前），使公开方法逐字节等价；或 ② 接受并把它写进 `design.md` 一句（「`is_write_allowed` 对空清单 + 越界路径由返回 `False` 改为抛 `PermissionError`，方向 fail-closed」）。**不接受**「提交信息改一改」——历史已入库。

---

### R2-6. 安全面：**整轮重跑**的原始结果（本轮改过 `workspace_policy.py` / `command_guard.py` / `bash.py`，R1 结论不沿用）

语料：40 个相对路径 + 7 个绝对路径 × {`assert_write_allowed` / `assert_read_allowed` / `is_denied`}，加 90 条命令。base 与 head 喂**同一个 workspace 路径**，逐行 diff。

**① `DEFAULT-STATE IDENTICAL`（默认空清单）→ ✅ 独立复现**

```
$ diff <(grep -v '^#' out-base-default.txt) <(grep -v '^#' out-head-default.txt)
*** DEFAULT-STATE IDENTICAL: 0 differing rows across 217 enumerated verdicts ***
# base header: has_allowed_write_paths=False / allowed_write_paths=ABSENT
# head header: has_allowed_write_paths=True  / allowed_write_paths=()
```

另在 read-source 语料上复算：`base default vs head default → IDENTICAL`。

**② allow 只放行清单内精确路径 → ✅（翻转全枚举）**

```
flips by channel (head: default -> allow):  W 8 / R 0 / D 0 / C 11
W flips  : .env, sub/.env, ./.env(→.env), x/../.env(→.env), deploy.pem, id_rsa, <WS>/.env, <WS>/deploy.pem
C flips  : 11 条，全部 DENY->ALLOW，且全部命令文本含被列入路径
allow->deny flips: 0
```

未列入的仍拒（逐条实测，未出现在翻转集里）：`.env.local` `.env.production` `config/.env` `config/.env.bak` `configX/.env` `src/.env` `a/b/c/.env` `bench/deploy.pem` `xdeploy.pem` `.git/config` `.git/HEAD` `/etc/passwd` `<OUTSIDE>/.env` `<WS>/../outside.env` `node_modules/x.js` `benchmarks/runs/x.json`。

**③ 读侧未被放宽 → ✅**

```
READ-layer flips (R|)  : 0
is_denied flips (D|)   : 0
$ grep -rn "allowed_write_paths\|write_allowlist_covers" agent/code_intelligence/   -> 0 命中（repo_map 索引跳过判定不感知 allowlist）
R|.env -> DENY      R|config/.env -> DENY      R|.env.local -> DENY
```

**④ `mv`/`cp` 的源位置未放行 → ✅（50 条读源命令）**

```
read-source commands: 50
flips caused by write allowlist among READ-SOURCE commands: 0
ALLOW->DENY flips: 0
  'cp .env /tmp/out'            default=DENY[cp_source]   allow=DENY[cp_source]
  'mv .env /tmp/out'            default=DENY[mv_source]   allow=DENY[mv_source]
  'cp .git/config /tmp/out'     default=DENY[cp_source]   allow=DENY[cp_source]
  'install -m 600 .env /tmp/out' default=DENY[install_source] allow=DENY[install_source]
  'dd if=.env of=/tmp/out'      default=DENY[denylist]    allow=DENY[denylist]
  'cp .env /tmp/.env'           default=DENY[denylist]    allow=DENY[denylist]
  'mv config/.env .env'         default=DENY[mv_source]   allow=DENY[mv_source]
```

即**被豁免的 `.env` 没有变成可外泄读源**。两条被我单独拎出来验的反向命令也干净：`cp /etc/passwd .env` → `DENY[denylist]`、`cp x /etc/passwd` → `DENY[denylist]`。

**⑤ 结构性 deny 永不翻转 → ✅（两源枚举，0 泄漏）**

```
A. 逐 pattern 派生后代路径 + 把该**精确路径**放进 allowlist（8 条）:
   .git/config .git/HEAD node_modules/x.js .venv/lib/x.py __pycache__/a.pyc
   benchmarks/runs/x.json .asterwynd/worktrees/w/x sub/id_rsa
   -> 8/8 DENY, leaks=0
B. SENSITIVE_DOTDIRS × {<d>/x, <d>, a/<d>/b} = 27 条（.aws .kube .netrc .ssh .npmrc .pypirc .gnupg .docker .git）
   -> 27/27 DENY
（另：裸目录名条目只开它自己那一条路径，开不出子树——allow=('node_modules',) 时
  write node_modules -> ALLOW 而 write node_modules/x.js -> DENY；allow=('.git',) 连 .git 本身都 DENY）
```

**⑥ 对抗/反转探针（base↔head 差分，normalize 掉随机临时目录名）→ 只出现预期翻转**

```
$ diff adv-base.n adv-head.n          # 除 5 组「allowlist 生效」翻转外无其它差异
  仅这些行不同（全部是 base 无 allowlist 能力 ⇒ DENY，head 命中豁免 ⇒ ALLOW）:
    allow=('node_modules',)  write node_modules        DENY -> ALLOW
    allow=('.venv',)         write .venv               DENY -> ALLOW
    allow=('deploy.pem',)    write pem_link            DENY -> ALLOW   （symlink 解析到被豁免目标）
    allow=('.env',)          write .env_link           DENY -> ALLOW   （同上）
    allow=('.env','sub/.env') write sub/../.env, ./sub/.env, sub/./.env, sub//.env   DENY -> ALLOW（规范化到被豁免路径）
```

**未翻转（两态一致的既有事实，逐条实测）**：`etcpasswd_link -> /etc/passwd` DENY；`escaper -> <OUTSIDE>/.env` DENY；`allow=('pem_link',)` 写 `pem_link` DENY；大小写 `.ENV`/`.Env`/`.eNv` 两态皆 ALLOW；前后缀近似 `.envx`/`x.env`/`my.env`/`deploy.pem.bak`/`deploy.pemx` 两态皆 ALLOW，`xdeploy.pem` 两态皆 DENY；多级相对 `../outside/.env`、`sub/../../outside/.env`、`/etc/passwd`、`<OUTSIDE>/.env` 全部 DENY。**这些「ALLOW」都是变更前既有**（`is_denied` 本就不覆盖 `.envx`/`*.pem.bak` 这类名字），差分证明与 allowlist 无关。

> **勘误 R1**：R1 §4「附加对抗探针」里那句「`allow=('deploy.pem',)` 时经链接写 `pem_link` ⇒ deny（解析后 rel 不匹配）」**是错的**——实测为 **ALLOW**（`assert_within_workspace` 先解析 symlink ⇒ rel 落在被豁免的 `deploy.pem` 上）。安全属性不因此受损：resolve-then-judge 意味着链接只能打开「它解析到的那个目标」，而该目标本身必须在清单里；`allow=('pem_link',)`（写链接名而非目标名）反而 DENY。R1 的方向结论对，举证句错，此处更正以免后续读者照抄。

**⑦ 变异探针（证明测试网不是空转）**

```
MUT-B  _allow_covers 把越界绝对路径按 basename 回退（模拟「护栏感知附加根」）
       -> TestAdditionalRootIsRootBlind::test_additional_root_writes_stay_denied_in_guard FAILED   ✔ 被杀
MUT-C  忽略注入的 denied_patterns（回退 I-4）
       -> TestGuardUsesPolicyDenyTable::test_custom_deny_table_is_honoured FAILED                  ✔ 被杀
MUT-D  write_allowlist_covers 无视结构性 deny（恒 return True）
       -> 12 failed（含 test_write_allowlist_never_overrides_structural_deny ×10）                 ✔ 被杀
```

---

### R2-7. 本轮测试与门禁的原始行

```
$ uv run --extra dev pytest -q --basetemp=/home/happy/wl-basetemp-rev2 -p no:randomly
FAILED tests/agent/commands/test_session_workspace.py::test_session_workspace_add_nonexistent_path
FAILED tests/agent/tools/test_sandbox_backends.py::test_contract[docker]
2 failed, 4459 passed, 8 skipped, 110 warnings in 1025.86s (0:17:05)

$ uv run --extra dev pytest -q <4 个受影响测试文件>
623 passed in 12.00s

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)          # EXIT=0

$ PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py
ERROR: guard-write-allowlist: review manifest missing:
  openspec/changes/guard-write-allowlist/reviews/building-review-manifest.json   # EXIT=1

$ git diff --name-only fd6d581..HEAD | grep -c '^\.github/'   -> 0
```

**两条失败的独立归因（我自己复现，不照抄简报）**：

- `test_session_workspace_add_nonexistent_path`：**`--basetemp` 落点决定**。`--basetemp=/home/happy/wl-basetemp-rev2`（`/tmp` 之外）⇒ `1 failed`；`--basetemp=/tmp/pytest-rev2-bt`（`/tmp` 之内）⇒ `1 passed`。另在**基线副本** `/tmp/wl-r2/base` 上逐字同样失败。⇒ 非本 change 引起。`/tmp/.git`（空目录）确实存在，与本仓 `TestFindScopeRoot` 的既知污染一致（本轮该组未失败，因为我把 basetemp 移出了 `/tmp`）。
- `test_contract[docker]`：**负载诱发**。单独跑 ⇒ `1 passed in 11.43s`；全量并发跑 ⇒ 失败。该用例属 sandbox backend 契约面，与本 change 的 diff 面（只多传一个 kwarg，且默认态等价已独立证明）无关。

**artifact checker 本轮 EXIT=1 的说明**：不是回归。`_check_review_manifests`（`scripts/check_openspec_artifacts.py:1150-1153`）会遍历 `reviews/*-review.md` 并**对每一份**要求 manifest——R1 的 `building-review.md` 已在 `6a43aee` 入库，于是活跃 change 现在必须有 `building-review-manifest.json`。按流程该 manifest 只在 **PASS** 时写；本轮 verdict 非 PASS，**故仍然没有**，checker 保持红——这与归档点门禁的设计一致（`--check-archived` 与活跃门是两套）。

---

### R2-8. 本轮新增问题清单

| # | 级别 | 位置 | 问题 | 修法 |
|---|---|---|---|---|
| **N-1** | **阻塞**（文档事实错误） | `openspec/changes/guard-write-allowlist/design.md:97` | 尾句断言「并有 `tests/agent/test_config.py` 的逐条用例」，实测**计数 0**（`6a43aee` 未触碰该文件；`a//b`/`a/./b`/`a\b` 全仓测试零命中）。提交信息同款断言。 | 补 4 条 `parametrize` 用例（推荐），或删掉该尾句与提交口径里的「逐条测试」。 |
| **N-2** | Nit（行为/口径不符） | `agent/workspace_policy.py:445-452` | 空 allowlist + 越界路径：旧实现返回 `False`，新实现抛 `PermissionError`（`:450` 无条件先 `assert_within_workspace`）。方向 fail-closed、无调用方，但与「无行为变更」不符。 | 恢复旧顺序，或在 design 记一句。 |

**其余维度（相对 R1 无新变化，此处不复述）**：冗余度、可维护性、CI 完整性三项我本轮复查仍成立——`.github/` 零改动；新谓词仍由两层共享单一实现（`command_guard.py:41` 导入 `write_allowlist_covers`），I-4 的修法正是把「共享」从谓词推进到了 deny 表，方向一致。

---

### R2-9. 结论

**离 PASS 只差 N-1 一句事实错误**（N-2 可选）。本轮的实现质量与安全面与 R1 结论同级甚至更严：`DEFAULT-STATE IDENTICAL` 217 行 0 差异、读侧 0 翻转、读源 0 翻转、结构性 deny 0 泄漏，且四个变异探针全部被测试网杀死——**新增的那两个测试类是真守门的，不是装饰**。I-1 的归因订正尤其到位：作者先自己实测证伪了 design 原先的混合归因（这一点**比 R1 的举证更准**），再把规格、设计、断言三处同步改齐。

> **不写 manifest**：按流程只在 verdict = `PASS` 时写 `building-review-manifest.json`；本轮 verdict 仍为 `CHANGES_REQUESTED`，**未写**。

---

## R1（revision 340c90e，已被 R2 取代）

- **Verdict**: `CHANGES_REQUESTED`
- **Reviewer**: 独立零记忆审阅者（不继承开发上下文），2026-10-14
- **Diff span**: `fd6d581`（`git merge-base HEAD origin/master`）..`340c90e`（HEAD）
- **审阅对象**: 26 文件 / +2089 −8，含 `openspec/changes/guard-write-allowlist/` 全套文档
- **方法**: 逐文件读实现 + 在隔离副本（`git archive` → `rm .git && git init`）跑**基线↔HEAD 差分探针**与**翻转枚举探针**；全称否定一律用「计数/枚举」口径，未使用 `head` 截断。

---

## 1. Verdict 摘要

**安全面五条核心主张全部独立复现通过**，无一处放宽泄漏；任务真实落地；规格 delta 与 current spec 同步完整；CI 未被弱化。
判 `CHANGES_REQUESTED` 的**唯一实质原因**是：一条 **spec Scenario 在「附加根」这一路径族上不被实现满足**，且该差异在 spec 里没有被 carve out（`openspec/specs/` 是绑定 artifact，design 里的口头豁免读者看不到），同时 design 对该差异的**机制归因有误**。另有两条「实现超出裁定但未回写文档」的记录完整性问题。**均为文档/规格精度问题，无安全影响、无行为缺陷。**

---

## 2. Tasks Verification（逐条核对 `[x]` 的**真实性**，读代码而非文件名）

### 第 0 节（设计门）
| 任务 | 结论 | 证据 |
|---|---|---|
| 0.2 / 0.3 | ✅ 真实 | `reviews/grill-design.md` 有 `## User Confirmation`（Q1–Q12 逐条）；`design.md` 有 `## User Rulings`（U1–U12）。机械证据：artifact checker（`_unconfirmed_open_questions`）本轮 exit 0 |
| 0.4 | ✅ 真实 | `reviews/grill-adversarial.md` 存在且含 R1→R2→R3 三轮，R3 判 PASS |
| 0.5 | ✅ 真实 | U1–U12 生效口径已落 `design.md`，U10 顺序（规格随裁定）在 1.1/1.2 的 delta 文本中体现 |

### 第 1 节（规格）
| 任务 | 结论 | 证据 |
|---|---|---|
| 1.1 | ✅ 真实 | delta `specs/workspace-safety/spec.md` 含 5 条 ADDED（`:5/:57/:80/:111/:136`）+ MODIFIED「工作区策略支持配置扩展」（`:155`） |
| 1.2 | ✅ 真实 | delta `specs/configuration/spec.md:5` |
| 1.3 | ✅ 真实 | `openspec/specs/workspace-safety/spec.md` +157 行（5 条新 Requirement + MODIFIED 重写 + 新增 Scenario）、`openspec/specs/configuration/spec.md` +25 行；事件 `workflow-events.jsonl` seq 4/5 `current_spec_synced` 齐 |
| 1.4 | ✅ 真实 | delta 与 design 同向，未见「只改设计不改规格」 |

### 第 2 节（测试先行）
| 任务 | 结论 | 证据（含我独立复算的计数） |
|---|---|---|
| 2.1 / 2.2 / 2.3 | ✅ 真实 | `tests/agent/test_workspace_policy.py:451-583` 正例/否定/默认态三组齐 |
| 2.4 / 2.5 / 2.5b / 2.6 / 2.7 | ✅ 真实 | `tests/agent/tools/test_command_guard.py:929-1098`；我独立复现：带 `.env` allowlist 时 `cp x .env`/`echo K >> .env`/`tee .env`/`dd of=.env` 全部 `ALLOW`；`cp .env /tmp/out` 仍 `DENY[cp_source]`、`mv .env /tmp/out` 仍 `DENY[mv_source]` |
| 2.8 | ✅ 真实 | `tests/agent/test_config.py:921-970`（含对 `DEFAULT_DENIED_PATTERNS` 逐条复算断言） |
| 2.9 | ✅ 真实（**我独立重算了计数**） | 攻击集 73 case / 69 guard-deny case；**无 allowlist 时 0 条未被拦；带无关 allowlist 时仍 0 条未被拦**；带 `.env`+`.env.local` 时恰好翻转 11 条，与测试硬编码集合逐字一致 |

### 第 3 节（实现）
| 任务 | 结论 | 证据 |
|---|---|---|
| 3.1 | ✅ 真实 | `agent/workspace_policy.py:131/:142/:169` 三个模块级谓词；**未**用覆写 `denied_patterns` 的伪实现（符合 Decision 1） |
| 3.2 | ✅ 真实 | `agent/tools/command_guard.py:724-749`（`_allow_covers`）+ 六个写目标挂钩点 `:980/:1003/:1040/:1170/:1204/:1219`；三条排除项均核对：`check()` 第 1 步整句扫描未动、`mv/cp` 源位置 `:1110` 走 `allow_write=False`、`_check_rm` 逐字节未改 |
| 3.3 | ✅ 真实 | `agent/tools/builtin/bash.py:86-92` 传 `self.policy.allowed_write_paths` |
| 3.4 | ✅ 真实 | `agent/config.py:158` 字段 + `:1953` `_parse_allowed_write_paths`（复用 `_parse_string_list`） |
| 3.5 | ✅ 真实 | 三处生产构造点 `agent/main.py:254` / `web/session.py:1731` / `benchmarks/agent_runner.py:352`；**并已核对下游不漏传**：`main.py:271`、`web/session.py:1734`、`agent_runner.py:356`、`agent/subagent/manager.py:1281` 的 registry、`agent/tools/factory.py:335/:457` 的 `BashTool(policy=policy)` 全部串上 |
| 3.6 | ✅ 真实 | `asterwynd.example.yaml:36-48` 用裸名 `['.env']` + 注明 deny 默认/精确覆盖/不接受 glob/嵌套 `cp`/`mv` 边界 |
| 3.7 | ✅ 真实 | `assert_write_allowed`（`:446`）接；`assert_read_allowed`（`:441`）、`is_denied`（`:401`）、`repo_map` 跳过判定均**未**接 |
| 3.8 | ✅ 真实 | `agent/browser/policy.py:121-123` 委托 `workspace_policy.assert_write_allowed` ⇒ 继承豁免，属预期 |
| 3.9 | ✅ 真实 | `agent/tools/builtin/subagents.py:2005` 仍 `WorkspacePolicy(workspace_root=sandbox)`，**未**传 allowlist |

### 第 4 节（验证）
| 任务 | 结论 | 证据 |
|---|---|---|
| 4.1 | ✅ 真实 | 全量 `4456 passed, 8 skipped`，唯一 1 failed 是**环境性**（见 §5，已在基线副本逐字复现） |
| 4.2 | ✅ 真实 | 我复跑 `Totals: 30 passed, 0 failed (30 items)` |
| 4.3 | ✅ 真实 | 我复跑 `OpenSpec artifact checks passed`（exit 0） |
| 4.4 | ✅ 真实 | 我在**完整 clone**（`/tmp/wl-clone`）复跑 benchmark-gate：`success_rate: baseline=1.0000 current=1.0000 delta=+0.0000 / result: PASS` |
| 4.5 | ✅ 真实（**我独立复现了 `DEFAULT-STATE IDENTICAL`**） | 见 §4，两轮差分共 265 行判定、0 行不同 |

### 第 7 节
| 任务 | 结论 |
|---|---|
| 7.1 | ⚠️ **部分**：① 已改（`docs/interview-script/walkthrough/W06-security.md:35` 补例外句，口径准确）；U6 债务已落 `docs/known-debt.md:480-489` + `protected_artifact_explained` 事件（seq 6）。但 ②③④⑤ 的结论写的是「记债务」，**仓库里没有任何落盘的债务条目**（见 I-3） |

### 第 5/6 节
`5.1`（本报告）、`5.2`、`6.1`–`6.9` 未勾，属收尾/阶段 B，符合预期。

---

## 3. Issues

### I-1（**Must fix**，Medium）附加根路径族上「两层同向变化」这条 spec Scenario 不被实现满足，且 spec 未 carve out

**证据链**

1. spec 把 allow 条目的作用域定义为**根无关**：`openspec/specs/workspace-safety/spec.md:548`「条目 SHALL 按「**任一 workspace 根**」的相对路径匹配（主 workspace 与附加根一视同仁）」，并配 Scenario `:577`（`Write /srv/other/.env` SHALL 放行）——文件工具层**确实**放行（我实测：`assert_write_allowed(extra/'.env') -> ALLOW`，与 `tests/agent/test_workspace_policy.py:565-575` 一致）。
2. spec `:650` Requirement「可写豁免不使任何一层比引入前更宽」把「写目标判定面」定义为**含**重定向/`mv`/`cp`/`tee`/`dd of=` 目标判定，排除项**只有** ①②③；其 Scenario `:660` 断言：allow 命中 + 护栏侧拒绝来源属可挂钩面 ⇒ **两层都从拒变放行**。
3. 实测（隔离副本，主根 `/tmp/wl-ar-*/repo`、附加根 `/tmp/wl-ar-*/other`、`allowed_write_paths=('.env',)`）：

```
file-tool Write /tmp/wl-ar-u1bthyio/other/.env   -> ALLOW
  guard DENY   [denylist]            cp x /tmp/wl-ar-u1bthyio/other/.env
  guard DENY   [protected_redirect]  echo K >> /tmp/wl-ar-u1bthyio/other/.env
  guard DENY   [tee_target]          tee /tmp/wl-ar-u1bthyio/other/.env
  guard DENY   [dd_target]           dd of=/tmp/wl-ar-u1bthyio/other/.env
  guard ALLOW  [None]                cp x .env
```

`protected_redirect` / `tee_target` / `dd_target` **都在** spec 定义的「写目标判定面」内，故 `:660` 的 Scenario 被违反（对照组：主根下 `echo K >> config/.env` 是 ALLOW）。
4. 根因：`agent/tools/command_guard.py:724-749` 的 `_allow_covers` 只持有**主 workspace**（`:736` 要求 `self._workspace` 非空，`:738-742` 用 `_within(normalized, workspace)` 判定，`CommandGuard` 接口上根本没有 `additional_roots`）；而 `WorkspacePolicy.relative_path` 对附加根返回根相对路径。
5. **design 对该差异的机制归因有误**：`openspec/changes/guard-write-allowlist/design.md:256` 写「Bash 层 `cp x /srv/other/.env` 实测 `last_reason=denylist`——先命中 `command_guard.py:609` 的**不可挂钩**整句正则，与 U7 的嵌套路径缺口**同源**」。这只对 `cp`/`mv` 成立；`>>` / `tee` / `dd of=` / `install` 的拒绝来源**不是** denylist 整句正则，而是护栏看不见附加根。即该条恰恰**不在** ①②③ 的 carve out 内。
6. 无测试钉住：`tests/agent/tools/test_command_guard.py` 中 `add_root|附加根|additional` **零命中**。

**为什么算问题**：本 change 的核心交付就是「**如实**划定兑现面」（design Decision 9 的原话）。Decision 9 的嵌套路径缺口被专门写了断言钉住，附加根这条却没有；而读者若只看 `openspec/specs/`（绑定 artifact），会读到一条实现并不满足的 Scenario。

**建议修法（不扩范围，与 U7/U9 的既有裁定一致）**：
- 在 spec 的 `:650` Requirement 排除项里**增列第 ④ 条**「命令护栏不感知附加根（`CommandGuard` 只持有主 workspace）」，或在 `:660` Scenario 加 NOTE；
- 修正 `design.md:256` 的机制归因（区分 `cp`/`mv` 的 denylist 与其余四形的 root-blindness）；
- 按 Decision 9 的同款做法**补一条断言**（带 `.env` allowlist 时，附加根下四个写形态仍 DENY，注释写明是规格行为），并同步 current spec。

### I-2（**Must fix**，Low）配置解析拒绝「非规范拼写」是超出 U2/Decision 3 的实现选择，只活在代码里

- U2（`design.md:187-193`）与 Decision 3（`:88-99`）点名的非法值只有四类：glob 元字符 / 绝对路径 / `..` 段 / 尾 `/`。
- 实现额外拒绝：前导 `./`、`//`、`a/./b` 等非规范拼写（`agent/config.py:1983-1986`）与反斜杠分隔（`:1988-1990`）。实测：

```
REJECT  './.env'   REJECT  'a//b'   REJECT  'a/./b'
REJECT  'a\\b'     REJECT  '.'
ACCEPT  '.env'  ACCEPT  'config/.env'  ACCEPT  ' .env' -> ('.env',)  ACCEPT  '.env ' -> ('.env',)
```
（`_parse_string_list` 已 `strip()` 并丢弃空串，故空白不会伪装成合法条目——这点值得肯定，它堵住了这一类「非规范 ⇒ 静默 no-op」。）

**判断：这条实现选择**合理，不该回退**。理由：(a) 这类条目**永远匹配不上** `relative_path()`，接受它就是给一个**安全白名单**制造静默 no-op——本能力最坏的失败模式；(b) 不误伤任何**功能性**配置：一切能表达的有效路径都有规范写法；(c) 报错可操作（提示「drop the leading `./`」）；(d) 与本能力「非法值 fail fast」的一贯口径一致。
**但**：它未被回写进 `design.md` 的 Decision 3 / U2，也不在 spec delta 里，只在 `agent/config.py:1945-1990` 的注释与 `tests/agent/test_config.py:946-957` 中。本 change 自订的 U10 是「规格随裁定改、design 与规格同向」，实现期新增的解析规则应至少补进 Decision 3（一句话即可），否则 future reader 会把它当成过度实现。

（同类但**无需改**的一条，一并记录以免误判：`.env.example` / `.env2` / `.envrc` / `app.env` / `.ENV` 在两层都被放行——我已在基线副本逐条复现，**全部是变更前既有行为**（见 §4 差分），不是本 change 的放宽。）

### I-3（Low）任务 7.1 的 ②③④⑤ 结论是「记债务」，但没有任何落盘债务记录

- `tasks.md:7.1`（第 7 节）列出五处文档命中，其中 ②③④⑤ 的结论是「变更前就存在…按 AGENTS.md **记债务**即可」。
- 我实测确认这些口径问题**确实是既有的**：`DEFAULT_DENYLIST` 在 `fd6d581` 上已经是 **59**（文档写 58）、`DEFAULT_DENIED_PATTERNS` 已经是 **32**（文档写 35）。故「不属于本 change 造成的事实变化」这个判断成立。
- 但 `docs/known-debt.md` 本轮只新增了 U6 那条（`:480-489`），②③④⑤ 在任何地方都没有落成债务条目（`grep "58 个|35 条" docs/known-debt.md docs/known-issues.md` 零命中；`AGENTS.md` 的「当前文档债务」段也未变）。
- 任务文本自身的硬要求（「必须在本任务里被显式列出并给出结论」）**已满足**，故判 Low 而非 Must fix；建议要么把四处在 `docs/known-debt.md` 落成一条（配 `protected_artifact_explained` 事件），要么把 7.1 的措辞从「记债务」改成「已在 tasks 记录结论、不落债务表」以免读成已执行。

### I-4（Low/Nit）`CommandGuard` 侧的结构性 deny 用的是默认表，不是 policy 的 `denied_patterns`

`agent/tools/command_guard.py:749` 调 `write_allowlist_covers(rel, self._allowed_write_paths)`，吃默认参数 `DEFAULT_DENIED_PATTERNS`；policy 侧 `agent/workspace_policy.py:444` 传的是 `self.denied_patterns`。当前**不可达**（`denied_patterns` 不是配置项、生产恒为默认），故无实际影响；但若日后把 `denied_patterns` 接进配置，两层对「什么算结构性 deny」会用两张表。建议把 `denied_patterns` 一并传进 `CommandGuard`，或加注释说明为何不需要。

### I-5（Nit）`WorkspacePolicy.is_write_allowed` 无外部调用方且重复解析

`agent/workspace_policy.py:433-444` 是新增 public 方法，全仓唯一调用方是 `assert_write_allowed`（`:446-455`），而后者已先做过 `assert_within_workspace`（`:447`），方法内又做一次（`:442`）。功能无误（`is_denied` 也具 public 形态），仅提示 API 面与一次多余的 `resolve()`。

---

## 4. 安全面：核心主张的独立验证（**逐条实测，非推理**）

方法：隔离副本 `/tmp/wl-base`（`git archive fd6d581`）与 `/tmp/wl-review`（`git archive HEAD`），各 `rm -f .git && git init -q`；用同一组探针脚本跑两棵树后 `diff`。

### 主张 1 — 默认空列表下与改动前**逐字节等价**（`DEFAULT-STATE IDENTICAL`）→ ✅ **独立复现 True**

```
$ diff <(tail -n +2 /tmp/out-base.txt) <(tail -n +3 /tmp/out-head.txt)
*** IDENTICAL: 0 differing rows across 123 enumerated verdicts ***
# base header: "# allowed_write_paths attr present: False"
# head header: "# allowed_write_paths attr present: True" / "# default allowed_write_paths = ()"

$ diff /tmp/wide-base.txt /tmp/wide-head.txt
*** WIDE DIFFERENTIAL: 0 differing rows (DEFAULT-STATE IDENTICAL) ***
# verdict rows base=142 head=142（61 路径 × write/read/is_denied + 81 命令，含 launcher/eval/heredoc/quoted/$HOME/..env 形态）
```
即 **265 行判定、0 行不同**。代码上也自洽：`is_write_allowed` / `_allow_covers` 都在空列表时立即返回 `False`。

### 主张 2 — allow **只**放行清单内精确路径 → ✅ 成立（枚举口径）

对 54 条路径 × 3 判定 + 58 条命令做「带/不带 allowlist」全枚举差分：

```
--- file-tool WRITE layer: flips ---
write flips: 4 -> [('.env','deny->allow'), ('config/.env','deny->allow'), ('deploy.pem','deny->allow'), ('./.env','deny->allow')]
--- file-tool READ layer: flips ---   read flips: 0
--- is_denied: flips ---              is_denied flips: 0
--- Bash layer: flips ---             command flips: 11（全部 DENY->ALLOW，全部命令文本含被列入路径）
  flips that are not deny->allow on a command mentioning an allowed path: 0
  allow->deny flips: 0
```
`./.env` 是 `.env` 的规范化解（`_allow_covers` 的 `_normalize_path` + 去前导 `./`），**非泄漏**。负向：`.env.local` / `.env.production` / `src/.env` / `x/config/.env` / `config/.env.bak` / `configX/.env` / `/etc/passwd` / `ws/../outside/.env` 全部仍拒（我逐一实测，`/etc/passwd`、`../outside.env` 亦在 `tests/agent/test_workspace_policy.py:536-543` 钉住）。

另：**无关 allowlist 对 56 条默认拒绝语料的翻转数 = 0**：
```
default-denied corpus size=56  flipped_by_unrelated=0 []
```

### 主张 3 — **读侧未被放宽** → ✅ 成立

- 读判定：`read flips: 0`（含 `.env` / `config/.env` / `.env.local` / `.git/config` / `deploy.pem` 全拒）。
- `is_denied`：`is_denied flips: 0`（两份 policy 对同一路径结论恒同）。
- 索引面：`_should_ignore(ws/'.env', with_allow, ()) is True`（`agent/code_intelligence/repo_map.py` 跳过判定不感知 allowlist）。
- `is_write_allowed:433` 只在 `assert_write_allowed:446` 求值；`assert_read_allowed:441` 逐字节未改。

### 主张 4 — `mv`/`cp` 的**源位置**未因 allow 而放行 → ✅ 成立（**实测**）

专门构造 47 条**读源**命令（含 `cp/mv/install` 源位置、`-f`/`-r`/`--`、`env`/`nohup`/`nice`/`timeout`/`sudo`/`doas`/`xargs` 包装、`bash -c` / `sh -c` / `eval` / heredoc 嵌套通道、`dd if=`、`<` 重定向、`rsync`/`ln`/`tar`/`base64`/`curl -T`/`curl -d @`/`scp`/`nc`）：

```
allowlist (write-only) = ('.env', 'deploy.pem', 'id_rsa', 'config/.env', '.git/config')
read-source command corpus = 47
flips caused by the write allowlist among READ-SOURCE commands: 0
```
即**没有任何读源命令因写豁免而变宽松**。（该组里 21 条两态皆 ALLOW 的，是 U6 已记账的 Bash 读侧既存缺口，非本 change 引入——我已在基线副本确认其两态一致。）
代码侧佐证：`agent/tools/command_guard.py:1110` 的源位置调用**不带** `allow_write`，`:967-972` 的默认值为 `False`。

### 主张 5 — 结构性 deny **永不翻转** → ✅ 成立（两源枚举）

```
structural patterns (16): ['.git/**','**/id_rsa','**/id_ed25519','**/id_ecdsa','__pycache__/**','**/__pycache__/**','node_modules/**','**/node_modules/**','.venv/**','venv/**','.mypy_cache/**','.pytest_cache/**','.ruff_cache/**','benchmarks/runs','benchmarks/runs/**','.asterwynd/worktrees/**']
D1 16/16 条：即便把该 pattern 的具象路径**显式列入 allowlist**，仍全部 deny
D2 9 个 SENSITIVE_DOTDIRS × 3 形态 = 27/27：仍全部 deny
```
正对照（防止「把 deny 表清空让一切可豁免」的伪实现）：16 条 `/`-free 的文件级 deny 条目（`*.pem`/`id_rsa`/`*.pyc` …）确可被覆盖：`allow pattern '*.pem' -> probe 'x.pem'` 等 16/16 allow（唯 `.git`/`__pycache__`/`node_modules`/`.venv` 等裸目录名也被划为文件级——这与 design.md:284 自陈的「8 条裸目录名被划成文件级」一致，且**不构成泄漏**：`write_allowlist_covers` 要求**精确等于**清单条目，一个条目只能开一条路径，开不出子树）。

### 附加对抗探针（全部 fail-closed）

- **符号链接**：`allow=('pem_link','etcpasswd_link','.env')`，`pem_link -> deploy.pem` ⇒ deny；`etcpasswd_link -> /etc/passwd` ⇒ deny；`allow=('deploy.pem',)` 时经链接写 `pem_link` ⇒ deny（解析后 rel 不匹配）。即「resolve-then-judge」方向正确，无 symlink 逃逸。
- **相对路径规范化**：`cp x x/../.env` / `cp x .//.env` / `cp x ./\\.env`（`_expand_obfuscation` 归一为 `.env`）⇒ deny 与 allow 落在**同一个归一化路径**上，无「deny 判 A、allow 匹配 B」的错位。
- **越界绝对路径**：`_within` 是**段边界感知**的（`command_guard.py:114-122`），`cp x {WS}-evil/.env` ⇒ deny（非前缀误判）。
- **大小写**：`.ENV`/`.Env` 两层皆 allow —— 基线副本逐字复现，**既存行为**。
- **攻击集**：69 条 guard-deny case 在无关 allowlist 下翻转 **0** 条。

---

## 5. Test Results（我独立复跑的**原始行**）

```
$ uv run --extra dev pytest -q --basetemp=/home/happy/wl-basetemp-review -p no:randomly
FAILED tests/agent/commands/test_session_workspace.py::test_session_workspace_add_nonexistent_path
1 failed, 4456 passed, 8 skipped, 110 warnings in 895.52s (0:14:55)

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)          # EXIT=0

$ PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py
OpenSpec artifact checks passed                  # EXIT=0

$ cd /tmp/wl-clone && asterwynd benchmark-gate benchmarks/tasks/gate-smoke --source-repo . \
      --runs-dir /tmp/wl-gate-runs-clone --baseline benchmarks/baseline.json --require-baseline --skip-p95
BENCHMARK GATE
  success_rate: baseline=1.0000 current=1.0000 delta=+0.0000
  result: PASS                                    # EXIT=0

$ cd /tmp/wl-review && pytest -q <新增/扩展的 4 个测试文件>
619 passed in 8.29s
```

**唯一失败项的归因（独立验证，非照抄）**：
- `test_session_workspace_add_nonexistent_path`：该用例假设 `tmp_path` 落在 `/tmp` 之下（`/tmp` 是 workspace 根的祖先 ⇒ 期望「无法添加」）。我按隔离纪律把 `--basetemp` 设在 `/tmp` 之外（`/home/happy/wl-basetemp-review`），祖先关系消失 ⇒ `已添加 workspace: /tmp`。**三重证据**：(a) 同一用例在**基线副本** `/tmp/wl-base` 上逐字同样失败（`1 failed, 11 passed`）；(b) 把 `--basetemp` 放回 `/tmp` 下（`/tmp/pytest-review-bt`）则 `12 passed`；(c) 与本 change 的 diff 面（未触及 `session_workspace` 命令）无关。⇒ **非本 change 引起**，CI（默认 basetemp）不受影响。
- `test_contract[docker]`：本轮**未**复现（此前并发负载下出现过）；`TestFindScopeRoot` 两条也未出现（本机 `/tmp/.git` 空目录 + 我把 basetemp 移出 `/tmp` 共同导致）。与任务简报一致。
- 早前我在 `git archive` 副本里跑 benchmark-gate 得 `current=0.0000 / FAIL`，根因是副本无 git 历史（`git worktree add ... 7c6fc3e` exit 128，`setup_error`），**基线副本同样 FAIL**；换成完整 clone 即 PASS（上方原始行）。属复现方式的环境假象，**非回归**。

---

## 6. 其余维度

- **冗余度（4）**：无重复实现。新谓词 `is_structural_deny_pattern` / `is_structural_denied_path` / `write_allowlist_covers`（`agent/workspace_policy.py:131/:142/:169`）由两层**共享**（`command_guard.py:41` 导入 `write_allowlist_covers`），未被各写一份，符合 Decision 2；与 `tools.command_denylist` / `ignore_patterns` / `permissions.profiles` 各司其职，无功能重叠。
- **可维护性（7）**：命名与既有 `is_denied` 同构；注释解释**为什么**（引用 U1/U2/U5/U8/U12 与 codex 先例、GlobPattern fail-closed 出处），非复述代码；`_parse_allowed_write_paths` 五段校验各有独立可读文案；`_allow_covers` 明确写出「只从写目标判定面调用，源位置与整句扫描刻意不调用」。I-4/I-5 为两处小瑕疵。
- **CI 完整性（8）**：`.github/` **零改动**（`git diff --name-only fd6d581..HEAD | grep -c '^.github/'` = 0）；`validate` job 仍跑 `uv run pytest -q`、编码 warn-as-error、`openspec validate --all --strict`、artifact checker、归档 manifest 校验；`benchmark-gate` job 未弱化。

---

## 7. 结论

实现**质量高、安全面干净**：五条核心安全主张（精确路径 / 读侧不放宽 / 源位置不放宽 / 结构性 deny 不翻转 / 默认态逐字节等价）我**全部独立复现通过**，且默认态等价性达到 265 行判定 0 差异；对抗探针（符号链接、规范化、越界、大小写、`$IFS`/引号/launcher/嵌套 shell）无一穿透。

判 `CHANGES_REQUESTED` 不是因为有安全洞或行为缺陷，而是因为 **spec 里有一条 Scenario 在「附加根」路径族上不被满足、且 spec 未 carve out**（I-1），加上两处「实现超出/偏离文档记录」的完整性问题（I-2、I-3）。三者的修法都很轻：改 spec/design 文字 + 补一条断言 + 补一条债务或改一句措辞，**均无代码行为变更**。修完即可 PASS。

> **不写 manifest**：按流程只在 verdict = `PASS` 时写 `building-review-manifest.json`；本轮 verdict 为 `CHANGES_REQUESTED`，**未写**。
