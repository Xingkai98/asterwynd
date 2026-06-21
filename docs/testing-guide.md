# 测试指南

本文档记录 MyAgent 的测试分层和回归测试要求。

## 基本原则

- 每个 bug fix 必须新增回归测试。
- 测试应该证明行为，而不是只覆盖实现细节。
- 涉及共享协议的变更必须覆盖协议不变量。
- real API 测试保持可选，不作为默认 CI 前置条件。

## 回归测试规则

当修复 bug 时：

1. 先定位根因。
2. 写出能复现问题的测试。
3. 修复实现。
4. 确认新测试和相关测试通过。

测试文件优先放在对应子系统下：

```text
tests/agent/<subsystem>/test_<component>.py
```

示例：

```text
agent/tools/builtin/edit.py
tests/agent/tools/test_edit_tool.py
```

## 测试分层

### 单元测试

覆盖确定性逻辑，不依赖真实 LLM 和网络。

重点模块：

- WorkspacePolicy
- ToolRegistry
- EditTool / BashTool / ListFiles / Find
- TraceRecorder
- Message / Result
- provider message serialization

### 集成测试

覆盖多个模块协作。

重点场景：

- EditTool + WorkspacePolicy + InspectGitDiff
- BashTool 执行本地测试并返回结构化输出
- AgentLoop 工具调用链
- Memory compact 后保持 tool-call 协议合法
- Web session 消息历史
- Benchmark runner artifact 写入

### Web 测试

Web 测试覆盖 server、session 和浏览器行为。

常用命令：

```bash
uv run pytest tests/web_tests/test_session.py tests/web_tests/test_server.py -q
```

浏览器测试需要 Playwright：

```bash
playwright install chromium
MYAGENT_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

### Benchmark 测试

Benchmark 测试要和模型质量解耦，优先使用 fake agent 和临时 git 仓库。

常用命令：

```bash
uv run pytest tests/benchmark -q
uv run python cli.py benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke
```

涉及 AgentLoop、coding tools、workspace safety、benchmark runner 或其他 coding-agent 核心路径的变更，除了相关单元/集成测试外，至少跑通一个 benchmark smoke。优先选择能验证真实 runner 闭环的任务；如果改动影响外部 SWE-bench 风格任务，至少单独跑一个 `swebench-*` 任务。

外部 SWE-bench 风格任务依赖 `swebench` 包；当前未作为默认 dev 依赖固定时，可在本地环境临时安装：

```bash
uv pip install swebench
```

单任务 SWE smoke 示例：

```bash
rm -rf /tmp/myagent-one-swe-task /tmp/myagent-swe-smoke
mkdir -p /tmp/myagent-one-swe-task
ln -s "$PWD/benchmarks/tasks/swebench-psf__requests-5414" \
  /tmp/myagent-one-swe-task/swebench-psf__requests-5414
uv run python cli.py benchmark /tmp/myagent-one-swe-task \
  --agent shell \
  --shell-command "git apply $PWD/benchmarks/tasks/swebench-psf__requests-5414/gold.patch" \
  --source-repo . \
  --runs-dir /tmp/myagent-swe-smoke \
  --clone-cache-dir /tmp/myagent-swe-cache
```

## 必须守住的协议

- assistant message 如果包含 `tool_calls`，必须保留匹配的 tool result。
- `max_iterations` 不能把最后一个 tool result 包装成 assistant 最终回复。
- 最终 assistant 回复需要进入消息历史，避免多轮对话复读。
- Memory compact 不能破坏 tool-call / tool-result 相邻链。
- `passed_with_warnings` 是测试通过但过程不干净，不能算 clean pass。

## 覆盖率目标

后续需要建立明确覆盖率门槛。初始建议：

- 核心 agent、工具、workspace policy、benchmark runner 保持高覆盖。
- CLI 和 Web 需要覆盖主要用户路径。
- 新增功能必须有单元测试；涉及跨模块行为时补集成测试。
