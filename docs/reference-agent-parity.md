# Reference Agent 对标矩阵

本文档记录 Asterwynd 与参考 coding agent 的能力对标关系。它服务路线图、OpenSpec backlog、benchmark 任务设计和面试叙事，不替代具体功能的需求、设计和测试策略。

## 对标策略

Asterwynd 的主线不是逐项克隆某个产品，而是建设“可解释、可复现、可 benchmark 的本地 coding agent”。对标采用分层策略：

| 参考对象 | 角色 | 基线 | 范围 |
| --- | --- | --- | --- |
| Codex CLI | `primary_reference` | `openai/codex@cfead68e5d3984b247cf0758e3e53b19165de848`，本地核对时间 2026-06-30 | 本地 coding agent 核心路径：runtime、工具协议、shell、审批/沙箱、项目指令、配置、MCP、TUI、session/rollout、context compaction。 |
| Claude Code | `product_reference` | 官方文档，核对时间 2026-06-30 | 产品能力边界：权限、MCP、hooks、subagents、IDE/桌面/多入口体验。闭源实现不作为唯一实现依据。 |
| Aider | `specialized_reference` | 官方文档，核对时间 2026-06-30 | terminal pair programming、repo map、git diff、lint/test feedback loop。 |
| OpenCode | `specialized_reference` | 官方文档，核对时间 2026-06-30 | TUI、多 provider、项目初始化、`AGENTS.md`/项目指令体验。 |
| AtomCode | `presentation_reference` | 官网与官方文档，核对时间 2026-06-30 | 能力对比和 benchmark 指标呈现方式；不作为当前必须追齐的实现目标。 |

AtomCode 官网的主要参考价值在呈现方式：它把可用工具、权限模式、Git 会话、视觉输入、自动压缩、MCP、hook、插件等能力用用户可理解的分类展示，并在对比区强调“同模型、真实任务、平均步骤数”。Asterwynd 吸收这类表达方式，但具体能力追齐仍以 Codex CLI 为主。

## 字段与状态

能力矩阵以“Coding Agent capability”为主键，而不是以“Codex feature”为主键。这样后续可以继续加入 Gemini CLI、Amp、Cursor Agent 或内部 agent，而不需要重写文档结构。

每个能力项必须维护以下字段：

| 字段 | 说明 |
| --- | --- |
| `domain` | 能力域，例如 runtime、tool system、workspace safety、code intelligence。 |
| `reference_agent` | 参考对象和角色；可以记录多个对象，但 Codex 主参照必须排在最前。 |
| `reference_source` | 参考来源链接或本地源码路径；Codex 核心项优先链接源码。 |
| `reference_capability` | 参考对象提供的能力，按用户目标描述，不按实现类名描述。 |
| `asterwynd_status` | `supported`、`equivalent`、`partial`、`gap` 或 `out_of_scope`。 |
| `asterwynd_evidence` | Asterwynd 的规格、代码、测试、benchmark、trace 或运行证据。 |
| `gap_priority` | `P0`、`P1`、`P2`、`P3` 或 `-`。`-` 表示已支持、等价支持或不纳入当前范围。 |
| `follow_up_change` | 已有 OpenSpec change id，或 `待新增:<change-id>`，或 `-`。 |
| `last_checked` | 最近核对日期。 |

状态语义：

| 状态 | 语义 |
| --- | --- |
| `supported` | Asterwynd 已有直接能力，并有规格、代码、测试、benchmark、trace 或运行证据。 |
| `equivalent` | Asterwynd 没有同名能力，但有满足同一用户目标的等价替代，并有证据。 |
| `partial` | Asterwynd 有部分能力，但缺少关键行为、入口、验证或文档。 |
| `gap` | Asterwynd 缺少该能力，且该能力符合项目定位，应拆 OpenSpec change。 |
| `out_of_scope` | 能力不符合当前项目定位或当前投入阶段，必须写明理由。 |

## 能力矩阵

