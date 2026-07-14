---
name: asterwynd-workflow-prompt-adapter
description: Use this in clients that cannot run the strict workflow host wrapper. It keeps workflow state visible by calling the workflow CLI before and after each agent run, but does not own human approval capability.
---

# Asterwynd Workflow Prompt Adapter

This adapter is the degraded entrypoint for clients such as Happy Coder or generic coding agents that can follow prompt instructions and run shell commands, but cannot host a trusted approval boundary.

## Required Entry Step

Before each agent run in a managed project, call:

```bash
asterwynd workflow enter --workflow <workflow-id> --json
```

If the response has `waiting_for_human: true`, stop and ask the user to approve through a trusted host command. Do not call `workflow gate approve` from an agent context.

## Required Exit Step

After completing the assigned work item, call:

```bash
asterwynd workflow report \
  --workflow <workflow-id> \
  --work-item-id <work-item-id> \
  --expected-version <version> \
  --summary "<short result>" \
  --json
```

## Enforcement Level

- Report `prompt_adapter` for normal operation.
- Report `audit_only` when the client cannot reliably prevent writes outside the active work item.
- Never report `strict_host`; only `asterwynd workflow chat` owns that level.

## Approval Rule

Prompt Adapter cannot approve gates. Exact `ok` approval belongs to the trusted host wrapper or CLI command with `ASTERWYND_WORKFLOW_TRUSTED_HOST=1` and without `ASTERWYND_WORKFLOW_AGENT_CONTEXT=1`.
