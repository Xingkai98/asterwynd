# 测试指南

本文档记录 Asterwynd 的测试分层和回归测试要求。

## 基本原则

- 每个 bug fix 必须新增回归测试。
- 测试应该证明行为，而不是只覆盖实现细节。
- 涉及共享协议的变更必须覆盖协议不变量。
- real API 测试保持可选，不作为默认 CI 前置条件。
- CLI、Web 和未来 TUI 的入口 smoke 优先使用共享 `ScriptedLLM` fake harness，只替换 LLM provider，不替换真实 AgentLoop。
- **本地文件 I/O 一律显式声明编码**，平台相关行为必须有平台无关的复现手段（见下节）。

## 平台与编码纪律

**规则一：本地文件 I/O 一律显式声明编码。**

`open()` / `Path.read_text()` / `Path.write_text()` 不写 `encoding=` 时会按**进程 locale** 编解码。本仓的数据一律是 UTF-8，因此在非 UTF-8 locale（Windows 中文机器 = GBK/cp936）上：

- 写含 emoji/生僻字的会话 → `UnicodeEncodeError` → **保存静默失败**（实测：磁盘上只剩 `.tmp`）；
- 读 UTF-8 文件 → `UnicodeDecodeError` → 单个坏文件曾让 `GET /api/sessions` **整个 500**。

```python
path.read_text(encoding="utf-8")                    # 我们自己的数据
path.read_text(encoding="utf-8", errors="replace")  # 用户/第三方内容（不许把「能读」变成崩溃）
```

**子进程是例外，且方向相反**：`subprocess.run(..., text=True)` 的输出编码是**子进程自己的契约**——我们自己的 python CLI 在 Windows 上往管道写的是 locale 编码，父进程若强行按严格 UTF-8 解码反而会崩（实测把 `tests/test_flow_policy.py` 的 `show.stdout` 变成 `None`，一次改动新增 11 条红）。所以只在**确定跨平台输出 UTF-8** 的子进程上写 `encoding="utf-8"`（本仓即 node harness），其余保持交给 locale。

**规则二：这类缺陷不许再靠人眼评审拦。** 仓库有一条机械守卫
`tests/web_tests/test_encoding_hygiene.py`（AST 扫描 `agent/ web/ benchmarks/ scripts/ tests/`），
命中「缺 `encoding=` 的 `open`/`read_text`/`write_text`」与「跑 node harness 的 `text=True`
子进程缺 `encoding=`」即失败。例外必须写进该文件的 `ALLOWLIST` 并给出理由——**白名单可评审，
静默放行不行**。

**规则三：平台信号必须进 CI，不许当环境噪声容忍。**

历史教训：这套缺陷在 CI 上**结构性不可见**（原本两个 job 都是 `ubuntu-latest`，locale 即 UTF-8），
而本机 Windows 的红灯被长期归类为「环境性失败」，两者叠加 = 零防护（积压到 47 条）。

| 信号面 | 手段 | 覆盖 |
|---|---|---|
| 非 UTF-8 locale | `validate` job 的 C-locale 步骤（`LC_ALL=C` + `PYTHONCOERCECLOCALE=0` + `PYTHONUTF8=0`） | 编解码类：会话持久化、列表容错 |
| 平台语义 | `windows-platform` job（`windows-latest`，跑平台敏感子集） | Windows 路径语义（敏感根、`~` 展开）、GBK 解码、前端工具行 |

**本机 Windows 出现红灯时**：MUST 修掉，或写进守卫的 `ALLOWLIST`/用 `skipif` 并说明「平台前提不成立」
（例如「路径大小写不敏感」在 Windows 上无法成立）；SHALL NOT 以「pristine 同样失败」为由长期挂账。

写平台相关行为测试时的三条经验：

- **用平台上真实存在的绝对路径**：`/etc` 在 Windows 上**不是绝对路径**（缺盘符），断言会落到
  `workspace_must_be_absolute` 而不是预期的错误码；`~` 展开在 POSIX 读 `HOME`、在 Windows 读
  `USERPROFILE`/`HOMEDRIVE`+`HOMEPATH`；NUL 字节用例要用 `tmp_path` 拼绝对路径。
