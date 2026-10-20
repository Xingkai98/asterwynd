# Building Review R3: web-agent-group-member-status

## Reviewer

- run id: building-review-agent-paseo-r3
- 时间: 2026-10-20
- 零记忆: 是（reviewer ≠ author；只读代码/测试/规格，不继承开发上下文，未写实现或测试代码）
- 审阅范围: R2 修复 `1180cf1` vs R2 审阅点 `3d57059`；同时抽核
  `git diff origin/master...HEAD`（`48d25f0...1180cf1`）与 X1/N1–N6/F1–F13 关键不变量
- 工作区: review 开始时 clean；变异验证为「临时改动 → 跑测试 → 立即还原」，结束后
  `git diff --exit-code` 对三个静态文件为空，工作区仍 clean
- 全量 pytest 未重跑：`/tmp/pytest-full2.log` 时间为 12:03，早于修复提交 12:26；修复只触及
  前端静态文件与前端测试，已由本轮定向套件覆盖（见 R3-N1）

### 本轮独立执行的验证

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/agent/team tests/web_tests/test_group_chat_team.py tests/web_tests/test_group_chat_server.py tests/web_tests/test_group_status_js.py tests/web_tests/test_group_status_browser.py` | **265 passed / 0 failed**（16.00s；4 条浏览器测试真实运行 Chromium，含 390px，不是 skip） |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **29/29 passed**，exit 0 |
| `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | `Project rule checks passed`，**EXIT=0** |
| R2-F1/F2/F3 变异验证 | 见下表；F1 **未通过**，F2/F3 通过 |

### R3 变异验证结果

| 变异 | 测试 | 结果 | 结论 |
|---|---|---|---|
| 删除 `web/static/group.js:523` 的 `scroller.scrollLeft = previousScroll`（R2-F1 指定变异） | `test_group_presence_mobile_q1_strip` | **PASS（未变红）** | 断言**不能**钉住恢复逻辑；见 R3-F1 |
| 对照：把同一行改成 `scroller.scrollLeft = 0` | 同上 | **FAIL（变红）** | 测试管线正常，断言读到的是重绘后的真实值；测试只能捕获「显式归零」回归 |
| 删除 `web/static/style.css:2350-2357` 的 `prefers-reduced-motion` 规则 | 同上 | **FAIL（变红）** | R2-F2 的断言有效：390px 下 `.group-sidebar` 原本有 `transition: transform 0.18s` |
| 让 `mergeTimeline` 丢弃 `current`（只保留服务端条目） | `test_group_status_js.py` | **FAIL（变红）**（`test_merge_timeline_keeps_newer_entries_and_server_wins_same_seq`） | R2-F3 的「重拉期间新消息保留」有回归保护 |
| 独立 Chromium 探针（临时页面，不落仓库）：同步 `textContent=''` + 立即重建 | — | 自然行为：`scrollLeft` 40 → 40 | 解释了 F1 变异为何不红 |
| 同一探针：清空后读取 `scroller.scrollWidth` 强制布局再重建 | — | 清空后 `scrollLeft` 被钳制为 0 | 给出 R3-F1 的可落地修法（见下） |

## R2 批次逐项验证

| R2 finding | 判定 | 证据 |
|---|---|---|
| **R2-F1** presence 横滚保留回归 | **未闭合** | 断言已存在（`tests/web_tests/test_group_status_browser.py:330-347`：先设 `scrollLeft=40`，再推 `member_post`，断言仍为 40），实现也存在（`web/static/group.js:471-525`，恢复在 `:523`）。但指定变异（删恢复逻辑）**测试仍绿**：Chromium 对「清空子节点 + 同一任务内重建」本就不清 `scrollLeft`，因此该断言通过并不依赖恢复代码。见 R3-F1 |
| **R2-F2** reduced-motion | **已修复** | 规则存在：`web/static/style.css:2350-2357`（`.group-sidebar` / `.group-presence-row` / `.group-avatar` 禁用 animation/transition）；浏览器断言 `computed transitionDuration == "0s"` 且 presence 行仍可查询（`test_group_status_browser.py:349-355`）；删除规则即变红，断言非空满足 |
| **R2-F3（L2）** limit 重拉 seq 合并回归 | **已修复** | 纯函数 `mergeTimeline`（`web/static/group_status.js:139-150`）：`current` 先入 Map、`incoming` 后入 ⇒ 同 seq 服务端覆盖；`seq == null` 两侧都不进入 ⇒ 客户端合成条目被权威时间线替换；按 `Number(seq)` 排序。`group.js:441-444` 已改为调用它（`Status` 缺失时退回整表替换）。node 单测 `test_group_status_js.py:163-181` 覆盖「重拉期间新消息保留」「同 seq 服务端覆盖」「null-seq 被替换」；丢弃 `current` 的变异变红 |
| **R2-N1** flush gate 用调用序号定位 | 未处理（nit） | `test_orchestrator.py:846-856` 仍以 `calls == 2` 认定 round-end flush；当前正确，落错窗口时后续断言仍会变红 |
| **R2-N2** 全量口径早于修复提交 | 未处理（nit） | 见 R3-N1 |

