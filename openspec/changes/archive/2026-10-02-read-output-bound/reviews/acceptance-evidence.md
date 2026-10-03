# #280-B 验收证据：Read 默认输出上界

- **日期**：2026-10-02
- **模型**：`deepseek-v4-flash`（provider anthropic / `https://api.deepseek.com/anthropic`），`--mode bypass`
- **执行方**：主 session（复现器 `/tmp/t280b-e0/run_e0.py`，外部每 0.3s 采样 asterwynd 自身 RSS + cgroup）

## R0/R0b/R1/R2/R3（确定性，已在单测覆盖）

见 `tests/agent/tools/test_read_output_bound.py`（27 条）+ `building-review.md` 的实测复核：

| 指标 | 结果 |
|---|---|
| R0 单次超大文件受界 | `scheduler.py` 160,526 字节 → 返回 **79,020 字节**（首 2000 行）+ 显式截断注记 ✅ |
| R0b 逃逸面 | `limit=0` 不返回全文；`offset` 无 limit 不到 EOF；单行 4MB 被字节界截 ✅（审阅独立实测） |
| R1 ≤界逐字节=现状 | CRLF / 尾换行 / 空 / 非 UTF-8 / 普通 五类逐字节等于**当前无界输出** ✅ |
| R2 注记显式 | 注记含 `truncated=true` + next offset ✅ |
| R3 offset 回退修复 | 默认截断 `offset=0` 不覆盖显式分页进度 ✅（审阅端到端实测） |

## E0 端到端对照（**人工观测，非 CI 门槛**）

同一 #278 失败任务（145 文件逐文件架构审查，同提示词/模型），对拍 asterwynd 自身 RSS 峰值：

| | t | asterwynd 自身 RSS 峰值 | 备注 |
|---|---|---|---|
| **#278 基线**（无界 Read） | 528s | **1228MB** | 看门狗拦下 |
| **本 change 之后** | 742s | **1172MB** | cgroup 顶 3600 被我拦下（邻居 ~2.47G + asterwynd 1.17G） |

**结论：B 未使 RSS 峰值数量级下降（1172 vs 1228MB 同量级）。**

### 归因（为什么 B 不够）

B 只削「**单条**」Read 输出（>2000 行或 >128KB 才截）。而实测 `agent/` 145 个文件**只有 2 个超过 2000 行**（`scheduler.py` 3196、`subagents.py` 2361），绝大多数文件（中位 107 行）**照样全文进上下文**。⇒ **OOM 的主因是「跨轮/跨文件的累积驻留」，不是「单条峰值」**——B 治不到累积。

### 对 A（`agent-context-bound`）的判据

**E0 数据支持「A 必须做」**：只治单条不足以压住峰值；累积（messages 里多份中小工具结果 + `tool_calls_made` / trace 副本 + `_workflows`/`_sessions` 驻留）才是量级来源。**A 若做，须先按 #280 对抗验证的修正重写 design**（其 grill 的 Q6/Q3/Q4 已被证伪）。

### 保留

B 本身**仍值得合**：它治了单条上界与三个逃逸面（`limit=0`/`offset` 无 limit/少行超长行）、修了 offset 回退 bug——是**防御性改进**，只是不足以防 OOM。
