# Design: 思维链的采集、回传与折叠展示（add-reasoning-content-support）

## Context

见 `proposal.md` 的 Why 与 Reference Implementation Research。核心事实：

- DeepSeek V4 系列**默认开启 thinking**，两条协议各按自身约定暴露（Anthropic 侧 `thinking` block、OpenAI 侧 `reasoning_content`）。
- 两条路径**都要求回传**，不回传 400。
- Anthropic 的 `signature` 是**不可解析的 opaque 载荷**，必须原样、顺序不变地回传。
- asterwynd 当前：Anthropic 侧零处理（靠 id 格式碰巧免于 400），OpenAI 侧采集回传但不展示。

本设计要解决的核心问题：**如何在不让消息模型退化成「一坨字符串」的前提下，同时满足「可展示」「可正确回传」「可持久化」三个诉求。**

## Goals / Non-Goals

### Goals

1. 四条路径（Anthropic 原生 / OpenAI 官方 / DS-Anthropic / DS-OpenAI）的 reasoning 都能被正确采集与回传。
2. 思维链在 Web 上可见：**通用折叠样式、默认关闭、单击展开**（用户已拍板）。
3. 消除 Anthropic 路径对「id 格式启发式」的隐式依赖（把碰巧可用变成显式正确）。
4. 无 reasoning 的 provider/模型行为零变化。

### Non-Goals

- 不提供「关闭 thinking」开关（Q3）。
- 不接入 OpenAI Responses API。
- 不做 reasoning 的跨协议转换（如把 Anthropic thinking 转成 OpenAI 上游可接受的形态）——本 change 只保证每条路径自身正确。
- 不改 tool-call 协议、approval、trace 语义。

## Decisions

### D1 消息模型：reasoning 结构化为「段」，段内区分文本与 opaque 载荷

**问题**：`signature` 不可解析、必须原样回传；`reasoning_content` 是可展示文本；Anthropic 的一段思考是「文本 + 签名」的组合。三者要能共存。

**候选**：

| | **A（选定）结构化 reasoning 段** | B 沿用单字符串 + 旁挂签名字段 | C 存 provider 原始块列表 |
|---|---|---|---|
| 形态 | `Message.reasoning: ReasoningBlock[]`（每段含 `text` + 可选 `opaque`） | `reasoning_content: str` + `reasoning_signature: str` | 直接存 provider 原生 dict 列表 |
| 可展示 | 直接取 `text` | 可取 | 需按 provider 解析 |
| 可回传 | 原样带 `opaque` | 带签名 | 原样回传 |
| 多段支持 | 支持（Anthropic 可有多段 thinking） | 不支持（只有一段） | 支持 |
| 跨协议 | 统一模型 | 统一模型 | 与 provider 强耦合，污染 Message |
| 复杂度 | 中 | 低 | 高 |

**选定 A**。理由：

1. **区分关注点**：`text` 供展示与日志，`opaque` 只回传、**永不展示、永不解析**（对应调研 F4 的 "SummaryText vs Opaque" 抽象）。
2. **多段**：Anthropic 的 content 数组可含多段 thinking（interleaved thinking），单字符串表达不了。
3. **不污染 Message**：C 会把 provider 细节渗进核心消息模型，使会话持久化格式绑定 provider。

**不变量**：`opaque` 载荷在采集→持久化→回放全链路**逐字节不变**（不 strip、不重排、不重新序列化）。

### D2 Anthropic 回传：按「最新轮必带、更早轮可省」实现，默认全带

**问题**：官方规则是「tool use 时最新 assistant 轮必须原样带 thinking；更早轮可省略（API 自动过滤）」。实现选哪边？

**选定**：**默认全带**（所有含 reasoning 的历史 assistant 轮都回传），仅在有明确理由时降级。

理由：

1. **更接近官方建议**：官方原文 "we suggest always passing back all thinking blocks to the API for any multi-turn conversation"。
2. **规避顺序陷阱**：官方要求「连续的 thinking 块序列必须与原始输出一致，不可重排」。全带避免了「取舍哪些轮」时可能引入的顺序错乱。
3. **成本可控**：官方说明历史轮 thinking 在缓存命中时按 input token 计费，且**上下文窗口计算里历史轮 thinking 会被剔除**——即全带不会挤占上下文预算。

**风险与退路**：D7 的错误自愈路径处理签名失配（`bound to a different conversation`）。

### D3 OpenAI 路径：仅接入统一模型，回传行为不变

