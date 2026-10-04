# Building Review: fix-windows-encoding-and-guard

**CHANGES_REQUESTED**

- **reviewer run id**：`building-review-fix-windows-encoding-and-guard-20261004-r3`
- **审阅时间**：2026-10-04T19:05+08:00（本机 Windows + 中文 locale `cp936`，即本 change 的目标环境）
- **审阅对象**：worktree `D:\code\asterwynd-worktrees\fix-windows-encoding-and-guard`，分支 `fix-windows-encoding-and-guard/2026-10-04`
  - **HEAD**：`31ac3ee0013f241fc3d6c73598b2a026ac9df899`（`fix(encoding): L1 守卫判据修正（Path.open 的 mode 位置 / 排除 os.open）+ 自检封口`）
  - base：`da8621f08d2bd51be949304148a1e57b997a34b4`（=`master`）；审阅前后 `git status --porcelain` 为空
  - 本轮起点确认：`40d5541`（Round-1 八条 MUST-FIX 的修复提交）→ 本轮 `31ac3ee` 仅多改一个文件：`M tests/web_tests/test_encoding_hygiene.py`（+17/−4）
- **受控文件 sha256（当前工作区，均已逐一复核）**

| 文件 | sha256 |
|---|---|
| `.github/workflows/ci.yml` | `7548039e1bb9a4f73eeae054ff6424c67d090a6ec222feb13899218fa6e858a0` |
| `docs/testing-guide.md` | `c04af1846f393a0de9c44ae23ba3ab3ad5355c9efdee5c2cad134b873f80a596` |
| `docs/openspec-change-backlog.md` | `922093dfdf7d9076c86c63f437103fe6776448dcf3641d4fa1d003969764e179` |
| `tests/agent/test_session_encoding.py` | `4e1dd56d1f1c944ebe49a637943bd91761138e6dea0d0868b3939e5af0ab0b6a` |
| `tests/web_tests/test_encoding_hygiene.py` | `8cc063a7aff4abbbfb4a95fccfc853a31a3fd6c0d9b0bdff8a97cb925a0eac5b` |
| `tests/web_tests/test_multi_session.py` | `26771273a3ca1238c51f754afb8e50ce7101620aae3bbd82061487441ac9bf44` |
| `openspec/changes/.../specs/web-ui/spec.md` | `05e4b0959ca1121cb1abbe2c1bfde51c364196e6d3013669f35907944f7d4045` |
| `openspec/changes/.../tasks.md` | `d166c16aa7400d6e3eca5ed2e48efc7a4dc1ed2ad284c0ada674dada7a804395` |
| `agent/session.py`（应冻结不变） | `dc26072d85c435f9686724879fda0e013fd2b65f0eeb1f2a98402d51268b315b` |
| `web/server.py`（应冻结不变） | `82e1e7f795604178…`（与 Round 1 相同，未被改动） |

**判据：`PASS` 需 0 条 MUST-FIX。Round-1 的 8 条 MUST-FIX 我已逐条复核并确认实质关闭（见 §1）；但本轮修复自身引入了 2 条新问题（1 条守卫假阴性、1 条文档与守卫口径分裂），另有 1 条任务证据数字未随修订更新，合计 3 条 MUST-FIX ⇒ CHANGES_REQUESTED。**

> 修订说明（避免误读）：上一版落在盘上的 `building-review.md` 是 Round-1 报告（头部写 `0575ee4`）。Round 2 的实际测量是在 `40d5541` 上完成的，只是报告尚未覆写；`40d5541 → 31ac3ee` 的差异已核对（仅守卫测试文件），故 Round 2 的其余结论继续有效。

## 1. Round-1 八条 MUST-FIX 的关闭确认

