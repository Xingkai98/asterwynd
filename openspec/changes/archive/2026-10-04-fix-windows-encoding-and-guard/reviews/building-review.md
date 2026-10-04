# Building Review: fix-windows-encoding-and-guard

**PASS**

- **reviewer run id**：`building-review-fix-windows-encoding-and-guard-20261004-r4`
- **审阅时间**：2026-10-04T19:55+08:00（本机 Windows + 中文 locale `cp936`，即本 change 的目标环境）
- **审阅对象**：worktree `D:\code\asterwynd-worktrees\fix-windows-encoding-and-guard`，分支 `fix-windows-encoding-and-guard/2026-10-04`
  - **HEAD**：`547194277f36c3bfc93b8e24de86e3404e13020e`（`fix(encoding): 审阅 Round 3 的 3 条 MUST-FIX（守卫假阴性 / 纪律文档口径 / tasks 数字）`）
  - base：`da8621f08d2bd51be949304148a1e57b997a34b4`（=`master`）；审阅前后 `git status --porcelain` 为空
  - 本轮增量：`31ac3ee..5471942` = `docs/testing-guide.md`、`openspec/.../tasks.md`、`tests/web_tests/test_encoding_hygiene.py`（+ 上一轮报告的覆写）
- **受控文件 sha256（当前工作区，逐一复核）**

| 文件 | sha256 |
|---|---|
| `docs/testing-guide.md` | `c43b1fa69f6a9cf9296a4606a8e6bec7c6f4c09b4c84b43be5440e1b850bfe19` |
| `tests/web_tests/test_encoding_hygiene.py` | `de977fe0e3b8964a3424acb22519ee70e5bb5066178beb2ac81a5a7c5dfc162c` |
| `openspec/changes/.../tasks.md` | `add739f2db941d54335aae2d75116e5fc71c6e2d3c808428ee974605a23df5eb` |
| `.github/workflows/ci.yml` | `7548039e1bb9a4f73eeae054ff6424c67d090a6ec222feb13899218fa6e858a0` |
| `docs/openspec-change-backlog.md` | `922093dfdf7d9076c86c63f437103fe6776448dcf3641d4fa1d003969764e179` |
| `openspec/changes/.../specs/web-ui/spec.md` | `05e4b0959ca1121cb1abbe2c1bfde51c364196e6d3013669f35907944f7d4045` |
| `tests/agent/test_session_encoding.py` | `4e1dd56d1f1c944ebe49a637943bd91761138e6dea0d0868b3939e5af0ab0b6a` |
| `tests/web_tests/test_multi_session.py` | `26771273a3ca1238c51f754afb8e50ce7101620aae3bbd82061487441ac9bf44` |
| `agent/session.py`（冻结不变） | `dc26072d85c435f9686724879fda0e013fd2b65f0eeb1f2a98402d51268b315b` |
| `web/server.py`（冻结不变） | `82e1e7f795604178…`（自 Round 1 起未改动） |

**判据：`PASS` 需 0 条 MUST-FIX。本报告确认 Round-1 的 8 条、Round-3 的 3 条 MUST-FIX 全部关闭，且无新增红 ⇒ 0 条 MUST-FIX。** 另记录 2 条 LOW 级观察（守卫的窄假阴性窗口、自检样例未逐行钉住）与 2 条本地不可完成的验证，均为**非阻塞**，见 §4/§5。

## 1. 本轮 3 条 MUST-FIX 的关闭确认（`31ac3ee` → `5471942`）

