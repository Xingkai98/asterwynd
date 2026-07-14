# Workflow Prompt Adapter 片段

使用降级 Workflow Prompt Adapter 的仓库可接入以下短规则：

1. 每次 run 开始时执行 `asterwynd workflow enter --workflow <workflow-id> --json`。
2. 如果 workflow 位于 `ready_for_review`，立即停止；agent session 内不得批准 gate。
3. 只执行返回的 WorkItem。
4. run 结束时执行 `asterwynd workflow report --workflow <workflow-id> --work-item-id <id> --expected-version <version> --summary <summary> --enforcement-level prompt_adapter --json`。
5. evidence enforcement 只能记录 `prompt_adapter` 或 `audit_only`；不得宣称 `strict_host`。
