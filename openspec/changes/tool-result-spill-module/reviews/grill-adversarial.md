# Adversarial Review: tool-result-spill-module (设计阶段)

> 独立零记忆设计阶段对抗审阅者产出（issue #298 设计阶段审阅闭环）。姿态：默认 `grill-design.md`
> 的结论可能站不住，逐条尝试证伪。基线 master @ 97b0370（worktree 分支 `tool-result-spill-module/2026-10-07`）。
> 本文所有行号经**亲自**读源码核验，非引用 grill 的行号。审设计不写实现。

## Verdict

- **CHANGES_REQUESTED**——grill 的事实类 Findings（F1–F9）与大部分 Confirmed Decisions 经对抗后成立，
  但 **Q2（谁持有 spiller）被错误分类为「用户架构偏好」**：它由 proposal/D2/e0 三处共同钉死，且与 Q1
  并非独立（Q1=保留委托 ⟹ Q2=MemoryManager 组合持有）。把二者当独立偏好抛给用户，用户若选「loop 自持」
  会**静默打断 e0 的 A/B 对照**（patch 变 no-op）并与 proposal 既有决策冲突——属「会导致实现走偏」的实质
  误判，需回改 `grill-design.md` 与 `design.md`。

## Refuted / Corrected

- **Q2（谁持有 spiller）归类错误**：grill 说「两者皆可运行且都能满足 D2，属架构归属偏好，代码判不了」
  （`grill-design.md:55`）。实际**代码/文档可判 —— MemoryManager 组合持有**，三条独立证据：
  - **proposal 已把它写成既成事实**：`proposal.md:39`「`MemoryManager` 组合并持有 spiller（`self.tool_result_spiller`）」。
    proposal 是需求权威；OQ2 的「loop 直接构造持有」选项不是被重新开启的备选，而是与 proposal 冲突的分叉。
  - **D2 的注入点本身就把构造放在 manager**：`design.md:63-68` 的示意代码写在 `manager.py`，闭包 `lambda text: _count_tokens(text)`
    必须定义在 manager 模块内才能 call-time 解析 `manager._count_tokens`（D2 自己的硬条件）。loop 自持则要把
    这层闭包复制到 loop，D2「单一注入点」的落点被搬离其自然位置。
  - **e0 的 patch 目标强约束**：`scripts/e0_tool_result_lifecycle.py:110` patch 的是 `loop.memory.prune_tool_results`。
    该 patch 生效的必要条件是 loop 运行时**经 `self.memory.*`** 发起剪枝（`agent/loop.py:1640`）。
    loop 若自持 `self._spiller.spill(...)`（`design.md:79-80` 的写法），patch 静默 no-op ⇒ `--mode unbounded` 不再
    关闭剪枝 ⇒ 真 A/B 失真。design Testing Strategy 第 3 条又明文要求「验证 monkeypatch 目标未破」，即设计自身
    承诺保 e0——在此承诺下 Q2 **唯一解**是 manager 组合持有。
- **F6 报道不全**：「谁持有 spiller」的表述冲突不止 `design.md`（D3 `self._spiller` vs OQ2 `self.tool_result_spiller`），
  **proposal 内部同样自相矛盾**——`proposal.md:39` 写 `self.tool_result_spiller`，`proposal.md:41` 又写 `self._spiller.mark(...)`。
  同一冲突横跨 proposal + design 两份文档 ⇒ 这是**文档一致的缺陷（bug）**，不是待用户裁决的架构偏好。
  grill 只点了 design 侧（`grill-design.md:67`），漏了 proposal 侧。
- **Q1 与 Q2 被当作独立问题呈报**：grill 分列 Q1（接口归属）与 Q2（所有权），各给「两者皆可」。
  实际二者**耦合**：若 Q1 选「保留薄委托」（grill 草案倾向、也是 e0 兼容解），则 `MemoryManager.prune_tool_results`
  的方法体必须能触达一个 spiller ⇒ manager 必须有一个 spiller 属性 ⇒ Q2 只能 manager 组合持有。反之，
  Q2=loop 自持 ⇒ manager 无 spiller 可转发 ⇒ Q1 必须删除委托（并连带改 13 处测试 + 改 e0 patch 目标）。
  把耦合对拆成两个「自由偏好」会让用户选出**互斥组合**。