`agent/openai_llm.py` 已经把 `reasoning_content` 采集、存入 `Message` 并回传，且实测能通过 DS 端点（带 tools 的多轮也通过）。本 change **不改其回传语义**，只把存储从裸字符串改为 D1 的结构化段，并接入前端事件。

**关键**：不引入「OpenAI 官方模型也回传 reasoning」之类的行为——官方 Chat Completions 根本不返回该字段，`reasoning_content` 缺席时链路自然退化为「无 reasoning」。

### D4 展示形态：统一折叠组件，默认关闭，单击展开

用户已拍板：**页面上做成通用样式、默认关闭、单击展开**。

实现要点：

- assistant 消息在**有 reasoning 时**才渲染该区；无则不渲染（对无 reasoning 的 provider 天然无副作用）。
- 折叠状态**默认 `closed`**；单击标题行切换。展开状态下流式增量实时追加。
- **跨 provider 统一样式**，不按 provider 分叉（这是用户明确要求「通用」的含义）。
- 该区与正文分离：思维链不混进 assistant 的 markdown 正文。

**为什么不做成默认展开**：think 内容通常很长，默认展开会把正文挤到屏幕外（调研 F5 的业界共识也是默认折叠或至少不与正文混排）。

### D5 流式：新增 reasoning 增量事件，与 text 增量并列

- `LLMStreamEvent` 增 reasoning 类型；Anthropic 的 `thinking_delta`、OpenAI 的 `reasoning_content` 各自映射到该类型。
- Loop 透传为独立事件（不复用 `assistant_delta`，否则前端无法区分「思考」与「回答」，会把思考渲染进正文）。

**为什么必须独立事件**：`assistant_delta` 的语义是「assistant 可见回复的增量」，前端据此写进 markdown 正文。思维链混进去会污染正文，且违背 D4 的「分离」要求。

### D6 compaction：旧轮 reasoning 可丢弃，最新轮必须保留

**问题**：`memory/manager.py` 的 compaction 会重写历史消息。若它丢掉了「最新 assistant 轮」的 thinking，下一轮请求会 400（官方规则）。

**选定**：compaction 时**保留最新 assistant 轮的 reasoning**；更早轮的 reasoning **可安全丢弃**（官方明确更早轮可省略）。

理由：官方「最新轮必须、更早轮可省」的规则恰好给出了这个自由度；丢弃旧轮 reasoning 还能省持久化体积与 input token。

**边界**：若 compaction 把「最新轮」也改写了（例如合并了多条 assistant 消息），需保证被改写后仍是「带 thinking 的最新轮」——具体策略在实现时按 compaction 的实际行为定，并在测试中固定。

### D7 错误自愈：识别 reasoning 相关 400 并降级重试

参照 Claude Code 的官方自愈策略（调研 F4）：

- 上游 400 且文案指向 **thinking 字段** → 该轮不带 thinking 重试。
- 上游 400 且文案指向 **signature** → 移除历史 thinking blocks 重试，并在该对话后续请求中持续不带（新回复仍可含 thinking）。

**前提**：错误体不被包装，否则文案匹配不上（本仓库当前不包装，需在实现时确认并加守护）。

**为什么需要**：D2 选择「全带」，而签名绑定对话（跨对话复用会失配）。自愈是 D2 风险的配套退路。

### D8 spec delta 的落点

- `agent-runtime`：reasoning 的采集、回传、流式事件与消息链不变量。
- `web-ui`：折叠展示区与前端消费。

**理由**：采集/回传是 runtime 契约，展示是 UI 契约；两者关注点不同，分属两个 capability。

## Open Questions

> **停轮确认项**：以下问题需用户明确答复后才进入实现。每条配具体场景例子。

### Q1 消息模型的字段命名与持久化兼容

**背景**：D1 选定结构化段，但字段名与旧数据兼容策略未定。

**具体场景**：现有一个旧会话 `messages.json`，其中某条 assistant 消息是
```json
{"role":"assistant","content":"...","reasoning_content":"我之前在想..."}
```
新模型下该字段如何表达？两种选择：

- **(a) 新增 `reasoning` 数组字段，旧字段 `reasoning_content` 保留为兼容读入**：旧会话加载时把 `reasoning_content` 转成一个单段。新写入只写 `reasoning`。→ 旧数据无损，但一段时期两种字段并存。
- **(b) 直接改名为 `reasoning`（数组），旧字段仅读取不写入**：更干净，但旧会话若被新版本重新保存，格式会变。

