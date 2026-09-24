# Building Review: fix-issue-226-browser-test-flake

> 两轮记录同文：**Round 1**（head `a3d1ae8`）verdict = CHANGES_REQUESTED，8 条 issue；**Round 2**（head `aa57fa0`）verdict = **PASS**，Round 1 的 blocker/major 全部闭合。Round 1 的发现与证据完整保留在「Round 1 发现与处置」节。

## Reviewer

- run id: `review-fix-issue-226-browser-test-flake-r2`（独立零记忆 subagent，未继承开发上下文；结论只来自实读代码 / 实跑输出 / change 文档）
- 时间：Round 1 = 2026-09-24（head `a3d1ae8`）；Round 2 = 2026-09-24（head `aa57fa0`）
- base: `d757683`（origin/master）
- 审阅方法（作者自述一律不作依据）：
  - Round 1：逐条核对 tasks 的 `[x]`；**两条回归测试各做一次变异验证**（改测试侧屏障 → 实跑 → 恢复）；实跑相关子集 + checker + strict validate；独立重算暴露面（不采信 D6 的 15/6/3，自建口径重数）；对 18 条改造用例逐 hunk 核对「只加屏障、未改断言」（`git diff -U0 | grep '^-'` 全量过删除行）
  - Round 2：核查 `aa57fa0` 逐条修复；**fail-loud 用例重复单跑 6 次**；**重做判别力变异**（把 `_wait_app_ready` 退回旧实现，确认重排后的用例**仍然**守护 fail-loud 且**未被削弱**）；**新增变异**（让 CDP 注入静默失效，确认「注入生效」守卫不空转）；全文件扫 `design.md`/`diagnosis.md`/`tasks.md` 找旧措辞残留；实跑两个测试文件 + checker + strict validate
- 资源纪律：全程单进程、串行、无并发、不跑全量

## Verdict

**Round 2：PASS**

Round 1 的唯一 major（I1：新用例的活竞态）**已按要求修复，且我做了三重独立验证**：①结构上，`initDone` 全仓只有一个写入点（`chat.js:2128` 的 `init().then`）且 `init()` 只被调用一次，等置位后再 `delete` 便不可能被重设；②经验上，修改后重复单跑 6 次全绿且耗时稳定 17.4s（走满屏障超时路径 = 触发路径确定，不是碰巧）；③**判别力未被削弱**——我把 `_wait_app_ready` 退回旧实现（含吞异常降级）后，重排后的用例**仍然转红**（`DID NOT RAISE`，13.2s），说明「先等再删」没有把用例改成恒过。

I2/I3/I4/I5/I6/I8 六条 minor 中，I4/I5/I6/I8 **已完整修复**（措辞与事实逐条核对一致）；I2/I3 的**实质结论已修复**（`design.md` D4 + Testing Strategy 已改为「只保留正向半场 + 注入守卫取注入值 × 50% + 偏离理由」，并且我**实测证明该阈值取舍成立**：注入静默失效时握手仅 99ms，守卫报错「远低于注入值 3000ms」，判别力充足），但**文档层面留了 3 处旧措辞未同步**（`tasks.md:25`、`diagnosis.md:141`、`diagnosis.md:78`），见「残留问题」。这 3 处均为 low、纯文档、不影响代码/规格/门禁，按本仓库审阅惯例（low/info 不阻塞）不改变 verdict，但建议归档前一并修掉。

另有一条**流程性提醒**（非缺陷）：`aa57fa0` 把 Round 1 的 `building-review.md` 提交进树后，`check_openspec_artifacts.py` 现在**报红**（`review manifest missing`）——这是「审阅报告已入树、manifest 未生成」的**预期过渡态**（tasks 6.4 未勾），但 baseline CI 含该 checker，故必须在 PR 前闭合；且顺序有硬约束（见残留问题 R4）。

## Round 1 发现与处置（逐条复核）

