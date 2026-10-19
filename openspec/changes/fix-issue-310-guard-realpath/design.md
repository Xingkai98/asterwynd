# Design: 命令护栏工作区包含判定两侧统一 realpath 归一

## Context

`CommandGuard` 的工作区包含判定是两段代码共同完成的：

1. **工作区侧**（构造时）：`agent/tools/command_guard.py:706`

   ```python
   self._workspace = str(Path(workspace).resolve()) if workspace else None
   ```

   `Path.resolve()` 是 realpath 语义：解析符号链接，得到规范绝对路径。

2. **命令目标侧**（判定时）：`_normalize_path()`（`:104-112`）只做 `os.path.normpath`，
   纯词法语义，不解析符号链接。消费点有两处：
   - `_check_rm()`（`:1146-1159`）：`rm` 目标的越界与「删工作区根」判定；
   - `_allow_covers()`（`:746-749`）：显式写白名单的 workspace 相对路径计算。

于是只要 workspace 的**字面表示**经过符号链接，两侧的规范表示就不同：

```
workspace 参数 = link → real
命令目标       = link/build
词法目标       = /…/link/build
realpath 工作区 = /…/real
→ 不含于 → rm_target_escape（DENY，误拒）
```

本机（Linux，`python3` + 显式 `os.symlink`）复现的矩阵与 issue #310 完全一致（见
proposal「Why」）。issue 指出的 `:746-747` 经复核是**同一对比较的另一个消费点**：目标用词法、
工作区用 realpath，写白名单在符号链接表示下无法计算相对路径（同样 fail-closed 误拒）。

其余 `_normalize_path()` 调用点（`_check_mv_cp` / `_check_dd` / `_check_tee` /
`_check_chmod` / 重定向）只与固定的 `_DENY_PATHS` 比较，不涉及工作区的两种表示，不受本缺陷
影响；它们既有的「不做 realpath」边界不在本 change 范围内。

**关键诊断（grill high）**：绝对路径不能先 `os.path.normpath` 再 `Path.resolve()`。
`os.path.normpath` 会把符号链接后的 `..` **按词法折叠**，而 POSIX 路径解析是在跟随符号链接
**之后**再处理 `..`。本机实测（Python 3.12）：

```text
<ws>/escape/../victim   （escape → <outside>）
  Path(...).resolve()                    = <ws 的父>/victim   ← 真实目标，工作区外
  Path(os.path.normpath(...)).resolve()  = <ws>/victim        ← 词法折叠，误判工作区内
```

即 normpath-first 会让 `rm -rf <ws>/escape/../victim` 继续放行真实越界路径，与「realpath 统一
表示」的目标相反。故绝对路径直接 `Path(path).resolve()`；只有相对路径才走
`os.path.normpath`。

## Goals / Non-Goals

**Goals**

- 工作区以任意符号链接表示时，工作区**内部**的 `rm`（任何一侧的表示）均 ALLOW。
- 越界、`..` 穿越、前缀碰撞、删工作区本身、工作区内符号链接逃逸（含 `escape/../x`）全部
  保持 DENY。
- 越界判定与写白名单使用同一归一化语义，保持路径段包含关系。
- 不引入平台分支；新增回归测试在 ubuntu 语义下红→绿，不依赖宿主 `/tmp` 是符号链接。

**Non-Goals**

- issue 的 C（windows job 清单、macOS runner）不在本 change。
- 不为 `_DENY_PATHS` 引入 realpath 判定；不改 denylist / 解析器 / 白名单谓词。
  因此 `_check_rm()` 内拆成两个变量：`_DENY_PATHS` 与特殊 token 仍用词法结果，只有
  工作区包含与根删除用 canonical 结果。
- 不改相对路径语义（护栏不掌握 cwd）。
- 不改 Windows 盘符绝对路径的既有口径：`:1154` 的 `startswith("/")` 与 `_within()` 的
  `/` 分隔使工作区包含判定实际是 **POSIX 绝对路径**口径；Windows 盘符路径不进入该判定，
  本 change 不扩大范围（issue 的 C 已解耦）。
- 不承诺「工作区内符号链接的 DENY」等于「真实删除目标一定在工作区外」：无尾斜杠的
  `rm -rf <ws>/escape` 只删除链接本身。该 DENY 是**保守过度判定**，以可预测性与
  fail-closed 优先，代价登记在 Risks。
