# Asterwynd — 项目重命名候选方案

本文档是 `Asterwynd` 作为 MyAgent 项目新名称的完整方案，可供另一个模型或团队成员独立评估。

---

## 名字

**Asterwynd**

读音：`AS-ter-wynd`（3 音节）

---

## 词源与寓意

| 组件 | 来源 | 含义 |
| --- | --- | --- |
| `Aster` | 希腊语 ἀστήρ（astēr） | 星辰 |
| `Wynd` | 古英语/苏格兰语 wind 的诗歌拼法 | 风 |

**整体寓意**：星辰是固定的参照点（测试、benchmark、trace），风是穿越复杂空间的动力（agent runtime、工具调用、代码变更）。Asterwynd 是一个在代码暗夜中辨认星座、乘风穿越、并记录航迹的导航者。

`wynd` 不是生造拼写——它真实存在于古英语和苏格兰语中（如 Sir Walter Scott 作品）。采用这个拼法有三层考虑：
1. `Asterwind` 的 GitHub 用户已被占，`Asterwynd` 完全干净
2. 古拼法给名字增加了一层"古老导航仪器"的质感
3. 视觉上更独特，和 logo 设计空间更契合

---

## GitHub 复查

| 检查项 | 结果 |
| --- | --- |
| 仓库名搜索 `Asterwynd` | 0 命中 |
| 仓库名搜索 `asterwynd` | 0 命中 |
| 用户/组织名 `Asterwynd` | 未被占用 |
| 用户/组织名 `asterwynd` | 未被占用 |
| `Asterwind`（常规拼法）用户 | 已被空账号占用，不影响 `Asterwynd` 使用 |

**结论**：GitHub 完全干净。可以注册 `asterwynd` 作为 GitHub organization，使用 `asterwynd/asterwynd` 作为仓库名。

---

## Slogan

**短版（推荐用于 README 标题下方、CLI banner、社交媒体简介）**

| 语言 | 文案 |
| --- | --- |
| EN | Navigate by stars. Prove with traces. |
| CN | 以星为引，变更有证。 |

**长版（用于项目介绍、GitHub About、PyPI description）**

| 语言 | 文案 |
| --- | --- |
| EN | A local agent system that navigates complex repositories and proves every change with test-backed traces. |
| CN | 一个在复杂代码仓库中辨认方向、执行变更、并用测试和 trace 证明每次修改的本地 Agent 系统。 |

---

## README 第一段

### 英文（推荐）

> **Asterwynd** is a local coding agent system for turning repository tasks into traceable, test-backed software changes. It reads your codebase, navigates to the right fix, runs tools, and leaves a trail of evidence—diffs, logs, tool traces, benchmark results—so every change is provable, not just plausible.
>
> Think of it as a navigator for complex code: stars for orientation, wind for movement, and a logbook that records the journey.

### 中文

> **Asterwynd** 是一个本地 Coding Agent 系统。它理解仓库结构、定位改动路径、调用工具执行变更，并留下完整的 trace、diff 和 benchmark 证据——让每次代码修改都是可验证的，而不只是"看起来对的"。
>
> 星辰是参照，风是动力，日志记录每一次航行。

---

## 面试叙事（中文，约 3 分钟）

> "Aster 是星辰，wynd 是古英语的风。这个名字说的是：在复杂代码空间里，你需要固定的参照点来定向，也需要动力来穿越。我们的固定参照点是 test 和 benchmark，动力是 agent runtime 和工具系统，而 trace 是我们留下的星图。
>
> 实际上它是一个本地 Coding Agent 系统——不是聊天机器人，不是 single-patch 工具。它读仓库、找路径、调工具、跑测试、产出可验证的 diff。我们在这个项目里建了完整的 agent loop、工具注册、上下文管理、benchmark 评测闭环。一句话：把模糊的软件任务变成可证明的代码变更。"

---

## 与项目愿景的契合度

项目定位（来自 `AGENTS.md`）：

> MyAgent 是一个面向大厂 Agent 相关开发岗位的 Coding Agent 系统项目。主线是 Agent 运行时、工具调用、上下文管理、代码修改、验证、可观测性和 benchmark 闭环。

Asterwynd 的三个意象直接映射三条主线：

| 意象 | 映射 |
| --- | --- |
| 星辰（固定参照） | 测试、benchmark、类型检查——代码正确性的参照系 |
| 风（动力/穿越） | Agent runtime、工具调用、代码修改——执行层 |
| trace（航迹记录） | 日志、diff、工具调用记录、benchmark 结果——可观测性 |

---

## 与其他候选的对比

| | Asterwynd | Orivane | Elarive | OpenCode |
| --- | --- | --- | --- | --- |
| 独特性 | 0 命中 | user 已占 | 0 命中 | 已有同类项目 |
| 画面感 | 最强（星+风） | 中（风向标） | 弱（抽象） | 无 |
| 一眼看懂 | 需要 tagline | 需要 tagline | 需要 tagline | 立即 |
| 品牌延展性 | 强 | 强 | 中 | 弱（太泛） |
| Logo 潜力 | 极高（星图+风线） | 中（风向标图标） | 低 | 低 |
| 中文叙事 | 强（以星为引） | 强（风向标） | 中（抵达） | 弱 |

---

## 风险与注意事项

1. **需要 tagline 建立认知**：不像 `OpenCode` 那样一眼看懂，但这是和搜索唯一性之间的 tradeoff。Kubernetes、Celery、Hermes 等成功项目也都需要 tagline。

2. **`wynd` 拼法可能有困惑**：部分人可能拼成 `asterwind`。应对方式是在 README 和文档中明确读音和词源，同时可以抢注 `asterwind` 相关域名做重定向。

3. **`Asterwind`（常规拼法）GitHub 用户已占**：不影响 `Asterwynd` 使用，但建议同时关注 `asterwind` 是否有其他平台的冲突。

---

## 下一步验证清单

如果接受 Asterwynd 作为首选名，需要按顺序完成：

- [ ] PyPI 包名 `asterwynd` 是否可用
- [ ] npm 包名 `asterwynd` 是否可用（如有前端/CLI 分发需求）
- [ ] `asterwynd.com` / `asterwynd.dev` / `asterwynd.io` 域名是否可注册
- [ ] 搜索引擎（Google/Bing）对 `Asterwynd` 的搜索结果是否干净
- [ ] `asterwynd` 在 Docker Hub、Homebrew 等注册源的可用性（按需）
- [ ] 注册 GitHub organization `asterwynd`
- [ ] 确定 rename 边界：仓库名、README 标题、包名、CLI 命令、环境变量前缀、配置文件、文档引用
- [ ] 先做品牌文本 rename（文档、README），Python package/import path 单独评估是否改
- [ ] 如果改 import path，拆成独立 OpenSpec change，明确兼容策略和迁移测试
