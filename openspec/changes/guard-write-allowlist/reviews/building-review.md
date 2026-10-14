# Building Review — guard-write-allowlist

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
