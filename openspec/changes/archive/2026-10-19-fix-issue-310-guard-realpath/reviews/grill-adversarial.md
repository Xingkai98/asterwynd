# Grill Adversarial: fix-issue-310-guard-realpath

## Reviewer
- run id: 274d81c4-e470-4f93-beea-a77c5ec4ed4f
- 时间: 2026-10-19
- 审阅基线: HEAD=`c2d2ba4ceb5a7ffc7e2ea8b15cd314d3c40b0edf`
  - `agent/tools/command_guard.py`: `8d56f8c22a61f2cc871706aa8a9cf4acdb1c7c91`
  - `tests/agent/tools/test_command_guard.py`: `d9a821e799f835d45d7f14343af51ad00626ad9a`
  - `openspec/specs/workspace-safety/spec.md`: `4f1c2ce9d68bbe3e9a59f02d43d6f02f6267ed57`
  - `design.md`: `9cc30bfe7dc1cea90ae1184a05b59f142a7841b4`；`proposal.md`: `73d57c927125aef6287ec405ad10f982c0c0d2df`
  - `tasks.md`: `95c3de97dec31c7a5b7f7e1789298eb4238b4ea1`；delta spec: `367793ea1bf843766673cc73c2253563a11ea37f`
  - `reviews/grill-design.md`: `6078d067ac56a6e914956e9167405b7b8eca8169`
- 复核方式：文档逐行对照 + 本机 Python 3.12.3 只读实测（`tmp_path` + `os.symlink`，含现状矩阵与按 design 方案的前瞻模拟），未修改任何实现或测试。

## Grill 六项必须修改项复核
六项均已在文档层落实，未发现遗漏：

1. helper 改为绝对路径直接 `Path(path).resolve()`，无 normpath 前置（`design.md:82-91`，Context 有反例 `design.md:38-50`）。
2. `_check_rm()` 拆词法 / canonical 两变量，`_DENY_PATHS` 与特殊 token 保持词法（`design.md:146-167`，与 `command_guard.py:1135-1163` 的现状结构吻合）。
3. 白名单正例固定 `tee` / `>>` / `dd of=`，并记录 `cp`/`mv` 被整句 denylist 先拦（`design.md:131-134`；本机实测 `cp x <link>/.env` → `deny/denylist`，`tee`/`>>`/`dd` 分别到达 `tee_target`/重定向/`dd_target`）。
4. delta spec 把 realpath 收窄到「工作区边界判定 + 白名单 workspace 相对路径计算」，并明写受保护路径保持词法（delta spec `:13`）。
5. `None` 显式 fail-closed，`_check_rm()` 在字符串操作前分支（`design.md:136-144`）。
6. 链接删除理由改为「保守过度判定」，Risks 登记误报（`design.md:169-177`、`design.md:203-206`；delta spec `:76-81`）。

## 本轮判定
- 第 1 轮：PASS（ADV-01 修复验证通过，批次收口）

