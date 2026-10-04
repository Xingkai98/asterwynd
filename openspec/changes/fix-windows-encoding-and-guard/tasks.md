# Tasks: 修 Windows/locale 编码缺陷类并加机械防护

## 1. 立项与定位

- [x] 1.1 写 `diagnosis.md`（Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests）——含本机实测日志、磁盘状态、站点清点、以及「CI 在 Linux 上结构上看不见这类」的归因
- [x] 1.2 写 `proposal.md`（Change Type / Why / What Changes / Capabilities / RIR `light`（PEP 597 + Ruff PLW1514 + 仓库先例）/ Impact Analysis / 非目标）
- [x] 1.3 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）

## 2. 修生产站点（测试先行）

- [x] 2.1 先写失败测试：L2 的 emoji/CJK 往返 + C locale 子进程往返——**在未修的代码上实测 6 条红**（含 PEP 597 在 `session.py:232` 报出的 `EncodingWarning: 'encoding' argument not specified`）
- [x] 2.2 `agent/session.py`：6 处 `open()` 补 `encoding="utf-8"`；读侧**不**用 `errors="replace"`，改为显式捕获 `UnicodeDecodeError` 并判为损坏——替换字符会把「半损内容」当完整会话交付，属静默降级（与仓库「不显示 = 没事」纪律冲突）
- [x] 2.3 `agent/session.py::list_sessions()`：快照/消息不可解码时该条以 `damaged: True` + 可读 `reason` 出现（`session_id` 取**目录名**，它一定可信），其余会话正常返回；异常不再冒泡
- [x] 2.4 `web/server.py::api_sessions`：列表条目原样透出（含 `damaged`/`reason`），接口保持 200（此前的失败形态是整个 500）
- [x] 2.5 `agent/main.py`：4 处 `read_text()` 补编码

## 3. 机械守卫与测试站点

- [x] 3.1 新增 `tests/web_tests/test_encoding_hygiene.py`：AST 全仓扫描（`open`/`read_text`/`write_text` 缺 encoding + **node harness** 子进程缺 encoding）+ 可评审白名单 + 自检用例（守卫自身必须有牙齿）
- [x] 3.2 批量补站点：**文件 I/O 379 处**（`open`/`read_text`/`write_text`，覆盖 `agent/ benchmarks/ scripts/ tests/`）+ **捕获文本的 subprocess 70 处加 `errors="replace"`**。**范围修正（实测驱动）**：初版给全部 71 处 `subprocess(text=True)` 都补严格 UTF-8，导致 `tests/test_flow_policy.py` / `test_workflow_guard.py` 等**新增 11 条红**——子进程的输出编码是**子进程的契约**（我们自己的 python CLI 在 Windows 上往管道写 locale=GBK），父进程强制严格 UTF-8 解码反而崩（实测 `show.stdout` 变 None）。已改为只钉 node harness（输出确定 UTF-8），其余子进程不动
- [x] 3.3 L2 新增 `tests/agent/test_session_encoding.py`：emoji/CJK 往返、`LC_ALL=C`+`PYTHONCOERCECLOCALE=0` 子进程往返、`PYTHONWARNDEFAULTENCODING=1` 下无 `EncodingWarning`、列表降级、落盘字节可按 UTF-8 解出、路径校验回归
- [x] 3.4 变异验证（4 条，全部被杀）：① 去掉写侧 `encoding=` → L1 红；② 去掉快照降级分支 → L2 红；③ 去掉消息降级分支 → L2 红；④ 自检用例（守卫自身）能抓住缺 encoding 的样例
- [x] 3.6 **子进程解码不得崩**（审阅 M7 驱动）：`asterwynd benchmark … --agent fake` 原先一次跑出 **16 处** `UnicodeDecodeError`（子进程写 UTF-8、父进程按 locale 解码 → `_readerthread` 抛错丢整段输出）；给 70 处捕获文本的 subprocess 补 `errors="replace"` 后重跑 **0 处**，L1 守卫判据同步升级为「`text=True` 必须至少有 `encoding=` 或 `errors=`」
- [x] 3.7 **Hub 层用例**（审阅 M6）：`tests/web_tests/test_multi_session.py` 补 2 条 —— 含 emoji 的会话 → `GET /api/sessions` 200 且出现在列表；单条损坏 → 200 + `damaged`/`reason`
- [x] 3.5 **批量改动保真校验**：用同一套 AST 逻辑从 `HEAD` 原文重算插入点，与工作区**逐字节比对**（71 个文件全部一致 ⇒ 只插入了关键字）；另对 72 个改动文件做 `ast.parse` 全通过

## 4. CI 与纪律

