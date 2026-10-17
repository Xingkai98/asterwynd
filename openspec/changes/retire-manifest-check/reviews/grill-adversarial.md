# Grill Adversarial: retire-manifest-check

> 取证基线：分支 `retire-manifest-check/2026-10-17`，HEAD `b68b0f8`，base `origin/master` = `1d6cfee`。
> 本报告只读仓库 + 实跑命令；未继承开发上下文。

## 取证摘要（非 finding）

- **归档点门确实在最终归档 commit 上求值**：`.github/workflows/ci.yml:84-89` 第一步带
  `--base-ref "$BASE_REF" --require-base` 且不带 `--check-archived`；`main()` 在
  `scripts/check_openspec_artifacts.py:1766-1774` 调用 `_check_new_archived_completion_gates`，
  `_new_archive_dirs_since_base`（`:1484-1544`）用 `--diff-filter=AR` + base 树不存在过滤，
  纯 rename 由既有测试 `test_archived_gate_ar_catches_pure_rename_where_a_only_misses` 锁定。
  这一点不构成 finding。
- **历史统计可复现**：`find openspec/changes/archive -name building-review.md` = 79 份；
  `^## 闭环出口` = 1 份（`2026-10-17-round-model-align`）；`^## Verdict` 前缀标题 67 份、无标题 12 份；
  按「最后一个 `## Verdict` 小节的首个 token」= 61 PASS / 5 CHANGES_REQUESTED / 1 无 token；
  该小节含多个 token 的 15 份。与 `design.md:26-30` 逐项一致。
- **OpenSpec strict validate 全绿但抓不到标题不匹配**：
  `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → `30 passed, 0 failed`。
  这使下文 R0-3 不会被现有门禁发现。
- **四类解析样例**：fenced code（围栏内标题/token 忽略）、中文括号标题后缀、
  多小节、`不是 PASS` / `未定` 在四条规则下都有确定结果；不构成歧义。
  `> PASS` / `` `PASS` ``（行首引用符/反引号）不在容忍清单内，会假红，见 L4。
  唯一实质漏洞是 R0-1 的模板占位行假绿。

## 初次开批 · 批次

| id | severity | 锚点 | 问题 |
|---|---|---|---|
| R0-1 | medium | `design.md:71-84`；`specs/dev-workflow-state-machine/spec.md:216`；`/tmp/wl-study/templates/review-loop.md:157-158` | 官方报告模板的出口占位行以 `PASS` 开头，按新四条规则会被判绿：`PASS \| BLOCKED（成因：…） \| BLOCKED（超上限：…）` 原样保留时，checker 判 PASS，直接击穿「BLOCKED 不会被当成通过」。 |
| R0-2 | high | `scripts/check_openspec_artifacts.py:1129-1152`（旧）；`design.md:115-119`、`design.md:160-163`、`design.md:205`；`specs/dev-workflow-state-machine/spec.md:216-219`；`tasks.md:18` | verdict 等价不成立：旧门是「`reviews/` 存在即要求每份 `*-review.md` 有 PASS manifest」，新门只在「非 docs + 有 spec delta + tasks 全勾」触发。**docs change、无 spec delta 的 process change、partial change 上的 `building-review.md` 即便出口是 BLOCKED，新 checker 一律 0 errors；旧 checker 红。** |
| R0-3 | medium | `specs/dev-workflow-gate/spec.md:5` vs `openspec/specs/dev-workflow-gate/spec.md:129`；`/home/happy/my-agent/.claude/commands/opsx/sync.md:59-64,41,70,107` | 该 delta 用「`## MODIFIED Requirements` + 新标题」表达改名；标准 `/opsx:sync` 的 MODIFIED 语义是「按标题在 main spec 找目标」，找不到「review manifest 单套承载：本仓形态退役」⇒ 旧 Requirement「两套并存」可能原样保留，当前规格出现两条互相矛盾的 Requirement。strict validate 实测不报错。 |
| R0-4 | medium | `docs/known-debt.md:25,31-33,158-206,232-241`；`proposal.md:111-112`；`tasks.md:40` | 计划只「新增退役记录」，未点名更新既有段落；这些段落在本 change 后变成假事实（`/review-loop` 仍写 ast manifest、`--check-archived` 仍能检测/修复漂移）。未来维护者会按已不存在的机制操作。 |
| R0-5 | medium | `design.md:210,230-231`；`tasks.md:15-21,41` | 设计承诺「测试中加文档守卫（断言 AGENTS/README/README_EN/docs 的规范面不再要求产 ast manifest）」，tasks 里没有对应测试任务，只有 3.7 的一次性 grep。文档回退不会被任何测试变红，风险缓解落空。 |

