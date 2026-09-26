# Building Review: fix-issue-247-guard-path-boundary

- reviewer: 独立零记忆 subagent（未参与实现）
- base: `369d99d`（master 祖先；`master` 现为 `14f6e24`，是本 change 之外的另一 change）
- head: `be480dd`
- 方式：只读审阅 + 独立复算（加载 base 版 `command_guard.py` 为 `old_guard` 与 head 版对比跑全量语料；另在 `/tmp/247-verify/mut` 影子树把 base 版 guard 装回、跑 head 的新测试做变异验证）

## Verdict

**CHANGES_REQUESTED**

修复方向正确、攻击集不退化、误报族确实清零，但**删除 `_EXTRA_DENYLIST` 的点目录正则分支时没有把链式命令（`cd x && cp ...`）纳入 argv 通道**，导致一批 base 能拦的敏感点目录写入被新代码放行——是净拦截面的**实质性缩小**，与 proposal Goal #4、「不削弱任何既有攻击拦截」及 spec 的 SHALL 直接冲突。见 I1（major）。

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
