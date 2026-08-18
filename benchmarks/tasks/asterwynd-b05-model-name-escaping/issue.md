# SWE-bench 验证：模型名含 `/` 时报告目录找不到

SWE-bench 外部评测走一个验证适配器：agent 的 patch 被写成 predictions 行（含 `model_name_or_path`），随后调用官方 harness 在 Docker 里跑评测，评测结果落在按模型名命名的报告目录下。

**症状**：当 `--model` 含 `/`（如 `claude/claude-fable-5[1m]`）时，评测命令本身正常结束，但验证返回「Missing SWE-bench report: ...」——报告目录找不到。模型名不含 `/` 时一切正常。

**根因方向**：报告目录按模型名生成。模型名经过拼接后形如 `asterwynd:claude/claude-fable-5[1m]`，而 harness 生成报告目录时会把模型名里的 `/` 归一化为 `__`。验证侧在构造报告目录查找路径时**必须做同样的归一化**，否则 `/` 使目录层级错位、路径永远找不到。当前代码漏了这一步。

## Task

定位验证适配器里报告目录查找路径的构造处，修复模型名转义：

- 模型名 `claude/claude-fable-5[1m]` → 拼接后 `asterwynd:claude/claude-fable-5[1m]` → 报告目录名必须是 `asterwynd:claude__claude-fable-5[1m]`（`/` → `__`，与 harness 命名一致）
- 把归一化逻辑提取为可单测的命名辅助（不要内联在路径表达式里），并应用到报告目录查找路径
- 保持其余行为不变：无 `/` 的模型名目录名不受影响

## Requirements

- 拼接后含 `/` 的模型名，其报告目录名把所有 `/` 归一化为 `__`
- 归一化逻辑可通过单元测试直接调用（不依赖 Docker）
- 既有适配器契约测试不得回归
