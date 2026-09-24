## ADDED Requirements

### Requirement: 机械门禁的信任边界

项目 artifact checker 的受保护路径解释门禁 SHALL 定位为**防误改**（防止改动受保护路径时漏配解释事件）而非**防伪造**。它 SHALL 只校验存在匹配的结构化解释事件（`event_type` / `artifact_path` / 必填字段齐全），SHALL NOT 尝试判定该事件是否出自真实的人类授权——`approved_by` 是自由字符串，无法被机械校验。

文档 SHALL NOT 声称该门禁提供了防伪造保证；其信任边界 SHALL 明文记录该边界位于仓库写权限（谁拥有 push 权限），而非门禁本身。

#### Scenario: 解释门禁只校验事件的存在与形状

- **WHEN** 一个受保护路径被改动
- **THEN** checker SHALL 要求存在覆盖该路径的结构化解释事件（匹配的 `event_type` 与 `artifact_path`，且必填字段齐全）
- **AND** checker SHALL NOT 校验发起事件的 change 是否真实立项、或 `approved_by` 是否对应真实身份

#### Scenario: 信任边界有明文记录

- **WHEN** 维护者查阅受保护路径门禁的保证强度
- **THEN** `docs/known-debt.md` SHALL 将其记录为「防误改而非防伪造」，并说明三条加固设想（绑定真实身份 / PR 审批背书 / 收紧锚点）均已排除
- **AND** 该边界 SHALL NOT 只以「待加固」措辞记录而暗示机械加固可行
