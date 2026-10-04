# web-ui spec delta: harness 式 transcript（正文成文 + 工具执行单行折叠）

## MODIFIED Requirements

### Requirement: Chat 视图按 display metadata 展示工具结果

Web Chat SHALL 把每次工具执行渲染为**对话流中的一行**（`harness-style` 折叠行），并消费服务端 `tool_result` 事件中的 display metadata 生成行尾元数据。折叠态 SHALL NOT 展示结果正文的任何字符；用户 SHALL 能按需展开查看完整参数与完整结果。工具结果 SHALL 作为纯文本展示，不按 Markdown 或 HTML 渲染。

具体地：

- **一行**：一次工具执行在对话流里 SHALL 恰好占一个可点击行（`[caret][标题][分隔点][摘要][元数据]`），行高 SHALL 不随参数或结果的长度变化。
- **折叠态零正文**：折叠态可见文本 SHALL NOT 含结果正文片段，SHALL NOT 含 `display.preview`（旧实现把 1200 字符预览直接铺在时间线上）。
- **展开**：展开后 SHALL 展示缩进 JSON 形式的原始参数与完整结果文本；展开体 SHALL 是头部按钮的**兄弟节点**（在其内部点选文本 SHALL NOT 触发折叠切换）。
- **元数据**：行尾 SHALL 展示结果规模（字符数；多行时附行数），值取自 `display.char_count` / `display.line_count`。
- **纯文本**：结果与参数 SHALL NOT 被解析或执行为 HTML。
- **参数上限**：展开态的参数与结果正文 SHALL 共享同一条展示上限；触顶时 SHALL 给出可读的截断提示。

#### Scenario: 长结果默认折叠为一行

- **GIVEN** `tool_result` 事件包含 collapsed display metadata
- **WHEN** Chat 页面展示该工具结果
- **THEN** 对话流 SHALL 只增加一个行高固定的工具行
- **AND** 该行的可见文本 SHALL NOT 包含结果正文预览
- **AND** 行尾 SHALL 展示字符数与行数
- **AND** 用户 SHALL 能展开查看完整参数与完整结果

#### Scenario: 短结果同样默认折叠

- **GIVEN** 工具结果短于 display policy 的任何阈值（`collapsed` 为 false）
- **WHEN** Chat 页面展示该工具结果
- **THEN** 该行 SHALL 同样处于折叠态
- **AND** 折叠判据 SHALL NOT 依赖服务端 `display.collapsed`

#### Scenario: 工具结果包含 HTML

- **GIVEN** 工具结果包含 HTML 字符串
- **WHEN** Chat 页面展示工具结果
- **THEN** 页面 SHALL 以纯文本展示该字符串
- **AND** SHALL NOT 执行或解析为 HTML

#### Scenario: 展开体内部点击不触发折叠

- **GIVEN** 某工具行处于展开态
- **WHEN** 用户在该行的展开体内点选文本
- **THEN** 该行 SHALL 保持展开态

### Requirement: Web UI 折叠展示思维链

Web UI SHALL 在 assistant 消息**含 reasoning 时**提供思维链的折叠展示区，且该区 SHALL 满足：**默认关闭**、**单击展开**、**与正文分离**、**跨 provider 统一样式**、**折叠态只占一行**。

具体地：

- **默认关闭**：初次渲染时该区处于折叠态，正文 SHALL NOT 被思维链挤占。
- **单击展开**：用户单击标题行切换展开/折叠；展开后可见思维链文本。
- **与正文分离**：思维链 SHALL NOT 混入 assistant 的 Markdown 正文。
- **跨 provider 统一**：形态 SHALL NOT 按 provider 分叉（Anthropic / OpenAI 兼容端点呈现同一交互）。
- **无则不渲染**：assistant 消息不含 reasoning 时 SHALL NOT 渲染该区。
- **折叠态一行**：折叠态 SHALL 与工具执行行同款（单行、行高不随思维链长度变化），SHALL NOT 用带边框的整块容器。

依据（issue #256）：思维链 token 已计入 output token（用户已付费）但当前完全不展示；用户拍板展示形态为「通用样式、默认关闭、单击展开」。折叠态一行是 change `harness-style-web-transcript` 的统一口径补充：对话区只保留正文为"块"，其余过程信息一律单行。

