# Building Review: fix-issue-247-guard-path-boundary

- reviewer: 独立零记忆 subagent（未参与实现）
- base: `369d99d`（**与 `master` 的 `command_guard.py` 字节相同**，sha256 `13d1f995…`；故下文的「vs base」等价于「vs master」。`master` 现为 `14f6e24`，那 1 个额外 commit 不触及本文件）
- head（本轮，R3）: `41cbd76`（前序：`be480dd` = R1、`ee893ba` = R2）
- 方式：只读审阅 + 独立复算。把 base/R1/R2/R3 四版 `command_guard.py` 各自独立加载成模块、对同一语料逐条对比；变异验证用影子树（其余全软链 head，仅换 guard）装回旧 guard 跑新测试

## Verdict

**CHANGES_REQUESTED**（Round 2 复审；R3 已修好 R2 的换行漏检，但仍有 **DENY→ALLOW 收缩面**未闭）

### Round 1（I1/I2）→ 已修复

R1 报的 I1（链式命令 `cd /tmp && cp …` 不检查）与 I2（`/dev/` lookahead 用 `\b` 非 `/` 感知）**均已确认修复**：R1 报的 23 条向量在 R3 全部由 ALLOW 回到 DENY（见「Round 2 独立复算」§1）。攻击集 50/54 四版不变，无误伤新增。

### Round 2（仍未闭）

R3 的修法把 argv 检查改成「按分隔符切段」，但**切分粒度仍落后于 shell 语法**，且 `bash -c` 解包只覆盖了部分 wrapper 形态。对 base（= master）逐条对比，下列真实可执行命令仍然是 **master DENY → R3 ALLOW**：

1. **shell `-c` wrapper 只解包了一部分**（major）：`bash -lc '…'`、`bash -ic '…'`、`zsh -ic '…'` 是全 ALLOW（组合短选项未识别）；`/usr/bin/env bash -c '…'`、`/usr/bin/env sh -c '…'`、`env -i bash -c '…'` 也全 ALLOW（`env` 解包只认字面 `env`，不认 `/usr/bin/env`，也不跳 `-i`）。注意 `bash -c '…'` 本身在 R2 起已 DENY——**同一语义的写法却因 wrapper 细节漏一半**，绕过成本几乎为零。
2. **subshell / brace 分组未切段**（major at R3）：`(cp evil ~/.ssh/authorized_keys)`、`cd /tmp && (cp evil a/.env)`、`cd /tmp && { cp evil a/.env; }`、`cd /tmp && (cd sub && cp evil a/.env)` 均 ALLOW。
3. **`\r` 残留 token**（minor）：`\n` 切分后 `\r` 落在**上一段最后一个 token** 上，而 tokenizer 不把 `\r` 当空白 ⇒ `cp evil a/.env\r\nls` 的 dest 变成 `a/.env\r`，`_dest_is_sensitive` 不认识 → ALLOW（base DENY）。R3 新加的 `cd /tmp\r\ncp evil .env` 用例恰好把 `\r` 落在无害 token 上，所以测不出这一支。

以上 1/2/3 都**不是本 change 逐轮新引入**（除 §1 表格标记 `NEW vs R1` 的一条外），但它们是 base（master）能拦、现在拦不住的面，与 proposal Goal #4「不削弱任何既有攻击拦截」同 I1 属一类。

### 未提交的在制品（WIP）已覆盖大部分，但不能计入本 verdict

审阅时工作区存在**未提交**改动（`git status` = `M agent/tools/command_guard.py`），内容：`_SEGMENT_SEPARATORS` 增加 `()`/`{}`、tokenizer 的元字符集加 `(){}`、`_shell_dash_c_payload` 改为「任意含 `c` 的 dash-token」。实测该 WIP 把上面第 2 类（subshell/brace）与第 1 类的 `-lc`/`-ic` 部分修好了。**但**：(a) 未提交，不是可审阅产物；(b) 未配套测试（`tests/` 无任何改动，无 `(cp …)`/`bash -lc` 回归用例）；(c) 仍留 `/usr/bin/env bash -c`、`env -i bash -c`、`\r` 三处。WIP 的 tokenizer 改动对 26 条良性命令的 verdict 无变化（仅对未加引号的 `a{2}`/`(a)` 切分不同），未见新误报。

