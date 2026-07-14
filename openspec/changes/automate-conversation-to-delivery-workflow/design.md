## Context

当前仓库已经具备 `agent/workflow/` 五阶段状态机、`handoff.json`、phase checker 和 Agent session 持久化，但这些能力从 OpenSpec change 创建后才生效，且命令脚本可以绕过领域状态机直接修改 JSON。闲聊探索、需求收敛、worktree 创建、人工 gate 和跨 worktree 恢复没有统一控制平面。

本设计将开发流程编排从 AgentLoop 中分离。Workflow Control Plane 是独立 bounded context，Asterwynd、Codex、Claude Code 和人工只作为 executor/client 接入。当前 `AGENTS.md` 保持不变，作为迁移期安全网与验收基线；控制平面稳定后再将长流程规则替换为短接入说明。

约束：

- V1 本地优先、单机运行，不依赖云端服务或常驻 daemon。
- 闲聊探索和需求定义不创建分支或 worktree。
- 需求 gate 获得可信人工批准后，进入设计前自动创建专属分支和 worktree。
- 设计、开发、修复和 closing 复用同一个 worktree，合入后清理。
- 人和 agent 均不得依赖聊天历史推断当前状态。
- Agent 不能直接推进状态或产生可信人工批准。
- 控制面核心不得依赖 `agent/`，以支持其他 executor。
- V1 支持 CLI Host Wrapper 强入口和 `skill + AGENTS.md` 轻量兼容入口；后者不侵入 Happy Coder 等宿主客户端，但必须明确降级为软约束。

## Goals / Non-Goals

**Goals:**

- 管理 `exploring → requirements → design → building → code-review → closing → done` 全生命周期。
- 在每个 agent run 前恢复并返回权威 `WorkItem`，包含当前状态、指定 workspace、允许操作、所需证据和下一步。
- 通过 append-only event log、版本检查和事件重放拒绝非法跳步与不一致历史。
- 在 gate 到达后 fail closed，直到可信用户客户端提交绑定当前状态版本的批准或拒绝事件。
- 自动管理 change worktree、branch、lease、漂移检测和 merge 后清理。
- 从主仓库统一发现 requirements 中的事项和 sibling worktree 中的 active workflows。
- 为 Agent、CLI、Web/TUI 和 CI 提供同一领域协议。
- 允许把项目流程定义为模板，并最终生成简短的 `AGENTS.md` 接入说明和可复用 workflow skill。

**Non-Goals:**

- V1 不提供跨机器同步、多人远程协作或托管 workflow 服务。
- V1 不以完整 Web/TUI 为交付前提，先提供 CLI 和 Python API。
- 不把自然语言聊天全文复制进 workflow event store；只保存结构化状态、决策摘要、artifact 引用和证据。
- 不让控制平面判断需求或设计在语义上必然正确；它只验证流程、来源、证据和批准是否合法。
- 不在本 change 中立即删除当前 `AGENTS.md` 流程章节或兼容脚本。
- 不要求所有 executor 共享同一种内部 session 格式。

## Decisions

### D0: Managed Workspace Root 是零 Token 激活门禁

Workflow Control Plane SHALL 维护显式 `managed_roots` 路径列表。Host adapter 在构造模型上下文前对当前 cwd 执行纯本地判定：canonicalize path、识别 Git common dir，并检查是否属于某个 Managed Workspace Root 或其已登记 worktree。

未命中时，当前 session 进入 sticky `Workflow Bypass`：不创建 workflow、不读取 event store、不注入 workflow prompt、不调用 LLM 做意图分类。旁路结果在整个 session 内固定，即使进程 cwd 后续变化也不自动启用 workflow；用户必须新建 session，或通过显式 `workflow attach <managed-root>` 建立新的受管 session binding。

该设计选择显式 allowlist，而不是自动扫描所有 Git 仓库或让模型判断是否启用，原因是用户希望只在指定项目中承担流程开销，并保证未受管路径零 token 成本。

### D0.1: 受管 Session 自动创建轻量 Exploration Workflow

受管 session 启动时，如果没有显式恢复目标且项目不存在唯一可自动恢复的 workflow，控制面 SHALL 创建轻量 Exploration Workflow。它记录 session binding、当前探索状态和后续结构化 Workflow Output，不要求 branch、worktree 或 OpenSpec change。

Exploration 使用可配置 aging policy，默认 TTL 为 24 小时。只有同时满足以下条件才自动产生 `workflow_abandoned` 事件：

- 当前 phase 仍为 `exploring`。
- 未记录任何 Workflow Output。
- 自最后一次 workflow activity 起超过 TTL。