| # | 严重度 | Round 1 发现 | Round 2 状态 | 本轮核查证据 |
|---|---|---|---|---|
| I1 | major | `test_ready_barrier_fails_loudly_when_signal_is_absent` 的 `delete initDone` 早于 `init()` resolve ⇒ `init().then` 回调会把标志**重新置回 true**，`_wait_app_ready` 立即返回，用例偶发失败（`DID NOT RAISE`） | **已修（验证通过）** | 测试现在先 `await _wait_app_ready(page)`（`:1299`）再 delete（`:1300`）。结构核查：`grep initDone` 全仓仅 `chat.js:2125/2128` 两处写；`grep "init()"` 确认 `init()` 只被调用一次（`workflow.js:1273` 是无关的模块内同名函数）⇒ 置位后无人再写。经验核查：单跑 6 次全绿、耗时 17.38–17.43s（稳定走满 15s 超时路径）。**削弱性核查**：把 helper 退回旧实现后本用例仍 `1 failed`（`Failed: DID NOT RAISE <class TimeoutError>`，13.22s）⇒ 重排没有把用例变成恒过 |
| I2 | minor | 回归 A 的注入守卫实为 `handshake_ms >= injection_ms * 0.5`，与 Q4 拍板原文「≥ 注入值」不符，且 tasks 2.3 描述未同步 | **实质已修；tasks 描述残留** | `tests/web_tests/test_multi_session_browser.py:893` 仍是 ×0.5（有意保留）；`design.md:124` 已写明「取 3000ms + 断言 ≥ 注入值的 50%」与偏离理由（**理由成立**：我实测注入正常时 `handshake_ms=3095`、注入静默失效时 99ms，阈值 1500 两侧余量分别 2× 与 15×）。残留：`tasks.md:25`（2.3）仍写「回归 A 断言「屏障实测等待 ≥ 注入值」」→ R1 |
| I3 | minor | `design.md` 仍写已移除的「负向半场」与「≥ 注入值」 | **已修（D4 + Testing Strategy）；另 3 处残留** | `design.md:128` 与 `:191` 均已改为「只保留正向半场 + 50% 阈值 + 理由」，措辞与实现一致。全文件扫描另见残留 R2（`design.md:122` 同一短语，属回归 B 语境，不影响正确性） |
| I4 | minor | `proposal.md` Non-Goal 称 `test_browser.py` / `test_reconnect_*`「不受本类 flake 影响」口径过宽（点击腿同源竞态未覆盖） | **已修（验证一致）** | `proposal.md:93` 已收窄为「发送腿受 `connected` 屏障保护、点击腿有残留、记为已知残余面」；`docs/known-debt.md:343-347` 新增该残余面条目，事实逐条核对无误（`index.html:43` 确为 `<section id="hub-view" class="view active">` 静态即满足；`setupHub()` 在 `chat.js:2031`，`hubNewBtn.addEventListener` 在 `:2039`） |
| I5 | minor | 第 4 份重复 preamble（`test_multi_tab_image_preview_isolation`）未收敛 | **接受「不做」（理由成立）** | `test_multi_session_browser.py:704-708` 加注释说明「该用例不发消息、不属根因 A 暴露面，收敛属纯重构」。核查：该用例确实只 `set_input_files` 断言预览区，不点发送 ⇒ 不属暴露面，「不扩大范围」正当。残留：`diagnosis.md:78` 该表口径仍不精确 → R3 |
| I6 | minor | `_ensure_workflow_view` 之后显式 `startTicker()` 看似冗余、注释半陈旧 | **已修** | `test_workflow_graph_browser.py:808-811` 注释改为「本用例断言全部依赖 ticker 在跑，显式再起一次作为**局部声明**，不把前提隐式挂在 helper 上」。与 `:170-173` 的 helper 版 `startTicker()` 并存**无问题**（`workflow.js:525-528` 幂等：`tickHandle !== null` 即返回），我实跑该用例通过 |
| I8 | minor | `known-debt.md` 引用未归档路径 + 「证伪」措辞过绝对 | **已修（验证一致）** | `docs/known-debt.md:309` 改为「该断言不成立（就『治住』而言已被实测推翻）」；`:348-349` 补「该归档路径在本条目写入时尚未归档，随本 change 的归档 commit 落地（归档目录缺失时以 active 路径为准）」——自洽且如实 |

