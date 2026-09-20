# Design — fix-issue-191

## 背景：现状的状态机

`web/static/chat.js` 用「全局变量代理 active tab」的模式（`bindActiveTab` 在 `switchTab` 时
把 `slashSuggestionsEl` / `slashMatches` / `activeSlashIndex` / `userInput` 重指到新 tab 的对象）。
slash 建议的可见性由**三个互不同步的来源**共同决定：

| 来源 | 触发 | 作用对象 |
|---|---|---|
| `input` 事件 | 用户输入 | `updateSlashSuggestions()` → 读 `userInput`（当前 active），写 active 的列表 |
| `blur` 事件 | 输入框失焦 | 100ms 后调 `hideSlashSuggestions()` → **在触发时刻**读 active |
| `switchTab` | 切 tab | **完全不处理** slash 状态 |

第二、三行是错配所在：`blur` 是**异步**的（定时器），它在 `t+100ms` 读到的 active 未必是
挂起它的那个 tab；而 `switchTab` 又不修复这个状态，于是「谁失焦」与「收谁的列表」解耦。

## 决策 D1：可见性的权威模型

### 候选

**方案 A — 仅归属化 blur（最小）**

`blur` 闭包捕获 `tab`，触发时仅当 `getActiveTab() === tab` 才收起；`switchTab` 取消
incoming tab 的挂起定时器。

- **实测否决**（grill probe_p）：缺陷只是**翻转**而非消除。给 A 插桩后读到两个分支——
  间隔 0/60ms 时 `BLUR-armed → SWITCHTAB → SWITCHTAB`（定时器被取消，列表保留）；
  间隔 140/250ms（长按鼠标 >100ms 再释放）时 `BLUR-armed → TIMER-FIRED(activeIsMine=true) → SWITCHTAB`，
  定时器在 `switchTab` 之前触发、此刻 active **仍是原 tab** → 守卫放行 → 列表被收，
  切回时无重算 → **永久收起**。**否决**（「click 快就挂」变成「click 慢就挂」）。

**方案 B — 归属化 blur + `switchTab` 按输入内容重新求值**

在 A 的基础上，`switchTab` 对 incoming tab 增加一次**状态收敛**：

```js
bindActiveTab(tab);
clearTimeout(tab.blurHideTimer);  tab.blurHideTimer = null;
if (!wasActive && slashSuggestionsEl.hidden) updateSlashSuggestions();
```

- **采用**（带一处修正，见下）。理由：让 `switchTab` 成为该 tab 建议状态的**收敛点**——
  无论 `blur` 定时器落在切换的哪一侧、无论 click 快慢，切到某 tab 后的可见性都唯一由
  「该 tab 的输入内容」决定。
- 语义可一句话说清：**「建议列表反映你在该 tab 里输入的内容，与你在 tab 间切换的快慢无关。」**

**方案 C — 删除 blur 收起，纯内容推导**

可见性严格 = `f(active tab, input content)`，不再有 blur 路径。**否决**：点击页面别处不再
收起列表（列表可能长期遮挡消息区），超出 bugfix 边界。

### 选定：方案 B（含 D1b 修正）

## 决策 D1b：收敛必须只发生在「非 active → active」的切换上

**这是 grill 发现的真回归（R3），已由主 agent 独立复现。**

`inputEl` 的 keydown 处理器第一行就是 `switchTab(tab.id)`（`chat.js:157`），然后在**同一函数内**
读 `tab.slashSuggestionsEl.hidden` 决定按键归属：

```js
tab.inputEl.addEventListener('keydown', (e) => {
  switchTab(tab.id);                       // ← 无条件收敛会在这里复活列表
  const suggestions = tab.slashSuggestionsEl;
  if (suggestions && !suggestions.hidden) {
    if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); applySlashSuggestion(...); return; }
    if (e.key === 'Escape') { e.preventDefault(); hideSlashSuggestions(); return; }
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
```

若 `switchTab` 无条件重算：用户输入 `/status` → 按 `Escape` 收起 → 按 `Enter`，`switchTab`
先把列表复活，同一个 keydown 随即落入 `applySlashSuggestion` 分支 → **Enter 被永久吞掉，
消息发不出去**（输入框保持 `/status`，再按多少次都一样）。

**独立复现（主 agent，`/tmp/verify191.py`，同一序列对照三变体）**：

| 变体 | Enter 后用户消息数 | Enter 后输入框 | 结论 |
|---|---|---|---|
| ORIG | 2 | `''`（已发送并清空） | 正常 |
| B_NAIVE（无条件收敛） | **1** | `/status`（没发出去） | **回归** |
| B_GUARD（仅非 active→active 收敛） | 2 | `''` | 正常，且保留收敛语义 |

修正：`switchTab` 记录调用前的 `wasActive = activeTabId === tabId`，**只有 `!wasActive` 才收敛**。
语义：**收敛是「切换」的语义，不是「keydown 恰好调了 switchTab」的语义**——已经是当前 tab
时不存在需要收敛的切换。

