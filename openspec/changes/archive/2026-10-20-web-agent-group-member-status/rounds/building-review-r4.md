# Building Review R4: web-agent-group-member-status

## Reviewer

- run id: building-review-agent-paseo-r4
- 时间: 2026-10-20
- 零记忆: 是（reviewer ≠ author；只读代码/测试/规格，不继承开发上下文，未写实现或测试代码）
- 审阅范围: R3-F1 收口轮，审阅点 `381bbc8`（修复 R3-F1）vs 基线 `1180cf1`；
  同时抽核 `git diff 1180cf1..381bbc8`、R2-F2/F3、M1/M2 与 X1/N1–N6/F1–F13 关键不变量
- 工作区: review 开始时 clean；变异验证为「备份 → 临时改动 → 跑测试 → 还原」，结束后
  备份文件 `cmp` 逐字一致、sha256 一致、`git diff --exit-code` 为空，工作区仍 clean

### 本轮独立执行的验证

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/agent/team tests/web_tests/test_group_chat_team.py tests/web_tests/test_group_chat_server.py tests/web_tests/test_group_status_js.py tests/web_tests/test_group_status_browser.py` | **265 passed / 0 failed / 0 skipped**（14.47s；浏览器测试真实运行 Chromium，非 skip） |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **29/29 passed**，**exit 0** |
| `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | `Project rule checks passed`，**EXIT=0** |
| R3-F1 指定变异（独立复现） | 见下表：**变异必红、还原必绿** |

## R3-F1 收口验证（本轮必核）

### 测试机制复核

`tests/web_tests/test_group_status_browser.py:330-348` 在
`#group-presence-list` 上用实例级 `Object.defineProperty` 覆盖 `textContent` setter：
每次赋值先调用原型 setter，随后读取 `scroller.scrollWidth` 强制布局。`renderMemberPresence`
（`web/static/group.js:471-490`）先捕获 `previousScroll`，再 `list.textContent = ''`；
该赋值触发注入 setter，清空后的强制布局把 `scrollLeft` 钳制为 0。随后重建行，并由
`group.js:523` 的 `scroller.scrollLeft = previousScroll;` 唯一恢复 40。

调用链确认：测试推的是 `member_post`（`test_group_status_browser.py:349-355`），
`handleRoomEvent` 的 `member_post` 分支调用 `renderMemberPresence()`（无 `focusActive`，
`group.js:363-367`），因此走 `else` 恢复分支而不是自动滚入分支。断言读的是重绘后的真实
`scrollLeft`（`test_group_status_browser.py:360-362`）。

### 独立变异结果

| 步骤 | 操作 | 结果 |
|---|---|---|
| 基线 | 未变异，跑 `test_group_presence_mobile_q1_strip` | **PASS**（1 passed，3.01s） |
| 变异 | `web/static/group.js:523` 的 `scroller.scrollLeft = previousScroll;` → `void previousScroll;` | **FAIL**：`test_group_status_browser.py:360: assert 0 == 40` |
| 还原 | 从备份 `cp` 回文件 | `CMP_IDENTICAL`；sha256 `6f28f19408806d345451bf1b646b53146e83993e8f06984c7fe6f64c6a82f27b` 与变异前一致；`git diff --exit-code` 干净 |
| 还原后 | 重跑同测试 | **PASS**（1 passed，2.93s） |

结论：R3-F1 描述的「假绿」已消除。恢复行成为唯一能把 40 还原的因素，删除/架空它即变红；
测试管线本身无问题。R2-F1 的回归保护口径「删恢复逻辑 → 红、保留 → 绿」本轮达成。

## 修复面与历史项复核

`git diff --stat 1180cf1..381bbc8` 仅两项：`tests/web_tests/test_group_status_browser.py`
（+17/-1）与 `reviews/building-review-r3.md`（新增）；`web/`、`agent/`、`scripts/` 零改动
（`git diff --name-only ... -- web/ agent/ scripts/` 为空）。因此后端与前端实现不变量
结构上未被本轮触碰，定向套件全绿可视为未破坏的实证。