- 不处理「workspace 的 realpath 本身落在受保护根」的病态配置：例如 workspace 指向
  `→ /etc` 时，`rm -rf <link>/passwd` 的 canonical 目标在 workspace 内、受保护路径判定
  仍是词法，因而 ALLOW（修复前因工作区表示不一致反而 DENY）。工作区是受信任的边界配置，
  同一 workspace 下相对路径 `rm -rf passwd` 修复前本就 ALLOW；本 change 不把受保护路径
  判定扩张成 realpath（见 Non-Goals 的上一条），该边界登记在 Risks。

## Decisions

### Decision 1：绝对路径直接 realpath，相对路径保持词法

**选择**：新增一个 helper（最终形态）：

```python
def _canonical_path(path: str) -> str | None:
    # POSIX 绝对路径口径，与既有 startswith("/") 判定一致
    if not path.startswith("/"):
        return os.path.normpath(path)
    try:
        return str(Path(path).resolve(strict=True))
    except FileNotFoundError:
        pass                    # 目标尚不存在：走下面的非严格解析
    except (OSError, RuntimeError):
        return None             # 循环 / 权限等：fail-closed
    try:
        return str(Path(path).resolve(strict=False))
    except (OSError, RuntimeError):
        return None
```

- 绝对路径**直接** `Path.resolve()`：`..` 在符号链接解析后折叠，符合 POSIX realpath 语义；
- **先 strict、仅对 `FileNotFoundError` 回退非严格**（grill 对抗轮 ADV-01）：Python 3.13+
  的非严格 `resolve()` 对符号链接循环会返回字面路径而不抛异常，若只用非严格解析，循环路径
  会凭字面表示混进工作区（实测 3.13/3.14；3.11/3.12 抛 `RuntimeError`）。strict 解析对循环
  抛 `OSError`/`RuntimeError` ⇒ `None`；「目标尚不存在」是 `rm` 的常见场景（`build` 可能还
  没创建），strict 抛 `FileNotFoundError` 后再用非严格解析，尾部按词法追加；
- 相对路径只做 `os.path.normpath`：护栏不掌握命令执行时的 cwd，`Path("build").resolve()`
  会错误地按护栏进程 cwd 展开；
- 解析失败返回 `None`，由调用方显式 fail-closed（见 Decision 3）。

**为什么不是「先 normpath 再 resolve」**：Context 的实测已证伪——它把 symbol-link + `..`
词法折叠，留下真实越界放行，且与 design 早期版本自己的证据表不符。grill 的 high 项即此。

**为什么不是「原始表示 + realpath 表示双向命中」**：设 workspace 词法为 W、real 为 R，目标
词法为 T、real 为 T′。若允许「T ∈ W **或** T′ ∈ R」，则工作区内部的链接 `escape → /outside`
下，`rm -rf W/escape` 的 T ∈ W 会成立并放行，而真实目标是 `/outside` —— 这正是要避免的
fail-open。若要求两种表示**同时**命中，则等价于本决策的 realpath 判定，还多维护一份状态。
单一规范表示（realpath）更简单且没有组合歧义。

**证据（本机 Python 3.12.3 实测）**：

| 输入 | `Path(path).resolve()`（采用） | `Path(normpath(path)).resolve()`（拒绝） |
| --- | --- | --- |
| `link/build`（link → real） | `real/build` | `real/build` |
| `link/missing/deep` | `real/missing/deep` | `real/missing/deep` |
| `real/escape/x`（escape → outside） | `outside/x` | `outside/x` |
| `real/escape/../real` | `real` | `real/real`（与真实解析不符） |
| `ws/escape/../victim` | `<ws 的父>/victim`（工作区外） | `<ws>/victim`（工作区内） |
| 符号链接循环（非严格 resolve） | 3.11/3.12 `RuntimeError`；**3.13/3.14 返回字面路径** | 同左（循环在 resolve 阶段） |
| 符号链接循环（strict-first） | `None`（3.11–3.14 实测一致） | `None` |

结论：resolve-first 才符合「两侧同一真正规范表示」；不存在的尾部组件按词法追加
（`link/missing/deep`），不会误伤尚未创建的删除目标。跨版本实测（`uv python install`
3.13.14 / 3.14.6，配合本机 3.11.15 / 3.12.3）：非严格 `Path.resolve()` 在 3.13+ 对循环返回
字面路径（不抛异常），因此必须 strict-first；strict-first 在四个版本上对循环均返回 `None`，
对不存在目标均正常回退。

