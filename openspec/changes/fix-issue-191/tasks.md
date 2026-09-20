# Tasks — fix-issue-191

## 实现

- [ ] `web/static/chat.js`：`blur` 处理器归属化——闭包捕获 `tab`；`getActiveTab() !== tab` 与
      `document.activeElement === tab.inputEl` **两道**守卫（D3：第二道经 probe_f 实测为必要，
      非可选防御）；定时器句柄挂 `tab.blurHideTimer`
- [ ] `web/static/chat.js`：`switchTab` 记录 `wasActive = activeTabId === tabId`，**仅当
      `!wasActive`** 取消 incoming tab 挂起定时器并按输入内容收敛（D1b：无条件收敛会使
      `Escape` 后的 `Enter` 被吞，已独立复现）
- [ ] `web/static/chat.js`：`createTab` 初始化 `blurHideTimer: null`（保持 tab 对象字段完整）
- [ ] `web/static/chat.js`：`closeTab` 清理挂起定时器（避免已关闭 tab 的回调触发）

## 测试

- [ ] 测试装 **playwright 假时钟**（`page.clock.install()` + `fast_forward`），把「100ms 宽限窗
      是否到点」变成测试的确定输入，而不是机器负载的函数（R1 Issue 1 的根因修复）
- [ ] 改造 `test_multi_tab_slash_suggestion_isolation`：**断言点落在宽限窗之后**（推进虚拟时间），
      使其对旧实现确定性变红 —— 断言早于定时器会让坏实现「碰巧通过」（R1 Issue 1）
- [ ] 新增判别性回归 t_b：**非活跃标签页的失焦不干扰活跃标签页**（对旧实现 100% 失败）
- [ ] 新增判别性回归 t_c：**收起后切走再切回按输入内容重新判定**（对「归属化但无收敛」失败，
      是 A/half 与 B 的唯一区分器之一）
- [ ] 新增判别性回归 t_d：**按住标签页按钮越过宽限窗再切走、切回**（对「仅归属化」失败，
      A 的翻转缺陷判别器）
- [ ] 新增判别性回归：**关闭当前活跃标签页后被切到的标签页按输入内容收敛**（R1 Issue 2
      把原「关闭标签页」Scenario 从不可证伪改写为可证伪）
- [ ] 新增回归：**`Escape` 后 `Enter` 仍能发送消息**（对「无条件收敛」实现 100% 失败）
- [ ] 宽限窗测试用**同一 JS turn 内的 `blur()`+`focus()`**，不用两次 click（后者的墙钟裕度
      只有几十毫秒，本身就是一类新 flake —— R1 Issue 3）
- [ ] 测试 fixture 处理 tab id rekey 陷阱：操作前 `wait_for_function` 等到 `.session-tab` 的 id
      不再以 `new-` 开头（否则新测试自身成为新 flake 源）
- [ ] `tests/web_tests/` 浏览器等待加显式超时 + 可读失败信息（回应 issue #191「偶发失败无输出」）
- [ ] 变异验证：逐条把实现改回坏版本（无归属 / 无收敛 / 无条件收敛 / 去 activeElement 守卫）
      → 对应测试必须变红 → 还原后变绿
- [ ] 确定性验证：对旧实现连续复跑，**每次得到同一组红灯**（而非「三次里红一次」）
- [ ] 去 flake 验证：修复后在**同一台机器、同一序列**重复跑 N 次必须全绿
- [ ] 回归：`tests/web_tests/` 全量通过

## 文档

- [ ] `diagnosis.md`：bugfix 门禁要求的 6 章（Symptom / Reproduction / Evidence / Root Cause /
      Recommended Direction / Regression Tests）
- [ ] spec delta：`openspec/changes/fix-issue-191/specs/web-ui/spec.md` 新增
      「多标签页瞬态交互状态按标签页隔离」Requirement
- [ ] **当前规格同步**：将 ADDED Requirement 合入 `openspec/specs/web-ui/spec.md`
      （`openspec/specs/` 为受保护路径，需 `current_spec_synced` 事件）
- [ ] 关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与多标签页 / slash 建议 /
      浏览器测试 flake 相关的段落并更新本次造成的事实变化
- [ ] `docs/openspec-change-backlog.md` 登记本 change（已有 `backlog_updated` 事件），完成后移除

## 审阅闭环

- [x] Round 1 独立 subagent 审阅（`/review-loop`）→ **CHANGES_REQUESTED**
      （run `review-fix-issue-191-2026-09-20-r1`，报告 `reviews/building-review.md`）
- [x] Round 1 修复：Issue 1（isolation 测试断言早于定时器，对旧实现只 1/3 变红）→ 假时钟 +
      断言落在宽限窗之后；Issue 2（关闭标签页 Scenario 不可证伪）→ 改写为「关闭当前活跃
      标签页后收敛」并补判别测试；Issue 3（宽限窗测试自带墙钟依赖）→ 改同 turn 的
      `blur()`+`focus()`；Issue 5（Scenario 1 两档无覆盖）→ 断言点改为宽限窗之后
- [x] Round 2 独立 subagent 审阅（run `review-fix-issue-191-2026-09-20-r2`）→ **CHANGES_REQUESTED**
      （R1 的五条修复全部验证成立；R2 新发现一条确定性功能回归）
- [x] Round 2 修复：跨 tab 收敛路径下 `Enter` 被吞（D1c）——`Enter` 的意图判定从「列表是否
      可见」改为「应用建议项是否为空操作」；补 `test_escape_switch_back_then_enter_still_sends_message`；
      spec 第 3 段与 Scenario 4 的口径改写（原文与用户 Q1「弹回来」拍板自相矛盾）；
      假时钟 docstring 更正为 `pause_at`（实测 `install()` 不冻结墙钟）；
      `closeTab` 的 `activeTabId` 残留按 R2 建议记入 `docs/known-debt.md`（含结构化事件）
- [ ] Round 3 独立 subagent 审阅（复跑本文件 + ORIG/变异对照）
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash

## 验证

- [ ] 全量 pytest 通过
- [ ] OpenSpec strict validate 通过
- [ ] OpenSpec artifact checker 通过
