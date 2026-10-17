# ADR-0005: 删除 legacy asterwynd 形态 review manifest 模块与写通道（第二刀）

- **Status**: accepted
- **Date**: 2026-10-17
- **Deciders**: 用户裁决（issue #316 第二刀方向）、主 agent、独立 grill / 设计对抗审阅者
- **关联**: [ADR-0004](./ADR-0004-retire-duplicate-review-manifest-check.md)（第一刀）、issue #316、issue #305

## Context

第一刀（`retire-manifest-check`，PR #317 / merge `5225207`）下掉了本仓 checker 对 asterwynd 形态
manifest（`reviews/<phase>-review-manifest.json`）的**消费面**，但生产面仍在：

- `agent/workflow/review_manifest.py`（264 行）提供 build / write / verify；
- `scripts/workflow_state.py review-manifest` 是合法子命令；
- `scripts/flow-policy.json` 与 `scripts/workflow_guard.py` 把 `-review-manifest.json` 当
  `manifest_verified` 受保护路径并豁免该 CLI；
- `agent/workflow/resume_audit.py` 把它当 workflow 管理文件忽略；
- 测试与文档仍称其为「legacy 通道，由第二刀处置」。

第一刀规格与 ADR-0004 明确把上述项留给第二刀。删除模块前，`artifact-event` 的归档回退
依赖模块的 `change_dir_for(archived=True)`，因此不能只删 import。

## Decision

1. **删除模块** `agent/workflow/review_manifest.py`，不保留薄壳、不新建替代模块。
2. **删除 CLI 子命令** `review-manifest` 与 `cmd_review_manifest`、`_resolve_review_base_sha`；
   调用它得到 argparse `invalid choice`（非零退出、无副作用）。
3. **归档解析内联**到 `scripts/workflow_state.py`：以 `CHANGES_ROOT / "archive"` 为根、按名
   排序、`re.fullmatch(r"\d{4}-\d{2}-\d{2}-<id>")` 精确匹配；同 id 命中多个日期目录时
   fail-closed。删除已不可达的 `_archive_dir_matches_change_id` 调用侧断言。
4. **删除受保护规则** `-review-manifest.json`（策略表与 guard 内嵌默认表）及 privileged CLI
   豁免中的 `review-manifest`。`manifest_verified` governance 枚举保留（无规则使用），只在
   `docs/known-debt.md` 记录。
5. **删除 resume audit 忽略项**：历史 manifest 的改动按普通文件进入 resume audit；
   同时修正 `_status_path` 对首行工作区修改路径的既有解析缺陷（`strip()` 去掉前导空格后
   原实现会吃掉路径首字符），并加单测。
6. **历史 80 份 manifest 冻结**：不迁移、不重算、不删除；仍在 `openspec/changes/archive/**`
   的归档前缀保护下。
7. **同步规格与文档**：`dev-workflow-gate` / `dev-workflow-state-machine` /
   `change-documentation` 三份 current spec 与 `AGENTS.md`、README 双语、development-guide、
   requirements-process、interview-script、known-debt、ADR-0004 的退役口径。

## Alternatives Considered

| 备选 | 描述 | 拒绝原因 |
|------|------|---------|
| 保留薄壳模块 | 只删 CLI，保留 `review_manifest.py` 供 `artifact-event` 用 | 留下没有生产者的「活 import 路径」，退役不彻底；唯一需要的解析只有 12 行 |
| 抽新模块 `change_paths.py` | 把 `change_dir_for` 移到通用路径模块 | 为一个函数新增模块，增加 import 面且无复用价值 |
| 保留 CLI 并打印「已退役」 | 保留命令面的 deprecation 提示 | CLI surface 与文档继续承认该通道；与「未知子命令、无副作用」的既有惯例冲突 |
| 保留受保护规则 | 以「历史文件仍在」为由保留 | 历史文件已被归档前缀规则覆盖；保留只会继续拦截一个不存在的流程产物 |
| 保留 resume audit 忽略项 | 避免历史证据改动被审计 | 写通道删除后，对历史 manifest 的修改不再由 workflow 产生，不应隐形 |
| 迁移历史 manifest | 补齐字段 / 重算 hash / 转换成 witnessloop 形态 | 第一刀已实测 80 份无法干净迁移（缺 `author_run_id`、27 份 `tasks_hash` 漂移、8 份提交不可解析），且 checker 已不消费 |

## Consequences

- 正面：仓库只剩一套 review manifest 实现；删除约 264 行模块、CLI 写通道、保护/豁免/忽略
  配置与对应正向测试；CLI 误用会明确失败。
- 负面/边界：active change 中手写 `*-review-manifest.json` 不再被 guard 立即拦截（它不是
  任何流程产物，归档内历史文件仍受保护）；`manifest_verified` 成为未使用策略词汇；历史
  manifest 的改动现在会进入 resume audit（有意暴露）。
- 行为修正：内联解析用 `fullmatch`，关闭「`alpha` 命中 `alpha-beta`」的前缀碰撞；同 id 多
  日期目录从「依赖 `iterdir()` 顺序」变为明确错误。既有兄弟前缀回归新增「不存在」断言，
  多日期目录新增 fail-closed 用例。
- 不变：witnessloop 形态三份 stage manifest、`## 闭环出口` PASS 判据、RIR / Impact /
  benchmark / backlog / 归档点其它门禁。

## Revisit Conditions

- [ ] 需要重新引入 asterwynd 形态 manifest（需先证明 witnessloop 形态不足，并另行立项）。
- [ ] witnessloop 开始读取或校验 `verdict`，且本仓不再需要本地 `## 闭环出口` 检查。
- [ ] 需要恢复 `--check-archived` 的历史 manifest drift 检测。