#### Scenario: 含 reasoning 的 assistant 消息默认折叠

- **GIVEN** assistant 消息含 reasoning 内容
- **WHEN** Web UI 渲染该消息
- **THEN** UI SHALL 渲染思维链折叠区
- **AND** 该区初始状态 SHALL 为折叠（正文不被思维链占据）
- **AND** 思维链文本 SHALL NOT 出现在 assistant 的 Markdown 正文里

#### Scenario: 单击标题行切换展开

- **GIVEN** 思维链折叠区已渲染且处于折叠态
- **WHEN** 用户单击该区标题行
- **THEN** 该区 SHALL 切换为展开态并显示思维链文本
- **AND** 再次单击 SHALL 切换回折叠态

#### Scenario: 无 reasoning 的消息不渲染该区

- **GIVEN** assistant 消息不含 reasoning 内容
- **WHEN** Web UI 渲染该消息
- **THEN** UI SHALL NOT 渲染思维链折叠区
- **AND** 该消息的展示 SHALL 与未引入本能力时一致

#### Scenario: 折叠态与工具行同款单行

- **GIVEN** assistant 消息含极长的 reasoning 内容
- **WHEN** Chat 页面以折叠态展示该消息
- **THEN** 思维链折叠区的可见高度 SHALL 等于单行高度
- **AND** 思维链正文 SHALL NOT 出现在折叠态的可见文本里

## ADDED Requirements

### Requirement: 工具执行行的失败信号在折叠态可见

Web Chat SHALL 在**折叠态**就让用户看出「这次工具执行失败了」，并给出可读的因由；失败 SHALL NOT 触发自动展开。

具体地：

- **状态可辨**：失败行 SHALL 带 `data-state="error"`，并在视觉上与成功行可分辨（行首导轨与行尾因由用错误色）。
- **因由可读**：可读的失败首行（后端 canonical 错误前缀）SHALL 顶到折叠摘要上；**结构化结果**（`Bash` 的单行 JSON 信封、`TaskOutput` 的多行 `[Task <id>]` + `status:` / `exit_code:` 信封）SHALL 保留参数摘要（命令/任务 id 是第一定位符），把失败因由（如 `exit 1` / `failed` / `timeout`）放在行尾元数据。
- **不自动展开**：失败行 SHALL 保持折叠。
- **前缀对齐**：失败判定 SHALL 覆盖后端自身的 canonical 错误通道（`[Error`、`Error`、`[Permission denied`、`[Approval denied`、`[Approval unavailable`、`[Approval required`、`[MCP tool error`）、浏览器族的自有文案（`[Browser Error`、`[Browser not available`、`[URL denied`）、非零退出码，以及 `TaskOutput` 的 `[Task <id>]` + `status: failed|timeout|orphaned|killed` / 非零 `exit_code:` 形态。
- **不误报**：失败特征 SHALL 锚定行首；结果正文里出现的失败字样（如 `Grep` 命中的源码行）SHALL NOT 被判为失败；多行形态（`TaskOutput`）SHALL 以首行 `[Task …]` 为门，SHALL NOT 仅凭「某行写着 `status: failed`」判失败，且 SHALL 在 `stdout:` 行停止扫描（其后是命令输出正文，不是元数据）；裸 `Error` 前缀 SHALL 只在结果整体为单行时判失败（读一个首行写着 `Error:` 的文件不是失败，而后端的工具失败文案都是单行消息）；判定 SHALL 以**首个非空行**为准（结果可能以空行开头）。
- **等待超时**：等待后台任务的包装形态（`[Task <id> timeout] [Task <id>]`，`agent/loop.py::_wait_task_output`）SHALL 判为失败并把因由显示为 `timeout`——任务可能仍在跑，但这次调用确实没拿到结果。

依据（grill R-A/Q1/Q2）：`agent/loop.py` 的 `_text_prefix_guess` 与 registry/approval 的拒绝文案才是真实失败的主路径；漏掉它们会让「审批被拒」「权限拒绝」在折叠行上显示为成功，而 `Bash` 永远是单行 JSON 信封，把首行顶到摘要上等于删掉命令。

