# group-unlimited-discussion

关联 issue：[#333](https://github.com/Xingkai98/asterwynd/issues/333)

群聊 `everyone` 模式新增「讨论链」形态：`discussion_mode = single`（默认，现状）/ `unlimited`（自动续轮，直到全员静默收敛或用户停止）；新增「停止讨论」控件与 `team:` 配置节安全阀参数（默认 200 轮 / 600 成员回合 / 6000 秒）。

- `proposal.md`：动机（收回首版"仅用户开轮"的有意分歧）、需求、影响面、RIR。
- `design.md`：Decision 1–10（房间字段与校验、讨论链与互斥、续轮判定、收敛、停止语义、安全阀、事件契约、teardown、兼容性、测试策略）。
- `tasks.md`：grill / TDD / 实现 / 规格同步 / 收尾。
- `specs/`：`multi-agent-collaboration` / `web-ui` / `configuration` 三个 delta。
- `reviews/`：grill 与审阅闭环证据（随实现补齐）。
