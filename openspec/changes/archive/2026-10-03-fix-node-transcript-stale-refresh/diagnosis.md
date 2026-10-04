# Diagnosis: 节点 transcript 终态后停在运行中那一帧

## Symptom

workflow 跑完后，节点抽屉「对话」tab 仍显示**运行期**抓到的那一帧，不再更新：

- 用户实例（session `d67875d24fe8`、workflow `wf_0af2c86f`、节点 `producer`，`completed · 2m4s`）：
  - 「对话」里只有 3 条消息 / 2 个工具行（`Repo map`、`Bash ls -la && git status`），「最后更新于 10 分钟前」不动；
  - 「对话」顶部失败证据显示「**该 run 尚未结束**，执行 trace 按设计只在终态写入——现在还没有失败证据，不代表没有失败。」；
  - 同一节点的「任务」tab 写着「⚠ 本 run 内 4 次工具/LLM 失败 →「对话」tab 查看」，但「对话」里看不到任何失败条目（S2 与 S1 同源）。

## Reproduction

1. 起 web（`uv run asterwynd web`），让模型跑一个含 `peer-review`（producer/reviewer/gate）模板的 workflow，`producer` 单轮耗时可到分钟级。
2. **在 `producer` 仍在运行**时点该节点 → 切到「对话」tab（此时首次取数发生）。
3. 等整个 workflow 跑完，停留在同一个「对话」tab 观察：内容与「最后更新于」都不再变化。
4. 刷新浏览器页面后再点同一节点 → 「对话」立刻是完整内容（19 条消息 / 20 个工具行，失败证据变 `present` 并列出 4 条）。

## Evidence

**同节点重新取数的对照（在本机 8000 端口的同一进程上实测）**：`GET /api/sessions/d67875d24fe8/workflows/wf_0af2c86f/nodes/producer/transcript`

| | 抽屉里那一帧（缓存） | 重新取数 |
|---|---|---|
| `messages` | 3（system / user / 1×assistant） | **19**（system + user + 17×assistant） |
| `messages[].tool_calls` 合计 | 2 | **20** |
| 渲染出的工具行 | 2 | **20** |
| `failure_evidence.state` | `running` | `present`（4 条，全为 `tool_result` + `permission_denied`，tool `Bash`） |

那一帧的指纹是失败证据文案：`running` 态文案由后端 `web/session.py` 的
`_FAILURE_EVIDENCE_MESSAGES["running"]` = 「该 run 尚未结束，执行 trace 按设计只在终态写入……」
产生——**只有运行期才可能出现这句**，所以它证明该载荷是在 `producer` 还在跑时取的。

三个环节共同造成「永不更新」：

| # | 位置 | 事实 |
|---|------|------|
| 1 | `web/static/workflow_transcript.js::fetchTranscript` | 按 `workflowId::nodeId::subagentId` 缓存在**模块级 `cache` Map**；`ctx.force` 为假时命中缓存直接返回，不发请求 |
| 2 | 同上 ::`fetchTranscript` / 全文件 | `cache` **没有任何失效路径**（全文件搜不到 `cache.delete` / `cache.clear`），UI 上也没有刷新按钮（`dataset.action` 只有 `pause-transcript` / `transcript-back`） |
| 3 | `web/static/workflow_graph.js::transcriptRefreshDue` | 唯一绕过缓存的路径是 10s 轮询里的 `force: true`，而它 `if (!node \|\| isTerminalNodeStatus(node.status)) return false;`——**节点一终态就再也不重取** |

即：`3` 的规则假设「最后一次取数已经覆盖到 run 结束」，而 `1`/`2` 让「运行中取的那一帧」既不会被覆盖、也不会被清掉。

## Root Cause

**「终态后不再重取」这条刷新节律缺少终态补取（catch-up）。**

`openspec/specs/web-ui/spec.md` 的既有条款写的是「节点已到终态或用户暂停后 SHALL NOT 再重取」——这句在**最后一次取数晚于终态**时是对的，但没约束「最后一次取数早于终态」的情形；缓存无失效路径 + 无手动刷新入口把这一缺口放大成「永久停留」。

后端数据面**没有缺口**（同节点终态后重取即得完整 19 条），所以这是纯前端取数时机问题，不是投影/载荷问题。

## Recommended Direction

1. **终态补取一次**（D1）：`transcriptRefreshDue(node, opts)` 增补 `fetchedStatus`（取数那一刻的节点状态）。规则：节点已终态 **且** `fetchedStatus` 非终态 → 判为「该重取」；补取后缓存记录的是终态，故天然只补一次。
2. **抽屉重绘时也判补取**（D2）：`render()` 命中缓存前先判同一条件，命中即 `force` 重取——终态是**事件**，不必等下一个 10s tick。
3. **手动刷新入口**（D3）：对话区工具条加「刷新」按钮（清该节点缓存 + 重取），与「暂停/继续实时更新」并列。
4. **保留原意**：终态后不做周期性重取（无补取条件时不重取）、暂停态永不自动重取、簇虚拟化与三态载荷不动。

## Regression Tests

| 层级 | 用例 | 判据 |
|------|------|------|
| node 纯函数（`test_workflow_graph_ux_js.py`） | `transcriptRefreshDue` 终态补取矩阵 | 终态+缓存终态 → false；终态+缓存非终态 → true；终态+无缓存状态 → true；暂停优先于一切 → false；非终态 + <10s → false、≥10s → true |
| 浏览器（`test_workflow_graph_browser.py`） | 「运行中打开对话 tab → 推终态快照 → 自动补取到完整内容」 | 请求次数 ≥2，且面板出现第二次载荷才有的标记串；「最后更新于」推进 |
| 浏览器 | 「刷新」按钮清缓存重取 | 点击后请求次数 +1 且内容为最新载荷 |
| 变异 | 去掉补取条件 | 上面两条必须变红 |
| 回归 | 既有抽屉用例（`.tool-call-block`、截断提示、候选下钻、失败证据） | 保持绿 |