## 残留问题（本轮均 low，不阻塞 PASS）

### R1（low，文档与实现不符）

`openspec/changes/fix-issue-226-browser-test-flake/tasks.md:25`（2.3 已勾 `[x]`）仍写「回归 A 断言「屏障实测等待 ≥ 注入值」」，而实现是 `>= injection_ms * 0.5`（`test_multi_session_browser.py:893`）。建议把 2.3 改成实际口径 + 一句理由（与 `design.md:124` 对齐），否则「已勾任务」的描述与代码不符会被后来的审阅者当成漏项。

### R2（low，残留旧措辞）

`openspec/changes/fix-issue-226-browser-test-flake/diagnosis.md:141`（`## Regression Tests` 表第一行）仍描述**已被移除的负向半场**：「新 tab 未等就绪即发送 → 发不出（前置条件）；补屏障后 → 成功发出并收到 assistant 回复」。建议改为「注入 3000ms → 等 rekey 屏障后发送 → 送达；判别力来自去掉屏障则发送落空（已两向实测）」，与 `design.md:128` 对齐。（同表第二行描述回归 B，仍准确。）

### R3（low，表格口径不精确）

`diagnosis.md:78` 的「| 其余 15 条 | 是（`_open_two_tabs`，含 rekey 屏障） | 否 / 已屏障 |」：全文件实为 19 条用例 = 13 条用 `_open_two_tabs`（改造后）+ 1 条 inline 拷贝（`test_multi_tab_image_preview_isolation`，即 I5 那条）+ 5 条单 tab。该行不改变结论（暴露面判定取自「在新 tab 发消息」），但计数不精确。

### R4（low，流程提醒 —— PR 前必须闭合）

`aa57fa0` 提交 `reviews/building-review.md` 后，`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` **报红**：

```
ERROR: fix-issue-226-browser-test-flake: review manifest missing:
  openspec/changes/fix-issue-226-browser-test-flake/reviews/building-review-manifest.json
```

（Round 1 时 checker 是绿的，因为当时报告尚未落盘。）这是预期的过渡态（tasks 6.4 未勾），但请**严格按此顺序**闭合，否则 CI 的 `validate` job 会红：

1. 先把**本报告（Round 2 版，含 PASS verdict）**提交入树 —— 现在树里的 `building-review.md` 是 `aa57fa0` 提交的 **Round 1 版（verdict=CHANGES_REQUESTED）**；若先跑 manifest 再更新报告，`report_hash` 会对不上（`agent/workflow/review_manifest.py:171-173` 强校验），且会出现「manifest 说 PASS、报告正文说 CHANGES_REQUESTED」的自相矛盾（注意：checker **不解析报告正文**，这个矛盾没有机械守护，只能靠纪律）。
2. 再按 6.4 生成 manifest（`tasks.md` 最终化 / 归档 move 之后），顺序见 AGENTS.md「Review manifest 纪律」。
3. 归档后跑 `--check-archived` 与 strict validate 复查。

### 观察（info，无需动作）

- 权威 spec 的 Scenario「多标签会话测试等待连接就绪」末条仍保留「**不适用于前置条件断言**：回归测试可以断言「未加屏障时消息发不出」…」的豁免（`openspec/specs/web-ui/spec.md:273`，delta 同文 `specs/web-ui/spec.md:36`）。负向半场已移除后，该豁免成为**未被使用的许可**——它只允许、不要求，故不构成「文档与实现不符」，无需为本 change 再加一条 `current_spec_synced` 事件；若将来有人用 `route_web_socket` 做确定性负向半场，它正好用得上。记录在此仅为避免后人误以为「spec 要求了负向断言」。
- `design.md:122`（D4 内、回归 B 语境的 bullet）仍含「（或等价地断言实测延迟 ≥ 注入值）」。对回归 B 而言该阈值（注入 6000ms vs 未注入 ~0）本来就成立，不改变任何结论；若顺手可改为「≥ 注入值的 50%」以求全文一致。

