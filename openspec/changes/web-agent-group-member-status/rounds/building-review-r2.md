# Building Review R2: web-agent-group-member-status

## Reviewer

- run id: building-review-agent-paseo-r2
- 时间: 2026-10-20
- 零记忆: 是（reviewer ≠ author；只读代码/测试/规格，不继承开发上下文，未写实现或测试代码）
- 审阅范围: R1 修复 `3d57059` vs R1 实现 `7b6994d`；同时抽核
  `git diff origin/master...HEAD`（`48d25f0...3d57059`）与 X1/N1–N6/F1–F13 关键不变量
- 工作区: clean；HEAD `3d57059`；审阅期间未修改实现或测试文件

### 本轮独立执行的验证

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/agent/team tests/web_tests/test_group_chat_team.py tests/web_tests/test_group_chat_server.py tests/web_tests/test_group_status_js.py tests/web_tests/test_group_status_browser.py` | **263 passed**（16.75s；浏览器测试真实运行 Chromium，含 390px，不是 skip） |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **29/29 passed**，exit 0 |
| `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | **EXIT=0** |
| M1 变异复核（运行时 monkeypatch，不落盘） | 见下表 |
| 全量 pytest | 按任务指示未重跑；`/tmp/pytest-full2.log` 时间 12:03 **早于修复提交 12:21**，故作者的全量口径是修复前树。定向前后覆盖了本轮修改面，未见失败 |

M1 变异复核结果（对 `test_message_during_round_end_flush_starts_new_round` 的行为等价模拟）：

| 变体 | R2 是否启动 | M3 是否 queued 进 R2 | R1 返回后 R2 是否仍 active | 测试预期 |
|---|---|---|---|---|
| 原实现 | 是 | 是 | 是 | 绿 |
| `_release_round` 移到 flush 之后 | **否**（M2 被吞进 R1） | 是 | **否** | 红 |
| 去掉 `is state` 身份判断 | 是 | 是 | **否**（R2 认领被旧轮 finally 删除） | 红 |

## R1 批次逐项验证

| R1 finding | 判定 | 证据 |
|---|---|---|
| **M1** N1 收尾窗口回归缺失 | **已修复** | `tests/agent/team/test_orchestrator.py:836-876`：gate 的是 `_flush_status_emits` 的第 2 次调用（成员终态 flush 是第 1 次，round-end flush 是第 2 次），不是 review；断言 M2 开 R2、M3 `queued=True`、放行 R1 flush 后 `is_round_active` 仍为 True；变异复核两向均变红（上表） |
| **M2** WS/生命周期/resume 断言缺失 | **已修复** | ① WS tool 状态：`test_group_chat_server.py:386-423`（真实房间 WS + 流式 `ScriptedLLM` + Bash，断言曾出现 `phase="tool"`、`tools=["Bash"]`，并收到 `member_post`）；② 非流式无 typing：`test_group_chat_server.py:425-445` 与 `test_group_chat_team.py:934-951`；③ 双标签页断线：`test_group_chat_server.py:447-465`（另一连接收到 `round_ended(termination="cancelled")` 与 int `status_seq`）；④ observer 两次 run 不重复：`test_group_chat_team.py:904-932`（若第 1 个 observer 泄漏，`first` 计数会 >1）；⑤ resume：`test_orchestrator.py:878-890`（脚本只有 `iteration_started`）；⑥ 12 条上限：`test_group_chat_server.py:243-253` 改为收 `round_ended` 即停 + 64 安全上限 |
| **M3** 浏览器断言缺失 | **部分修复（4/6）** | 已补：桌面三列几何 `test_group_status_browser.py:157-172`；迟到 `round_ended(limit)` 仍重拉时间线 `:354-377`；发送失败 `op` 清除 `:379-408`；断线 `stale` `:411-429`。**仍未补**：presence 横滚保留（见 R2-F1）、`prefers-reduced-motion`（见 R2-F2） |
| **L1** 快照未按房间成员过滤 | **已修复** | `agent/team/orchestrator.py:661-674` 已提交过滤；回归 `test_orchestrator.py:826-834` |
| **L2** limit 重拉整体替换时间线 | **代码已修，回归测试缺失** | `web/static/group.js:439-452` 按 seq 合并；但 `tests/` 无任何覆盖（grep `bySeq` 仅实现命中；`test_group_status_browser.py:332-408` 没有让重拉与新消息竞态）。见 R2-F3 |
| **L3** `tool_finished` name 兜底不可达 | **已修复** | `agent/team/member_status.py:120-138` 真正按 name 移除；单测 `test_member_status.py:143-150` |
| **L4** 死分支/未用常量 | **已修复** | `SIGNALS` 已删除；`orchestrator.py:574-575` 去掉 `is_idle` 死分支 |
| **L5** teardown 2s 是「每段 2s」 | **已修复** | `orchestrator.py:699-725` 外层 `wait_for(_flush_and_emit(), timeout=2.0)` 包住 flush + emit |

