# Grill: fix-issue-310-guard-realpath 设计追问

## Reviewer
- run id: 1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b
- 时间: 2026-10-19

## Confirmed Decisions

- **决策**: 工作区与绝对目标采用**单一 realpath 规范表示**，拒绝「原始表示 + realpath 表示任一命中」的双表示方案；理由: 工作区内存在 `escape → outside` 时，词法表示会命中工作区从而放行真实越界，双表示方案正是该反例的受害者；`_within()` 只接受单一 `path`/`prefix` 比较（`agent/tools/command_guard.py:115-123`）；来源: 1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b
- **决策**: 相对路径保持词法归一，不做基于进程 cwd 的展开；理由: 护栏不掌握命令执行时的 cwd，这是既有契约，也是 issue #310 验收「相对路径语义不变」的要求；`Path.resolve()` 对相对路径会按护栏进程 cwd 展开，语义错误；来源: 1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b
- **决策**: `_allow_covers()` 必须与 `_check_rm()` 共用同一归一化 helper；理由: `agent/tools/command_guard.py:746-749` 是同一对「词法目标 vs realpath 工作区」比较，实测符号链接工作区下白名单目标算不出 workspace 相对路径（`_within` 不成立）而同向 fail-closed；来源: 1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b
- **决策**: 保留 `_within()` 的路径段包含判据，不退化字面前缀；理由: realpath 只改变比较前的表示，`<ws>-evil` 在归一后仍不构成段包含，issue 验收第 4 条要求；来源: 1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b
- **决策**: 绝对路径解析失败时 helper 返回 `None`，调用方 fail-closed；理由: 退回字面比较会让循环链接等不可解析路径混进工作区；但 `_check_rm()` 必须在任何 `str` 操作（尤其 `:1154` 的 `.startswith("/")`）之前显式处理 `None`；来源: 1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b
- **决策**: 工作区内指向外部的符号链接判定为越界（收紧）保持 DENY；理由: 主判定应看真实目标，与白名单逃逸闭合同向；但 design/spec 对该场景的**理由**不准确（无尾斜杠的 `rm -rf` 只删除链接本身），必须以「保守过度判定」如实记录，不能写成「真实目标确实在工作区外」；来源: 1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b

## Code-Resolved Questions

- 白名单正例能否用 `cp x <link>/.env` 验证？ → 不能。`_EXTRA_DENYLIST` 的整句正则 `\b(mv|cp)\s+\S+\s+\S*/\.(?:git|ssh|env|…)(?![\w.-])`（`agent/tools/command_guard.py:611`）在 IR 判定之前就拦截；实测 `cp x <link>/.env` 返回 `deny / last_reason=denylist`，永远到不了 `_allow_covers()`。必须用 `tee`、重定向 `>>` 或 `dd of=`（实测修复前分别为 `tee_target` / `protected_redirect` / `dd_target`）。
- helper 先 `os.path.normpath` 再 `Path.resolve()` 是否满足 design 的证据表？ → 不满足。实测（Python 3.12.3）：`Path('<td>/real/escape/../victim').resolve()` = `<td>/victim`（工作区外），而 `Path(os.path.normpath(...)).resolve()` = `<td>/real/victim`（工作区内）；`real/escape/../real` 同理，design 表写 `real`，按设计的 helper 实得 `real/real`。即 `..` 穿过符号链接被词法折叠，realpath 契约未兑现。
- `_check_rm()` 的 `_DENY_PATHS` 分支会被 realpath 影响吗？ → 会。`:1146` 的同一个 `normalized` 变量同时供 `:1148` 的 `_DENY_PATHS` 判定与 `:1154` 的工作区判定使用；这会让 rm 的受保护路径判定隐式 realpath，与 proposal「不为 `_DENY_PATHS` 引入 symlink 解析」的 Non-Goal（`proposal.md:86-88`）冲突，也与 `_check_mv_cp`/`_check_dd`/`_check_tee`/redirect 的词法判定不一致。
- helper 返回 `None` 时 `_check_rm()` 会怎样？ → `:1147` 的 `in` 比较安全，但 `:1154` 若直接 `normalized.startswith("/")` 会抛 `AttributeError`；Decision 3 必须落成显式分支（`None ⇒ rm_target_escape DENY`），不能只写「视为不在工作区内」。
- spec delta 与 current spec 是否对齐？ → `## MODIFIED Requirements` 的完整 Requirement 块与 `openspec/specs/workspace-safety/spec.md:218-268` 逐行一致，仅目标段（normalize 句）与新增 2 个 Scenario 不同；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 实测 29 passed / 0 failed。但新句「受保护路径与工作区边界…绝对路径 SHALL 解析符号链接」在语法上覆盖了**所有**受保护路径判定，而实现只改 `_check_rm()`/`_allow_covers()`，需收窄措辞。
- `rm -rf <ws>/escape`（无尾斜杠）真的删除工作区外内容吗？ → 不是。实测 GNU rm 只删除符号链接本身（`outside/` 下的 victim 保留）；`rm -rf <ws>/escape/`（带尾斜杠）才跟随链接删除目标内容（victim 消失）。Scenario「工作区内符号链接不得成为越界通道」的括号理由与 Decision 4 的论证需改写为保守过度判定。
- 平台口径如何？ → `:1154` 用 `startswith("/")`、`_within()` 用 `prefix.rstrip("/") + "/"`（`:123`），实现实际是 POSIX 绝对路径口径；Windows 盘符绝对路径不会进入工作区包含判定（既有行为）。与 issue 的 C 解耦，但 spec 的「绝对路径」措辞或 Non-Goals 应如实说明。
- 归档门禁能否满足？ → `.witnessloop/policy.json:11-15` 要求 `agent/**` 挂 change 且 required artifacts 齐全；change 目录已存在；`tasks.md:60-61` 的两条 closeout 已标 `(post-merge)`；RIR `exempt` 的 reason 含 `bugfix`（命中 `scripts/check_openspec_artifacts.py:67-72` 的结构关键词）且 `status: disabled` 符合 tasks 全勾时的要求；grill-design 本报告 + 后续 `grill-adversarial.md`/`building-review.md` 满足归档点证据。
- 既有护栏回归面？ → 实测当前矩阵为第 1、4 行 DENY（`rm_target_escape`）、第 2、3 行 ALLOW，与 issue #310 完全一致；既有 `TestPathSegmentBoundary` 依赖的负例在 realpath 后仍不构成段包含。