- **造「脏数据」时载荷必须真的非 UTF-8**：`json.dumps({...}).encode("gbk")` 在载荷全为 ASCII 时
  产出的仍是合法 UTF-8，用例会**恒真/恒假**（本仓踩过一次：断言恒失败，等于没覆盖）。
- **在 Linux 上复现非 UTF-8 locale**：把断言放进子进程，用 `LC_ALL=C PYTHONCOERCECLOCALE=0
  PYTHONUTF8=0` 跑（ASCII locale 比 GBK 更严格）；再用 `PYTHONWARNDEFAULTENCODING=1`
  （PEP 597）断言**没有** `EncodingWarning`——「用了默认编码」从此是运行时可观测信号。

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
- EditTool / BashTool / ListFiles / Find / RepoMap / SymbolSearch
- WebSearch / WebFetch 的 fake provider、fake transport、错误诊断和截断逻辑
- TraceRecorder
- Message / Result
- provider message serialization

### 集成测试

覆盖多个模块协作。

重点场景：

- EditTool + WorkspacePolicy + InspectGitDiff
- BashTool 执行本地测试并返回结构化输出
- AgentLoop 工具调用链
- Tool permission metadata、ModePolicy 三值判定和 require_approval fail-closed 行为
- Memory compact 后保持 tool-call 协议合法
- CLI slash command registry 的命令解析、未知命令拦截、上下文清理、手动 compact、`/skills` reload 和 skill command 触发 Agent run
- MCP adapter 的 fake stdio / Streamable HTTP server discovery、tool 调用、prompt/resource 读取、mode policy 拦截和 slash command 注入
- CLI 入口 smoke 应至少覆盖真实 `build_agent` + `ScriptedLLM` 的普通回复、streaming 去重和工具调用摘要；旧 `FakeAgent` 测试只能作为 adapter 层补充。
- Skill runtime 的多 root 加载、诊断、重复名称处理、index 注入、匹配注入和 `ActivateSkill` 工具激活
- Web session 消息历史
- Web session 的 session id / run id / session mode、Plan Document、planning state 事件、工具结果 display metadata、approval request/response 和 skill command 执行
- Benchmark runner artifact 写入

### Web 测试

Web 测试覆盖 server、session 和浏览器行为。

重点覆盖：

- server/session/browser 测试默认复用 `tests/support/llm_harness.py` 中的 `ScriptedLLM`，覆盖普通回复、streaming、tool call、错误和调用记录。
- Chat 页面 assistant Markdown 渲染，包括列表、代码块、链接，以及 raw HTML / unsafe link 的转义或阻断。
- 工具结果展示策略，包括长结果折叠、preview、字符/行数元数据，以及工具结果不走 Markdown/HTML 注入。
- session id、run id、session mode、Plan Document、planning state、approval request/response 和 Debug 开关的前端可见行为。

常用命令：

```bash
uv run pytest tests/web_tests/test_session.py tests/web_tests/test_server.py -q
```

浏览器测试需要 Playwright：

