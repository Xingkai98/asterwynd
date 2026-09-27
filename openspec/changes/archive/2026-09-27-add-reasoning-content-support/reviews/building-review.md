# Building Review: add-reasoning-content-support

## Reviewer

- run ids（三轮独立零记忆 subagent，未继承开发上下文）：
  - Round 1：`aadc79b9-c0fe-4af2-a3dd-ef717863278e`（head `20e6244`）
  - Round 2：`213ae12f-4923-4528-be7a-ce9cb4701e75`（head `b0cbeae`）
  - Round 3（封顶）：`de3e09e6-fa40-4e07-adda-10bd49d60f6b`（head `908eed0`）
- base: `5752ca0`（master）
- 审阅方法（作者自述一律不作依据）：三轮各自独立读代码 + 实跑测试 + **自己做变异验证**（改坏实现 → 观察是否变红 → `git checkout` 还原并核验）。Round 3 另跑「delta↔主 spec 逐字节比对」与「双 run 事件探针」。

## Verdict

**PASS**（Round 3 封顶轮，head `908eed0`）

三轮共发现 1 个「修复方向本身错误」+ 4 个真缺陷。**Round 3 确认三项 blocker 全部真修复且有变异证据**，全量回归无新增失败。

### 三轮的问题与闭合

| 轮次 | verdict | 关键发现 |
|---|---|---|
| R1 | CHANGES_REQUESTED | S-1 降级标志每回合重置（等于没记）；S-2 beta 通道是死开关；S-3 opaque 含 lone surrogate 时持久化崩；S-4 `5a4c87d` 把变异残留提交入库；S-5 六组变异存活（测试无判别力） |
| R2 | CHANGES_REQUESTED | **S-1 的修复方向本身就是错的**（回写放在父 task，ContextVar 单向导致永远读不到）；NEW-1 `test_multi_session.py` 替身漏改（CI 会挂）；NEW-2 主 spec 未同步但任务虚勾；NEW-3 降级状态无 UI 暴露 |
| R3 | **PASS** | 三项真修复 + 变异证据；NEW-3 发射已核实；仅余低优先级 UI 消费端缺失与 tasks 2.7 虚勾 |

### 收尾（R3 后）

R3 指出的两项残留均已处理：补 `chat.js` 的 `reasoning_disabled` 消费分支（Q8 的 UI 可见真正落地）；补 3 条 Playwright 断言（tasks 2.7 从虚勾变为真实覆盖），并做变异验证（折叠区默认展开 → 测试变红）。

## 关键问题的证据

**S-1（最严重，两轮才修对）**：
- R1 实测：`session.reasoning_disabled` 恒为 False —— ContextVar 按 task 隔离，web 下每回合新 task（`web/session.py` 的 `asyncio.create_task(run_agent())`），标志回到默认。
- R2 实测：作者的第一次修复把回写放在 `_run_session_locked` 的 finally（**父 task**），而 LLM 置位在 `run_agent` **子 task** —— ContextVar **单向**（父写子可见、子写父不可见），父 task 永远读到 False。R2 另指出该测试手工赋值、无判别力（删掉回写仍全绿）。
- R3 复核：回写已移到 `run_agent` 的 finally（子 task 内）；R3 独立跑两个变异（删回写 / 移回父 task）**双红**，证明测试确有判别力。

**S-4（流程缺陷）**：`5a4c87d` 把当时的变异残留（openai 的 reasoning 混入 `assistant_delta`）一起提交入库。根因是**变异验证与提交共用同一 worktree**。已由 `aef3c69` 修正，并把后续变异验证改为用独立副本。

**S-5（测试判别力）**：R1 实测 6 组变异存活；补齐后 R3 独立复跑，全部转红。

## Issues（全部已闭合）

| # | 轮次 | 严重度 | 问题 | 处置 |
|---|---|---|---|---|
| S-1 | R1+R2 | 严重 | 降级标志每回合重置（R1）；修复方向错误、回写落在父 task（R2） | 改为子 task 内回写；测试改走真实 `run_session` |
| S-2 | R1 | 严重 | beta 通道死开关，无生产调用方 | 新增 `ReasoningConfig` 接 config → `build_llm` → LLM 实例 |
| S-3 | R1 | 严重 | opaque 含 lone surrogate 时 `json.dump` 崩 | 降级丢弃该 opaque、保留 text；spec 明确不变量边界 |
| S-4 | R1 | 中 | 变异残留被提交入库 | `aef3c69` 修正；变异验证改用独立副本 |
| S-5 | R1 | 中 | 6 组变异存活（无判别性测试） | 补齐测试并逐条变异验证 |
| NEW-1 | R2 | 中 | `test_multi_session.py` 替身漏改（CI 挂） | 已修 + 全库扫描确认无遗漏 |
| NEW-2 | R2 | 中 | 主 spec 未同步但任务虚勾 | 实际同步（5 条 Requirement 逐字节一致）+ 写事件 |
| NEW-3 | R2+R3 | 低 | 降级状态无 UI 暴露（R2）；事件发出但前端无消费者（R3） | 补 `chat.js` 消费分支 |
| S-6 | R1 | 低 | anthropic 两份流式实现重复、无防漂移机制 | 已知取舍，未处理 |
| S-7 | R1+R3 | 低 | 折叠区无浏览器断言、tasks 2.7 虚勾 | 补 3 条 Playwright 断言 + 变异验证 |

## 三轮的独立验证

**R3 的最终确认**（封顶轮）：
- 全量 pytest（含 `tests/web_tests/`）：`2 failed, 3302 passed`，两条失败均为预先存在的环境问题（本机 `/tmp` 是 git 仓库），无本 change 引入的新失败。
- `tests/web_tests/`：423 passed。
- OpenSpec strict validate：29 passed / 0 failed；artifact checker：passed。
- delta↔主 spec 逐字节比对：5/5 Requirement `IDENTICAL`，无重复 Requirement。
- 双 run 事件探针：`reasoning_disabled` 事件恰好 1 次，`session.reasoning_disabled` 为 True。
- 变异：删回写 / 移回父 task → 双红（证明测试判别力）。

**收尾后补充**（`2600875`）：3 条浏览器测试通过（默认关闭 / 单击展开 / 无 reasoning 不渲染 / 降级可见），变异「折叠区默认展开」→ 变红。

**收尾后全量**：`3304 passed, 2 failed`（同两条环境失败）。