- [x] 4.1 `.github/workflows/ci.yml`：`validate` job 增加 C-locale 步骤（`LC_ALL=C` + `PYTHONCOERCECLOCALE=0` + `PYTHONUTF8=0`，跑 session/encoding/server 子集）；本机模拟该步骤通过
- [x] 4.2 `.github/workflows/ci.yml`：新增 `windows-platform` job（`windows-latest` + `playwright install chromium`，跑平台敏感子集）；**本机按同一文件清单实跑 `207 passed / 1 skipped`** 作为代理验证
- [x] 4.3 `docs/testing-guide.md`：新增「平台与编码纪律」（三条规则 + 两条写平台相关测试的经验）
- [x] 4.4 平台假设修正（8 条恒红用例）：`/etc` 在 Windows 非绝对路径 → 参数化改用**平台解析后**的敏感根；`~` 展开补 `USERPROFILE`/`HOMEDRIVE`/`HOMEPATH`；NUL 字节用例改用 `tmp_path` 绝对路径；大小写变体用例 `skipif(os.name == "nt")` 并写明前提不成立
- [x] 4.5 本机复验：`tests/web_tests` = **533 passed / 0 failed**（本 change 之前 9 failed；+2 为 Hub 层新用例）；13 文件对比块 = pristine master **34 failed → 本分支 23 failed**，**新增回归 0 条**，另有 **11 条既有红**被本次修复（memory / persistent / reversibility / read_doc）
- [x] 4.6（原始记录）**benchmark smoke**：本 change 触及 `agent/` 核心路径，触发核心路径 smoke 要求。实测 `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir <tmp>`：**本 change 之前**该命令在本机（Windows + GBK locale）因 `Path.read_text()` 解码 UTF-8 直接 `UnicodeDecodeError` 失败；**本 change 之后**可正常跑完（`Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29`——失败项是 fake runner 对未实现任务类型的预期结果，关键结论是**命令本身不再因编码崩溃**）

## 5. 收尾

- [ ] 5.1 (closeout) 把 spec delta 同步到 current spec（`openspec/specs/web-ui/spec.md`；受保护路径，需结构化事件）
- [ ] 5.2 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描后按事实更新
- [ ] 5.3 (closeout) 从 `docs/openspec-change-backlog.md` 移除（受保护路径，需结构化事件；与归档同步）
- [ ] 5.4 (closeout) 归档到 `openspec/changes/archive/2026-10-04-fix-windows-encoding-and-guard/`（受保护路径，需结构化事件）
- [ ] 5.5 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [ ] 5.6 (closeout) `uv run python scripts/check_openspec_artifacts.py` 与 `--check-archived --skip-protected-paths --skip-backlog`
- [ ] 5.7 (closeout) `/review-loop` 独立审阅至 PASS 或 3 轮封顶，报告落 `reviews/building-review.md` + manifest（manifest 在 5.4 归档 move 之后生成）
- [ ] 5.8 提交分支并写好 PR 描述
- [ ] (post-merge) 推送分支并创建 PR、创建关联 GitHub issue 并把编号回填

## 6. 审阅修复（review-loop Round 1 → Round 2）

- [x] 6.1 **M1/M2/M3（HIGH）L3 CI 与纪律文档整体缺失**：`.github/workflows/ci.yml`（C-locale 步骤 + `windows-platform` job）与 `docs/testing-guide.md`（「平台与编码纪律」）被实现过程中的一次 `git checkout -- .`（重置批量补丁）连带回滚，而 tasks 已勾选。已重新落盘并逐项验证：YAML 三个 job 可解析、windows job 7 步（含 `playwright install chromium`）
- [x] 6.2 **M3（HIGH）新增回归恒红 + 声称覆盖的分支没覆盖**：`tests/agent/test_session_encoding.py` 的 `sess_worse` 载荷是纯 ASCII（GBK 编码后仍是合法 UTF-8）⇒ 解码根本不失败、断言恒失败。载荷改为含中文后 **9 passed**，且两条降级分支的变异都被杀
- [x] 6.3 **M4（HIGH）spec delta 的 MODIFIED 块未逐字保留 + host 语义写反**：用现行 spec 的原文逐字重建两个 MODIFIED 块（`Web session 本地持久化与恢复` 5 条 Scenario + `Web UI 提供 session hub 列表` 4 条 Scenario），修正 `host 绑定策略为 127.0.0.1`（原文被我误写成「不得为」）；新增 3 条 Scenario 挂在正确的 requirement 下。**独立校验**：脚本比对既有 Scenario 名与正文逐字节一致、只增不减
- [x] 6.4 **M5（MEDIUM）backlog 入队缺失但有事件**：`docs/openspec-change-backlog.md` 重新入队（同一 `backlog_updated` 事件对应的内容已落盘）
- [x] 6.5 **M6（MEDIUM）承诺的 web 层用例不存在**：`tests/web_tests/test_multi_session.py` 补 `test_api_sessions_returns_200_with_emoji_session` 与 `test_api_sessions_marks_damaged_entry_without_failing`（均 200 + 列表/标注断言）
- [x] 6.6 **M7（MEDIUM）benchmark smoke 数字不可复现 + 运行期 16 处解码崩溃**：崩溃已修（70 处捕获文本的 subprocess 补 `errors="replace"`，重跑 0 处）；数字以 fresh `--runs-dir` 两次实跑为准（`passed: 5 | unsupported: 38 | failed: 29`），并如实记录「不同 runs-dir 状态下数字会变」这一事实
- [x] 6.7 **M8（MEDIUM）`errors="replace"` 口径矛盾**：proposal / diagnosis / spec delta 全部改为与实现一致——**文件读侧不用 `replace`**（判为损坏并如实暴露），**subprocess 侧用 `replace`**（不确定子进程编码时也不许崩）
