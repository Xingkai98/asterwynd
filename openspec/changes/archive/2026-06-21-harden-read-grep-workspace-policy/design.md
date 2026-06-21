## Context

MyAgent 已有 WorkspacePolicy，用于限制 workspace 内路径、敏感文件和命令执行。当前 Write、Edit、ListFiles、Find、InspectGitDiff 和 benchmark MyAgentRunner 中的 Bash 会使用 policy，但 ReadTool 和 GrepTool 不使用 policy，导致最常用的读工具绕过安全边界。

审计探针确认当前行为可以读取 workspace 外文件、`.env` 内容，并可通过 Grep 递归扫描敏感文件。该问题属于现有能力框架内的安全边界缺陷，不是扩展新能力。

## Goals / Non-Goals

**Goals:**

- ReadTool 和 GrepTool 默认只读取 WorkspacePolicy 允许的路径。
- read policy 默认拒绝 denied patterns。
- 所有默认 agent tool set 使用同一个 workspace-rooted policy。
- 裸构造 `ReadTool()` / `GrepTool()` 时使用当前进程工作目录作为默认 workspace root。
- 回归测试覆盖 workspace 外路径、敏感文件、递归搜索泄露和正常读取。
- 不破坏 Write/Edit/Bash/ListFiles/Find/InspectGitDiff 的既有合理行为。

**Non-Goals:**

- 不收紧 Bash command policy。
- 不实现 MemoryManager summary compact。
- 不改变 benchmark artifact 生成策略。
- 不新增权限交互 UI 或用户确认流程。
- 不做通用沙箱或容器隔离。

## Decisions

### Decision 1: ReadTool / GrepTool 接收 WorkspacePolicy

ReadTool 和 GrepTool 增加可选 `policy: WorkspacePolicy | None` 构造参数。默认构造保持可用，但默认 policy 应以当前工作目录为 workspace root。

理由：

- 与 Write/Edit/ListFiles/Find/InspectGitDiff 的模式一致。
- 方便单元测试注入临时 workspace。
- 避免工具内部各自实现路径安全逻辑。

备选方案：

- 只在 AgentLoop 或 ToolRegistry 层统一拦截工具参数。该方案对不同工具的路径参数约定过于隐式，短期不采用。

### Decision 2: read policy 应用 denied patterns

`assert_read_allowed()` 应在 `assert_within_workspace()` 后应用 read denied patterns。初始可复用现有 denied patterns；如发现读写边界需要分化，再拆分为 read/write 两组配置。

理由：

- `.env`、`.git`、私钥、虚拟环境和 benchmark runs 对读操作同样敏感。
- 当前只保护写入会给用户造成“WorkspacePolicy 已保护文件安全”的错误预期。

备选方案：

- 保持 read policy 宽松，只在 Read/Grep 中单独拒绝敏感路径。该方案会让 ListFiles/Find/InspectGitDiff 等读工具继续拥有不一致语义，不采用。

### Decision 3: 递归 Grep 必须逐项过滤 denied paths

Grep 搜索起点通过 `assert_read_allowed()` 后，递归遍历过程中还必须跳过 denied pattern 命中的目录和文件。

理由：

- 根目录 `.` 本身通常允许读取，但其子树可能包含 `.env`、`.git`、`.venv` 等敏感路径。
- 只校验搜索起点不能防止递归泄露。

备选方案：

- 依赖 Path glob 结果后读取失败。该方案没有明确安全边界，也难以测试，不采用。

### Decision 4: 本 change 不设计内部读取绕过

本 change 聚焦普通 agent tool 的读取安全边界。benchmark runner 当前通过隐藏任务文件和任务 workspace policy 工作，不应依赖 Read/Grep 读取受限路径；除非测试证明需要，否则不新增内部读取绕过机制。

理由：

- agent-facing tool 的安全边界必须清晰。
- 避免在安全修复中引入未证实需要的新接口。
- 后续如出现内部读取需求，可单独建 change 设计。

## Risks / Trade-offs

- [Risk] 现有测试或脚本依赖 Read/Grep 读取绝对路径。  
  Mitigation: 更新测试为显式 workspace policy；必要时只在测试中构造临时 workspace。

- [Risk] 复用 denied patterns 可能让某些读操作变得过严。  
  Mitigation: 先以安全为默认；如发现合法内部读取需求，新增内部接口或拆分 read/write denied patterns。

- [Risk] Grep 递归过滤增加少量遍历成本。  
  Mitigation: 当前工具已有输出上限，优先保证安全；性能问题后续再优化。

- [Risk] 默认 `ReadTool()` 的 workspace root 变为当前工作目录，和旧行为不同。  
  Mitigation: 这是本 change 的预期 breaking change；CLI/Web/benchmark 的 tool set 应显式传入 policy。
