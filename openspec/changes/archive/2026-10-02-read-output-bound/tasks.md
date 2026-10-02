# Tasks: Read 工具默认输出上界

## 1. 立项与调研

- [x] 1.1 关联 GitHub issue #280（其第一步 B），写 `proposal.md`
- [x] 1.2 写 `design.md`（D1–D5 / Risks / Testing Strategy / Impact Analysis）
- [x] 1.3 写 spec delta（context-engineering ADDED 1 独立 Requirement）
- [x] 1.4 补 `## Reference Implementation Research`（`research_tier: light`；参考仓库读文件默认行为）
- [x] 1.5 同步 `docs/openspec-change-backlog.md` 入队（受保护路径）

## 2. grill 与确认

- [x] 2.1 独立零记忆 subagent 按 `batch-grill-me` 追问 `design.md`，产出 `reviews/grill-design.md`
- [x] 2.2 **按新流程纪律：派独立对抗 agent 证伪 grill 结论，产出 `reviews/grill-adversarial.md`；主 session 逐条复核其发现**
- [x] 2.3 停轮把（经对抗验证的）`## Open Questions` 逐项（每条配例子）抛给用户，等待答复
- [x] 2.4 用户答复写回 `grill-design.md` 的 `## User Confirmation` 节
- [x] 2.5 按 grill + 对抗结论回写 design/proposal/spec delta

## 3. 实现（测试先行）

- [x] 3.1 先写失败测试：超行界截断 + 显式注记 / 少行超长行按字节截 / `limit=0` 不落全文 / `offset` 无 limit 不到 EOF / ≤界逐字节=现状 / 显式正 limit 不变 / 图片不变 / 边界
- [x] 3.2 `Read.execute`：**无显式正 `limit`** 的三条路径（无参 / offset / limit=0）统一施加默认界（行 N=2000 **且** 字节 B=128KB，取先到者）
- [x] 3.3 上界常量化（N/B）；用 `limit is not None` 语义区分 0（D5）
- [x] 3.4 注记**显式**化（`truncated=true` + next offset）+ **同步 `_READ_PROGRESS_RE`**（双模块契约）+ 跨模块测试
- [x] 3.5 修 D6：默认截断 `offset=0` 不覆盖显式分页进度
- [x] 3.6 `total` 恒为文件总行数（D7）
- [x] 3.7 回归 `tests/agent/tools/`（含 `test_read_doc_and_pagination.py`）
- [x] 3.8 端到端对照：#278 复现器缩比版，如实记录 RSS 峰值对比基线（不设门槛）+ 确定性字节界单测（进 CI）

## 4. 审阅与验收

- [x] 4.0 review-loop Round 1（CHANGES_REQUESTED）修复：① 上界可配置（Q4：`tools.read.{max_lines,max_bytes}` + `ReadTool` 构造参数 + factory/调用链接线 + 测试）；② 文档口径统一（proposal/design/tasks 的 MODIFIED→ADDED、「SHALL 可配置」落地）；③ 清 `design.md` 的「待 grill 确认」占位；④ `proposal.md` 的「待 grill 补强」改为已完成
- [x] 4.1 `/review-loop` 独立审阅至 PASS 或 3 轮封顶（report + manifest）
- [x] 4.2 全量 `uv run pytest -q`
- [x] 4.3 验收：R0（单次超大文件读数受界）、R1（小文件逐字节不变）、R2（进度注记可测）；E0 如实记录
- [x] 4.4 benchmark smoke（触及 `agent/tools/`）

## 5. 收尾

- [x] 5.1 同步 spec delta 到 current spec（`openspec/specs/context-engineering/spec.md`；受保护路径，需结构化事件）
- [x] 5.2 归档到 `openspec/changes/archive/2026-10-02-read-output-bound/`
- [x] 5.3 从 `docs/openspec-change-backlog.md` 移除
- [x] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 5.5 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
- [x] 5.6 文档影响检查
- [ ] 5.7 (post-merge) 发起 PR 并合入（关联 #280），写明验证结果 + E0 实测（作为 A 的判据）；由主 session 执行，worktree 不 push
- [ ] 5.8 (post-merge) 合入后按 E0 实测决定 A（`agent-context-bound`）是否/如何做，并在 #280 记录