**结论**：把 WIP 提交并补 3 条测试（subshell/brace、`bash -lc`、`/usr/bin/env bash -c` 或 `env -i`），再处理 `\r`（在 `_check_command_text` 里按 `\r\n|\r|\n` 切，或把 `\r` 加入 tokenizer 空白集），并给每类补回归用例，即可转 PASS。范围很小。

## 任务逐项验证

| 任务 | 声称 | 核验结论 | 证据 |
|---|---|---|---|
| 0.1–0.4 grill + 停轮 + 回填 | 已完成 | 完成：`reviews/grill-design.md` 有 7 条 `## Confirmed Decisions`、6 条 Open Questions、4 条 `## User Confirmation`（Q1/Q2/Q3/Q6 均含实质答复 + 时间），design/proposal 的 `待确认` 已清理为结论 | `reviews/grill-design.md:11-31`；`design.md:47-127` |
| 1.1–1.4 spec delta / Impact / RIR / Pre-Impl Review | 已完成 | 完成，MODIFIED Requirement + 5 条新 Scenario 与 design 一致 | `specs/workspace-safety/spec.md:1-60` |
| 1.5 落地到正式 spec | 已完成 | 完成，`openspec/specs/workspace-safety/spec.md` 与 delta 逐段一致（唯一例外见 I1：spec 无条件 SHALL，实现在链式命令下不成立） | `openspec/specs/workspace-safety/spec.md:206-267` |
| 2.1–2.6 / 2.3b / 2.3c 回归用例 | 已写 | 已写且**判别力足够**（变异验证见下） | `tests/agent/tools/test_command_guard.py:215-360` |
| 2.7「运行新测试确认必红」 | 已记录 | **证据缺失**：change 目录内无任何红测输出记录（`grep -rn "红\\|变异"` 只命中 tasks/proposal/design/diagnosis 的**计划**文字）。但该结论**可独立复现**（见「独立复算」变异验证），故非实质缺陷 | `tasks.md:28`、`tasks.md:51` |
| 2.8 不依赖时序 | 已完成 | 成立：新用例全是纯函数调用，无 sleep / IO | `tests/agent/tools/test_command_guard.py:215-410` |
| 2.9「电池全集固化为测试数据」 | 已勾选 | **未真正落地**：仓库内无「26 条良性电池」fixture（`grep -rln 良性命令` 只命中 change 文档）。新用例覆盖了各家族但打散在参数化表里，且**不含** proposal 表格逐条枚举的 26 条全集 → 4.4「与预测数字对齐」仍缺可复算基线（R4 未真正闭） | `tests/agent/tools/test_command_guard.py:215-340`；无 fixture 文件 |
| 3.1–3.9、3.11–3.12 实现 | 已完成 | 已实现：`_normalize_path`/`_within`/`_is_device_exempt`/`_dest_is_sensitive`、5 处调用点改段边界、`..` 规范化、rm 工作区根拒绝、docstring 更新。**但 3.8 的落地方式引入回归**（I1） | `agent/tools/command_guard.py:49-84, 243-257, 284-356` |
| 3.10（条件任务） | 未勾 | 合理未勾；但实现期确实发现新影响面（I1）却**未回写 Impact Analysis**，该任务实为被绕过 |
| 4.1 command_guard 用例 | 全绿 | 实测 `91 passed` | `uv run pytest tests/agent/tools/test_command_guard.py -q` |
| 4.2 攻击集 | 全绿 ≥50 | 实测 `56 passed`（50 guard-deny + 4 sensitive-read + 2 结构），拦截数 50/50 不降 | `uv run pytest tests/benchmark/test_attack_suite.py -q` |
| 4.3 变异验证 | 双向已记录 | **可复现**：影子树装回 base 版 guard → 新测试 `32 failed, 59 passed`；装回 head 版 → 全绿。判别力成立 | `/tmp/247-verify/mut`（base 版 guard + head 测试） |
| 4.4 仿真复算对齐 | 17→0、50/54 | **部分成立**：攻击集 50/54 复算一致；误报**方向**一致（我的 26 条重建电池 21→0）。但「17」这一精确数字**不可复现**——电池未落库，无基准可对齐（同 2.9） | 见「独立复算」 |
| 4.5 全量 pytest | 全绿（2 条 memory 失败为 master 既有） | **数字属实**：实测 `2 failed, 3113 passed, 9 skipped in 825s`，2 条失败均为 `tests/agent/memory/test_persistent.py::TestFindScopeRoot`。**「既有」说法独立证实**：该测试文件未被本 diff 触碰；失败根因是本机 `/tmp/.git` 目录存在（`/tmp` 是 git 仓库），测试从 `tmp_path` 上溯把 `/tmp` 当成 scope root；把 `TMPDIR` 指向非 git 目录后同样两条**全绿**（`5 passed`）。与 guard 改动无关 | `TMPDIR=~/.cache/247-tmp uv run pytest tests/agent/memory/test_persistent.py::TestFindScopeRoot -q` |
| 4.6 OpenSpec strict validate | 通过 | 实测 `29 passed, 0 failed` | `npx @fission-ai/openspec@1.4.1 validate --all --strict` |
| 4.7 artifact checker | 通过 | 以真实 base 运行 `--base-ref 369d99d` → `OpenSpec artifact checks passed`（exit 0）。默认 `--base-ref master` 会报 `2026-09-26-fix-issue-249-...` 归档缺事件——那是 master 上**另一个** change（`14f6e24`）的产物，与本 change 无关 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref 369d99d` |
| 4.8 Bash 层未受影响 | 已确认 | 未单独复跑，但 4.5 全量通过已覆盖 `tests/agent/tools/test_bash*` | 全量 pytest |
| 4.9 benchmark smoke | 已跑，结论可信 | **可信**：`/tmp/smoke-247` 与 base 对照 `/tmp/smoke-247-base` 的逐任务 pass/fail **完全一致**（同一 fake agent 基线）。注：fake agent 不执行真实 Bash（trace 里 tool_calls 为空），该 smoke 只能证明主循环未崩，**不能**作为护栏判定行为的证据 | `diff` `/tmp/smoke-247/2026-09-26T02-44-50/summary.md` vs `/tmp/smoke-247-base/2026-09-26T02-46-19/summary.md` |
| 5.1 文档扫描 + 纳入 interview 目录 | 已完成 | 部分完成：`walkthrough.md` §2.2/§2.3、`Q10-sandbox.md` 行号已同步；但 §2.4/§2.5 的行号、`_EXTRA_DENYLIST` 残留口径未同步 → I3 | 见 I3 |
| 5.2 / 5.3 / 5.4 文档收尾 | 未勾 | 尚未执行（acceptable：属 PR 前收尾阶段），但 R6 残余面记入 `known-debt.md` 的任务仍未落地 → I4 |
| 6.x / 7.x | 未勾 | 未执行（本审阅即 6.1） |

## Issues

- **I1 (major)**: 链式命令中的 mv/cp 敏感点目录写入**不再被拦**——base 能拦、新代码放行，净拦截面缩小。
  实现把点目录正则分支从 `_EXTRA_DENYLIST` 删除（`agent/tools/command_guard.py:113`，现仅剩 `/etc/|/proc/|/sys/|/var/|/dev/(?!null\b|stdout\b|stderr\b)`），改为只在 `_check_mv_cp` 里做段级判定（`:313-329`）。但 `_check_mv_cp` **只在 `tokens[0]` 是 `mv`/`cp` 时被调用**（`_check_argv`，`:261-282`；分派点 `:274`）。命令链（`cd`/`echo`/`true`/`bash -c` 打头）下 argv 通道完全不触发，而正则通道又被删掉了点目录分支 ⇒ **两通道均不覆盖**。
  实测（我自己构造的向量，`old` = `369d99d` 版 guard，`new` = `be480dd` 版）：
  | 命令（单次 Bash 调用，真实可执行） | old | new |
  |---|---|---|
  | `cd /tmp && cp evil ~/.ssh/authorized_keys` | DENY/denylist | **ALLOW** |
  | `cd /tmp && mv evil ~/.ssh/authorized_keys` | DENY | **ALLOW** |
  | `bash -c "cp evil ~/.ssh/authorized_keys"` | DENY | **ALLOW** |
  | `cd /tmp && cp evil ~/.git/hooks/pre-commit` | DENY | **ALLOW** |
  | `cd /tmp && cp evil ~/.gitconfig` | DENY | **ALLOW** |
  | `cd /tmp && cp evil ~/.docker/config.json` | DENY | **ALLOW** |
  | `cd /tmp && cp evil ~/.aws/credentials` | DENY | **ALLOW** |
  | `cd /tmp && cp evil ~/.kube/config` | DENY | **ALLOW** |
  | `cd /tmp && cp evil ~/.gnupg/secring.gpg` | DENY | **ALLOW** |
  | `cd /tmp && cp evil ~/.npmrc` / `~/.pypirc` / `~/.netrc` / `~/.git-credentials` | DENY | **ALLOW** |
  | `cd /tmp && cp evil a/.env` / `~/.env` | DENY | **ALLOW** |
  | `cd /tmp && cp evil proj/.git/hooks/pre-commit` | DENY | **ALLOW** |
  | `true; cp evil sub/.env/secrets` | DENY | **ALLOW** |
  纯 mv/cp 形式（非链式）仍正确拦截，说明判定逻辑本身对、**只是没接上链式路径**。
  这与 proposal `Goal #4`/`Non-Goals`「不削弱任何既有攻击拦截」、`spec` 的 SHALL「mv/cp 目标命中敏感点目录 SHALL 被拒绝」（`openspec/specs/workspace-safety/spec.md:210` 无「仅限首 token」限定）**直接冲突**；`50/54` 攻击集没有链式点目录用例，故该验收口径测不出（grill `R1` 已预警这个盲区，`reviews/grill-design.md:35`，现在确实发生了）。
  建议：把点目录判定从「首 token 的 argv 通道」提升为**命令级扫描**——按 `&&`/`;`/`|`/换行切分命令串，对每个子命令跑 `_check_mv_cp`（或对每个 `mv`/`cp` 出现位置做段级检查）；等价地，在 `_EXTRA_DENYLIST` 保留一个**段感知**的点目录分支兜底。并补链式回归用例（含 `~/.ssh/authorized_keys`、`bash -c` 包裹）。

