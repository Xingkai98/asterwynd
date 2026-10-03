# 验收证据：harness 式 Web transcript

change `harness-style-web-transcript` · 分支 `harness-style-web-transcript/2026-10-03` · 2026-10-03

## 1. 真实链路 run（端到端，非合成事件）

用 `ScriptedLLM` 驱动**真实 AgentLoop + 真实工具 + 真实 WebSocket**，浏览器加载生产
`chat.js`/`tool_rows.js`/`style.css` 后发送一条消息，事件按生产路径抵达前端：

```
用户输入：读一下 README 的 Chat 界面那段，跑一下测试
                                  ↓（真实 WS 事件）
REAL RUN → rows: 2  hidden bodies: 2  visible chars: 265
states: ['Read:ok', 'Grep:ok']
  row: ▸ Read  README.md                        19.0k 字符 · 499 行
  row: ▸ Grep  Chat 界面 · README.md             5 字符
```

- 两次工具执行 = **两行**；`visible chars: 265`（19.0k 字符的结果正文**一个字符都没进可见文本**）。
- 两个 body 全部 `hidden`。
- 第三次调用是 `Bash`（高风险）→ 服务端发 `approval_request`，run 正常停在审批点（截图中的审批卡）。
- 截图：`transcript-real-run.png`（本目录）。

## 2. 合成事件观感验证（覆盖失败态与历史回放）

用 `window.AsterwyndChatTest.dispatch` 派发一份含「成功 / 失败 / 待办 / 思维链 / 长结果」
的 transcript，分别截折叠态与展开态：

- `transcript-collapsed.png`：一次 `Read`（9.0k 字符）+ `Grep`（成功）+ `Bash`
  （`{"exit_code": 1, …}` 结构化失败，行尾**红色** `exit 1 · 135 字符`、保留命令
  `uv run pytest tests/web_tests -q`）+ `Todo`，全部一行；展开态为
  `transcript-expanded.png`（参数缩进 JSON + 结果全文，头部行保留）。

## 3. 自动化测试