| # | Round-1 问题 | 状态 | 证据（本轮实测） |
|---|---|---|---|
| M1 | L3 CI 层完全缺失 | **关闭** | `yaml.safe_load` 解析通过；3 个 job：`validate`（11 步，含 `Run tests (non-UTF-8 locale)`：`LC_ALL=C`/`LANG=C`/`PYTHONCOERCECLOCALE=0`/`PYTHONUTF8=0`，跑 5 个文件）/ `benchmark-gate`（7 步）/ `windows-platform`（7 步，`runs-on: windows-latest`，`uv run playwright install chromium`，PowerShell 反引号续行）。CI 引用的 9 个 pytest 路径全部存在；无 `continue-on-error` / `|| true` / `--deselect` 等逃逸口 |
| M2 | `docs/testing-guide.md` 纪律小节缺失 | **关闭** | `docs/testing-guide.md:14` 起「## 平台与编码纪律」（三条规则 + 三条写平台测试的经验）确实落盘；`docs/testing-guide.md:12` 也在「基本原则」补了一条（内容准确性另有 1 条 MUST-FIX，见 §3-1） |
| M3 | 新增回归恒红 + snapshot 降级分支未覆盖 | **关闭** | fixture 改为含中文（`test_session_encoding.py:108` `"note": "中文"`）⇒ GBK 字节非法 UTF-8；未变异下 `pytest tests/agent/test_session_encoding.py` = **9 passed**；变异「去掉 snapshot 降级分支」= **红**（R2-B），「去掉 messages 降级标注」= **红**（R2-A） |
| M4 | delta 未逐字保留 + host 语义写反 | **关闭** | 用 OpenSpec 1.4.1 自己的 `buildUpdatedSpec` 只读模拟：`counts={added:0, modified:2, removed:0}`；整文件 56 requirement 不变、Scenario **161 → 164**；`scenario headers present in current but not in built: []`；两个 requirement 的正文经 unified diff 只显示**追加**（`@@ -3,0 +4,2 @@`），既有 5 条 + 3 条 Scenario 全部**逐字节相同**；host 句恢复为「Web 默认 host 绑定策略为 `127.0.0.1`」，与 `openspec/specs/web-ui/spec.md:397`、`agent/main.py:671` 一致 |
| M5 | backlog 入队缺失但有事件 | **关闭** | `docs/openspec-change-backlog.md` 的「未实现队列」首位为 `### 1. fix-windows-encoding-and-guard`，含状态、分支与收口说明 |
| M6 | 承诺的 web 层用例不存在 | **关闭** | `test_multi_session.py:286` `test_api_sessions_returns_200_with_emoji_session`、`:309` `test_api_sessions_marks_damaged_entry_without_failing` 均存在且通过；变异 R2-C（让 `api_sessions` 过滤掉 damaged 条目）→ 红；R2-D（去掉写侧 encoding）→ 红 |
| M7 | 运行期 16 处解码崩溃（+ 数字不可复现） | **关闭**（含对我 Round-1/2 结论的更正） | 70 处 `subprocess` 补 `errors="replace"`（保真复核见 §2.1）；用**文档里的原命令** `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir <fresh>` 复跑：`Tasks: 72 \| passed: 5 \| warnings: 0 \| unsupported: 38 \| failed: 29`，**`UnicodeDecodeError` 计数 = 0**（此前 16）——数字与 tasks 记录**完全一致**。我此前用 `.venv\Scripts\asterwynd.exe` 直接调用得到的 `passed: 0 / failed: 34` 属**调用方式偏差**（`uv run` 提供的 uv/PATH 上下文影响 benchmark 内部子进程），不是编码缺陷；Round-1 M7 的「数字不可复现」判据据此**更正为不成立** |
| M8 | `errors="replace"` 口径矛盾 | **部分关闭** | 我 Round-1 点名的位置已改：`proposal.md:27`（读侧**不**用 replace）、`proposal.md:32`（子进程侧 encoding= 或 errors=）、`diagnosis.md:62`、delta `:15`。**但 `docs/testing-guide.md:28` / `:31-33` 仍是修复前口径**（见 §3-1） |

Round-1 的可选建议 #1/#2 也已落实：`_literal_mode` 位置修正（`:65-84`）、`os.open` 排除（`:99-105`）、自检补 `Path('g.bin').open('rb')` 与 `os.open(...)` 样例；Round-1 存活的「放宽二进制排除」变异现在**会被自检杀死**（W1）。

## 2. 复现与证据

### 2.1 新增 `errors="replace"` 批量插入保真（70 处）——通过

用我自己的「行级 diff → 行内字符级 diff → 插入偏移映射到 AST keyword」管线（base = `0575ee4`）：

```
modified .py: 41   added .py: 0
pure-insertion sites: errors=70   encoding=0
errors= parent funcs: {'run': 70}
errors= sites that are NOT last kwarg: []
所有 70 处插入唯一对应 AST 上的 errors= keyword；70/70 父调用均为 subprocess.run 且 text=True；
70 处中同时带 encoding= 的：0
BAD: 3 → 均为预期改动，非编码站点：
   tests/agent/test_session_encoding.py:108（M3 的 fixture 修复：新增 "note": "中文"）
   tests/web_tests/test_encoding_hygiene.py:13-14（守卫 docstring 重写）
结构性改动 6 处，集中在 3 个文件：test_session_encoding.py（fixture）、test_encoding_hygiene.py（判据+自检）、test_multi_session.py:284-334（两条新用例）
occurrences errors="replace"（既有 .py）: base=51 → head=124（delta 73 = 70 插入 + 3 处守卫自身示例/文档串）
```

