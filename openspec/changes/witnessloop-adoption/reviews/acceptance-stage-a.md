# 阶段 A 验收报告：witnessloop 影子接入

> 本文件是 `witnessloop-adoption` 阶段 A 的验收报告（tasks A.1.1 / A.1.2 / A.5.5 的落盘载体）。
> **它不是 `*-review.md`**，不参与本仓 checker 的 review-manifest glob（`scripts/check_openspec_artifacts.py:1150`）；
> 也**不是** witnessloop 形态证据——阶段 A 默认一份 witnessloop manifest 都不落（Decision 7 / A.5.6）。

## 1. 阶段 A 验收判据（A.1.1，测试先行）

> 写判据在先、落产物在后。以下 7 条在**产物落盘之前**写定，落盘后逐条填实测结果（各条证据见后续小节）。

| # | 判据 | 证据位置 | 结果 |
|---|---|---|---|
| ① | `init --dry-run` 待建文件 = **4 个**且**零冲突**（全为新建） | §3.1 | 见 §3.1 |
| ② | 本分支 PR 的 CI 里**出现** `gate / check` job 并**跑出结果** | §7.1 | 见 §7.1 |
| ③ | **触发面验证**：探针 diff（改 `agent/**`）下，定制 policy 让 `building` / `grill-adversarial` 两条 stage 判定**出现** | §5.1 | 见 §5.1 |
| ④ | **负向对照**：同一探针 diff 换**出厂 policy**，这两条判定**消失** | §5.2 | 见 §5.2 |
| ⑤ | `validate` / `benchmark-gate` 行为与本 change 前**逐字节一致**，branch protection 的 `contexts` **未变** | §6 / §7.2 | 见 §6、§7.2 |
| ⑥ | **双守卫实测**（A.4.5，主 checkout 与 building worktree **各一次**） | §8 | 见 §8 |
| ⑦ | **`reviews/` 处于一致状态**——「要么每份报告都有 witnessloop 形态 manifest，要么**一份都没有**」，**默认选后者** | §9 | 见 §9 |

**判据 ③ 为什么要用探针**：本 change 自己的 diff **不触** `require_change_for`（不改 `agent/**` / `scripts/**` / `web/**`）⇒ `code_hits` 为空 ⇒ `building` / `grill-adversarial` 两条判定**本来就不触发**，用本 change 自身**无法**验证触发面（只能用探针）。

**已被证伪而删除的原判据**：原「阶段 A 验收里第一次出现**绿的一侧**」——对抗轮实测证伪（样板 manifest 会激活孤儿规则，红数 2 → 14 → 16；且 grill stage 因 `来源:` 谓词结构性判不了绿）。见 `design.md` Decision 7。

## 2. 基线（A.1.2）

**采集时刻**：2026-10-13，阶段 A 开工前，分支 `witnessloop-adoption/2026-10-13`，HEAD `7c37ef1`，`origin/master` = `da3fd4f`。

命令：`gh api repos/Xingkai98/asterwynd/branches/master/protection`（**只读**，未 apply）

| 字段 | 基线实况 |
|---|---|
| `required_status_checks.contexts` | `["validate", "benchmark-gate"]` |
| `required_status_checks.strict` | `true` |
| `required_pull_request_reviews.required_approving_review_count` | `0` |
| `required_conversation_resolution.enabled` | `true` |
| `enforce_admins.enabled` | `true`（附记） |

**另记**：`.github/workflows/ci.yml` 的 sha256 基线 = `b5417b87e69af0556232a045be6ebabd7728e999c7e77eda3da102f57fea8a33`（供判据 ⑤ 的「逐字节不变」比对）。
