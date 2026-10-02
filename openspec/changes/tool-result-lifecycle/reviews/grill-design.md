# Grill: tool-result-lifecycle 设计追问报告

## Reviewer

- run id: 独立零记忆设计评审 subagent（本 worktree 内直接执行；自述 id `grill-design-tool-result-lifecycle`）
- 时间: 2026-10-03
- 范围: `proposal.md` / `design.md` / `tasks.md` / `specs/` delta + 被改代码逐点走读（`agent/loop.py`、`agent/memory/manager.py`、`agent/trace_recorder.py`、`agent/result.py`、`agent/message.py`、`agent/session.py`、`agent/workspace_policy.py`、`agent/subagent/manager.py`、`agent/subagent/workflow_store.py`、`agent/subagent/snapshot.py`、`agent/tools/builtin/read.py`、`agent/tools/builtin/subagents.py`、`agent/main.py`）+ 既有 spec（`context-engineering` / `memory-context` / `agent-runtime`）+ 前任 A 的 grill/对抗（`/home/happy/my-agent/.claude/worktrees/context-bound/.../reviews/`，可读）。
- 方法：本 worktree 现场核验行号（漂移见文末）；对 D0 的 GC 测试可行性做**运行时实测**（`weakref.ref(str)` 抛 `TypeError`，`str` 子类可弱引用）；对全文消费者做全仓 sweep；对 `Message` 持久化路径（`messages.json`）做核实。

---

## Confirmed Decisions

- **决策**: 工具结果全文的单受管持有 + 三持有者一起治（`messages`/`trace`/`tool_calls_made` 是同一对象的三个引用）。
  理由: #282 的 `is` 判定实测坐实；本 worktree 逐点核验三处写入共享同一 `result` 变量——错误路径 `agent/loop.py:830`（`result = f"[Error: {e}]"`）→ `:854`（`messages.append(tool_result_message(tool_call.id, result))`）+ `:855`（`ToolCallMade(..., result=result)`），正常路径 `:1047`+`:1048`，trace `:997`（`record_tool_result(..., result, ...)`）。单做一处 = 白做。来源: design Context 事实 1/4 + 现场走读。

- **决策**: `messages` 需 spill+ref（无损回读），`trace`/`tool_calls_made` 只需 bounded（预览 + 诚实标记，不落 ref）。
  理由: 全仓 full-text 消费者逐点核实——`agent/web/session.py:898` 只读 `text[:text_limit]`（截断，`TRANSCRIPT_CONTENT_LIMIT=4000`/preview=400）；`benchmarks/agent_runner.py:459` 只 `call.result.startswith("[Error"/"[Permission denied")`；`agent/main.py:656` 走 `summarize_tool_result`（collapsed 时只打 `preview=text[:config.preview_chars]`，`agent/tool_result_display.py:55`）；`agent/subagent/snapshot.py:79` 只数 `llm_iteration` steps；`agent/subagent/scheduler.py:2315-2317` → `trace_recorder.count_failures`/`iter_failure_steps`（`trace_recorder.py:277`）**只读 `status` 不读正文**。**唯一读全文的是 `benchmarks/runner.py:661`（`trace.write_to_file` → `to_dict()` 落 `trace.json`）**。⇒ 形态判断成立（带两条子项，见 Open Q3/Q-new2：`tool_calls_made.arguments` 是另一条无界通道；benchmark 全文需求用 inert 的 `full_trace` 开关承接）。

- **决策**: 剪枝每轮无条件跑（不嵌进 90% 阈值分支）。
  理由: 单一压缩入口 `agent/loop.py:1056` 每轮恰好调一次；阈值 `agent/memory/manager.py:159`（`max_tokens-15_000`，80K→65K）。一次默认 Read（B 后 ≤128KB ≈ 32K token）即占近半预算，两条即过阈——若剪枝只在阈值分支内跑，剪枝生效前常驻已到 2×阈值。来源: 前任 grill Q1 + 对抗实测；现场复核成立。