### 第 1 轮 · 批次
- **ADV-01 [medium] 符号链接循环的 fail-closed 语义在 Python 3.13+ 不成立，新增 spec Scenario 与跨版本测试断言不可执行。**
  - **规格**：delta spec 新增 Scenario「无法解析的绝对路径 fail-closed」要求 `rm -rf <workspace>/loop/x`（`loop → loop`）SHALL 拒绝（`specs/workspace-safety/spec.md:89-93`）。
  - **设计自相矛盾**：Decision 7 声称该用例「helper 返回 `None`，在 Python 3.11–3.14 上均断言 fail-closed」（`design.md:194-196`）；同一份 design 的 Risks 又承认 3.13+ `Path.resolve()` 改为委托 `os.path.realpath`、循环可能不再抛异常（`design.md:209-211`）。两处不能同时成立。
  - **实测**（Python 3.12.3，本机）：`Path('<ws>/loop/x').resolve()` 抛 `RuntimeError: Symlink loop`；但直接调用 3.13+ 将采用的实现路径 `os.path.realpath('<ws>/loop/x', strict=False)` 返回**字符串** `<ws>/loop/x`（不抛异常）。该字符串在工作区内 ⇒ 计划中的 `_canonical_path()`（`design.md:82-91`）返回非 `None` ⇒ `_within(canonical, workspace)` 为真 ⇒ **ALLOW**。
  - **后果**：在 issue 报告环境 Python 3.14.7 上，上述 spec Scenario 不成立；若测试按 Decision 7 把 `loop` 建在工作区内并断言 DENY，Python 3.13/3.14 会失败；若把 `loop` 建在工作区外，DENY 只是「越界」结论，根本没有覆盖 `None`/fail-closed 分支。两者都不是设计声称的可执行跨版本回归。
  - **影响限定**：OS 自身对 ELOOP 路径的 `rm` 会失败，因此这不是「真实删除越界」的 fail-open，而是**规格条款 + 测试策略的正确性问题**；但该条款是本 change 新写入 SHALL 层的，必须与实现真实一致。
  - **修复建议（二选一，并在 design/spec/tasks 同步）**：
    1. 让 helper 真正对循环 fail-closed：先 `Path(path).resolve(strict=True)`，仅捕获 `FileNotFoundError` 后回退到非 strict resolve（保留「目标尚不存在」的常见删除场景），`OSError`/`RuntimeError` 一律返回 `None`。这样 3.11–3.14 行为一致，spec Scenario 可保留；测试须把 `loop` 放在**工作区内**并断言 DENY。
    2. 或把规格/测试口径限定为「resolver 抛异常时 fail-closed」，删除「3.11–3.14 均断言」与「helper 返回 None」的表述，并新增一条明确覆盖 3.13+ 返回循环字面路径行为的测试（仍建议至少在工作区内验证不出现「凭字面表示混进工作区」的放行）。
  - **证据文件**：`openspec/changes/fix-issue-310-guard-realpath/specs/workspace-safety/spec.md:89-93`、`design.md:138-144`、`design.md:192-196`、`design.md:209-211`。

### 第 1 轮 · 修复验证
- **ADV-01：PASS**
  - **① helper 形态**：`design.md:87-102` 已改为 strict-first——绝对路径先 `resolve(strict=True)`，仅 `FileNotFoundError` 回退 `resolve(strict=False)`，其余 `OSError`/`RuntimeError` 返回 `None`；与修复要求逐行一致。`ADR-0008` 的 Decision 与 Alternatives 同步（`:24-26`、`:39`），并把「只用非严格 resolve」列为拒绝方案。
  - **② 跨版本独立复测**（本机 `/tmp` 显式符号链接，脚本仅用 stdlib）：Python 3.11.15 / 3.12.13 / 3.13.14 / 3.14.6 结果与作者声明一致——非严格 `resolve()` 对 `<ws>/loop/x` 在 3.11/3.12 抛 `RuntimeError`、在 3.13/3.14 返回字面路径 `<ws>/loop/x`；strict-first helper 在四个版本上均返回 `None`（3.13/3.14 strict 抛 `OSError`，3.11/3.12 strict 抛 `RuntimeError`）。
  - **③ 回归面复测**：同一 helper 在四个版本上对 `<ws>/build`、`<ws>/missing/deep` 走 `FileNotFoundError` → 非严格回退并得到工作区内路径；`escape/../victim` 解析为工作区外；dangling 内/外链接分别解析到真实字面目标；权限拒绝（000 目录）返回 `None`。完整 12 用例矩阵（四行 ALLOW、`escape` 与 `escape/`、`escape/../victim`、工作区内循环、link/real 根删除、前缀碰撞、不存在目标）在 3.11–3.14 全部 0 failures；工作区内循环稳定判 `DENY`（`None` 分支）。
  - **④ 文档一致性**：spec delta 的循环 Scenario 已改为「工作区内存在 `<loop> → <loop>`」（`specs/workspace-safety/spec.md:89-93`）；design Decision 3/7 与 Risks 改为 strict-first 口径（`design.md:160-169`、`:219-222`、`:235-238`）；tasks 1.4/2.1 同步（`tasks.md:21`、`:28`）。未发现「非严格 resolve 已足够 fail-closed」的残留宣称——design 证据表与 Risks 均明确 3.13/3.14 非严格解析返回字面路径。
  - **⑤ 门禁**：`scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` EXIT=0；`openspec validate --all --strict` 29 passed / 0 failed。
  - **结论**：ADV-01 已修复；本批 medium+ 清零。

