# Building Review: fix-issue-310-guard-realpath

## Reviewer
- run id: ae0f52bd-27fc-4542-9395-9aebdefc52aa
- 时间: 2026-10-19
- 审阅基线: base origin/master=`c2d2ba4ceb5a7ffc7e2ea8b15cd314d3c40b0edf`；head=`39a9126d3b19f55c82f863f5357f9044671ffcd4`

## 本轮判定
- 第 1 轮：PASS

### 第 1 轮 · 批次（只列 blocker/high/medium）
- 无

### 第 1 轮 · 下一批（deferred）
- 无

### low/nit 登记
| id | severity | 问题 | 处置理由 |
|---|---|---|---|
| L-1 | low | `_canonical_path()` 未捕获 `ValueError`（路径内嵌 NUL）：`agent/tools/command_guard.py:142,148`。实测 `guard.check("rm -rf <ws>\x00x")` 在 master（`origin/master` 的同文件加载后实测）返回 `DENY/rm_target_escape`，本分支抛 `ValueError: lstat: embedded null character in path`。`BashTool.execute` 对 guard 调用无 try/except（`agent/tools/builtin/bash.py:117`），`AgentLoop._execute_single_tool` 兜底为错误结果且**不执行命令**（`agent/loop.py:1429-1432`）。 | 无 fail-open（命令不会执行），影响仅为错误呈现从 `permission_denied` 退化为普通 error；需构造含控制字符的输入。建议顺手改为 `except (OSError, RuntimeError, ValueError): return None`，一支 1 行硬化，不值得升 medium。**复核（head c92a8db）：已修**（两个 resolve 分支补 `ValueError`，新增 NUL 回归测试）。 |
| L-2 | low | `tasks.md` 1.5 要求用 `tee`、`echo K >> <ws>/.env`、`dd of=<ws>/.env` 三种写法验证白名单同源，新增测试只用了 `tee`（`tests/agent/tools/test_command_guard.py:407-414`），没有 symlink 工作区下的 `>>` / `dd of=` 行。 | reviewer 实测 `echo K >> <link>/.env` 与 `dd of=<link>/.env` 均 ALLOW、`escape` 目标均 DENY，三条调用点共享同一 `_allow_covers()`（`command_guard.py:784`），且 plain workspace 下已有 `>>`/`dd` 白名单用例（同文件 `:1095-1117`）。语义已被覆盖，属任务措辞与测试矩阵的粒度差；建议补两行 param 或修正任务文字，非必须。**复核（head c92a8db）：已修**（三种写形态 × link/real 双向参数化）。 |
| L-3 | low | `tasks.md` 4.3 已标 `[x]`「矩阵记录进 `reviews/building-review.md`」，但提交 `39a9126` 时该文件并不存在（`git status` 干净、`git diff --name-only` 无此文件）；矩阵实际由 reviewer 复核并记录于本报告下文。 | 时序问题（报告由审阅者产出），本报告已补录完整矩阵，无代码/规格影响。**复核（head c92a8db）：已处置**（tasks 4.3 已指向本报告矩阵节）。 |
| L-4 | nit | 模块顶部 docstring（`agent/tools/command_guard.py:16-22`）仍只写「按路径段比较 + 规范化」，未提工作区包含判定已改用 realpath；两个 helper 的 docstring（`:104-150`）是准确的。 | 不影响调用点选择——唯一涉及 workspace 的两个消费点都已接线正确；属文档一致性小债，后续触碰该文件时顺手补。**复核（head c92a8db）：已修**（模块 docstring 已补充 realpath 口径）。 |
| L-5 | nit | 四行正向矩阵的目标 `build` 是**已存在**目录（`tests/agent/tools/test_command_guard.py:329-337`），「目标尚不存在 → 非严格回退」在 `rm` 通道没有直接用例，只在 `tee <ws>/.env`（`.env` 不存在，`:407-414`）间接覆盖同一 helper 分支。 | 同一 helper 分支已被白名单用例覆盖；补一条 `rm -rf <ws>/missing/deep → ALLOW` 能更直观钉住 spec 的「目标尚不存在」条款，非必须。**复核（head c92a8db）：已修**（新增缺失目标 ALLOW 回归）。 |

### 审阅后 low/nit 复核
复核基线：`39a9126..c92a8db`，diff 只含 4 个文件——`agent/tools/command_guard.py`（+ValueError/docstring）、`tests/agent/tools/test_command_guard.py`（新增/参数化）、`tasks.md`（4.3 措辞）、本报告；无 CI/规格/实现语义的额外改动。验证期**未扩大批次**，未发现新的 medium+，deferred 为空。

