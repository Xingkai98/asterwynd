## Context

当前 Asterwynd 的上下文注入管线有三个独立缺陷：

1. `AgentLoop._messages_with_run_context()` 以 ad-hoc 方式拼接多层上下文（memory index → skill index → active skill context → plan mode → plan → todos），缺乏统一的优先级、预算分配和截断策略
2. CLI（`agent/main.py`）和 Web（`web/session.py`）的 system prompt 是一句通用助手 prompt，缺少 coding agent 专属约束
3. `MemoryManager.compact()` 只有 LLM 摘要一种策略，无 LLM 时直接丢弃中间消息

本 change 建立统一的 **ContextBuilder 分层注入管线**：从 System Prompt（P0）到对话历史（P6），用七层优先级模型替代 ad-hoc 拼接，并配备多策略上下文压缩。

## Goals / Non-Goals

### Goals
- `ContextBuilder` 类：注册 ContextSource → 优先级排序 → 预算分配 → 渲染
- 七层优先级模型（P0-P6），P0 永不被截断，层间用 `---` 分隔
- 注入层总预算 20K tokens，超出时从低优先级层尾部逐层砍
- 重写 system prompt 为 coding agent 专用三段式结构（身份→约束→工具约定），NEVER/ALWAYS 力度分层
- 定义 ASTER.md 文件规范 + 全量拼合加载策略（上界→CWD 逐目录收集 + 来源标注 + precedence 声明）+ `/init` 命令
- `Summarizer` 抽象协议 + 两种 P0 策略（LLMSummarizer / TruncationSummarizer），ToolOutputCompressor 留 P1
- 90% 阈值触发压缩，目标降到 budget 的 20-30%，保留最近 ~20K tokens 用户消息
- 重构 `AgentLoop._messages_with_run_context()` 委托给 ContextBuilder

### Non-Goals
- 不引入 Cursor 风格的 `.asterwynd/rules/` 模块化目录
- 不做子目录 ASTER.md 懒加载
- 不做 AGENTS.md/CLAUDE.md 运行时 fallback
- 不做 model 自动检测与适配（system prompt 先为 Claude 优化）
- 不做 `compact_context` 工具（agent 主动压缩）
- 不引入基于嵌入的语义压缩
- 不改变各上下文来源的内容生成逻辑（除 system prompt 重写外）

## Decisions

### 1. 七层优先级模型

```
P0  System Prompt         ~1.5K   不截断   身份、约束、工具约定
P1  ASTER.md              ~3K     不截断   项目指令（本 change 新增）
P2  记忆索引               ~2K     可截     MEMORY.md 摘要
P3  自动召回记忆           ~3K     可截     语义搜索匹配的记忆（Change ⑥ 输出）
P4  Skill 上下文           ~5K     可截     活跃 skill 的完整 prompt
P5  Plan / Todo 状态      ~5K     可截     当前计划 + 进度
P6  对话历史               ~80K    最先压缩  已有 MemoryManager 管理
───
注入层合计（P0-P5）        ~20K
```

**P2 与 P3 不合并**：P2 来自 MEMORY.md 文件（静态、始终加载），P3 来自向量搜索（动态、按需注入）。来源不同、变化频率不同、触发条件不同，分开各自管理。

**P0 与 P1 分开**：System Prompt 是"你作为一个 coding agent 怎么运作"，ASTER.md 是"在这个项目里怎么干活"。与 Cursor/Claude Code 一致：先定义 agent 能力边界，再给项目约束。

### 2. ContextBuilder 架构

```python
class BuildContext:
    cwd: str
    mode: AgentMode
    context_window: int      # 模型总上下文窗口大小（如 100K）
    total_budget: int        # ContextBuilder 分配给本 source 的上限


class ContextSource(Protocol):
    priority: int           # 0-6, 0 = highest
    name: str               # Human-readable name for debugging
    budget: int             # Target token budget (advisory)
    critical: bool          # True = never truncate

    async def render(self, context: BuildContext) -> str:
        """Render this source's content given current build context."""
        ...
```

- **BuildContext** 只放通用的环境级信息。`context_window` 由 AgentLoop 初始化时从 LLM 实例读取（如 LLM 不暴露则默认 100K），特定依赖在构造函数注入（如 persistent_memory、skill_runtime）。
- **注册方式**：AgentLoop 初始化时静态注册所有 source。未实现的 source 不注册或渲染返回空字符串。
- **async 协议**：协议签名保留 `async def render()`，为 P3 向量搜索预留。同步实现不加 `await` 即可，零开销。
- **错误处理**：单个 source render 失败时跳过该 source 并 log warning，不阻塞其余 source 的渲染。

