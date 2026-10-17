# Proposal: 删除 legacy asterwynd 形态 review manifest 生成模块与写通道（第二刀）

关联 issue：[#316](https://github.com/Xingkai98/asterwynd/issues/316)（探索结论、第一刀/第二刀范围）；
跟踪总账：[#305](https://github.com/Xingkai98/asterwynd/issues/305)（保持 OPEN）。
前置：第一刀 `retire-manifest-check` 已合入（PR #317 / merge `5225207`）。

## Change Type

- primary: process
- secondary: []

## Why

第一刀下掉了 `scripts/check_openspec_artifacts.py` 对 asterwynd 形态 manifest
（`reviews/<phase>-review-manifest.json`，schema `review-manifest/v1`）的**消费面**，但生产面
仍然存在：

- `agent/workflow/review_manifest.py`（264 行）仍提供 build / write / verify；
- `scripts/workflow_state.py review-manifest` 仍是可执行子命令；
- `scripts/flow-policy.json` 与 `scripts/workflow_guard.py` 仍把 `-review-manifest.json`
  当受保护路径并豁免该 CLI；
- `agent/workflow/resume_audit.py` 仍把 `-review-manifest.json` 当 workflow 管理文件忽略；
- 测试、`AGENTS.md`、`openspec/specs/**` 与 `docs/**` 仍把它描述为「legacy 通道，由第二刀处置」。

这会让仓库同时保持「流程只产 witnessloop 形态」与「仍有一个合法命令产出第二套 manifest」的
双面状态：读者无法从代码与规则判断哪一套是活通道，guard 的豁免清单与受保护规则也保留了
一个没有生产者的写入口。`openspec/specs/dev-workflow-gate/spec.md` 明确写这两项
**由第二刀处置**。本 change 就是第二刀：**纯删除 + 收尾，不加功能**；唯一的行为修正来自被移动代码自带的已知前缀碰撞缺陷（见 design Decision 2）。

## 需求

1. **删除模块**：`agent/workflow/review_manifest.py` SHALL 被删除；`agent/workflow/**` 内
   SHALL NOT 再存在 asterwynd 形态 manifest 的生成 / 校验实现。
2. **删除写通道**：`scripts/workflow_state.py` SHALL 删除 `review-manifest` 子命令、其
   parser 接线、`cmd_review_manifest` 与只被它使用的 `_resolve_review_base_sha`。调用
   `workflow_state.py review-manifest ...` SHALL 以 argparse 未知子命令失败（非零退出），
   SHALL NOT 产生任何文件或事件副作用。
3. **保留 `artifact-event` 的归档解析**：该命令的归档回退原先委托
   `review_manifest.change_dir_for(archived=True)`。删除模块后 SHALL 在
   `scripts/workflow_state.py` 内提供等价解析；解析 SHALL 只接受裸 `<id>` 或
   `<date>-<id>` 目录（精确匹配），SHALL NOT 把写入落到更长前缀的兄弟 change。该行为
   SHALL 由既有回归测试继续锁定。
4. **清理引用**：
   - `scripts/flow-policy.json` SHALL 删除 `-review-manifest.json` 受保护路径规则；
     `scripts/workflow_guard.py` 的内嵌默认表 SHALL 同步删除该规则；
   - `scripts/workflow_guard.py` 的 privileged CLI 豁免正则 SHALL 移除
     `review-manifest`（该子命令已不存在）；
   - `agent/workflow/resume_audit.py` SHALL 移除 `-review-manifest.json` 忽略规则——
     没有 workflow 写生产者之后，历史 manifest 的改动应按普通文件进入 resume audit；
   - 测试、`AGENTS.md`、`README.md` / `README_EN.md`、`openspec/specs/**`、`docs/**`、
     `agent/workflow/__init__.py` SHALL 逐处改为「已删除 / 已退役」的准确表述，或删除已失效的用例与说明。
     README 双语目录树须在同一变更内同步（AGENTS.md 维护规则）。
5. **历史文件冻结**：80 份历史 `*-review-manifest.json` SHALL 保持原样，SHALL NOT 被
   迁移、重算或删除；它们位于 `openspec/changes/archive/**`，继续由归档前缀规则保护。
6. **规格同步**：`dev-workflow-gate`、`dev-workflow-state-machine`、`change-documentation`
   三份 current spec SHALL 反映「模块与 CLI 已删除、受保护规则已移除、历史文件冻结」。
7. **不回退其它门禁**：RIR、Impact Analysis、benchmark smoke、审查闭环、`## 闭环出口`
   PASS 判据、归档点完成度门、backlog 一致性、grill / grill-adversarial 证据、
   witnessloop 接入形态 SHALL 一律不动。

## 非目标

- **不动** witnessloop 仓、`v1` / `v1.7.0` tag、`.witnessloop/**` 与
  `evidence.review_manifest_glob`。
- **不动** 80 份历史 manifest，不回填、不重算、不删除。
- **不统一 schema**、不引入公共超集格式。
- **不改** `artifact-event` 的语义、投影刷新规则或其它受保护写通道。
- **不改** `agent/workflow/event_log.py` / `state_machine.py` / `models.py` /
  `routing.py` / `resume_audit.py` 的其它行为（除移除 manifest 忽略项）。
- **不新增** 任何 manifest 相关能力。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `dev-workflow-gate`：把「本仓形态退役」Requirement 中「模块与写通道保留到第二刀」改为
  「已删除」；同步阶段 A Scenario 中指向 manifest 生成器的表述。
- `dev-workflow-state-machine`：从受保护写通道 Requirement 与相关 Scenario 中移除
  `review-manifest`；同步 Workflow 总开关、guard 写通道豁免与受保护路径规则描述。
- `change-documentation`：从受保护 artifact 写通道清单中移除 `review-manifest`。

## Impact Analysis

> 行号基于 `origin/master` = `5225207`（2026-10-17），即本 change 的分支基点。

- **删除文件**：`agent/workflow/review_manifest.py:1-264`。
- **`scripts/workflow_state.py`**：
  - `:10` docstring 的 usage 行；`:41` 的 import；
  - `:139-155` `_resolve_review_base_sha`（仅 `:497` 使用）；
  - `:320-326` `_is_archived_change_dir` docstring、`:327-343` 删除 `_archive_dir_matches_change_id`、
    `_require_change_target` 的 `:359-384` 归档回退接线改为内联 helper；
    删除 `_resolve_review_base_sha` 后 `:23` 的 `subprocess` import 一并清理；
  - `:484-519` `cmd_review_manifest`；
  - `:699-706` parser 接线。
- **策略与 guard**：`scripts/flow-policy.json:55-59`；`scripts/workflow_guard.py:16,81,271`
  （docstring、内嵌默认表、豁免正则）。`manifest_verified` governance 值本身保留为策略词汇，
  但当前无规则使用（在本 change 的 known-debt 退役记录中写明）。
- **resume audit**：`agent/workflow/resume_audit.py:340` 的忽略项；`:322-328` 的
  `_status_path` 首行解析缺陷（新回归暴露，随本 change 修正并加单测）。
- **包说明**：`agent/workflow/__init__.py:9`。
- **测试**：
  - 删除 `tests/agent/workflow/test_review_manifest.py`；
  - `tests/test_openspec_artifact_checker.py:1778-1830` 删除模块级 archived 用例；
    `:2109` 的合成文件名改为非 manifest 文件（该用例只验证 base 树过滤）；
  - `tests/test_workflow_state_cli.py:19,219-251`：删除正向 manifest 用例，把
    `review-manifest` 加入 `REMOVED_SUBCOMMANDS` 负向回归（另用合法 target 证明删除前会写文件）；
  - `tests/test_workflow_archive_write_channel.py`、`tests/test_workflow_protected_write_channel.py`：
    删除 manifest 正向用例与 import，保留 / 改写 `artifact-event` 覆盖；兄弟前缀用例断言
    「不存在」（区分旧 `re.match` 路径），新增同 id 多日期目录 fail-closed 用例；
  - `tests/test_flow_policy.py:140-147` 文案与 `tests/test_workflow_guard.py:91` 的 manifest
    路径改为其它受保护路径；
  - `tests/agent/workflow/test_resume_audit.py`：新增「历史 manifest 改动被审计发现」的回归；
  - `tests/test_retire_manifest_check.py`：文档守卫扩展为「不再有模块/CLI 调用形态」，
    带阳性/阴性对照（退役说明允许，调用指示拒绝）。
- **文档（含受保护路径）**：
  - `AGENTS.md:108,115,203`；
  - `README.md:264` 与 `README_EN.md:264`（双语目录树，必须同改）；
  - `docs/development-guide.md:294-300,324`、`docs/requirements-process.md:45,293`、
    `docs/interview-script/questions/Q14-dev-process.md:38,49`；
  - `docs/known-debt.md:25,168-177,186-192,229,516-537`（受保护，需 event）；
  - `docs/adr/ADR-0004-retire-duplicate-review-manifest-check.md` 的 Revisit Conditions；
  - 新增 `docs/adr/ADR-0005-retire-legacy-review-manifest-module.md`。
- **规格（受保护，需 event）**：`openspec/specs/dev-workflow-gate/spec.md`、
  `openspec/specs/dev-workflow-state-machine/spec.md`、
  `openspec/specs/change-documentation/spec.md`。
- **本地入口（不进版本控制）**：`/home/happy/my-agent/.claude/commands/review-loop.md`
  已不再调用 `workflow_state.py review-manifest`；本次只复核表述，不混进 PR。
- **明确不变**：80 份历史 manifest、`.witnessloop/**`、`scripts/check_openspec_artifacts.py`
  的 `## 闭环出口` 检查、CI job 组成、platform-gate 配置。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 上游决策锁定：issue #316 已给出两套 manifest 的逐字段对照与退役裁决，第一刀
  `openspec/changes/archive/2026-10-17-retire-manifest-check/` 与
  `docs/adr/ADR-0004-retire-duplicate-review-manifest-check.md` 明确把模块、CLI、历史文件与
  受保护路径规则留给第二刀；本 change 无待定的产品/方案取舍，只执行既有裁决。删除面已用
  `grep -rn` 全仓清点，除被列举的消费者外无其它引用；witnessloop 侧只消费
  `reviews/*.manifest.json`，与本模块无关（`.witnessloop/policy.json` 的
  `review_manifest_glob` 明确匹配不到 `*-review-manifest.json`）。

## 用户故事

- 作为本仓维护者，我看到的代码里只有一套 review manifest 实现，不存在「规则说退役、命令仍可用」
  的双面状态。
- 作为开发者，我误调用 `workflow_state.py review-manifest` 时会得到明确的未知子命令错误，
  而不是悄悄写出第二套 manifest。
- 作为审阅者，`artifact-event` 的归档写入能力不因删除模块而回退，历史归档仍可追加解释事件。
- 作为仓库使用者，历史 80 份 manifest 保持冻结，任何迁移/重算都不会发生。
