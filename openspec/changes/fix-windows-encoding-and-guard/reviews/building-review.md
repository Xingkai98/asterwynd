# Building Review: fix-windows-encoding-and-guard

**CHANGES_REQUESTED**

- **reviewer run id**：`building-review-fix-windows-encoding-and-guard-20261004-r1`
- **审阅时间**：2026-10-04T18:15+08:00（本机 Windows + 中文 locale `cp936`，即本 change 的目标环境；`sys.flags.utf8_mode=0`、`locale.getpreferredencoding(False)=cp936`）
- **审阅对象**：worktree `D:\code\asterwynd-worktrees\fix-windows-encoding-and-guard`，分支 `fix-windows-encoding-and-guard/2026-10-04`，HEAD `0575ee4a755284a0aaff80e820a384af703b1982`，base `da8621f08d2bd51be949304148a1e57b997a34b4`（=`master`）；审阅前后 `git status --porcelain` 为空
- **受控文件 sha256（HEAD 工作区）**

| 文件 | sha256（前 64 位） |
|---|---|
| `agent/session.py` | `dc26072d85c435f9686724879fda0e013fd2b65f0eeb1f2a98402d51268b315b` |
| `agent/main.py` | `581a9d4e9ddd193f00e33069628340a9033e0090b8a2e4ce41cec4c051e299df` |
| `tests/agent/test_session_encoding.py` | `24c689d344c29cc755a2e470ae35dab458ae3e52a91e17fbaee6316d34785790` |
| `tests/web_tests/test_encoding_hygiene.py` | `0cb654fdc0f7ae92f3af0e04367515153836c44ed698fa0925bb6617aca868ed` |
| `tests/web_tests/test_multi_session.py` | `dad6fa7436ea9d6dd0369795a605388f0c3bc88e8c998bcf6ec208795ff5b502` |
| `openspec/changes/fix-windows-encoding-and-guard/tasks.md` | `476c29c9afa9cae7619296f2a9c961f15a9c5ed73e9563ffec97bb1e43166a45` |
| `openspec/changes/fix-windows-encoding-and-guard/proposal.md` | `252cd7a4f0944602d86b95a9e62ab29065797737392c7ba04971da9d854cdeda` |
| `openspec/changes/fix-windows-encoding-and-guard/diagnosis.md` | `3cf625b7a6e55e805e7f535c87e84c3d58c0906db42ac80efbe283a4923179bf` |
| `openspec/changes/fix-windows-encoding-and-guard/specs/web-ui/spec.md` | `8bba6dae2cbf7348d0f96734119b759391ef68ddeb7dd0cb2b13d3986dbf5a2e` |
| `openspec/changes/fix-windows-encoding-and-guard/workflow-events.jsonl` | `552b7fe28447c977b0e3a0b29625a4765eacbf3848f0a11308b3328073e252b5` |
| `openspec/specs/web-ui/spec.md`（未改动） | `08b1680621af94e33240295733a49e20c84d796b55ee093d84159660700b582f` |
| `.github/workflows/ci.yml`（未改动） | `1c321ad9bac7d0ff44ca4c7ec255443fdb8991398787896617c9cffacd326f83` |
| `docs/testing-guide.md`（未改动） | `e2016caffb5cc4653015de6ebbdc127ce50f5bbd439b29a5375dbe9a0a01da25` |
| `docs/openspec-change-backlog.md`（未改动） | `50efd26f7fc55f35e8fa1745aae0a654a8836b13b788ddacf5899125f7a5590b` |

审阅判据：`PASS` 需 0 条 MUST-FIX。本报告给出 **8 条 MUST-FIX**（其中 3 条是「任务已勾 `[x]` 但产物不存在」）⇒ **CHANGES_REQUESTED**。

## 0. 审阅方法与本地限制

- **只读**：除本报告外未落盘任何仓库文件；为验证做的所有临时改动（变异 / 临时测试文件）均已**按字节还原**，还原后 sha256 与改动前一致，且全程结束后 `git status --porcelain` 为空。临时脚本与日志写在 `%TEMP%\aw-review\`（仓库外）。
- **不采信实现方自述**：批量保真用我自己写的「逐行字符级 diff + AST 父调用绑定」校验；spec delta 用 OpenSpec 1.4.1 **自己的** `buildUpdatedSpec`（`@fission-ai/openspec@1.4.1`，`dist/core/specs-apply.js:60`）算出重建结果再比对；守卫判据用自己的探针（synthetic 样例）复核。
- **全量 pytest 在本机不可完成**（进程在 45%~67% 处被资源限制杀掉，`[exit code: 1]` 无失败断言，属进程级终止）。因此全部结论来自分块验证：`tests/web_tests` 全量、基线 5 文件、7 路径对比块、若干单文件与单用例变异。
- 运行解释器：worktree venv `.venv\Scripts\python.exe`（3.12.10）；pristine 对比在 `D:\code\asterwynd` 下运行同一个 venv，并用插件打印确认 `agent.session` 解析到 `D:\code\asterwynd\agent\session.py`（未混用 worktree 代码，主仓未被修改）。

## 1. 复现与证据

### 1.1 批量改动保真（最高风险项）——**独立复核通过**

我的方法：对 `da8621f..HEAD` 的 72 个修改文件，把 base blob 与工作区文件做**行级** `difflib` 比对；对每个替换块再做**行内字符级**比对，要求差异只是插入 `, encoding="utf-8"`；再把每处插入偏移映射到 HEAD 的 AST，确认它是 `open/read_text/write_text/subprocess.run` 调用的**关键字参数**（不是插到内层调用）。

```
modified=72 added=7 deleted=0
新出现的 encoding="utf-8" 站点（base→HEAD 计数差）: 385
  ├─ 干净的纯插入 op（正则 + AST 双重确认）: 382
  ├─ 字符级对齐伪差异（人工核对后同样为纯插入）: 2
  └─ 落在 session.py 结构性 hunk 内的 1 处: 1（agent/session.py:256，该 hunk 同时新增 2 行注释故行数不等长）