| 历史项 | 证据 | 本轮结果 |
|---|---|---|
| **R2-F2** reduced-motion | `web/static/style.css:2350` 的 `@media (prefers-reduced-motion: reduce)` 仍在；浏览器断言 `test_group_status_browser.py:365-370`（`transitionDuration == "0s"` 且 presence 行仍渲染） | 测试存在，定向套件通过 |
| **R2-F3（L2）** mergeTimeline | `test_group_status_js.py:163-181`（新消息保留 / 同 seq 服务端覆盖 / null-seq 替换）仍在；`group.js` 接线未改 | 测试存在，定向套件通过 |
| **M1/M2（N1）** 收尾窗口不吞新消息 | `test_orchestrator.py:837` `test_message_during_round_end_flush_starts_new_round` | 通过 |
| **X1** 已释放认领的轮次被取消不影响新轮 | `test_orchestrator.py:798` `test_cancelling_released_round_does_not_touch_new_round` | 通过 |
| resume 首帧 thinking | `test_orchestrator.py:879` | 通过 |
| WS tool 状态 / 非流式无 typing / 双标签页 cancelled | `test_group_chat_server.py` 对应用例（R3 已列行号） | 定向套件通过 |
| observer 两次 run 不重复 | `test_group_chat_team.py` 对应用例（R3 已列行号） | 定向套件通过 |

以上用例均在 265 passed 的定向套件中真实执行，无 skip。

## 新洞扫查（high / medium）

本轮改动仅测试加固与报告，未发现新的 **high/medium** 问题。抽核实现与测试后确认：

- 注入 setter 挂在 `#group-presence-list` 实例上，`renderMemberPresence` 每次重新取同一元素，
  覆盖不会被重建丢失；`desc` 在覆盖前捕获原型描述符，getter/setter 委托正确。
- `member_post` 断言前，`renderTimeline()` 先于 `renderMemberPresence()` 执行，但同一任务内
  同步完成；`wait_for_function` 观测到时间线文本时 presence 重绘已完成，不存在竞态读窗口。
- 断言 `== 40` 与实现恢复值一致；强制布局注入未改变 `previousScroll` 的捕获时机（捕获发生在
  清空之前，变异已实证）。

### 低优先/ nit（不阻塞）

- **R4-N1（nit）**：注入 setter 对**任意** `textContent` 赋值都强制布局（当前实现只赋 `''`）。
  若未来 presence 渲染改用 `innerHTML`、分片/异步渲染或非空赋值路径，注入会失配，可能重新
  退化为假绿。建议后续把强制布局限定为 `value === ''` 并在测试注释中点明该假设。
- **R4-N2（nit）**：测试依赖 Chromium「清空后强制布局即钳制 `scrollLeft`」的具体时序；
  当前项目固定 Playwright Chromium，实测稳定（同一测试连续两次绿、变异一次红），但换引擎时
  需重验。
- **R3-N1（nit，承接）**：本轮未重跑全量 pytest；修复只触及前端测试与报告，定向套件已覆盖
  全部改动面。若归档要求「修复后全量」证据，归档前补跑并记录。
- **R3-N2（nit，承接）**：`mergeTimeline` 的 `group.js` 调用接线仍无集成测试（纯函数回归有效），
  可作为后续加固。

## 任务清单抽核（本轮相关）

| 任务 | 判定 | 说明 |
|---|---|---|
| 1.6 浏览器断言（presence 横滚 / reduced-motion） | **通过** | 横滚断言经独立变异验证有效（删恢复行必红）；reduced-motion 断言仍在且套件通过 |
| 4.4 CSS（reduced-motion） | 通过 | 规则仍在，行为未变 |
| 1.5 JS 纯函数（mergeTimeline） | 通过 | node 回归仍在，套件通过 |
| 6.1–6.4 验证 | 通过 | 265 passed / OpenSpec 29/29 exit 0 / 瘦 checker EXIT=0 |
| 7.1 收口验证 | 通过 | 本轮仅收口 R3-F1，无新批次 |

## 已确认站得住的部分

- **R3-F1 已闭合**：指定变异（删恢复逻辑）测试红在 `assert 0 == 40`；还原后文件逐字一致且测试绿。
- **R2-F2 / R2-F3**：回归测试与实现均在，定向套件通过；本轮实现面零改动。
- **M1/M2 与 X1/N1–N6/F1–F13 关键项**：未被本轮修改破坏，相关回归在定向套件中真实通过。
- **门禁**：OpenSpec strict 29/29（exit 0）；瘦项目规则 checker EXIT=0。
- **工作区完整性**：变异文件已逐字还原（`cmp` + sha256 + `git diff` 三重校验），工作区 clean。

## 闭环出口

PASS
- R3-F1 的变异验证在零记忆独立复现下成立：`void previousScroll;` ⇒ FAIL（`assert 0 == 40`），
  逐字还原 ⇒ PASS；定向套件 265 passed、OpenSpec strict 29/29、瘦 checker EXIT=0。
- 本轮未发现新的 high/medium；R2-F2/F3、M1/M2 与 X1/N1–N6/F1–F13 关键不变量未被破坏。
- 可收口；低优先项 R4-N1/R4-N2/R3-N1/R3-N2 仅登记，不阻断归档。
