# Tasks: 工具结果生命周期

## 1. 立项与调研

- [ ] 1.1 关联 GitHub issue #282（主）/ #280（父），写 `proposal.md`（Change Type / Why / 实测证据 / What Changes / Capabilities / 验收 / RIR / Impact Analysis / Non-Goals）
- [ ] 1.2 写 `design.md`（Context / Goals-Non-Goals / Decisions D0–D11 / Risks / Testing Strategy / Impact Analysis）
- [ ] 1.3 写 spec delta（context-engineering ADDED 1「单受管持有与释放」+ memory-context MODIFIED 1「压缩硬顶」）
- [ ] 1.4 补齐 `## Reference Implementation Research`（`research_tier: full`；deepseek-harness + Anthropic context editing + 本地 6 仓库）
- [ ] 1.5 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）
- [ ] 1.6 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过

## 2. grill 与对抗（实现前强制）

- [ ] 2.1 独立零记忆 subagent 按 `batch-grill-me` 追问 `design.md`，产出 `reviews/grill-design.md`
- [ ] 2.2 独立零记忆对抗 subagent 证伪 grill 结论，产出 `reviews/grill-adversarial.md`；主 session 逐条复核新发现（`file:line`）
- [ ] 2.3 停轮把经对抗幸存的 `## Open Questions` 逐项（每条配具体例子）抛给用户，等待答复
- [ ] 2.4 用户答复写回 `grill-design.md` 的 `## User Confirmation` 节（`- **Q<N>**: 用户答复：<实质内容>；确认时间: <date>`）
- [ ] 2.5 按 grill + 对抗结论回写 design/proposal/spec delta

## 3. 实现（测试先行）

- [ ] 3.1 前置核实（D11）：逐点确认无消费者依赖 `trace` observation / `ToolCallMade.result` 的**全文**（预期仅 `benchmarks/runner.py:661` 落盘）
- [ ] 3.2 先写失败测试：GC 不变量 / `messages` 陈旧被替换 / 当轮保留 / `trace`+`tool_calls_made` bounded / 按 ref 无损回读 / 无 ref 不谎称 / tool-call 链合法 / `_tokens` 重置 / 硬顶无视 gap / 图片字节维度
- [ ] 3.3 agent 通用 ref 存储（复用 `WorkflowStore` 实现；`.asterwynd/artifacts/`；根 `session_id` / 子 `run_id` 寻址；清理路径显式实现）
- [ ] 3.4 泛化 `ReadWorkflowResult` 按 ref 前缀分派（工具名/schema 不变；改写 description；确认根/深度到限子 agent 注册路径）
- [ ] 3.5 统一工具结果入库通道（`loop.py`）：三处持有者经同一判定点
- [ ] 3.6 `MemoryManager` 加 `messages` 工具结果剪枝（在 `compact_if_needed` 之前；「已消费一轮」∩（滑出窗口 ∪ 单条超阈）；含 `_tokens` 重置）
- [ ] 3.7 `trace_recorder.record_tool_result` 对超阈 observation 存 bounded 预览 + 诚实标记
- [ ] 3.8 `ToolCallMade.result` 超阈 bounded（保 `name`/`arguments`）
- [ ] 3.9 `compact_if_needed` 加硬上限（token + 字节双维度；超硬限无视 gap 强制压；次序=剪枝→判硬顶→强压）
- [ ] 3.10 spill 可观测（计数 + 字节；经既有 trace/event 通道）
- [ ] 3.11 回归：`agent-runtime` tool-call 链 + `memory-context` 既有压缩 + `context-engineering` Read/分页
- [ ] 3.12 端到端：#278 复现器缩比版（单 agent 直读，RSS 峰值对照 E0）

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