| # | Round-3 问题 | 状态 | 本轮实测证据 |
|---|---|---|---|
| M1 | `docs/testing-guide.md` 子进程规则与守卫判据分裂 | **关闭** | `:28` 重写为「**子进程的规则不同（输出编码是子进程的契约）**……因此对**每一个** `text=True` 的子进程，二者至少要有一个」，并给出两个可复制示例（`:31` `node … encoding="utf-8"` / `:32` `git … errors="replace"`）；`:37-38` 的守卫判据改为「`text=True` 的子进程**既无 `encoding=` 也无 `errors=`**」，与 `test_encoding_hygiene.py:161-165` 完全一致；`:49` 的 windows 覆盖改为「编码往返（该 runner 是 **en-US/cp1252**，**不是** GBK；GBK 只在中文 Windows 本机成立）」。逐行读核 + 关键词扫描通过 |
| M2 | `_literal_mode` 守卫假阴性（`io.open(path, mode)` 读错字段） | **关闭** | 落盘实现即我 Round-3 用内存补丁验证过的修法（`test_encoding_hygiene.py:65-89`：`is_bound_open and len(args)==1 → args[0]`，`elif len(args) >= 2 → args[1]`），docstring 补了「两种形态都会踩」的说明；自检样例补 `io.open('b.txt','w')`（应报）与 `io.open('i.txt','rb')`（不应报），期望命中数 5→6。**我的 7 个反例全部按预期**（见 §2.2）；`guard + L2` = **11 passed** |
| M3 | `tasks.md` 对比数字与代理验证数字过期 | **关闭** | `tasks.md:30`（4.2）改为「本机按该 job 的 **7 文件清单**实跑 `209 passed / 1 skipped`」——我按 CI job 里那 7 个文件原样复跑，得 **209 passed / 1 skipped**，数字一致；`tasks.md:33`（4.5）改为 `533 passed / 0 failed`、pristine `34 failed → 19 failed`、**15 条**既有红被修、新增回归 0，与同页 §6 及我的实测一致 |

## 2. 复现与证据（本轮在 `5471942` 上实跑）

### 2.1 测试与校验

```
$ pytest tests/web_tests -q                                   → 533 passed, 9 skipped   (0 failed)
$ pytest <CI windows-platform 的 7 文件清单> -q                → 209 passed, 1 skipped
$ pytest tests/web_tests/test_encoding_hygiene.py tests/agent/test_session_encoding.py -q
                                                              → 11 passed
$ pytest <7 路径块: memory/, read_doc, read_write, edit, test_session, workspace_policy, memory_e2e>
                                                              → 5 failed, 316 passed
   （与 pristine 捕获的 FAILED 集合做差集：新增回归 = [] ，被修 15 条）
$ pytest <基线 5 文件: bash×3 + flow_policy + workflow_guard>  → 9 failed, 66 passed   （与 pristine 完全一致）
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict → Totals: 29 passed, 0 failed
```

对比 pristine `D:\code\asterwynd`（master）：`tests/web_tests` = `9 failed / 521 passed / 8 skipped`，`7 路径块` = `20 failed / 301 passed`。本轮修订后：`0 failed` 与 `5 failed`，**无新增红**。

### 2.2 守卫判据探针（我的独立样例，逐行断言期望值）

```
样本                                  HEAD(5471942)  期望
Path('x.bin').open('rb')              ----          不报 ✅   （Round-3 误报已修）
Path('y.txt').open('w')               FLAG          报   ✅
io.open('b.txt', 'w')                 FLAG          报   ✅   （Round-3 漏检已修）
builtins.open('baseline.json', 'w')   FLAG          报   ✅   （Round-3 漏检已修）
io.open('x.txt', 'rb')                ----          不报 ✅   （Round-3 误报已修）
gzip.open('f.gz', 'rb')               ----          不报 ✅   （Round-3 误报已修）
io.open('i.txt', 'rb')                ----          不报 ✅   （新增自检样例）
os.open('h.txt', os.O_RDONLY)         ----          不报 ✅
open('d.txt', 'w')                    FLAG          报   ✅
```

### 2.3 批量改动的保真（累计，Round-1/2 的结论在本轮继续有效）

- Round-1：`da8621f..0575ee4` 的 385 处新增 `encoding="utf-8"`（378 文件 I/O + 1 node harness + `agent/session.py` 6）经「行级 + 行内字符级 + AST 父调用绑定」三重校验，**全部为纯关键字插入**（`MISMATCH=0`、均为最后一个 kwarg、74 个改动 `.py` 全部 `ast.parse` 通过）；交叉验证：把守卫扫描逻辑指向 pristine 树恰好报 **385** offenders、指向分支报 **0**。
- Round-2：`0575ee4..40d5541` 新增的 **70 处 `errors="replace"`** 经同一管线校验，**全部为 `subprocess.run(..., text=True)` 的纯关键字插入**、全部最后一个 kwarg、**无一处同时带 `encoding=`**；结构性改动仅 3 个文件（fixture / 守卫 / 新用例）。
- 本轮（`31ac3ee..5471942`）只有 `_literal_mode` 与自检样例的改动，无新增编码站点；改后 `.py` 全部可解析，测试全绿。

