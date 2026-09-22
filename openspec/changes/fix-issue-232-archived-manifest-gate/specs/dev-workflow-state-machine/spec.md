## MODIFIED Requirements

### Requirement: Review evidence manifest

每个阶段的独立 review report SHALL 绑定机器可验证的 manifest。review report 文件为 `.handoff/<change-id>/<phase>-review.md`，manifest 文件为 `.handoff/<change-id>/<phase>-review-manifest.json`。gate/CI 不得只根据 review report 文本中的 `PASS` 判断审查通过。

存续期（active）change 的 manifest SHALL 在其 `tasks.md` **最终化之后**生成（含归档移动之后的最终 head），使 `tasks_hash` 绑定的是该 change 的最终任务清单而非收尾中途的快照。

`tasks_hash` 的校验 SHALL 按 change 存续期分别处理：**active** change SHALL 校验 `tasks_hash` 与当前 `tasks.md` 一致；**已归档** change SHALL NOT 以 `tasks_hash` 判定失败——`tasks.md` 是贯穿到归档的活文档，其收尾清单项在 manifest 生成后仍会被勾选，故其字节哈希在归档语境下不构成漂移证据。该降级 SHALL NOT 静默：校验输出 SHALL 说明归档语境跳过 `tasks_hash`。归档 change 的 manifest 存在性、字段完整性与 `report_hash` / `spec_hash` / git span SHALL 仍被校验（这些才承载「审阅了什么」的实质证据）。

CI SHALL 对已归档 change 执行 manifest 校验（`check_openspec_artifacts.py --check-archived`），使 change 归档后不脱离校验范围。

#### Scenario: review report 缺少 manifest

- **GIVEN** `.handoff/<change-id>/<phase>-review.md` 存在
- **AND** 对应 review manifest 不存在
- **WHEN** 运行 gate 或项目 artifact checker
- **THEN** 系统 SHALL 拒绝通过
- **AND** SHALL 报告 review manifest 缺失

#### Scenario: manifest 字段和 hash 校验

- **WHEN** 校验 review manifest
- **THEN** manifest SHALL 声明 `schema`、`change_id`、`phase`、`verdict`、`reviewer_run_id`、`base_sha`、`head_sha`、`tasks_hash`、`spec_hash`、`diff_hash`、`report_hash`
- **AND** `verdict` SHALL 为 `PASS`
- **AND** checker SHALL 验证 `report_hash`、`tasks_hash`、`spec_hash`
- **AND** 当 repo root 是 git repo 时，checker SHALL 验证 `head_sha` 匹配当前 `HEAD`，`base_sha` / `head_sha` 均为 commit，且 `diff_hash` 匹配 `git diff --binary <base_sha> <head_sha>` 的 sha256

#### Scenario: 归档 change 的 manifest 校验不因 tasks_hash 漂移而失败

- **GIVEN** 一个已归档 change，其 manifest 的 `tasks_hash` 与当前 `tasks.md` 不一致（因收尾清单项在 manifest 生成后被勾选）
- **WHEN** 对归档语境运行 manifest 校验
- **THEN** 系统 SHALL NOT 以 `tasks_hash` 不一致判定失败
- **AND** SHALL 在输出中说明归档语境跳过 `tasks_hash` 校验（该降级不得静默）
- **AND** manifest 存在性、字段完整性、`report_hash`、`spec_hash` 与 git span SHALL 仍被校验，任一不符 SHALL 判定失败

#### Scenario: active change 的 tasks_hash 漂移仍判失败

- **GIVEN** 一个 active（未归档）change，其 manifest 的 `tasks_hash` 与当前 `tasks.md` 不一致
- **WHEN** 对该 change 运行 manifest 校验
- **THEN** 系统 SHALL 判定失败并报告 `tasks hash mismatch`
- **AND** 该判据 SHALL NOT 因归档语境的降级而放宽