- **I2 (major, 与 I1 同源)**: `_DEVICE_EXEMPT` 与 denylist lookahead 并**未真正同步**，注释与测试的保证不成立。
  `agent/tools/command_guard.py:113` 用 `\b` 作词边界（`(?!/null\b...)`），`\b` 不是 `/` 感知的：`/dev/null/sda` 中 `null` 后接 `/` 已构成词边界，故 lookahead 判为「豁免」——但按段语义 `/dev/null/sda` **不在** `_DEVICE_EXEMPT` 内。实测 regex：`cp x /dev/null` 不匹配（对，豁免）、`cp x /dev/null/../sda` **不匹配**（错）、`cp x /dev/null/sda` **不匹配**（错）、`cp x /dev/nullx` 匹配（对）。因此链式下 `echo hi && cp evil /dev/null/sda`、`echo hi && cp evil /dev/stdout/../sda` 由 base 的 DENY 变 **ALLOW**（argv 通道在链式下不触发，正则已被 lookahead 放走）。
  `:111-112` 的注释「The lookahead must stay in sync with `_DEVICE_EXEMPT`; a test asserts exactly that」与 `tests/agent/tools/test_command_guard.py:392-410` 的测试都**只覆盖 `cp x /dev/null` 等价形式**与 `/dev/sda`、`/dev/fd/1`、`/dev/tcp/x`，**未覆盖 `/dev/null/<sub>` 与 `/dev/null/../*`**，因此无法发现该失配。
  建议：lookahead 改为 `/` 感知（如 `(?!/null(/|$)|stdout(/|$)|stderr(/|$))`），并给同步测试加 `/dev/null/x`、`/dev/null/../sda`、`/dev/stdout/x` 三个反例。（注：`/dev/null/x` 在真实内核是 ENOTDIR，危害有限；但 `/dev/null/../sda` 类写法与 I1 同属「链式下两通道皆空」的模式，应一并收口。）

