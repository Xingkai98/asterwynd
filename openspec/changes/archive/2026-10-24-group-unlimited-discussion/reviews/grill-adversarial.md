# 设计对抗闭环（r1 → r2 → r3）：group-unlimited-discussion

## 结论

**PASS（r3 收口，2026-10-24）**。设计阶段对抗闭环共 3 轮，累计 2 个已收口轮（r2 收口批次 II、r3 收口批次 III），≤ 20 上限；无未清 medium+。逐轮证据：

- `notes/grill-adversarial-rounds/grill-adversarial-r1.md`：r1 = **CHANGES_REQUESTED**，批次 I 12 条（1 high + 11 medium）——链认领跨 await 窗口（I1）、single 分支未钉死（I2）、`rounds` 口径（I3）、事件发射点缺失（I4）、`pending_user_seqs` 写入时机（I5）、取消路径释放身份（I6）、续轮 slot 入参（I7）、`room_state` 恢复（I8）、delta 内矛盾（I9）、Q 裁决联动（I10）、tasks 字段（I11）、安全阀算术/reason 归属（I12）。
- `notes/grill-adversarial-rounds/grill-adversarial-r2.md`：r2 = **CHANGES_REQUESTED**（修复验证，基线 `3a2ca57c`）：I1–I9、I11–I12 ✅；I10 仅剩 delta 两处未同步 Q2 裁决（1 medium）；L1–L18 全部已修/可接受；新发现 N1–N13 均 low/deferred。
- `notes/grill-adversarial-rounds/grill-adversarial-r3.md`：r3 = **PASS**（修复验证，基线 `086bc57c`）：I10-a/I10-b 两处 medium 全清且与 design/modified 正文逐字一致；N1–N10 落地；r1 I1–I12 回归锚点全在位；无新 medium+（新增 N14–N16 low/nit，按批次冻结规则登记不阻塞）。

## 收口时登记未修项（均不阻塞）

| # | 严重度 | 位置 | 处置 |
|---|---|---|---|
| N11 | deferred low | design Decision 8 / `orchestrator.py:408-426` | 终局收尾 await 窗口内取消可能导致本轮终态不发（与既有单轮同形窗口），下一批决定是否补「已释放链的终态保底」。 |
| N13 | low（已修） | delta ADDED | `每轮结束` 已限定为「链内每轮结束（空成员退化路径除外）」。 |
| N14 | low（已修） | design Decision 3 4a | 轮间停止请求的收尾路径已钉死：不建新轮、不补发 `round_ended`、`rounds/rounds_started/turns` 保持上一轮值。 |
| N15 | nit（已修） | tasks 0.3 | 已记录 r1→r2→r3 轮次与本 PASS。 |
| N16 | nit | delta 文案 | 「该通知」指代可再收紧，语义已由 delta 场景/design Decision 8 钉死；不构成测试误写风险。 |

## 闭环出口

**PASS** —— 允许进入实现（building 在独立 worktree `D:\code\asterwynd-worktrees\group-unlimited-discussion`，分支 `group-unlimited-discussion/2026-10-24`）。