#### Scenario: 审批被拒的调用在折叠行上可见

- **GIVEN** 一次需要审批的工具调用被拒绝，服务端结果文本以 `[Approval denied:` 开头
- **WHEN** Chat 页面展示该工具结果
- **THEN** 该行 SHALL 带 `data-state="error"`
- **AND** 折叠摘要 SHALL 显示该失败首行
- **AND** 该行 SHALL NOT 自动展开

#### Scenario: 命令非零退出

- **GIVEN** `Bash` 返回 `{"exit_code": 1, ...}` 形式的单行 JSON 结果
- **WHEN** Chat 页面展示该工具结果
- **THEN** 该行 SHALL 带 `data-state="error"`
- **AND** 折叠摘要 SHALL 保留原始命令
- **AND** 行尾元数据 SHALL 给出退出码

#### Scenario: 成功结果中的失败字样不误报

- **GIVEN** `Grep` 成功返回，某命中行的正文里包含 `failed with exit status 128`
- **WHEN** Chat 页面展示该工具结果
- **THEN** 该行 SHALL 保持成功态
- **AND** 折叠摘要 SHALL 保留搜索 pattern 与作用域

### Requirement: 工具调用与结果按到达顺序配对

Web Chat SHALL 把 `tool_call` 与 `tool_result` 事件配成**同一行**，且配对方向 SHALL 为「最早未配对」；没有配对调用的结果 SHALL 自建一行而 SHALL NOT 被丢弃。run 结束时仍未配对的行 SHALL 被收尾标记，SHALL NOT 保持「运行中」或跨 run 残留。

具体地：

- **顺序**：同一 run 内按到达顺序 FIFO 配对；同名调用优先匹配同名未配对项。
- **兜底**：取不到未配对项时新建一行（覆盖参数解析失败路径的重排与重连补发）。
- **收尾**：`done` / `error` 事件到达时，剩余未配对行 SHALL 被标记为异常并清空队列，避免僵尸行认领下一轮的结果。
- **重绘**：`session_history` 与 `/clear` SHALL 清空未配对队列（消息区已整体重绘，行引用已失效）。

依据（grill Q4/D5）：`agent/loop.py` 的两处发射点都成对相邻，`_execute_tool_calls` 对每个 entry 恰好返回一条结果并按原顺序回放，所以「最早未配对」是正确的一侧；取最近会把同名多次调用整体错位。不新增协议 id 是本 change 的刻意取舍（无 id 也能配准，加了会把展示层 change 变成协议 change）。

#### Scenario: 同名多次调用按顺序配对

- **GIVEN** 同一轮里连续三次 `Read`（路径各不相同），结果按同样顺序到达
- **WHEN** Chat 页面渲染这些结果
- **THEN** 第 i 个结果 SHALL 落在第 i 行上
- **AND** 每行的折叠摘要 SHALL 保留各自调用的参数

#### Scenario: 结果先到

- **GIVEN** 收到一个 `tool_result` 事件但队列里没有未配对的调用
- **WHEN** Chat 页面渲染该结果
- **THEN** 页面 SHALL 新建一行承载它
- **AND** 该行 SHALL 同样默认折叠

#### Scenario: run 结束时收尾未配对行

- **GIVEN** 某次工具调用一直没有等到结果
- **WHEN** 该 run 的 `done` 或 `error` 事件到达
- **THEN** 该行 SHALL NOT 保持「运行中」
- **AND** 未配对队列 SHALL 被清空

### Requirement: 对话区以单列文档流展示，不使用聊天气泡

Web Chat 的对话区 SHALL 呈现为**单列定宽文档流**：assistant 正文无气泡底色与边框，用户轮为整列宽的输入块并带角色标签，system 提示居中；工具执行行 SHALL 作为同一列的兄弟节点按到达顺序排列。

#### Scenario: 用户轮不是右对齐气泡

- **GIVEN** Web Chat 已渲染一条用户消息
- **WHEN** 用户查看对话区
- **THEN** 用户消息 SHALL 占满正文列宽并带角色标签
- **AND** SHALL NOT 表现为右对齐的圆角气泡

#### Scenario: assistant 正文是文档流