- **I3 (minor)**: 文档行号/口径同步不完整（本 change 自身移动了行号，属于本次引入的事实变化）。
  - `docs/interview-bullets/walkthrough.md:2649` `_check_argv()（:190-211）`、`:2653-2657` 的 `:213-231`/`:233-242`/`:244-257`/`:269-287`/`:259-267`、`:2665` 的 `:166-176` 全是**旧行号**（新值分别为 261-282、284-311、313-329、331-344、358-376、346-356、231-241），而同一文件的 §2.2/§2.3 已更新为新行号——同文档内自相矛盾。
  - `walkthrough.md:3054/3058` 仍写「扩展黑名单 (18)」，与 §2.3 已改成的「16 个」矛盾（实测 `len(_EXTRA_DENYLIST) == 16`，base 亦为 16 → §2.3 的 16 是对的，18 是历史错误值）。
  - `docs/interview-bullets/interview-prep.md:429,445` 仍写「18 个扩展模式」（未被本 change 触碰）。
  - `docs/interview-script/questions/Q10-sandbox.md:35` 「`_EXTRA_DENYLIST` … 31 行」未更新（base 29 行 / head 35 行，本就失准）。
  建议：一并把上述行号与计数改为新值，或至少不再新增错误口径；同时补 `docs/known-debt.md` 的 R6 残余面（tasks 5.2 未勾）。