### R0-1 · 模板占位行被读成 PASS（medium）

规则原文（`design.md:77-80`、spec delta `:216`）：只认小节首个非空行，剥掉 list/bold 标记后
以 `PASS` / `BLOCKED` / `CHANGES_REQUESTED` 之一**开头**即可，行内后续说明不参与判定。

witnessloop 官方报告骨架（`/tmp/wl-study/templates/review-loop.md:157-158`）给出的出口行是：

```markdown
## 闭环出口（仅在终结时填写；轮内写「未定」）
PASS | BLOCKED（成因：…） | BLOCKED（超上限：20 个轮已收口仍有 medium+，或第 20 轮自身未收口；建议重开设计）
```

具体反例（输入 → 错误行为）：

- 作者从模板复制报告骨架、把「未定」改成终结结论，但**忘记删掉三个可选分支**；报告保留
  `PASS | BLOCKED（成因：…） | BLOCKED（超上限：…）` 这一行。
- 首个非空行以 `PASS` 开头 ⇒ 新 checker 判 PASS；但该行同时声明了两种 BLOCKED 出口，
  事实上没有做出唯一裁决。
- 同类：`PASSED（仍在验证）` / `PASSAGE` 也以 `PASS` 开头（规则没有钉 token 边界）。
  这正落在 `design.md:204` 自列的「解析过松导致 BLOCKED / 未定被读成 PASS」风险上，
  而该行的缓解措施只防住了「不以 token 开头」的 `不是 PASS`。

可落地修法：规则 3 追加两条可执行约束并补测试——

1. 首个 token 后必须紧跟行尾 / 空白 / `（`/`(`/`：`/`:` 等终止符（拒绝 `PASSED` 这类字母续写）；
2. 首个 token 之后**不得出现 `|` 分隔的其它终结 token**（拒绝模板占位行），
   同时保留 `PASS（此前 CHANGES_REQUESTED 已收口）` 合法（括号内说明，非 `|` 分隔）。

### R0-2 · verdict 等价不成立：docs / 无 spec delta / partial 上的 BLOCKED 报告不被检查（high）

旧事实（`scripts/check_openspec_artifacts.py:1129-1152`）：

- `requires_building_review` 只控制「报告是否存在」；
- 只要 `reviews/` 存在，`for report_path in sorted(review_dir.glob("*-review.md"))` 就对**每一份**
  报告调用 `verify_review_manifest`（`:1145-1152`）；
- 缺 manifest → `review manifest missing`，manifest `verdict != "PASS"` → 报错
  （`agent/workflow/review_manifest.py:133-134,158-159`）；
- 现有测试 `tests/test_openspec_artifact_checker.py:211-220` 用 **docs change** 断言该错误，
  证明旧门对 docs change 同样生效。

新事实（`design.md:115-119`，spec delta `:216-219`）：触发条件固定为
「非 docs + `_changed_capabilities` + `_tasks_all_complete`」；归档点同条件（非 docs + spec delta）。
`tasks.md:18` 还会把上述 docs 旧用例改写成「无 manifest 不再报错」。

具体反例：

- **A（docs change，完成态）**：`primary: docs`，tasks 全勾，`reviews/building-review.md` 含
  `## 闭环出口` → `BLOCKED（成因：README_EN 口径不一致，未收口）`，无 ast manifest。
  旧 checker：`review manifest missing` ⇒ 红。新 checker：docs 使存在性门与 verdict 门都不触发
  ⇒ 0 errors；归档时归档点门也因 `change_type.primary != "docs"` 跳过 verdict ⇒ 仍绿。
