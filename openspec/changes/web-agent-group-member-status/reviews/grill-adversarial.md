# 设计对抗收口: web-agent-group-member-status

## Reviewer

- **final round run id**: `adversarial-agent-paseo-r6`
- **时间**: 2026-10-20
- **零记忆**: 是（独立 paseo agent；只读 change 文档、issue #307、代码与既有规格）
- **性质**: 设计阶段对抗闭环（与实现后 `/review-loop` 同构，审设计不审代码）的最终收口报告。
  逐轮完整证据见同目录的 `grill-adversarial-r1.md` … `grill-adversarial-r6.md`；本文件只记录
  轮次、最终判定与残留登记。

## 轮次与收口

| 轮 | 报告 | verdict | 本轮主要产出 |
|---|---|---|---|
| R1 | `grill-adversarial-r1.md` | CHANGES_REQUESTED | 2 medium（F1 头部发言文案生命周期、F2 两条核心顺序不变量缺确定性测试）+ 11 low/nit；C1–C27 核对 |
| R2 | `grill-adversarial-r2.md` | CHANGES_REQUESTED | 2 medium（N1 收尾 flush/pop 顺序、N2 spec 无条件递增）+ 4 low；F1–F13 复核 |
| R3 | `grill-adversarial-r3.md` | CHANGES_REQUESTED | 1 high（X1 旧轮 finally 误删新一轮认领）+ 4 low |
| R4 | `grill-adversarial-r4.md` | CHANGES_REQUESTED | 2 medium（M1 WS 中间态测试可执行性、M2 「本轮结束」未在新轮清除）+ 1 low |
| R5 | `grill-adversarial-r5.md` | CHANGES_REQUESTED | 1 medium（T1 web 层事件→进度信号映射无确定性测试）+ 5 low + 3 nit |
| R6 | `grill-adversarial-r6.md` | **PASS** | T1/L1–L8 全部修复或合理处置；X1/N1–N6/F1–F13 关键项未被破坏；无新 high/medium |

## 最终验证（R6）

- **T1**：真实 `WebSessionRunner` + 真实 `AgentSession` + `ScriptedLLM(stream=True)` + 一次
  工具调用 + `on_progress` collector 的 web 层映射测试已写入 design Testing 3 / tasks 1.3.1；
  两次 LLM 调用各断言一次 `assistant_delta`，并含「删接线 / 删 `saw_delta` 复位 → 变红」的
  变异口径。FakeRunner 直调 `on_progress` 明确不能替代。
- **X1**：正常路径 reset（同步）→ 身份 release → flush；Cancelled/Exception 仅在
  `_rounds.get(room_id) is state` 时 reset + 调度强引用后台 teardown；已释放认领时只记录并
  re-raise；finally 的兜底 reset/release 都带身份判断。R1 已释放、R2 已认领、R1 收尾任务被
  取消的窗口不会改写 R2。
- **N1/N2**：termination/limit system 条目在 reset/pop 之前同步完成；pop 在 flush 之前；
  空表 no-op reset 返回当前 seq，新轮首个 `slot_started` 使旧终态 seq 严格更小。
- **协议**：全量表 + 房间级 `status_seq`；`member_status` 用 `<=` 丢弃、终态用 `<` 丢弃、
  相等应用；`room_state` 首帧 + 锁内同步构造快照 + 订阅后所有发送同一把锁 + try/finally
  unsubscribe；客户端水位在快照上重置（服务端重启 seq 变小也接受）。双标签页/慢客户端/
  服务端重启逐条核对未发现新的错误丢弃或清空。
- **规格/门禁**：两份 spec delta（ADDED + MODIFIED）自洽；OpenSpec strict validate
  **29/29 passed**；瘦 checker `--base-ref origin/master --require-base` **EXIT=0**；
  RIR `research_tier: full` 字段完整、无本地绝对路径；backlog 已登记 #307 且有
  `backlog_updated` 事件；benchmark smoke 按 checker 文本触发口径列入 tasks 6.6。

## R6 后顺手收敛的 low/nit（不改变 PASS）

- L-a：T1 两次 LLM 调用都产生可见 delta，各断言一次（已写入 design/tasks）。
- L-b：design Testing 5 补「迟到的 `round_ended(limit)` 仍重拉时间线」。
- L-c：编排器测试的「最终完整表」改为「终态快照（表为空 / 与 `status_snapshot()` 一致）」。
- L-d：浏览器测试补「发送失败提示在下一次成功后清除」。
- L-e：切换/关闭房间时清空状态表与水位（状态按房间作用域）。
- L-f：迟到 limit 重拉响应应用前校验 `state.activeRoom.id`。
- L-g：浏览器测试补断线「可能过期」标记的 class/属性断言。

## Verdict

**PASS**

- 设计对抗环收口：R6 无 high/medium；T1/L1–L8 已修复或合理处置；X1/N1–N6/F1–F13 关键项
  未被破坏；门禁通过。
- **PASS 不等于写码许可**：`design.md` 的 Open Questions Q1（移动端形态）、Q2（失败标记）、
  Q3（issue「多成员并发」的解释）仍需停轮由用户明确答复；答复写入
  `reviews/grill-design.md` 的 `## User Confirmation` 后，才允许进入实现/测试代码。