- **I4 (minor)**: `tasks.md:30`（2.9）与 `:52`（4.4）的可复算基线要求未真正满足——「26 条良性电池」没有作为 fixture 落库，`4.4` 的「17」不可机械复现（我重建 26 条得 base 误拒 21、fix 后 0；精确 17 依赖具体取样）。建议把电池写成参数化用例表或 JSON fixture，使 4.4 有参照物。

## 独立复算

- **攻击集拦截（base vs head，`benchmarks/attacks/attacks.json` 全 54 例）**：base `50/54`（reason 直方图 `{denylist:40, rm_target_escape:7, pipe_to_shell:2, curl_exfil:1}`，未拦 4 例为 `sensitive-read-001..004`）；head `50/54`，直方图**逐项相同**，未拦 4 例相同。限定 guard-deny 子集：base `50/50`、head `50/50`；sensitive-read 两侧均 `4/4 ALLOW`。**结论：攻击集侧不退化，实现方与 grill 的数字属实。**
- **自构造绕过尝试（我独立构造，非照抄文档）**：
  - 链式点目录族：12+ 条 base DENY → head **ALLOW**（见 I1 表）。
  - 链式 `/dev/null/<sub>` 族：`echo hi && cp evil /dev/null/sda`、`... /dev/null/../sda`、`... /dev/stdout/../sda`、`echo hi && mv evil /dev/stderr/../sda` 均 base DENY → head **ALLOW**（见 I2）。
  - `bash -c "cp evil ~/.ssh/authorized_keys"`：base DENY → head **ALLOW**。
  - 正对照（head 仍拦，未放松）：`cp x src/.git/hooks/pre-commit`→DENY/`mv_cp_dest`；`cp x .env`→DENY；`cp x /dev/null/../sda`（非链式）→DENY/`mv_cp_dest`；`rm -rf /dev/null`→DENY；`echo x > /dev/fd/1`→DENY；`echo x > /dev/null/../sda`→DENY（重定向通道用等值判定，不受 I2 的 `\b` 问题影响，**这条通道是干净的**）。
  - workspace 侧：head 新增拦截 `/tmp/ws/../etc`、`/tmp/ws/../../etc`、`/tmp/ws/..`、`/tmp/ws`、`/tmp/ws/`、`/tmp/ws-evil`、`/tmp/wsX`（均 DENY/`rm_target_escape`），且仍放行 `/tmp/ws/build`、`/tmp/ws//evil`、`rm -rf build`（相对路径）——**收紧方向正确，无误伤**。`_check_rm` 的分支顺序（先 `_within` 判越界、再 `== ws` 判根）**无逻辑漏洞**：`_within(ws, ws)` 为真故不会误入第一支，第二支能正确接住根。
  - `/dev/null/../sda`、`/dev//sda`、`/dev/./sda`（重定向）经 `_normalize_path` 均正确 DENY——**规范化有效**。