## M1/M2 与既有不变量复核（本轮未被破坏）

修复提交 `1180cf1` 只改 `web/static/*.js`、`web/static/style.css`、两份前端测试与
`reviews/building-review-r2.md`，未触及后端；以下测试本轮全部通过，且代码路径与 R2 记录一致：

| 不变量 | 证据 | 本轮结果 |
|---|---|---|
| N1 收尾窗口不吞新消息 | `test_orchestrator.py:837-876`（gate 第 2 次 `_flush_status_emits`；断言 M2 开 R2、M3 `queued=True`、放行后 R2 仍 active） | 通过 |
| X1 已释放认领的轮次被取消不影响 R2 | `test_orchestrator.py:798-824` | 通过 |
| WS 层 tool 状态 | `test_group_chat_server.py:387-423`（真实 WS + 流式 `ScriptedLLM` + Bash，断言出现 `phase="tool"`/`tools=["Bash"]`） | 通过 |
| 非流式无 typing | `test_group_chat_server.py:425-445`、`test_group_chat_team.py:935-951` | 通过 |
| 双标签页断线 `round_ended(cancelled)` | `test_group_chat_server.py:447-465` | 通过 |
| observer 两次 run 不重复 | `test_group_chat_team.py:905-932` | 通过 |
| resume 首个 thinking 来自 `iteration_started` | `test_orchestrator.py:879-890` | 通过 |
| 身份释放 / except/finally 身份判断 | `orchestrator.py:381-426`（reset → `is state` release → flush）、`:676-679` | 静态复核通过 |
| reset 先于 release、幂等 reset | `orchestrator.py:383-385`、`:643-659` | 静态复核通过 |
| 全量表 seq 与合并发射 | `orchestrator.py:566-621`（同步更新表/seq/脏标记，发射时同段读表与 seq） | 静态复核通过 |
| 握手锁与首帧顺序 | `web/server.py:104-132`（`_room_handshake`）、`:681-720`（每连接 `send_lock`；pong 也走 `send`） | 静态复核通过 |
| 头部文案单一归属 | `group.js:367-377`（`member_speaking` 只更新 presence，不写「正在发言...」）；`round_ended` 在 `:418-432` 按 `applied` 更新头部 | 静态复核通过 |

## 任务清单抽核（本轮相关）

| 任务 | 判定 | 说明 |
|---|---|---|
| 1.6 浏览器断言（presence 横滚 / reduced-motion） | **部分** | reduced-motion 已落地；横滚断言存在但变异不红（R3-F1） |
| 4.4 CSS（reduced-motion） | 通过 | 规则真实存在且经变异验证有效 |
| 1.5 JS 纯函数（mergeTimeline） | 通过 | 新增两条 node 单测，覆盖 F3 要求的三种语义 |
| 6.1–6.4 验证 | 通过 | 本轮重跑：265 passed / 29/29 / EXIT=0 |
| 7.x | 进行中 | 本轮 = 7.1 的收口验证 |

## Findings

### R3-F1（severity: low，但阻断 R2-F1 收口）presence 横滚回归测试是「假绿」，无法钉住恢复逻辑

- **问题**: R2-F1 的修复补了浏览器断言（`test_group_status_browser.py:330-347`），但按本轮
  指定口径做变异——删除 `web/static/group.js:523` 的 `scroller.scrollLeft = previousScroll`——
  测试**仍然通过**。原因经独立 Chromium 探针确认：实现是同步地
  `list.textContent = ''` 后立即重建（`group.js:477-512`），同一任务内没有布局计算，
  浏览器不会把 `scrollLeft` 钳制回 0，所以删除恢复行对可观察行为没有影响；测试断言的
  「重绘后仍为 40」由浏览器自然行为满足，而不是由被声称修复的代码满足。
