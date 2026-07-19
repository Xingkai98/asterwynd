# Harbor 框架接入可行性分析与方案

**日期**: 2026-07-19
**状态**: 草案
**分支**: `analyze-harbor-integration/2026-07-19`

---

## 1. Harbor 框架概述

[Harbor](https://github.com/harbor-framework/harbor) 是 Laude Institute（Terminal-Bench 团队）开发的 coding agent 评测框架。它是一个标准化、可扩展的 agent benchmark 运行环境，已被 Google Android Bench、Terminal-Bench 2.0/3.0、GraphicDesignBench 等主流评测体系采用。

### 1.1 核心架构

```
┌────────────────────────────────────────────┐
│                Harbor CLI                   │
│  harbor run    harbor adapter    harbor job │
└──────────────────┬─────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│  Job   │  │  Agent   │  │ Sandbox  │
│ Config │  │ Adapter  │  │ Env      │
└────────┘  └──────────┘  └──────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
                 Docker      Daytona       Modal
                 (local)     (cloud)     (serverless)
```

### 1.2 关键组件

| 组件 | 说明 |
|------|------|
| **Job / Trial** | 一次评测运行单位；`JobConfig` + `TrialConfig` Pydantic schema |
| **Agent Adapter** | `BaseAgent` / `BaseInstalledAgent` — 定义 agent 如何安装、运行、采集结果 |
| **Environment** | `BaseEnvironment` — Docker/Daytona/E2B/Modal 等 sandbox 后端的统一抽象 |
| **Task** | `task.toml` + `instruction.md` + Dockerfile + test.sh — 标准化任务格式 |
| **Adapter** | 将外部 benchmark 转为 Harbor task 格式的转换器 |
| **Verifier** | test.sh 驱动，产出 `{"pass": 1, "tests_passed": N}` 等 reward JSON |
| **ATIF** | Agent Trajectory Interchange Format (v1.7) — 轨迹、token、cost 的标准化格式 |

### 1.3 已支持 Agent（50+）

Harbor 内置对 Claude Code、Codex、Aider、OpenHands、OpenCode、SWE-agent、Gemini CLI、Cline、Roo Code、Amazon Q、Cursor CLI 等 50+ coding agent 的 adapter。Agent 只需实现：

```python
class MyAgent(BaseInstalledAgent):
    @staticmethod
    def name() -> str: ...
    def get_version_command(self) -> str | None: ...
    async def install(self, environment: BaseEnvironment) -> None: ...
    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None: ...
    def populate_context_post_run(self, context: AgentContext) -> None: ...
```

### 1.4 Task 格式

```
<task-id>/
  task.toml            # 任务元数据和配置
  instruction.md       # Agent 看到的任务指令
  environment/
    Dockerfile         # 沙箱环境定义
  solution/
    solve.sh           # Oracle 解（用于 parity 验证）
  tests/
    test.sh            # 验证/评分脚本
```

### 1.5 运行方式

```bash
# 安装
pip install harbor
# 或
uv tool install harbor

# 运行已注册 agent
harbor run --agent claude-code --task-dir ./tasks/my-task

# 运行自定义 agent
harbor run --agent-import-path my_package:MyAgentClass --task-dir ./tasks/my-task

# 大规模并行评测
harbor job run --config job.yaml
```

---

## 2. Asterwynd 现有 Benchmark 架构

### 2.1 已有能力

| 维度 | 现状 |
|------|------|
| **任务格式** | `task.json` (TaskSpec) + `issue.md` |
| **任务数量** | 34 本地任务 + 9 SWE-bench 外部任务 |
| **Sandbox** | git worktree (本地) / Docker (SWE-bench) |
| **Agent 适配** | `AgentRunner` ABC，4 个实现 (FakeAgent/ShellCommand/ClaudeCode/Asterwynd) |
| **评分** | test_command exit code + passed_with_warnings |
| **结果格式** | `TaskResult` + `RunMetadata` → `result.json` + `summary.md` |
| **轨迹** | `TraceRecorder` → `trace.json`，结构化 step 记录 |
| **跨 agent 对比** | `compare.py` 生成 MD + HTML 对比报告 |
| **SWE-bench** | `swebench.harness.run_evaluation` Docker 评测 |

### 2.2 与 Harbor 的差异

| 维度 | Asterwynd 当前 | Harbor 标准 | 差距 |
|------|---------------|------------|------|
| **任务格式** | 自定义 `task.json` | `task.toml` 标准 | 需转换 |
| **Sandbox** | git worktree 为主 | Docker/Daytona 等 | Harbor 更通用 |
| **Agent 接口** | `async run(task, workspace, output_dir, trace)` | `install() + run(instruction, environment, context)` | 需适配 |
| **评分** | test_command exit code | verifier reward JSON | Harbor 更灵活 |
| **轨迹** | 自定义 JSON | ATIF 标准 (1.7) | 需映射 |
| **可观测性** | `run.json` + `summary.md` | Opik 集成，ATIF tracing | Harbor 更完整 |
| **生态** | 自建本地 runner | 50+ agents, 多种 sandbox backend | Harbor 生态成熟 |

---

## 3. 可行性分析

### 3.1 结论：可行，推荐分两阶段接入

Harbor 的 agent adapter 接口和 Asterwynd 现有 CLI 命令行模式可以对接。核心工作分两条路径：

- **路径 A（Agent 接入）**：为 Harbor 写一个 `AsterwyndAgent(BaseInstalledAgent)`，让 Asterwynd 作为被评测 agent 运行在 Harbor 的 sandbox 中
- **路径 B（Task 接入）**：为 Harbor 写一个 Asterwynd task adapter，将 Asterwynd 现有的本地 benchmark 任务转为 Harbor 格式

### 3.2 路径 A：Agent 接入（低风险，优先推荐）

**核心思路**：利用 Asterwynd 已有的 headless 模式（`uv run asterwynd run "..."`）和 benchmark CLI（`uv run asterwynd benchmark`），封装为 Harbor agent adapter。

**技术路径**：

```
Harbor sandbox (Docker)
  └── AsterwyndAgent (BaseInstalledAgent)
        ├── install(): pip install asterwynd (或 uv tool install)
        ├── run(): 调用 asterwynd headless solver
        └── populate_context_post_run(): 解析 trace.json → ATIF
```

**关键问题与解决方案**：

| 问题 | 方案 |
|------|------|
| Asterwynd 如何 headless 运行 | `asterwynd run "<instruction>"` CLI 已有；需确认支持自定义 API endpoint/env |
| LLM API key 注入 | Harbor 的 `_env` 属性注入 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` 等 |
| Sandbox 环境 | Harbor 的 Dockerfile 中安装 Python + Asterwynd 依赖 |
| 轨迹转换 | `trace.json` → ATIF 格式的转换器（约 200 行） |
| 超时控制 | Harbor TrialConfig.timeout_seconds 覆盖 |

**示例 Dockerfile**：

```dockerfile
FROM python:3.12-slim
RUN pip install uv
# Asterwynd 依赖由 Harbor 的 install() 步骤处理
```

**示例 Agent Adapter 骨架**：

```python
from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

class AsterwyndAgent(BaseInstalledAgent):
    @staticmethod
    def name() -> str:
        return "asterwynd"

    def get_version_command(self) -> str | None:
        return "asterwynd --version"

    async def install(self, environment: BaseEnvironment) -> None:
        await self.exec_as_agent(
            environment,
            command="uv tool install asterwynd"
        )

    @with_prompt_template
    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None:
        await self.exec_as_agent(
            environment,
            command=f"asterwynd run {shlex.quote(instruction)}"
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        # 解析 /logs/agent/trace.json → ATIF trajectory
        ...
```

### 3.3 路径 B：Task Adapter（中风险，锦上添花）

**核心思路**：用 `harbor adapter init` 创建 Asterwynd task adapter，将 `benchmarks/tasks/` 下的 34 个本地任务转为 Harbor 标准格式。

**需要处理**：

| 问题 | 方案 |
|------|------|
| task.json → task.toml 映射 | 编写转换脚本，字段映射表（见下方） |
| git worktree → Docker sandbox | 每个 task 生成 Dockerfile，checkout base_commit |
| test_command → test.sh | 包装 shell 命令为 test.sh |
| gold.patch → solve.sh | 包装 `git apply gold.patch` |
| 隐藏 test.patch | Harbor 已有 solution/ 和 tests/ 分离机制 |

**字段映射**：

| Asterwynd (task.json) | Harbor (task.toml) |
|----------------------|-------------------|
| `id` | `name` |
| `problem_statement_file` → `issue.md` | `instruction_path = "instruction.md"` |
| `timeout_seconds` | `timeout_seconds` |
| `test_command` | 写入 `tests/test.sh` |
| `base_commit` | 写入 `environment/Dockerfile` 的 checkout 步骤 |
| `category`, `difficulty` | `tags = ["category:xxx", "difficulty:xxx"]` |

### 3.4 综合收益

| 收益 | 说明 |
|------|------|
| **对标 50+ agents** | 接入 Harbor 即可与 Claude Code、Codex、Aider、OpenHands 等同一 benchmark 直接对比 |
| **标准化评分** | 统一 verifier、ATIF 轨迹、Opik 可观测性 |
| **多 sandbox 后端** | 一次适配即可跑在 Docker、Daytona、Modal、E2B 等环境 |
| **社区权威性** | Harbor 已被 Google Android Bench、Terminal-Bench 采用，结果更有说服力 |
| **RL 训练支持** | Harbor 的 rollout 格式可直接用于 TRL 等 RL 框架做 post-training |
| **复用现有任务** | 34 个本地任务可转为 Harbor 格式，也可直接跑 Harbor 生态的任务 |

---

## 4. 推荐实施计划

### Phase 1：Agent 接入（预估 3-5 天）

目标：Asterwynd 能在 Harbor 中作为 agent 被评测

1. **编写 AsterwyndAgent adapter**
   - 实现 `BaseInstalledAgent` 四个方法
   - 编写 `environment/Dockerfile`（Python 3.12 + uv + Asterwynd deps）
   - 处理 API key 注入和模型配置
2. **headless 模式验证**
   - 确认 `asterwynd run "<prompt>"` 在容器中可正常运行
   - 支持通过环境变量配置 provider/model
3. **轨迹映射**
   - 编写 `trace.json` → ATIF 转换器
   - 提取 token 用量、tool call 序列、最终 diff
4. **冒烟测试**
   - 用 Harbor 内置简单 task 跑 Asterwynd
   - 验证评分和轨迹输出正确

### Phase 2：Task 适配（预估 2-3 天）

目标：Asterwynd 的本地 benchmark 任务可在 Harbor 中运行

1. **编写 task adapter（`harbor adapter init`）**
   - task.json 解析 + task.toml 生成
   - 为 git worktree 任务生成 Dockerfile（checkout base_commit）
   - issue.md → instruction.md 直接复制或转换
2. **parity 实验**
   - 在 Asterwynd 本地 runner 和 Harbor runner 上跑相同任务
   - 验证评分一致性
3. **集成 SWE-bench 任务**
   - 9 个已有 SWE-bench 任务转为 Harbor 格式或直接复用 Harbor multi-swe-bench adapter

### Phase 3：CI 集成与持续对比（预估 1-2 天）

目标：Asterwynd 每次变更自动在 Harbor 上跑 benchmark

1. **编写 Harbor job config**：选择 Terminal-Bench 子集 + Asterwynd 本地任务
2. **CI 脚本**：`harbor run` → 解析结果 → 生成对比报告
3. **结果归档**：存储到 `benchmarks/runs/harbor/<date>/`

---

## 5. 风险与注意事项

| 风险 | 等级 | 缓解 |
|------|------|------|
| Asterwynd headless 模式在容器中不稳定 | 中 | 先在本地 Docker 验证，必要时新增 `--headless` flag |
| 现有 task 依赖 git worktree | 低 | 路径 B 转换为 Dockerfile + `git checkout` |
| API 费用 | 中 | Harbor 支持 dry-run，优先用轻量 task 验证 |
| Harbor 版本 API 变化 | 低 | 锁定 Harbor 版本，参考 50+ 已有 adapter 的更新模式 |
| Agent 依赖仓库非公开 | 高 | Asterwynd 开源前，adapter 需要 CLI 模式或 API 模式 |

---

## 6. 待确认问题

1. **Asterwynd 以什么形态被 Harbor 调用？**
   - [ ] CLI headless（`asterwynd run "..."`) — 最直接
   - [ ] Python SDK（直接 import asterwynd） — 更灵活但需要适配
   - [ ] API server（HTTP endpoint） — 适合 remote sandbox

2. **目标 benchmark 优先级？**
   - [ ] Terminal-Bench 2.0（89 tasks，software engineering + biology + security + gaming）
   - [ ] 仅 Asterwynd 本地 34 个任务
   - [ ] 两者都跑

3. **LLM backend 策略？**
   - [ ] 共用 Harbor 环境变量注入的 API key
   - [ ] Asterwynd 自己的 config 文件挂载
   - [ ] 支持多 provider 切换

---

## 7. 参考资料

- [Harbor Framework GitHub](https://github.com/harbor-framework/harbor)
- [Harbor PyPI (v0.15.0)](https://pypi.org/project/harbor/0.15.0/)
- [Harbor Adapters 开发指南](https://github.com/harbor-framework/harbor/blob/main/docs/content/docs/datasets/adapters.mdx)
- [ATIF Trajectory Spec (RFC 0001)](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md)
- [Google Android Bench + Harbor](https://android-developers.googleblog.com/2026/07/android-bench-llm-measurement.html)
- [Opik + Harbor 集成](https://www.comet.com/docs/opik/integrations/harbor)
- [Asterwynd Benchmark Plan](./benchmark-plan.md)
