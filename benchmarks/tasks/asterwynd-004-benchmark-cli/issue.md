# benchmark CLI 入口增强：--list-tasks 列出任务集

`agent/main.py` 的 `benchmark` 命令是当前 benchmark CLI 入口，支持 `--agent`（fake/shell/asterwynd/claude）、`--repeat N` 聚合、`--parallel` 等参数。它缺少一个只读的「列出任务集」模式：想确认某个 tasks 目录被正确识别、包含哪些任务时，只能真跑一遍 benchmark。

## Task

给 `benchmark` 命令新增 `--list-tasks` 开关：不运行任何 runner，只扫描 `TASKS_DIR` 下带 `task.json` 的任务子目录，输出任务总数与每个任务 id，然后直接返回。

- `--list-tasks` 置位时 SHALL NOT 触发 `_build_benchmark_runner`（不产生 run、不消耗 LLM）
- 输出格式：首行 `Tasks: <N>`，随后每个任务一行 `  <task_id>`
- 某个任务加载失败（缺字段/文件不存在）时输出 `Error: failed to load <name>: <原因>` 到 stderr 并跳过，不影响其余任务列出

## Requirements

- `asterwynd benchmark --list-tasks <tasks_dir>` 输出任务总数与每个任务 id，退出码 0
- `--list-tasks` 模式下不得调用 runner（用 monkeypatch 断言 `_build_benchmark_runner` 不被调用）
- 不带 `--list-tasks` 时行为完全不变（向后兼容）