| 命令 | 结果 |
|------|------|
| `uv run pytest tests/web_tests/test_transcript_js.py` | **57 passed**（node + `vm` 纯函数层） |
| `uv run pytest tests/web_tests/test_transcript_view_browser.py` | **21 passed**（真实 Chromium） |
| `uv run pytest tests/web_tests/test_transcript_js.py tests/web_tests/test_transcript_view_browser.py tests/web_tests/test_workflow_graph_browser.py` | **106 passed**（含抽屉回归） |
| `uv run pytest tests/web_tests/test_server.py tests/web_tests/test_session.py tests/web_tests/test_workflow_graph_browser.py tests/web_tests/test_browser.py tests/web_tests/test_multi_session_browser.py tests/web_tests/test_reconnect_pending_interaction_browser.py tests/agent/test_tool_result_display.py` | 全绿，**唯一例外** `test_server.py::test_websocket_tool_events`（用例里跑 Unix `printf`，Windows 无此命令；**pristine master 同样失败**） |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 29 passed, 0 failed` |
| `uv run python scripts/check_openspec_artifacts.py --change harness-style-web-transcript` | 实现期通过；**当前 exit 1 且唯一错误是 `review manifest missing`**——这是预期状态：`reviews/` 下存在审阅报告但尚无 manifest，而 manifest 按纪律必须在 `tasks.md` 最终化（含归档 move）之后生成（见 §5 收尾顺序）。归档后生成 manifest 即恢复绿 |

### 本机环境导致的既有失败（与本次改动无关，已逐项在 pristine master 复现）

| 失败集 | 根因 |
|--------|------|
| `test_workflow_graph_js.py` / `test_workflow_graph_ux_js.py`（合计 27 项：ux 26 + graph 1） | 这两个测试文件的 node harness 用 `subprocess.run(..., text=True)` 而不指定编码，Windows 中文机器上按 GBK 解码 UTF-8 的 node 输出 → `UnicodeDecodeError`。pristine master 同样失败 |
| `test_server.py::test_websocket_tool_events` | 用例执行 `printf`（Unix 命令），Windows 无此命令 → 工具结果 `exit_code: 1`。pristine master 同样失败 |
| `asterwynd benchmark benchmarks/tasks --agent fake` | 读取任务文件的 `Path.read_text()` 用 locale 编码 → `UnicodeDecodeError`。pristine master 同命令逐字同样失败 |

（本次改动**修好**了其中一类：`test_server.py::test_web_static_assets_include_session_and_run_display`
原先在本机因 `read_text()` 缺省 GBK 而失败，现已显式 `encoding="utf-8"`，通过。）

## 4. 变异验证（新测试是否真有牙齿）

每一条都「改坏实现 → 对应用例必须变红 → 还原」，实测 5 条全部变红：

| 变异 | 变红的用例 |
|------|-----------|
| `createToolRow` 的 body 默认 `hidden = false` | `test_tool_rows_collapse_to_one_line_by_default` |
| 折叠行摘要改成「结果前 150 字符」 | 同上（总量 + 逐行结构断言同时命中） |
| `summarizeToolResult` 永不判失败 | 失败相关 node 用例（3 项） |
| `renderHistory` 去掉 `role === 'tool'` 分支 | `test_history_tool_messages_render_as_collapsed_rows` |
| 配对改取最近（`lastIndexOf`） | `test_calls_and_results_pair_in_arrival_order` |

独立审阅（`/review-loop` round 1）另做 5 条变异，同样全部变红：摘要泄漏结果前 150 字符
（可见文本 3279 > 1200 预算）、配对取最近、失败判定失效（8 node + 2 浏览器用例）、
`resultPre.textContent` → `innerHTML`（护栏）、在 `tool_rows.js` 内引入 `scrollHeight`（护栏）。

## 4b. 轮 1 审阅发现的缺陷与修复（round 2 前回改）

| 编号 | 缺陷 | 修复 |
|------|------|------|
| MEDIUM-1 | `TaskOutput` 失败被判成成功——它的结果是**多行** `[Task <id>]` + `status:` + `exit_code:`（非 JSON 信封、不匹配任何行首前缀），实测 `status: failed` 返回 `ok` | 新增 `taskFailure()`（首行 `[Task …]` 为门 + 限定行内扫 `status`/`exit_code`），4 条 node 用例（含「门不成立不得误报」）；订正 spec 里的事实错误 |
| MEDIUM-2 | spec 要求历史行显示参数摘要，但投影只发 id/name，二者互斥；实测摘要恒为空串 | 契约改为「摘要降级为结果首行」并真的实现（`argsSummary \|\| 结果首行`），补浏览器断言与 JSDoc |
| MEDIUM-3 | 「参数已截断」的可见性断言只有 `text_content`（连 hidden 一起取），用例名与断言相反 | 抽屉侧加 `inner_text` 可见性断言；聊天侧那条更名并写明它断言的是「未截断时无提示」 |
| HIGH-1 | `tasks.md` 的 5.1/5.3/5.4 标记与工作区状态矛盾 | 已在 tasks 里改回未勾并标注 `(closeout)`，写明**必须与终审 PASS 之后同步执行**（归档与 backlog 出队互为条件，manifest 也须在归档 move 后生成）；终审通过后执行并重新勾上 |

## 4c. 轮 2 审阅的复核与修复

轮 2 报告给出 `CHANGES_REQUESTED`，其中 1 条 HIGH 与实测不符，另有 7 条已逐条处理：

| 编号 | 报告结论 | 处理 |
|------|----------|------|
| Issue 1（HIGH） | `settleOrphanToolRows` 丢了清空队列的赋值，僵尸行会认领下一轮结果 | **该发现在其对应的 16:42:44 修订上确实成立**（审阅者随后用 `git diff --no-index` 提供了行级证据），但**当前工作树**（`chat.js:864`）该赋值在场，自写 Playwright 探针实跑报告描述的序列（`tool_call → done → 同名 tool_call → tool_result`）得到第 1 行 `error/未返回结果/摘要 run-1-stuck`、第 2 行 `ok/output-of-run-2`，**无错配**。根因是审阅者的变异还原用过期备份覆盖了实现方随后的落盘（见 §4d 末行），已重新落盘。**并按建议加固**：清空改用 `pendingToolRows.length = 0`（保持 per-tab 数组引用）、新增 `AsterwyndChatTest.pendingToolRowCount()` 探针、新增两条回归（队列深度 + 僵尸行不得认领下一轮结果）；变异验证：去掉清空后两条用例同时变红 |
| Issue 2（MEDIUM） | tasks 三个假勾选 | 已改回未勾 + `(closeout)` 标注（见 §4b HIGH-1） |
| Issue 3（LOW） | `onclose`/`onerror` 仍对已关闭 tab 写全局 chrome | 已把整段连接结果处理纳入 `tabs.has(tab.id)` 守卫 |
| Issue 4（LOW） | `dataset.summarySource` 只写不读 | 已删除 |
| Issue 5（LOW） | `structured` 文档口径、`firstLine(lines.join('\n'))`、`name` 未用 | 已订正 / 简化 / 注明保留参数位 |
| Issue 6（LOW） | 文档计数与改动清单漂移 | 已订正（浏览器用例计数、把 `test_workflow_graph_browser.py` 列入被修改的测试） |
| Issue 7（LOW） | 4 条规格条款只有实现没有断言 | 已补：结果 HTML 按纯文本（无元素注入、`onerror` 不执行）、行高恒定（`bounding_box` ≤26px）、单列文档流（`align-self` + 无底色 + 左边界对齐）、思维链折叠态单行高度 |
| Issue 8（LOW，流程） | 实现先于 grill | 已记入 `docs/known-debt.md`（受保护路径，附 `protected_artifact_explained` 事件） |

## 4d. 轮 3/4 审阅的新发现与修复

| 编号 | 缺陷（独立审阅在浏览器端复现） | 修复 |
|------|------------------------------|------|
| MEDIUM | **`TaskOutput` 的 stdout 正文被当成元数据**：`_format_task_output` 把 stdout 拼在 `stdout: ` 之后、内容可再带换行 → 「成功但恰好打印了 `status: failed`」被判红 | 扫描在 `^stdout:` 收尾；新增 node 用例 |
| MEDIUM | **浏览器族失败文案未覆盖**：`[Browser Error: …]` / `[Browser not available: …]` / `[URL denied: …]`（真实产生方 `browser_*.py`、`browser/session.py`；后端 `_text_prefix_guess` 也没覆盖）→ 浏览器失败显示成成功 | 并入前缀集 + 3 条 node 用例 + 订正 spec 前缀清单 |
| MEDIUM | **裸 `Error:` 前缀与文件内容不可区分**：读一个首行写着 `Error:` 的文件被判失败并顶掉路径摘要（违反 spec 的「不误报」） | 裸前缀只在结果整体为单行时判失败（方括号/`Traceback` 不受限）+ node 用例 + 订正 spec |
| LOW | §8.1 的 `onclose` 守卫缺断言 | 新增多 tab 用例（关掉一个 tab 后另一 tab 状态仍是 `connected`）；变异验证：去掉守卫 → 变红 |
| 环境 | 审阅者的变异还原会覆盖实现方随后的落盘（本轮实际发生：`onclose` 守卫与 `length = 0` 被还原掉） | 逐文件标记扫描确认全部落盘在盘上；冻结窗口纪律与还原方式建议记入 tasks §8.4/§9.5 |

## 5. 已知边界

- 本机无 LLM API key（无 `.env`、无相关环境变量），因此**没有**真实模型 run 的验收；
  第 1 节的端到端证据用 `ScriptedLLM` 驱动真实 loop/工具/WS/前端。
- 历史工具行的工具名依赖 `session_history` 的 `tool_calls` 投影；拿不到时降级为
  「工具结果」+ 结果首行摘要（已有用例覆盖降级路径）。
- 大结果仍会把全文写进**折叠的** DOM（上限 200000 字符）；重连时一次性渲染全部历史
  工具行是已知的后续优化点（惰性渲染），已在 design 的 R7 记录。
