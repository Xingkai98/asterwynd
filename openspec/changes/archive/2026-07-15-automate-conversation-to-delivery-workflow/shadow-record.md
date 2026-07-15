# Shadow Record

试点 change：`automate-conversation-to-delivery-workflow`。

对比目的：迁移期验证旧 `handoff.json` 只读视图与 Workflow Control Plane event-derived snapshot 可以表达同一阶段进度，同时确认旧脚本不再写入状态。

验证方式：

- `tests/workflow_control/test_shadow_record.py` 构造旧 handoff 只读输入。
- 同一测试通过 `WorkflowOrchestrator` 创建 event history 并派生 snapshot。
- 断言旧 `phase/sub_state` 与新 event-derived `StateSnapshot` 一致。