**推荐 (a)**。**影响**：会话持久化格式的向后兼容策略。

### Q2 Anthropic 的多段 thinking 与 signature 的配对粒度

**背景**：Anthropic 一个响应可能含多段 thinking，每段各有自己的 signature。DS 端点实测每段 signature 是 UUID 形态（36 字符）。

**具体场景**：一个响应含 `[thinking(文本A, 签名A), thinking(文本B, 签名B), tool_use, text]`。前端的折叠区应该：

- **(a) 合并成一个折叠区**，把所有段文本按序拼接展示。→ 展示简洁，但丢失「段」的边界。
- **(b) 每段一个折叠区**。→ 保留边界，但 UI 会碎（一个回复可能出现多个折叠块）。

**推荐 (a)**（展示合并、存储分段）。**影响**：D4 的实现与前端渲染粒度。

### Q3 是否同时提供「关闭 thinking」的能力

**背景**：DeepSeek 文档说 OpenAI 格式用 `{"thinking":{"type":"disabled"}}` / Anthropic 格式用 `{"reasoning":{"effort":"none"}}` 可关（但文档表格列归属有歧义）。关掉能省 token 预算（issue #249 的截断很可能就是 thinking 吃掉的）。

**具体场景**：用户跑一个简单任务（「把文件里的 a 改成 b」），当前每次请求都会先产生几百 token 的思考。如果提供开关，可以配置 `thinking: off` 省掉这部分成本。

**注意陷阱**：官方明确「禁用 thinking 后，**当轮 tool use 再传 thinking 内容会失败**」——所以「关」必须同时作用于采集与回传两侧。

**选项**：(a) 本 change 不做，另立 issue；(b) 本 change 一并做（范围变大，需处理上述陷阱）。

**推荐 (a)**。**影响**：本 change 的范围与工期。

### Q4 compaction 丢弃旧轮 reasoning 的边界

**背景**：D6 说「旧轮可丢、最新轮必须留」，但「最新轮」的判定在 compaction 后可能变化。

**具体场景**：历史有 3 轮 assistant 回复（各带 thinking），compaction 触发后只保留最近 1 轮。此时「最新 assistant 轮的 thinking」应指向**保留下来的那条**；若 compaction 把它也重写了（如合并多条），签名会失配 → 下一轮 400。

**选项**：(a) compaction 无条件保留最新轮的 reasoning 原样不动；(b) compaction 时丢弃所有 reasoning，并接受「最新轮无 thinking 可回传」（此时若端点强校验则 400，走 D7 自愈）。

**推荐 (a)**。**影响**：compaction 实现与 D7 自愈的触发频率。

## Pre-Implementation Review

（待 grill 后填写。）

## Risks / Trade-offs

- **R1 签名失配**：D2 全带策略下，若历史被重写（compaction / 跨会话复用），签名可能失配 → 400。退路是 D7 自愈。
- **R2 DS 端点的未文档化依赖**：id 格式启发式是实测发现、非官方文档。本 change 让它变成「显式回传、不依赖启发式」，但**该启发式本身的行为可能变化**，需在实现时以端到端测试固定当前行为。
- **R3 持久化体积**：全带 reasoning 会增大 `messages.json`。D6 的「旧轮可丢」缓解，但需实测体积影响。
- **R4 前端性能**：长思维链的流式增量若逐字符触发 reflow 会影响大输出场景。实现需注意增量写入策略（参考既有 `assistant_delta` 的处理方式）。
- **R5 跨 provider 样式统一的代价**：不同 provider 的 reasoning 形态不同（有的无签名、有的是纯文本），统一组件需容忍字段缺席。

## Testing Strategy

TDD（先写失败测试）：

1. **采集**：Anthropic 流式喂 `thinking_delta` + `signature_delta` → 断言 reasoning 段含正确文本与 opaque 载荷。
2. **回传（Anthropic）**：构造含 thinking 的历史 assistant 消息 → `_build_payload` 断言发出带 `signature` 的 thinking block。
3. **回传（OpenAI）**：既有行为回归（`reasoning_content` 仍回传）。
4. **展示**：前端回归——有 reasoning 时渲染折叠区、默认 `closed`、单击后 `open`、无 reasoning 时不渲染。
5. **流式**：reasoning 增量事件在正文之前到达且不混入 `assistant_delta`。
6. **不回归**：无 reasoning 的 provider/模型，全链路逐字不变。

判别力验证：每条测试做变异验证（改坏实现 → 必红）。