```bash
playwright install chromium
uv run pytest tests/web_tests/test_browser.py -q
ASTERWYND_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

默认浏览器 smoke 使用 fake LLM 测试专用 Web server，不要求 API key；真实 API 浏览器 E2E 仍然必须显式传入 `--run-real-api`。

### 共享 LLM 测试 Harness

共享 fake LLM 位于 `tests/support/llm_harness.py`。新增 CLI、Web、未来 TUI 或 benchmark 入口回归时，优先复用 `ScriptedLLM`：

- 使用顺序脚本响应表达普通文本、streaming delta、tool call 和 provider-like error。
- 使用 `call_count`、`calls`、`last_messages` 和 `messages_seen` 断言入口层传给 LLM 的消息、工具和 model。
- 首版 harness 不做 prompt hash 匹配、record/replay 或真实响应录制；这些能力可作为后续扩展单独设计。
- fake 入口 smoke 不应 monkeypatch 整个 AgentLoop；只有 adapter 层测试才保留私有 fake agent。

未来 TUI 实现时，至少新增一个基于 `ScriptedLLM` 的入口 smoke，证明 TUI 输入、runtime event 消费和屏幕状态展示接入真实 AgentLoop。

### Benchmark 测试

Benchmark 测试要和模型质量解耦，优先使用 fake agent 和临时 git 仓库。

常用命令：

```bash
uv run pytest tests/benchmark -q
uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke
```

涉及 AgentLoop、coding tools、workspace safety、benchmark runner 或其他 coding-agent 核心路径的变更，除了相关单元/集成测试外，至少跑通一个 benchmark smoke。优先选择能验证真实 runner 闭环的任务；如果改动影响外部 SWE-bench 风格任务，至少单独跑一个 `swebench-*` 任务。

外部 SWE-bench 风格任务依赖 Docker daemon 和 `swebench` 包；默认 `uv sync --extra dev` 会一并安装。Docker 不可用时，这类任务应返回 `unsupported`，而不是误记为 agent 失败。

单任务 SWE smoke 示例：

```bash
rm -rf /tmp/asterwynd-one-swe-task /tmp/asterwynd-swe-smoke
mkdir -p /tmp/asterwynd-one-swe-task
ln -s "$PWD/benchmarks/tasks/swebench-psf__requests-5414" \
  /tmp/asterwynd-one-swe-task/swebench-psf__requests-5414
uv run asterwynd benchmark /tmp/asterwynd-one-swe-task \
  --agent shell \
  --shell-command "git apply $PWD/benchmarks/tasks/swebench-psf__requests-5414/gold.patch" \
  --source-repo . \
  --runs-dir /tmp/asterwynd-swe-smoke \
  --clone-cache-dir /tmp/asterwynd-swe-cache
```

如果当前开发环境是没有 `systemd` 的容器，可先用辅助脚本启动 Docker daemon：

```bash
sudo ./scripts/start-docker-daemon.sh
```

Claw-SWE-Bench 集成使用独立 harness，不通过 `asterwynd benchmark`。如果改动影响 `claw-swe-bench/`，在环境具备 Docker 镜像和 API key 时至少跑一个单实例 smoke：

```bash
cd claw-swe-bench
uv run python run_infer.py \
  --claw asterwynd \
  --dataset verified \
  --instance_ids psf__requests-1142 \
  --run_id asterwynd-claw-smoke \
  --model deepseek-v4-pro \
  --timeout 600
```

## 必须守住的协议

- assistant message 如果包含 `tool_calls`，必须保留匹配的 tool result。
- `max_iterations` 不能把最后一个 tool result 包装成 assistant 最终回复。
- 最终 assistant 回复需要进入消息历史，避免多轮对话复读。
- Memory compact 不能破坏 tool-call / tool-result 相邻链。
- CLI/Web 独立 slash command 属于命令输入；未知 slash command、`/clear`、`/compact`、`/skills` 和 `/mcp` 系列命令不能作为普通用户消息发送给 AgentLoop/LLM。`kind=prompt` 的 skill command 必须只把命令参数作为用户消息启动 Agent run，并在 run 前激活对应 skill。`/mcp-prompt` 和 `/mcp-resource` 读取结果必须以带来源标记的 system context 注入，并保留 metadata。
- `passed_with_warnings` 是测试通过但过程不干净，不能算 clean pass。
- benchmark 结果分类读 `status`，具体细节读 `reason`；`unsupported` 不能并入 `failed`。
- Web Chat 的 assistant streaming 必须通过 AgentLoop `assistant_delta` / `assistant_stream_complete` 事件进入 WebSocket 和 CLI；回归测试必须覆盖流式展示不重复最终 `llm_response`，不能只改前端展示。

## 覆盖率目标

后续需要建立明确覆盖率门槛。初始建议：

- 核心 agent、工具、workspace policy、benchmark runner 保持高覆盖。
- CLI 和 Web 需要覆盖主要用户路径。
- 新增功能必须有单元测试；涉及跨模块行为时补集成测试。