即：**批量插入只动了关键字**，没有顺带改动任何既有代码；且 70 处全部是「捕获文本」的 `run(text=True)`，与 `errors="replace"` 的语义（保持 locale 解码、绝不解码崩）一致。

### 2.2 守卫判据与自检（当前 HEAD）——通过，但 `_literal_mode` 有新缺陷

```
$ pytest tests/web_tests/test_encoding_hygiene.py -q
2 passed
```
- 自检样例现含 `Path('g.bin').open('rb')`、`os.open('h.txt', os.O_RDONLY)`，命中数仍断言 5。
- 自检牙齿（我的变异，全部按字节还原）：W1 放宽二进制排除 → 自检红；W2 回退 `os.open` 排除 → 自检红；W3 回退 `_literal_mode` 位置修正 → 自检红；注入裸 `subprocess.run(..., text=True)` → 全仓守卫红。
- **但**：`_literal_mode` 的「绑定方法取 `args[0]`」对**非 `Path` 的属性式 open** 会读错字段，造成假阴性/假阳性（§3-2；同一份样例分别在 `HEAD` 与 `git show 0575ee4:...` 两个版本的守卫上跑）：

```
样本                                 HEAD(31ac3ee)    0575ee4(round-1)
io.open('x.txt', 'rb')               FLAG ← 误报       ----
io.open('b.txt', 'w')                ---- ← 漏检       FLAG
builtins.open('baseline.json', 'w')  ---- ← 漏检       FLAG
gzip.open('f.gz', 'rb')              FLAG ← 误报       ----
Path('x.bin').open('rb')             ----（已修）      FLAG ← 原误报
Path('y.txt').open('w')              FLAG             FLAG
open('c.txt','rb') / open('d.txt','w')  ---- / FLAG     ---- / FLAG
```

### 2.3 无新增红（分块对照，pristine `D:\code\asterwynd` vs 本分支）

| 块 | pristine | 本分支(31ac3ee) | 结论 |
|---|---|---|---|
| `tests/web_tests` 全量 | 9 failed / 521 passed / 8 skipped | **0 failed / 533 passed / 9 skipped** | 9 条平台红修复；+2 为 Hub 新用例；0 新增 |
| 基线 5 文件（bash×3 + flow_policy + workflow_guard） | 9 failed / 66 passed | 9 failed / 66 passed | 无变化、无回归 |
| 7 路径块（memory/, read_doc, read_write, edit, test_session, workspace_policy, memory_e2e） | 20 failed / 301 passed | **5 failed / 316 passed** | 集合差集：**15 条既有红被修，新增回归 0 条** |
| `test_session_encoding.py` + 两条 Hub 用例 | （不存在/旧版） | **11 passed** | 全绿 |

被修复的 15 条（集合差集，非自述）：`test_persistent.py` ×5、`test_long_term.py` ×2、`test_reversibility.py` ×7、`test_read_doc_and_pagination.py` ×1。仍红的 5 条与 pristine 完全一致（bash 工具类既有环境红）。

### 2.4 其它

- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **29 passed / 0 failed**（含本 change）。注意它抓不到 delta 的文本漂移，故 M4 仍需 `buildUpdatedSpec` 比对。
- M5 backlog 条目内容正确（未实现队列首位 + 状态/分支/收口说明）。

## 3. Issues（MUST-FIX：归档前必须改）

### 3-1 【MEDIUM】`docs/testing-guide.md` 的子进程规则与守卫判据仍是修复前口径（文档 ↔ 机械门禁分裂）
- 位置：`docs/testing-guide.md:28`、`:31-33`（附带 `:44`）
  - `:28`：「所以只在**确定跨平台输出 UTF-8** 的子进程上写 `encoding="utf-8"`（本仓即 node harness），**其余保持交给 locale**。」
  - `:31-33`：「命中「缺 `encoding=` 的 `open`/`read_text`/`write_text`」与「**跑 node harness 的** `text=True` 子进程缺 `encoding=`」即失败」
  - `:44`：windows 信号面写「GBK 解码」（`windows-latest` 默认 en-US/cp1252，GBK 只在本地中文机成立）
