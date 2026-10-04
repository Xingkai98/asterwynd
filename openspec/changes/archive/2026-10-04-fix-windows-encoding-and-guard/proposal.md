# Proposal: 修 Windows/locale 编码缺陷类并加机械防护（会话持久化 + 本地文件 I/O）

- 关联 issue：[#294](https://github.com/Xingkai98/asterwynd/issues/294)（实现期网络可用，已建号并回填）。
- 用户报告：在 Windows 上起 web 实测时发现两处可见故障——Hub 会话列表接口 500、新会话根本没落盘；进一步排查确认是同一类缺陷（本地文件 I/O 未显式指定编码，依赖进程 locale）。
- 相关先例：`tests/web_tests/test_python_version_compat.py`（全仓 `rglob` 静态守卫，本次沿用其形态）；#291 里已修掉 4 处同类测试编码缺陷（`subprocess(..., text=True)`）。

## Change Type

- primary: bugfix
- secondary: []

## Why

在 Windows（中文 locale = GBK/cp936）上，**未显式指定编码**的本地文件 I/O 会按 locale 编解码，而仓库里的会话/基准数据一律是 UTF-8：

| 症状 | 证据 |
|------|------|
| `GET /api/sessions` 恒 500（Hub 列表在 Windows 上完全不可用） | `web/server.py:331 → agent/session.py:177` `json.load(f)` → `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa8` |
| 会话保存静默失败（刷新/重启即丢会话） | `agent/loop.py` `WARNING Failed to save session` → `agent/session.py:233` `json.dump` → `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f44b'`（👋）。磁盘上实测只剩 `messages.json.tmp` / `snapshot.json.tmp` |
| benchmark 结果/manifest 读取在本机 `UnicodeDecodeError` | `agent/main.py:952/968/1096/1097` 的 `read_text()`（JSON，UTF-8） |
| 测试大面积假红（本机 47 条） | `tests/**` 33 处 `subprocess(..., text=True)` 未指定编码；#291 已修 4 处，本机 web 套件随即从 47 红降到 9 红 |

**为什么长期没暴露**：CI 两个 job 都是 `ubuntu-latest`，Linux 的 locale 即 UTF-8 ⇒ 不写 `encoding=` 与显式 UTF-8 **行为完全一致**，这类缺陷在现有 CI 上不可能变红；而本机 Windows 的红灯被长期当作「环境性噪声」容忍（本 change 之前 47 条、容忍记录散落在多次 `reviews/acceptance-evidence.md` 里）。**CI 盲区 + 容忍 = 零防护**，所以本次不只要修站点，还要把这类缺陷变成**机械可拦、且 CI 上可复现**的东西。

## What Changes

1. **会话存储显式 UTF-8**：`agent/session.py` 的 6 处 `open()`（读 4 处 + 写 2 处）补 `encoding="utf-8"`，并把 `UnicodeDecodeError` 显式纳入捕获（它是 `ValueError` 的子类、**不是** `OSError`，此前会直接冒泡）。读侧**不**用 `errors="replace"`：替换字符会把「半损内容」当完整会话交付，属静默降级；改为判为「损坏」并如实暴露（见第 2 条）。
2. **列表接口容忍单条损坏**：`list_sessions()` 遇到不可解码/损坏的会话文件 SHALL 跳过该条并在结果里如实标注，SHALL NOT 让整个 `GET /api/sessions` 500（现在一个坏文件就能打掉整个 Hub）。
3. **其余生产站点**：`agent/main.py` 的 4 处 `read_text()` 补编码。
4. **测试站点**：`tests/**` 其余 `subprocess(..., text=True)` 补 `encoding="utf-8"`（33 处里已被 #291 修掉 4 处）。
5. **L1 机械守卫**（新增 `tests/web_tests/test_encoding_hygiene.py`）：全仓静态扫描 `agent/ web/ benchmarks/ scripts/ tests/`，命中三类站点即失败并列出 `file:line`——`open(...)` 缺 `encoding=`（排除 `rb/wb/ab`、非文件 open 如 PIL `Image.open`、fd 形态）、`Path.read_text()/write_text()` 缺 `encoding=`、`subprocess(..., text=True)` **既无 `encoding=` 也无 `errors=`**；配一份**显式白名单 + 理由**（例外可见、可评审）。
6. **子进程口径（与文件 I/O 相反，实测驱动）**：子进程的输出编码是**子进程自己的契约**——我们自己的 python CLI 在 Windows 上往管道写 locale 编码（GBK），父进程若强行按严格 UTF-8 解码反而会崩（实测 `tests/test_flow_policy.py` 的 `show.stdout` 变 `None`，一次改动新增 11 条红）；反过来，子进程写 UTF-8 而父进程按 locale 解码时 `_readerthread` 会抛 `UnicodeDecodeError` 让整段输出丢失（实测 benchmark 一次跑出 16 处）。故规则是：**要么声明 `encoding=`（确定 UTF-8，如本仓 node harness），要么至少 `errors="replace"`（不确定时也不许崩）**——本 change 给 70 处捕获文本的 subprocess 加了 `errors="replace"`。
7. **L2 行为回归**（新增 `tests/agent/test_session_encoding.py`）：
   - emoji（👋）+ CJK + 生僻字往返：`save()` → `load()` 内容一致；
   - 同一段往返放进**子进程**、用 `LC_ALL=C` + `PYTHONCOERCECLOCALE=0`（必要时 `-X utf8=0`）运行，必须同样成功——这是在 Linux 上等价复现 Windows/GBK 条件的办法（ASCII locale 比 GBK 更严格）；
   - 同进程再跑一遍并断言**没有 `EncodingWarning`**（PEP 597：`PYTHONWARNDEFAULTENCODING=1` 下默认编码使用会告警），把「依赖默认编码」变成运行时可观测信号；
   - `list_sessions()` 遇到不可解码/损坏文件时降级（返回其余会话 + 标出损坏项），不抛异常；
   - web 层补一条：某会话含 emoji 时 `GET /api/sessions` 返回 **200** 且含该会话元数据。
7. **L3 CI 覆盖面**：`ci.yml` 的 `validate` job 增加一个 **C locale** 步骤（`LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0` 跑 session/web 子集），并新增一个 **`windows-latest` job** 跑子集（`test_session.py` / `test_server.py` / `test_multi_session.py` / `test_transcript_*`）——后者是唯一能覆盖 Windows 路径语义（`/etc` 拒绝、`~` 展开、大小写不敏感）的手段。
8. **纪律文档**：`docs/testing-guide.md` 增加「平台与编码纪律」一节：本地文件 I/O 一律显式 UTF-8；本机 Windows 红灯 MUST 修或进白名单，SHALL NOT 当环境噪声长期容忍。

## Capabilities

### Modified Capabilities

- `web-ui`：「Web session 本地持久化与恢复」补两条不变量——存储层显式 UTF-8 读写（含非 ASCII/emoji 往返）与「单条会话损坏 SHALL NOT 打掉列表接口」。

## Dependencies

- 无新依赖。CI 层新增 `windows-latest` runner（GitHub 托管，计费约 2×；限定文件范围以控成本）。

## Reference Implementation Research

- research_tier: light
- status: enabled
- reason: 常规缺陷类的收口——「I/O 边界显式编码 + 机械守卫 + 非 UTF-8 locale 下回归」是成熟模式，不需要横向方案调研；命中 `light` 判据（findings + design impact 必填）。
- findings:
  - **CPython 官方为这一类缺陷专门加了机制**：PEP 597（Python 3.10+）引入 `EncodingWarning`，并给出 `-X warn_default_encoding` / `PYTHONWARNDEFAULTENCODING=1` 让「使用 locale 默认编码」变成**可观测告警**；同时明确长期方向是「显式编码优先」。这直接支持本次的双保险（静态扫描 + 运行时告警断言），而不是只靠人眼评审。
  - **业界通行做法是「边界显式 + 机械守卫」两条腿**：显式编码只在有人记得时有效，所以成熟项目普遍配一条 lint/AST 规则（如 flake8 的编码插件、Ruff 的 `PLW1514`「unspecified-encoding」）。本仓没有 Ruff，但已有等价的**全仓静态守卫**先例（`tests/web_tests/test_python_version_compat.py` 用 `rglob` + 子进程 + 列 offenders），因此本 change 沿用该形态而不引入新工具链。
  - **CI 平台矩阵是这类缺陷的唯一有效信号源**：locale 相关缺陷在 UTF-8 环境下不可复现，故业界（含 CNCF/GitHub Actions 生态）通用做法是把「非 UTF-8 locale」显式放进 CI——要么加 Windows/macOS runner，要么在 Linux 上用 `LC_ALL=C` 复现。本 change 两条都加（前者贵、后者便宜，故前者限定文件范围）。
  - **本地参考仓库**：本 change 与 `D:\code\deepseek-harness`（web transcript 展示形态的参考）无关，未使用；如实记录。
- design impact:
  - D1 静态扫描（L1）而非只靠运行时告警：静态可覆盖**未被测试执行到**的代码路径（本缺陷点 `list_sessions` 就没被任何测试跑到）。
  - D2 运行时 `EncodingWarning` 断言（L2）而非只靠静态：静态扫描会漏动态构造（`getattr(Path, "read_text")` 之类），且它让「新写的默认编码」在**执行到**时立刻可见。
  - D3 CI 加 C-locale 步骤 + Windows job：前者便宜且能覆盖编码类，后者覆盖路径语义类；只加其一都会留下确定性的盲区。
  - D4 列表降级而非 500：现有实现一个坏文件即打掉整个 Hub 列表，属「单点失败放大成全局失败」，与仓库既有的「负向态要如实报、不许静默」纪律一致——降级并标注，而不是抛。

## Impact Analysis

### 能力域

- `web-ui`：会话列表接口的可用性与会话持久化的正确性（Windows 上原本完全不可用）。
- 跨能力（存储层）：`agent/session.py` 是 CLI `--resume` 与 Web 共用的存储实现，修复对两端一致生效。

### 代码

| 文件 | 改动 |
|------|------|
| `agent/session.py` | 6 处 `open()` 补 `encoding="utf-8"` + 捕获 `UnicodeDecodeError`；`list_sessions()` 单条降级（`damaged`/`reason`，不冒泡） |
| `agent/main.py` | 4 处 `read_text()` 补 `encoding="utf-8"` |
| `tests/**` | 其余 `subprocess(..., text=True)` 补 `encoding="utf-8"`（33 处，已修 4 处） |
| `tests/web_tests/test_encoding_hygiene.py` | **新增**：L1 全仓静态守卫 + 白名单 |
| `tests/agent/test_session_encoding.py` | **新增**：L2 行为回归（C locale 子进程 / emoji 往返 / EncodingWarning / 列表降级 / API 200） |
| `.github/workflows/ci.yml` | C-locale 步骤 + `windows-latest` job（子集） |
| `docs/testing-guide.md` | 「平台与编码纪律」一节 |

### 测试

- L1/L2 见上；L2 的 C-locale 子进程用例在 **Linux 上也必须能抓到**「不写编码」的回归（否则等于没加）。
- 变异验证：把 `agent/session.py` 的任一 `encoding=` 去掉 → L1 必红；把 `list_sessions()` 的降级去掉 → L2 的降级用例必红；把 API 的容错去掉 → web 用例必红。

### 文档

- `docs/testing-guide.md`（纪律）、`docs/known-debt.md`（若存在无法本次修完的同类站点则记债）、`docs/openspec-change-backlog.md`（立项入队 / 归档出队）。

### process

- 本机 `github.com:443` 若不可达则 issue 创建列为 `(post-merge)`；网络可用时立即建号回填。

### 边界与非目标

- **不做**全仓「所有 I/O 强制显式编码」的大重构：只修生产站点 + 加守卫；测试里的历史站点一次性补齐。
- **不引入**新 lint 工具（Ruff/flake8 插件）：仓库既有的「全仓扫描测试」形态已足够，且不增加依赖。
- **不改**存储格式（仍是 UTF-8 JSON）：本 change 只让读写**确定**用 UTF-8，不动 schema；也**不改**子进程的编码选择（只保证解码不崩）。
- **不改** CLI/Web 的行为契约（除了列表接口从 500 变 200 + 标注）。