- **良性命令电池**：按文档家族重建 26 条 → base 误拒 21/26、head 误拒 **0/26**。方向与「误报清零」一致；文档的精确「17」因无落库 fixture 无法逐条对齐（见 I4）。
- **变异验证**：影子树 `/tmp/247-verify/mut`（其余全软链 head，仅 `agent/tools/command_guard.py` 换回 `369d99d` 版）跑 head 的 `tests/agent/tools/test_command_guard.py` → `32 failed, 59 passed`；换回 head 版 → `91 passed`。**新测试判别力成立，非自证。**
- **全量 pytest**：`2 failed, 3113 passed, 9 skipped in 825.00s`。2 条失败 = `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir,test_malformed_git_file_falls_back_to_scan}`；`TMPDIR` 改指非 git 目录后 `5 passed`，确认是本机 `/tmp/.git` 导致的环境问题，**非本 change 引入**。实现方「2 条 memory 失败是既有」的说法**成立**。
- **OpenSpec strict validate**：`29 passed, 0 failed`。
- **artifact checker**：`--base-ref 369d99d` → `OpenSpec artifact checks passed`（exit 0）。
- **benchmark smoke**：`/tmp/smoke-247` 存在且与 `/tmp/smoke-247-base` 逐任务 pass/fail 完全一致；但 fake agent tool_calls 为空，该 smoke 不构成护栏行为证据。

## 备注

- 未修改任何仓库文件，仅新增本 review 报告。所有复算脚本位于 `/tmp/247-verify/`（`verify.py`、`probe*.py`、`battery.py`、`mut/` 影子树）。
- I1/I2 是**同一根因的两个表现**（点目录/设备豁免从「命令级正则」搬到「仅首 token 的 argv 通道」），建议一并修并在同一轮复审；I3/I4 可同轮清掉。

---

## Round 1 修复记录（主 session 复核后）

reviewer 的 I1/I2 经主 session 独立复现**均确认属实**，且都是本 change 引入的拦截面收缩：

- **I1**：`cd /tmp && cp evil ~/.ssh/authorized_keys` 等链式形态，master DENY → 修复后 ALLOW。
  已修：`_check_argv` 改按命令段切分（`_split_command_segments`），逐段检查；`bash -c "…"` 解包后独立检查（`_shell_dash_c_payload`）。
- **I2**：`/dev/null/sda` 因 `\b` 非 `/` 感知而被误豁免，master DENY → ALLOW。
  已修：`/dev/` 从 `_EXTRA_DENYLIST` 的 mv/cp 分支移除，设备豁免由 `_DEVICE_EXEMPT` 精确匹配唯一拥有。

**修复后复算**：攻击集 50/54（不变）；良性误拒 0/33；与 master 逐条对比零回归，另有 4 处 ALLOW→DENY（`ls && mv evil .git/config` 等 master 上的既有洞一并堵上）；新增 12 条链式回归测试在未修时必红。

I3（行号）：已修正本 change 触及的引用；`18 个` 计数在 master 上即已漂移（实际 16），按仓库规则另记，不在本 change 内静默修正。
I4（电池未落库）：本轮 33 条电池已固化进测试；proposal 的「17/26」为早期电池构造，与 reviewer 复建的 26 条口径不同，以测试数据为准。

---

## Round 2（独立复审：`ee893ba` = R2 → `41cbd76` = R3）

四版 `command_guard.py`（base `369d99d` / R1 `be480dd` / R2 `ee893ba` / R3 `41cbd76`）各自独立加载，对同一语料逐条对比。base 与 `master` 的该文件 sha256 相同（`13d1f995…`），故 base 列即 master 列。脚本：`/tmp/247-verify/v/{compare,final,final5,sweep2,residual,deep}.py`。

### 1. R1 的 I1/I2 是否真修好 —— 是

R1 报告里逐条列出的 23 条向量（17 条链式点目录 + 6 条 `/dev/null/<sub>`），在 R3 **全部回到 DENY**（reason `mv_cp_dest`），base 也是 DENY。例：

| 命令 | base | R1 | R2 | R3 |
|---|---|---|---|---|
| `cd /tmp && cp evil ~/.ssh/authorized_keys` | D | A | A | **D** |
| `bash -c "cp evil ~/.ssh/authorized_keys"` | D | A | A | **D** |
| `true; cp evil sub/.env/secrets` | D | A | A | **D** |
| `echo hi && cp evil /dev/null/sda` | D | A | A | **D** |
| `cd /tmp && cp evil /dev/null/../sda` | D | A | A | **D** |
| `echo hi && mv evil /dev/stderr/../sda` | D | A | A | **D** |