## 决策 D1c：收敛重新展开的列表不得劫持下一次 `Enter`（R2 审阅发现）

D1b 只堵住了「同一标签页内按键」这条路径。**真正的跨 tab 路径仍在**（R2 审阅实测，3/3 确定性）：

```
tab2 输入 /status → 按 Escape 收起 → 切到 tab1 → 切回 tab2
  → 收敛按输入内容重新展开列表（用户已拍板「弹回来」，是预期行为）
  → 按 Enter
  → 列表可见，keydown 落入 applySlashSuggestion 分支
  → 而被选中的 /status 的 insert_text 就是 '/status'：**应用它等于什么都没做**，
     消息却发不出去（输入框仍留着 /status）
```

对照组实测（固定版修复前 / ORIG 基线）：

| 实现 | `/status` → Escape → 切走 → 切回 → Enter |
|---|---|
| ORIG | 消息正常发出 |
| 仅 D1b 修正 | **0 条发出**（被吞，3/3 确定性） |
| 加 D1c | 消息正常发出 |

**修正**：`Enter` 的意图判定不能只看「列表是否可见」，而要看**「应用建议项是不是空操作」**：

```js
const picked = slashMatches[activeSlashIndex];
const insertText = picked ? (picked.insert_text || picked.command) : null;
if (e.key === 'Enter' && !e.shiftKey
    && (insertText === null || userInput.value === insertText)) {
  sendMessage();   // 应用它是空操作 → 用户的意图是发送
  return;
}
applySlashSuggestion(activeSlashIndex);
```

保留 `Tab` / 值为真的 `Enter` 走原有的「应用建议项」语义（那是自动补全的既有行为）。
判据落在「输入框现有内容」上，而不是「用户是否曾按过 Escape」——后者要在 tab 上多存一个
状态位，且无法覆盖「输入内容本来就等于某条命令」的其他入口。

**规格同步**：spec 的 Requirement 第 3 段与 Scenario 4 一并改口径——从「收敛 SHALL NOT 覆盖
显式收起」（与用户 Q1「弹回来」的拍板自相矛盾）改为「收敛 SHALL NOT 由同标签页按键触发」+
「`Enter` 的意图判定 SHALL 以应用是否为空操作为准」。

## 决策 D2：`activeSlashIndex` 的重置

`if (hidden) updateSlashSuggestions()` 会把 `activeSlashIndex` 置 0。两种情形：

- 列表**被收起后**才重新求值 → 用户此前的方向键选中项已不可见，重置为 0 合理（「重新打开」）；
- 列表**一直展示** → 跳过重建，**选中项保留**（grill probe_c c5 实测：ORIG 切回后丢失选中项，
  B 保留）。

即：**只在「列表确实从无到有」时重置选中项**。

**读取对象无需额外处理**（grill probe_g 实测）：`bindActiveTab(tab)`（`chat.js:286` 调用，
定义在 `chat.js:184-191`）把 `slashMatches`/`activeSlashIndex`/`userInput`/`slashSuggestionsEl`
一次性重指到 incoming tab，**先于**任何求值执行。因此收敛读到的是 incoming tab 自己的输入，
不存在「读到 A 残留」的竞态。此点曾列为待验证风险，实测排除。

## 决策 D3：blur 守卫里的 `document.activeElement` 检查是**必要**的

```js
if (getActiveTab() !== tab) return;                  // 失焦的不是当前 tab → 不归我管
if (document.activeElement === tab.inputEl) return;  // 焦点已回到本 tab 输入框 → 不该收
```

**不是可选防御**（grill probe_f 实测）：去掉第二道守卫的变体（`B_no_focus_guard`）在
「点消息区真实失焦 → 100ms 内点回输入框」场景下 `hidden=true`——列表被错误收掉；带守卫的
B 为 `hidden=false`。该场景是真实操作（误点空白后马上回来继续输入），无守卫时列表会闪没。

## 决策 D4：测试侧的去时序化与失败信息

1. **去掉对间隔的依赖**：断言改为「切回后该 tab 的建议可见」——方案 B 下与 click 快慢无关。
2. **变异靶子必须能杀死 A 与 half**（grill R4 实测判别矩阵）：

   | 测试 | ORIG | half（只加 active 守卫） | A（归属化+取消，无重算） | B |
   |---|---|---|---|---|
   | t_a 切走即切回 | ✗ | ✗ | ✓ | ✓ |
   | t_b 跨 tab 失焦 | ✗ | ✓ | ✓ | ✓ |
   | **t_c 收起后切走切回按内容重算** | ✗ | ✗ | ✗ | **✓** |
   | **t_d 慢 click（mousedown 后按住 >100ms 再释放）** | ✗ | ✗ | ✗ | **✓** |

   Scenario 1/2 风格的两条**杀不死 half，也区分不出 A 与 B**；只有 t_c（收敛语义）与
   t_d（A 的翻转缺陷）是判别器。**本 change 必须包含 t_c 与 t_d。**