普通聊天消息数量不算 Workflow Output。Agent 通过 report 只能创建 `draft` 或 `proposed` output，这些状态不阻止 aging。Output 只有在被 approved requirements/phase gate snapshot 引用，或用户请求保留后通过 retain mini-gate 输入严格 `ok`，才产生 `workflow_output_accepted` 并变为 durable。进入 `requirements` 后停止应用 empty-exploration aging policy。

V1 不运行 aging daemon。`workflow chat`、`status`、`enter` 和 `manage` 在主操作前执行 lazy aging scan；若扫描时发现 exploration 已超过 TTL，则当场追加 abandon event。TTL 表示“下一次控制面调用时，超过该时长即老化”，不保证墙钟时间到点立即执行。

### D1: 独立 bounded context，Agent 作为 executor

新增 `workflow_control/`，建议模块边界：

```text
workflow_control/
  domain/
  event_store/
  orchestrator/
  gates/
  worktrees/
  executors/
  clients/
  templates/
  cli/
```

依赖方向 SHALL 为 executor adapter 依赖 `workflow_control` 协议，控制面核心不得导入 `agent/`。Asterwynd adapter 可以位于 `workflow_control/executors/asterwynd.py` 或集成层，但不能把 AgentLoop 类型泄漏进 domain。

选择该方案而不是扩展 AgentLoop，是因为开发流程编排跨越 agent session、human gate、Git worktree、OpenSpec 和 CI，其生命周期高于单次 agent run。架构决策记录于 `docs/adr/ADR-0001-independent-local-workflow-control-plane.md`。

V1 提供两种接入形态：

- CLI Host Wrapper：`workflow chat --executor <adapter>`。Wrapper 在启动或调用 Codex、Asterwynd、Claude Code 等 executor 前完成 managed-root 判定、workflow binding、user-message capture、Gate Approval Token 匹配和 WorkItem 生成。它是 V1 唯一可以声明可信 gate 与强执行边界的自然语言入口。
- Prompt Adapter：通过可复用 skill 和短版 `AGENTS.md` 接入说明，让 Codex、Claude、Happy Coder 等现有客户端在每个 run 前调用 `workflow enter`，结束时调用 `workflow report`，必要时展示 `workflow status`。它不侵入宿主客户端、不拦截用户消息，也不持有 approval capability；因此只能提供软约束、状态恢复和审计提示，不能宣称等同 Host Wrapper。

直接启动原生 agent CLI 或 Happy Coder session 可以使用 Prompt Adapter 降级接入。控制面应在输出中明确 enforcement level，例如 `strict_host`、`prompt_adapter` 或 `audit_only`，避免把提示词遵从误报为机械强制。

### D2: V1 使用本地 CLI/library 与项目外 SQLite

V1 提供 Python API 和 `workflow` CLI，不启动常驻 daemon。SQLite 数据库存放在用户数据目录下的项目隔离路径，例如：

```text
~/.asterwynd/workflows/<repo-id>/workflow.sqlite3
```

`repo-id` 由 canonical repository root 与 git common dir 的稳定指纹派生，使主仓库和 sibling worktree 解析到同一 registry。数据库不进入 Git，不污染主仓库，也不会随 worktree 删除而丢失。

用户级配置 SHALL 保存 `managed_roots`，并通过 `workflow manage add/remove/list` 维护。路径记录使用 canonical root；手工列出的 worktree path 不作为独立项目 root，而由 Git common dir 归属到对应受管项目。

SQLite 使用事务、外键、WAL 和 workflow version CAS 处理多 session 并发。若将来需要实时订阅或远程审批，可在领域 API 外增加 daemon，不改变核心事件协议。

### D3: Append-only events 是权威，snapshot 是派生缓存

每个 workflow 由不可变事件序列派生当前状态。核心事件至少包括：

- `workflow_started`
- `workflow_output_recorded`
- `workflow_output_proposed`
- `workflow_output_accepted`
- `workflow_abandoned`
- `requirements_updated`
- `requirements_snapshot_approved`
- `transition_requested`
- `transition_accepted` / `transition_rejected`
- `gate_reached`
- `gate_approved` / `gate_rejected`
- `worktree_created` / `worktree_rebound` / `worktree_removed`
- `work_item_claimed` / `lease_released` / `lease_expired`
- `evidence_attached`
- `workflow_blocked` / `workflow_resumed`
- `pull_request_linked` / `merge_confirmed`

每个事件包含 `workflow_id`、单调 `version`、`event_type`、`actor_kind`、`actor_id`、`session_id`、`correlation_id`、时间戳和 JSON payload。可选 hash chain 用于导出后的篡改检测，但不把 hash 当作身份认证。

Snapshot 表保存当前 phase/sub-state、gate、workspace、branch、lease、blocker 和 next action，用于快速查询；恢复和 CI 审计 SHALL 能从事件重新派生并验证 snapshot。