| domain | reference_agent | reference_source | reference_capability | asterwynd_status | asterwynd_evidence | gap_priority | follow_up_change | last_checked |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent runtime | Codex CLI (`primary_reference`) | Codex `codex-rs/core/src/session/mod.rs`; `codex-rs/core/src/codex_thread.rs` | 本地 session/thread runtime，接收用户输入、调用模型、处理 response item、驱动工具调用和 turn 完成事件。 | `supported` | `agent/loop.py`; `openspec/specs/agent-runtime/spec.md`; `tests/agent/test_loop.py`; benchmark task `benchmarks/tasks/asterwynd-010-agent-loop`。 | - | - | 2026-06-30 |
| tool protocol | Codex CLI (`primary_reference`) | Codex `codex-rs/core/src/function_tool.rs`; `codex-rs/core/src/session/mod.rs` | 将模型工具调用映射为内部工具 schema、执行结果和可回放 response item。 | `supported` | `agent/tools/registry.py`; `agent/tools/base.py`; `openspec/specs/tool-system/spec.md`; `tests/agent/tools/test_registry.py`; benchmark task `benchmarks/tasks/asterwynd-001-tool-registry`。 | - | - | 2026-06-30 |
| shell execution | Codex CLI (`primary_reference`); Aider (`specialized_reference`) | Codex `codex-rs/core/src/exec.rs`; Aider lint/test workflow 文档 | 使用 shell 执行测试、构建、诊断命令，并把 exit code、stdout/stderr、超时反馈给 agent。 | `supported` | `agent/tools/builtin/bash.py`; `agent/workspace_policy.py`; `tests/agent/tools/test_bash_tool_structured_output.py`; `tests/agent/tools/test_bash_tool_workspace.py`; benchmark task `benchmarks/tasks/asterwynd-005-bash-workspace`。 | - | - | 2026-06-30 |
| file editing | Codex CLI (`primary_reference`); Aider (`specialized_reference`) | Codex `codex-rs/core/src/safety.rs`; Aider git diff/edit loop 文档 | 读写文件、精确编辑、保留 diff，并避免覆盖或越权写入。 | `supported` | `agent/tools/builtin/read.py`; `agent/tools/builtin/write.py`; `agent/tools/builtin/edit.py`; `agent/tools/builtin/inspect_git_diff.py`; `openspec/specs/coding-tools/spec.md`; `tests/agent/tools/test_read_write_tools.py`; `tests/agent/tools/test_edit_tool.py`。 | - | - | 2026-06-30 |
| workspace safety | Codex CLI (`primary_reference`) | Codex `codex-rs/core/src/safety.rs`; `codex-rs/core/src/exec_policy.rs`; `codex-rs/core/src/exec.rs` | 对文件、命令、沙箱和审批做统一安全判定。 | `partial` | `agent/workspace_policy.py`; `openspec/specs/workspace-safety/spec.md`; `tests/agent/test_workspace_policy.py`; `tests/agent/tools/test_sandbox.py`。当前已有 workspace 边界、敏感路径、命令 denylist/allowlist，但缺少 Codex 风格的细粒度 approval profile、policy amendment 和统一权限元数据。 | P0 | `refine-tool-permission-model` | 2026-06-30 |
| approval policy | Codex CLI (`primary_reference`); Claude Code (`product_reference`); AtomCode (`presentation_reference`) | Codex `codex-rs/core/src/exec_policy.rs`; Claude Code 权限文档；AtomCode 权限模式展示 | 按操作风险和当前模式决定自动执行、询问用户或拒绝，并让用户理解当前权限边界。 | `partial` | `agent/run_config.py`; `agent/tools/registry.py`; `openspec/specs/agent-modes/spec.md`; `tests/agent/test_run_config.py`; `tests/agent/tools/test_plan_mode_tools.py`。当前 mode policy 可禁用工具，但还没有 capability/risk/origin/profile 维度。 | P0 | `refine-tool-permission-model` | 2026-06-30 |
| project instructions | Codex CLI (`primary_reference`); OpenCode (`specialized_reference`) | Codex `codex-rs/core/src/agents_md.rs`; `codex-rs/core/src/agents_md_manager.rs`; OpenCode `AGENTS.md` 文档 | 自动发现并注入项目指令，支持从项目根到当前目录的层级指令。 | `partial` | 当前仓库通过 `AGENTS.md` 给 agent 和 Claude Code 提供入口说明；`agent/skills/loader.py` 支持 skill prompt 注入。Asterwynd runtime 尚未内置 Codex 风格 `AGENTS.md` 层级发现、fallback 文件名、最大字节限制和 session cache。 | P1 | `待新增:add-project-instruction-discovery` | 2026-06-30 |
| configuration | Codex CLI (`primary_reference`); OpenCode (`specialized_reference`) | Codex `codex-rs/core/src/config/`; `codex-rs/config/src/`; OpenCode provider/config 文档 | 配置 provider、模型、工具、profile、sandbox、审批和项目级行为。 | `partial` | `agent/config.py`; `asterwynd.example.yaml`; `openspec/specs/configuration/spec.md`; `tests/agent/test_config.py`。Asterwynd 已有 YAML 配置、mode、web search、LSP 配置，但缺少 Codex 风格 profile、managed config/requirements、MCP server 配置和审批配置。 | P1 | `refine-tool-permission-model`; `add-mcp-tool-adapter`; `待新增:add-agent-runtime-profiles` | 2026-06-30 |
| MCP integration | Codex CLI (`primary_reference`); Claude Code (`product_reference`); AtomCode (`presentation_reference`) | Codex `codex-rs/codex-mcp/src/`; `codex-rs/core/src/mcp*.rs`; Claude Code/AtomCode MCP 文档 | 发现 MCP server，把外部 tool 暴露为 agent tool，并纳入权限、超时和 trace。 | `gap` | 已有 OpenSpec change `add-mcp-tool-adapter`；current spec `openspec/specs/mcp-integration/spec.md` 目前为空能力域，尚未有 runtime adapter。 | P1 | `add-mcp-tool-adapter` | 2026-06-30 |
| skills/plugins | Codex CLI (`primary_reference`); Claude Code (`product_reference`); OpenCode/AtomCode (`specialized_reference`) | Codex `codex-rs/cli/src/plugin_cmd.rs`; `codex-rs/codex-mcp/src/plugin_config.rs`; Claude Code/AtomCode 插件和 hook 文档 | 加载可复用能力包或插件，并把额外指令/工具接入 runtime。 | `partial` | `agent/skills/loader.py`; `openspec/specs/skills/spec.md`; `tests/agent/skills/test_loader.py`; benchmark task `benchmarks/tasks/asterwynd-007-skill-loader`。Asterwynd 有 Markdown skill loader，但还没有插件 manifest、插件 tool、hook 分发或安装命令。 | P2 | `待新增:add-plugin-manifest-and-loader` | 2026-06-30 |
| memory/context | Codex CLI (`primary_reference`); AtomCode (`presentation_reference`) | Codex `codex-rs/core/src/compact.rs`; `codex-rs/core/src/compact_remote.rs`; AtomCode automatic compaction 展示 | 自动压缩上下文，在长会话中保留系统指令、近期工具链和总结。 | `supported` | `agent/memory/manager.py`; `openspec/specs/memory-context/spec.md`; `tests/agent/memory/test_memory.py`; benchmark task `benchmarks/tasks/asterwynd-006-memory-manager`。 | - | - | 2026-06-30 |
| session history / resume | Codex CLI (`primary_reference`); AtomCode (`presentation_reference`) | Codex `codex-rs/core/src/rollout*.rs`; `codex-rs/core/src/session/rollout_reconstruction.rs`; AtomCode session/Git session 展示 | 持久化 rollout、恢复会话、重建历史和跨 session 追踪。 | `partial` | `agent/trace_recorder.py`; `web/session.py`; `tests/agent/test_trace_recorder.py`; `tests/web_tests/test_session.py`。Asterwynd 有 trace、session id、run id 和 Web session，但缺少 Codex 风格本地 rollout 持久化、resume/fork 和重建历史。 | P1 | `待新增:add-session-rollout-resume` | 2026-06-30 |
| CLI | Codex CLI (`primary_reference`); Aider/OpenCode (`specialized_reference`) | Codex `codex-rs/cli/src/main.rs`; Aider/OpenCode CLI 文档 | 从命令行启动 agent、web、benchmark，并传入 mode、provider、模型和任务配置。 | `supported` | `cli.py`; `openspec/specs/cli/spec.md`; `tests/test_cli.py`; `tests/benchmark/test_cli_benchmark.py`。 | - | - | 2026-06-30 |
| TUI | Codex CLI (`primary_reference`); OpenCode (`specialized_reference`) | Codex `codex-rs/tui/src/`; OpenCode TUI 文档 | 在 terminal 中展示对话、工具调用、审批、状态、MCP、hook 和 token 信息。 | `gap` | 已有 OpenSpec change `add-minimal-tui-runtime-view`；current spec `openspec/specs/tui/spec.md` 目前定义目标能力，runtime 入口尚未实现。 | P1 | `add-minimal-tui-runtime-view` | 2026-06-30 |
| Web UI | Claude Code (`product_reference`) | Claude Code 多入口和 IDE/desktop/web 相关文档 | 提供非终端交互入口，展示 session、run、tool result、plan 和 debug 信息。 | `equivalent` | `web/`; `openspec/specs/web-ui/spec.md`; `tests/web_tests/test_server.py`; `tests/web_tests/test_session.py`; `tests/web_tests/test_browser.py`。Asterwynd 当前用 Web UI 作为 Codex/terminal TUI 之外的等价可观测交互入口。 | - | - | 2026-06-30 |
| observability / trace | Codex CLI (`primary_reference`); AtomCode (`presentation_reference`) | Codex `codex-rs/core/src/rollout*.rs`; AtomCode 任务步骤/对比指标展示 | 记录模型响应、工具调用、结果、事件、run id、步骤数和失败原因，便于回放与诊断。 | `supported` | `agent/trace_recorder.py`; `agent/hooks/`; `tests/agent/test_trace_recorder.py`; `tests/agent/hooks/test_logging_tracing.py`; benchmark task `benchmarks/tasks/asterwynd-003-agentloop-trace`。 | - | - | 2026-06-30 |
| benchmark / eval | AtomCode (`presentation_reference`); Aider/OpenCode (`specialized_reference`); Codex CLI (`primary_reference`) | AtomCode 官网能力对比和指标展示；Claw-SWE-Bench 适配 Aider/OpenCode | 用可复现任务、hidden tests、trace、runner log、步骤数和 SWE-bench Verified harness 衡量能力。 | `supported` | `benchmarks/`; `claw-swe-bench/`; `openspec/specs/benchmark/spec.md`; `tests/benchmark/`; `docs/benchmark-plan.md`。矩阵后续引用外部指标时必须记录任务集、模型、样本量、度量口径和核对日期。 | - | - | 2026-06-30 |
| code intelligence | Aider (`specialized_reference`); Codex CLI (`primary_reference`) | Aider repo map 文档；Codex 源码中未把 LSP/repo map 作为本次主证据 | 生成 repo map、符号摘要、定义/引用/hover/诊断，辅助跨文件代码理解。 | `supported` | `agent/code_intelligence/`; `agent/lsp/`; `agent/tools/builtin/code_intelligence.py`; `agent/tools/builtin/lsp.py`; `openspec/specs/code-intelligence/spec.md`; `tests/agent/code_intelligence/`; `tests/agent/lsp/`; benchmark task `benchmarks/tasks/asterwynd-021-lsp-diagnostics`。 | - | - | 2026-06-30 |
| subagents / multi-agent | Codex CLI (`primary_reference`); Claude Code (`product_reference`) | Codex `codex-rs/core/src/session/review.rs`; `codex-rs/core/src/session/mod.rs`; Claude Code subagents 文档 | 创建受限子 agent、异步执行、查询结果，并把子 run 摘要注入父上下文。 | `supported` | `agent/subagent/manager.py`; `agent/tools/builtin/subagent.py`; `openspec/specs/subagents/spec.md`; `tests/agent/subagent/test_subagent_manager.py`; `tests/agent/subagent/test_protocol.py`; benchmark task `benchmarks/tasks/asterwynd-009-subagent-manager`。 | - | - | 2026-06-30 |
| hooks | Codex CLI (`primary_reference`); Claude Code/AtomCode (`product_reference`) | Codex hooks 配置和 TUI hooks view；Claude Code/AtomCode hooks 文档 | 在生命周期事件前后触发扩展逻辑，支持记录、审计、重试和外部集成。 | `partial` | `agent/hooks/manager.py`; `tests/agent/hooks/test_manager.py`; `tests/agent/hooks/test_retry_budget.py`; `tests/agent/hooks/test_logging_tracing.py`。当前 hooks 偏内部 Python 扩展，缺少用户配置 hook、managed hook 和 UI 可见性。 | P2 | `待新增:add-configurable-runtime-hooks` | 2026-06-30 |
| research / web tools | Codex CLI (`primary_reference`) | Codex `codex-rs/core/src/session/mod.rs` 的 `WebSearchCall` response item | 让 agent 可按需搜索和抓取网页，并把诊断返回给模型。 | `supported` | `agent/tools/builtin/web_search.py`; `agent/tools/builtin/web_fetch.py`; `openspec/specs/research-tools/spec.md`; `tests/agent/tools/test_web_research_tools.py`; `tests/agent/tools/test_search_providers.py`。 | - | - | 2026-06-30 |
| browser / computer use | Claude Code (`product_reference`) | Claude Code 产品能力边界和外部工具生态 | 通过浏览器/桌面工具执行网页任务、截图和交互。 | `gap` | 已有 OpenSpec change `add-browser-use-safety-foundation`；current spec `openspec/specs/browser-computer-use/spec.md` 定义能力域，runtime 尚未实现。 | P2 | `add-browser-use-safety-foundation` | 2026-06-30 |
| visual input / screenshots | AtomCode (`presentation_reference`); Claude Code (`product_reference`) | AtomCode image-based task examples and screenshot-oriented capability presentation | 让 agent 使用截图或图片作为任务证据。 | `out_of_scope` | 当前 Asterwynd 以本地代码仓库、CLI/Web/benchmark 和可复现文本 trace 为主；浏览器截图能力已由 `add-browser-use-safety-foundation` 承载，通用视觉输入不纳入本阶段。 | - | - | 2026-06-30 |
| IDE / desktop integration | Claude Code (`product_reference`) | Claude Code IDE/desktop 相关文档 | 深度接入 IDE、桌面 App、账号和云协作。 | `out_of_scope` | `docs/project-positioning.md` 将 Asterwynd 定位为本地、可解释、可复现、可 benchmark 的 coding agent；当前阶段以 CLI/Web/benchmark/TUI 为主要入口。 | - | - | 2026-06-30 |