- 判据：守卫的实际判据（`tests/web_tests/test_encoding_hygiene.py:161-165`）是**任何** `text=True` 子进程缺 `encoding=` **且**缺 `errors=` 即失败；实现也据此给 70 处非 node 站点补了 `errors="replace"`（`proposal.md:32`、`tasks.md` 3.6/6.7 均已改口径）。于是出现「**守卫要求 `errors=`，文档说不要求**」的分裂：开发者按文档新增 `subprocess.run(cmd, text=True)` 会在 CI 被守卫拦下。
- 复现：`Select-String -Path docs\testing-guide.md -Pattern 'errors=|node harness'` → 仅 `:25`（文件读侧示例）命中，`:28`/`:32` 仍是旧口径；对照 §2.2 的注入探针（守卫 red）。
- 建议修法：`:28` 补「其余若无法确定编码，SHALL 至少 `errors="replace"`」；`:32` 改为「`text=True` 子进程既未声明 `encoding=` 也未声明 `errors=`」；`:44` 的「GBK 解码」改为「非 UTF-8 默认编码（GBK 需本机中文环境）」。

### 3-2 【MEDIUM】`_literal_mode` 对属性式 open 读错字段：守卫出现假阴性（并伴随假阳性）
- 位置：`tests/web_tests/test_encoding_hygiene.py:65-84`（`is_bound_open` 分支）
- 判据：该函数 docstring 与 `_is_open_call`（`:99-105`）都明确把 `io.open` / `builtins.open` 当作要检查的文件 I/O，但 `_literal_mode` 把所有 `*.open(...)` 都当**绑定方法**取 `args[0]`。对 `io.open(path, mode)` 这类**模块函数**，`args[0]` 是**路径**——若路径字面量恰含字母 `b`（如 `"b.txt"`、`"baseline.json"`），守卫会当成二进制模式**静默跳过**，真正的文本 open 漏检；反之 `io.open('x.txt', 'rb')` 这类合法二进制调用被**误报**。
- 复现（不写仓库，纯内存加载两版守卫对比，样例与输出见 §2.2）：
  ```
  io.open('b.txt','w')               → HEAD 不报（漏检）  / 0575ee4 报
  builtins.open('baseline.json','w') → HEAD 不报（漏检）  / 0575ee4 报
  io.open('x.txt','rb')              → HEAD 误报           / 0575ee4 不报
  gzip.open('f.gz','rb')             → HEAD 误报           / 0575ee4 不报
  ```
- 已用**内存补丁**验证最小修法（未落盘，仅替换 2 行）：绑定形态仅在**恰好 1 个位置参数**时取 `args[0]`，有 ≥2 个位置参数时一律取 `args[1]`：
  ```python
  if is_bound_open and len(call.args) == 1:
      mode_node = call.args[0]
  elif len(call.args) >= 2:
      mode_node = call.args[1]
  ```
  验证结果：上述 4 个错例全部消失（`io.open('b.txt','w')`/`builtins.open(...)` 被正确报出，`io.open('x.txt','rb')`/`gzip.open(...,'rb')` 正确跳过），且**现有自检样例仍是 5 条命中**（`:211` 断言不变）。建议同时补一条 `io.open('b.txt','w')` 自检样例封口。

### 3-3 【LOW】`tasks.md` 的对比数字未随修订更新（与 §6 及最终状态自相矛盾）
- 位置：`openspec/changes/fix-windows-encoding-and-guard/tasks.md:33`（4.5）、`:30`（4.2）
- 判据：`4.5` 记「13 文件对比块 = pristine 34 failed → 本分支 **23 failed**，另有 **11 条**既有红被修」，而当前修订（本轮实测 + §6 的修复说明）是 **19 failed / 15 条被修**（我的 7 路径块集合差集也实测为 **15 条修复、0 新增**）。同页 `:30`（4.2）记「本机按同一文件清单实跑 `207 passed / 1 skipped`」，但该文件清单不在仓库中，无法复核（我按 proposal 描述构造的相近子集 = 198 passed / 1 skipped，差异只因清单不同）。
- 复现：`Select-String -Path openspec\changes\fix-windows-encoding-and-guard\tasks.md -Pattern '23 failed|11 条|207 passed'`；对照 `:55`（6.6）与本报告 §2.3。
- 建议修法：把 4.5 的数字更新为最终修订实测值（或标注为「Round-1 快照」并给出最终值）；4.2 补上所用文件清单，或把「207 passed / 1 skipped」改为不含具体数字的表述。

## 4. 变异验证结果表（Round 2 + Round 3，全部按字节还原、sha256 前后一致、`git status` 为空）

