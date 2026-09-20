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

- [ ] 改造 `test_multi_tab_slash_suggestion_isolation`：去掉对两次 click 间隔的墙钟依赖，
      断言「切回后建议可见」，并显式覆盖「间隔短于宽限期」（原失败档位）
- [ ] 新增判别性回归 t_b：**非活跃标签页的失焦不干扰活跃标签页**（对旧实现 100% 失败）
- [ ] 新增判别性回归 t_c：**收起后切走再切回按输入内容重新判定**（对「归属化但无收敛」失败，
      是 A/half 与 B 的唯一区分器之一）
- [ ] 新增判别性回归 t_d：**慢 click（mousedown 后按住 >100ms 再释放）后切回**（对「仅归属化」
      失败，A 的翻转缺陷判别器）
- [ ] 新增回归：**`Escape` 后 `Enter` 仍能发送消息**（对「无条件收敛」实现 100% 失败）
- [ ] 测试 fixture 处理 tab id rekey 陷阱：操作前 `wait_for_function` 等到 `.session-tab` 的 id
      不再以 `new-` 开头（否则新测试自身成为新 flake 源）
- [ ] `tests/web_tests/` 浏览器等待加显式超时 + 可读失败信息（回应 issue #191「偶发失败无输出」）
- [ ] 变异验证：逐条把实现改回坏版本（无归属 / 无收敛 / 无条件收敛 / 去 activeElement 守卫）
      → 对应测试必须变红 → 还原后变绿
- [ ] 去 flake 验证：修复后在**同一台机器、同一序列**重复跑 N 次（含 0ms 间隔档）必须全绿
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

- [ ] Round 1 独立 subagent 审阅（`/review-loop`）
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash

## 验证

- [ ] 全量 pytest 通过
- [ ] OpenSpec strict validate 通过
- [ ] OpenSpec artifact checker 通过
