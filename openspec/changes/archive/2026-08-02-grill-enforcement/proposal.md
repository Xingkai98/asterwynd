# Proposal: 流程强制 — batch-grill-me 独立执行 + 写代码前门禁

## Change Type

primary: process
secondary:
  - change-documentation

## 需求

1. 复刻 subagent 审阅闭环的机制到 batch-grill-me：开发前由独立零记忆 subagent 执行设计追问，产出结构化决策记录。
2. 新增写代码前门禁：workflow_guard（或新 hook）在 change 首次写操作时检查 grill 证据，缺失则阻止写操作。
3. artifact checker 的 `_check_design_review_task` 从"字面检查 tasks.md 含 batch-grill 字样"升级为"验证结构化 grill 证据存在且有实质内容"。
4. 新增 `/grill` 命令封装独立 subagent grill 闭环（对应对称的 `/review-loop`）。

## 背景

三个 Batch A session（#74/#75/#76 第二批）被用户发现「一股脑开发，没有 batch-grill-me 提问」。排查发现当前所有护栏都拦不住：

- AGENTS.md 规则只是指令，LLM 可选择性遵守，无机械强制。
- artifact checker 只检查 tasks.md 是否含「batch-grill」字样（`"batch-grill" in lowered`），agent 加一行字即可通过。
- workflow_guard / CI 只管受保护文件、只管实现后 review 证据，不管实现前 grill。

根因：所有门禁基于 agent 自我报告（荣誉制度）。grill 证据是主 agent 自证的（tasks 勾字），无独立执行者、无前置阻塞、无可验证内容。

## 变更范围

- `AGENTS.md`：把「必须 batch-grill-me」从文字规则升级为"写代码前被机械拦截"的描述。
- `.claude/commands/grill.md`：新增独立 subagent grill 闭环命令（本地）。
- `scripts/workflow_guard.py`：写代码前检查 grill 证据（缺失 exit 2）。
- `scripts/check_openspec_artifacts.py`：`_check_design_review_task` 验证结构化 grill 证据。
- `openspec/specs/change-documentation/spec.md`：更新设计追问 requirement。

## 验收标准

1. 新 change 无 grill 证据时，写代码被 workflow_guard 阻止（exit 2）。
2. 有结构化 grill 证据时，写代码放行。
3. artifact checker 对缺 grill 证据的 change 报错（替换字面检查）。
4. `/grill` 命令 spawn 独立 subagent 产出结构化决策记录。
5. 全量 pytest + openspec validate + artifact checker 通过。

## Impact Analysis

- `AGENTS.md`：流程文档更新。
- `.claude/commands/grill.md`：新增命令。
- `scripts/workflow_guard.py`：写操作门禁新增 grill 检查。
- `scripts/check_openspec_artifacts.py`：design review task 检查逻辑。
- 测试：`test_workflow_guard.py`、`test_openspec_artifact_checker.py`。

## Reference Implementation Research

- status: disabled
- reason: 本 change 是流程/工具链强制机制，设计复刻本仓库 #90 已实现的 subagent 审阅闭环（`/review-loop` + artifact checker 强制），无需外部参考。