### D4: 两段式生命周期与需求批准时的 worktree promotion

主流程为：

```text
exploring
  → requirements
  → requirements.ready_for_review
  → [trusted human approval]
  → create branch + worktree
  → design
  → design.ready_for_review
  → building
  → building.ready_for_review
  → code-review
  → code-review.ready_for_review
  → closing
  → closing.ready_for_review
  → done
```

`exploring` 和 `requirements` 使用 canonical main workspace，默认只允许讨论、读取和控制面 artifact 草稿更新，不允许业务代码修改。需求批准后，Worktree Coordinator 原子执行：

1. 校验 main repository 与目标 branch 状态。
2. Fetch 配置的远端 base branch；可 fast-forward 时自动同步，dirty、diverged 或无法安全同步时进入 blocked。
3. 从同步后的 base commit 创建 `<change-id>/<YYYY-MM-DD>` 分支。
4. 创建专属 worktree。
5. 将已批准需求 materialize 为 OpenSpec change artifacts。
6. 写入包含 base branch/base commit 的 `workspace_bound` 事件。
7. 进入 `design` 首个 sub-state。

如果任一步失败，workflow 进入 `blocked`，不得部分推进 phase。

默认 promotion SHALL 要求 canonical main workspace 无未提交修改，且本地 base branch 与配置 remote tracking branch 一致或可安全 fast-forward。离线或远端不可用时不得静默使用旧基线；可信用户 MAY 显式批准 local-base override，事件必须记录 reason、base branch、base commit 和未完成 fetch 的事实。

Agent 在 requirements 中根据已确认标题提出 kebab-case change id，并在 gate summary 中展示 change id、预计 branch、base branch 和 base commit。用户可以在 gate approval 前自然语言修改；精确 approval token 只批准当前展示版本。批准后 change id 冻结。控制面 SHALL 检查 active/archive OpenSpec 目录、Git branch 和 worktree binding 冲突；冲突时等待明确重命名，不自动追加随机后缀。

Requirements 草稿 SHALL 仅保存在项目外 event store 中，包括结构化 goal、scope、non-goals、acceptance criteria、test strategy 和可渲染 Markdown projection。结构化字段是 gate、审计、UI 和后续 materialization 的 source of truth；Markdown 只是人读投影，可由结构化 snapshot 重新生成。该阶段不得在 canonical main repository 创建未提交 OpenSpec change。每次草稿更新形成 versioned requirements event；Gate approval 绑定并冻结一个 requirements snapshot，promotion 时只 materialize 该已批准版本。

Promotion materialization SHALL 创建需求类 artifact：`proposal.md`、对应 capability 的 spec delta，以及绑定 workflow/template/requirements snapshot 的去敏 manifest。`design.md`、ADR 和 `tasks.md` 属于 design phase，不得在 requirements approval 前伪造完成；Design executor 在绑定 worktree 中生成并推进这些 artifact。

Exploration 中当 agent 通过 report 提供 goal candidate 等最低证据时，Orchestrator MAY 自动进入 requirements，不要求用户输入流程命令。该转换不创建 worktree、可以回退，且不代表需求已批准；只有 requirements gate 的可信 approval 才触发 design promotion。

### D5: Agent 使用 `enter/report`，不能指定任意下一状态

公开领域协议：

```text
enter(repo, session, actor) -> WorkItem
report(workflow_id, state_version, result, evidence) -> ReportOutcome
status(repo) -> WorkflowSummary[]
```

`WorkItem` 至少包含：

- `workflow_id`
- `state_version`
- `phase` / `sub_state`
- `workspace_path` / `branch`
- `instructions`
- `allowed_actions`
- `required_evidence`
- `gate`
- `lease`

`WorkResult` 至少包含：

- `status`: `completed | failed | blocked | needs_input`
- `summary`
- `artifact_refs`
- `evidence`
- `blockers`

Agent 不提交自由目标状态。Orchestrator 根据当前 state、phase definition、结果与证据决定接受、拒绝、保持、回退或到达 gate。所有写请求携带 `state_version`，版本不一致时返回 stale state，要求重新 `enter`。

用户可在同一个 User Session 中通过自然语言贯穿整个 workflow。每个用户 turn 或内部执行产生新的 Executor Run；phase 变化默认只生成新的 WorkItem 并继续复用当前 Session，不意味着创建新聊天窗口或新 agent 进程。模板 MAY 为特定 phase 配置 fresh executor，但其结果仍回传到原 User Session。

### D5.1: Phase Template 配置 Executor Lane、Review Lane 和 Runner Profile