## Tasks Verification

Round 1 的逐项核对结果（对 `a3d1ae8` 有效；`aa57fa0` 只额外在 `tasks.md` 追加「审阅修复」节并改两处文档，未动实现，故本表结论仍适用）：

| 任务 | 结论 | 证据（实读/实跑） |
|---|---|---|
| 1.1 / 1.2 spec delta | **真实存在** | delta 两条 Requirement：接缝（2 Scenario）+ 就绪屏障（3 Scenario）齐全，首行均含 SHALL |
| 1.3 范围/非目标/验收 | **真实存在** | `proposal.md` Change Type / Why / What / Non-Goals / Impact Analysis 齐 |
| 1.4 grill 证据 | **真实存在** | `reviews/grill-design.md`：5 条 Confirmed Decisions + 5 条 Open Questions 逐条配具体例子 + `## User Confirmation` 5/5 有实质答复与时间（无占位文本） |
| 1.5 Impact Analysis | **真实存在** | `proposal.md:96-130`，「待确认影响面」已清理为「无」 |
| 1.6 RIR | **真实存在** | `proposal.md:132-138`，`research_tier: exempt` + reason 命中 `bugfix` / `#191` / `#223` / `openspec/changes/archive/`；findings 记录本地参考仓库与 `.codegraph` 不可用事实（我确认两者确实不存在） |
| 1.8 当前规格同步 | **真实存在且逐字一致** | delta 与 `openspec/specs/web-ui/spec.md` 字节级一致（48 行 vs 48 行），见「Spec 对齐」 |
| 2.1 回归 A | **真实存在** | `test_multi_session_browser.py:856`；CDP 注入 3000ms；只保留正向半场（与描述一致）；守卫阈值见 R1 |
| 2.2 回归 B | **真实存在** | `test_workflow_graph_browser.py:1200`；`INIT_DELAY_MS = 6000`（`:30`）；**只调 `_wait_app_ready`、不调 `_ensure_workflow_view`**（逐行确认） |
| 2.3 断言注入生效 | **部分与描述不符** | 回归 B 的「`initDone` 延迟窗口内为 `false`」真实存在（`:1226-1231`）；回归 A 实为 ×0.5 → R1 |
| 2.4 变异验证 | **描述成立，change 内无留档** | 我独立实跑两向（见 Test Results）；`tasks.md`/`design.md`/`diagnosis.md` 只写「已两向实测」，无输出留档 |
| 2.5 `initDone` 语义验证 ×2 | **真实存在** | ①完成态置位：`test_chat_init_seam_reports_completion:1255`；②未完成态 + 延迟窗口：`test_workflow_view_survives_delayed_app_init:1220-1231` |
| 2.6 负向路径守护 | **真实存在** | `test_ready_barrier_fails_loudly_when_signal_is_absent:1284`；实跑 6/6 通过且退旧实现必红 |
| 2.7 不依赖机器负载 | **成立** | 注入走 CDP / `page.route`，无 sleep 型断言 |
| 3.1 修 `_wait_app_ready` + 删降级 | **真实存在** | `:148-152`（旧 `try/except + wait_for_timeout(300)` 已删净）；`BROWSER_TIMEOUT_MS = 15000` 本文件自有（`:26`） |
| 3.2 15 条接屏障 | **真实存在，且只加屏障** | 15 条与清单 `:168/:198/:216/:233/:275/:333/:392/:433/:467/:573/:642/:664/:745/:905/:939` 一一对应；`git diff -U0` 删除行**只有** helper 正文与 3 条用例的旧导航 preamble，**无断言删改** |
| 3.2b `:168` 插入位置 | **真实存在** | `_ensure_workflow_view` 在 `assert await page.is_visible("#workflow-view")` 之后 |
| 3.2c 补 `startTicker` | **真实存在** | `:170-173`（与 `onWorkflowStarted()` 同一次 evaluate）；全仓 tests 无 `stopTicker` 依赖 |
| 3.3/3.4/3.5 三条改 `_open_two_tabs` | **真实存在** | `:275` / `:745` / `:805`；断言未动 |
| 3.6 `chat.js` 只增不改 | **真实存在** | `chat.js:2125` + `:2128`（无 `onRejected`）；唯一删除行 `-init();`，语义等价 |
| 3.7/3.8 回写影响面/RIR | **真实存在** | 「待确认影响面」已清为「无」；RIR 未被推翻 |
| 4.1–4.4 子集/重复跑/全量 | **自述，无留档** | 我可复现的部分成立：47 passed（Round 1）、28 + 19 passed（Round 2） |
| 4.5 / 4.6 / 4.7 门禁三件套 | **部分复核** | strict validate 30/30；checker 现因 manifest 报红（R4，预期过渡态）；全量 pytest 未跑（资源纪律） |
| 4.9 spec 同步 | **真实存在** | 见「Spec 对齐」 |
| 5.3 更正 known-debt | **真实存在** | `docs/known-debt.md:307-315`；`protected_artifact_explained` 事件（`workflow-events.jsonl` seq 5） |
| 5.4 新增 issue #226 记录 | **只改 known-debt.md（判断正确）** | `known-issues.md` 实为 pytest pattern 豁免清单、不是 issue 台账 ⇒ 不动正确；`tasks.md` 5.4 原文措辞「两文件」宜修正 |
| 5.5 接缝注释 | **真实存在** | `chat.js:2117-2124` 写明测试专用 / 零生产行为 / 不得当死代码移除 |
| 5.6 backlog 登记 | **真实存在** | `docs/openspec-change-backlog.md:154-156`；`backlog_updated` 事件 seq 1/4 |