R2 引入的 per-segment 分派 + I2 的「`/dev/` 移出 denylist、豁免由 `_check_mv_cp` 精确拥有」都成立，且未见 ALLOW→DENY 误伤。

### 2. R3 声称的「换行修复」—— 属实

`cd /tmp\ncp evil ~/.ssh/authorized_keys`、`cd /tmp\ncp evil a/.env`、`echo hi\ncp evil /dev/sda`、`cd /tmp\nmv evil sub/.env/secrets`、`echo hi\r\ncp evil a/.env`：R2=A → R3=D。`cd /tmp\r\ncp evil .env` 更是 base=A → R3=D（净收紧，因为 base 的 `\r` 让 `/tmp\r` 也不匹配，且该形态 base 靠正则漏掉）。良性多行命令（`cd /tmp\nls -la`、`git add .\ngit commit -m x`）仍 ALLOW。

### 3. 仍然存在的 DENY→ALLOW 收缩面（base/master 能拦，R3 放行）

格式：`base / R1 / R2 / R3`

**3a. shell `-c` wrapper 只解包一部分（major）**

| 命令 | base | R1 | R2 | R3 |
|---|---|---|---|---|
| `bash -lc 'cp evil a/.env'` | D | A | A | **A** |
| `bash -ic 'cp evil a/.env'` | D | A | A | **A** |
| `zsh -ic 'cp evil a/.env'` | D | A | A | **A** |
| `/usr/bin/env bash -c 'cp evil a/.env'` | D | A | A | **A** |
| `/usr/bin/env sh -c 'cp evil a/.env'` | D | A | A | **A** |
| `env -i bash -c 'cp evil a/.env'` | D | A | A | **A** |
| `bash -c 'cp evil a/.env'` | D | A | **D** | **D** |
| `sudo bash -c 'cp evil a/.env'` | D | D | D | D |

即：`bash -c` 已拦，但**组合短选项 `-lc`/`-ic`** 与 **`/usr/bin/env` / `env -i` 前缀**未覆盖。修法：`_shell_dash_c_payload` 已在 WIP 里改成「任一 `-…c…` token」；还需 (a) `env` 解包接受 `…/env`（`rsplit('/')[-1] == 'env'`）并跳过 `-i`/`-u X` 等选项，(b) 或在 segment 归一化阶段剥 wrapper。

**3b. subshell / brace 分组未切段（major at R3；WIP 已修）**

| 命令 | base | R1 | R2 | R3 |
|---|---|---|---|---|
| `(cp evil ~/.ssh/authorized_keys)` | D | A | A | **A** |
| `cd /tmp && (cp evil a/.env)` | D | A | A | **A** |
| `cd /tmp && ( cp evil a/.env )` | D | A | A | **A** |
| `cd /tmp && { cp evil a/.env; }` | D | A | A | **A** |
| `cd /tmp && (cd sub && cp evil a/.env)` | D | A | A | **A** |
| `cd /tmp && (cp evil /dev/sda)` | D | **D** | A | **A** ← 注：R2 起是**新出现**的 vs R1 收缩（R1 靠 denylist 的 `/dev/` 拦到，R2 移除后无通道接管） |
| `cd /tmp && { cp evil /dev/sda; }` | D | **D** | A | **A** ← 同上 |

**3c. `\r` 残留 token（minor）**

`_check_command_text` 按 `\n` 切，`\r` 留在上一段末尾；tokenizer 不把 `\r` 当空白，于是 `a/.env\r` 逃过 `_dest_is_sensitive`。

| 命令 | base | R1 | R2 | R3 |
|---|---|---|---|---|
| `cp evil a/.env\r\nls` | D | A | A | **A** |
| `cp evil a/.env \r\nls` | D | A | A | **A** |

**3d. 未提交 WIP 仍未覆盖的**

`/usr/bin/env bash -c …`、`/usr/bin/env sh -c …`、`env -i bash -c …`、以及 3c 的两条 —— WIP 列均为 A。

