# ADR-0007: artifact checker 的默认 base 解析（origin/master 优先）

- **Status**: accepted
- **Date**: 2026-10-18
- **Deciders**: 主 agent（issue #319 的修复方案）、独立 grill 审阅者
- **关联**: issue [#319](https://github.com/Xingkai98/asterwynd/issues/319)、
  issue [#235](https://github.com/Xingkai98/asterwynd/issues/235)（归档点完成度门）、
  issue [#316](https://github.com/Xingkai98/asterwynd/issues/316)（`## 闭环出口` 判据的来源）、
  ADR-0006（TUI proposal 退役，由后续 PR B 提供）

## Context

`scripts/check_openspec_artifacts.py` 的归档点完成度门（issue #235）只对「本 PR 新归档」
求值，靠两条过滤判定：

1. `git diff --name-only --diff-filter=AR <base> --`；
2. 该归档子目录在 `<base>:openspec/changes/archive` 树中不存在。

`--base-ref` 的 argparse 缺省值是字符串 `master`。本仓的 PR 都从 `origin/master` 分支，
但本地 `master` 分支可以长期落后（本工作区实测落后 103 个提交）。此时裸跑：

- 实际 PR base 是 `origin/master = b0469cb`；
- diff 使用的是陈旧的 `master = 3c7196b`；
- 8 个历史归档目录进入 AR diff（在陈旧 master 的 archive 树中不存在），其中 5 个缺
  `## 闭环出口` 的报告被当成「本 PR 新归档」追溯求值 → EXIT=1。

CI 显式传 `github.event.pull_request.base.sha`，AGENTS.md 的标准命令显式传
`--base-ref origin/master --require-base`，因此都不受影响；缺陷只在「不传参数」的本地入口。
但本地裸跑是门禁的常用入口，误红会让「历史归档不追溯」的承诺在代码层不成立。

## Decision

1. `--base-ref` 的 argparse 默认值改为 `None`。
2. 新增 `_resolve_base_ref(repo_root, explicit)`：
   - `explicit is not None and explicit.strip()` 时原样返回（空/纯空白视为未提供，
     避免 `--base-ref ""` 静默跳过两个 diff 检查）；
   - 否则依次尝试 `origin/master`、`master`，并用 `git merge-base HEAD <candidate>` 的
     结果作为**隐式 base**（三点语义）；merge-base 不可用（如 shallow clone）时退回
     candidate 名；
   - 两者都不可解析时返回 `"master"`，交给下游既有的 `--require-base` fail-closed /
     WARNING 逻辑。
   - 隐式 base 用 merge-base 而不是直接两点 diff `<candidate>`：分支落后于
     `origin/master` 时，两点 diff 会把上游已合入的受保护路径改动反向列为本分支改动，
     造成「本分支没碰受保护路径却被要求解释」的误红。
3. `main()` 解析一次，把结果**同时**传给归档点门（`_check_new_archived_completion_gates`）
   与受保护路径 diff（`_changed_paths_since_base`）。
4. 隐式解析命中时向 stderr 打印 `INFO: using implicit base ref '<ref>' -> <base>`，便于定位
   「`origin/master` 也陈旧」导致的误红。
5. 归档点门的两条过滤、出口判据、`--check-archived` / `--change` / `--skip-*` 语义
   一律不变。

## Alternatives Considered

| 备选 | 描述 | 拒绝原因 |
|------|------|---------|
| 保持 `master` 默认 | 继续要求调用方显式传 `--base-ref origin/master` | issue #319 明确要求裸跑可用；文档已推荐显式命令但仍会误红，说明默认值选错 |
| 按日期阈值排除「旧」归档 | 例如只把最近 N 天内的归档当作新归档 | 魔数阈值会误杀真正的新归档；历史性不能由日期推断 |
| 无参数时跳过归档点门 | 裸跑只做 protected-path / backlog 检查 | 会让裸跑不再检查新建归档，违反 issue #319 的「新建归档仍必须红」，且是放宽判据 |
| 直接用 `origin/master` 两点 diff | 把 `origin/master` 作为 base 名原样传入 | 分支落后时反向 diff 会把上游受保护路径改动列为本分支改动，引入新的误红；merge-base 才代表本 PR 的变更集 |
| 用 `git merge-base HEAD master` | 用本地 master 与 HEAD 的分叉点作 base | 本地 `master` 陈旧时 merge-base 仍在旧点，历史归档照样被误判 |
| 无参数时直接报错要求显式传参 | 把裸跑变成错误 | 破坏本地体验；CI 与标准命令已有显式路径，不需要把裸跑列为非法 |
| 计算 `origin/master` 与 `master` 的较新者 | 两个 ref 都尝试并选新 | 实现复杂度高于收益；`origin/master` 是本仓 PR 的语义 base，本地 `master` 不代表 PR |

## Consequences

- 正面：干净检出裸跑 EXIT=0；新建归档缺 `## 闭环出口` 仍红；CI 与显式参数零影响；
  历史归档不再因本地默认分支陈旧被追溯。
- 负面/边界：`origin/master` 自身陈旧（未 fetch）时仍可能把更新的上游提交误判——这是
  fail-loud，不是 fail-open；文档补充「裸跑前 fetch」。merge-base 已消除「分支落后但未
  merge」的反向 diff 噪音；显式 `--base-ref` 仍是逃生口。
- `origin` 指向 fork/镜像时 `origin/master` 可能不是 PR base；显式参数可覆盖。
- 需要的相关变更：`dev-workflow-state-machine` 的归档点 Requirement 增加 base 解析口径；
  `AGENTS.md` / `development-guide` / `requirements-process` 的说明同步；四条先红回归 +
  三条守卫测试（防退化、显式优先、三点语义）。

## Revisit Conditions

- [ ] CI 或 witnessloop 开始提供稳定的「PR base」环境变量（如 `WITNESSLOOP_BASE_REF`）时：
      重新评估默认解析顺序，优先使用显式环境变量。
- [ ] 仓库主分支改名（`master` → `main`）或改用其它集成分支时：更新候选 ref 列表。
- [ ] 需要支持从 release 分支发起的 PR 时：默认解析应改为读取分支 upstream 或显式要求
      `--base-ref`，而不是固定 `origin/master`。