- **F3 的「张力」措辞过强（结论仍对）**：grill 说「保留委托」需要给 spiller 加「外部标记灌入」通道，
  「这与 D1『对外仅 mark/reset/spill、不暴露内部 dict』有张力」（`grill-design.md:51`）。给 `spill` 增加一个
  `added_iterations` 形参**并不暴露内部 dict**，也与「对外仅三方法」不冲突——它只是给既有方法加一个可选策略参数。
  结论（spill 必须接纳 added_iterations，且 reset 不可顶替）正确，但「张力」被夸大；实际这是标准解法而非两难。

## Survives

- **D2（counter 单一注入点）**：经证伪尝试仍成立。`is_oversized_result`（`manager.py:200-202`）与 `prune_tool_results`
  （`manager.py:249-251`）今日都在方法体内裸引用模块全局 `_count_tokens`（`manager.py:62`）→ call-time 解析。闭包
  `lambda text: _count_tokens(text)` 定义在 manager 模块内时 `__globals__` 指向 manager 的命名空间，调用时解析 ⇒
  与今日逐字等价，`monkeypatch.setattr(_manager_mod, "_count_tokens", ...)` 仍生效；无默认参数固化陷阱。证据：`manager.py:62/200/249`；
  `tests/agent/memory/test_tool_result_lifecycle.py:42`、`tests/agent/test_tool_result_lifecycle_loop.py:40`。
- **D3（迭代状态归 spiller）**：`_tool_result_iterations`（`loop.py:206`）唯一消费点是 `loop.py:1643` 传入
  `added_iterations=`；写入 `loop.py:898`/`:1092`、重置 `loop.py:1573` 全在 loop 内，无外部读者/导出。迁入 spiller 不破外部面。
- **D4（PruneStats 迁出 + manager 重导出）**：`PruneStats` 唯一定义 `manager.py:93`，仓库内唯一外部 import 是
  `scripts/e0_tool_result_lifecycle.py:108`；重导出即兼容。迁移循环体时用 `policy.flatten_content` 而非 `manager._flatten` 则无环。
- **F5（必须用 flatten_content 否则成环）**：成立，且**行为逐字一致**——`manager._flatten`（`manager.py:54-58`）是
  `tool_result_policy.flatten_content`（`tool_result_policy.py:140`）的**纯委托包装**，两者对同一 content 输出完全相同。
  故 spiller 直接 import `policy.flatten_content` 既破环又零语义差。
- **D5（is_oversized_result 保留）**：唯一调用方 `loop.py:1600` 的 `_bound_ledger_result`，确非剪枝循环。保留在
  `MemoryManager` 并以同一 `manager._count_tokens` 全局与 spiller 共享解析点，符合「单一来源」。
- **D7（事件/trace 发射留 loop）**：可观测契约钉在 `loop.py:1646-1658`；`spill` 只产 `PruneStats` 即满足
  `tests/agent/test_tool_result_lifecycle_loop.py:342-346` 的断言。
- **D8（纯重构等价可机械判据）**：两既有测试文件确实覆盖事件名/payload（`:342-345`）、trace step（`:346`）、
  ref 无损回读（`:186-198`）、resume 历史被剪（`:252-279`）、`_tokens` 失效（`:200-212`）、幂等（`:242-254`）。基线充分。
- **F1（13 非 14）**：属实。`grep -c "prune_tool_results(" tests/agent/memory/test_tool_result_lifecycle.py` = 13
  （真实调用点 `:144/162/180/192/207/219/233/245/249/261/275/288/304`）；`:6` 是 docstring。design/proposal 的「14 处」失实。
- **F2（loop 不引用 PruneStats）**：属实。`grep -n "PruneStats" agent/loop.py` 零命中；唯一外部 import 是 `e0:108`。
- **F3 的核心结论（spill 签名漏 added_iterations、reset 不可顶替）**：属实。13 处直调全传 `added_iterations=`；
  该形参为 kw-only 且无默认（`manager.py:213`）⇒ 必填。`reset` 对 `test_prune_skips_fresh_unconsumed_result`
  （`:140-150`，传 `{"c1":3}, current_iteration=3`，期望**不剪**）会把 c1 预置 `-1`（`loop.py:1573`）⇒ 该用例变**剪**、语义相反。