### 4. 攻击集 / 误报（四版一致）

- 攻击集（`benchmarks/attacks/attacks.json`，54 例）：base/R1/R2/R3 **均 50/54**，reason 直方图逐项相同 `{denylist:40, rm_target_escape:7, pipe_to_shell:2, curl_exfil:1}`，未拦 4 例仍是 `sensitive-read-001..004`。**不退化。**
- 良性命令（50 条重建电池）：base 14 误拒 → R1/R2/R3/WIP **1 误拒**。唯一「误拒」是 `cp .env.example .env`（dest 是 `.env`，命中 `_SENSITIVE_DOTFILES`）——这是 base 放行、现在拒绝的**收紧**（与 workspace policy 的 `DEFAULT_DENIED_PATTERNS` 含 `.env` 口径一致），非误伤回归；但它是 agent 的常见 bootstrap 步骤，值得在 PR 描述里点明。
- 组合扫描（192 语料：12 prefix × 16 payload）：R3 相对 base 的 DENY→ALLOW 共 34 条，其中 31 条是**设计上刻意**的设备豁免（`/dev/null`）与前缀假朋友（`/various.txt`），3 条属 3b/3c 的未闭面。

### 5. 变异验证（判别力）

- R3 的 `TestNewlineSeparatedCommands` 对 **R2 guard** 必红：`5 failed, 127 passed`（5 条全是换行用例）。
- R3 全测试文件对 **R1 guard** 必红：`17 failed, 115 passed`。
- R3 全测试文件对 **R3 guard**：`179 passed`（含 attack suite 56 条）。
- 结论：新测试**有判别力、非自证**；但 3a/3b/3c 三类**没有对应测试**（这正是它们能残留的原因）。

### 6. 递归 / 崩溃安全（新逻辑 `_shell_dash_c_payload` + `self.check(payload)`）

用交替引号构造 1–3000 层嵌套 `bash -c`：无 `RecursionError`、无异常，最深实测 0.03s。原因是本 tokenizer 对深层嵌套会先「打散」payload，实际递归深度封顶在 ~2 层。指数级转义的深度 16（命令长 131KB）也在 0.27s 内返回 DENY。**`BashTool.execute` 不会因该路径崩（无需 try/except 兜底）。**

### 7. R3 仍未解决的问题（与 R1 的 I3/I4 合流）

- **I3'（major）**：3a 的 wrapper 家族。
- **I4'（major at R3）**：3b 的 subshell/brace 分组（WIP 已修但未提交、无测试）。
- **I5'（minor）**：3c 的 `\r` 残留。
- **I6'（minor, 流程）**：WIP 未提交且**无配套测试**（仓库硬规则：每个 fix 必须有回归测试）；`git status` 为 `M agent/tools/command_guard.py` 而 `tests/` 未动。
- R1 的 I3（文档行号）与 I4（电池落库）在主 session 说明中已按「本 change 不复修 master 既有漂移」处理，**接受**；但 `walkthrough.md` §2.4/§2.5 的行号仍是旧值（本 change 移动了行号），建议在收尾一并更新。

### 独立复算小结（本轮）

| 指标 | 我的实测 |
|---|---|
| 攻击集（base / R1 / R2 / R3） | 50/54 · 50/54 · 50/54 · 50/54（直方图一致，未拦 4 例同） |
| R1 报的 23 条向量在 R3 | 全部回到 DENY（I1/I2 确认修复） |
| 仍存 DENY→ALLOW（vs base/master） | 3a 6 条 + 3b 7 条 + 3c 2 条 = **15 条** |
| 其中 WIP 已修 | 3b 全 7 条 + 3a 的 `-lc`/`-ic`/`-zic` 3 条 |
| WIP 仍缺 | 3a 的 `/usr/bin/env`(2) + `env -i`(1)，3c 的 `\r`(2) |
| 良性误报 | base 14/50 → R3 **1/50**（`cp .env.example .env`，收紧非误伤） |
| 变异验证 | R3 新测试 vs R2 guard = 5 red；vs R1 guard = 17 red；vs R3 = 179 green |
| 递归安全 | 1–3000 层嵌套无 RecursionError |
| 全量 pytest | 见下 |
