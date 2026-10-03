# Proposal: 节点 transcript 的终态补取（修「跑完后对话 tab 停在运行中那一帧」）

- 关联 issue：待创建（本机 `github.com:443` 不可达，已列为 `(post-merge)` 任务）。
- 相关既有 change：`enhance-workflow-graph-ux`（抽屉「对话」tab + 刷新节律 + 簇虚拟化，issue #197）、`fix-issue-215`（失败证据主体落在「对话」tab）。
- 用户报告：workflow 跑完后，节点抽屉的「对话」tab 仍停在运行中抓到的早期内容（只剩两条工具行），而「任务」tab 提示的「本 run 内 4 次工具/LLM 失败 → 对话 tab 查看」在里面也看不到。

## Change Type

- primary: bugfix
- secondary: []

## Why

用户可见的两个症状同源：

| 症状 | 表现 |
|------|------|
| S1 | `producer` 节点 `completed` 2m4s 后，抽屉「对话」里仍是 3 条消息 / 2 个工具行（`Repo map`、`Bash ls -la && git status`），「最后更新于 10 分钟前」不变 |
| S2 | 「任务」tab 写着「本 run 内 4 次工具/LLM 失败 →「对话」tab 查看」，但「对话」tab 里看不到任何失败条目 |

根因是**「终态后不再重取」这条刷新节律缺了补取**：若最后一次取数发生在节点终态**之前**，该帧会被永久缓存，而终态一到轮询就关掉了。

## What Changes

1. **终态补取一次**：`transcriptRefreshDue()` 增补「取数时的节点状态」这一输入——节点已终态**且**缓存取自非终态时 SHALL 判为「该重取」（补取后缓存记录的即为终态，因此天然只补一次）。
2. **抽屉重绘时同样判补取**：`render()` 命中缓存前先判上述条件，命中即强制重取，用户不必等 10s 轮询。
3. **手动刷新入口**：对话区工具条新增「刷新」按钮（清该节点的缓存并重取），给「暂停/继续实时更新」之外的逃生通道。
4. **不变**：
   - 终态后**不再周期性**重取（除非上面的补取条件成立）——原意（不打断阅读、不空转请求）保留；
   - 暂停态永不自动重取；
   - 簇虚拟化、失败证据渲染、三态 union 载荷都不动。

## Capabilities

### Modified Capabilities

- `web-ui`: 「workflow 节点详情面板」的刷新节律条款补上**终态补取**与**手动刷新**动作；其余（懒加载、定死节律、暂停语义、簇虚拟化）不变。

## Dependencies

- 无。纯前端（`workflow_graph.js` 的纯函数 + `workflow_transcript.js` 的取数/按钮）。

## Reference Implementation Research

- research_tier: light
- status: enabled
- reason: 常规功能修正——「长任务面板读到一半被终态卡住」是成熟监控/日志面板的常见形态，看业界既有做法即可，不需要完整横向调研；命中 `light` 判据（findings + design impact 必填、research questions 可省）。
- findings:
  - **GitHub Actions / CI 日志面板**：跑到终态时会**再拉一次**完整日志（用户看到的是「刷新到最终态」而不是停在最后一次轮询），并保留手动「Download/Refresh」入口；自动刷新只在非终态期间节流。
  - **Vercel / Netlify 部署日志**：终态事件本身就是一次「必须重取」的触发（终态是**事件**，不是「停止轮询」的理由）。
  - **本仓既有先例（强证据）**：`enhance-workflow-graph-ux` 的节点详情「任务/产出」两 tab 是**快照驱动**的，终态快照一到就重绘（`workflow.js::renderDrawer*` 每次快照重建面板）；只有「对话」tab 因为走了缓存 + 终态停轮询而落后。也就是说本仓自己的面板内就存在「其它 tab 已经更新、对话 tab 没更新」的不一致——这本身就是判据。
  - **本地参考仓库不可用不是豁免理由**：本 change 未依赖 `D:\code\deepseek-harness`（该参考仓库是 web transcript 展示形态的参考，与本 bug 无关；如实记录本次未使用它）。
- design impact:
  - D1（纯函数扩参）来自「CI 面板的另一条既有做法」：把「要不要重取」继续留在可单测的纯函数里，而不是散到定时器回调里。
  - D2（render 时也判补取）来自「终态是事件」这条：不必等下一个 10s tick。
  - D3（手动刷新）来自两个来源都保留逃生通道这一共同点。

## Impact Analysis

### 能力域

- `web-ui`：workflow 节点抽屉「对话」tab 的取数时机（终态补取 + 手动刷新）。不改载荷契约、不改后端。

### 代码

| 文件 | 改动 |
|------|------|
| `web/static/workflow_graph.js` | `transcriptRefreshDue(node, opts)` 增补 `fetchedStatus` 输入：终态 + 缓存取自非终态 → `true`。仍是纯函数（保持既有 node 单测可覆盖）。 |
| `web/static/workflow_transcript.js` | 取数时记下节点状态（`cacheStatus`）；`render()`/`paint()` 命中缓存前判补取；工具条新增「刷新」按钮（清缓存 + 重取）；`fetchedAt`/按钮文案同步。 |
| `web/static/index.html` | bump `workflow_graph.js?v=4`、`workflow_transcript.js?v=4`（两者原本都是 `?v=3`，构成缓存击穿串）。 |

### 测试

- 扩展 `tests/web_tests/test_workflow_graph_ux_js.py`：`transcriptRefreshDue` 的终态补取矩阵（终态+缓存终态→false；终态+缓存非终态→true；终态+无缓存状态→true 且只补一次；暂停优先；非终态仍按 10s 节律）。
- 扩展 `tests/web_tests/test_workflow_graph_browser.py`：一条端到端回归——「运行中打开对话 tab（首次载荷只有 2 行）→ 推终态快照 → 断言自动补取到完整内容（≥2 次请求 + 出现第二次载荷的标记串）」；再一条断言「刷新」按钮能清缓存并重取。
- 既有 `test_workflow_graph_browser.py` 的抽屉用例（含 `.tool-call-block` 与截断提示）SHALL 保持绿。
- 变异验证：把补取条件去掉 → 新用例必须变红。

### 文档

- `openspec/specs/web-ui/spec.md`：同步 delta（终态补取 + 手动刷新）。
- `docs/openspec-change-backlog.md`：立项入队、归档出队（受保护路径，各需结构化事件）。
- `README.md` / `README_EN.md`：扫描后按事实更新（抽屉刷新语义若被提及）。

### process

- 本机 GitHub 不可达 → issue 创建与 PR 推送列为 `(post-merge)`。

### 边界与非目标

- **不做**「终态后继续轮询」：那会破坏 10s 节律与「不打断阅读」的既定意图，也会给已结束的图空转请求。
- **不做** WebSocket 推送 transcript（把消息流也搬进图事件通道）：本 bug 用一次补取即可消除，推送方案会把载荷契约扩大一圈。
- **不改**后端 `build_node_transcript_payload` / `inspect_transcript`：已核实同一节点在终态后重新取数返回的是完整 19 条消息 / 20 个工具行，数据面没有缺口。