## 缺口到 OpenSpec 的映射

| 优先级 | 能力缺口 | 当前处理 |
| --- | --- | --- |
| P0 | 细粒度权限模型、审批策略、tool capability/risk/origin 元数据 | 已有 `refine-tool-permission-model`，作为后续 MCP/browser/custom tool 前置。 |
| P1 | MCP adapter | 已有 `add-mcp-tool-adapter`。 |
| P1 | TUI runtime view | 已有 `add-minimal-tui-runtime-view`。 |
| P1 | Codex 风格项目指令发现 | 待新增 `add-project-instruction-discovery`。 |
| P1 | session rollout/resume/fork | 待新增 `add-session-rollout-resume`。 |
| P1 | runtime profiles / managed requirements | 待新增 `add-agent-runtime-profiles`，可与权限模型和配置改造合并评估，但不应混入 runtime 实现。 |
| P2 | browser/computer use 安全基础 | 已有 `add-browser-use-safety-foundation`。 |
| P2 | plugin manifest / plugin tool / install flow | 待新增 `add-plugin-manifest-and-loader`。 |
| P2 | configurable runtime hooks | 待新增 `add-configurable-runtime-hooks`。 |

## 实现级深挖队列

本节只定义后续 deep dive 的归属和产出物，不在本文档内展开完整实现设计。每个 deep dive 进入对应 OpenSpec change 后，仍必须按 `AGENTS.md` 的设计追问要求审视 `design.md`，再进入实现。