- **L-1 ✅ 已修**：`_canonical_path()` 两个 resolve 分支均改为 `except (OSError, RuntimeError, ValueError)`（`agent/tools/command_guard.py:149,153`），返回 `None` ⇒ fail-closed。新增 `test_embedded_nul_fails_closed_without_raising`（`tests/agent/tools/test_command_guard.py:465`）。独立诊断：`_canonical_path(<ws>/bad\x00name)` 返回 `None`；`rm -rf <ws>/bad\x00name` 在 workspace=real 与 workspace=link 两种表示下均 `deny/rm_target_escape`，不再抛异常；`tee <ws>/.git/\x00`（带 allowlist）为 `deny/tee_target`，同样无异常。
- **L-2 ✅ 已修**：`test_write_allowlist_uses_same_canonical_semantics` 现为 `tee` / `echo K >>` / `dd of=` × workspace {link, real} × target {link, real} 共 12 行（`:411`）；`test_write_allowlist_cannot_cover_symlink_escape` 按三种写形态参数化并分别断言 `tee_target` / `protected_redirect` / `dd_target`（`:442`）。实跑新类 34 passed，与作者声明一致。
- **L-3 ✅ 已处置**：`tasks.md:46` 的 4.3 已改为「已由审阅者独立复核并记录进 `reviews/building-review.md` 的『符号链接命令级实测矩阵』节」，与本文 `## 符号链接命令级实测矩阵（tasks 4.3）` 对应，措辞与事实一致。
- **L-4 ✅ 已修**：模块顶部 docstring（`agent/tools/command_guard.py:20-24`）已补充 workspace containment 比较 real paths、绝对目标走 `_canonical_path()`（strict-first，loops 时 fail-closed）、protected-path checks stay lexical；与实现及 spec 口径一致。
- **L-5 ✅ 已修**：新增 `test_missing_target_inside_workspace_allowed`（`tests/agent/tools/test_command_guard.py:456`）；独立诊断 `<ws>/not-yet-created/deep` 在 workspace=real 下 ALLOW，经 link 表示 `<link>/missing/deep` 亦 ALLOW，`FileNotFoundError` 非严格回退生效。

实跑记录：
```text
$ uv run python -m pytest -q tests/agent/tools/test_command_guard.py -k TestSymlinkedWorkspaceContainment -p no:cacheprovider
34 passed, 272 deselected

$ uv run python -m pytest -q tests/agent/tools/test_command_guard.py -p no:cacheprovider
306 passed

# 独立诊断（tmp_path 显式符号链接）
_canonical_path(<ws>/bad\x00name)            → None
rm -rf <ws>/bad\x00name（ws=real / link）     → deny/rm_target_escape（无异常）
tee <ws>/.git/\x00（allowlist）              → deny/tee_target（无异常）
rm -rf <ws>/not-yet-created/deep（real/link） → allow
```

## 任务逐项验证