### Decision 2：`_allow_covers()` 一并修复（issue 的 `:746-747`）

`:746-747` 与 `_check_rm()` 是同一对「词法目标 vs realpath 工作区」比较：写白名单要先用
`_within()` 判断目标是否在工作区、再 `os.path.relpath()` 求相对路径。统一改走 helper 后：

- workspace=`link`、目标 `<link>/.env` 或 `<real>/.env` 都能算出相对路径 `.env`，白名单生效；
- workspace 内的 `escape → /outside` 下，目标 `<ws>/escape/.env` 的 realpath 在工作区外，
  `_within()` 不成立 ⇒ 白名单**不覆盖**，保持 DENY；
- helper 返回 `None` ⇒ `_allow_covers()` 返回 `False`（不覆盖）；
- 白名单按**真实目标的 workspace 相对路径**匹配：工作区内 `.env → config/dev.env` 时，
  allowlist 里的 `.env` 不再覆盖该目标（修复前按字面覆盖），allowlist 需写
  `config/dev.env`；反方向（`.env → 工作区外`）由本修复关闭（修复前可借白名单写外部）。
  这是 fail-closed 方向的语义收紧，测试同时钉住两个方向。

**测试命令注意（grill medium）**：白名单正例**不能**用 `cp x <ws>/.env` / `mv`。`cp`/`mv`
的绝对敏感目标会先被 `_EXTRA_DENYLIST` 的整句正则（`:611`）拦下（`last_reason=denylist`），
根本到不了 `_allow_covers()`。测试固定用 `tee <ws>/.env`、`echo K >> <ws>/.env` 或
`dd of=<ws>/.env`（修复前分别落在 `tee_target` / `protected_redirect` / `dd_target`）。

### Decision 3：`None` 显式 fail-closed

绝对路径无法规范化（strict 解析对符号链接循环抛 `OSError`/`RuntimeError`，权限等同理）时
helper 返回 `None`。`FileNotFoundError` 是「目标尚不存在」而非失败，走非严格解析（Decision 1）：

- `_check_rm()`：在**任何字符串操作之前**显式判 `None` ⇒ `rm_target_escape` DENY；
  不能把 `None` 传进 `normalized.startswith("/")`（会 `AttributeError`）；
- `_allow_covers()`：返回 `False` ⇒ 白名单不覆盖。

不把「无法解析」当作词法路径继续比较，否则循环链接可能凭字面表示混进工作区。

### Decision 4：`_check_rm()` 拆成词法与 canonical 两个变量

`_check_rm()` 的同一个 `normalized` 变量今天同时供两处使用：

- `:1148` `_DENY_PATHS` 与 `"/"` / `$HOME` / `~` 的特殊 token 判定；
- `:1154` 工作区包含判定、`:1159` 工作区根判定。

本 change 只让后者改用 `_canonical_path()`；前者保持 `_normalize_path()`：

```python
lexical = _normalize_path(target.replace("$IFS", ""))       # 受保护路径，词法，不变
if lexical in ("/", "$HOME", "~") or any(_within(lexical, p) for p in _DENY_PATHS):
    deny
if self._workspace:
    canonical = _canonical_path(target.replace("$IFS", ""))  # 工作区包含，realpath
    if canonical is None: deny
    if canonical.startswith("/") and not _within(canonical, self._workspace): deny
    if canonical == self._workspace: deny
```

这样 proposal 的 Non-Goal「不为 `_DENY_PATHS` 引入 symlink 解析」在代码上成立，且与
`_check_mv_cp` / `_check_dd` / `_check_tee` / 重定向的词法判定保持一致。

### Decision 5：工作区内指向外部的符号链接目标改判越界（保守过度判定）

修复前：目标词法在工作区内 ⇒ ALLOW。修复后：realpath 在工作区外 ⇒ DENY。

**准确表述（grill low）**：无尾斜杠的 `rm -rf <ws>/escape` 在 GNU rm 下只删除符号链接本身，
不会删除外部 victim；带尾斜杠的 `rm -rf <ws>/escape/` 才会跟随链接删除外部内容。守卫无法
在不解析尾部语义的情况下区分两者，因此选择**保守过度判定**：只要 realpath 在工作区外就
DENY。代价是对「只删链接」这一常见操作新增误报（fail-closed 方向），登记在 Risks；
SHALL NOT 用「真实删除目标一定在工作区外」来解释该 DENY。

