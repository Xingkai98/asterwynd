# Workflow Prompt Adapter Snippet

For repositories using the degraded Workflow Prompt Adapter:

1. At the start of each run, execute `asterwynd workflow enter --workflow <workflow-id> --json`.
2. If the workflow is at `ready_for_review`, stop. Do not approve the gate from the agent session.
3. Do only the returned WorkItem.
4. At the end of the run, execute `asterwynd workflow report --workflow <workflow-id> --work-item-id <id> --expected-version <version> --summary <summary> --json`.
5. Mark evidence enforcement as `prompt_adapter` or `audit_only`; never claim `strict_host`.
