## Context

本次讨论的核心问题是：Asterwynd 应该对标哪个当前 coding agent，并保证对方具备的关键能力在 Asterwynd 中有对应实现、等价替代或明确不做的理由。

公开资料显示，Codex CLI 是 OpenAI 的本地运行 coding agent，代码开源，适合作为主实现参照；Claude Code 的公开文档将其描述为能读代码库、编辑文件、运行命令并集成开发工具的 agentic coding tool，适合作产品能力上限参照；Aider 强调 terminal pair programming、codebase map、git/lint/test workflow，适合作 code intelligence 和编辑闭环参照；OpenCode 强调 terminal agent、TUI、provider 配置和项目初始化生成 `AGENTS.md`，适合作终端体验和多入口参照。

Asterwynd 的项目定位不是复刻某个商业产品，而是建设“可解释、可复现、可 benchmark 的本地 coding agent”。因此对标产物必须服务能力证明链，而不是变成无边界功能清单。

## Goals / Non-Goals

**Goals:**

- 建立一份可维护的 reference-agent parity matrix。
- 明确 Codex CLI 为主对标对象，Claude Code、Aider、OpenCode 为辅参照。
- 为每个能力项记录参考来源、Asterwynd 状态、等价能力、证据、缺口等级和后续 change。
- 规定 runtime 缺口必须拆成独立 OpenSpec change，不允许直接在矩阵中承诺“已支持”。
- 让矩阵能服务路线图、backlog 排序、benchmark 任务设计和面试叙事。

**Non-Goals:**

- 不在本 change 中实现 Codex、Claude Code、Aider 或 OpenCode 的具体能力缺口。
- 不要求 Asterwynd 逐 UI、逐命令、逐配置项克隆任何一个参考产品。
- 不把闭源产品的非公开实现细节写成 Asterwynd 的实现依据。
- 不把商业生态能力，例如云端协作、计费、账号体系、IDE marketplace，纳入当前必须补齐范围。

## Decisions

### Decision 1: Codex CLI 作为主对标对象

Codex CLI 与 Asterwynd 的形态最接近：本地运行、面向代码仓库、通过工具读写文件和执行命令，并有项目指令、安全/审批和配置能力。它开源，适合进行实现层调研和能力拆解。

矩阵中 Codex 相关能力应优先标为 `primary_reference`，除非某项能力明显不是 Asterwynd 当前项目定位需要覆盖的范围。

### Decision 2: Claude Code 只作为产品能力上限参照

Claude Code 能帮助识别成熟 coding agent 的产品能力边界，例如多入口、权限、MCP、hooks、subagents、IDE/desktop/web 集成等。但它不是完整开源实现，不能作为 Asterwynd 实现细节的唯一依据。

矩阵中 Claude Code 相关能力应标为 `product_reference`，主要用于判断能力价值和用户预期。

### Decision 3: Aider 和 OpenCode 作为专项辅参照

Aider 的 repo map、git workflow、lint/test feedback 与 Asterwynd 的 code intelligence、coding tools、benchmark 闭环高度相关。OpenCode 的 TUI、多 provider、`AGENTS.md` 初始化和 terminal workflow 与 Asterwynd 的 TUI、configuration、skills、CLI 方向相关。

矩阵中 Aider 和 OpenCode 相关能力应标为 `specialized_reference`，只在对应专题上提升权重。

### Decision 4: 对标矩阵使用证据优先状态

每个能力项必须使用以下状态之一：

- `supported`: Asterwynd 已有直接能力，并有规格、代码、测试或 benchmark 证据。
- `equivalent`: Asterwynd 没有同名能力，但有满足同一用户目标的等价替代，并有证据。
- `partial`: Asterwynd 有部分能力，但缺少关键行为、入口、验证或文档。
- `gap`: Asterwynd 缺少该能力，且该能力符合项目定位，应拆 OpenSpec change。
- `out_of_scope`: 能力不符合当前项目定位或投入阶段，必须写明理由。

没有证据的能力项不得标为 `supported` 或 `equivalent`。

### Decision 5: 矩阵只负责发现和排序，不负责实现

矩阵发现的 `gap` 或重要 `partial` 项必须链接到已有 OpenSpec change，或新增独立 change。矩阵不得把多个 runtime 缺口塞进同一个大 change。

理由：保持需求边界清晰，也避免“对标”变成无限扩张。

## Risks / Trade-offs

- [Risk] 对标范围过大，导致路线图发散。Mitigation: Codex 作为主对标，其他项目只做专项补充；每项必须给出 `out_of_scope` 选项。
- [Risk] 只按功能名称对标，忽略 Asterwynd 的可解释和 benchmark 差异化。Mitigation: 矩阵状态必须绑定证据和能力证明链。
- [Risk] 参考产品快速变化，矩阵过期。Mitigation: 每个能力项记录 `last_checked` 和来源链接，后续定期更新。
- [Risk] 对标矩阵被误用为实现许可。Mitigation: runtime 缺口必须拆分 OpenSpec change，并通过 `grill-with-docs` 或等价设计追问后才能实现。

## Testing Strategy

- 文档验证：运行 OpenSpec strict validate 和项目 OpenSpec artifact checker。
- 矩阵结构验证：人工检查首版矩阵中每个能力项都包含参考对象、来源链接、Asterwynd 状态、证据或后续 change。
- OpenSpec 追踪验证：抽查 `gap` 和重要 `partial` 项，确认它们链接到 backlog 中已有或待新增的 change。
- Benchmark 映射验证：对涉及 AgentLoop、工具协议、coding tools、workspace safety、benchmark runner 等核心路径的能力项，确认后续 runtime change 会包含 benchmark smoke 或说明不适用原因。