- **决策**: 复用 `WorkflowStore` 的实现基因（ref 格式族 / 原子写 / 分页读），泛化作用域，落盘置于 `sessions/<id>/` 之外。
  理由: `agent/subagent/workflow_store.py:64-81` 的 `parse_ref` 是 `@staticmethod` 且**硬编码** `RESULT_REF_PREFIX="artifact://workflow/"`（`:25`）；`path_for`（`:91-97`）校验 `workflow_id == self.workflow_id`；原子写 `:210-220`（tmp+`os.replace`）；分页读 `:156-186`（`DEFAULT_READ_LIMIT=4000`/`MAX_READ_LIMIT=20000`）；store 根 `:60` = `.asterwynd/workflows/<id>`。`agent/session.py:189` `SessionStore.remove` 用 `shutil.rmtree` ⇒ artifacts/ 必须与 `sessions/<id>/` 隔离（`workflow_store.py:6-10` 头注释已警告此坑）。`agent/workspace_policy.py:9-43` deny-list 只含 `.asterwynd/worktrees/**`，`.asterwynd/artifacts/` 允许写；`WorkflowStore` 自身不经 policy（直接原子写）。⇒ 复用 + 隔离成立。

- **决策**: ref 身份按 agent 类型分——根用 `session_id`、子用 `run_id`。
  理由: 子 agent 的 loop `session_id=session.subagent_id`（`agent/subagent/manager.py:1214`），而 `subagent_id = uuid.uuid4().hex[:8]`（`:573`）**进程内、不落盘**；checkpoint `session_id=run.run_id`（`agent/subagent/snapshot.py:60`）、`resume_subagent(..., run_id=...)`（`manager.py:771` 起，keyword-only）靠 `run_id` 取。⇒ 子 agent durable 身份 = `run_id`；根 agent resume 时 `session_id` 不变、`run_id` 新起 ⇒ 根用 `session_id`。来源: 前任对抗 Q3 修正 + 现场复核成立。

- **决策**: `Message.content` 是 `str | list[ContentBlock]`（非 `str`）。
  理由: `agent/message.py:150` 实测为 `content: str | list[ContentBlock]`；图片工具返回 `[TextBlock, ImageBlock]`（`agent/tools/builtin/read.py:242-248` base64 `ImageUrl` + `file_path`）。A 的 design 曾误写为 `str`，本 change 已修正。

- **决策**: `_tokens` 缓存失效是红线——改 `content` 后 MUST 置 `_tokens=None`。
  理由: 全仓唯一写点在 `agent/memory/manager.py:142`（`message._tokens = count_tokens_for_content(...)`），读回在 `:141`。缓存住在非序列化字段 `Message._tokens`（`agent/message.py:155`，`to_dict`/`from_dict` 不含 ⇒ 持久化/重载后为 `None`）。前任实测：原地改 `content` 后 `count_tokens` 仍报旧值 25001，置 `None` 后降为 14 ⇒ 不重置会**反复误触发压缩**。成立。

- **决策**: 只替换 `content`、保留 `tool_call_id`，不破坏 tool-call 链。
  理由: `tool_result_message(id, content)`（`agent/message.py:208-210`）把 `tool_call_id` 与 `content` 分离；`_find_tool_call_assistant`（`agent/memory/manager.py:395-407`）按 id 匹配配对。替换正文不动 id ⇒ provider 侧配对关系不变。

- **决策**: `TraceRecorder.full_trace` 现为 inert，可复活为 benchmark 开关。
  理由: `agent/trace_recorder.py:33` 赋值（注释 "retained for serialization compat only"），仅在 `to_dict`（`:240`）原样回吐；全仓（`agent/ benchmarks/ scripts/ tests/`）**无任何行为分支读它**。⇒ 用它承接 benchmark 全文需求是安全增量。

---

## Open Questions

> 每条 = design 里带 `> 待 grill 确认` 的项 + 我新发现的未决项。每条给推荐答案 + **本 change 真实场景的具体例子**（#278 复现器：单 agent 逐文件审查 145 个 `.py`；`max_tokens=80_000`；B 后单次默认 Read ≤128KB/2000 行，≈32K token）。

- **Q1（D0｜GC 不变量的测试形态——本 change 的最硬验收项）**
  - **具体例子**：单元测试驱动真实入库路径，但让 fake `ReadTool` 返回一个 **`class _WeakStr(str): pass`** 的实例（内容 `"A"*128_000`，唯一、非 interned）。测试持 `w = weakref.ref(payload)`。跑 1 轮：`:854/:997/:1047/1048` 三处都持有它 ⇒ 断言 `w() is payload`（活着，三持有）。跑第 2 轮触发剪枝（该结果「已消费一轮」）⇒ 断言 `messages[i].content` 已是预览+ref、`tool_calls_made[j].result` 已 bounded、`trace.steps[*].data["observation"]` 已 bounded；`gc.collect()` 后 **`assert w() is None`**。
  - **推荐答案**：**主用 `str` 子类弱引用**——实测确认 `weakref.ref(str)` 抛 `TypeError`，但 `str` 的**子类可弱引用**（`weakref.ref(_WeakStr("B"*100000))` 成功），且因为它是 `str`，生产代码所有 `isinstance(x, str)`/`startswith`/`extract_text` 路径**完全等价**，无需 mock 管线。**兜底**一条 `gc.get_referrers(payload)` 断言无 `Message`/`ToolCallMade`/容器强引用，但**只对大且唯一（非 interned）的字符串可靠**（实测 100KB 唯一串可被 `get_referrers` 找到，小 interned 串不可靠）——故须与 `_WeakStr` 合用，或改断 `tracemalloc` 快照已释放。