ContextBuilder 流程：
```
注册 sources → 按 priority 排序 → 分配 budget → 逐个 render → 超预算时从最低优先级尾部砍 → 层间插入 --- → 返回拼接结果
```

- 注入层总预算公式：`min(20_000, int(context_window * 0.20))`
- P0 和 P1 不参与截断（默认不超过 5K，超过时警告）
- 预算不足时从 P5 尾部开始砍，仍不足则移除 P5 → 继续砍 P4 → ...
- 截断保留层开头（更早的内容可能更重要），砍尾部

**ContextBuilder API**：
```python
class ContextBuilder:
    def __init__(self, total_budget: int):
        ...
    def register(self, source: ContextSource) -> None:
        """Register a context source. Sources are sorted by priority on build."""
        ...
    def set_budget(self, total_budget: int) -> None:
        """Update total injection layer budget (e.g., when context window changes)."""
        ...
    async def build(self, context: BuildContext) -> str:
        """Sort sources, render each, apply truncation, return joined result."""
        ...
```

**迁移路径**：现有 `AgentLoop` 方法一对一映射为 ContextSource，内容生成逻辑不变：

| 现有方法 | ContextSource | P |
|---|---|---|
| `_messages_with_run_context()` 中的 memory_index 一段 | `MemoryIndexSource` | P2 |
| `skill_runtime.render_skill_index()` | `SkillIndexSource` | P4 |
| `skill_runtime.render_active_skill_context()` | `SkillActiveSource` | P4 |
| `_plan_mode_context()` | `PlanModeSource` | P5 |
| `_planning.render_context()` | `PlanningStateSource` | P5 |
| `_todo_context()` | `TodoSource` | P5 |

System Prompt（P0）和 ASTER.md（P1）是本 change 新增的 ContextSource。

### 3. System Prompt 三段式结构

```
## 身份

你是 Asterwynd，一个运行在本地的 coding agent。你的工作目录是 {cwd}。
你通过工具调用来读取、搜索、编辑代码，完成用户提出的工程任务。

技术栈：Python {python_version}，Asterwynd {asterwynd_version}

## 约束

### NEVER（红线圈死）
- NEVER 修改 .git/、.env、secrets、缓存文件或 benchmark 产物
- NEVER 在没有先用 Read 工具查看文件内容的情况下编辑文件
- NEVER 跳过工具调用直接编造文件内容作为回答
- NEVER 在用户或项目指令未明确要求的情况下创建测试文件或文档文件
- NEVER 做任务范围之外的修改或重构

### ALWAYS（每次必做）
- ALWAYS 对已有文件使用 Edit 工具做精确替换；Write 工具仅用于创建新文件
- ALWAYS 有意义的代码修改后，使用 InspectGitDiff 检查变更

## 工具使用约定

- 调用工具前，确保理解其参数和副作用
- 工具调用失败时，分析错误原因后再重试，不要盲目重复相同调用
- 对不确定的操作（删除文件、强制推送、修改配置），先向用户确认
- 可以并行调用多个无依赖的工具，减少往返次数
```

- 中文为主，代码标识符和工具名保留英文
- Prompt 模板内嵌在 `agent/context/sources.py` 中，不独立文件
- 从 `pyproject.toml` 读取 Asterwynd 自身版本，session 启动时读一次
- 用户 `--system` 参数追加在默认 prompt 末尾，用 `---` 分隔（近因效应让用户指令覆盖默认）
- CLI 和 Web 入口统一使用同一套 prompt 构建逻辑

### 4. ASTER.md 文件规范和加载

**文件命名**：
- `ASTER.md`：团队共享，提交 Git
- `ASTER.local.md`：个人本地覆盖，gitignored
- 格式：纯 Markdown，无 YAML frontmatter
- `.local.md` 追加在 `.md` 之后（不替换段落）

**加载策略（全量拼合 + 来源标注）**：
```
确定上界 → 从上界向下遍历到 CWD → 收集每个目录的 ASTER.md → 按路径顺序拼合
```
- 有 Git：上界 = Git 根目录
- 无 Git：上界 = CWD（安全考虑：防止 `~/ASTER.md` 被意外注入到所有无 Git 项目）
- 每个目录加载 ASTER.md 和 ASTER.local.md（均存在时两者都加载，ASTER.md 在前、ASTER.local.md 在后，用 `---` 分隔）
- 排序：越靠近上界的越靠前，越靠近 CWD 的越靠后（近因效应让子目录指令自然获得更高优先级）