- **F4（e0 缝的充分条件）**：属实。`e0:110` 需 loop 经 `self.memory.prune_tool_results` 才生效（见上 Q2 证据）。
- **F7（logger 名漂移盲点）**：属实。`manager.py:21` = `logging.getLogger("asterwynd.memory")`，消息 `:260`/`:268-271`；
  全仓无日志断言。D8 的「日志文案不变」指 message 文本，不含 logger 名。
- **F8（Impact Analysis 遗漏面，轻）**：属实。`tests/web_tests/test_tool_result_expand.py`、`test_transcript_js.py`、
  `test_transcript_view_browser.py` 与 `docs/interview-script/questions/{Q02-agent-loop,Q11-error-type}.md`、
  `walkthrough/W01-agent-loop.md` 均存在且未列入显式清单（因 policy 不改而实质无影响）。
- **F9（RIR 事实偏弱）**：属实。`.dev/reference-repos.txt` 确不存在；但 `/home/shared/agent-study/reference-repos/`
  存在 6 个库（codex/deepseek-harness/kimi-code/opencode/pi/zcode），其中 `codex/codex-rs/hooks/src/output_spill.rs`
  确存在——「不可用」结论不准确，as-占位判定应改为「配置缺失、改用本地参考仓库」。
- **Code-Resolved 各项**（reset 转发等价、OQ5 命名锁定、D2 单来源硬条件、flatten 迁移、PruneStats 引用面、
  65 行规模 `manager.py:208-272`、spec delta 合规 29/29）经复核均成立。

## New Findings

- **NF1（spec 与 e0 的三方张力，grill 未联立）**：新 spec Requirement 的 Scenario 写「调用方（AgentLoop）SHALL 经**该入口**
  触达工具结果剪枝」（`specs/context-engineering/spec.md`「剪枝经单一入口触达」）。若「该入口」= spiller 的对外接口，
  则 loop 应 `self.memory.tool_result_spiller.spill(...)`；但 e0 patch 的是 `loop.memory.prune_tool_results`（`e0:110`），
  loop 直调 spiller ⇒ e0 patch 静默 no-op。**即：spec 字面（loop 经模块入口）+ e0 不变 ⇒ 不可同时成立**，除非把
  manager 的薄委托也算作「该入口」，或改 e0 的 patch 目标。grill 的 F4 只提了 e0 的必要条件，Q1/Q2 也未把 spec 字面纳入联立，
  这个三方一致性（spec 措辞 × e0 patch 目标 × loop 调用点）在设计文档中始终未被言明。
- **NF2（迁移后遗留死代码/死 import，纯重构应收尾）**：剪枝循环体迁出后，`manager.py` 下列设施失去唯一使用者，
  应在迁移中清理，否则「纯重构」遗留浅转发与死 import：
  - `_flatten`（`manager.py:54-58`）唯一使用点 `:258` 随循环体迁走 ⇒ 死函数；
  - `is_spilled_preview as _is_spilled_preview`（`:12`）唯一使用点 `:243` 迁走 ⇒ 死 import；
  - `make_preview as _make_preview`（`:13`）唯一使用点 `:262` 迁走 ⇒ 死 import。
  （保留的：`_content_bytes` 仍用于 `_message_bytes:46`；`_READ_PROGRESS_RE` 仍用于 `_extract_read_progress:644`；
  `_exceeds_single_threshold` 仍用于 `is_oversized_result:200`。）grill 的 9 条 Findings 未含此项。
- **NF3（`spill` 丢失 `messages=None → self.messages` 回退）**：今日 `prune_tool_results(messages=None)` 回退到
  `self.messages`（`manager.py:236`）。D1 的 `spill(messages, *, ...)`（`design.md:50`）把 messages 变为**必填**。
  当前无调用方依赖该回退（loop 与 13 处测试均显式传 messages），故行为不破；但若 Q1=保留委托，委托体必须自行把
  `None` 解析为 manager 的 `self.messages` 再交给 spiller（spiller 不持 manager 的消息列表），此实现细节 grill/design 未提。
- **NF4（monkeypatch 缝有第 3 处，轻）**：除 grill 列的两处外，`tests/agent/memory/test_memory.py:259` 也
  `monkeypatch.setattr(manager_mod, "_count_tokens", counting)`。它不触碰 prune 路径，**不影响 D2 结论**，但说明该缝
  的依赖面是 3 处；新 `test_tool_result_spiller.py` 若要真覆盖 D2，须经 `MemoryManager` 触达（grill 已正确点出），
  而非直接构造 spiller 自传 counter。