**未勾任务**：6.1–6.4、7.1–7.6（审阅/归档/PR 收尾），7.6 已正确标注 `(post-merge)` —— 符合活跃 change 的中间态。

**Spec 对齐**：delta 与权威 spec 字节级一致（去 `## ADDED Requirements` 头与尾部空行后 `diff` 为空，48 vs 48 行）——**逐字一致**，无两处口径漂移；两条 Requirement 首行均含 SHALL（满足 strict validate 规则）。

**暴露面独立重算（不采信 D6）**：以「用例依赖 workflow 视图处于激活态」为口径逐函数数 —— 零屏障 15 条（`:168/:198/:216/:233/:275/:333/:392/:433/:467/:573/:642/:664/:745/:905/:939`）、只有死等 6 条（`:619/:708/:769/:821/:868/:983`）、有真屏障 3 条（`:487/:1039/:1084`），**24 = 15 + 6 + 3**，与 D6 / proposal / diagnosis / backlog 四处口径完全一致，且 `test_session_without_workflow_is_unaffected` 被正确排除（它断言的是「workflow-view **不** active」，与根因 B 反向）。

## Test Results

全部单进程串行（无并发、无加压）；命令前缀 `export PATH=/home/happy/.local/bin:$PATH`，工作目录为本 worktree。

### Round 2（head `aa57fa0`）