选择全量拼合而非最近匹配的原因：
- 参考 Codex CLI（root→CWD 全量拼合）和 OpenCode（local+global 合并），三者都不因有子目录指令而丢弃祖先指令
- 根目录放通用规范（"用 pytest"），子目录放领域约束（"用 Django ORM"），两者都需要

**拼合格式（带来源标注）**：
```
## ASTER.md ({relative_path})
{file_content}

## ASTER.md ({relative_path})
{file_content}
```
- `relative_path` 是文件所在目录相对于上界的路径，如 `## ASTER.md (项目根)` 和 `## ASTER.md (src/backend/)`
- agent 能区分每条指令来自哪个目录层级
- `.local.md` 标注为 `## ASTER.local.md ({relative_path})`
- 拼合后在末尾追加 precedence 声明：`> 以上 ASTER.md 文件中，越靠近当前工作目录的指令优先级越高。如有冲突，以靠近工作目录的为准。`

**大小限制**：拼合后总大小不超过 32 KiB（参考 Codex `project_doc_max_bytes` 默认值）

**`/init` 命令（非交互）**：
1. 检测项目类型（pyproject.toml / package.json / go.mod 等）
2. 检测已有 AGENTS.md / CLAUDE.md，有则将内容复制到 ASTER.md 并注明来源（`> 以下内容从 AGENTS.md 导入`）
3. 检测入口文件（main.py / index.js 等），生成常用命令段：
   ```
   ## 常用命令
   - 安装依赖: `uv sync --extra dev`
   - 运行测试: `uv run pytest -q`
   - 启动服务: `uv run python src/main.py`
   ```
4. 生成 ASTER.md：
   ```
   # ASTER.md
   
   本文件供 Asterwynd 在该项目中读取项目专属的指令和约束。
   
   > 以下内容从 AGENTS.md 导入
   ...
   
   ## 常用命令
   - ...
   ```
5. 追加 `ASTER.local.md` 到 `.gitignore`（如有）
6. 一行确认输出

`/init`（agent 会话内）和 `asterwynd init`（CLI）共享同一套核心逻辑，入口不同。

### 5. 上下文压缩多策略

**Summarizer 协议**：
```python
class Summarizer(Protocol):
    name: str
    def summarize(self, messages: list[Message], budget: int,
                  priority_map: dict[str, int]) -> list[Message]:
        """Compress messages to fit within budget, respecting priority map."""
        ...
```

三种实现：
- `ToolOutputCompressor`：扫描旧 tool 调用，将超过阈值（如 2K tokens）的输出替换为 LLM 生成的简述（如"Read agent/loop.py → 1122 行，包含 AgentLoop 类和 _messages_with_run_context 方法"）。保护信息不丢失，只压缩体积
- `LLMSummarizer`：将旧对话轮次压缩为结构化手交摘要（四段式输出：已完成/关键决策/进行中/阻塞与待办，强制保留文件路径、函数名、关键决策、未解决事项）。摘要作为 user message 注入（语义上代表"之前的对话历史"，而非 agent 约束）
- `TruncationSummarizer`：无 LLM 时降级——tool 输出截断到前 500 字符 + 旧消息丢弃（警告）

**触发和压缩策略**：
```
token < 90% budget     → 不压缩
token ≥ 90% budget     → 触发压缩
                         保留最近 ~20K tokens 用户消息（不参与压缩）
                         旧对话轮次 → LLMSummarizer 结构化手交摘要
                         旧 tool 调用 → 随旧轮次一起被摘要覆盖
                         目标: P6 对话历史压到原大小的 20-30%
                         最小间隔 5 轮
                         无 LLM → TruncationSummarizer 降级（警告）
```

触发阈值参考 Codex CLI（~90-95%）和 OpenCode（80%），取 90%。压缩目标 20-30% 仅针对 P6 对话历史（注入层 P0-P5 不受压缩影响）。压缩后总量 = P0-P5 ~20K + 压缩后 P6 ~15-20K ≈ ~35-40K。

**总预算协调**：ContextBuilder 管理 P0-P5 注入层预算，MemoryManager 管理 P6 对话历史预算。总预算由 AgentLoop 统筹：`P6_budget = context_window - 注入层实际占用`。ContextBuilder 的 `BuildContext.total_budget` 传入注入层上限，MemoryManager 收到的是扣减后的剩余空间。