- **0.1** ✅ `reviews/grill-design.md` 存在：`## Confirmed Decisions` 6 条（≥3），每条含同行裸 `来源:`；`## Open Questions`、`## User Confirmation` 均存在。
- **0.2** ✅ 6 条决策覆盖两侧 realpath、相对路径词法、`_allow_covers` 同类修复、fail-closed、链接逃逸收紧、路径段包含；Non-Goals 在 proposal/design 齐备。
- **0.3** ✅ `reviews/grill-adversarial.md` 存在，1 个已收口轮（ADV-01 medium 修复并跨版本复验），deferred=0，出口 PASS。
- **0.4** ✅ 无 Open Question；设计环出口 PASS（同上）。
- **0.5** ✅ `design.md:276-299` 的 `## Pre-Implementation Review` 已回填 grill / 对抗轮结论。
- **1.1** ✅ `TestSymlinkedWorkspaceContainment`（`tests/agent/tools/test_command_guard.py:307`）用 `tmp_path` + `os.symlink` 显式构造；`os.name != "posix"` 与 `os.symlink` 抛 `OSError` 时 `pytest.skip`。
- **1.2** ✅ 四行 ALLOW 矩阵为 `workspace_kind × target_kind` 参数化（`:329-337`），覆盖 link/real 双向组合。
- **1.3** ✅ 前缀碰撞（`<ws>-evil`、`<ws>X`，`:340-353`）、`../etc`（`:367-372`）、根删除 link/real（`:355-365`）均有 DENY 断言并校验 `last_reason`。
- **1.4** ✅ `escape` 无尾斜杠/带尾斜杠（`:374-383`）、`escape/../victim`（`:385-394`）、工作区内 `loop → loop`（`:396-405`）均 DENY；reviewer 另测互相循环 `loopa ↔ loopb` 同样 DENY。
- **1.5** ✅ `tee` 四行矩阵、前缀碰撞、逃逸目标、`.env → config/dev.env` 双向匹配都有；`>>` 与 `dd of=` 的 symlink 行已在 `c92a8db` 补齐（见下节 L-2 复核）。
- **1.6** ✅ 无提交态的红/绿记录，但 reviewer 以变异法复现：把 `_canonical_path` 退回 `os.path.normpath` 后新类 9 failed / 13 passed（正向行与逃逸/循环/白名单负例全红），恢复后全绿——「可红→绿」成立。
- **1.7** ✅ 同上变异验证（9 红即变异应红项；恢复后 294 passed）。
- **2.1** ✅ `_canonical_path()`（`command_guard.py:119-150`）实现与设计与 tasks 逐字一致：POSIX 绝对路径**直接** strict-first `Path.resolve()`（无 normpath 前置）；`FileNotFoundError` 回退非严格；其余 `OSError`/`RuntimeError` → `None`；相对路径 `os.path.normpath`。
- **2.2** ✅ `_check_rm()`（`:1175-1211`）拆分 `lexical`（`:1190`，`_DENY_PATHS`/`/`/`$HOME`/`~`）与 `canonical`（`:1197`，工作区包含/根删除）；`canonical is None` 在任何字符串操作前显式 DENY（`:1198-1200`）。
- **2.3** ✅ `_allow_covers()`（`:770-797`）改走 `_canonical_path`（`:784`），`None ⇒ False`（`:785-786`），直接使用构造时已 realpath 的 `self._workspace`（`:744`、`:787`）。
- **2.4** ✅ 无 `sys.platform`/`os.name` 分支；`_check_target`/`_check_mv_cp`/`_check_dd`/`_check_tee`/chmod/redirect 仍用 `_normalize_path`（grep 核对全部调用点）；Windows 盘符路径仍走非 `/` 分支；`_normalize_path` docstring 已同步（`:104-116`）。
- **2.5** ✅ 定向 `test_command_guard.py` 294 passed；三态/攻击集/ask 集/bash_tool_ask 共 307 passed。
- **3.1** ✅ delta spec 仅 `## MODIFIED Requirements` 一条完整 Requirement + 4 个新 Scenario（`specs/workspace-safety/spec.md:70-93`）。
- **3.2** ✅ current spec 的该 Requirement 块与 delta **逐字一致**（diff 仅尾部空行）；Requirement 计数 19→19（修订前后均 19）；`current_spec_synced` 事件存在（`workflow-events.jsonl` seq 3）；strict validate 29/29。
- **3.3** ✅ backlog 第二十一批登记本 change 并链接 issue #310；`backlog_updated` 事件存在（seq 2）。
- **3.4** ✅ 关键词扫描 `docs/`、`README*`、`AGENTS.md`、`CONTEXT.md`：除 ADR/backlog 外仅 `docs/interview-bullets/walkthrough.md` 命中一个既有 benchmark 任务名（`asterwynd-005-bash-workspace`），无陈旧口径需要同步。
- **3.5** ✅ `docs/adr/ADR-0008-guard-workspace-realpath-containment.md` 存在：Decision 5 条 + 4 个备选（含双表示、normpath-first、仅非严格 resolve）及拒绝理由，并含 Revisit Conditions。
- **4.1** ✅ reviewer 实测 294 passed（272 基线 + 新类 22 条），与 tasks 的 272 基线口径吻合。
- **4.2** ✅ 作者记录 2 failed / 4383 passed / 9 skipped（2 条既有 `/tmp` 环境失败）；reviewer 按指示未重跑全量，定向套件无回归，未发现矛盾证据。
- **4.3** ✅ 矩阵由 reviewer 独立复核并记录于下文「符号链接命令级实测矩阵」；`tasks.md` 4.3 已在 `c92a8db` 指向该节（见下节 L-3 复核）。
- **4.4** ✅ reviewer 重跑 `openspec validate --all --strict`：29 passed / 0 failed。
- **4.5** ✅ reviewer 重跑瘦 checker `--base-ref origin/master --require-base`：EXIT=0（`Project rule checks passed`）。
- **4.6** ✅ 作者记录 benchmark smoke EXIT=0；本 change 未改工具策略接线，reviewer 未重跑。
- **5.1** ✅ 本报告即本轮独立审阅产出（run id 见上）。
- **5.2** ✅ 本批 medium+ 为 0，无修复项；low/nit 已登记并写理由。
- **6.1 / 6.2** ⏸ 正确保持未勾并标 `(post-merge)`。

