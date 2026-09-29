# 复现脚本（issue #261）

这些脚本是本 diagnosis 的证据载体，随 change 归档保留，供实现期改写为回归测试。

| 文件 | 作用 | 期望 |
|------|------|------|
| `min_repro_261.py` | 最小确定性复现（纯 contextvar + Task 生命周期，不依赖生产类） | 打印 `>>> REPRODUCED`，退出码 1 |
| `min_repro_fix_check.py` | 对照：分别用现状 `set(previous)` 与方案 A `reset(token)` 跑同一最小脚本 | `CURRENT` polluted=True；`FIXED` polluted=False |
| `realpath_ab.py` | 真实 `AgentLoop`/`SubAgentManager`/`WorkflowScheduler` 的确定性复现 | 现状 `bw` 冻结为 `build`（REPRODUCED）；应用方案 A 后为 `read_only`（CLEAN） |
| `carrier_stack.py` | 捕获遗留 run 的 `finally` 执行栈，证明其由**活跃上下文里的 `gc.collect()`** 触发 | 栈里出现 `events.py:84 _run` → `gc.collect` |

运行（在 worktree 根目录）：

```bash
.venv/bin/python -u openspec/changes/fix-issue-261-mode-ceiling-flake/repro/min_repro_261.py
.venv/bin/python -u openspec/changes/fix-issue-261-mode-ceiling-flake/repro/min_repro_fix_check.py CURRENT
.venv/bin/python -u openspec/changes/fix-issue-261-mode-ceiling-flake/repro/min_repro_fix_check.py FIXED
```

注：`realpath_ab.py` 用 `.venv` 的 Python（3.11）跑；它只在 `agent/loop.py` 为**现状**
实现时复现，应用方案 A 后转绿——这正是变异验证的依据。