- **GIVEN** assistant 回复包含段落与列表
- **WHEN** Web UI 渲染该回复
- **THEN** 正文 SHALL 无气泡底色与边框
- **AND** 其宽度 SHALL 与同列的工具执行行一致

### Requirement: 工具执行行在对话区与工作流抽屉间共享同一渲染口径

Web UI SHALL 用同一个渲染模块（`window.AsterwyndToolRows`）生成工具执行行，供对话区与工作流节点详情抽屉的「对话」标签页共用，SHALL NOT 在两处各写一份。

具体地：

- **共享模块**：摘要生成 SHALL 是 DOM 无关的纯函数（可被 node 直接单测），DOM 构建 SHALL 接受调用方注入的 `document`。
- **兼容类名**：工具行外壳 SHALL 保留 `tool-call-block` 类名（工作流抽屉的既有断言依赖），标题 SHALL 保留 `tool-name`。
- **截断提示可见**：工作流节点 transcript 的 `arguments_truncated` 提示 SHALL 渲染在**可见**位置（头部行），SHALL NOT 藏在折叠 body 内。

依据（grill Q3/D2/D10）：抽屉侧原先手搓同类名（注释自称"与主 chat 同口径"），口径漂移会让两个面慢慢分叉；截断提示此前写在 `hidden` body 里，用户永远看不到而 `text_content` 型断言照样绿。

#### Scenario: 抽屉与对话区同一行形态

- **GIVEN** 工作流节点详情抽屉的「对话」标签页渲染了一条工具调用
- **WHEN** 用户查看该调用
- **THEN** 该调用 SHALL 呈现为与对话区一致的单行折叠行
- **AND** 标题 SHALL 显示工具名

#### Scenario: 参数被投影截断时提示可见

- **GIVEN** 节点 transcript 的工具调用参数被后端投影截断（`arguments_truncated` 为 true）
- **WHEN** 抽屉渲染该调用
- **THEN** 折叠行上 SHALL 出现可见的截断提示
- **AND** 该提示 SHALL NOT 需要展开才能看到

### Requirement: 重连历史携带工具名以还原工具执行行

`session_history` 载荷 SHALL 携带每条消息的 `tool_call_id` 与 assistant 消息的 `tool_calls`（至少 `id` 与 `name`），使前端能把 `role: "tool"` 的历史消息还原成**带工具名与参数摘要**的折叠工具行。`role: "tool"` 的历史消息 SHALL NOT 被渲染成用户消息；工具名 SHALL NOT 通过新增 provider 字段或改变 provider 消息转换来获得。

具体地：

- **投影**：`tool_calls` 投影 SHALL 只含 `id` 与 `name`，SHALL NOT 外发 `arguments`（量级不可控，且历史补发在重连首屏关键路径上）。
- **降级**：拿不到对应 `tool_calls` 的历史工具消息 SHALL 退化为通用标题 + 结果首行摘要，SHALL NOT 抛错或丢行。
- **不变量**：历史消息的 `content` / `reasoning` / opaque 不外发等既有语义 SHALL 保持不变。

依据（grill Q6）：`Message` 已带 `tool_call_id` 与 `tool_calls`，成本是 `web/session.py` 一处载荷投影 + 前端一张 id→name 表，不是协议改造；不做则重连后 N 行一模一样的「工具结果」无法分辨。

#### Scenario: 重连后工具行显示真名

- **GIVEN** 历史里有 assistant 消息带 `tool_calls: [{id: "t1", name: "Bash"}]`，随后是对应的 `role: "tool"` 消息
- **WHEN** 前端渲染 `session_history`
- **THEN** 该工具行标题 SHALL 显示 `Bash`
- **AND** 折叠摘要 SHALL 降级为**结果首行**（历史投影只带 id/name，不含 `arguments`，参数摘要无法还原）
- **AND** 该消息 SHALL NOT 被渲染成用户消息

#### Scenario: 拿不到调用信息时降级

- **GIVEN** 历史里的 `role: "tool"` 消息没有 `tool_call_id`，或对应调用不在本次载荷中
- **WHEN** 前端渲染 `session_history`
- **THEN** 该行标题 SHALL 退化为通用文案
- **AND** 折叠摘要 SHALL 取结果首行
- **AND** 渲染 SHALL NOT 抛异常
