# Tasks: 工具结果生命周期

## 1. 立项与调研

- [ ] 1.1 关联 GitHub issue #282（主）/ #280（父），写 `proposal.md`（Change Type / Why / 实测证据 / What Changes / Capabilities / 验收 / RIR / Impact Analysis / Non-Goals）
- [ ] 1.2 写 `design.md`（Context / Goals-Non-Goals / Decisions D0–D11 / Risks / Testing Strategy / Impact Analysis）
- [ ] 1.3 写 spec delta（context-engineering ADDED 1「单受管持有与释放」+ memory-context MODIFIED 1「压缩硬顶」）
- [ ] 1.4 补齐 `## Reference Implementation Research`（`research_tier: full`；deepseek-harness + Anthropic context editing + 本地 6 仓库）
- [ ] 1.5 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）
- [ ] 1.6 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过

## 2. grill 与对抗（实现前强制）

- [x] 2.1 独立零记忆 subagent 按 `batch-grill-me` 追问 `design.md`，产出 `reviews/grill-design.md`（8 条 Confirmed + 13 Open Q/新发现）
- [x] 2.2 独立零记忆对抗 subagent 证伪 grill 结论，产出 `reviews/grill-adversarial.md`；主 session 逐条复核新发现（`file:line`，含 Web `on_event` 全文外发、`asdict` 对 str 子类复制、Q4 off-by-one、根 run 无 trace_recorder）
- [x] 2.3 按 grill + 对抗结论回写 design（D0/D1/D2/D3/D6/D6b/D7/D8/D9/D12）与 spec delta（穿透 scenario + 预览保尾 + arguments + 残余边界声明）
- [x] 2.4 停轮把经对抗幸存的 Open Questions 逐项（每条配具体例子）抛给用户，等待答复（用户 2026-10-03 拍板：**A1=`-1`**；**A2=D12 形态 (c)** Web Expand 按需回读；**A3=非工具大内容残余边界只记录、另立 issue #283**）
- [x] 2.5 用户答复写回 `grill-design.md` 的 `## User Confirmation` 节

## 3. 实现（测试先行）

- [ ] 3.1 前置核实（D11）：逐点确认无消费者依赖 `trace` observation / `ToolCallMade.result` 的**全文**（结论：仅 `benchmarks/runner.py:661` 落盘 + Web `on_event`，后者由 D12 决策）
- [ ] 3.2 先写失败测试：GC 不变量（**断言内存字段，不只靠弱引用**——`asdict` 对 str 子类复制）/ `messages` 陈旧被替换 / 当轮保留 / 穿透窗口 / **预览保尾（`_READ_PROGRESS_RE`）** / `trace`+`tool_calls_made` bounded / `arguments` bounded / 按 ref 无损回读 / 无 ref 不谎称 / tool-call 链合法 / `_tokens` 重置 / 硬顶无视 gap / 图片字节维度 / 残余边界（后台注入不被剪）
- [ ] 3.3 agent 通用 ref 存储（复用 `WorkflowStore` 实现；`.asterwynd/artifacts/`；根 `session_id` / 子 `run_id` 寻址；`ArtifactRef.parse` 前缀路由；清理路径**显式实现**——`SessionStore.remove` 里追加 rm artifacts/<id>）
- [ ] 3.4 泛化 `ReadWorkflowResult` 按 ref 前缀分派（工具名/schema 不变；**改写 description**；确认根/深度到限子 agent 注册路径）
- [ ] 3.5 工具结果有界化**两段式**（D1）：判定纯函数 `agent/memory/tool_result_policy.py` + loop 侧注入 store/scope；`loop.py` 三处写入点经同一判定
- [ ] 3.6 `MemoryManager.prune_tool_results` 剪 `messages` 工具结果（在 `compact_if_needed` 之前；**`added_iteration <= current_iteration - 1`**（A1 已拍板）∩（滑出窗口 ∪ 单条超阈）；**`:854`+`:1047` 两 append 点都记 `added_iteration`**；含 `_tokens` 重置；含预览保尾）
- [ ] 3.7 `trace_recorder.record_tool_result` 对超阈 observation 存 bounded 预览 + 诚实标记；**`record_tool_call` 的 arguments 亦 bounded**；评估 `record_edit`/`record_iteration` 的全文面
- [ ] 3.8 `ToolCallMade.result` 与 `arguments` 超阈 bounded（保 `name`）
- [ ] 3.9 `compact_if_needed` 加硬上限（token + 字节双维度；超硬限无视 gap 强制压；次序=剪枝→判硬顶→强压）
- [ ] 3.10 spill 可观测（新增 trace step `tool_result_spill` + `on_event`；计数区分无损 spill / 有损 bounded）
- [ ] 3.11 **D12（形态 c）落地**：`tool_result` 事件 payload 去全文、增 `tool_call_id`；新增只读端点 `GET /api/sessions/{id}/tool-result/{tool_call_id}`（找 session.messages → 全文直返 / 已 spill 则解析 ref 读回 / 找不到返 missing）；`chat.js` Expand 改 fetch 懒加载 + Collapse 释放缓存；回归测试（含 missing 降级）
- [ ] 3.12 回归：`agent-runtime` tool-call 链 + `memory-context` 既有压缩 + `context-engineering` Read/分页 + `web-ui`（tool_result 事件/展开）
- [ ] 3.13 端到端：#278 复现器缩比版（单 agent 直读，RSS 峰值对照 E0）

## 4. 审阅与验收

- [ ] 4.1 `/review-loop` 独立审阅至 PASS 或 3 轮封顶（review report + manifest）
- [ ] 4.2 全量 `uv run pytest -q`（对照 pristine 排除环境噪声）
- [ ] 4.3 真实验收：A0 GC 不变量（机械）/ A1 剪枝 / A2 账本有界 / A3 无损回读 / A4 不谎称 / A5 不退化 / A6 硬顶
- [ ] 4.4 E0 对照：复现器对拍 RSS 峰值（如实记录，不设门槛）
- [ ] 4.5 **benchmark smoke**（触及 `agent/loop.py`/`agent/tools/`）：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-tool-result-lifecycle`

## 5. 收尾

- [ ] 5.1 spec delta 同步到 current spec（`openspec/specs/context-engineering/spec.md` + `openspec/specs/memory-context/spec.md`；受保护路径，需结构化事件）
- [ ] 5.2 归档到 `openspec/changes/archive/2026-10-03-tool-result-lifecycle/`（受保护路径）
- [ ] 5.3 从 `docs/openspec-change-backlog.md` 移除（受保护路径）
- [ ] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [ ] 5.5 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
- [ ] 5.6 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描
- [ ] 5.7 发起 PR（标题关联 #282），写明验证结果
- [ ] 5.8 (post-merge) PR 合入后给 #282 / #280 加完成说明 comment 并关闭 #282
