# 工作流提示词适配器片段

使用降级工作流提示词适配器的仓库可接入以下短规则：

1. 每次 run 开始时执行 `asterwynd workflow enter --workflow <workflow-id> --json`。
2. 如果 workflow 位于 `ready_for_review`，立即停止；agent session 内不得批准 gate。
3. session 恢复或用户询问状态时执行 `asterwynd workflow status --workflow <workflow-id> --json`。
4. 只执行返回的 WorkItem。
5. run 结束时执行 `asterwynd workflow report --workflow <workflow-id> --work-item-id <id> --expected-version <version> --summary <summary> --enforcement-level prompt_adapter --json`。
6. evidence enforcement 只能记录 `prompt_adapter` 或 `audit_only`；不得宣称 `strict_host`。
