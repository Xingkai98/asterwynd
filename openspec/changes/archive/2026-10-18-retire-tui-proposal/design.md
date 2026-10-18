# Design: 原地废弃未实现的 `add-minimal-tui-runtime-view` proposal

## Context

- proposal 立项于 2026-06-22，18 条任务全未勾、无 `reviews/`、RIR 未完成；最后提交
  `97b037006faa4581a48eb7fcfc10894f8b7f6348`。
- 用户已决定废弃；将来 TUI 单独重新立项。
- witnessloop v1.7.0 的 change 契约对「diff 触及的 active change 目录」要求必需件与
  `stage=grill` manifest；实测：
  - 删除目录 → `check` 5 项 finding（目录不存在 + 缺 manifest/grill/grill-adversarial/building）；
  - 目录内加 `WITHDRAWN` → 3 项 finding（缺 reviews / manifest / grill manifest）。
- 因此本 change 不改 TUI 目录的一个字节，只改记录层。

## Goals / Non-Goals

**Goals**

- backlog 不再引用该 proposal；决定、原因、失败证据与取回方式可追溯。
- required 门禁保持绿；不伪造任何 review 证据。

**Non-Goals**

- 不实现 TUI；不删除目录；不加目录内标记；不改 witnessloop。

## Decisions

### Decision 1：目录字节不变，废弃声明放 ADR + backlog + 规格

**选择**：保留 `openspec/changes/add-minimal-tui-runtime-view/` 原样。新增
`docs/adr/ADR-0006-...md`；backlog 移除三处引用；`dev-workflow-gate` 规格把「已知红」
改为「已原地废弃」；`docs/development-guide.md` 同步。

**理由**：删除与目录内标记都会让 witnessloop 把它当 change target 并要求伪造 reviews /
manifest。ADR + backlog + 规格是非 target 位置，既表达决定又不触门禁。

**被拒备选**：删除目录（5 项 finding）、归档为已完成（伪造完成证据）、`abandoned/`
目录（新约定）、目录内标记（3 项 finding）、保持 active 不标记（语义误导）。

### Decision 2：不伪造 review 证据

**选择**：不补 `reviews/`、不勾 TUI 的 18 条任务、不生成 manifest。

**理由**：该 proposal 从未实现；补证据会污染「审阅=已工作」的口径，且用户明确要求
「不要为了能加标记而伪造 reviews / manifest」。

### Decision 3：未来触及该目录必须先处置

**选择**：ADR 与规格写明：未来任何触及 TUI 目录的 diff 必须先重新立项，或等 witnessloop
支持删除/退休；否则 `gate / check` 会红。

**理由**：目录仍在 active，witnessloop 的 change target 判定无法通过目录外记录豁免。

## Pre-Implementation Review

本 change 是 docs-only 退役记录；独立 grill 产出 `reviews/grill-design.md`，0 个 Open
Question。删除/标记两种处置的实测证据来自 issue #319 初版分支与临时 worktree：

- 删除：`check：未通过 ✗（5 项）`（change 目录不存在 + 4 项 manifest/stage）；
- 标记：`check：未通过 ✗（3 项）`（缺 reviews / manifest / grill manifest）。

## Risks / Trade-offs

- **TUI 目录仍可被未来 diff 触及**：这是原地废弃的代价；ADR/规格已写明处置路径。
- **backlog 与规格可能出现口径漂移**：本 change 同时改两处并加事件；归档点 checker 校验
  backlog 一致性。
- **witnessloop 升级后可能支持删除**：ADR Revisit Condition 已列。

## Testing Strategy

- 无代码/测试变更。
- 验证：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`、
  `--base-ref origin/master --require-base`、`--check-archived`、
  `npx @fission-ai/openspec validate --all --strict`、
  `/home/happy/wl170/bin/witnessloop check` 全绿。
- 临时分支实测 marker：见 ADR-0006 与 PR 描述；不在工作树留下标记。