版本化 phase template SHALL 使用统一 lane 配置描述“谁执行”“谁审查”“谁批准”。`executor_lane` 描述当前 phase/sub-state 的执行者，可配置 `mode: self | runner | subagent | command | ask`；其中 `self` 表示当前 User Session/当前 executor 继续执行，适合 exploring、requirements、design 讨论和 closing 等低隔离需求；`ask` 表示 Orchestrator 返回可选 executor 列表并等待用户明确选择，选择 executor 不产生 human gate approval。`review_lane.reviewers[]` 描述 automated reviewers，只允许 `mode: runner | subagent | command`，明确禁止 `self`，且所有 agent reviewer 必须使用 `context: fresh`；inline checker 应建模为 `mode: command`，不作为独立 reviewer mode。

Runner 的具体 CLI 命令、参数、权限和 prompt 传递方式 SHALL 放在 `runner_profiles` 中，而不是硬编码到 phase 语义里。Profile 至少描述 `command`、`args`、`prompt_mode`、`permissions`、`timeout_seconds` 和可选 environment allowlist。Review profile 默认应为 read-only、`approval_policy: never`；build profile 才可声明 workspace write。任何 bypass 权限必须显式配置、进入 WorkItem/evidence/receipt，不能作为默认。

示例模板片段：

```yaml
runner_profiles:
  codex_build:
    type: codex_cli
    command: ["codex"]
    args: []
    prompt_mode: stdin
    permissions:
      filesystem: workspace_write
      network: enabled
      approval_policy: on_failure
    timeout_seconds: 3600

  codex_review:
    type: codex_cli
    command: ["codex"]
    args: []
    prompt_mode: stdin
    permissions:
      filesystem: read_only
      network: disabled
      approval_policy: never
    timeout_seconds: 900

phases:
  design:
    executor_lane:
      mode: self
      session: current
      allowed_actions: [edit_design, edit_tasks, edit_specs]
    review_lane:
      policy: all_pass
      reviewers:
        - id: spec_review
          mode: subagent
          context: fresh
          prompt_template: spec_review.md
        - id: standards_review
          mode: runner
          runner: codex_review
          context: fresh
          prompt_template: standards_review.md
    approval_gate:
      type: human
```

`approval_gate` 只能配置为 human gate 或 disabled-by-template 的显式非人工 gate；不得配置 agent、runner 或 command 自动批准 human gate。CLI Host Wrapper 可以强执行 lane 配置；Prompt Adapter 可以按配置启动 executor/reviewer，但仍不能获得 approval capability。

Asterwynd 默认模板 SHALL 在 exploring、requirements、design、building 和 closing 复用当前 executor；`code-review` 默认使用 fresh executor，以减少实现者自审偏差。Fresh reviewer 只获得审查所需的 design、diff、tests、evidence 和 workflow context，不继承实现阶段的隐藏推理；审查结果回传原 User Session。若需要修改，workflow 回到 building，并由原 executor 在同一 worktree 处理。

每个进入 human `ready_for_review` gate 的 phase MAY 配置 `review_lane.reviewers[]`，作为人工审阅前的自动 review lane。Reviewer mode 只能是 subagent、runner 或 command；Codex CLI、Claude Code 和 Asterwynd 等外部 agent 通过 runner profile 表达，inline checker 必须通过 `mode: command` 表达。Orchestrator 在进入 human gate 前按模板生成 review WorkItem；CLI Host Wrapper 或 Prompt Adapter 均可按自身 capability 派发 reviewer run，并为 agent reviewer 使用 fresh context。输入仅包含当前 phase artifact、diff、tests、evidence、workflow state 和必要项目约束，不继承执行 agent 的隐藏推理上下文。

Automated reviewer 只能提交 `review_result`，取值为 `pass`、`changes_requested`、`blocked` 或 `inconclusive`，并附 findings、evidence refs 和建议修复目标。Reviewer 不持有 approval capability，不能直接产生 human gate approval。所有必需 reviewer 返回 `pass` 后，Orchestrator 才能进入 `ready_for_review` 等待人工；若任一 reviewer 返回 `changes_requested`，workflow SHALL 回到模板定义的修复 sub-state；`blocked` 或 `inconclusive` SHALL 进入 blocked 或等待人工决定是否重新 review。

Prompt Adapter 可以负责 automated review lane 的派发与结果上报，例如在 Happy Coder 中启动 fresh Codex CLI reviewer 或 subagent reviewer。该能力仍属于自动质量门，不提升 Prompt Adapter 的 human approval 权限；review pass 之后仍必须等待可信 CLI/client 的人工批准。由 Prompt Adapter 派发的 executor/reviewer run SHALL 在 WorkResult evidence 和最终 Receipt 中记录 enforcement level 为 `prompt_adapter` 或 `audit_only`，不得呈现为 `strict_host` 或强隔离执行。

