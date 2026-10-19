# ADR-0008: 命令护栏的工作区包含判定统一使用 realpath 规范表示

- **Status**: accepted
- **Date**: 2026-10-19
- **Deciders**: fix-issue-310-guard-realpath（issue #310）

## Context

`CommandGuard` 在构造时把 workspace 存成 `Path(workspace).resolve()`（realpath），但判定命令
目标时只做 `os.path.normpath`（纯词法）。workspace 经符号链接表示时两侧永远对不上：工作区
内部的 `rm` 被误判为越界（`rm_target_escape`），写白名单也因算不出 workspace 相对路径而
同向误拒。该缺陷与操作系统无关（macOS `/tmp` 只是默认触发入口）。

同时，`os.path.normpath` 在解析符号链接**之前**折叠 `..`，与 POSIX 路径解析语义不同：
`<ws>/escape/../victim`（`escape → <outside>`）会被词法折叠成 `<ws>/victim`，从而放行真实
越界目标。修法必须避免这个陷阱，并保证 fail-closed（不得引入任何真实越界放行）。

## Decision

工作区包含判定对**POSIX 绝对路径**使用单一 realpath 规范表示：

1. 绝对路径（`/` 开头）**直接** `Path(path).resolve()`，不做 `os.path.normpath` 前置；
   `..` 在符号链接解析后折叠。
2. 解析 **strict-first**：先 `resolve(strict=True)`；仅 `FileNotFoundError`（目标尚不存在）
   回退 `resolve(strict=False)`；循环/权限等 `OSError`、`RuntimeError` 返回 `None`，
   调用方显式 fail-closed。
3. 相对路径只做 `os.path.normpath`（护栏不掌握命令 cwd，既有契约如此）。
4. 只改两个工作区比较点：`_check_rm()` 的越界/根删除判定与 `_allow_covers()` 的 workspace
   相对路径计算。`_check_rm()` 内 `_DENY_PATHS` 与特殊 token 判定保持词法；受保护路径判定
   整体不引入 realpath。
5. 继续使用 `_within()` 的路径段包含判据，不退化字面前缀。

## Alternatives Considered

| 备选方案 | 描述 | 拒绝原因 |
|----------|------|---------|
| 双表示双向命中 | workspace 同时保留词法表示与 realpath 表示；目标任一表示命中任一 workspace 表示即放行 | `escape → outside` 时目标的词法表示会命中词法 workspace，放行真实越界；若要求两种表示同时命中，则等价于 single realpath，还多维护一份状态 |
| 先 normpath 再 resolve | 绝对路径先词法折叠 `..`，再解析符号链接 | 与 POSIX 解析语义不符；实测 `<ws>/escape/../victim` 被折叠回工作区内，留下真实越界放行（grill high） |
| 只用非严格 resolve | `resolve(strict=False)` 同时覆盖「不存在」与「循环」 | Python 3.13+ 对符号链接循环返回字面路径而不抛异常（3.13/3.14 实测），循环会凭字面表示混进工作区；spec 的 fail-closed 条款不可兑现（对抗轮 ADV-01） |
| 两侧都退回词法 | 构造时也存 workspace 词法表示 | workspace 为 real、命令用 link 表示时仍然失败；且丢失既有 workspace realpath 规范化 |

## Consequences

- 正面影响：符号链接工作区内 `rm` 恢复正常 ALLOW；前缀碰撞、`..`、符号链接后 `..`、工作区
  内 escape、删根、解析失败全部 DENY；越界判定与白名单使用同一语义；无平台分支。
- 负面影响：
  - 工作区内指向外部的链接目标从 ALLOW 变 DENY，其中无尾斜杠的 `rm -rf <ws>/escape` 实际只删
    链接，属保守过度判定；
  - 白名单改按真实目标相对路径匹配（`.env → config/dev.env` 时需写 `config/dev.env`）；
  - 每个绝对目标增加 realpath 解析（目标存在时一次 strict resolve；不存在时最多两次，
    可忽略）；
  - workspace 的 realpath 本身落在受保护根（如 `→ /etc`）时，受保护路径判定仍为词法，
    该病态配置边界不因本决策改变。
- 需要的相关变更：`agent/tools/command_guard.py` 的 helper 与两个消费点、回归测试、spec delta；
  无配置/CLI 变更。

## Revisit Conditions

- [ ] 需要支持 Windows 盘符绝对路径的工作区包含判定时（当前为 POSIX-only 口径）。
- [ ] 需要区分「删除链接本身」与「跟随链接删除目标内容」的尾部斜杠语义时。
- [ ] 决定把受保护路径判定也 realpath 化时（会改变 workspace → 受保护根的行为）。
- [ ] Python 引入新的解析 API 且 `Path.resolve()` 语义再次变化时。