## 3. tasks.md 逐项验证（最终状态）

| # | 任务 | 勾选 | 判定 |
|---|---|---|---|
| 1.1–1.2 | diagnosis.md / proposal.md | [x] | ✅ 成立 |
| 1.3 | backlog 入队（受保护路径 + 事件） | [x] | ✅ 成立（未实现队列首位 `### 1. fix-windows-encoding-and-guard`，文件已落盘且事件一致） |
| 2.1 | 先写失败测试（历史声明） | [x] | ⚠️ 无法在 HEAD 复核（仅能证 `2959990` 版 L2 = 9 passed），见 §5 |
| 2.2 | session.py 6 处 open + 读侧判损坏 | [x] | ✅ 成立（`:119/121/170/198/256/258`；`:123/172/201` 捕获 `UnicodeDecodeError`，无 `errors="replace"`） |
| 2.3 | list_sessions 单条降级（快照/消息两条分支） | [x] | ✅ 成立，且**两条分支各有变异能杀**（R2-A / R2-B） |
| 2.4 | api_sessions 原样透出 + 200 | [x] | ✅ 成立（`web/server.py:331-332` 透传；R2-C 变异杀 Hub 用例） |
| 2.5 | main.py read_text 补编码 | [x] | ✅ 成立（实际 6 处：4 read_text + 2 write_text；总数口径 379 = 378 + 1 与实测吻合） |
| 3.1 | L1 守卫 + 白名单 + 自检 | [x] | ✅ 成立（`ALLOWLIST` 为空；W1/W2/W3 变异均被杀；全仓 0 offenders） |
| 3.2 | 批量补 379 处（378 文件 I/O + 1 node harness） | [x] | ✅ 成立（实测 385 = 378 + 1 + session.py 6） |
| 3.3 | L2 用例（往返 / C-locale / EncodingWarning / 降级 / 落盘字节 / 路径校验） | [x] | ✅ 成立（11 passed；M16 型变异全套被杀） |
| 3.4 | 变异验证 | [x] | ✅ 成立（M2/M3 两分支、L1 站点均被杀，见 §4 变异表） |
| 3.5 | 批量改动保真校验 | [x] | ✅ 成立（我用独立方法复核一致） |
| 3.6 | 子进程解码不崩（70 处 `errors="replace"` + 守卫判据升级） | [x] | ✅ 成立（benchmark 重跑 `UnicodeDecodeError` = 0；注入无 `errors=` 的 `text=True` 子进程 → 守卫红） |
| 4.1 | CI C-locale 步骤 | [x] | ✅ 成立（YAML 可解析；`validate` 11 步含该步骤；5 个引用文件均存在） |
| 4.2 | CI `windows-platform` job | [x] | ✅ 成立（3 job / 7 步 / `windows-latest` / PowerShell 反引号续行 / 无逃逸口；7 文件清单本机实跑 **209 passed / 1 skipped**） |
| 4.3 | testing-guide「平台与编码纪律」 | [x] | ✅ 成立（三条规则 + 三条经验，口径已与守卫一致） |
| 4.4 | 平台假设修正（8 条恒红） | [x] | ✅ 成立（web 套件 9 red → 0 red；断言未放宽） |
| 4.5 | 本机复验数字 | [x] | ✅ 成立（533/0；34 → 19；15 条被修；新增回归 0 —— 与我的实测一致） |
| 4.6 | benchmark smoke | [x] | ✅ 成立（用文档原命令 + fresh runs-dir 复现 `passed: 5 / unsupported: 38 / failed: 29`，`UnicodeDecodeError` = 0） |
| 5.1–5.8 | closeout（spec 同步 / 文档影响 / backlog 移除 / 归档 / validate / checker / 审阅 / PR） | [ ] | ⏳ 待办，符合 building 阶段预期；5.1 现在可安全执行（见 §4 的 delta 验证） |
| 5.9 | `(post-merge)` 推送 + 建 issue 回填 | [ ] | ✅ 标记合规 |

