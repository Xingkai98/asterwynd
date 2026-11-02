# ADR-0009: 被打断 run 的 tool-call 配对恢复

- **Status**: accepted
- **Date**: 2026-11-02
- **Deciders**: issue #304 复现与设计环（grill + 设计对抗）

## Context

`AgentLoop` 先追加 assistant `tool_calls`（`agent/loop.py:867`），再 await 工具执行
（`agent/loop.py:1014`），最后才写 `tool_result`（`agent/loop.py:1099`）。在中间取消/
异常/群聊成员 240s 超时时，`run()` 的 `finally` 仍会落盘这份半截消息链
（`agent/loop.py:655-662`、`1744-1770`）。下一次请求把悬空 `tool_use` 原样发给
Anthropic/DeepSeek，上游返回 400，会话永久不可用。

已有 self-heal 只覆盖 reasoning / `cache_control` / 图片 400；`SessionStore.load`
（`agent/session.py:158-197`）与 resume 分支（`agent/loop.py:709-735`）不校验配对。
LangGraph、pydantic-ai、Google ADK、Bernstein、OpenAI Agents 的公开处置都把「补一条
明确标记的合成结果」作为主方向。

## Decision

在 **AgentLoop run 边界**做持久化自愈：

1. `AgentLoop._run` 起点（resume 重建后、进入迭代前）调用纯函数
   `repair_tool_call_pairing(messages)`，对**整条历史中不存在同 id 任何 tool 消息**的
   悬空调用补一条确定性、固定前缀 `[asterwynd:synthetic-tool-result] Error:` 的
   `tool` 消息；幂等、正常链零改动、发 `tool_pairing_repaired` 事件与 trace。
2. `AgentLoop.run()` 的 `finally` 第一条语句同步调用同一函数（cleanup/落盘前），
   覆盖取消/异常展开；SIGKILL/断电不在保证范围。
3. 合成结果在 Anthropic 序列化层带 `is_error: true`，OpenAI 用 `Error:` 文本前缀；
   不新增 `Message` 字段/持久化 schema。
4. orphan-before / misplaced-after 畸形链只 warning、不重复合成、不破坏性重排。
5. resume 的所有同步状态恢复（messages/todos/skills/user_system_prompt）移到
   `set_mode` await 之前，避免早期取消用截断历史覆盖快照。
6. 诊断性：HTTP >= 400 时读取并附加完整 body 到 `httpx.HTTPStatusError`；trace/Web
   展示有界原始 detail；群聊共享日志只写 `HTTP <status>` + 已知错误类型枚举。

## Alternatives Considered

| 备选方案 | 描述 | 拒绝原因 |
|----------|------|---------|
| 只在 `SessionStore.load` 修复 | 读快照时补配对 | 存储层应忠实；不落盘则每次重复；覆盖不了同进程下一次 run（`session.messages` 直接复用，`web/session.py:2149` 已清 resume_snapshot） |
| 只修 resume 分支 | 首次恢复时修复 | 同进程取消后的下一次 run 走普通 run 路径，不会进入 resume 分支；CLI 也只首轮 |
| 只在 provider 序列化层修复 | `_build_payload`/OpenAI 转换时临时补 | 只改临时 payload、不落盘；需同时改两套 provider；无自然事件出口；掩盖上层 bug |
| 丢弃悬空 assistant / tool_calls | 删除非法历史 | 不可逆丢失 assistant 文本/reasoning；静默篡改用户已看到的内容；无法告诉模型工具可能已部分执行 |
| 新增 `Message.is_error` 字段 | 持久化错误标记 | 改动持久化 schema；OpenAI 无对应字段；文本前缀 + Anthropic 序列化层 `is_error` 已足够 |

## Consequences

- 正面：中断后的会话可继续使用；正常链字节不变；修复幂等、确定、可观测。
- 负面：合成结果可能被模型当作真实结果（用 `is_error`/`Error:` 前缀缓解）；极端
  provider 输入（空/重复 id、已有 orphan/重复结果）不承诺修复；SIGKILL/断电仅靠
  run 起点兜底。
- 相关变更：`agent/message.py`、`agent/loop.py`、`agent/llm.py`、`agent/anthropic_llm.py`、
  `agent/openai_llm.py`、`agent/trace_recorder.py`、`web/session.py`、`web/static/chat.js`。

## Revisit Conditions

- [ ] 需要在 provider 协议层持久化 `is_error` 或更细的中断状态。
- [ ] 需要在 SIGKILL/断电后恢复未落盘的中断链（需增量快照机制）。
- [ ] 需要把 Case B（orphan/misplaced）也纳入自愈范围。