## Open Questions（收敛后）

- **Q1**（接口归属 + `added_iterations` 通道）：`MemoryManager.prune_tool_results` **保留薄委托**（`e0:110` 的 patch
  目标不破、13 处测试不动，但须接受一个转发浅方法 + 把外部 `added_iterations` 灌入 spiller）还是**删除委托**（接口最干净，
  但须改 13 处测试 + 改 e0 的 patch 目标为 spiller）？
  - 为何仍留用户：两种形态都能让测试通过，取舍在「接口纯净 vs churn/回归姿态」。
  - **但必须先与 Q2 联立**：Q1=保留委托 ⟺ Q2=manager 组合持有（见 Refuted）；Q1=删除 才使「loop 自持」在逻辑上可行，
    且此时必须同步改 e0 的 patch 目标。用户不能独立拍 Q1、又独立拍 Q2。
- **Q4**（seam 边界）：账本有界路径（`_bound_ledger_result` `loop.py:1593-1603` / `_bound_arguments`）**本轮不收进**
  spiller 的边界是否被认可？
  - 为何代码判不了：这是本 change 的范围边界决策（做什么/不做什么）；D6 的「目标不同」理由（账本预览无 ref 消费者、
    会话消息预览可回读）本身有代码支撑，但「是否本轮合并」是范围取舍，非可判定事实。

## Code-Resolved（对抗新增/修正）

- **Q2（原 design OQ2 的「所有权」）**：**改判为代码/文档可定 —— 结论：`MemoryManager` 组合持有
  （`self.memory.tool_result_spiller`），非用户偏好**。证据：`proposal.md:39`（写成既成事实）；`design.md:63-68`
  （D2 构造点写在 manager）；`scripts/e0_tool_result_lifecycle.py:110` + `agent/loop.py:1640`（e0 patch 需 loop 经
  `self.memory.*` 才生效）。「loop 直接构造持有」仅在**同时**删除 manager 委托（Q1=删除）**并**改 e0 patch 目标时才自洽——
  那是一个更大的联合改动，不是独立的「持有偏好」。相应地，`design.md:79-80`/`design.md:116` 的 `self._spiller` 措辞
  应改为 `self.memory.tool_result_spiller`，`proposal.md:41` 的 `self._spiller.*` 同步改为 `self.memory.tool_result_spiller.*`。
- **新增（由 NF1 派生）**：**loop 的剪枝调用点须与 e0 的 patch 目标一致**——结论：在「保 e0 不变 + 改文档不改脚本」
  姿态下，loop 的剪枝调用 SHALL 落在 `self.memory.prune_tool_results`（而非直调 spiller），且新 spec Scenario 的
  「经该入口」措辞需与之一致（或明确 manager 委托即「该入口」）；否则须改 `e0:110` 的 patch 目标为
  `loop.memory.tool_result_spiller.spill`。证据：`e0:110`、`loop.py:1640`、`specs/context-engineering/spec.md`。

## 需回改清单（供主 session 收敛，不代改）

1. `grill-design.md`：把 **Q2 从 `## Open Questions` 移入 `## Code-Resolved`**（结论：manager 组合持有，证据如上）；
   在 Q1 补「与 Q2 联立、不可独立拍」的约束；F6 补 proposal 侧不一致（`proposal.md:41` vs `:39`）；
   新增 NF1–NF3 三条 Finding（NF4 可并入 D2 的 Code-Resolved）。
2. `design.md`：修正 `:79-80`（`self._spiller` → `self.memory.tool_result_spiller`）、`:116`（OQ2 措辞）；
   OQ 列表按收敛后重排（Q2 不再是待决 OQ）；D1 的 `spill` 签名补 `added_iterations` 通道说明（F3）；
   迁移步骤补 NF2 的死代码/死 import 清理；补 NF1 的 loop 调用点 × e0 patch 目标一致性说明。
3. `proposal.md`：修正 `:41` 的 `self._spiller.*` 与 `:89`/`:20`/`:111`/`:113`/`:175` 的「14 处」→「13 处」（F1）。
