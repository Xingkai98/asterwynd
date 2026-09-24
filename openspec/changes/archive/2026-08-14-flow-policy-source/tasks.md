# Tasks: flow-policy-source

## 1. 规格

- [x] 1.1 创建 proposal.md，明确需求、非目标、行为定义与验收（关联 issue #131）。
- [x] 1.2 创建 design.md，记录 Context、Goals/Non-Goals、Decisions（D1-D9）、Risks、Testing Strategy。
- [x] 1.3 维护 `## Impact Analysis`（proposal.md），列出影响/不影响/待确认影响面。
- [x] 1.4 维护 `## Reference Implementation Research`（status: disabled + 理由 + findings + design impact）。
- [x] 1.5 开发前使用独立 subagent 等价设计追问（grill）审视 `design.md`，产出 `reviews/grill-design.md`（6 条 Confirmed Decisions + Q1-Q10 + 风险），逐项确认实现细节；停轮获得用户对 `## Open Questions`（Q1-Q10）的确认并记录到 `## User Confirmation`。
- [x] 1.6 更新 `docs/openspec-change-backlog.md`，把 flow-policy-source 加入未实现队列（配 workflow-events.jsonl 解释事件）。
- [x] 1.7 当前规格同步：把 dev-workflow-state-machine spec delta 合并到 `openspec/specs/dev-workflow-state-machine/spec.md`，确认未实现能力没有被写成已实现，并配 workflow-events.jsonl 解释事件。

## 2. 测试

- [x] 2.1 guard 单元测试：从 `flow-policy.json` 加载受保护路径规则；内嵌默认表；fail-closed（策略文件缺失/损坏/非法 schema → exit 2）；match_type（exact/prefix/contains）语义；路径归一化（`docs/./`、`..`、绝对路径）。
- [x] 2.2 guard 4 个绕过回归测试：`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./` 变体 → 全部 exit 2 拦截。
- [x] 2.3 guard User Confirmation 正则死锁修复测试：`- **Q8**（分支命名）:` 后缀可提取；`_h2_section` 跳过 fenced code block 内的 `##`。
- [x] 2.4 checker 单元测试：`PROTECTED_PATH_RULES` 从策略文件加载；checker 规则集 == 策略表 `event_explained` 子集。
- [x] 2.5 同源 parity 测试：磁盘表 == guard 内嵌默认表；guard Bash fragment 集 == 策略表 path 值集；unconfirmed 词表 guard↔checker 一致（bash 写正则仅 guard 侧有实现，checker 无对应，无 parity 对象）。
- [x] 2.6 内容门槛测试（#123）：tasks 全勾 + 命中「自认未完成」短语 → checker exit 2；tasks 未全勾 → 不触发内容门槛。
- [x] 2.7 agent schema JSON Schema 校验测试（#127）：非法 provider/model 类型、未知 phase 键 → checker 报错。
- [x] 2.8 集成测试：策略文件变更后 guard 与 checker 同时生效；`policy-show`/`policy-validate` 子命令行为。

## 3. 实现

- [x] 3.1 创建 `scripts/flow-policy.json`（受保护路径规则表 + `phases`/`review` agent schema 占位），按 D4 清单。
- [x] 3.2 guard 改造：从策略文件加载规则；内嵌默认表；fail-closed（缺失/损坏 exit 2）；match_type 语义；Write/Edit 路径归一化；Bash 受保护路径扫描前移（is_write 之前）。
- [x] 3.3 guard 修复：User Confirmation 正则死锁（容忍 `（…）` 后缀 + `_h2_section` 跳过代码块）。
- [x] 3.4 checker 改造：`PROTECTED_PATH_RULES` 从策略文件加载（替换硬编码 :122-128）；规则来源失败时 fail-closed。
- [x] 3.5 checker 内容门槛（#123）：tasks 全勾时对 Reference Implementation Research 字段做「自认未完成」短语级模式匹配，命中 exit 2。
- [x] 3.6 checker agent schema JSON Schema 校验（#127 P0 边界）：`flow-policy.json` 的 `phases`/`review` 节结构校验。
- [x] 3.7 `workflow_state.py` 新增 `policy-*` 子命令（`policy-show`/`policy-validate`）。
- [x] 3.8 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试（tests/test_workflow_guard.py 等）。
- [x] 4.2 运行全量测试 `uv run pytest -q`。
- [x] 4.3 运行 OpenSpec strict validate `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 4.4 运行项目 artifact checker `uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.5 确认 4 个绕过用例被拦、归档校验不变（P0 出口）。

## 5. PR 收尾

- [x] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-flow-policy-source/`。
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [x] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [x] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 5.6 PR 合入时，给关联 GitHub issue #131 添加完成说明 comment 并关闭。

## 6. 审阅修复记录（building-review Round 1，verdict CHANGES_REQUESTED）

- [x] R1-1（HIGH）特权 CLI 豁免可被 `&&`/`;` 链式劫持 → `_is_privileged_cli` 严格化为独立调用（无复合/重定向/命令替换）+ 链式劫持回归测试。
- [x] R1-2（MEDIUM）内嵌默认表运行时 fallback 违反 parity-only → 移除 `_CURRENT_RULES or _DEFAULT_PROTECTED_PATHS`，Write/Bash 一致用磁盘规则集 + 空规则一致性测试。
- [x] R1-3（MEDIUM）checker/policy-validate 对 schema 非法策略裸 RuntimeError → 捕获返回可读错误 + 测试。
- [x] R1-4（MEDIUM）unconfirmed 词表 parity 无测试锁 → 新增 guard↔checker 词表机械断言；tasks 2.5 措辞修正（bash 写正则仅 guard 侧无 parity 对象）。
- [x] R1-5（LOW）shell 变量拼接路径绕过 → 记录为已知限制（静态 shell 分析无法解析变量，属工具面纪律），记 known-debt，不引入过度误拦。
- [x] R1-6（LOW）Write/Edit blanket contains vs match_type → design D2 文档对齐（guard 面对任意路径字符串用 contains 保守超集，deny-by-default）。
- [x] R1-7（LOW）guard 恢复文案误导 + policy-set 无法修复损坏 JSON → 文案微调（明确「先修复 JSON，可读时可 policy-validate」）。
