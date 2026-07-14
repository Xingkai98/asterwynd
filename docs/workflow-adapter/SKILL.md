---
name: asterwynd-workflow-prompt-adapter
description: 在无法运行严格 workflow host wrapper 的客户端中使用。该适配器要求每次 agent run 前后调用 workflow CLI，让状态可恢复；它不拥有人工审批能力。
---

# Asterwynd 工作流提示词适配器

该适配器用于 Happy Coder 或通用 coding agent 这类只能遵循 prompt 并执行 shell 命令、但不能托管可信审批边界的客户端。

## 进入步骤

每次 agent run 开始前，在受管项目中执行：

```bash
asterwynd workflow enter --workflow <workflow-id> --json
```

如果返回 `waiting_for_human: true`，必须停止并要求用户通过可信 host 命令审批。agent session 内不得调用 `workflow gate approve`。

## 恢复状态

当 session 重启、用户询问当前进度，或需要重新展示状态时执行：

```bash
asterwynd workflow status --workflow <workflow-id> --json
```

`status` 只用于恢复和展示状态，不替代 `enter` 领取 WorkItem，也不拥有审批能力。

## 退出步骤

完成当前 WorkItem 后执行：

```bash
asterwynd workflow report \
  --workflow <workflow-id> \
  --work-item-id <work-item-id> \
  --expected-version <version> \
  --summary "<short result>" \
  --enforcement-level prompt_adapter \
  --json
```

## 强制级别

- 正常 Prompt Adapter 运行记录 `prompt_adapter`。
- 客户端无法可靠限制写入范围时记录 `audit_only`。
- 不得记录 `strict_host`；只有 `asterwynd workflow chat` 严格 host wrapper 可以使用该级别。

## 审批规则

Prompt Adapter 不能审批 gate。精确 `ok` 审批只属于可信 host wrapper，或满足 `ASTERWYND_WORKFLOW_TRUSTED_HOST=1` 且没有 `ASTERWYND_WORKFLOW_AGENT_CONTEXT=1` 的 CLI host 命令。