MISMATCH(插入无法唯一对应到 AST keyword，或父调用不在允许集合): 0
parent funcs（382 处纯插入的父调用分布）: {'write_text': 246, 'read_text': 127, 'open': 8, 'run': 1}
not-last-kwarg count: 0
改动 .py 文件 ast.parse: 74 个改动 .py，0 失败
```

- 2 处被我第一版正则判为「异常」的行是**字符级对齐方式**导致的假警报，人工核对确认插入内容就是 `, encoding="utf-8"`：
  - `tests/agent/tools/test_worktree_tools.py:233`、`tests/web_tests/test_multi_session.py:303`
  - `tests/benchmark/test_benchmark_runner.py:19/33/66/78`（同一行内嵌套调用插了 2 处：`target.write_text(target.read_text(encoding="utf-8").replace(...), encoding="utf-8")`，AST 校验确认两处分别绑定到 `read_text` 与 `write_text`）
- 结构性改动只有两处文件、共 12 个 hunk：`agent/session.py`（降级分支 + 注释）与 `tests/web_tests/test_multi_session.py`（平台假设修正）——与 change 声明一致，**没有第三处内容漂移**。
- 「插错位置」风险已被排除：`not-last-kwarg=0` 且每条插入唯一对应某个允许调用的 keyword 节点（若插进 `os.path.join(a, b, encoding=...)` 这类内层调用，会立刻报父调用不在允许集合）。
- 交叉验证（强证据）：**把 L1 守卫的扫描逻辑指向 pristine 树**，恰好报 **385** 个 offenders；指向分支工作区报 **0**。而我从 base→HEAD 独立数出的新增 `encoding="utf-8"` 也正是 **385** 处（378 文件 I/O + 1 node harness + `agent/session.py` 6 处）。
```
=== D:\code\asterwynd: scanned 413 files -> 385 offenders ===
      32  tests/benchmark/test_benchmark_runner.py
      ...
        sample: ['agent/main.py:922: write_text() 未指定 encoding=', 'agent/main.py:954: ...', 'agent/main.py:952: read_text() ...']
=== D:\code\asterwynd-worktrees\...: scanned 415 files -> 0 offenders ===
```

因此 tasks.md:20/23 的「379 处（文件 I/O 378 + node harness 1）」+「session.py 6 处」与实测**逐项吻合**：`378 + 1 + 6 = 385`。

### 1.2 范围修正（subprocess）——**通过**

用 AST 独立清点全仓 `subprocess.run/Popen/call/check_call/check_output(..., text=True)`：

```
base(da8621f): text=True 且无 encoding = 71 处，其中 node harness 恰 1 处（tests/web_tests/test_server.py:694）
HEAD(0575ee4): text=True 且无 encoding = 70 处，唯一被补的是 tests/web_tests/test_server.py:698 的 node harness
HEAD: text=True 且有 encoding = 8 处 = 7 处 node harness（6 处 base 已有）+ tests/agent/test_session_encoding.py:156（新增用例自己的 python 子进程，输出是纯 ASCII JSON）
HEAD: 非 node 的 text=True 子进程被补 encoding = 0 处 ✅
```

`tests/test_flow_policy.py` / `test_workflow_guard.py` 未被波及：两树该 5 文件块均 `9 failed, 66 passed`（完全一致）。tasks.md:20 的范围修正结论成立，且守卫 docstring（`tests/web_tests/test_encoding_hygiene.py:16-19`）与实现口径一致。

### 1.3 L1 守卫 —— 有牙齿；两处判据与 proposal/diagnosis 措辞不一致（见 §4 建议 1）

- 守卫本体：全仓 0 offenders；`ALLOWLIST` 为空字典（`test_encoding_hygiene.py:37`），无未说明理由的例外 ✅
- 牙齿（我自己的变异，全部还原）：去掉任一 `encoding=`（open/read_text/write_text/node harness）→ 守卫红；在被扫描文件**新注入**裸 `open()` 或裸 `read_text()` → 守卫红；把守卫自削弱（去 `Image` 排除 / 关 node 判据 / 关 read_text 判据）→ **自检用例红** ✅
- 假阴性方向未发现真实站点：`open(..., "rb")`、`gzip.open(..., "rb")`、fd 字面量形态、PIL `Image.open` 均按预期跳过；动态 mode 会被保守报出。
- 两处口径分歧（保守方向：多报不漏报，故不作为 MUST-FIX）：
  - `proposal.md:31` / `diagnosis.md:41` 称判据「排除 `rb/wb/ab`、`os.open`、fd 形态」，但**守卫并不排除 `os.open`**：探针里 `os.open('p', os.O_RDONLY)` 被报为「open() 的 mode 非字面量且未指定 encoding=」。
  - `_literal_mode`（`test_encoding_hygiene.py:63-73`）对**绑定方法** `Path.open()` 取了 `args[1]`（实际 `args[0]` 才是 mode），于是 `Path('x.bin').open('rb')` 被误报（探针实测）。

### 1.4 L2 行为回归 —— 写路径有效；**snapshot 降级分支未被覆盖且用例恒红**

```
$ .venv\Scripts\python.exe -m pytest tests/agent/test_session_encoding.py -q
1 failed, 8 passed
E  AssertionError: assert None is True
   where None = {'created_at': '', 'messages': 0, 'mode': 'build', 'session_id': 'sess_worse'}.get('damaged')
   tests\agent\test_session_encoding.py:117