## 4. Issues

**MUST-FIX：无。** 归档前不需要再改代码。

**非阻塞观察（LOW，建议随后续 change/issue 处理，不影响本轮 PASS）**

1. **【LOW】守卫仍有一个窄假阴性窗口（1 位置参数的模块式 open）**——`tests/web_tests/test_encoding_hygiene.py:65-89`：当属性式 `open` **只有一个位置参数且该参数是含字母 `b` 的字符串字面量**时，`args[0]` 被当成 mode，于是被误判为二进制而跳过。实测：`io.open('b.txt')`、`builtins.open('baseline.json')` 不报（应为文本 open，缺 `encoding=`）；对照 `io.open('notes.txt')`（路径不含 `b`）会报 ✅。
   - 复现：把这三行喂给 `_check_file`（脚本见 Round-3/4 探针），只有含 `b` 的两行漏报。
   - 当前暴露面：**零**——全仓扫描「模块式属性 open」调用数为 **0**（`agent/ web/ benchmarks/ scripts/ tests/` 全量）；且变量路径形态（`io.open(p)`）、`mode=` 关键字形态、内置 `open(...)` 都**不会**漏。
   - 若要封口，最小改法是把「绑定 vs 模块」判定收敛为「单参数是否为 `^[rwaxb+]{1,3}$` 形态的字面量」或按接收者名（`io`/`builtins`/`gzip`…）区分；也可只在 docstring 里记明该边界。
2. **【LOW】新增的两条自检样例只钉「命中总数」，未逐行钉住**——`:214-232`：把 `_literal_mode` 回退成 Round-3 的 buggy 版本后，`io.open('b.txt','w')` 漏报（−1）与 `io.open('i.txt','rb')` 误报（+1）**相互抵消**，`assert len(problems) == 6` 仍然通过（我实跑该变异 = `2 passed`，**变异存活**）。
   - 判据：自检样例的注释已写明「`io.open('b.txt','w')` 应报、`io.open(...,'rb')` 不应报」，但断言只比较数量，无法区分这两行。
   - 建议（3 行）：把断言改成行号集合，例如 `assert {int(p.split(":")[1]) for p in problems} == {...}`。
3. **【LOW】`docs/known-debt.md` 未记录**「非 node 子进程用 locale + `errors="replace"`」这一边界的取舍（Windows 上子进程若写 UTF-8 会得到替换字符而非异常）。该取舍已在 `proposal.md:32`、守卫 docstring `:16-21`、`testing-guide.md:28-32` 三处写明，故只是「是否另记债务」的选择。

## 5. 未验证项与残余风险

1. **`windows-platform` job 仍无法在本地验证**：本轮只做静态验证（YAML 解析、3 job / 7 步、`runs-on: windows-latest`、反引号续行、7 个测试路径均存在、无 `continue-on-error`/`|| true`/`--deselect`）＋按该 job 的 7 文件清单本机代理跑（209 passed / 1 skipped）。**首跑必须在 PR 上观察**；另该 runner 是 en-US/cp1252，GBK 场景仅由本机中文环境覆盖（该事实已写入 `testing-guide.md:49`）。
2. **全量 `uv run pytest` 本机不可完成**（进程在 45%~67% 处被资源限制杀掉，`[exit code: 1]` 无断言失败，属进程级终止）。本轮覆盖：`tests/web_tests` 全量、CI windows 子集 7 文件、基线 5 文件、7 路径块、新增/修复用例、单用例变异；`tests/benchmark/*` 与其余 `tests/agent/tools/*` 未逐一复跑。
3. **tasks 2.1 的历史声明**（「未修代码上实测 6 条红」）无法在 HEAD 复核；我能证明的是 `2959990` 版 L2 文件为 `9 passed`，不构成阻塞。
4. **C-locale 步骤只跑 5 个文件**（子集，非全量）——成本/收益取舍，属设计选择；`validate` 的默认 job 仍跑全量 pytest（Linux/UTF-8）。

## 6. 变异验证结果表（累计，全部按字节还原、sha256 前后一致、`git status` 为空）