## 任务清单抽核（本轮修复相关）

| 任务 | 判定 | 说明 |
|---|---|---|
| 1.2.2 N1/X1 收尾窗口 | 通过 | `test_orchestrator.py:836-876`；X1 延伸「取消已释放认领的收尾」仍由 `:797-824` 覆盖 |
| 1.4 WS/集成 | 通过 | 见 M2 证据；64 安全上限已落地 |
| 1.6 浏览器 | **部分** | tasks 1.6 仍声称 presence 横滚保留与 reduced-motion 已测，但两者在 `test_group_status_browser.py` 中不存在 |
| 4.4 CSS | **部分** | `style.css:2205-2280` 无任何动效/过渡，所以 reduced-motion 当前是「空满足」；但 tasks 4.4 的声称与提交信息未按 R1 要求改写成空满足说明 |
| 6.1–6.4 验证 | 通过 | 本轮重跑：263 passed / 29/29 / EXIT=0 |
| 7.x | 进行中 | 本轮 = R2 修复验证 |

## Findings

### R2-F1（severity: low，但属于 R1-M3 的未闭合验收项）presence 横滚保留没有回归断言

- **问题**: R1-M3 明确要求「presence 在时间线重绘后保持横向 `scrollLeft`」；实现存在
  （`web/static/group.js:481-531`：保存 `previousScroll`，非 focus 重绘时恢复），但
  `test_group_status_browser.py` 没有任何断言覆盖该路径。现有移动端测试
  `:314-328` 只断言自动滚入后 `scrollLeft > 0`——这个断言在「恢复逻辑被删掉」时同样成立，
  因为自动滚入本身就会产生 `> 0`。
- **失败场景**: 用户把 5 人房间的横向条滑到「戊」，此时一条 `member_post`/`member_silent`
  到达，`renderMemberPresence()`（`focusActive` 为空）重建列表；若后续有人删掉
  `scroller.scrollLeft = previousScroll` 或改成先清空再取值，横条会跳回最左。现有测试全绿。
- **证据**: `web/static/group.js:478-532`；`tests/web_tests/test_group_status_browser.py:314-328`；
  `tasks.md:81-90`（1.6 声称已测）。
- **修法**: 在移动端测试里先手动设置一个与自动滚入不同的 `scrollLeft`（例如回到中间值），
  再推送一条不触发 focus 的 `member_post`（或 `member_silent`），断言 `scrollLeft` 不变；
  或在桌面宽条上同样断言。

### R2-F2（severity: low，但属于 R1-M3 的未闭合验收项）`prefers-reduced-motion` 的声称无落地

- **问题**: tasks 1.6（`tasks.md:81-90`）与 4.4（`tasks.md:161-165`）声称浏览器测试覆盖
  reduced-motion，修复提交信息也声称已补；但 `web/static/style.css` 没有任何
  `prefers-reduced-motion` 规则（grep 零命中），`tests/` 也没有相关断言。R1-M3 给过明确
  出口：若确无状态动效，应删除这些声称并写明「当前无状态动效，规则为空满足」。
- **失败场景**: 当前 presence 确实没有 animation/transition（`style.css:2205-2280`），行为上
  是空满足；但 tasks 与提交信息让后续维护者以为存在 reduced-motion 门禁。将来若给状态行
  加脉冲/过渡（很自然的产品迭代），没有任何测试或规则阻止它在 reduced-motion 下继续播放。
- **证据**: `web/static/style.css:2205-2280`（无 animation/transition）；全仓 grep
  `prefers-reduced-motion` 零命中；`tasks.md:81-90,161-165`。
- **修法**: 二选一——(a) 在 presence 样式加
  `@media (prefers-reduced-motion: reduce) { .group-presence-row { animation: none; transition: none; } }`
  并加浏览器断言（emulate reduced motion 后状态行无动画）；或 (b) 删除 tasks 4.4/1.6 的
  reduced-motion 声称，在 4.4 写明「当前无状态动效，规则空满足」，修正提交信息口径。

### R2-F3（severity: low，不阻塞本批收口）L2 的 seq 合并修复没有回归测试

