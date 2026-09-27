# Tasks — add-reasoning-content-support

## 0. 前置

- [x] 0.1 建跟踪 issue #256 并在 proposal 关联
- [x] 0.2 维护 `## Reference Implementation Research`（`research_tier: full`，五个 research questions + F1–F5 findings + design impact）
- [x] 0.3 写 `design.md`（D1 消息模型 / D2 回传策略 / D5 事件隔离 / D6 压缩边界 / D7 自愈）
- [x] 0.4 **停轮**把 Open Questions（Q1–Q9）逐项抛给用户确认，每条配具体场景例子；答复已记录到 `reviews/grill-design.md` 的 `## User Confirmation`（Q6 经用户追问「业界对 keep-all 模型咋做的」后二次确认）
- [x] 0.5 运行 batch-grill-me（`/grill`，独立零记忆 subagent 设计追问），产出 `reviews/grill-design.md`（5 条 Confirmed Decisions + 9 条 Open Questions + 挑战记录；证伪 D2 一处事实、发现 `build_history_payload` 遗漏）

## 1. 规格

- [x] 1.1 维护 `specs/agent-runtime/spec.md` delta（3 条 ADDED Requirement：采集/持久化/回传、流式事件隔离、压缩处理）
- [x] 1.2 维护 `specs/web-ui/spec.md` delta（2 条 ADDED Requirement：折叠展示、流式消费）
- [x] 1.3 落地 spec delta 到 `openspec/specs/`（当前规格同步；受保护路径，写 `current_spec_synced` 事件）
- [x] 1.4 维护 `## Impact Analysis`，把 Q1–Q4 的待确认项清理为明确结论
- [x] 1.5 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险

## 2. 测试（TDD：先写失败测试）

- [x] 2.1 **采集（Anthropic）**：流式 `thinking_delta` + `signature_delta` → 断言 reasoning 段含正确文本与 opaque 载荷
- [x] 2.2 **回传（Anthropic）**：含 thinking 的历史 assistant → `_build_payload` 断言发出带 `signature` 的 thinking block 且 opaque 逐字节一致
- [x] 2.3 **回传（OpenAI）**：既有 `reasoning_content` 回传行为回归
- [x] 2.4 **事件隔离**：reasoning 增量走独立事件、不混入 `assistant_delta`
- [x] 2.5 **压缩**：compaction 保留最新轮 reasoning、可丢更早轮
- [x] 2.6 **端到端不回归**：无 reasoning 的 provider 全链路逐字段不变
- [x] 2.7 **浏览器回归**（`tests/web_tests/test_browser.py`）：折叠区默认关闭 / 单击展开 / 再点折叠 / 正文不被污染 / 无 reasoning 不渲染 / 降级事件 UI 可见。审阅 Round 3 指出初版虚勾（无对应测试），本轮补 3 条真实 Playwright 断言并做变异验证（默认展开 → 变红）
- [x] 2.8 每条测试做**变异验证**（改坏实现 → 必红；还原 → 必绿）并记录

## 3. 实现

- [x] 3.1 `agent/message.py`：reasoning 结构化段 + 序列化/反序列化（含旧字段兼容）
- [x] 3.2 `agent/llm.py`：`LLMResponse` / `LLMStreamEvent` 增 reasoning 承载与事件类型
- [x] 3.3 `agent/anthropic_llm.py`：流式采集 thinking/signature；`_build_payload` 回传 thinking block
- [x] 3.4 `agent/openai_llm.py`：接入统一模型（回传语义不变）
- [x] 3.5 `agent/loop.py`：透传 reasoning 到事件与消息
- [x] 3.6 `agent/memory/manager.py`：compaction 保留最新轮 reasoning
- [x] 3.7 `web/session.py`：`build_history_payload` 携带 reasoning（重连重绘，grill 发现的遗漏）+ `on_event` 转发 reasoning 增量
- [x] 3.8 `web/static/chat.js` + `style.css`：通用折叠区（默认关闭、单击展开、流式追加）；`renderHistory` 历史重绘也渲染折叠区
- [x] 3.9 `agent/anthropic_llm.py`：**新建 `anthropic-beta` 头通道**（`clear_thinking_20251015` 清理 + `block_binding.prefix_mismatch_behavior=drop_block`）
- [x] 3.10 `agent/anthropic_llm.py`：reasoning 相关 400 的**两套**文案自愈（缺回传 / 签名失配），降级粒度为「本轮 + session 状态」（D7）

## 4. 验证

- [x] 4.1 四条路径的端到端实测（Anthropic 原生 / DS-Anthropic / DS-OpenAI / OpenAI 官方形态）
- [x] 4.2 全量 pytest 通过（改动涉及 AgentLoop 与 Web）
- [x] 4.3 浏览器回归通过
- [x] 4.4 OpenSpec strict validate 通过
- [x] 4.5 项目 artifact checker 通过
- [x] 4.6 benchmark smoke 验证（改动涉及 agent-runtime 核心面：跑 `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-reasoning` 确认 benchmark smoke 不回归）

## 5. 收尾

- [x] 5.1 运行 `/review-loop` 独立审阅闭环，产出 `reviews/building-review.md` + manifest（PASS）
- [ ] 5.2 文档影响检查：`docs/architecture.md`、`docs/agent-internals.md` 同步；`docs/known-issues.md` / `docs/known-debt.md` 按结论记录（含「DS 端点 id 启发式」这一未文档化依赖）；扫描 `README.md`/`AGENTS.md`/`CONTEXT.md`
- [ ] 5.3 同步 backlog（受保护路径，写 `backlog_updated` 事件）
- [ ] 5.4 归档 change 到 `openspec/changes/archive/2026-09-27-add-reasoning-content-support/`，从 backlog 移除
- [ ] 5.5 (post-merge) 发起 PR；合入时给 issue #256 添加完成说明 comment 并关闭
