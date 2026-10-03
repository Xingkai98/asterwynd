# E0 端到端对照记录（change tool-result-lifecycle，task 3.13 / 验收 E0）

日期: 2026-10-03。脚本: `scripts/e0_tool_result_lifecycle.py`（#278 复现器缩比版：单 agent
逐文件审查，N=30 × ~192KB 工具结果，`max_tokens=80_000`）。

**E0 是对照观测，不设门槛**（design D0/Risks）：RSS 受解释器内存池、cgroup 邻居、采样
时机影响，机制正确性由 GC 不变量（A0，机械证明）承担。以下数字如实记录。

## 参数

- N=30 个 ~192KB 工具结果（`BODY = "line of content here\n" × 9000`）。
- 三态：
  - **bounded**：真实 `AgentLoop`（剪枝 + 账本 bounded + spill + 压缩）；
  - **unbounded**：同一 `AgentLoop`，关掉本 change 的三处有界化（no-op 剪枝 +
    identity 账本 + `full_trace=True`）——真 A/B，差异只来自本 change；
  - **legacy**：change 前布局，直接构造三处（`messages` / `tool_calls_made` / `trace`）
    各持全文，不经 loop。

## 结果（每态独立进程，各跑两遍，数字稳定）

| 态 | RSS 增量 | tracemalloc cur | tracemalloc peak | **常驻文本** |
|---|---|---|---|---|
| bounded | 67844 / 67904 KB | 13438 KB | 20899 KB | **302 KB** |
| unbounded | 67116 / 67140 KB | 12995 KB | 20899 KB | **5906 KB** |
| legacy | 5956 / 5964 KB | 5805 KB | 5809 KB | **11075 KB** |

## 读法（如实）

1. **机制信号清晰**：常驻文本 bounded 302KB vs unbounded 5906KB（**−95%**）、vs legacy
   11075KB（**−97%**）。这正是 #278 的根因面（工具结果跨轮累积驻留），本 change 直接治它。
2. **RSS 在本缩比下不具区分度**（bounded/unbounded 均 ~67MB）：该量级由**每轮 tiktoken
   编码**（30 轮对 ~192KB 文本反复 `count_tokens`）与 asyncio/loop 脚手架主导，而非工具
   结果驻留——放大 N 才能让 5.7MB 的工具结果驻留从脚手架里浮出。**RSS 不作判据**，与
   design D0 一致；真实 OOM（#278 的 4GB cgroup）需要真实 LLM + 长程才能复现，非本缩比
   所能覆盖。
3. legacy 态 RSS 增量（~6MB）≈ 30×192KB，印证三处**共享同一对象**（不是三份拷贝），
   与 #282 的地基实测一致。

结论：机制正确性由 A0（GC 不变量，见 `tests/agent/test_tool_result_lifecycle_loop.py`）
机械承担；E0 如实显示「常驻工具结果文本有界」成立，RSS 层面缩比不可判。