- **Q2（D1｜统一入库通道放哪 + ref store 与 scope 从哪来）**
  - **具体例子**：一条 128KB 的 `Bash` 输出。入库时（`loop.py:997/:855/:1048`）需要「bounded 预览」给 trace/tcm；剪枝时（`loop.py:1056` 前）需要「写 ref 到 `.asterwynd/artifacts/<scope>/`」给 messages。但 `MemoryManager` 是构造期建的，根 loop 的 `MemoryManager(max_tokens=80_000)`（`agent/main.py:297`）**没有 workspace_root/store**，且 `AgentLoop` 默认 memory `MemoryManager(llm=llm)`（`loop.py:156`）连 max_tokens 都是默认。而 **scope id（子 agent 的 `run_id`）只在 `run()` 调用时才知道**（`loop.py:1214-1216`），构造期拿不到。
  - **推荐答案**：**两段式，不塞一处**。(1) **bounded 逻辑**做成一纯函数（新模块，如 `agent/memory/tool_result_policy.py::bound_result(result, *, budget) -> (preview, released_bytes)`），`loop.py` 在三处写入点调用——无状态、可单测。(2) **messages 剪枝**做成 `MemoryManager.prune_tool_results(...)`，但 **store 与 scope 由 `loop.py` 在 `run()` 期构造并注入**（loop 持有 `self._artifact_store`，scope=根 `session_id`/子 `run_id`）；`MemoryManager` 只负责「判哪些消息该剪（窗口∪单条∧已消费）」+「`_tokens=None` 重置」，**真正的落盘写 ref 由 loop/注入的 store 完成**。理由：scope 只有 loop 知道，把 I/O 放在 loop 侧避免给 `MemoryManager` 反向注入一堆构造期未知量。

- **Q3（D2｜bounded-vs-ref 的形态判断对不对 + benchmark 消费者）**
  - **具体例子**：(a) **benchmark 全文**——`asterwynd benchmark` 经 `benchmarks/runner.py:661` 写 `trace.json`（含每个 observation 全文）。若 trace observation 被 bounded 到 4KB，事后分析/回放丢正文。(b) **`tool_calls_made.arguments`**——一次 `Write` 带 300KB 正文时，`ToolCallMade` 的 `result` 只有状态串，**300KB 在 `arguments` 里**；且 `messages` 里那条 assistant 消息的 `tool_calls[].arguments`（`agent/message.py:172-176` + `_recent_with_tool_chains` 原样保留 assistant，`manager.py:380-392`）**也持 300KB**。
  - **推荐答案**：形态**基本成立**，两条修正：(a) benchmark 全文 = **显式开 `TraceRecorder(full_trace=True)`**（已验证 inert、可复活），仅 benchmark 走全量、默认仍 bounded，并把「benchmark 用 full trace」写进 design/tasks；(b) **bounded 必须覆盖 `arguments` 与 `result` 两者**——至少 `tool_calls_made.arguments` 要 bounded；`messages` 里 assistant 的 `arguments` 若不剪，也**必须计入字节预算**（否则 `Write` 型大参数绕过白名单）。design 只谈 `result`，是**覆盖缺口**。