- **问题**: R1-L2 建议「重拉响应按 seq 合并并加浏览器或 node 层回归测试」。代码已按 seq 合并
  （`web/static/group.js:439-452`），但没有任何测试在「重拉未返回期间到达新消息」的竞态下
  验证它。`test_group_status_late_limit_refetch_and_op_clear`（`:332-408`）只验证了
  LIMIT-MARKER 出现，没有并发新消息。
- **失败场景**: 若有人把 `.then` 改回 `state.timeline = body.timeline || []`，用户在
  limit 提示后立刻发的消息会先 append、再被快照覆盖而消失；当前测试不会变红。
- **证据**: `web/static/group.js:434-455`；`tests/web_tests/test_group_status_browser.py:332-408`；
  `tests/web_tests/test_group_status_js.py` 无 timeline 用例。
- **修法**: 浏览器层用 `page.route` 延迟 `/timeline` 响应，在延迟窗口内 `_push` 一条
  `user_message`，放行后断言该消息仍在时间线中；或抽纯函数合并逻辑到 `group_status.js`
  做 node 单测。

### R2-N1（nit）M1 回归以 flush 调用序号定位窗口

- **问题**: `test_orchestrator.py:846-856` 用 `calls == 2` 认定 round-end flush。当前正确，
  但若将来在成员终态前增加/减少一次 flush（例如 `_finish_member` 内部调整），gate 会落到
  错误窗口。虽然落错时后续断言仍会变红（不是假绿），但失败信息会指向无关位置。
- **建议**: 改成 R1 建议的语义条件，如 `if not orch.is_round_active(room_id)` 时 gate，
  并注释「此时已 reset+release」。

### R2-N2（nit）全量 pytest 口径早于修复提交

- `/tmp/pytest-full2.log`（12:03）早于 `3d57059`（12:21）。本轮按任务指示未重跑全量；
  定向套件覆盖了修复面。若收尾 PR 要求「修复后全量」证据，需再跑一次全量并记录。

## 已确认站得住的部分（未被本轮破坏）

- **M1/N1/X1 终态与收尾顺序**: 正常路径 reset → 身份 release → flush → review → 新 seq 终态
  （`orchestrator.py:381-398`）；取消/异常仅在仍持认领时 reset + 后台 teardown
  （`:408-426`）；`finally` 兜底 reset 与 release 都带身份判断。变异复核证明回归测试确实
  钉住这些不变量。
- **M2 web 层映射与生命周期**: `ProgressObserver` 完整 7 方法、逐 run 新实例、
  `try/finally` 身份摘除（`web/session.py:458-520,2166-2225`）；连续两次 run 无重复信号。
- **_seq 语义**: 房间级单调 seq + 全量表；终态用重置后 seq；空表重置幂等不递增
  （`orchestrator.py:643-659`）；快照一次同步取 (表, seq)（`:661-674`）；客户端
  `member_status` 用 `<=`、终态用 `<`、快照重置水位（`group_status.js:51-95`）。
- **快照过滤（L1）**: 只返回 `room.members` 中非 idle 成员，幽灵成员不再进入 `room_state`。
- **握手**: 持锁构造快照 → 订阅 → 发首帧 → 释放锁；失败 unsubscribe；pong 与广播共用发送锁
  （`web/server.py:104-132,682-752`）。
- **前端分发**: 状态事件只重绘 presence；`member_speaking` 仅 idle/未知时降级；终态按 seq
  守卫；迟到 limit 仍重拉；open/close room 清状态水位；epoch 守卫旧 socket；
  全部文本走 `textContent`（无 XSS 注入面）。
- **L3/L4/L5**: name 兜底可达且有单测；死符号已清理；teardown 整体 2s。
- **规格/门禁**: 两份 delta 与 current 一致；OpenSpec strict 29/29；瘦 checker EXIT=0；
  浏览器测试真实运行（桌面 1200px 与 390px），非 skip。

## 闭环出口

CHANGES_REQUESTED（轮内状态；R1 批次尚未收口）
- M1、M2 已修复且回归确定性成立（M1 经两向变异实测变红）；L1、L3、L4、L5 已修复；
  L2 代码已修但缺回归（low）；X1/N1–N6/F1–F13 关键不变量未被破坏；本轮未发现新的
  high/medium。
- **阻塞点**: R1-M3 的 6 项验收里仍有 2 项未落地（presence 横滚保留回归、reduced-motion
  的规则/测试/空满足说明）。按批次冻结口径，R1 的 medium 批次未全修，不能置 PASS。
- 收口动作: 补 R2-F1 与 R2-F2（二选一形态即可），可选补 R2-F3；之后开 R3 只验证本批修复，
  不引入新批次。
