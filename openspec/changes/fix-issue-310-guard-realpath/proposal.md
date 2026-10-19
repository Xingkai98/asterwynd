# Proposal: 命令护栏工作区包含判定两侧统一 realpath 归一

关联 issue：[#310](https://github.com/Xingkai98/asterwynd/issues/310)（本 change 跟踪入口）。
关联既有原语：[#247](https://github.com/Xingkai98/asterwynd/issues/247)（工作区路径段包含判定与
`rm` 越界规则）、[#254](https://github.com/Xingkai98/asterwynd/issues/254)（写白名单共享谓词）。

## Change Type

- primary: bugfix
- secondary: []

## Why

`CommandGuard` 对「工作区」和「命令目标」使用了**不对称的路径归一化语义**：

- 工作区侧在构造时 `Path(workspace).resolve()`（`agent/tools/command_guard.py:706`），是 realpath
  语义，会解析符号链接；
- 命令目标侧 `_normalize_path()`（`:104-112`）只做 `os.path.normpath`，是纯词法语义，不解析
  符号链接。

因此当工作区以符号链接表示时，比较的两侧永远对不上：工作区**内部**的删除被判成越界
（`rm_target_escape`，DENY）。本机（Linux）用显式符号链接实测得到与 issue 完全一致的矩阵：

| workspace 入参 | 命令中的路径 | 实测判定 |
| --- | --- | --- |
| link → real | link/build | **DENY**（`rm_target_escape`） |
| link → real | real/build | ALLOW |
| real | real/build | ALLOW |
| real | link → real/build | **DENY**（`rm_target_escape`） |

同一不对称还出现在 `_allow_covers()`（`:746-749`）：显式写白名单在符号链接工作区下无法覆盖
工作区内的目标（fail-closed，但属同一缺陷类）。缺陷与操作系统无关：macOS 的 `/tmp`、`/var`
只是默认触发入口；Linux 上把 workspace 放到任意符号链接后同样复现（上表实测即为 Linux）。
判定方向是 fail-closed，不构成安全漏洞，但会让符号链接工作区下的正常删除全部被拒。

## What Changes

1. **两侧统一归一化语义（绝对路径 realpath）**：新增单一 helper，对**POSIX 绝对路径直接**
   `Path.resolve()`（realpath，解析符号链接，且 `..` 在符号链接解析后折叠）；工作区在构造时
   已使用同一 realpath 语义，命令目标改用该 helper 后两侧可比。**不做** `os.path.normpath`
   前置——实测 normpath-first 会把 `<ws>/escape/../victim` 词法折叠成工作区内路径，留下真实
   越界放行。解析**strict-first**：仅 `FileNotFoundError`（目标尚不存在）回退非严格解析，
   循环/权限等 `OSError`/`RuntimeError` 一律 `None`（fail-closed）——Python 3.13+ 的非严格
   `resolve()` 对符号链接循环会返回字面路径而不抛异常。相对路径保持词法归一化：护栏不掌握
   命令的 cwd，既有契约也把相对目标视为工作区内，不做基于 cwd 的解析。
2. **两个工作区包含判定点统一修复**：`_check_rm()` 的越界/根删除判定与 `_allow_covers()` 的
   白名单相对路径计算都改走该 helper。`:746-747` 经确认是同类问题（同一对「词法目标 vs
   realpath 工作区」比较），一并修复。`_check_rm()` 内**拆两个变量**：`_DENY_PATHS` 与特殊
   token 仍用词法结果，只有工作区包含与根删除用 canonical 结果（见 Non-Goals）。
3. **保持 fail-closed 与双向包含关系**：仍使用 `_within()` 的路径段比较（不是裸字面前缀）；
   绝对路径无法解析（符号链接循环等）时**显式**判「不在工作区内」，不得让 `None` 进入字符串
   操作；`..` 穿越（含符号链接后的 `..`）、前缀碰撞、删工作区本身全部保持 DENY。符号链接
   工作区**内部**指向工作区**外部**的链接目标由 realpath 判为越界（这是保守收紧，不是放行；
   无尾斜杠的 `rm -rf <ws>/escape` 实际只删链接，误报代价登记在 design Risks）。
4. **测试加固**：用 pytest `tmp_path` + `os.symlink` 显式构造「workspace 与命令字面表示不一致」
   的双向场景，在 ubuntu 语义下即可稳定复现红→绿，不依赖宿主 `/tmp` 是否为符号链接；Windows
   上 `os.symlink` 无权限时 `pytest.skip`。
5. **规格同步**：`workspace-safety` 的路径规范化条款补充「工作区边界判定对绝对路径 SHALL
   解析符号链接，使工作区与目标使用同一规范表示；受保护路径判定保持词法；解析失败
   fail-closed」，并新增 4 个 Scenario（工作区放行、链接逃逸、`escape/../victim`、循环
   fail-closed）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `workspace-safety`：命令护栏的工作区包含判定在原有「解析 `..`/`.` 段」之上，SHALL 对绝对路径
  同时解析符号链接（realpath 语义），使工作区的符号链接表示与目标路径可比较；相对路径保持词法
  归一化。该判定 SHALL 继续使用路径段包含关系，SHALL NOT 退化为裸字面前缀；绝对路径解析失败
  时 SHALL 判为不在工作区内（fail-closed）。

## 需求

1. **符号链接工作区内 ALLOW**：workspace 为 `link → real` 时，`rm -rf <link>/build` 与
   `rm -rf <real>/build` 均 SHALL 为 ALLOW；workspace 为 `real` 时两者同样 SHALL 为 ALLOW。
2. **负例保持 DENY**：越界路径、`..` 穿越、前缀碰撞（`<ws>-evil`）、删工作区根本身（两种表示）
   SHALL 全部 DENY；判定 SHALL 保持路径段包含关系。
3. **无 fail-open**：工作区内部指向外部的符号链接目标、以及符号链接后的 `..`
   （`<ws>/escape/../victim`，`escape → outside`）SHALL 被判为越界；绝对路径无法解析时
   SHALL 显式 fail-closed；相对路径语义 SHALL 保持不变。
4. **白名单同源**：`_allow_covers()` SHALL 与越界判定使用同一归一化语义；符号链接表示下的
   工作区内白名单目标 SHALL 被覆盖，指向工作区外部的链接目标 SHALL NOT 被覆盖。白名单
   正例 SHALL 用 `tee` / `>>` / `dd of=` 构造（`cp`/`mv` 的绝对敏感目标会先被 denylist 拦下，
   测不到该判定点）。
5. **无平台分支**：实现 SHALL NOT 包含按 `sys.platform` / `os.name` 等平台分支的逻辑。工作区
   包含判定的「绝对路径」沿用既有 POSIX 口径（`/` 开头）；Windows 盘符路径的既有行为 SHALL
   NOT 被本 change 改变。
6. **回归测试**：SHALL 用 `tmp_path` + `os.symlink` 显式构造双向场景；既有护栏测试 SHALL NOT
   回归；新增用例在 ubuntu 语义下可红→绿复现；符号链接循环（loop 放在工作区内）SHALL 有一条
   fail-closed 回归，且在 Python 3.11–3.14 上语义一致。Windows 上测试 SHALL 按 POSIX 语义
   skip（`os.name != "posix"`），不把平台差异伪装成业务失败。

## Non-Goals

- **不**把 issue 的 C（把 `test_command_guard.py` 纳入 `windows-platform` job、新增 macOS
  runner）拖进本 change；C 与本 issue 明确解耦。
- **不**为 `_DENY_PATHS`（`/etc`、`/var` 等）引入 symlink 解析：那属于另一判定面，且会扩大本
  bugfix 的语义变化面；本 change 只修工作区包含判定这一处不对称。
- **不**处理相对路径的 `..` 逃逸（护栏不掌握 cwd，属既有边界，另记债务/issue）。
- **不**改变 Windows 盘符绝对路径的既有判定口径：工作区包含判定沿用 `startswith("/")` 的
  POSIX 口径，不新增平台分支（issue 的 C 已解耦）。
- **不**追求「工作区内 symlink 的 DENY 一定对应真实删除目标在工作区外」：无尾斜杠的
  `rm -rf <ws>/escape` 只删链接，该 DENY 是保守过度判定，误报代价在 design Risks 登记。
- **不**改 `rm` 以外的命令判定规则；唯一例外是写白名单的 workspace 相对路径计算
  （`_allow_covers()` 同时服务 `cp`/`mv`/`dd`/`tee`/重定向/`install`），它改用同一 canonical
  语义。不改 denylist 扫描顺序，不改写白名单匹配谓词本身。
- **不**处理「workspace 的 realpath 本身落在受保护根」的病态配置（如 workspace → `/etc`）：
  受保护路径判定保持词法，该边界在 design Non-Goals/Risks 登记。
- **不**改动 witnessloop 仓、`v1` / `v1.7.0` tag 或 `.witnessloop/**`。

## Impact Analysis

- 影响代码：`agent/tools/command_guard.py`
  - 新增统一归一化 helper；
  - `CommandGuard._check_rm()` 的工作区包含与根删除判定；
  - `CommandGuard._allow_covers()` 的相对路径计算；
  - 其余 `_normalize_path()` 调用点（受保护路径判定）不动。
- 影响测试：`tests/agent/tools/test_command_guard.py`
  - 新增符号链接双向矩阵、负例、工作区内 symlink 逃逸（含 `escape/../victim`）、循环
    fail-closed、写白名单同源用例；
  - 本分支基线实测 **272 passed**（issue 的 301 来自更早的 `83dbaae` 口径），既有用例不回归。
- 影响规格：`openspec/specs/workspace-safety/spec.md`（MODIFIED 命令护栏 Requirement 的规范化
  条款 + 4 个 Scenario：工作区放行、链接逃逸、`escape/../victim`、循环 fail-closed）。
- 影响文档：
  - `docs/openspec-change-backlog.md`（登记/移除本 change）；
  - `docs/adr/ADR-0008-guard-workspace-realpath-containment.md`（归一化方案与备选、strict-first）。
- 风险面：
  - 对绝对目标增加 realpath 解析（目标存在时一次 strict resolve；不存在时最多两次）；
    护栏本就只处理单条命令，成本可忽略。
  - symlink 在工作区内、真实目标在工作区外的删除从 ALLOW 变 DENY —— 属正确收紧，已在
    design 论证并加回归测试。
  - TOCTOU：检查后符号链接被替换的窗口与既有 realpath 工作区语义同源，不在本 change 责任面。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: bugfix（无新增能力面，配套回归测试）；根因、修法方向与验收标准已由 issue #310 的诊断
  与实测矩阵锁定，属既定 bugfix 处置，无待定设计项，无需横向调研。

## 用户故事

- 作为在 `/tmp`（macOS）或任意符号链接工作区下运行的开发者，工作区内部的 `rm -rf build`
  ALLOW，而不是被 `rm_target_escape` 误拒。
- 作为安全审阅者，前缀碰撞、`..` 穿越、删工作区根本身与通过工作区内符号链接逃逸的删除仍全部
  DENY，修复没有引入 fail-open。
- 作为维护者，工作区包含判定与写白名单共享同一归一化语义，不再有两套互相对不上的路径表示。