- **Q4（D3｜单条阈取值 + 「已消费一轮」实现——最核心待定项）**
  - **具体例子**：`max_tokens=80_000` ⇒ 90% 阈 72K。模型第 3 轮 `Read` 一个 100KB 文件（≈25K token）。**(i) 单条阈**：若阈=20K token（`max_tokens×0.25`）或 128KB 字节，此条**超阈** ⇒ 消费一轮后即使仍在 recent window 内也要剪（否则硬顶每轮空转）。**(ii) 已消费一轮**：结果在第 k 轮末尾 `:1047` 入库，模型要到第 k+1 轮 `_call_llm`（`loop.py:1205/1215` 发全量 messages）才见到它 ⇒ **k 轮末尾绝不能剪，k+1 末尾起才可剪**。
  - **推荐答案**：**(a) 单条阈** = 独立常量，**token 与字节双判据取先到**：`token > max(TOOL_RESULT_SPILL_MIN_TOKENS, max_tokens*0.25)` **或** `bytes > TOOL_RESULT_SPILL_MAX_BYTES(=128KB，与 B 的 Read 默认界同值)`。写成常量（可配），不留实现即兴。**(b) 已消费一轮 = 按 iteration 记录**：`loop.py` 在 append 时为每个 `tool_call_id` 记 `added_iteration`（存在 loop/manager 侧，不新增 `Message` 字段）；剪枝时**只剪 `added_iteration <= current_iteration - 2`** 的结果（等价「至少一次 `_call_llm` 已把它发出去过」）。天然覆盖并行多 tool call（同轮多条同 `added_iteration`）。**(c) 预览必须保尾**——见 Q-new1。

- **Q5（D4｜ref 前缀命名 + `parse_ref` 泛化方式 + 清理触发点）**
  - **具体例子**：根会话 `s-abc` 剪掉一条 Read 结果 → 写 `.asterwynd/artifacts/s-abc/<key>` → ref `artifact://agent/s-abc/<key>`。`--resume s-abc`（新 `run_id`）→ `messages.json` 重载预览+ref → 模型调 `ReadWorkflowResult(ref=artifact://agent/s-abc/<key>)`：**当前 `WorkflowStore.parse_ref`（`workflow_store.py:64-81`）硬编码前缀**，直接 `ValueError` ⇒ 回读 404。子 agent：scope=`run_id`，`resume_subagent(run_id=...)` 后仍可解析。
  - **推荐答案**：前缀 `artifact://agent/<scope_id>/<key>`（与既有 `artifact://workflow/<workflow_id>/<key>` 并列）。泛化方式：**新增一个共享 `ArtifactRef.parse(ref) -> (kind, scope_id, key)`**（或等价静态路由），`WorkflowStore.parse_ref` 委托之——**在工具层按前缀路由**（`artifact://workflow/`→`manager.workflow_store(wid)`；`artifact://agent/`→agent store），**不改 workflow 语义**。清理：`SessionStore.remove(session_id)`（`session.py:184-191`）里**显式追加** rm `.asterwynd/artifacts/<session_id>`（`_sessions` 永不清理，故必须显式）；子 agent 的 artifacts 清理同理须**显式实现**（当前无子 agent 归档清理路径），否则退化为永不清理——**写进 design 的生命周期段**。

- **Q6（D5｜泛化 vs 并列边界 + 根 agent 构造来源 + 注册门）**
  - **具体例子**：根 agent 在 `agent/main.py:320-327` 建 loop（`expose_subagent_tools=True`）⇒ `_ensure_subagent_tools_registered`（`loop.py:381-434`）在 `:420` 建 `ReadWorkflowResultTool(self.subagent_manager)` ⇒ 注册可用。深度到限子 agent 在 `manager.py:1314-1322` 建 loop（`expose_subagent_tools=True`，`unregistered=SPAWN_TOOL_NAMES`）——`SPAWN_TOOL_NAMES`（`manager.py:430-440`）={CreateSubagent, RunSubagent, ResumeSubagent, StartWorkflow, RunWorkflow, RunWorkflowAsset}，**不含 ReadWorkflowResult**（`subagents.py:945` 注释亦声明它非 spawn 类）⇒ 深度到限子 agent **仍可用**。**但**：凡 `expose_subagent_tools=False` 的入口（`loop.py:135` 默认 False）**整套不注册** ⇒ 溢出 ref 无法回读。
  - **推荐答案**：泛化（不新增工具）成立，落实三条：**(a)** 工具按前缀分派，构造依赖改为**一个解析器**（由 `workspace_root`+ref 路由组成），不再只依赖 `manager.workflow_store`；**(b)** **改写 description**（`subagents.py:918-924` 现为 workflow 专用文案，必须泛化为「按 ref 读任意 artifact」）；**(c)** **把「回读工具是否可用」作为 spill 的启用前提**——见 Q-new2。