### D6: Approval 是 host capability，不是命令参数中的身份字符串

可信批准协议由用户客户端调用：

```text
approve(workflow_id, gate_id, state_version, decision, user_identity)
```

Approval SHALL 绑定 workflow、gate、phase、state version、用户身份和客户端来源。Agent 执行环境只获得 `enter/report/status` capability，不获得 approval capability。

用户不需要使用专用按钮或命令。处于 gate 时，host adapter SHALL 在把用户消息发送给模型前执行确定性的 Gate Approval Token 检查。V1 配置白名单默认且仅包含完整字符串 `ok`；只有整条用户消息与白名单项精确相等时才生成 approve decision，不调用 LLM、不做关键词包含、同义词、正则或语义模糊匹配。

精确匹配使用客户端提供的用户消息原文，不执行 trim、大小写转换或 Unicode normalization。V1 因此只接受两个 ASCII 字符 `ok`；`OK`、`Ok`、前后空白、换行附加内容或组合文本均不批准。

匹配结果绑定原始 user message id/hash、当前 gate id 和 state version；只有 host 确认消息 actor 为用户时才能生成 approval event。未匹配消息 SHALL 保持 gate，不得静默批准；消息可以继续交给 agent 作为问题、拒绝或修改反馈，但 agent 无权将其升级为 approval。

匹配成功的 approval token SHALL 由 host 消费，不再作为普通聊天消息发送给 agent。Host 在同一用户 turn 内完成 gate event、phase transition、必要的 worktree 操作和新一次 `enter`，然后自动调度下一阶段 WorkItem；默认复用当前 User Session 和 executor。任何 transition/preflight/worktree 失败 SHALL 进入 blocked 或返回明确错误，不得在部分完成状态下执行下一 WorkItem。

Prompt Adapter 模式没有用户消息拦截能力。处于 gate 时，它只能要求 agent 停止、运行只读检查、展示下一步，并提示用户改用可信 CLI/client 批准或要求修改；agent 自己不得把聊天里的 `ok` 转换为 approval event。V1 默认提示用户在终端直接运行 `workflow gate approve --workflow <id>` 完成可信批准，然后回到当前聊天继续。若用户继续在 Happy Coder 等客户端里自然语言确认，最多作为反馈交给 agent，不产生可信 gate approval。

安全模型明确承认：如果 agent 与用户拥有完全相同的主机权限，并能修改数据库、读取 approval secret 或调用用户客户端，则本地系统无法证明批准来自人。V1 必须依赖 host adapter 将数据库和 approval capability 放在 agent writable roots/环境变量之外；无法提供隔离的 executor 标记为 `untrusted_host`，只能提供审计与提示，不能宣称强制防伪。

V1 选择 Host Wrapper 进程内 capability：用户消息、event store 和 approval service 都由外层 host 持有，agent 作为受限子进程或受限 runtime 只获得 `enter/report/status` adapter。V1 不建立 Unix socket daemon，也不向 agent 环境暴露 approval secret 或一次性签名 token。CLI 人工批准只能通过用户直接运行的可信 CLI/client 完成；Prompt Adapter 中由 agent 调用的命令不得拥有 approval capability。

### D7: Gate 是运行时停止与 workspace 权限状态

进入 `ready_for_review` 后，Orchestrator 发出 `gate_reached`，释放 agent lease，并使后续 `enter` 返回：

```yaml
gate: waiting_for_human
allowed_actions:
  - status
  - provide_requested_information
workspace_write: denied
```

Gate 不只是 prompt。Workspace adapter 和 executor policy SHALL 拒绝代码/文档写操作、状态推进和新 work item claim。用户批准后创建新状态版本，旧 WorkItem 和旧 approval 自动失效。

Human gate 前的 automated review lane 不等同于 gate 本身。执行顺序 SHALL 为：phase 产物完成、机械检查通过、配置的 automated reviewers 完成并满足策略、进入 `ready_for_review`、等待可信人工批准。Automated review 失败不得绕过到人工批准；人工仍可查看 reviewer findings 并要求修复或显式处理 blocker。

### D8: Worktree Coordinator 管理唯一 workspace binding

每个进入 design 的 workflow SHALL 绑定唯一 branch 与 worktree。Coordinator 负责：

- 基于 `git common-dir` 识别 canonical repository。
- 创建、发现、校验和清理 worktree。
- 检查 worktree path、branch、HEAD、dirty state 与 registry 是否一致。
- 在创建 worktree 前校验 base branch 与 remote tracking branch 的同步状态。
- 在 `enter` 时返回绝对 workspace path，强 adapter 必须以该路径为 cwd；Prompt Adapter 必须展示 cwd 不匹配风险并停止写入建议。
- 拒绝一个 worktree 同时绑定多个 active workflows。
- worktree 缺失、branch 被删除或绑定漂移时进入 blocked。
- PR merge 确认、active change 已归档且工作区安全后清理。

