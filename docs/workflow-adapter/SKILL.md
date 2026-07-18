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

## Happy Coder 端到端验证

这条验证路径确认 `skill + AGENTS.md` 降级入口在新 session 中可恢复状态、按 WorkItem 推进，并在 gate 前停止。它不验证强 host wrapper；强入口验证见 `docs/development-guide.md` 的 Workflow Control Plane 端到端验证。

### 1. 准备 workflow id

在仓库根目录执行：

```bash
WF="happy-skill-e2e-$(date +%Y%m%d%H%M%S)"
echo "$WF"
uv run asterwynd workflow prompt-adapter show --json
```

### 2. Happy Coder Session 1：领取并完成第一个 WorkItem

新开 Happy Coder session，打开当前仓库目录，然后把 `<workflow-id>` 替换为上一步输出的 `$WF`，发送：

```text
请按 docs/workflow-adapter/SKILL.md 的 Prompt Adapter 规则执行。
workflow id 是 <workflow-id>。

本轮开始前先运行：
uv run asterwynd workflow enter --workflow <workflow-id> --json

只执行返回的 WorkItem。不要调用 workflow gate approve。
本轮只做一个轻量任务：读取 docs/workflow-adapter/AGENTS_SNIPPET.md，并总结当前 adapter 规则。
结束前必须运行：
uv run asterwynd workflow report --workflow <workflow-id> --work-item-id <enter返回的id> --expected-version <enter返回的version> --summary "read prompt adapter snippet" --enforcement-level prompt_adapter --json
```

外部终端检查：

```bash
uv run asterwynd workflow status --workflow "$WF" --json
```

预期状态为 `requirements.drafting`。

### 3. Happy Coder Session 2：跨 session 恢复并到达 gate

再新开一个 Happy Coder session，打开同一仓库目录，发送：

```text
继续按 docs/workflow-adapter/SKILL.md 的 Prompt Adapter 规则执行。
workflow id 是 <workflow-id>。

先运行 workflow enter，按返回 WorkItem 推进到 requirements ready_for_review。
不要调用 workflow gate approve。
结束前运行 workflow report，enforcement-level 使用 prompt_adapter。
```

外部终端检查：

```bash
uv run asterwynd workflow status --workflow "$WF" --json
```

预期状态为 `requirements.ready_for_review`，说明新 session 没依赖聊天记忆也能恢复 workflow 状态。

### 4. Happy Coder Session 3：验证 gate 前停止

再新开一个 Happy Coder session，发送：

```text
继续按 docs/workflow-adapter/SKILL.md 的 Prompt Adapter 规则执行。
workflow id 是 <workflow-id>。

先运行 workflow enter。如果返回 waiting_for_human 是 true，必须停止并告诉我需要人工可信审批；不要调用 approve。
```

预期 Happy Coder 停止，不继续设计或开发。

### 5. 外部可信审批

在普通终端中先验证非可信审批会失败：

```bash
uv run asterwynd workflow gate approve --workflow "$WF" --message ok --json
```

再用可信 host 环境审批：

```bash
ASTERWYND_WORKFLOW_TRUSTED_HOST=1 \
uv run asterwynd workflow gate approve --workflow "$WF" --message ok --json
```

预期状态进入 `design.writing_design`。这证明 Prompt Adapter 只能提示和记录状态，不能在 Happy Coder session 内代替用户审批。