- **Q7（D6｜图片策略——token 硬顶对图片失效）**
  - **具体例子**：模型 `Read` 一张 5MB PNG（<`MAX_IMAGE_SIZE=20MB`，`read.py:18`）。`read.py:_read_image`（`:242-248`）返回 `[TextBlock("[image: …, 5.0MB]"), ImageBlock(data_url≈6.7MB base64, file_path=<磁盘路径>)]`。`count_tokens_for_content`（`message.py:97-98`）对其计 **1000 token** ⇒ token 账本几乎不动，而 `messages` + `tool_calls_made` **各持 6.7MB**。3 张图 ≈ 20MB 常驻，token 硬顶（160K）**永不触发**。
  - **推荐答案**：四管齐下：**(1)** 字节维度对 `ImageBlock` 计 `len(url)`（base64 长度），纳入单条阈与硬顶；**(2)** 图片「预览」= 复用 trace 既有形态 `[image: <file_path>]`（`trace_recorder.py:140-142`）——消费一轮后把 `ImageBlock` 换成该 TextBlock，**字节立即释放，模型必要时可 `Read` 该路径取回像素**（file_path 在）；**(3)** `file_path is None`（粘贴图）时，把 base64 落 ref store、标 `[image: <ref>]`（字节有界、诚实标注「模型不能直接再看到」，或靠字节预算逼压缩）；**(4)** `MAX_IMAGE_SIZE`（`read.py:18`）**收敛到与常驻预算相容的值**——20MB/张与「常驻有界」目标自相矛盾。**注意**：trace 已 sanitize 图片 ⇒ **trace 不是图片持有者**，图片持有者只有 `messages` + `tool_calls_made`（修正「三持有者」在图片场景的形态）。

- **Q8（D9｜可观测落点）**
  - **具体例子**：第 k 轮剪掉 3 条结果、释放 380KB，同时 bounded 了 2 条账本 observation。
  - **推荐答案**：**新增一个 trace step 类型** `record("tool_result_spill", spilled_messages=N, bounded_ledger=M, released_bytes=B)`（形态对齐既有 `record_compaction`，`trace_recorder.py:164-180`），并在 `loop.py` 同步发 `on_event("tool_result_spill", ...)`（对齐 `memory_compaction` 的 `:1058-1066`）。run 级累计总量在 `completion` step 落一段汇总，满足 spec「一次 run 结束 SHALL 可被观察」。**不**改 `RunResult` 协议。计数须区分「messages 无损 spill（有 ref）」与「账本有损 bounded（无 ref）」。

- **Q-new1（新发现｜预览必须保尾，否则破坏「分页进度保留」既有能力）**
  - **具体例子**：`Read /big.py` 返回 128KB 正文 + 尾部注记 `\n\n[ReadProgress file="/big.py"; offset=2000; total=8000; truncated=true]`（`read.py:46-55`）。若预览只留头 4KB，**注记被剪掉**；此后若 compaction 在模型回读前触发，`_extract_read_progress`（`manager.py:460-485`）匹配不到 ⇒ 分页续读位点丢失 ⇒ **违反既有 base spec「Pagination Progress Preservation」**（`openspec/specs/context-engineering/spec.md`）。
  - **推荐答案**：预览 = **头 N 字符 + 保留的尾部 `[ReadProgress ...]` 注记**（正则 `_READ_PROGRESS_RE`，`manager.py:23-25`，抽出后原样重附）。design 的「预览」默默假设 head-only，需显式改为 head+progress-tail。

- **Q-new2（新发现｜无回读工具时可溢出的 ref 会「悬空」）**
  - **具体例子**：`AgentLoop` 用默认 memory 建（`loop.py:156`，`expose_subagent_tools=False`，如单测或非 CLI 入口）⇒ `ReadWorkflowResult` **未注册**。此时若 spill 写「full result in result_ref」，模型被告知去用一个不存在的工具 ⇒ **违反 spec「SHALL NOT 声称存在可读的 ref」**。
  - **推荐答案**：**溢出前门控「回读工具是否已注册且能解析该 ref」**（`self.tool_registry.get_tool("ReadWorkflowResult")` 可得）；不可回读时**不 spill**（或 spill 但如实标 `[truncated]` 不指向 ref）。即 spill 能力与回读能力**必须成对启用**。

- **Q-new3（新发现｜spec delta 与 design D3 口径不一致）**
  - **具体例子**：`specs/context-engineering/spec.md` 的 Scenario「陈旧的工具结果被替换」写「已消费过**且滑出近期窗口**」（**窗口单向**）；而 design D3 是「（窗口 **∪** 单条超阈）」（**单条可独立穿透窗口**）。delta **没有**任何单条穿透窗口的 scenario。
  - **推荐答案**：二者对齐——**向 delta 增补一条 scenario**「窗口内的超大单条结果在消费一轮后仍被替换（穿透窗口）」，否则实现按 design 做会被 spec 判偏离、按 spec 做则硬顶压不动 recent 大项。

