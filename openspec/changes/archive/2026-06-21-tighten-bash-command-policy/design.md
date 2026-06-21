## Context

WorkspacePolicy 当前通过 `_match_allowlist()` 和 `DEFAULT_DENYLIST` 控制 BashTool 命令执行。但 `assert_command_allowed()` 先检查 allowlist，命中后直接返回，导致 denylist 无法覆盖宽泛 allowlist 前缀。

典型风险：

- `python -c "..."` 命中 `python` 前缀后被允许。
- `cp /etc/passwd ./passwd.copy` 命中 `cp` 前缀后被允许。
- `mv .env backup.env` 命中 `mv` 前缀后被允许。

## Goals / Non-Goals

**Goals:**

- denylist SHALL 优先于 allowlist。
- 常见验证命令仍可执行。
- 高风险宽泛前缀必须收紧。
- 回归测试覆盖当前已知绕过路径。

**Non-Goals:**

- 不实现完整 shell parser。
- 不引入容器级沙箱。
- 不设计交互式命令审批。
- 不改变 BashTool 的结构化 JSON 输出格式。
- 不改变 Read/Grep 的路径策略。

## Decisions

### Decision 1: denylist 优先

`assert_command_allowed()` SHALL 先检查 denylist，再检查 allowlist。只要命中 denylist，无论是否命中 allowlist，都拒绝。

理由：

- denylist 表达的是高危模式，应覆盖宽泛 allowlist。
- 当前测试里 `git reset --hard` 已表达这个期望，但实现依赖于 allowlist 恰好没覆盖 `git reset`，不够稳。

### Decision 2: 收窄 allowlist 而不是继续扩大 denylist

高风险前缀如 `python`、`python3`、`cp`、`mv` 不应作为无条件安全前缀。初始策略：

- 允许 `python -m pytest`、`python3 -m pytest` 等验证命令。
- 允许 `uv run pytest`、`uv run python -m pytest`。
- 对 `cp`、`mv` 这类文件操作，默认不作为 Bash allowlist 前缀；agent 应使用 Write/Edit 等工具修改文件。

理由：

- 单靠 denylist 无法穷尽脚本执行和文件搬运风险。
- Coding agent 已有专用文件工具，Bash 不需要承担任意文件修改能力。

### Decision 3: 保留开发验证路径

必须保留项目常用验证命令：

- `pytest`
- `uv run pytest`
- `python -m pytest`
- `python3 -m pytest`
- `git status`、`git diff`、`git log`、`git show`
- `rg`、`grep`、`cat`、`ls` 等只读查看命令

理由：

- BashTool 的核心价值之一是运行测试和检查状态。
- 收紧策略不能破坏本项目常规验证闭环。

## Risks / Trade-offs

- [Risk] 某些原本通过 Bash 执行的合法脚本被拒绝。  
  Mitigation: 优先引导使用专用工具；确需允许时通过后续 change 明确命令模式。

- [Risk] 纯字符串策略仍可能被 shell 语法绕过。  
  Mitigation: 本 change 先修复已知高风险短路和宽泛前缀；完整 parser 或沙箱隔离另立 change。

- [Risk] 过度收紧影响 benchmark 或测试运行。  
  Mitigation: 跑相关 Bash/benchmark 测试和至少一个 benchmark smoke。