```

根因（我用最小脚本复核）：

```
payload = json.dumps({"session_id": "sess_worse", "mode": "build"}, ensure_ascii=False)
gbk bytes : b'{"session_id": "sess_worse", "mode": "build"}'   ← 全 ASCII
decoded as utf-8 OK: {"session_id": "sess_worse", "mode": "build"}
```

该 fixture（`tests/agent/test_session_encoding.py:105-107`）声称造了一个「不可解码的 snapshot.json」，但载荷是纯 ASCII，`.encode("gbk")` 出来的就是合法 UTF-8 ⇒ 永远走**正常**分支 ⇒ 断言 `:117-118` 恒失败，`agent/session.py:172-181` 的 snapshot 降级分支**没有任何信号**。对照：`messages.json` 那条 fixture 含中文，`decode("utf-8")` 抛 `invalid continuation byte`，分支被真实覆盖。

该红是本 change 自己引入的（可复现）：

```
$ git show 2959990:tests/agent/test_session_encoding.py  →  Pytest: 9 passed
$ HEAD 版本                                              →  Pytest: 1 failed, 8 passed
```

即 commit `0575ee4`（"补 snapshot.json 降级分支的覆盖（变异 M2 原本存活）"）既引入了这条红，也没有真正补上该分支的覆盖（见 §5 M2/M7/M8）。

### 1.5 spec delta —— **MODIFIED 块会静默改写现行 spec（含一处与实现相反的陈述）**

用 OpenSpec 1.4.1 自己的 `buildUpdatedSpec` 重建（`counts={"added":0,"modified":1,"removed":0,"renamed":0}`）后逐块比对：

```
current spec: 56 requirements, 161 scenarios
built  spec : 56 requirements, 164 scenarios      ← Scenario 数 +3，未减少 ✅
requirements lost: []   requirements added: []
LOST scenario headers: '#### Scenario: run 结束后自动落盘' / '#### Scenario: 进程重启后按 id 恢复' / '#### Scenario: 未知 session id 回退新建'
NEW  scenario headers: '#### Scenario: run 结束后自动保存' / '#### Scenario: 按 session id 恢复' / '#### Scenario: 未知 session id 则新建' / +3 条本次新增
DIFF scenario: '#### Scenario: 刷新页面回到原 session'（GIVEN/THEN 被改写）
DIFF scenario: '#### Scenario: 显式恢复入口'（THEN/AND 被改写）
```

即 delta 头部第 3-4 行「本块**逐字保留**原 requirement 的全部 5 条 Scenario」与事实不符：3 条既有 Scenario 被**改名**、2 条正文被**改写**、requirement 正文被整段替换。

最严重的一处是**事实性反转**（会写进受保护 spec）：

| 来源 | 陈述 |
|---|---|
| delta `specs/web-ui/spec.md:10` | 「Web 默认 host 绑定**不得为** `127.0.0.1`，显式 `--host 0.0.0.0` 才开放局域网访问」 |
| 现行 spec `openspec/specs/web-ui/spec.md:397` | 「Web 默认 host 绑定策略为 `127.0.0.1`，显式 `--host 0.0.0.0` 才开放局域网访问」 |
| 实现 `agent/main.py:671` | `host: str = typer.Option("127.0.0.1", "--host", help="绑定地址")` |

delta 的 requirement 正文既不等于现行 spec，也不等于归档 change 的原文（`openspec/changes/archive/2026-08-09-web-multi-session-entry/specs/web-ui/spec.md:152` 与现行 spec `:397` **逐字相同**），是一段本次新写的改写稿，且把 host 绑定语义写反了。tasks 5.1 一旦执行同步，就会把这条矛盾写进 `openspec/specs/**`（受保护路径）。

### 1.6 平台假设修正 —— **通过（表达真实前提，不是放宽断言）**

```
$ (pristine) pytest tests/web_tests -q   →  9 failed, 521 passed, 8 skipped
   9 条红 = test_add_workspace_creates_directory_and_persists,
            test_add_workspace_rejects_sensitive_path[/, /etc, /etc/hosts, /dev, /root]（5 参数）,
            test_add_workspace_expands_tilde, test_add_workspace_rejects_nul_byte_path,
            test_api_sessions_rejects_case_variant
$ (branch)   pytest tests/web_tests -q   →  0 failed, 531 passed, 9 skipped
```

- 数字可完全对账：pristine `538 = 521 passed + 9 failed + 8 skipped`；branch `540 = 531 passed + 0 failed + 9 skipped`。差额 = 新增 2 条守卫用例（`test_encoding_hygiene.py` 两条，均 pass）+ 9 条平台红转绿 + `test_api_sessions_rejects_case_variant` 由 failed 转 skipped（`skipif(os.name=="nt")`，`test_multi_session.py:435-441`）；跳过理由「Windows 路径大小写不敏感 ⇒ 该用例前提不成立」成立。
- 断言**没有放宽**：`_sensitive_paths()` 改的只是参数取值，用例仍断言 `400` + 具体 `workspace_sensitive_path`（`test_multi_session.py:259-269`）；NUL 用例仍断言 `workspace_path_invalid`（`:272-283`）；`~` 展开只是补齐 `USERPROFILE`/`HOMEDRIVE`/`HOMEPATH`（`:173-181`）。且该组用例仍有牙齿：若 `_DENY_ROOTS`（`agent/workspace_policy.py:232`）被清空，用例会立刻红。

### 1.7 CI 与纪律文档 —— **产物不存在（tasks 4.1/4.2/4.3 却已勾选）**

```
$ git diff --stat da8621f..HEAD -- .github/workflows/ci.yml docs/testing-guide.md
(空)
$ Select-String -Path .github/workflows/ci.yml -Pattern "windows-platform|LC_ALL|PYTHONCOERCECLOCALE|PYTHONUTF8"
(无命中)
$ ci.yml 的 job 只有： validate(ubuntu-latest) / benchmark-gate(ubuntu-latest)
$ Select-String -Path docs\testing-guide.md -Pattern "平台与编码纪律|encoding|UTF-8|locale|平台"
(无命中；标题只有 基本原则/回归测试规则/测试分层/必须守住的协议/覆盖率目标)
$ .github/workflows/ci.yml sha256 = 1c321ad9...  （= base 同值）
$ docs/testing-guide.md  sha256 = e2016caf...  （= base 同值）
```

主仓 `D:\code\asterwynd` 亦无这两处改动 ⇒ 不是「改在别处」。**本 change 声称的 L3 CI 层与纪律文档层完全不存在**，而它们正是本 change 论证（「CI 在 UTF-8 locale 上看不见这类缺陷」）的闭环。

### 1.8 backlog 入队 —— **文件未改（tasks 1.3 却已勾选）**

```
$ git log -1 -- docs/openspec-change-backlog.md   → 8f575c8（与本 change 无关）
$ Select-String -Path docs/openspec-change-backlog.md -Pattern "fix-windows-encoding-and-guard"  → 无命中
$ docs/openspec-change-backlog.md sha256 = 50efd26f...（= base 同值）
$ workflow-events.jsonl: {"event_type":"backlog_updated", "artifact_path":"docs/openspec-change-backlog.md",
                          "reason":"立项入队：fix-windows-encoding-and-guard 写入「未实现队列」..."}
```

即：**事件已写、受保护 artifact 实际未改**，`## 未实现队列`（backlog:109 起）里没有本 change。

### 1.9 本机红绿对照（分块，pristine vs branch）

| 块 | pristine(`D:\code\asterwynd`) | branch(worktree) | 结论 |
|---|---|---|---|
| `tests/web_tests` 全量 | 9 failed / 521 passed / 8 skipped | **0 failed / 531 passed / 9 skipped** | 9 条平台红修复，0 新增 |
| 基线 5 文件（bash×3 + flow_policy + workflow_guard） | 9 failed / 66 passed | 9 failed / 66 passed | 既有红不变，无回归 |
| 7 路径块（memory/, read_doc, read_write, edit, test_session, workspace_policy, memory_e2e） | 20 failed / 301 passed | **9 failed / 312 passed** | **11 条既有红被本次修复，本块新增回归 0** |
| 新增 `tests/agent/test_session_encoding.py` | 不存在 | **1 failed / 8 passed** | **本 change 新引入 1 条红**（§1.4） |

11 条被修复的用例（集合差集，非自述）：`test_persistent.py` ×5、`test_long_term.py` ×2、`test_reversibility.py` ×3、`test_read_doc_and_pagination.py` ×1。
`tests/web_tests` 与 7 路径块合计修复 20 条既有红；**「新增回归 0 条」（tasks.md:31）在本 change 自己的新测试文件上不成立**。

### 1.10 benchmark smoke（tasks 4.6）

```
$ .venv\Scripts\asterwynd.exe benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir <tmp>
（重复两次，结果一致）
Tasks: 72 | passed: 0 | warnings: 0 | unsupported: 38 | failed: 34
且两次各含 16 处：
  File "...\subprocess.py", line 1599, in _readerthread
  UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 393: illegal multibyte sequence
```

- tasks.md:32 声称 `passed: 5 | unsupported: 38 | failed: 29`；我两次独立运行都是 `passed: 0 | failed: 34`（确定性，非抖动）。
- 「命令本身不再因编码崩溃」这一点**部分成立**且我已独立证实：`benchmarks/task_set.py:74` 的 `read_text()` 在 pristine 上抛 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xba`（`Manifest.load` 最小复现），分支上正常返回 `Manifest`。但 CLI 级不崩 ≠ 运行期无编码故障：runner 里那些**故意不钉** `subprocess(text=True)`（scope 修正的边界）在 Windows 上仍会以 GBK 解码 UTF-8 输出，16 处 reader-thread 崩溃即证据，并很可能就是 `passed` 从 5 掉到 0 的原因。

### 1.11 OpenSpec 校验

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed (29 items)     ← 含 change/fix-windows-encoding-and-guard
```

注意：OpenSpec 的结构校验**抓不到** §1.5 的 delta 文本漂移，所以这一项不能替代 `buildUpdatedSpec` 比对。

## 2. tasks.md 逐项验证表

| # | 任务 | 勾选 | 我的验证 | 判定 |
|---|---|---|---|---|
| 1.1 | 写 diagnosis.md | [x] | 文件存在，五节齐全（Symptom/Reproduction/Evidence/Root Cause/Recommended Direction/Regression Tests） | ✅ 成立 |
| 1.2 | 写 proposal.md | [x] | Change Type / Why / What Changes / Capabilities / RIR `light`（含 findings+design impact）/ Impact Analysis / 非目标 齐全 | ✅ 成立 |
| 1.3 | backlog 入队（受保护路径 + 事件） | [x] | 文件 sha256 同 base、无 change id、事件却已写 | ❌ **不成立（MUST-FIX 5）** |
| 2.1 | 先写失败测试（未修代码上 6 条红） | [x] | 历史声明，无法在 HEAD 复核（能证 2959990 版 L2 = 9 passed） | ⚠️ 无法验证 |
| 2.2 | session.py 6 处 open 补 encoding，读侧不用 errors="replace" | [x] | `session.py:119/121/170/198/256/258` 共 6 处 ✅；读侧确实只捕获 `UnicodeDecodeError`（:123/:172/:201），无 `errors="replace"` ✅（但 proposal/diagnosis/delta 仍写 `errors="replace"`，见 MUST-FIX 8） | ⚠️ 实现成立、文档三处不自洽 |
| 2.3 | list_sessions 单条降级 + damaged/reason + 目录名 | [x] | 代码成立（`session.py:172-181` 快照坏、`:201-204` 消息坏；`session_id` 取目录名）；但**快照分支无用例钉住**，且该用例恒红 | ❌ **部分不成立（MUST-FIX 3）** |
| 2.4 | api_sessions 原样透出 + 保持 200 | [x] | `web/server.py:331-332` 直接返回 `list_sessions()` 结果，`damaged/reason` 会透出 ✅；但承诺的 web 层用例不存在（MUST-FIX 6） | ⚠️ 代码成立、覆盖缺失 |
| 2.5 | main.py 4 处 read_text 补编码 | [x] | 实际改了 **6** 处（`:922` write_text、`:952` read_text、`:954` write_text、`:968` read_text、`:1096/1097` read_text）；总数口径仍吻合 | ⚠️ 数字小错（见 §4 建议 3） |
| 3.1 | 新增 L1 AST 守卫 + 白名单 + 自检 | [x] | 文件存在；AST 判据覆盖跨行；ALLOWLIST 为空；自检用例有牙齿（§1.3/§5） | ✅ 成立（判据措辞有两处分歧，§4 建议 1） |
| 3.2 | 批量补 379 处（文件 I/O 378 + node 1），改范围 | [x] | 独立数出 385 = 378 + 1 + 6(session.py)，**逐项吻合**；subprocess 只钉了 node harness 1 处，其余 70 处未动 | ✅ 成立 |
| 3.3 | L2 用例（往返/C-locale/EncodingWarning/降级/落盘字节/路径校验） | [x] | 用例都在且写路径有效（M16 全套被杀）；**缺「web 层 200」那条**（proposal:37、diagnosis:78 承诺）；降级用例恒红 | ❌ **部分不成立** |
| 3.4 | 变异验证：去 encoding→L1 红；去列表降级→L2 红 | [x] | 去 encoding→L1 红 ✅；去 messages 降级→L2 红 ✅；**去 snapshot 降级→该用例的红与基线红是同一条断言、无信号** ⇒ 「M2 已杀」不成立 | ❌ **不成立（MUST-FIX 3）** |
| 3.5 | 批量保真校验（逐字节 + ast.parse） | [x] | 我用独立方法复核：385 处全为纯插入、父调用全对、74 个 .py 全 ast.parse 通过 | ✅ 成立（措辞 71 files vs 实测 72，§4 建议 4） |
| 4.1 | ci.yml C-locale 步骤 | [x] | **不存在**（ci.yml 与 base 同 sha256，无 LC_ALL/PYTHONCOERCECLOCALE/PYTHONUTF8） | ❌ **不成立（MUST-FIX 1）** |
| 4.2 | ci.yml windows-platform job | [x] | **不存在**（无 `windows-platform`、无 `windows-latest`）；自述「207 passed / 1 skipped」的文件清单不在仓库，无法复核（我按 proposal 描述构造的相近子集 = 196 passed / 1 skipped） | ❌ **不成立（MUST-FIX 1）** |
| 4.3 | testing-guide「平台与编码纪律」 | [x] | **不存在**（文件与 base 同 sha256，无相关小节/关键词） | ❌ **不成立（MUST-FIX 2）** |
| 4.4 | 平台假设修正（8 条恒红） | [x] | web 套件 9 red → 0 red，断言未放宽，skip 理由成立 | ✅ 成立 |
| 4.5 | web_tests 531/0；13 文件块 34→23、新增回归 0 | [x] | web_tests 531/0 ✅、pristine 9 failed ✅、11 条既有红被修 ✅、**新增回归 0 不成立**（新文件 1 failed）；我未复现他们的 13 文件清单（我的两块：9/9 与 20→9） | ❌ **部分不成立（MUST-FIX 3、7）** |
| 4.6 | benchmark smoke | [x] | 命令不再因 manifest 解码崩溃 ✅（最小复现证实）；但声称的 `passed: 5 / failed: 29` 两次都复现为 `passed: 0 / failed: 34`，且有 16 处 GBK 解码崩溃 | ❌ **数字不成立（MUST-FIX 7）** |
| 5.1–5.8 | closeout（spec 同步 / 文档影响 / backlog 移除 / 归档 / validate / checker / 审阅 / PR） | [ ] | 未勾，符合 building 阶段预期；注意 5.1 若按现 delta 执行会引入 MUST-FIX 4 的回归 | ⚠️ 待办 |
| 5.9 | (post-merge) 推送 + 建 issue 回填 | [ ] | 已带 `(post-merge)` 标记，符合门禁要求 | ✅ 标记合规 |

## 3. Issues（M1–M8 均为 MUST-FIX，即归档前必须改；severity 见每条标题）

### M1 【HIGH】CI 的 L3 层完全缺失（tasks 4.1/4.2 已勾）
- 位置：`.github/workflows/ci.yml`（全文 91 行，job 仅 `validate` / `benchmark-gate`）；`openspec/changes/fix-windows-encoding-and-guard/tasks.md:27-28`
- 判据：tasks 勾选 + `proposal.md:38`（What Changes 7）、`proposal.md:83`（Impact Analysis 表格）承诺 C-locale 步骤与 `windows-platform` job；缺了就等于本 change 的核心论点（CI 看不见 locale 类缺陷）没有闭环。
- 复现：`git diff --stat da8621f..HEAD -- .github/workflows/ci.yml`（空）；`Get-FileHash .github/workflows/ci.yml` = `1c321ad9...`（与 base 相同）；`Select-String -Path .github/workflows/ci.yml -Pattern "windows-platform|LC_ALL"` 无命中。

### M2 【HIGH】`docs/testing-guide.md`「平台与编码纪律」缺失（tasks 4.3 已勾）
- 位置：`docs/testing-guide.md`（标题仅 基本原则 / 回归测试规则 / 测试分层 / 必须守住的协议 / 覆盖率目标）；`tasks.md:29`
- 判据：`proposal.md:39`（What Changes 8）、`proposal.md:84`（Impact Analysis「文档」行）、`diagnosis.md:67` 第 6 条。
- 复现：`git diff --stat da8621f..HEAD -- docs/testing-guide.md`（空）；`Select-String -Path docs\testing-guide.md -Pattern "平台与编码纪律|encoding|locale|UTF-8"` 无命中。

### M3 【HIGH】新增回归测试恒红 + snapshot 降级分支实际未覆盖（tasks 2.3/3.3/3.4/4.5 相关声明不成立）
- 位置：`tests/agent/test_session_encoding.py:105-107`（fixture，纯 ASCII 载荷）、`:117-118`（恒失败断言）；被测分支 `agent/session.py:172-181`
- 判据：AGENTS.md「每个 bug fix 必须新增回归测试」；归档门禁要求测试绿；`tasks.md:22`（3.4）与 `tasks.md:31`（4.5「新增回归 0 条」）声明不成立。
- 复现：
  1. `pytest tests/agent/test_session_encoding.py -q` → `1 failed, 8 passed`，断在 `:117`。
  2. 最小复现：`json.dumps({"session_id":"sess_worse","mode":"build"}, ensure_ascii=False).encode("gbk")` 是合法 UTF-8。
  3. 该红由本 change 引入：`git show 2959990:tests/agent/test_session_encoding.py` 运行 = `9 passed`，HEAD = `1 failed, 8 passed`。
  4. 该分支本可被钉住：把载荷改成含中文（如 `"mode": "构建"`）→ `9 passed`；再叠加「去掉 `agent/session.py:172-181` 降级分支」的变异 → 红在 `:116`。
- 建议修法（供实现方参考）：fixture 里放一个 GBK 不可逆的非 ASCII 字符（或直接 `write_bytes(b'{"session_id": "\xff\xfe"...}')`），使 `json.load(..., encoding="utf-8")` 必抛 `UnicodeDecodeError`；然后重跑 M2 变异确认被杀。

### M4 【HIGH】spec delta 的 MODIFIED 块不是「逐字保留」，会静默改写现行 spec（含与实现相反的事实）
- 位置：`openspec/changes/fix-windows-encoding-and-guard/specs/web-ui/spec.md:3-4`（自称逐字保留）、`:10`（host 绑定反转）、`:16-49`（5 条既有 Scenario 被改名/改写）；对照 `openspec/specs/web-ui/spec.md:397`、`agent/main.py:671`
- 判据：MODIFIED 是整块替换（本仓历史上已踩过）；`tasks.md:36`（5.1）一旦同步即写入受保护路径；delta 自身头注与事实不符。
- 复现（用 OpenSpec 自己的实现，不写仓库）：
  1. `buildUpdatedSpec({source: <delta>, target: <main spec>, exists:true}, "fix-windows-encoding-and-guard")`（`@fission-ai/openspec@1.4.1/dist/core/specs-apply.js:60`）→ Scenario 161 → 164。
  2. 逐块比对：3 条 Scenario header 变化、2 条正文变化、requirement 正文整段替换。
  3. `Select-String -Path agent\main.py -Pattern "127.0.0.1"` → `:671 host: str = typer.Option("127.0.0.1", ...)`，与 delta `:10`「默认 host 绑定**不得为** 127.0.0.1」相反。
- 建议修法：以 `openspec/specs/web-ui/spec.md` 现状为基准重写 MODIFIED 块（原 5 条 Scenario 逐字复制），只追加本次 3 条新 Scenario 与两段新增不变量，host 那句照抄现行文本。

### M5 【MEDIUM】backlog 入队缺失，但已写入 `backlog_updated` 结构化事件
- 位置：`docs/openspec-change-backlog.md`（`## 未实现队列` 从 :109 起，无本 change）；`tasks.md:7`（1.3 已勾）；`openspec/changes/fix-windows-encoding-and-guard/workflow-events.jsonl`（seq 1）
- 判据：AGENTS.md「新增 OpenSpec change 后…应把它加入本队列」；受保护 artifact 纪律要求「事件 ↔ artifact 改动」一致，这里是**有事件无改动**。
- 复现：`git log -1 -- docs/openspec-change-backlog.md` → `8f575c8`；`Select-String -Path docs\openspec-change-backlog.md -Pattern "fix-windows-encoding-and-guard"` 无命中；sha256 与 base 相同。

### M6 【MEDIUM】承诺的 web 层回归用例不存在
- 位置：承诺见 `proposal.md:37`（第 6 条最后一条 bullet）与 `diagnosis.md:78`（Regression Tests 表：`test_api_sessions_returns_200_with_emoji_session`）；被测代码 `web/server.py:331-332`
- 判据：接口「不 500 且透出 damaged/reason」这一层不变量当前**没有任何用例**钉住（现有 `test_api_sessions_*` 都是 workspace 授权类）。
- 复现：`Select-String -Path tests\**\*.py -Pattern "api_sessions_returns_200|damaged"` → 仅 `tests/agent/test_session_encoding.py` 命中 `damaged`，无 API 级用例。

### M7 【MEDIUM】benchmark smoke 的数字不可复现，且运行期仍有 GBK 解码崩溃
- 位置：`tasks.md:32`（4.6）；证据面 `benchmarks/runner.py:1006`、`benchmarks/adapters.py:114`、`benchmarks/agent_runner.py:145/230` 等（scope 修正后**故意不钉** `text=True` 的站点）
- 判据：任务勾选所依据的验证数字应可复现；「命令本身不再因编码崩溃」的结论需限定作用域。
- 复现：`& .venv\Scripts\asterwynd.exe benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir <tmp>`（两次一致）→ `Tasks: 72 | passed: 0 | warnings: 0 | unsupported: 38 | failed: 34`，各含 16 处 `UnicodeDecodeError: 'gbk' ...`（`subprocess._readerthread`）；声称值为 `passed: 5 / failed: 29`。可独立证实的正向部分是 `benchmarks/task_set.py:74` 的 `Manifest.load` 修复（pristine 抛 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xba`，分支返回 `Manifest`）。

### M8 【MEDIUM】读侧 `errors="replace"` 的三处文档口径与实现（及 tasks 2.2）相反，且 delta 也照抄
- 位置：`proposal.md:27`、`diagnosis.md:62`、`openspec/changes/.../specs/web-ui/spec.md:12`（「读侧…SHALL 降级（`errors="replace"` 语义）」）；实现 `agent/session.py:123/172-181/201-204`（显式捕获 `UnicodeDecodeError` → 判损坏 / 返回 None），`tasks.md:12`（2.2）明确**不**用 `errors="replace"`。
- 判据：spec delta 是受保护 spec 的同步源，不得写与实现相反、且与本 change 自己的 tasks 决策相反的实现口径。
- 复现：`Select-String -Path agent\session.py -Pattern 'errors="replace"'`（无命中；只有 `tests/**` 里 pytest 自己写的 `write_text` 站点带 `errors="replace"`）；对照上述三处文档行。
- 建议修法：三处统一改成「不可解码 SHALL 判为损坏并如实标注（列表）/ 返回 None（单条 load），SHALL NOT 用替换字符静默交付」。

## 4. 可选建议（不阻塞，但建议顺手修）

1. **L1 守卫判据与 proposal/diagnosis 措辞对齐**：`test_encoding_hygiene.py:63-73` 的 `_literal_mode` 对 `Path.open()` 取了 `args[1]`（应为 `args[0]`），导致 `Path('x.bin').open('rb')` 误报；同时 `os.open` 未被排除（`proposal.md:31` / `diagnosis.md:41` 声称排除）。复现：把我构造的探针样例（`Path('x.bin').open('rb')`、`os.open('p', os.O_RDONLY)`、`open(FD_NAME)`）喂给 `_check_file`，共报 6 条而按文档口径应为 3 条。方向是保守（多报不漏报），故只列为建议；也可只改文档措辞。
2. **自检样例补 `Path.open("rb")` 与 `os.open`**：现样例的 `Path('e.txt').open('r')` 实际走的是 `mode is None` 分支，所以放宽二进制排除的变异（M6b）**存活**；补一条真二进制绑定方法样例即可封住。
3. **tasks.md:15（2.5）数字**：`agent/main.py` 实际改了 6 处（4 处 `read_text` + 2 处 `write_text`），不是 4 处；总数口径（379 = 378 + 1）不受影响。
4. **tasks.md:23（3.5）措辞**：「71 个文件全部一致」与实测 72 个改动 `.py` 文件不符（其中 `agent/session.py`、`tests/web_tests/test_multi_session.py` 另有非插入改动，属预期的结构性改动）。
5. **`test_encoding_hygiene.py:5`** 的 docstring 直接引用 `openspec/changes/archive/*-fix-windows-encoding-and-guard/diagnosis.md`——该路径归档后才存在，建议改为相对 change 目录的描述。
6. **SCAN_ROOTS**（`test_encoding_hygiene.py:33`）不含仓库根目录 `.py`（`duration.py`）与 `openspec/**/*.py`；当前这些文件无违规站点，属「全仓扫描」措辞略超实现。

## 5. 变异验证结果表

> 本节的变异编号（M1/M2/…）与 §3 的 Issue 编号（M1–M8）**互相独立**，勿混淆。

所有变异均在改动前后记录 sha256，还原后校验一致，最终 `git status --porcelain` 为空。

| 变异 | 目标用例 | 观察结果 | 判定 |
|---|---|---|---|
| M1 去掉 `agent/session.py:119` 的 `encoding=` | L1 守卫 | red（`test_local_file_io_always_declares_its_encoding`） | **杀死** ✅ |
| M15 去掉 `agent/main.py:968` 的 `encoding=` | L1 守卫 | red | **杀死** ✅ |
| M4 去掉 node harness `tests/web_tests/test_server.py:698` 的 `encoding=` | L1 守卫 | red | **杀死** ✅ |
| M5 往被扫描文件注入裸 `open()` | L1 守卫 | red | **杀死** ✅ |
| M11 往被扫描文件注入裸 `read_text()` | L1 守卫 | red | **杀死** ✅ |
| M12 注入非 node 的 `subprocess(text=True)` | L1 守卫 | green | 存活，**但不属漏报**：docstring `:16-19` 明示只钉 node harness（属已知覆盖边界） |
| M6a 守卫削弱：`NON_FILE_OPENERS` 去掉 `Image` | 守卫自检 | red（自检 + 全仓） | **杀死** ✅ |
| M6c 守卫削弱：关掉 node 子进程判据 | 守卫自检 | red（自检） | **杀死** ✅ |
| M6d 守卫削弱：关掉 read_text/write_text 判据 | 守卫自检 | red（自检） | **杀死** ✅ |
| M6b 守卫削弱：任何字面量 mode 都跳过 | 守卫自检 | green | **存活**（自检样例未触及 mode 解析；见 §4 建议 2） |
| M16 去掉 `agent/session.py:258` 写 messages 的 `encoding=` | L2 全套 | 6 failed，含 C-locale 子进程用例（子进程报 `UnicodeEncodeError: 'gbk' ... '\U0001f44b'`）与 `EncodingWarning` 用例 | **杀死** ✅ |
| M13 去掉 `agent/session.py:256` 写 snapshot 的 `encoding=`（跑全套 L2） | L2 | 2 failed：`test_no_default_encoding_warning_from_our_code`（真杀）+ 基线红 `test_list_sessions_...` | **杀死**（由 PEP 597 告警层）✅ |
| M13b 同一变异，只跑 C-locale 子进程用例 | L2 | green（该用例的 snapshot 载荷纯 ASCII，属**弱变异**，非用例缺陷） | 存活 |
| M14 去掉 `agent/session.py:198` 读 messages 的 `encoding=` | L2 | red（`:114` damaged 断言失败：GBK locale 下坏文件被当默认编码读成功）。注意这条只在**非 UTF-8 locale** 有效，Linux 上可能存活，靠 L1 兜底 | **杀死**（本机）✅ |
| **M2 去掉 `agent/session.py:172-181` 的 snapshot 降级分支** | L2 | red —— 但与**未变异时同一条断言（`:117`）、同一现象**（该用例本就恒红） | ❌ **未被杀死（无信号）** |
| M3 去掉 `agent/session.py:201-204` 的 messages 降级分支 | L2 | red（断在 `:114`，与 M2 的失败点不同） | **杀死** ✅ |
| M7 只把 fixture 载荷改成含中文（不改实现） | L2 | **9 passed** | 证明恒红是 fixture 缺陷 |
| M8 M7 + 去掉 snapshot 降级分支 | L2 | red（断在 `:116`，session_id 可见性） | 证明该分支**可被**钉住 |

## 6. 未验证项与残余风险

1. **`windows-platform` CI job 无法验证 —— 它根本不存在**（M1）。即便补上，`windows-latest` 上的真实行为（PowerShell 步骤写法/续行、`playwright install chromium`、路径语义、以及是否会「静默 skip」）本轮无法在本地证实；补上后**必须**在 PR 上观察首跑结果，不能只靠本地代理跑。
2. **全量 `uv run pytest` 在本机不可完成**：进程在 45%~67% 处被资源限制杀掉（非断言失败）。本轮用分块覆盖了改动面（web 套件全量 + 基线 5 文件 + 7 路径块 + 若干单文件/单用例），但**不等价于全量套件**；`tests/benchmark/*`、`tests/agent/tools/*` 等其余文件未逐一复核。
3. **tasks 2.1「未修代码上实测 6 条红」属历史声明**，无法在 HEAD 复核（我仅能证明 `2959990` 版 L2 文件 = 9 passed）。
4. **tasks 4.2「按同一文件清单实跑 207 passed / 1 skipped」**：清单不存在于仓库，无法精确复核；我按 proposal 描述构造的相近子集（`test_session.py` + `test_server.py` + `test_multi_session.py` + `test_transcript_*.py`）= **196 passed / 1 skipped**。
5. **web 层 damaged 透出的端到端行为无用例**（M6）；`list_sessions` 在「snapshot 可读但 `session_id` 与目录名不一致」时返回的 id 语义也无用例。
6. **benchmark 运行期的 locale 解码边界**：scope 修正（只钉 node harness）有其道理，但代价是 Windows 上 benchmark 仍会出现子进程输出解码崩溃（§1.10 的 16 处），可能污染任务判定；本 change 未处理，也未在文档里记债（`docs/known-debt.md` 未提及）。
7. 变异 M12/M6b 的存活属覆盖面缺口而非漏报真站点：今天全仓 0 offenders，方向是保守（多报不漏报）。

## 7. 结论

- **verdict：CHANGES_REQUESTED**（8 条 MUST-FIX，其中 M1/M2/M5 是「任务已勾但产物不存在」，M3 是新引入的红测试 + 覆盖缺失，M4 是会在同步时污染受保护 spec 的 delta 漂移）。
- **归档前必须改**：需要改代码/测试（M3、M6、M8 相关文字）与文档/配置（M1、M2、M4、M5、M7）。具体最小改动集：
  1. 修 `tests/agent/test_session_encoding.py:105-107` 的 fixture（用真正不可 UTF-8 解码的字节），并重跑 M2 变异确认被杀；
  2. 补 `.github/workflows/ci.yml` 的 C-locale 步骤与 `windows-platform` job，补 `docs/testing-guide.md`「平台与编码纪律」；
  3. 按现行 spec 重写 `specs/web-ui/spec.md` 的 MODIFIED 块（逐字保留 5 条既有 Scenario，删掉反转的 host 陈述）；
  4. 写入 `docs/openspec-change-backlog.md` 的未实现队列（并保持事件与 artifact 一致）；
  5. 补 `GET /api/sessions` 的 200 + damaged 用例；把 tasks 4.6 的 smoke 数字改成实测值并注明运行期残余 GBK 边界；统一 `errors="replace"` 口径。
- 修复后建议再审一轮（本轮 3 个「文档/CI 产物缺失」类问题是机械可复核的，第二轮可快速确认）。