- **Q-new4（新发现｜ref 存哪：Goal 说「不改 Message 结构」）**
  - **具体例子**：Goal/SHALL「不改协议：`Message` 结构不变」。若 ref 不作为字段，就必须**嵌进 `content` 文本**（如 `\n…[spilled; full result: artifact://agent/<scope>/<key>]`），回读侧用正则抽取（仿 `_READ_PROGRESS_RE`）；它经 `messages.json`（`session.py:217` dump `m.to_dict()`）自然持久化、resume 后仍在。若改成新增 `Message.result_ref` 字段，则 `to_dict`/`from_dict`（`message.py:162-205`）与 `_hash_dict`（`session.py:235-239`）都要改，等于**自破 Goal**。
  - **推荐答案**：**内容内嵌机器可解析标记**（不改结构、随消息持久化），并登记一条回归：resume 后从预览里能正则出 ref 且可解析。

- **Q-new5（新发现｜硬顶死结只解了「工具结果」，未解「非工具大内容」）**
  - **具体例子**：用户把一份 300KB 日志当任务贴进 `user` 消息，或某轮 assistant 产出巨大的 `Write` `arguments`。强制 compact 时 `_recent_with_tool_chains`（`manager.py:375-393`）**原样保留 recent（含这条大 user/assistant 消息）**，而 design 的 D3 只剪**工具结果** ⇒ 超硬顶后每轮强压、压不动、无物可剪 ⇒ **空转**（与 A 的 Q6 同款死结，只是主角从 tool 换成 user/assistant）。
  - **推荐答案**：硬顶的兜底必须**不止「先剪工具结果」**——超硬顶**且剪无可剪**时应允许 compact **收缩/驱逐 recent window 本身**（或对 recent 内的超大非工具消息做有损截断），否则「硬顶 = 常驻有界」在非工具主导的 run 上不成立。至少要在 design 明写这条**残余边界**，不能只断言 D3 已解死结。

---

## 风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| **大 `tool arguments` 无界**（`Write`/`Edit` 正文住在 assistant 消息 `tool_calls[].arguments` + `ToolCallMade.arguments`，剪 `result` 不触及） | **高** | bounded 覆盖 `arguments`；`messages` 侧 assistant `arguments` 至少计入字节预算（Q3） |
| **无回读工具时溢出 → 悬空 ref**（`expose_subagent_tools=False` 默认入口） | **高** | spill 与「回读工具已注册」成对启用（Q-new2） |
| **预览剪掉 `[ReadProgress]` 尾注 → 破坏分页进度保留**（既有 base spec） | **中-高** | 预览 = 头 + 保尾注记（Q-new1） |
| **硬顶对非工具大内容空转**（大 user 粘贴 / 大 assistant 参数在 recent 内） | **中** | 超硬顶+剪无可剪时允许收缩 recent（Q-new5）；至少写清残余边界 |
| **图片绕过 token 硬顶**（1000 token/张 vs 6.7MB/张） | **高** | 字节维度 + file_path 化 spill + `MAX_IMAGE_SIZE` 收敛（Q7） |
| **`_tokens` 缓存使剪枝白剪 / 反复误触发压缩** | **高** | 改 `content` 后置 `_tokens=None` + 回归（已在 D10） |
| **GC 不变量测试难写/易 flaky** | **中** | `str` 子类弱引用为主 + `get_referrers`/`tracemalloc` 为辅（Q1；已实测子类可弱引用） |
| **ref store/scope 注入错层**（`MemoryManager` 构造期未知 workspace/scope） | **中** | I/O 放 loop 侧、policy 放纯函数 + manager（Q2） |
| **spec/design 口径漂移**（单条穿透窗口；delta 只写窗口） | **中** | 增补 delta scenario（Q-new3） |
| **ref 存法自破「Message 结构不变」** | **中** | 内容内嵌可解析标记，不加字段（Q-new4） |
| **硬顶倍数取值** | **中** | 推荐 `max_tokens×2`（80K→160K）为独立常量（前任 Q4；须与字节维并看） |
| **`benchmarks/agent_runner.py:459` 对 `list` 结果调 `.startswith` 会崩**（既存缺陷，非本 change 引入） | **低** | bounded 后可顺带修（先转 `extract_text`）；D11 前置核实应记录 |
| **字节维度每轮重算 `len(encode)` 的 O(n) 开销** | **低-中** | 字节数在入库时与 `_tokens` 一同缓存，勿每轮重编码全量 |
| **`.asterwynd/artifacts/` 无生产者/无清理**（当前无该目录代码） | **低** | 显式实现写+清理（Q5），勿依赖 `_sessions`（永不清理） |
| **spill 不降「落盘那一瞬时」峰值** | **低-中** | 单条阈越早触发峰值越低；复现器量化确认不成为新尖峰 |
| **trace bounded 影响 benchmark 全文分析** | **中** | benchmark 显式 `full_trace=True`（已验证 inert 可复活） |
| **`MemoryManager` 三处共用，改一处影响全部** | **中** | 根/子一致回归（`main.py:297`、`subagent/manager.py:1318`、`loop.py:156` 默认） |