## Open Questions

- 无

## 风险

- **high**：helper 的「先 normpath 再 resolve」顺序使 `..` 穿过符号链接仍按词法折叠，`rm -rf <ws>/escape/../victim` 实测被判定在工作区内（planned helper：`<td>/real/victim` inside=True；resolve-first：`<td>/victim` inside=False）。这是既有的真实越界放行，而且 design 的证据表与 spec delta 的 realpath 口径都宣称它会被修掉；实现前必须修正（建议绝对路径直接 `Path(path).resolve()`，相对路径才 normpath）。
- **medium**：`_check_rm()` 内 `_DENY_PATHS` 与工作区判定共用一个 `normalized`，realpath 会隐式改变受保护路径判定面，与 proposal Non-Goal 冲突。必须二选一：拆成「词法变量 + canonical 变量」保持 Non-Goal，或显式接受收紧并同步修改 proposal/design/spec。
- **medium**：白名单正例若按 tasks 1.5 用 `cp`/`mv` 的绝对 `.env` 目标编写，会被 denylist 在 `_allow_covers()` 之前拦下，TDD 永远无法转绿；可能诱导实现者去改明令不动的 denylist 扫描顺序。测试必须固定用 `tee`/重定向/`dd of=`。
- **medium**：spec delta 把 realpath 规范化写进「受保护路径与工作区边界」整句，超出本 change 实际改动面（`_check_mv_cp`/`_check_dd`/`_check_tee`/redirect 仍词法），属规格 overclaim。
- **low**：无尾斜杠的 `rm -rf <ws>/link` 只删除链接本身却被 DENY，是对常见操作的新误报（fail-closed 方向，但应在 Risks/Non-Goals 登记，不能以「真实目标在工作区外」解释）。
- **low**：符号链接循环的 fail-closed 证据只在 Python 3.12 上取得；`pyproject.toml:5` 声明 `>=3.11`，issue 环境是 Python 3.14，3.13+ 的 `Path.resolve()` 改为委托 `os.path.realpath`，非 strict 模式下符号链接循环可能不再抛异常。建议补一条循环回归测试并明确预期（影响有限：OS 自身也拒绝跟随循环）。
- **low**：`startswith("/")` 与 `_within()` 的 `/` 分隔决定了该判定是 POSIX-only，Windows 绝对路径不进入包含判定；需在 Non-Goal 或规格中如实记录，避免读者按字面理解「任意绝对路径」。
- **low**：每个绝对目标多一次 `Path.resolve()` 文件系统调用；护栏粒度是单条命令，成本可忽略（同意 design 判断）。
- **low**：`_normalize_path()` 的 docstring 与模块顶部注释仍描述「规范化即可」而不提 realpath 不对称，改动后应同步注释，避免后续调用点误用词法版本。

## User Confirmation

- 无待拍板项
