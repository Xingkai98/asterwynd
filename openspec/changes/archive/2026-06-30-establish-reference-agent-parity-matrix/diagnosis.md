## Symptom

Asterwynd 已有较多 coding-agent 基础能力，但缺少一份稳定的外部对标矩阵。当前路线图能说明项目方向，却不能逐项回答：

- 主流 coding agent 已经具备哪些关键能力？
- Asterwynd 哪些能力已经等价覆盖？
- 哪些缺口值得做，哪些不符合当前定位？
- 每个能力的证据在哪里，是否有测试或 benchmark 支撑？

这会削弱项目的能力证明链，也会让后续需求排序依赖临时判断。

## Reproduction

围绕“用哪个 coding agent 做对标”进行资料核对：

- Codex CLI README 将其定位为 OpenAI 的本地运行 coding agent，并提供开源仓库和安装方式。
- Claude Code overview 文档描述其能读取代码库、编辑文件、运行命令，并集成 terminal、IDE、desktop 和 browser 等入口。
- Aider README 将其定位为 terminal AI pair programming，并强调 codebase map、git、lint/test 等能力。
- OpenCode 文档强调 terminal agent、provider 配置、项目初始化和生成 `AGENTS.md`。

将这些能力与 Asterwynd 当前项目定位和 `docs/coding-agent-roadmap.md` 对比后，可以看到：Asterwynd 不是缺一个单点实现，而是缺一套把外部能力映射到自身规格、实现、测试、benchmark 和面试叙事的机制。

## Evidence

- Asterwynd `CONTEXT.md` 明确项目主线是 Coding Agent 系统，关注 Agent 运行时、工具调用、上下文管理、代码修改、验证、可观测性和 benchmark 闭环。
- `docs/project-positioning.md` 要求重要功能能回答面试价值、代码位置、测试位置、benchmark 或运行证据。
- `docs/coding-agent-roadmap.md` 已说明目标不是逐功能克隆 Claude Code 或 Codex，而是做更小但可解释、可复现、可 benchmark 的 coding agent runtime。
- Codex CLI 公开仓库说明其是本地运行的 coding agent，适合作主对标对象。
- Claude Code 公开文档适合判断成熟产品能力边界，但不能提供完整开源实现细节。
- Aider 和 OpenCode 在专项能力上与 Asterwynd 后续路线有交集，但不适合作单一主对标对象。

## Root Cause

根因不是 Asterwynd 当前缺少某一个功能，而是缺少“参考能力 -> Asterwynd 等价能力 -> 证据 -> 缺口 change -> benchmark 验证”的稳定链路。

如果没有这条链路，后续容易出现两类问题：

- 看见参考产品的新能力就直接开发，导致范围发散。
- 已有能力没有证据归档，面试和路线图中难以证明等价性。

## Recommended Direction

建立 `establish-reference-agent-parity-matrix` change，先交付对标矩阵和维护规则：

- Codex CLI 作为主对标对象。
- Claude Code 作为产品能力上限参照。
- Aider 作为 code intelligence、repo map 和编辑闭环专项参照。
- OpenCode 作为 TUI、多 provider、`AGENTS.md` 初始化和 terminal workflow 专项参照。
- 每个能力项必须记录状态、证据、缺口等级和后续 OpenSpec change。
- 对 runtime 能力缺口，后续必须拆独立 change 并补测试/benchmark 证据。

## Regression Tests

本 change 主要修改文档和流程，不直接修改 runtime 行为。验证重点是防止后续对标工作退化成无证据功能清单：

- OpenSpec artifact checker 应通过，确保 research change 包含 diagnosis，process change 包含 design。
- 首版对标矩阵应人工抽查，确认每个 `supported` / `equivalent` 项都有证据。
- 每个 `gap` / 重要 `partial` 项应链接到已有或待新增 OpenSpec change。
- 后续涉及核心 runtime 的缺口 change 必须包含相关测试和 benchmark smoke。