3. **新增 Escape→Enter 回归测试**：对 B 的朴素实现 100% 失败（见 D1b），锁住 D1b 的修正。
4. **显式超时 + 可读失败信息**：该文件的等待目前走 Playwright 默认 30s，超时信息只有选择器。
   引入薄封装，把「超时」变成带**期望描述 + tab 上下文**的失败信息，回应 issue #191 的
   「避免偶发失败无输出」。
5. **测试写法的隐含陷阱**（grill R8）：新建 tab 的 id 会从 `new-N` 被 rekey 成真实 session id
   （`chat.js:416-433`）。测试若提前缓存 `data-tab-id` 会拿到过期值而随机 flake。操作前须
   `wait_for_function` 等到 id 不再以 `new-` 开头——这与本 change 想根治的 flake 是**同类不同源**，
   必须一并处理，否则新测试自己就是新的 flake 源。

## 决策 D5：不做的取舍

- **不改 100ms 时长**：但**理由要改**（grill R7 实测）。proposal/design 原称该宽限窗服务于
  「建议项 mousedown → blur → click 的点击落地」——**该因果不成立**：建议项用 `mousedown` +
  `event.preventDefault()`（`chat.js:1768-1771`），焦点从未离开输入框，blur 计数恒为 **0**
  （probe_e/probe_o 在 ORIG/A/B 下一致），把 delay 改成 0 点建议项仍成功。
  保留 100ms 的**真实理由**是：它决定「失焦后多久内点回来不算数」这一用户可感知窗口，
  即 D3 第二道守卫的生效范围。结论不变，因果修正——否则后续维护者会基于错误因果去动这个常量。
- **不重构全局代理架构**：`bindActiveTab` 的全局变量模式覆盖 `chat.js` 全文，全量重构超出
  bugfix 边界，且回归面不可控。
- **不加测试重试**：会把真实 flake 掩盖成「重试通过」，与 issue #191 的验收口径相反。

## 风险

| 风险 | 说明 | 处置 |
|---|---|---|
| 用户可见行为变更（范围比初版公告更大） | 除「切走再切回」外，**「点空白/应用建议项收起后切回」也会按输入内容复活列表**（grill probe_c c3/c4 实测） | proposal 的对外公告已补全；Q1 由用户拍板语义 |
| 半吊子实现难以区分 | 「归属化但无收敛」会通过 Scenario 1/2 风格的断言 | 已由 t_c/t_d 两条判别测试覆盖，见 D4.2 |
| 收敛与 keydown 代理耦合 | Escape 后 Enter 静默失效 | 已由 D1b 修正 + 回归测试锁定 |
| spec Scenario 3 不可证伪 | 关闭 tab 的挂起回调只写到自身 detach 元素，ORIG 与 B 均不违反（grill R5 插桩实测） | 已改写为可证伪断言，见 spec delta |
| 该假设被其它浏览器测试共享 | 别的测试可能压在同一竞态上 | 跑全量 `tests/web_tests/` |

## 用户已拍板（grill 停轮确认，记录见 `reviews/grill-design.md` 的 `## User Confirmation`）

1. **「可见性由输入内容唯一决定」覆盖「用户主动收起」**——切走再切回时按输入内容重算，
   列表重新出现。**不做** `userDismissed` 区分：不引入「主动收起 vs 切换顺带收起」的分支，
   实现与测试面保持最小。（D1 的收敛语义即此，无需改动。）
2. **Escape→Enter 回归采用 D1b**：`switchTab` 只在 `!wasActive`（确实从别的 tab 切过来）
   时收敛，keydown 代理触发的同 tab `switchTab` 不收敛。
3. **门禁补齐**：补 `diagnosis.md` + tasks 的 current spec 同步任务（已落实）。

## Pre-Implementation Review

独立零记忆 grill（run `grill-fix-issue-191-2026-09-20-001`，见 `reviews/grill-design.md`）
产出 10 条 Confirmed Decisions + 3 条 Open Questions + 9 条风险。已整合：

- **必须改（已落实）**：R3 → 新增 D1b（收敛限定在非 active→active）并附主 agent 独立复现；
  R4 → D4.2 补 t_c/t_d 两条判别靶子；R5 → spec Scenario 3 改写为可证伪；
  R1/R2 → 补 `diagnosis.md` 与 tasks 的 spec-sync 任务（Q3 选法一）。
- **建议（已落实）**：R6 → proposal 补全对外公告范围；R7 → D5 修正 100ms 的因果；
  R8 → D4.5 记录 tab id rekey 陷阱；R9 → 归档事件清单。
- **排除的疑虑**：「switchTab 内读到 A 残留」（probe_g 实测读取对象正确）；
  D3 守卫非必要（probe_f 实测必要）。
- **grill 过程自纠**：grill 初版曾误判「design 对 A 的否决不成立」，重跑插桩（probe_p）后
  自行更正为「否决成立」——报告记录的是复验结果。