| # | 命令 / 操作 | 结果 |
|---|---|---|
| 1 | `uv run pytest tests/web_tests/test_workflow_graph_browser.py -q -p no:randomly` | **28 passed** in 76.97s |
| 2 | `uv run pytest tests/web_tests/test_multi_session_browser.py -q -p no:randomly` | **19 passed** in 39.76s |
| 3 | **I1 修复有效性**：`test_ready_barrier_fails_loudly_when_signal_is_absent` 重复单跑 **6 次** | **6/6 passed**，耗时 17.38 / 17.38 / 17.38 / 17.40 / 17.41 / 17.43s —— 稳定走满 15s 屏障超时路径 ⇒ 触发路径确定，非碰巧 |
| 4 | **判别力未被削弱（削弱性变异）**：把 `_wait_app_ready` 退回旧实现（`wait_for_selector(".tab-pane.active .user-input", 5000)` + `except → wait_for_timeout(300)`）后跑同一用例 | **1 failed**：`Failed: DID NOT RAISE <class 'playwright._impl._errors.TimeoutError'>`，13.22s ⇒ 重排后的用例**仍然**守护 fail-loud，且失败态更快（13.2s vs 17.4s）证明它抓的正是「降级静默返回」 |
| 5 | **新变异（注入失效守卫是否空转）**：让 `_inject_ws_latency` 只 `Network.enable` 后直接 return（模拟 CDP `emulateNetworkConditions` 退役/静默失效）→ 跑回归 A | **1 failed**：`AssertionError: 从建 tab 到握手完成仅 99ms，远低于注入值 3000ms —— 注入可能未生效，本回归的判别力会归零` ⇒ 守卫**不空转**：失效侧 99ms 对阈值 1500ms 有 15× 余量（生效侧 3095ms 有 2× 余量）——这就是 I2 的「×0.5 取舍成立」的实证 |
| 6 | 恢复变异（`git checkout --` ×2），`git status --porcelain` | 干净（仅本报告文件） |
| 7 | 全文件扫 `design.md` / `diagnosis.md` / `tasks.md` 的「负向半场 / ≥ 注入值 / 前置条件」旧措辞 | 发现 4 处（含 1 处 info）→ R1/R2/R3 + 观察 |
| 8 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | **ERROR: review manifest missing**（exit 1）—— 预期过渡态，见 R4；受保护路径检查**已通过**（错误列表只有 manifest 这一条 ⇒ `docs/known-debt.md` 的改动有 seq 5 事件覆盖） |
| 9 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed**（含 `spec/web-ui`） |
| 10 | 全量 pytest | **未跑**（4 核/7GB、需与他人共享；按审阅指令只跑相关子集） |

### Round 1（head `a3d1ae8`，保留）

| # | 命令 / 操作 | 结果 |
|---|---|---|
| 1 | `uv run pytest tests/web_tests/test_multi_session_browser.py tests/web_tests/test_workflow_graph_browser.py -q` | **47 passed** in 119.40s |
| 2 | 变异（回归 B 判别力）：helper 退回旧实现 → `test_workflow_view_survives_delayed_app_init` | **FAILED**（14.67s）：`AssertionError: init 落定后派发 workflow 事件，#workflow-view 应保持激活 / assert False` |
| 3 | 变异（回归 A 判别力）：fill+click 移到 rekey 屏障之前 | **FAILED**（20.99s）：`wait_for_selector(".tab-pane.active .message.assistant")` 超时 |
| 4 | 插桩实测回归 A 注入余量 | `PROBE handshake_ms=3095`（注入 3000ms），用例 6.00s 通过 |
| 5 | 插桩实测 `init` 完成时刻，3 次采样 | `early=True / False / True` ⇒ 当时 I1 的窗口确实是活的 |
| 6 | 暴露面独立重算 + 删除行全量核对 | 15/6/3 = 24 与 D6 一致；无断言删改 |
| 7 | `check_openspec_artifacts.py` / strict validate | passed（当时报告尚未落盘） / 30 passed |
| 8 | 全量 pytest | **未跑** |

## 结论

Round 1 的唯一 major（I1）**已修且经三重独立验证**（结构单写入点 + 6 次重复稳定触发 + 削弱性变异仍红）；I4/I5/I6/I8 完整修复且事实核对无误；I2/I3 的**实质结论**（负向半场移除、注入守卫取 50%）已在 `design.md` 落为可追溯的决策，且我**用新变异实测证明该取舍的正确性**（失效侧 99ms 判红、生效侧 3095ms 通过）。代码与测试层面**未发现新问题**，无生产行为漂移、无 spec 错位、无安全面问题、无 CI 弱化。

残留 4 条均为 low：3 处纯文档旧措辞（R1/R2/R3，建议归档前一并修，不需改代码/测试），1 条流程提醒（R4：manifest 生成顺序 —— 必须先提交**本 Round 2 报告**再生成 manifest，否则 `report_hash` 对不上且会出现「manifest PASS / 报告 CHANGES_REQUESTED」的矛盾）。

**Verdict：PASS**（Round 1 的 CHANGES_REQUESTED 已被本轮 PASS 取代）。
