# 在 Web 上实测多 Agent 编排模式（RunPattern）

> 面试讲到多 Agent 时，"我真在 web 上跑过 4 种模式"比纯讲代码更有说服力。
> 本指南基于源码核实：web 会话 `expose_subagent_tools=True`（web/session.py:288），RunPattern 工具 schema 见 subagents.py:320-354。

## 0. 前置

```bash
cd ~/code/asterwynd
cp .env.example .env   # 填 API key（OpenAI 或 Anthropic）
uv sync --extra dev
```

## 1. 启动（bypass 模式：命令免审批，试起来最顺）

```bash
uv run asterwynd web --port 8000 --mode bypass
```

浏览器打开 `http://localhost:8000`。

> 为什么 bypass？BYPASS profile `auto_approve_max_risk=HIGH`，Bash 等高风险工具自动放行不弹审批框（tool_permissions.py:161-166）。子 agent 想跑命令时不会被单槽审批卡住。
> 注意：BYPASS 会跳过审批，仅限本地安全环境试用。

## 2. 用自然语言驱动 RunPattern

RunPattern 工具参数（subagents.py:320-354）：

```
pattern: "orchestrator-worker" | "peer-review" | "hierarchical" | "bidding"
task:    给参与子 agent 的目标
params:  workers/teams/proposers 数量、max_rounds、worker_max_tokens、worker_max_time_s
```

### ① orchestrator-worker（扇出并行）

> 用 orchestrator-worker 模式，开 3 个 worker，让他们各自分析这个项目里有哪些测试没有覆盖到，汇总给我

### ② peer-review（迭代批判）

> 用 peer-review 模式，让 producer 写一份 README 的改进方案，reviewer 审到通过为止，max_rounds 3

### ③ hierarchical（嵌套 manager）

> 用 hierarchical 模式，开 2 个 manager 子团队，分别审查 agent/loop.py 和 agent/memory/ 的代码质量，manager 可以自己再派 worker

### ④ bidding（独立方案 + 评选）

> 用 bidding 模式，3 个 proposer 各自给一个方案：怎么优化这个项目的测试运行速度，再让 selector 选最好的

## 3. 界面上看什么

- **流式输出**：子 agent 输出、RunPattern 聚合信封逐字显示。
- **聚合信封**：模式结束返回 `{pattern, task, completed, failed, workers: [{subagent_id, status, summary, usage}], selected/selector(bidding)}` —— 每个子 agent 的完成状态和 token 消耗都可见。

## 4. 如果 agent 不主动调 RunPattern

- 直接点名工具："调用 RunPattern 工具，pattern=peer-review，task=...，params={max_rounds: 3}"
- 确认工具可见：问它"你有哪些 RunPattern 相关的工具？"——正常情况下 10 个子代理工具都在（CreateSubagent / RunSubagent / ListSubagents / GetSubagentRun / CancelSubagentRun / InspectSubagentTranscript / PublishBusMessage / ReadBus / ResumeSubagent / RunPattern）。

## 5. 常见坑

- **护栏**：并发上限 4、嵌套深度上限 3（manager.py:714），超了报错——这是设计好的保护。
- **bidding 的 selector 只看紧凑摘要**：想让 selector 看完整方案，让 proposer 把方案写文件、selector 读 artifact。
- **单槽审批**：若不用 bypass，一次只能一个 pending 审批，别同时等两个。
- **BYPASS 仅本地试用**：真实安全实践请回 build 模式 + 审批。

## 6. 面试讲法参考

试完可以这样说："我在 web 上实测过 4 种模式。orchestrator-worker 是并行扇出最快；peer-review 会迭代到 APPROVED 为止，能看到 producer 被 critique 回喂后的改进；bidding 里我故意让 proposer 把方案写文件，因为 selector 只看摘要、读 artifact 拿全文——这是 drop-oldest 会丢投标的设计取舍。预算 kill 我也触发过：给 worker 设 max_tokens 超限，能看到它先写检查点再标记 budget_exceeded，是可恢复的。"