设计参考 Claude Code 持久化 worktree session 并在 resume 时验证路径、扫描 sibling worktrees 的实现，但 source of truth 由本控制平面 registry 提供。

### D9: Claim/lease 防止多个 session 并发推进

`enter` 在可执行状态下原子创建有限时长 lease，绑定 workflow、state version、session 和 actor。第二个 session 可以读取 status，但不能领取同一 WorkItem。Lease 支持续期、显式释放和超时回收；所有 report 必须携带匹配 lease。

该模型参考 Claude Code task watcher 的 claim owner 行为，避免两个 agent 同时处理相同 sub-state 并覆盖产物。

### D9.1: Session 使用确定性 Workflow 恢复顺序

Host adapter SHALL 在模型调用前按以下优先级绑定 workflow：

1. 用户或启动参数显式指定 workflow id。
2. 当前 cwd 位于已绑定 worktree，恢复该 worktree 的 workflow。
3. 从 canonical main repository 启动且只有一个 active workflow，自动恢复该 workflow。
4. 从 canonical main repository 启动且存在多个 active workflows，展示确定性列表并等待用户选择；列表必须包含“创建新的 Exploration”。
5. 没有 active workflow 时，自动创建轻量 Exploration Workflow。

该选择不调用 LLM，也不根据聊天内容猜测。处于 gate 或 blocked 的 workflow 仍属于 active，并在列表中展示状态。

### D9.2: 一个 User Session 固定绑定一个 Workflow

Prompt Adapter 中的 Happy Coder 等用户聊天 Session 一旦绑定 workflow，在该 Session 生命周期内 SHALL 保持 sticky binding，不允许静默或显式切换到另一个 workflow。Workflow 可以跨多个顺序 Session 恢复；同一 workflow 同时只允许一个持有写 lease 的 Session。

Workflow 到达 done 后，原 Session MAY 继续查看、总结和回答该 workflow 的问题，但启动新的受管事项 SHALL 创建新的 User Session。该约束避免聊天历史、Gate Approval Token、worktree 和 evidence 在多个 change 之间混淆。未来只有当客户端提供真正隔离的 context branch/tab 时，才重新评估 Session 内切换。

### D10: 项目模板、Skill 与 AGENTS.md 只是 Prompt Adapter

机器可执行流程定义采用版本化模板，包含 phases、sub-states、gates、evidence requirements、workspace policy、branch pattern 和 checks。Asterwynd 项目使用首个 `coding-agent-openspec` 模板。

最终 `AGENTS.md` 只保留短接入说明，配合一个可复用 workflow skill，要求每个 agent run 通过 `workflow enter` 获取 WorkItem，并使用 `workflow report` 提交结果。该文本可由模板渲染，但不是安全 source of truth。当前 `AGENTS.md` 在迁移验收完成前保持不变。

短接入说明还 SHALL 指示用户和 agent：需要强约束受管开发流程时从 `workflow chat --executor ...` 启动；如果用户选择 Happy Coder 或其他原生客户端，则走 Prompt Adapter 降级路径。降级路径允许读取和报告受管 workflow 进度，但 gate approval 与强制写权限仍必须由可信 CLI/client 完成；控制面必须清楚展示该 session 的 enforcement level。

路径策略进一步区分 canonical main/普通 worktree 与 active workflow 专属 worktree：前两者允许 unmanaged session 自由处理其他事务；专属 worktree 只允许持有匹配 workflow/session/version binding 的受管 executor 写入。Asterwynd 和具备 host hook/sandbox adapter 的 executor SHALL 机械拒绝未绑定写入。无法提供进程级隔离的第三方原生 CLI 只能依赖 marker、instruction 和 CI 审计，并 SHALL 标记为 audit-only，不能宣称硬阻断。

### D11: Git 只提交最小签名 Workflow Receipt

完整 workflow events、snapshot、user-message reference 和本地 workspace metadata SHALL 只保存在项目外 SQLite。进入 closing 或需要 PR 审计时，Host 先对本地完整 history 执行重放和一致性验证，验证通过后生成并签名 `workflow-receipt.json`。

Receipt 至少包含：schema/key id、workflow/change/template id 与 version、base branch/commit、最终 state/version、event-chain root、必需 Gate 的 phase/version/decision、proposal/spec/design/tasks 等 artifact hash、测试与 review evidence hash、签名。Receipt SHALL NOT 包含聊天消息、完整事件、用户输入原文、Session transcript、本地绝对路径、approval capability 或工具完整输出。

