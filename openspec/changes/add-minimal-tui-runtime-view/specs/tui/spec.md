## MODIFIED Requirements

### Requirement: TUI 当前为预留能力域

系统 SHALL 在本 change 实现后提供最小多轮 TUI runtime view；在实现前不得声称已经支持独立 TUI。

#### Scenario: 当前用户入口

- **GIVEN** 用户使用当前仓库
- **WHEN** 查看可用入口
- **THEN** 系统 SHALL 只提供当前 CLI、Web 和 benchmark 入口
- **AND** 只有在本 change 实现后才 SHALL 提供 TUI 命令

## ADDED Requirements

### Requirement: TUI 提供基本多轮会话

TUI SHALL 允许用户在同一个 TUI session 中连续发送多轮消息，并复用同一个 AgentLoop session 语义维护 message history。

#### Scenario: 用户连续发送两轮消息

- **GIVEN** TUI 已启动并显示输入区
- **WHEN** 用户发送第一条消息并等待运行完成，再发送第二条消息
- **THEN** TUI SHALL 在同一个 transcript 中展示两轮用户消息和 assistant 回复
- **AND** 第二轮运行 SHALL 复用同一个 session id
- **AND** 第二轮运行 SHALL 生成新的 run id

### Requirement: TUI 展示运行事件

TUI SHALL 展示用户消息、assistant 回复、工具调用进度、planning state 和最终结果摘要。

#### Scenario: AgentLoop 产生工具事件

- **GIVEN** TUI 正在运行 AgentLoop
- **WHEN** 工具调用开始和结束
- **THEN** TUI SHALL 更新工具事件展示

#### Scenario: 展示当前运行标识

- **GIVEN** TUI 中已经启动至少一轮 AgentLoop 运行
- **WHEN** 用户查看 TUI 状态栏或等价状态区域
- **THEN** TUI SHALL 展示当前 session id
- **AND** TUI SHALL 展示最近一轮 run id

### Requirement: TUI 提供 slash command 提示

TUI SHALL 在输入区提供与 Web UI 一致的 slash command 提示，命令来源 SHALL 复用现有 slash command registry 和 skill command catalog。

#### Scenario: 输入 slash 前缀

- **GIVEN** TUI 已启动并加载 slash command catalog
- **WHEN** 用户在输入区输入 `/st`
- **THEN** TUI SHALL 展示匹配当前前缀的命令提示
- **AND** 提示 SHALL 包含命令名、参数提示和描述

#### Scenario: 选择 slash 命令

- **GIVEN** TUI 正在展示 slash command 提示
- **WHEN** 用户用键盘选择某个命令
- **THEN** TUI SHALL 将该命令的 `insert_text` 填入输入区

#### Scenario: Skill command 出现在提示中

- **GIVEN** 当前 skill runtime 加载了可显式调用的 skill
- **WHEN** 用户输入匹配该 skill 名称的 slash 前缀
- **THEN** TUI SHALL 在提示中展示对应 skill command
- **AND** 提交该命令后 SHALL 按现有 slash command 语义组装后续输入给 skill

### Requirement: TUI 复用核心运行协议

TUI SHALL 复用 AgentLoop、工具事件、planning state 和 session 语义，不得另起不兼容协议。

#### Scenario: TUI 启动运行

- **GIVEN** 用户通过 TUI 命令启动任务
- **WHEN** TUI 创建运行时
- **THEN** 系统 SHALL 使用现有 AgentLoop 构造路径

### Requirement: TUI 非交互环境降级

TUI SHALL 在当前终端不支持交互式渲染时给出清晰错误，而不是卡死、静默失败或输出损坏的控制字符。首版 TUI SHALL NOT 实现 `--plain` 文本事件流降级。

#### Scenario: 非 TTY 环境启动 TUI

- **GIVEN** 标准输入或标准输出不是 TTY
- **WHEN** 用户执行 TUI 命令
- **THEN** 系统 SHALL 拒绝启动交互式 TUI 并输出可读原因

### Requirement: TUI 支持 approval 决策

TUI SHALL 支持高风险工具调用的基本 approval request 展示和 approve/deny 决策，并复用现有 approval handler 语义。

#### Scenario: 工具调用需要审批

- **GIVEN** TUI 中的一轮 AgentLoop 运行触发 approval request
- **WHEN** TUI 接收到 approval request 事件
- **THEN** TUI SHALL 展示工具名、审批原因和必要的脱敏参数摘要
- **AND** 用户 SHALL 能选择 approve 或 deny

#### Scenario: 用户批准审批

- **GIVEN** TUI 正在等待 approval 决策
- **WHEN** 用户选择 approve
- **THEN** TUI SHALL 将 approved 决策交给当前 approval handler
- **AND** AgentLoop SHALL 继续执行对应工具调用

#### Scenario: 用户拒绝审批

- **GIVEN** TUI 正在等待 approval 决策
- **WHEN** 用户选择 deny
- **THEN** TUI SHALL 将 denied 决策交给当前 approval handler
- **AND** AgentLoop SHALL 按现有审批拒绝语义继续运行

### Requirement: TUI 支持基础鼠标交互

TUI SHALL 保留 Textual 默认支持的基础点击聚焦和滚轮滚动能力，但不要求实现复杂鼠标工作台交互。

#### Scenario: 滚动历史对话

- **GIVEN** transcript 内容超过可视区域
- **WHEN** 用户使用鼠标滚轮滚动
- **THEN** TUI SHOULD 滚动 transcript 历史内容

#### Scenario: 点击输入区

- **GIVEN** TUI 已启动
- **WHEN** 用户点击输入区
- **THEN** TUI SHOULD 聚焦输入区以便继续输入