压缩后结构：
```
[System Prompt + ASTER.md + 记忆索引 + Skill + Plan/Todo]  ← 不受压缩影响
[结构化摘要: 已完成 | 关键决策 | 进行中 | 阻塞与待办]         ← LLM 产出，替代旧消息
[最近 ~20K tokens 用户消息 + assistant 回复 + tool chain]  ← 原样保留
```

**优先级保留策略**（从高到低）：
1. System messages — 绝对保留
2. 完整的 tool chain（call + result 不拆散）
3. 最近的用户消息
4. 最近的 assistant 回复
5. 中间的历史消息 — 最先被压缩

**摘要模型**：P0 统一用主模型做摘要（简单，少一个模型配置），P1 引入模型选择（允许配置便宜的摘要模型如 Haiku）。

### 6. 实现顺序

四个子系统的实现顺序由依赖关系决定：

```
Phase 1: ContextBuilder 核心       ← 中枢，其他三个都依赖它
Phase 2: System Prompt 优化        ← 独立的 P0 ContextSource
Phase 3: ASTER.md 注入             ← 独立的 P1 ContextSource + /init 工具
Phase 4: 上下文压缩                 ← P6 管理，依赖 MemoryManager 重构
```

## Pre-Implementation Review

以下决策已通过 grill-with-docs（2026-07-12）逐项确认：

- [x] ASTER.md 加载策略：全量拼合 + 来源标注 + precedence 声明（参考 Codex CLI / OpenCode）
- [x] System Prompt 约束结构：NEVER / ALWAYS 力度分层
- [x] ContextBuilder API：BuildContext（cwd/mode/budget）、静态注册、async 协议
- [x] P2/P3 分层：保持分开（来源不同、触发条件不同）
- [x] 压缩策略：90% 单触发、P6 目标 20-30%、摘要为 user message
- [x] P0/P1 边界：ToolOutputCompressor 和便宜模型摘要放 P1
- [x] `/init` 行为：内容复制 + 来源标注、CLI/tool 共享核心逻辑
- [x] 摘要模型：P0 用主模型，P1 引入模型选择
- [x] Codex CLI 审查（2026-07-12）：8 个问题全部修复（context_window / ASTER.md 加载矛盾 / 上界安全 / proposal 同步 / render 错误处理 / 摘要角色变更风险 / 去掉关键词检测 / 总预算协调）

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| ContextBuilder 重构导致现有 context 注入行为变化 | 先将当前行为固化为集成快照测试，重构后逐项验证 |
| 全量拼合时祖先与子目录指令冲突 | 末尾追加 precedence 声明；子目录指令因近因效应自然优先 |
| `/init` 检测不准（项目类型误判） | 多信号综合判断；不确定时留空让用户填 |
| NEVER 约束过于绝对 | 约束段只列高风险的硬性禁止项；模糊场景由工具约定段处理 |
| LLMSummarizer 丢失关键信息 | 摘要 prompt 强制保留函数名、文件名、关键决策、未解决事项 |
| ToolOutputCompressor 简述失准（把关键输出泛化） | 简述 prompt 要求保留数字、参数、文件名；标注来源消息索引 |
| TruncationSummarizer 完全丢弃旧消息 | 只在无 LLM 时使用，且报警告 |
| 摘要角色从 system 改为 user message | 行为变更，可能影响模型对摘要的重视程度。通过 benchmark smoke 验证 |

## Testing Strategy

- 单元测试：ContextBuilder 注册/排序/渲染/截断逻辑
- 单元测试：P0 层永不截断，层间 `---` 分隔符正确位置
- 单元测试：System Prompt 三段结构完整性，版本占位符替换
- 单元测试：ASTER.md 上界确定、全量拼合遍历、来源标注格式
- 单元测试：`/init` 项目类型检测（pyproject.toml / package.json / go.mod）
- 单元测试：各 Summarizer 的压缩行为 + 压缩后 token ≤ budget
- 单元测试：ToolOutputCompressor 简述准确性（已知长输出 → 正确简述）**(P1)**
- 单元测试：90% 触发逻辑 + 最小间隔 5 轮防抖
- 集成测试：重构前后 context 内容对比（快照测试）
- 集成测试：CLI 和 Web 入口使用新 system prompt
- 集成测试：`--system` 参数正确追加
- 集成测试：`/init` 在空目录、有项目文件的目录、有已有 AGENTS.md 的目录中运行
- 集成测试：tool chain 完整性保护验证
- 集成测试：无 LLM 降级路径
- Benchmark smoke：确保 AgentLoop 核心路径行为不变
