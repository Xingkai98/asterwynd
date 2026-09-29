# 复现脚本（issue #264）

本 change 的证据链，随 PR 归档保留。全部脚本**只读**生产代码（本 change 立项阶段未改
`agent/` 下任何 `.py`）。

运行（在 worktree 根目录；脚本自带 `_find_repo_root`，无需 `PYTHONPATH`）：

```bash
.venv/bin/python -u openspec/changes/fix-issue-264-sandbox-sink-context/repro/sandbox_sink_repro.py
.venv/bin/python -u openspec/changes/fix-issue-264-sandbox-sink-context/repro/sandbox_sink_misroute.py
.venv/bin/python -u openspec/changes/fix-issue-264-sandbox-sink-context/repro/sandbox_sink_misroute_gcwindow.py
.venv/bin/python -u openspec/changes/fix-issue-264-sandbox-sink-context/repro/design_points_probe.py
```

| 文件 | 作用 | 本机实测（Python 3.12.13） |
|------|------|------|
| `sandbox_sink_repro.py` | **形态 A**：sink 被覆盖成 `_NOOP`、后续 run 的事件静默丢失（源自 #261 归档版，仅路径自适应） | **5/5 复现**，退出码 1 |
| `sandbox_sink_misroute.py` | **形态 B**：事件串写进旧 run 的 trace（源自 #261 归档版，仅路径自适应） | **0/10**（脚本 GC 时机脆弱，见下） |
| `sandbox_sink_misroute_gcwindow.py` | **形态 B 的确定性变体**：仅比上面多一行 plant 阶段 `gc.collect()`，把遗留 task 的终结时机钉死 | **10/10 复现**；对照 `PLANT_ABANDONED=False` 3/3 无串写 |
| `design_points_probe.py` | 三个设计点取证（token 可用性 / `_NOOP` vs `None` 哨兵 / 跨上下文对照） | 结论见输出，见 `diagnosis.md` §Evidence 4 |

## 为什么形态 B 有两个脚本

`repro/sandbox_sink_misroute.py` 是 #261 的归档原版（路径适配），在本机 **0/10** 不复现；
`repro/sandbox_sink_misroute_gcwindow.py` 是它加一行 `gc.collect()` 的变体，**10/10** 复现。

差异不在生产代码，在**何时终结遗留 task**：原版在 plant 阶段 `del loop_old, root_old, mgr_old`
后仍通过 `llm.mgr` 持有旧 manager（`llm` 活到 main 结束），引用环未成垃圾，遗留 task 活到进程
尾部、**从未在 LIVE 窗口内被终结**；补一次 `gc.collect()` 即恢复确定性。

**含义**：缺陷是真的（对照组证明串写确由遗留子 run 的收尾引起），但**回归测试不得依赖
「碰巧 GC 到」**，必须显式 `gc.collect()`（见 `tasks.md` 2.1）。完整推导见 `diagnosis.md`
的 `## Reproduction` 第 2 节。

## 脚本适配记录（相对 #261 归档原版）

1. `parents[4]` → `_find_repo_root()`（向上寻找 `agent/loop.py`）。归档原版硬编码
   `parents[4]`，只在 change 处于 `openspec/changes/<id>/` 时指向仓库根，**归档后**会静默
   指向 `openspec/`（当时靠 `PYTHONPATH=.` 掩盖）。改为位置无关。
2. 标题改为 issue #264 口径。
3. 形态 B 另存确定性变体（见上）。

生产代码**未做任何修改**。