Host signing private key SHALL 位于 agent 不可读取的控制面数据目录；仓库配置保存允许的 public key/key id。CI SHALL 验证：

- Receipt 签名和 schema 有效。
- 必需 Gate 摘要存在且状态顺序合法。
- Artifact 与 evidence hash 匹配 PR 内容。
- Base commit、change、branch/PR 关联一致。
- Active 与 archived change 均保留有效 receipt。

CI 不从 Receipt 重放完整本地事件，而是信任受保护 Host key 对“完整历史已经通过控制面验证”的签名声明。若执行环境无法保护 private key，则 receipt enforcement SHALL 标记为 audit-only。

V1 使用专用 Workflow Ed25519 key pair，不复用用户 Git/SSH identity。首次配置受管项目时，Host 在 `~/.asterwynd/workflows/keys/<key-id>.key` 或平台等价安全目录生成 private key，设置仅当前用户可读权限，并在项目 `.workflow/trusted-signers/<key-id>.pub` 登记 public key。Receipt 对 deterministic canonical JSON payload 签名，签名字段不参与自身 payload hash。信任配置支持多个 key id 和 signer 状态：`active` 可签发并验证新 Receipt；`retired` 用于正常轮换，只允许验证历史 Receipt，不允许签发新 Receipt；`compromised` 表示 key 已泄露或不可信，所有由该 key 签发的 Receipt 均不可信，CI/审计必须失败或要求可信 Host 重新签发。private key 永不进入 agent environment、Git 或日志。

## Pre-Implementation Review

- 决策标题：独立本地 Workflow Control Plane。
- 已确认方案：控制平面独立于 AgentLoop；V1 为本地 CLI/library + SQLite，无 daemon；需求批准后创建 worktree，设计到 closing 全程复用；接入形态为 CLI Host Wrapper 强入口和 `skill + AGENTS.md` Prompt Adapter 降级入口；最终 `AGENTS.md` 只保留短接入说明。
- 备选方案与拒绝原因：继续强化提示词无法形成硬边界；集成进 AgentLoop 无法复用其他 executor；V1 daemon 和独立仓库增加过早复杂度；可变 JSON 无法可靠并发与重放。完整记录见 `docs/adr/ADR-0001-independent-local-workflow-control-plane.md`。
- 依赖：Python SQLite、Git worktree、现有 OpenSpec CLI/artifact checker、host executor 的 sandbox/capability 接口。
- 主要风险：本地相同 OS 身份下的批准防伪、旧 workflow 迁移、CLI 多 session 并发、worktree 漂移和过度耦合 Asterwynd 项目规则。
- Approval capability transport：V1 使用 Host Wrapper 进程内调用；不使用 daemon/socket 或传递给 agent 的 token。
- Prompt Adapter gate UX：默认可信批准命令为 `workflow gate approve --workflow <id>`；该命令必须由用户在可信终端直接运行，agent 不拥有 approval capability。
- Receipt signer 状态：`active` 可签发和验证；`retired` 保留历史验证但禁止新签发；`compromised` 使该 key 的历史和新 Receipt 均不可信。
- 测试策略：事件状态机、SQLite 事务、capability 拒绝、worktree 集成、跨 session 恢复、Host history validation、Receipt 签名/哈希验证和各 executor contract test。
- 文档影响：本 change、ADR、架构、需求流程、开发/测试指南、backlog；稳定后才精简 `AGENTS.md`，如 README 事实变化则中英文同步。
- 本轮 `grill-with-docs` 设计追问已完成并进入 planning human gate；实现仍需等待可信人工批准该 gate 后才能开始。

## Testing Strategy

### 单元测试

- Managed Workspace Root canonicalization、symlink、nested path、sibling worktree、sticky bypass 和显式 attach。
- Exploration 自动创建、唯一 workflow 恢复、24 小时默认 TTL、可配置 aging 和有产出/requirements 时不自动 abandon。
- Lazy aging 在 chat/status/enter/manage 前执行，不依赖 daemon/cron，重复扫描保持幂等。
- Draft/proposed output 不阻止 aging；requirements/phase gate 与 retain mini-gate 将引用 output 提升为 durable。
- 显式 workflow、worktree cwd、唯一 active、多 active 选择和无 active 新建 exploration 的恢复优先级。
- User Session sticky workflow binding、跨 Session 恢复、done 后只读总结和新事项要求新 Session。
- 每个 phase/sub-state 的合法邻接、非法跳步、回退、skip 和 blocked 恢复。
- 事件 reducer、snapshot 重建、version CAS、hash/export consistency。
- WorkItem/WorkResult schema 和 evidence requirement 判定。
- Approval capability、gate/version 绑定和 stale approval 拒绝。
- Gate Approval Token 的精确匹配、未匹配保持 gate、原始用户消息绑定和配置白名单 fixtures。
- `ok` 原文匹配以及 `OK`、大小写变化、前后空白、换行和 Unicode 变体拒绝 fixtures。
- Lease 领取、续期、冲突、过期和释放。