## 验证命令实跑记录

```text
$ uv run python -m pytest -q tests/agent/tools/test_command_guard.py -p no:cacheprovider
294 passed in 2.06s

$ uv run python -m pytest -q tests/agent/tools/test_guard_three_state.py \
    tests/benchmark/test_attack_suite.py tests/benchmark/test_ask_suite.py \
    tests/agent/tools/test_bash_tool_ask.py -p no:cacheprovider
307 passed in 2.03s

# 变异验证（内存中把 _canonical_path 退回 os.path.normpath，未改仓库文件）
TestSymlinkedWorkspaceContainment: 9 failed, 13 passed   → 恢复后全绿

$ uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
Project rule checks passed   (EXIT=0)

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed (29 items)

# 差分扫描（origin/master 的 CommandGuard vs HEAD，41 条 rm 命令）
OLD=allow → NEW=deny 的差异仅 3 条，且均为预期的符号链接收紧：
  <ws>/etc-link/passwd（工作区外链接）、<ws>/dangling（悬空链接指向外部）、<ws>/outlink/x
无任何 DENY→ALLOW 差异（workspace 为 real 的对照矩阵）。

# 对抗探针（tmp_path 显式符号链接）
前缀碰撞 link-evil / real-evil / link-wsX   → deny/rm_target_escape
rm -rf <link>、<link>/、<real>              → deny/rm_target_escape
<link>/../etc、escape、escape/、escape/../victim → deny/rm_target_escape
inside-link（指向工作区内）                 → allow
loop / 互相循环 loopa↔loopb                 → deny/rm_target_escape
/etc/passwd、$IFS/etc、~、$HOME             → deny/rm_target_escape
相对路径 build / ../../etc                  → allow（既有相对路径语义不变）
```

## 符号链接命令级实测矩阵（tasks 4.3）

workspace ∈ {`link-ws → real-ws`, `real-ws`} × 命令目标 ∈ {link 表示, real 表示}：

| workspace | 命令 | 判定 |
|---|---|---|
| link | `rm -rf <link>/build` | ALLOW |
| link | `rm -rf <real>/build` | ALLOW |
| real | `rm -rf <link>/build` | ALLOW |
| real | `rm -rf <real>/build` | ALLOW |
| link | `rm -rf <link>-evil` / `<real>-evil` / `<link>X` | DENY（`rm_target_escape`） |
| link | `rm -rf <link>` / `<link>/` / `<real>` | DENY（`rm_target_escape`） |
| link | `rm -rf <link>/../etc` | DENY（`rm_target_escape`） |
| link | `rm -rf <real>/escape`（`escape → outside`） | DENY（保守过度判定） |
| link | `rm -rf <real>/escape/` | DENY |
| link | `rm -rf <real>/escape/../victim` | DENY（先跟随链接再折叠 `..`） |
| link | `rm -rf <real>/loop/x`（工作区内 `loop → loop`） | DENY（`None` fail-closed 分支） |
| link | `tee / echo K >> / dd of= <link>/.env`（allowlist `.env`） | ALLOW |
| link | `echo K >> <real>/escape/.env`（allowlist `escape/.env`） | DENY（`protected_redirect`） |
| link | `dd of=<real>/escape/.env`（allowlist `escape/.env`） | DENY（`dd_target`） |

结论：修复达到 issue #310 验收 1–4；未发现真实越界放行；`_DENY_PATHS` 仍为词法判定（`command_guard.py:1190-1195`），`_check_rm` 的 canonical 结果只用于工作区包含/根删除。

## 收口确认
- 本批 medium+ 数量：0（low/nit 5 条已登记，其中 L-2/L-3 为任务/文档粒度差，L-1 为 fail-closed 方向的一行健壮性建议）。deferred 为空，第 1 轮收敛。
- low/nit 复核（head `c92a8db`）：L-1～L-5 全部已修/已处置（见「审阅后 low/nit 复核」），low/nit 复核无新增 medium+，deferred 为空。

## 闭环出口
PASS