### Decision 6：判定仍用路径段包含，不退化

`_within()` 原样保留：`path == prefix` 或 `path.startswith(prefix.rstrip("/") + "/")`。
realpath 只改变比较前的表示，不改变「包含」的定义。`<ws>-evil` 这类前缀碰撞在 realpath 后仍
不是路径段包含 ⇒ DENY。

### Decision 7：测试显式构造符号链接，不依赖宿主形态

- `tmp_path` 下创建 `real-ws/` 与 `link-ws → real-ws`；
- 四行 ALLOW 矩阵：workspace ∈ {link, real} × 目标 ∈ {link/build, real/build}（修复前第 1、
  4 行红，第 2、3 行绿）；
- 负例：`<tmp>/link-ws-evil`、`<link>/../etc`、`rm -rf <link>`、`rm -rf <real>`；
- **符号链接逃逸（两条）**：工作区内 `escape → outside` 的 `rm -rf <ws>/escape` 与
  `rm -rf <ws>/escape/` 均 DENY；`rm -rf <ws>/escape/../victim` DENY（区分 resolve-first 与
  normpath-first 的关键用例）；
- **符号链接循环**：在工作区内建 `<ws>/loop → loop`，`rm -rf <ws>/loop/x` 断言 DENY
  （strict-first 解析返回 `None`）；本机 3.11.15 / 3.12.3 / 3.13.14 / 3.14.6 均已实测
  strict-first 对循环 fail-closed。该测试把 loop 放在**工作区内**，确保覆盖的是
  `None`/fail-closed 分支而不是「越界」结论；
- 写白名单同源：`allowed_write_paths=(".env",)` 下用 `tee` / `>>` / `dd of=` 验证 link/real
  双向表示 ALLOW；前缀碰撞与逃逸目标 DENY；
- 测试类在 `os.name != "posix"` 时 `pytest.skip`（工作区包含判定是 POSIX 口径；
  Windows 盘符路径不进入 `startswith("/")` 分支），`os.symlink` 抛 `OSError` 时同样
  `pytest.skip`（无开发者模式/管理员权限的常见情形）。
- 修复前红/绿记录与变异验证（把 helper 退回 `os.path.normpath` 应使新增正向用例与
  `escape/../victim` 负例变红）。

## Risks / Trade-offs

- **保守误报（low）**：`rm -rf <ws>/escape`（无尾斜杠）只删链接却被 DENY。选择可预测的
  fail-closed；如未来要区分尾部斜杠语义，应另立 change。
- **POSIX-only（low）**：工作区包含判定只对 `/` 开头的绝对路径做 realpath；Windows 盘符路径
  沿用既有口径（不进入包含判定）。issue 的 C 已明确解耦。
- **Python 版本差异（已缓解）**：`Path.resolve()` 在 3.13+ 改为委托 `os.path.realpath`，
  非严格解析对符号链接循环返回字面路径（3.13/3.14 实测）。helper 采用 strict-first、仅对
  `FileNotFoundError` 回退非严格，3.11–3.14 实测对循环一致 fail-closed；回归测试把 loop
  放在工作区内。`pyproject.toml` 声明 `>=3.11`，issue 环境为 3.14。
- **workspace 本身落在受保护根（low）**：病态配置下 `rm` 的工作区包含判定优先于词法
  `_DENY_PATHS` 判定（见 Non-Goals）。工作区是受信任配置，且相对路径本就可删其内容；
  如未来要求「受保护根即使作为 workspace 也拒绝」，应另立 change 把受保护路径判定也
  realpath 化。
- **白名单按真实目标匹配（low）**：工作区内 `.env → config/dev.env` 时 allowlist `.env`
  不再覆盖，需写 `config/dev.env`；反向的外部链接目标由本修复关闭。属 fail-closed 收紧，
  已在 Decision 2 与测试中钉住。
- **多余的文件系统调用（low）**：目标存在时一次 strict `Path.resolve()`；目标不存在时
  strict 抛 `FileNotFoundError` 后再做一次非严格解析（最多两次）。护栏处理的命令粒度是
  单条 shell 行，成本可忽略。