- **失败场景**: 这不是当前用户可见 bug（恢复行仍在，可观察不变量也成立），而是回归保护
  失效：未来若有人在重绘前后插入一次强制布局/异步渲染（或换浏览器/换更新方式），
  `scrollLeft` 会被钳制，而测试仍可能以「恰好没触发钳制」的方式通过；反过来，删除恢复行
  也不会有人发现。R2-F1 要求的「删掉恢复逻辑 → 变红」未达成。
- **证据**: `web/static/group.js:471-525`（恢复在 `:523`）；
  `tests/web_tests/test_group_status_browser.py:330-347`；变异结果见上文两张表。
- **建议修法**: 在测试里让「清空列表」这一步可观察地钳制 `scrollLeft`，使恢复行成为唯一
  能把 40 还原的因素。已验证可行的形态（临时 Chromium 探针：自然行为 40→40；强制布局后
  清空即 0）：
  ```python
  await page.evaluate(
      """() => {
        const list = document.getElementById('group-presence-list');
        const scroller = document.getElementById('group-room-presence');
        const desc = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
        Object.defineProperty(list, 'textContent', {
          configurable: true,
          get() { return desc.get.call(this); },
          set(value) {
            desc.set.call(this, value);
            // 模拟会在清空后立即布局的浏览器：此时滚动位置被钳制到 0。
            if (value === '') { void scroller.scrollWidth; }
          },
        });
        scroller.scrollLeft = 40;
      }"""
  )
  ```
  然后在同一测试中推 `member_post`，断言最终仍为 40；删除恢复行后应变红。若团队认为该恢复行
  在当前 Chromium 下是冗余防御，也可以删除它并改断言口径，但必须同步修正 R2-F1 的验收表述，
  不能保留「删掉恢复逻辑会变红」的声称。

### R3-N1（nit）全量 pytest 证据仍早于修复提交

- `/tmp/pytest-full2.log`（12:03）早于 `1180cf1`（12:26）。本轮修复只改前端静态文件与前端
  测试，定向套件已覆盖全部改动面（265 passed），故不阻塞；若归档要求「修复后全量」证据，
  需在归档前再跑一次全量并记录（承接 R2-N2）。

### R3-N2（nit）`mergeTimeline` 的调用接线没有集成测试

- 纯函数本身有 node 回归且变异有效，`group.js:441-444` 的调用也可静态确认；但若有人把该处
  改回 `body.timeline || []`（整表替换），现有测试不会变红。R2-F3 的修法接受「抽纯函数 +
  node 单测」，故不阻塞；可在浏览器层用延迟 `/timeline` 响应 + 窗口内推一条新消息补一条竞态
  测试，作为后续加固。

## 已确认站得住的部分

- **R2-F2**：reduced-motion 规则真实存在（不是空满足），移动端 `.group-sidebar` 过渡为
  0.18s，规则删除即变红；presence 在 reduced-motion 下仍渲染。
- **R2-F3**：`mergeTimeline` 语义与测试一致——按 seq 合并、同 seq 服务端覆盖、null-seq
  客户端合成条目被权威时间线替换；实现与 `group.js` 接线一致。
- **M1/M2 与 X1/N1–N6/F1–F13 关键项**：后端未被本轮修改；N1 收尾窗口、WS tool 状态、
  非流式无 typing、双标签页 cancelled、observer 两次 run、resume thinking 的回归测试全部
  通过；身份释放、reset-before-release、幂等 reset、全量表 seq、握手锁、头部文案均保持。
- **规格与门禁**：OpenSpec strict 29/29；瘦项目规则 checker EXIT=0。
- **工作区完整性**：变异验证后 `git diff --exit-code` 对改动文件为空，工作区 clean。

## 闭环出口

CHANGES_REQUESTED（轮内状态；R2-F1 未闭合）
- R2-F2、R2-F3 已修复且变异验证有效；M1/M2 与 X1/N1–N6/F1–F13 关键不变量未被破坏；
  本轮未发现新的 high/medium。
- **阻塞点**: R2-F1 的回归断言存在，但按指定变异（删除 `group.js:523` 的恢复逻辑）测试
  仍绿，属于假绿；不满足 R3 的 PASS 条件「R2-F1 已修复」。
- 收口动作: 按 R3-F1 建议给测试注入一次布局钳制（或等价方案），确认「删恢复逻辑 → 红、
  保留 → 绿」后再做一轮只验证本项的收口轮；不引入新批次。