- **B（无 spec delta 的 process change）**：`primary: process`、无 `specs/`、tasks 全勾、
  真实改动 `scripts/**`，出口 `BLOCKED`。旧：`reviews/` 存在 ⇒ 红；新：`_changed_capabilities`
  为空 ⇒ 两处都不触发 ⇒ 绿。
- **C（partial）**：非 docs + spec delta + 一条 `- [ ]` 后续批任务，出口 `BLOCKED`。
  旧：红；新：`_tasks_all_complete` 为假 ⇒ 绿。
  `design.md:205` 把 C 写成「有意为之」，但 A/B 是**完成态**，不在该风险的说明范围内；
  `design.md:160-163` 的 loss 登记只写了「非 building 的 `*-review.md`」，漏了
  「docs / 无 spec delta 的 **building** review」。这正是 #316「不放宽任何判据」的缺口。

可落地修法：把 verdict 检查与存在性门解耦——

- **只要 `reviews/building-review.md` 存在，且出口小节首个 token 是 `BLOCKED` /
  `CHANGES_REQUESTED`（terminal 非 PASS），一律报错**，不区分 change 类型、spec delta、tasks 状态；
- `未定` / 出口小节缺失仍只在完成面触发（保住「避免误伤在途 partial review」的初衷）；
- 补三条回归测试：docs、无 spec delta、partial 各一（BLOCKED 必须红；同形态 `未定` 在 partial 下仍绿）。

### R0-3 · 改名用了 MODIFIED + 新标题，标准 sync 找不到旧 Requirement（medium）

- delta：`openspec/changes/retire-manifest-check/specs/dev-workflow-gate/spec.md:5`
  `### Requirement: review manifest 单套承载：本仓形态退役`，位于 `## MODIFIED Requirements` 下。
- 当前规格对应 Requirement：`openspec/specs/dev-workflow-gate/spec.md:129`
  `### Requirement: review manifest 两套并存，schema 统一延后`（标题不同）。
- OpenSpec 的 sync 语义（`/home/happy/my-agent/.claude/commands/opsx/sync.md:59-64`）：
  「MODIFIED Requirements: **Find the requirement in main spec**」；改名的规范通道是同文件
  `:41,:70,:107` 的 `## RENAMED Requirements`（FROM:/TO:）。

具体反例：

- 执行 `/opsx:sync retire-manifest-check`：agent 按 delta 在 main spec 找
  「review manifest 单套承载：本仓形态退役」→ 找不到；按文档没有定义「MODIFIED 未命中」的处置，
  实际只能新增或跳过。**旧 Requirement `:129` 原样保留** ⇒ 当前规格同时要求
  「两套并存」和「单套承载」。
- 实测 strict validate 为 `30 passed, 0 failed`，该矛盾不会在 CI 阶段暴露。
- `tasks.md:50`（4.6）只修 `openspec/specs/dev-workflow-gate/spec.md:45` 的交叉引用，
  不能保证旧 Requirement 被删除。

可落地修法：delta 改用 `## RENAMED Requirements`（FROM 旧标题 / TO 新标题）+
对新标题的 `## MODIFIED Requirements`（或 `REMOVED` + `ADDED`）；tasks 4.4 增加验收
`grep -c '两套并存' openspec/specs/dev-workflow-gate/spec.md` 必须为 0。

### R0-4 · known-debt 既有段落变假且不在更新清单（medium）

- 计划面：`proposal.md:111-112` 只写「`docs/known-debt.md` **新增**退役记录与剩余第二刀清单」；
  `tasks.md:40`（3.6）只列新登记项（退役、diff_hash、历史 drift 检测消失、非 building PASS 门、第二刀清单）。
- 既有段落将变成假事实：
  - `docs/known-debt.md:25`：`/review-loop` 写 `reviews/*-review-manifest.json` —— 任务 2.7 之后它改产
    `reviews/<stage>.manifest.json`；
  - `docs/known-debt.md:31-33`：「`--check-archived` 模式可捕获并修复：重建 manifest 绑定当前 artifact」
    —— 本 change 后 `--check-archived` 不再读 manifest；
  - `docs/known-debt.md:158-206`（#232 A/B 全节）与 `:232-241`（覆盖面隐含上界）整段描述
    `--check-archived` 的 manifest 校验 / `tasks_hash` 降级 / `*-review.md` 覆盖面，机制删除后语义过期。

