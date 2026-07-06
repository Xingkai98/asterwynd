## Why

项目已经规定“需要设计或对比 coding-agent 能力时，应先查找当前工作区可用的参考仓库”，并约定本地参考仓库路径由 `.dev/reference-repos.txt` 提供。但该规则目前主要依赖 agent 自觉执行，不能稳定阻止以下问题：

- 新 change 直接进入设计或实现，没有显式判断是否需要横向调研其他 coding agent 的实现。
- 即使做了调研，结论也可能只留在聊天记录里，后续实现者、审阅者和归档记录无法追溯。
- 本地参考仓库缺失时，agent 可能静默跳过调研，没有留下原因和替代判断依据。

本 change 目标是把“参考实现调研”纳入 OpenSpec change artifact 的硬门禁：非 docs change 必须显式声明调研状态、原因、问题、发现和设计影响；允许关闭，但必须写明原因。artifact checker 和 CI 负责阻止漏填或空壳。

## Change Type

- primary: process
- secondary: []

## What Changes

- 非 docs OpenSpec change SHALL 维护 `## Reference Implementation Research`。
- 默认状态为 `enabled`；如果关闭，必须声明 `status: disabled` 并提供非空理由。
- 启用时必须记录 research questions、findings 和 design impact。
- 本地 `.dev/reference-repos.txt` 缺失、为空或参考仓库不可用时，不阻塞 change 创建，但必须在 findings 中记录无法使用本地参考仓库的事实和后续依据。
- `openspec/templates/tasks.md` SHALL 默认包含参考实现调研任务。
- `scripts/check_openspec_artifacts.py` SHALL 机械检查参考实现调研记录，不判断调研质量。
- CI 通过既有 artifact checker 自动执行该门禁。

## Capabilities

### Modified Capabilities

- `change-documentation`: OpenSpec change 文档流程增加参考实现调研决策记录和机械门禁。

## Impact Analysis

- 影响代码：
  - `scripts/check_openspec_artifacts.py`
- 影响测试：
  - `tests/test_openspec_artifact_checker.py`
- 影响文档：
  - `AGENTS.md`
  - `docs/requirements-process.md`
  - `openspec/config.yaml`
  - `openspec/templates/tasks.md`
  - `openspec/specs/change-documentation/spec.md`
  - `docs/openspec-change-backlog.md`
- 影响现有 active changes：
  - 需要补充 `## Reference Implementation Research`，否则新 checker 会让现有队列失败。
- 不影响：
  - `.dev/reference-repos.txt` 的本地配置方式；该文件仍不提交。
  - 参考仓库本身；本项目不把参考仓库作为依赖。
  - CI 基础命令；继续复用现有 artifact checker 门禁。

## Reference Implementation Research

- status: enabled
- reason: 本 change 本身定义 coding-agent 需求设计阶段的参考实现调研门禁，必须横向查看其他 coding agent 仓库如何固化 agent 入口规则、命令、hooks 和 CI。
- research questions:
  - 其他 coding-agent 仓库是否把 agent 行为规范放在仓库级入口文档中？
  - 它们是否使用命令、skills、hooks 或 CI 把流程约束固化为可执行规则？
  - 对 Asterwynd 来说，哪些做法应沉淀为 OpenSpec change artifact，而不是仅依赖聊天记录？
- findings:
  - `.dev/reference-repos.txt` 存在并列出 Claude Code、Codex、Hermes Agent、Nanobot、OpenClaw、opencode、Pi mono 等本地参考仓库。
  - 当前环境没有可调用的 `codegraph` 命令，因此本次按项目规则降级为 `rg`、`find` 和定点文件阅读。
  - Codex、opencode、OpenClaw 等仓库均存在仓库级或分目录 `AGENTS.md`，用于固化 agent 操作规则、验证命令、评审要求和风险边界。
  - Claude Code、OpenClaw 等仓库存在命令或 hooks 目录；Codex、opencode、OpenClaw 等仓库存在 `.github/workflows/`，说明成熟 coding-agent 项目会把规则从文字入口延伸到命令、hooks 或 CI。
  - OpenClaw 的入口规则尤其强调“硬门槛”和“亲自检查参考实现/依赖合同后才能下结论”，支持本项目把参考实现调研设为显式 artifact 门禁。
- design impact:
  - 采用 `## Reference Implementation Research` 作为 change artifact，而不是只在 AGENTS.md 写文字规则。
  - artifact checker 只检查记录是否存在、状态是否合法、必填字段是否非空；调研质量仍由设计追问和人工审阅负责。
  - 本地参考仓库不可用时不让 checker 读取 `.dev/reference-repos.txt`，避免 CI 依赖本地路径；但 change 文档必须记录不可用事实和替代依据。