### 下一批（deferred）
- 无（验证期未发现新的 medium+ 问题）。

### low/nit 登记
| id | severity | 问题 | 处置理由 |
|---|---|---|---|
| ADV-L1 | low | 工作区本身经符号链接指向受保护根时，`rm -rf <link>/passwd` 从修复前 DENY 变为修复后 ALLOW。实测：workspace=`<tmp>/etc-link → /etc`，修复前 `rm_target_escape`（目标词法不在 `/etc`、又不在 realpath 工作区 `/etc` 内）；按 design 方案模拟，canonical `/etc/passwd` 落在 workspace `/etc` 内且不等于根 ⇒ ALLOW。design 只声明 `_DENY_PATHS` 保持词法（`design.md:146-167`），未分析这个交互。 | 该 workspace 属病态配置；同一 workspace 下相对命令 `rm -rf passwd` 修复前本就 ALLOW，增量能力有限，且 spec 明写受保护路径判定保持词法（delta spec `:13`），故不升 medium。建议在 Risks/Non-Goals 明写「workspace 的 realpath 若落在受保护根，词法受保护路径不再拦其内部目标」，并补一条钉住该行为的测试；若作者认为「受保护路径始终拒绝」是硬不变量，则本项应升 medium 并在 canonical 分支补 `_DENY_PATHS` 判定。 |
| ADV-L2 | low | 新增测试的 Windows skip 条件不充分：只处理 `os.symlink` 抛 `OSError` 的情形（`design.md:197-199`、`tasks.md:18`）。若 Windows 开发者模式/管理员权限下 `os.symlink` 成功，`tmp_path` 是 `C:\...` 路径，而护栏的工作区包含判定以 `normalized.startswith("/")` 为门槛（`command_guard.py:1154`），新负例（`<ws>-evil`、`<ws>/../etc`、根删除）会因不进入包含判定而 ALLOW ⇒ 测试在 Windows 上失败。 | 实现「无平台分支」不代表测试不能按平台 skip。建议 skip 条件加 `os.name != "posix"`（或断言前检查路径以 `/` 开头），issue 的 C 已把该测试排除在 windows job 之外，故影响有限。 |
| ADV-L3 | low | 场景数量口径不一致：proposal 与 tasks 写「新增 2 个 Scenario」（`proposal.md:56-57`、`tasks.md:36`），delta 实际新增 4 个（`specs/workspace-safety/spec.md:70-93`：放行、escape、`escape/../victim`、循环）。 | 纯文档计数错误，不影响语义；但 tasks 3.2「记录 Requirement 计数」时容易按 2 核对而漏掉 2 条，建议顺手修正。 |
| ADV-L4 | low | Proposal Non-Goal「不改 `rm` 以外的命令语义」（`proposal.md:102`）与 What Changes #2 修复 `_allow_covers()`（同时服务 `cp`/`mv`/`dd`/`tee`/重定向/install 的写目标）字面冲突；后者在符号链接工作区 + allowlist 下确实改变非 `rm` 命令的判定。 | 意图清楚（不改其他命令的判定规则，只修白名单相对路径计算），属措辞过宽；建议改为「不改 `rm` 以外的命令判定规则，除写白名单的 workspace 相对路径计算」。 |
| ADV-L5 | low | 基线测试数「301」与实测不符：`tasks.md:43` 写「基线 301 passed」、`proposal.md:114` 写「301 条左右」；本 worktree/HEAD 实测 `pytest --collect-only tests/agent/tools/test_command_guard.py` = **272**，且 `83dbaae` 与 HEAD 的该测试文件内容相同（100 个 `def test_`、1212 行）。 | tasks 已留「以本分支实测为准」的退路，不阻塞；建议把 301 改为 272（或写明口径来源），避免收尾时按错误基线判断回归。 |
| ADV-L6 | low | `_allow_covers()` 改用 canonical 后，工作区内 `.env` 本身是符号链接（如 `.env → config/dev.env`）时，白名单从「按字面 `.env` 覆盖」变为「按 realpath `config/dev.env` 覆盖」⇒ 修复前 ALLOW、修复后 DENY（实测 old=True/new=False）。这是 fail-closed 方向的语义收紧，design Decision 2 / Risks 未提及。 | 不构成安全问题；反向的 `.env → 工作区外` 反而被本修复关闭（修复前可借白名单写入外部）。建议在 Decision 2 或 Risks 补一句「白名单按真实目标相对路径匹配」，并加一条正向/负向回归钩子。 |
| ADV-L7 | nit | 按 AGENTS.md「planning 阶段有 ≥2 备选方案必须创建 ADR」，Decision 1（single realpath vs 双表示 vs normpath-first）与 Decision 3（`None` 处置）都属多备选设计决策，但 tasks 未安排 `docs/adr/`。 | 该规则无机械门禁，且同类历史 bugfix change（如 guard-write-allowlist）也未建 ADR，故只作提示；建议在 design 中写明不建 ADR 的理由，或按规则补一份简短 ADR。**复验：已建 `docs/adr/ADR-0008-guard-workspace-realpath-containment.md`，内容含 strict-first 与备选拒绝理由，已处置。** |
| ADV-L2-V | low | 第 1 轮 ADV-L2 处置残留：`tasks.md:18` 已加 `os.name != "posix"`，但 `design.md:225` 仍只写「`os.symlink` 抛 `OSError` 时 `pytest.skip`」，未写 POSIX-only skip。 | 不影响实现与 ubuntu CI；属文档未落齐，建议把 `os.name != "posix"` 同步到 design Decision 7。 |
| ADV-L3-V | low | 第 1 轮 ADV-L3 处置残留：`proposal.md:59` 仍写「新增符号链接工作区放行/越界两个 Scenario」，而同文件 Impact Analysis `:125` 与 `tasks.md:36` 已改为 4 个。 | 纯计数遗留；不影响语义，建议把 `proposal.md:59` 改为 4。 |
| ADV-L8 | nit | spec delta 循环 Scenario 的目标写作 `<loop>/x`（`specs/workspace-safety/spec.md:91-93`），未显式写成 `<workspace>/loop/x`；若按相对路径 `loop/x` 读，相对路径保持词法、不会被 helper 规范化，结论会是 ALLOW，与 Scenario 的 DENY 矛盾。 | design/tasks 明确写 `<ws>/loop/x`，实现/测试按绝对路径构造即正确；属措辞歧义，建议在 Scenario 中写全绝对路径以消除误读。 |
| ADV-L9 | nit | 性能表述仍为「每个绝对目标多一次 `Path.resolve()`」（`design.md:246`、`proposal.md:130`、`ADR-0008:50`）；strict-first 对不存在目标会先 strict（抛 `FileNotFoundError`）再非严格，即最多两次 resolve。 | 成本仍可忽略（单条命令粒度），不影响设计；建议改为「一次（目标存在）/最多两次（目标不存在）」。 |

## 收口确认
- 本批 medium+ 数量：**0**（ADV-01 已修复并通过跨版本复验）。deferred 为空，第 1 轮收敛。

## 闭环出口
PASS