- **TOCTOU（low）**：检查时与执行时的符号链接可能被替换。既有工作区 realpath 语义已接受同一
  窗口，且默认执行后端本就不承诺文件系统边界（护栏不是边界）。
- **相对路径仍是既有边界**：`rm -rf ../outside` 在无绝对前缀时不进入工作区判定。这是既有
  语义（护栏不掌握 cwd），本 change 不扩大范围；design 如实记录。

## Testing Strategy

1. **TDD**：先在 `tests/agent/tools/test_command_guard.py` 写符号链接矩阵与新负例，确认在
   未修实现上红（断言 `ALLOW` 的第 1/4 行、白名单两行、`escape/../victim` 负例失败），再实现
   helper 与两处接线。
2. **负例回归**：既有 `TestPathSegmentBoundary` 的前缀碰撞、`..`、根删除用例保持绿；新增
   `<ws>-evil` / 根删除的 link 与 real 两种表示。
3. **变异验证**：把 helper 的 realpath 分支退回 `os.path.normpath`（或把 resolve 改成
   normpath-first），新增正向用例与 `escape/../victim` 负例应变红；恢复后全绿。
4. **定向命令**：
   `uv run pytest -q tests/agent/tools/test_command_guard.py tests/agent/tools/test_guard_three_state.py tests/benchmark/test_attack_suite.py tests/benchmark/test_ask_suite.py`。
5. **全量**：`uv run pytest -q`；与本机基线对照，已知 `/tmp` 环境失败须同因、无新增失败类型。
6. **规格**：OpenSpec strict validate；瘦 checker `--base-ref origin/master --require-base`。

## Open Questions

无。归一化语义取舍已由 issue #310 的验收标准约束，且替代方案（词法 workspace / 双表示 /
normpath-first）经 grill 的实测反例证伪；其余边界（相对路径、`_DENY_PATHS` realpath、
POSIX-only、尾部斜杠误报）明确列为 Non-Goal 或 Risks。

## Pre-Implementation Review

- **grill**：独立零记忆 agent `1ffd9f5c-b848-4de7-87a6-3b3f275dbe2b`（2026-10-19）产出
  `reviews/grill-design.md`：6 条 Confirmed Decisions、0 Open Questions；提出 6 项必须修改，
  已全部整合：
  1. high（helper 顺序）→ Decision 1 改为绝对路径直接 resolve，Context 增补实测反例；
  2. medium（`_DENY_PATHS` 隐式 realpath）→ Decision 4 拆两个变量；
  3. medium（白名单 `cp` 被 denylist 先拦）→ Decision 2 / Testing Strategy 固定用
     `tee` / `>>` / `dd of=`；
  4. medium（spec overclaim）→ spec delta 把 realpath 收窄到工作区包含与白名单相对路径；
  5. medium（`None` 落到代码路径）→ Decision 3 显式分支；
  6. low（链接删除理由不准确）→ Decision 5 改为「保守过度判定」，Risks 登记误报。
  另整合 3 条 low：POSIX-only 口径、循环链接回归、`_normalize_path()` 注释同步。
- **设计阶段对抗闭环**：独立零记忆审阅者 `274d81c4-e470-4f93-beea-a77c5ec4ed4f`
  （2026-10-19）产出 `reviews/grill-adversarial.md`。第 1 轮批次 1 项 medium
  **ADV-01**：非严格 `Path.resolve()` 在 Python 3.13+ 对符号链接循环返回字面路径，
  使新 spec Scenario 与跨版本测试断言不可执行。已修：Decision 1 改为 strict-first、
  仅对 `FileNotFoundError` 回退非严格；跨版本实测 3.11.15 / 3.12.3 / 3.13.14 / 3.14.6
  对循环一致 fail-closed；Decision 7 与 spec Scenario 保持 DENY 口径。
  low/nit（ADV-L1–L7）已逐条处置：L1/L6 写入 Non-Goals/Risks，L2 测试加 POSIX skip，
  L3–L5 修正文档计数与措辞，L7 补 `docs/adr/ADR-0008-...`。
  **第 1 轮修复验证 PASS**（同一审阅者复验）：ADV-01 在 Python 3.11.15 / 3.12.13 /
  3.13.14 / 3.14.6 上均 fail-closed，deferred=0，`## 闭环出口` = PASS；剩余 4 条
  low/nit 残留（L2/L3 文档未落齐、L8 场景路径措辞、L9 性能表述）已在收口后补齐。
