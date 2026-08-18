# 流程状态机新增 awaiting 态：awaiting_grill_confirmation

流程状态机用「blocked + 子态」建模等待确认场景：设计追问（grill）流程需要一个新的等待态 `awaiting_grill_confirmation`——当 agent 产出设计追问结果、停轮等用户确认时，change 进入该态；用户确认后 `flow confirm` 恢复到设计阶段。

当前已有三个等待态（awaiting_proposal_confirmation / awaiting_human_review / awaiting_user_confirmation），各自有两类配套定义：状态机声明的「恢复语义」（进该态前的来源 + 恢复默认目标），以及 Python 层的镜像常量（校验 `--awaiting` 取值合法）+ 恢复默认值（`flow confirm` 解除等待时回到哪个子态）。**改动必须让四层同步**，否则 `flow block --awaiting` / `flow confirm` / 状态机校验 / parity 测试会互相矛盾：

1. **状态机声明**：新增 `blocked.awaiting_grill_confirmation` 态，恢复语义与既有等待态一致（恢复默认目标 = 设计阶段的写设计子态）。
2. **等待态镜像常量**：新态名必须进入 Python 镜像常量，否则 `flow block --awaiting awaiting_grill_confirmation` 在校验层直接被拒。
3. **恢复默认值表**：`flow confirm` 解除等待时需要查到该态的恢复默认目标，缺了则 confirm 失败。
4. **parity 测试**：既有断言「等待态集合」的测试必须同步为新集合（该测试现在断言精确的 3 个态），否则加态后既有测试即红。

判定成功的标准是端到端：`flow block --awaiting awaiting_grill_confirmation` 接受新值、`flow confirm` 恢复到正确的设计阶段子态、状态机校验通过、等待态集合的 parity 断言一致。

## Requirements

- 状态机校验通过，`awaiting_grill_confirmation` 是合法 awaiting 态
- 镜像常量包含新态名；恢复默认目标正确（设计阶段写设计子态）
- 既有「等待态集合」parity 断言更新为新集合
- `flow block --awaiting awaiting_grill_confirmation` 与 `flow confirm` 的既有用例模式不回归