### 集成测试

- `exploring → requirements` 不创建 worktree。
- 需求批准后原子创建 branch/worktree，并 materialize change artifacts。
- 新 session 从 main repository 恢复 sibling worktree workflow。
- Design、building、fix 和 closing 始终路由到绑定 worktree。
- Gate 后 agent report 和 workspace write fail closed。
- Gate 输入精确 approval token 后，同一 turn 自动推进并调度下一阶段；失败时不启动 executor。
- worktree 删除、branch 漂移和 dirty cleanup 进入预期状态。
- base branch fast-forward、dirty/diverged blocked、远端不可用和显式 local-base override。
- change id 格式、active/archive/branch/worktree 冲突、gate 前修改和 approval 后冻结。
- merge 确认后归档、生成/验证最终 Receipt 并清理 worktree。

### Contract 与入口测试

- Asterwynd、CLI Host Wrapper、Prompt Adapter 和 fake executor 使用同一 WorkItem/WorkResult fixtures。
- Host Wrapper 在 executor 启动前完成 managed-root、binding 和 user-message approval preflight；Prompt Adapter 不被误标为强制受管。
- Automated review lane 在 human gate 前派发 configured reviewers，fresh reviewer 不继承实现隐藏上下文，结果回传原 User Session，修改任务返回模板定义的修复 executor。
- CLI `enter/status/report` 输出稳定 JSON schema，文本模式只是渲染层。
- 用户客户端 approval 与 agent capability 完全隔离。
- CI 在非法 history、缺失 approval、伪造 actor、snapshot 不一致和 archive 漏审时失败。

## Risks / Trade-offs

- [相同 OS 身份削弱可信 Gate] → 控制面数据位于 agent sandbox 外，approval 使用独立 capability；不满足隔离的 executor 明确降级为 audit-only。
- [第三方原生 CLI 或 Happy Coder 可直接进入专属 worktree] → 支持 hook/sandbox 的 adapter 强制 binding；Prompt Adapter 显示 marker/instruction 并标记 prompt/audit-only，CI 检测无合法事件的变更。
- [SQLite 与本地 CLI 无实时推送] → V1 使用每轮 `enter` 刷新；未来在领域 API 外增加 daemon/event subscription。
- [事件模型增加实现复杂度] → 先交付单仓库单模板 tracer bullet，保持事件种类和 payload 最小化。
- [旧 `handoff.json` 与新 event store 双写漂移] → 迁移期单向导出兼容文件，不允许两个 source of truth；完成迁移后停止旧脚本写入。
- [worktree 创建后 requirements artifact 才进入 Git] → 控制面在需求阶段保存结构化草稿和批准快照，promotion 时原子 materialize 并保留来源事件。
- [流程模板过度绑定 Asterwynd] → domain 只认识 phase/gate/evidence/workspace 抽象，OpenSpec 和项目命令放入模板/provider。
- [每轮 enter 增加延迟] → 本地 SQLite 查询与 Git 校验分层缓存；仅在版本变化或关键 phase 执行完整 worktree reconciliation。
- [全局启用造成无关对话开销] → 以 Managed Workspace Root allowlist 在模型调用前旁路，未受管 session 不读取 workflow 状态或注入提示。

## Migration Plan

1. 新增独立 domain、event store 和 CLI，不改变现有 `AGENTS.md` 与 workflow 脚本行为。
2. 实现单一 fake executor 的 `requirements → design gate` tracer bullet，验证事件、approval、worktree 和恢复。
3. 增加 CLI Host Wrapper 和 Prompt Adapter，并在一个试点 change 上影子记录，不接管写权限。
4. 导入或映射现有 active `handoff.json`，生成 migration event；旧历史不伪造缺失的人工身份。
5. 对试点 change 启用控制平面单写，旧 `workflow_state.py` 降级为只读兼容入口，并为 Happy Coder 等客户端提供非侵入 skill 接入。
6. Host 开始签发最小 Workflow Receipt，CI 校验签名与 artifact/gate hash；稳定后要求新 change 必须由 control plane 创建。
7. 最后将 `AGENTS.md` 长流程章节替换为短接入说明和项目特有约束。

回滚时保留 event database 和已签名 Receipt，停止 adapter 自动调用，恢复当前 `AGENTS.md` 与只读状态检查；不得把新事件反向压缩成虚假的旧 transition history。
