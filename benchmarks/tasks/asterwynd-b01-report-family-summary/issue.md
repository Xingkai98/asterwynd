# benchmark 结果页按 task_family 分组摘要

`benchmarks/report.py` 的评测结果页目前有「By Capability Layer」（按能力层聚合）和「By Task」两张表。前者按 `category` 归一化后的能力层聚合，后者逐任务展示（每行含 `task_family` 列）。结果页**缺少按 task_family（评测框架：`local`/`swebench`）的分组聚合视图**——混跑本地任务与 SWE-bench 子集后，无法一眼看出哪个框架族整体表现如何。

## Task

给 `benchmarks/report.py` 的 `_render` 增加「By Task Family」聚合块：按 `TaskAggregate.task_family` 分组，每族展示任务数与 `Pass@k`（全部轮次通过率）。放在「By Capability Layer」块之后、「By Task」表之前。

- 分族聚合时复用 `aggregate_results` 已产出的 `task_family`（含 `_infer_task_family` 的 id 前缀推断）
- 通过率用 `pass_at_k(sum(passes), total)`，保持与其他块一致的统计口径
- 输出为 markdown 表：`| Family | Tasks | Pass@k |`，按 family 名排序
- 无任务族时（空 aggregates）不渲染该块

## Requirements

- 结果页含 `## By Task Family` 块
- `swebench` 族 1 任务 1 通过 → `| swebench | 1 | 1.00 |`；`local` 族 1 任务 0 通过 → `| local | 1 | 0.00 |`
- 既有结果页渲染测试不得回归