| 变异 | 目标 | 观察 | 判定 |
|---|---|---|---|
| 去 `agent/session.py:119` 的 `encoding=`（open 站点） | L1 守卫 | 红 | 杀死 ✅ |
| 去 `agent/main.py:968` 的 `encoding=` | L1 守卫 | 红 | 杀死 ✅ |
| 去 node harness（`test_server.py:698`）的 `encoding=` | L1 守卫 | 红 | 杀死 ✅ |
| 注入裸 `open()` / 裸 `read_text()` | L1 守卫 | 红 | 杀死 ✅ |
| 注入无 `encoding=`/`errors=` 的 `text=True` 子进程 | L1 守卫 | 红 | 杀死 ✅ |
| 去真实站点 `tests/test_flow_policy.py:33` 的 `errors="replace"` | L1 守卫 | 红 | 杀死 ✅ |
| 守卫自削弱：去 `Image` 排除 / 关 node 判据 / 关 read_text 判据 | 守卫自检 | 红 | 杀死 ✅ |
| 守卫自削弱：放宽二进制排除（任何字面量 mode 都跳过） | 守卫自检 | 红（Round-1 曾存活，已封口） | 杀死 ✅ |
| 守卫自削弱：回退 `os.open` 排除 | 守卫自检 | 红 | 杀死 ✅ |
| 守卫自削弱：回退 `_literal_mode` 绑定位置修正 | 守卫自检 | 红 | 杀死 ✅ |
| 去 `_write` 写 messages 的 `encoding=`（携带 emoji） | L2 全套 | 6 failed（含 C-locale 子进程用例报 `UnicodeEncodeError: 'gbk' … '\U0001f44b'`） | 杀死 ✅ |
| 去 `_write` 写 snapshot 的 `encoding=`（弱变异，载荷 ASCII） | L2 | 由 `EncodingWarning` 用例杀死 | 杀死 ✅ |
| 去 `list_sessions` 读 messages 的 `encoding=` | L2 | 红（`:114` damaged 断言） | 杀死 ✅ |
| 去 `list_sessions` 的 snapshot 降级分支 | L2 | 红（fixture 修好后是真信号） | 杀死 ✅ |
| 去 `list_sessions` 的 messages 降级标注 | L2 + 新 Hub 用例 | 两条各自红 | 杀死 ✅ |
| 只修 fixture 不改实现（对照） | L2 | 9 passed（证明原红是 fixture 缺陷） | 对照通过 |
| 让 `api_sessions` 过滤 damaged 条目 | 新 Hub 用例 | 红 | 杀死 ✅ |
| 去 `_write` 写 messages 的 `encoding=`（新 Hub emoji 用例） | 新 Hub 用例 | 红 | 杀死 ✅ |
| 回退 `_literal_mode` 到 Round-3 buggy 版 | 守卫自检 | **green（存活）** | ❌ 存活 → 见 §4-2（非阻塞） |

## 7. 结论

- **verdict：PASS —— 0 条 MUST-FIX。归档前不需要再改代码。**
- Round-1 的 8 条 MUST-FIX（L3 CI 与纪律文档缺失、backlog 入队缺失、新增回归恒红 + 降级分支未覆盖、delta 非逐字保留 + host 语义写反、web 层用例缺失、benchmark 运行期 16 处解码崩溃、`errors="replace"` 口径矛盾）与 Round-3 的 3 条 MUST-FIX（守卫假阴性、纪律文档口径、tasks 数字）**全部已在当前 HEAD `547194277f36` 上实测关闭**。
- 关键不变量均已由独立方法复核：批量补丁只插入关键字（385 + 70 处，AST 父调用绑定校验 `MISMATCH=0`）、守卫对 pristine 树报 385 offenders 而对分支报 0、delta 经 OpenSpec 自己的 `buildUpdatedSpec` 重建后既有 Scenario **逐字节不变且只增不减**（161 → 164）、测试无新增红（web `533 passed / 0 failed`；基线 5 文件不变；7 路径块 15 修复 / 0 新增）。
- 归档收尾（tasks 5.1–5.8）可继续推进：`5.1` 的 spec 同步现在可以安全执行（delta 已自洽、host 句与实现一致）；`5.7` 的 manifest 请在 `5.4` 归档 move 之后生成（本报告未写 manifest）。
