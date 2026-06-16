# P2 跨 Agent 基准对比——详细实现计划

**日期**: 2026-06-16
**状态**: 设计阶段

---

## 1. 目标

在同一套 benchmark 任务上用 MyAgent、Claude Code、Codex 分别评测，产出对比报告。回答核心问题：MyAgent 的 pass rate 瓶颈在框架还是在模型？

## 2. 适配器架构

所有外部 agent 实现 `AgentRunner.run()` 接口，通过 subprocess 在工作区中调用 CLI：

```
BenchmarkRunner
  ├── MyAgentRunner（已有）
  ├── ClaudeCodeRunner（新增）
  └── CodexRunner（延后）
```

统一执行流程：

```
1. 创建 worktree（runner 统一处理）
2. 隐藏 benchmark/tasks（runner 统一处理）
3. subprocess 调用 agent CLI，等待完成或超时
4. 捕获 final diff（runner 统一处理）
5. 应用 test.patch、跑测试（runner 统一处理）
6. 写入结果
```

## 3. 核心参数统一

| 参数 | MyAgent | Claude Code | 说明 |
|------|---------|-------------|------|
| 时间限制 | 600s timeout | 600s timeout | 纯 wall-clock，统一 |
| 轮次限制 | 无（靠 timeout） | 无（不传 --max-turns） | — |
| 工作目录 | worktree root | subprocess cwd=worktree | Claude 无 --cd 参数 |
| 权限 | 无需确认 | `--dangerously-skip-permissions` | worktree 隔离，可销毁 |
| Prompt | `CodingPromptBuilder`（MyAgent 专属） | `issue.md` 原文 | 各用各自 prompt |
| 模型 | DeepSeek v4 | DeepSeek（`ANTHROPIC_BASE_URL` + `--model`） | 同模型对比框架差距 |

## 4. Claude Code 适配器细节

```python
class ClaudeCodeRunner(AgentRunner):
    def __init__(self, timeout_seconds: int = 600):
        self.timeout_seconds = timeout_seconds

    async def run(self, task, problem_statement, workspace, output_dir, trace):
        prompt = f"""You are working in a code repository. Complete the following task:

{problem_statement}

Verification command (run this before finishing):
{task.test_command}
"""
        cmd = [
            "claude", "-p",
            "--model", "deepseek-chat",
            "--dangerously-skip-permissions",
            "--output-format", "text",
            prompt,
        ]
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = "https://api.deepseek.com/anthropic"
        # ANTHROPIC_API_KEY 继承当前环境

        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True, text=True,
            timeout=self.timeout_seconds,
            env=env,
        )
        return AgentRunResult(...)
```

## 5. 对比报告格式

`summary.md` 扩展为多列对比表：

```markdown
| Task | MyAgent | Claude Code |
|------|---------|-------------|
| myagent-001-tool-registry | passed (21s, 11iters) | passed (18s) |
| myagent-002-sandbox-executor | failed (test_failure) | passed (45s) |
| ... | ... | ... |

**Summary**
| Agent | Passed | Failed | Error | Pass Rate |
|-------|--------|--------|-------|-----------|
| MyAgent | 11 | 12 | 0 | 48% |
| Claude Code | ? | ? | ? | ? |
```

## 6. 可收集 vs 不可收集

| 可收集 | 不可收集 |
|--------|---------|
| 最终 git diff（runner 统一抓） | 每一轮的 tool call 轨迹 |
| stdout/stderr 日志 | 内部 token 消耗、迭代数 |
| test 结果（exit_code, output） | 内部工具调用详情 |
| 总耗时 | — |

对标 SWE-bench 评测模型——**看结果不看过程**。

## 7. 安全风险

- Agent 在 `/tmp` 下 isolated worktree 中运行
- 没有容器隔离，agent 理论上可以 `rm -rf /home/happy/...`（同用户权限文件）
- MyAgent benchmark 已经跑了 4 轮，没出现过危险命令执行
- P2 阶段不引入 Docker，风险可控。长期方案：对标 Codex 的 kernel-level sandbox

## 8. Codex 延后原因

- Codex 需要 `codex login` 预配置认证
- 自定义 API 端点（`OPENAI_BASE_URL`）没有明显支持
- 先搞 Claude Code 对比，Codex 后续补充

## 9. 实现步骤

1. `ClaudeCodeRunner` 类（~40 行）
2. Benchmark CLI 加 `--agent claude` 选项
3. `summary.md` 扩展为多列对比
4. 契约测试（fake agent 模式验证 adapter 接口）
5. 真实 benchmark 跑一轮，产出对比数据