---

## 附：走读证据索引

| 事实 | 文件:行号 | 校注 |
|---|---|---|
| 错误路径工具结果入库 | `agent/loop.py:854` | 与 design 一致 |
| 错误路径 `ToolCallMade(result=result)` | `agent/loop.py:855` | 同一 `result`（`:830` 定义） |
| 正常路径工具结果入库 | `agent/loop.py:1047` | 一致 |
| 正常路径 `ToolCallMade(result=result)` | `agent/loop.py:1048` | 同一 `result` |
| `record_tool_result(..., result, ...)` | `agent/loop.py:997-1005` | 一致 |
| `_call_llm` 定义 / 发全量 messages | `agent/loop.py:1194`（def）/`:1205`、`:1215`（发送） | design 写 `:1194` |
| 唯一压缩入口（每轮一次） | `agent/loop.py:1056` | 一致 |
| 后台结果以 role=user 注入（绕过工具结果通道） | `agent/loop.py:737` | 与 `MAX_OUTPUT_BYTES=64KB`（`background.py:13`）同看 |
| 阈值 = `compact_trigger_tokens` 否则 `max_tokens-15_000` | `agent/memory/manager.py:159` | |
| `compaction_gap` 判定 | `agent/memory/manager.py:161` | |
| `_tokens` 缓存读 / 唯一写 | `agent/memory/manager.py:141` / `:142` | 全仓唯一赋值点 |
| `_count_message_tokens` 定义 | `agent/memory/manager.py:132-143` | design 引 `:141-143` 正确；函数起于 `:132` |
| `compact` 写回 | `agent/memory/manager.py:309` | 一致 |
| `_recent_with_tool_chains` | `agent/memory/manager.py:375-393` | **design 写 `:371-389`，漂移 +4** |
| `_find_tool_call_assistant` | `agent/memory/manager.py:395-407` | |
| `_READ_PROGRESS_RE` / `_extract_read_progress` | `agent/memory/manager.py:23-25` / `:460-485` | 预览保尾依据 |
| `MemoryManager` 默认 100K/10/5 | `agent/memory/manager.py:81-88` | **类默认 100K**，80K 是调用方覆写 |
| `_bounded_summary` + `has_ref` 诚实纪律 | **`agent/subagent/manager.py:53-80`** | **design 写 `manager.py:53-78` 且语境易读成 `memory/manager.py`——实为 `subagent/manager.py`** |
| `Message.content` 类型 | `agent/message.py:150` | 一致 |
| `Message._tokens`（非序列化） | `agent/message.py:155` | |
| `tool_result_message(id, content)` | `agent/message.py:208-210` | |
| `count_tokens_for_content` 图片固定 1000 | `agent/message.py:89-99`（`:97-98`） | 一致 |
| `to_dict`/`from_dict` 含 `tool_calls[].arguments` | `agent/message.py:162-205` | 大 `arguments` 驻留依据 |
| `ToolCallMade.result: Optional[str \| list[...]]` | `agent/result.py:20` | 类型为 `Optional`（design 表未提） |
| `record_tool_result` 签名/存储 | `agent/trace_recorder.py:103-129` | 一致 |
| `_sanitize_observation`（图片→`[image: path]`） | `agent/trace_recorder.py:131-143` | trace 非图片持有者 |
| `to_dict` / `steps.append` | `agent/trace_recorder.py:236` / `:54` | 一致 |
| `full_trace` inert | `agent/trace_recorder.py:33`（+`to_dict` `:240`） | 无行为读者 |
| 消费者：web 截断 / bench startswith / bench 全文落盘 / CLI collapsed / snapshot 计数 / scheduler 失败数 | `agent/web/session.py:898` · `benchmarks/agent_runner.py:459` · `benchmarks/runner.py:661` · `agent/main.py:656` · `agent/subagent/snapshot.py:79` · `agent/subagent/scheduler.py:2315-2317` | 全部逐点核实 |
| `SessionStore.remove` rmtree | `agent/session.py:189` | artifacts 须在其外 |
| 消息持久化 `messages.json` | `agent/session.py:217` | resume 后 ref 须仍可解析 |
| `.asterwynd/artifacts`/`workflows` 写允许 | `agent/workspace_policy.py:9-43` | deny 仅 `.asterwynd/worktrees/**`；WorkflowStore 另有自身校验 |
| `parse_ref` 硬编码 workflow 前缀 | `agent/subagent/workflow_store.py:64-81` / `RESULT_REF_PREFIX :25` | **A 文档曾引 `:72-102`，实为 `:64-81`（`:91-102` 是 `path_for`）** |
| 原子写 / 分页读 / store 根 | `agent/subagent/workflow_store.py:210-220` / `:156-186` / `:60` | 一致 |
| `ReadWorkflowResultTool` 类/名/描述/ref 处理 | `agent/tools/builtin/subagents.py:942` / `:917` / `:918-924` / `:954-965` | description 为 workflow 专用 |
| `_ensure_subagent_tools_registered` / 构造点 / `expose_subagent_tools` 默认 False | `agent/loop.py:381-434` / `:420` / `:135`（默认）`:204-205`（门） | 默认不注册整套 |
| 根 loop 构造（`expose_subagent_tools=True`） | `agent/main.py:320-327` | 根有回读工具 |
| 子 loop 构造（`expose_subagent_tools=True`，hidden=SPAWN） | `agent/subagent/manager.py:1314-1322` | `SPAWN_TOOL_NAMES` 不含 ReadWorkflowResult |
| `SPAWN_TOOL_NAMES` | `agent/subagent/manager.py:430-440` | 6 项 |
| 子 agent `session_id=session.subagent_id` | `agent/subagent/manager.py:1214` | **design 写 `:1212`，漂移 +2** |
| `subagent_id = uuid4().hex[:8]` | `agent/subagent/manager.py:573` | 一致 |
| `resume_subagent(..., run_id=...)` | `agent/subagent/manager.py:771` 起 | keyword-only |
| checkpoint `session_id=run.run_id` | `agent/subagent/snapshot.py:60` | 一致 |
| `run.trace = trace.to_dict()` 四处 | `agent/subagent/manager.py:1349`/`:1425`/`:1440`/`:1459` | **首处 `:1349`（A 文档曾写 `:1348`）** |
| `_sessions`/`_workflows` 从不清理 | `agent/subagent/manager.py:470`/`:518` | grep 无 pop/clear/del |
| `MemoryManager(max_tokens=80_000)` 构造点 | `agent/main.py:297` · `agent/subagent/manager.py:1318` | **main 为 `:297`（design 写 `:296`）**；`loop.py:156` 为默认 100K |
| 图片默认界 / `MAX_IMAGE_SIZE` / `_read_image` | `agent/tools/builtin/read.py:25-26` / `:18` / `:242-248` | base64 + file_path |
| `.asterwynd` 命名空间 | `agent/main.py:224` · `agent/subagent/snapshot.py:35` · `agent/subagent/workflow_store.py:60` · `agent/uploads.py:17` | 文件均在 `agent/` 下（**非 `subagents/` 目录**） |
| `weakref.ref(str)` 不可 / `str` 子类可弱引用 | 本机实测（2026-10-03） | D0 测试形态依据 |

### 行号漂移汇总（design/前任文档 vs 现状）
- `_recent_with_tool_chains`：design `manager.py:371-389` → 实 `375-393`。
- `MemoryManager(max_tokens=80_000)` 根：design `main.py:296` → 实 `297`。
- 子 agent `session_id=subagent_id`：design `:1212` → 实 `1214`。
- `run.trace` 首处：A 文档 `:1348` → 实 `1349`。
- `_bounded_summary`：语境指向 `memory/manager.py`，实为 `agent/subagent/manager.py:53-80`。
- `parse_ref`：A 文档 `:72-102` → 实 `:64-81`（`path_for` 在 `:91-102`）。
- `snapshot.py` llm_iteration 计数：design `:77` → 实计数表达式在 `:79`（函数 `:76`）。