具体反例：未来维护者遇到历史 manifest 漂移，按 `docs/known-debt.md:33` 运行
`--check-archived --skip-protected-paths --skip-backlog`，得到 exit 0 便认为漂移已被检测/修复；
实际新语义只做事件可投影校验，检测能力已消失。

可落地修法：task 3.6 明确「退役/标注上述既有段落（不是只新增一节）」，
并在 proposal Impact 的债务登记行点名这四处；新增记录同时链接旧段落。

### R0-5 · 设计承诺的文档守卫没有落成任务（medium）

- `design.md:210`（风险缓解）与 `design.md:230-231`（Testing Strategy）明确承诺
  「测试中加文档守卫：断言 `AGENTS.md` / `README.md` / `README_EN.md` / `docs/**` 的规范面
  不再要求产出 ast manifest（历史归档与 known-debt 历史记录除外）」。
- `tasks.md:15-21`（先红测试）没有该任务；`tasks.md:41`（3.7）只是一次性 grep 复核，
  不是能在未来变红的回归测试。

具体反例：实现完成后有人在 `AGENTS.md:108` 或 `README.md:153` 重新写回
「审阅需 review manifest 绑定 hash」；`uv run pytest -q` 不会变红，只有人工再跑 grep 才能发现
⇒ 下一次开发又产 ast manifest，双套并存回潮（`design.md:210` 列出的正是这个风险）。

可落地修法：新增一条先红测试任务（例如 1.6）：扫描 `AGENTS.md` / `README.md` / `README_EN.md` /
`docs/development-guide.md` / `docs/requirements-process.md`，断言不再出现
`building-review-manifest.json`、「review manifest 绑定 … tasks/spec/diff/report hash」等旧要求
（排除 `openspec/changes/archive/**` 与 `docs/known-debt.md` 的历史记录）。

## 下一批（deferred）

无（初次开批）。

## low/nit 登记

| id | severity | 锚点 | 处置/理由 |
|---|---|---|---|
| L1 | low | `design.md:70`、`tasks.md:26` | 函数命名不一致：design 写 `_check_building_review` / `_review_exit_verdict`，tasks 写 `_review_exit_verdict` / `_building_review_errors`。实现前钉死一对名字即可。 |
| L2 | low | `proposal.md:27-31` vs `proposal.md:149-169`、`design.md:150-163` | 「verdict 是唯一不被 witnessloop 覆盖的判据」表述过宽：本 change 自己还登记了 `diff_hash` 强校验与历史 drift 检测两项损失。建议限定为「active 侧 `_check_review_manifests` 的判据里唯一不被 witnessloop 覆盖的是 verdict」。 |
| L3 | low | `proposal.md:54` vs `proposal.md:48-50` | 需求 6「其它检查行为不变」未提及需求 4 已明确移除的 `--check-archived` 历史漂移检测；建议加一句指回需求 4，避免两处口径冲突。 |
| L4 | low | `specs/dev-workflow-state-machine/spec.md:216`、`design.md:77-80` | 规则未定义行首引用符/反引号：`> PASS` 与 `` `PASS` `` 会假红。不是绕过；建议在规格里写明「仅支持 list/bold 前缀」或在实现里一并剥离。 |
| L5 | low | `scripts/check_openspec_artifacts.py:1732-1748` | `--check-archived` 改写时应钉住既有「`change_type is None` ⇒ `continue`」语义。实测 4 个老世代归档无 `workflow-events.jsonl`（`2026-06-21-*`），当前无可观察差异；但改写若不保留会让 `_check_archived_projectable` 覆盖面静默扩大。 |
| L6 | low | `tests/test_openspec_artifact_checker.py:2116`；`scripts/check_openspec_artifacts.py:1713-1717` | CI 测试的错误文案「CI 缺少归档 manifest 校验步骤」与 `--check-archived` help（「verify review manifests … catching drift」）在退役后不再准确；tasks 2.5 覆盖 help，未点名测试文案。 |

## 闭环出口

未定