| 顺序 | 主题 | 归属 change | Codex 源码入口 | Asterwynd 对照入口 | deep dive 产出物 |
| --- | --- | --- | --- | --- | --- |
| 1 | 权限、审批、沙箱和 tool risk metadata | `refine-tool-permission-model` | `codex-rs/core/src/exec_policy.rs`; `codex-rs/core/src/safety.rs`; `codex-rs/core/src/exec.rs`; `codex-rs/core/src/config/` | `agent/run_config.py`; `agent/workspace_policy.py`; `agent/tools/registry.py`; `agent/tools/base.py`; `openspec/specs/tool-system/spec.md`; `openspec/specs/workspace-safety/spec.md` | 权限术语对照表、mode/profile 状态机、tool metadata schema、兼容迁移策略、测试和 benchmark smoke 清单。 |
| 2 | Codex 风格项目指令发现和注入 | `待新增:add-project-instruction-discovery` | `codex-rs/core/src/agents_md.rs`; `codex-rs/core/src/agents_md_manager.rs`; `codex-rs/core/src/context/user_instructions.rs` | `AGENTS.md`; `CLAUDE.md`; `agent/skills/loader.py`; `agent/loop.py`; `docs/requirements-process.md` | root marker 策略、层级文件收集规则、fallback 文件名、大小限制、session cache、prompt 注入格式和回归测试。 |
| 3 | session rollout、resume 和 history reconstruction | `待新增:add-session-rollout-resume` | `codex-rs/core/src/rollout*.rs`; `codex-rs/core/src/session/rollout_reconstruction.rs`; `codex-rs/core/src/codex_thread.rs`; `codex-rs/core/src/session/session.rs` | `agent/trace_recorder.py`; `agent/loop.py`; `web/session.py`; `benchmarks/agent_runner.py`; `openspec/specs/agent-runtime/spec.md` | 持久化 artifact schema、resume/fork 语义、history rebuild 规则、trace/benchmark 兼容策略和失败恢复测试。 |
| 4 | MCP server 配置、tool discovery 和权限接入 | `add-mcp-tool-adapter` | `codex-rs/codex-mcp/src/`; `codex-rs/core/src/mcp*.rs`; `codex-rs/config/src/mcp_types*.rs`; `codex-rs/core/src/session/mcp*.rs` | `openspec/changes/add-mcp-tool-adapter/`; `agent/tools/registry.py`; `agent/config.py`; `openspec/specs/mcp-integration/spec.md` | MCP 配置模型、fake server 测试、schema 映射、超时和错误语义、权限 metadata 接入点、trace 事件。 |
| 5 | TUI runtime event model 和状态展示 | `add-minimal-tui-runtime-view` | `codex-rs/tui/src/`; `codex-rs/tui/src/chatwidget/`; `codex-rs/tui/src/bottom_pane/`; `codex-rs/core/src/session/mod.rs` | `web/session.py`; `web/debug_hook.py`; `agent/trace_recorder.py`; `openspec/changes/add-minimal-tui-runtime-view/`; `openspec/specs/tui/spec.md` | 运行事件字典、终端布局最小范围、approval/tool/planning/streaming 展示规则、非交互降级和快照测试。 |
| 6 | config profiles、managed requirements 和 strict config | `待新增:add-agent-runtime-profiles` | `codex-rs/core/src/config/`; `codex-rs/config/src/`; `codex-rs/config/src/config_loader_tests.rs` | `agent/config.py`; `asterwynd.example.yaml`; `openspec/specs/configuration/spec.md`; `tests/agent/test_config.py` | 配置层级和优先级、profile 选择、managed/locked 字段范围、requirements 检查点和配置迁移测试。 |
| 7 | plugin、hook 和 skill 的用户可配置化 | `待新增:add-plugin-manifest-and-loader`; `待新增:add-configurable-runtime-hooks` | `codex-rs/cli/src/plugin_cmd.rs`; `codex-rs/codex-mcp/src/plugin_config.rs`; `codex-rs/core/src/config/` hooks 相关路径；`codex-rs/tui/src/bottom_pane/` hooks view | `agent/skills/loader.py`; `agent/hooks/manager.py`; `skills/`; `openspec/specs/skills/spec.md`; `tests/agent/hooks/`; `tests/agent/skills/test_loader.py` | manifest schema、安装/发现路径、hook lifecycle、权限边界、UI/trace 可见性和插件隔离策略。 |
| 8 | benchmark 对比指标呈现 | `待新增:add-reference-agent-benchmark-reporting` | AtomCode 官网指标展示；Claw-SWE-Bench agent adapters；Codex/Aider/OpenCode CLI 文档 | `benchmarks/`; `claw-swe-bench/`; `docs/benchmark-plan.md`; `openspec/specs/benchmark/spec.md` | 同模型/同任务口径、样本量和任务集记录、平均步骤数/工具调用数/耗时字段、结果表和 HTML/Markdown 报告格式。 |

## 维护规则

- Codex 核心路径能力项优先使用源码证据；如果本地参考仓库更新，需要同时更新 commit、核对日期和受影响条目。
- `supported` 和 `equivalent` 必须链接 Asterwynd 证据；没有证据时只能标为 `partial`、`gap` 或 `out_of_scope`。
- `gap` 和重要 `partial` 不允许直接在本文档承诺实现；必须链接已有 OpenSpec change 或记录 `待新增:<change-id>`。
- 后续加入新的 reference agent 时，只追加 baseline 行和能力矩阵来源，不改变状态枚举和证据规则。
- 外部性能或能力指标不得只摘结论；必须记录任务集、模型、样本量、度量口径、来源和最后核对日期。
- 影响 AgentLoop、工具协议、workspace safety、coding tools、benchmark runner 的后续 runtime change，必须在 tasks 中包含测试和 benchmark smoke，或记录明确不适用原因。