| 变异 | 目标 | 观察 | 判定 |
|---|---|---|---|
| R2-A 去掉 `list_sessions` 的 messages 降级标注 | `test_session_encoding.py` / 新 Hub 用例 | 两条各自红 | **杀死** ✅ |
| R2-B 去掉 `list_sessions` 的 snapshot 降级分支（fixture 已修） | `test_session_encoding.py` | 红（断点与基线红不同，是真信号） | **杀死** ✅ |
| R2-C 让 `api_sessions` 过滤 damaged 条目 | 新 Hub 用例 | 红 | **杀死** ✅ |
| R2-D 去掉 `_write` 写 messages.json 的 `encoding=` | 新 Hub emoji 用例 | 红（GBK 下保存失败） | **杀死** ✅ |
| R2-E 去掉真实站点 `tests/test_flow_policy.py:33` 的 `errors="replace"` | 全仓守卫 | 红 | **杀死** ✅ |
| R2-F 注入无 `encoding=`/`errors=` 的 `text=True` 子进程 | 全仓守卫 | 红 | **杀死** ✅ |
| W1 放宽二进制排除（任何字面量 mode 都跳过） | 守卫自检 | 红（Round-1 曾存活，现已封口） | **杀死** ✅ |
| W2 回退 `os.open` 排除 | 守卫自检 | 红 | **杀死** ✅ |
| W3 回退 `_literal_mode` 的位置修正 | 守卫自检 | 红 | **杀死** ✅ |
| W4 §3-2 探针：属性式 open 的 mode 位置 | 守卫判据本身 | 4/4 例判错（2 漏检 + 2 误报） | ❌ **守卫判据仍有洞（MUST-FIX 3-2）** |

## 5. 未验证项与残余风险

1. **`windows-platform` job 无法在本地验证**：本轮只做静态验证（YAML 可解析、3 job / 7 步、`runs-on: windows-latest`、反引号续行、引用的 9 条路径全部存在、无逃逸口）。真实首跑必须在 PR 上观察；另外 `windows-latest` 默认 en-US/cp1252，**不等价于 GBK**——GBK 场景仍只有本机中文环境这一路信号（该措辞已列入 MUST-FIX 3-1）。
2. **全量 `uv run pytest` 本机不可完成**（进程在 45%~67% 被资源限制杀掉，非断言失败）。本轮覆盖：web 套件全量 + 基线 5 文件 + 7 路径块 + 新增/修复用例 + 单用例变异；`tests/benchmark/*` 与其余 `tests/agent/tools/*` 未逐一复跑。
3. **`errors="replace"` 的取舍**：70 处非 node 子进程保持 locale 解码但改用 replace——比「严格 UTF-8 解码崩掉」好，但 Windows 上子进程输出为 UTF-8 时会得到替换字符（乱码）而非异常。这是本 change 明示的规则（`proposal.md:32`、守卫 docstring `:16-21`），属已知边界；`docs/known-debt.md` 未记这条边界（可选）。
4. 守卫仍会把 `open(FD_NAME)`（fd 经变量传入）报为违规（保守方向，可接受）；`SCAN_ROOTS` 不含仓库根 `.py` 与 `openspec/**/*.py`（当前无违规站点）。
5. 数字口径更正留痕：本报告已更正 Round-1/2 对 benchmark smoke 数字的判断（`uv run` 原命令复现 5/29；直接调用 exe 得 0/34 是调用偏差，非缺陷）。

## 6. 结论

- **verdict：CHANGES_REQUESTED**，3 条 MUST-FIX（2 条 MEDIUM + 1 条 LOW），全部是小改动：
  1. `docs/testing-guide.md:28`/`:31-33`/`:44` 的子进程规则与守卫判据更新为「`encoding=` **或** `errors="replace"`」；
  2. `tests/web_tests/test_encoding_hygiene.py:65-84` 的 `_literal_mode` 改为「绑定形态仅 1 个位置参数时取 `args[0]`，≥2 个位置参数取 `args[1]`」（本报告已用内存补丁验证：4 个错例全消、自检仍 5），并补 `io.open('b.txt','w')` 样例；
  3. `tasks.md:33`（及 `:30`）的对比数字 / 代理验证数字更新为最终修订口径。
- **Round-1 的 8 条 MUST-FIX 均已实质关闭**（M1–M7 全部实测通过，M8 的点名位置已改，仅 testing-guide 这一新增位置漏改）；**无新增红**（web 533/0、基线 9 不变、7 路径块 15 修复 / 0 新增）。
- 上述 3 条修完后，本 change 可判 PASS；其中第 2 条属守卫自身正确性（假阴性窗口），建议连同自检样例一起补，避免归档后才发现机械门禁有漏检。
