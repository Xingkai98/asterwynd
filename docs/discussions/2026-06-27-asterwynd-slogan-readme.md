# Asterwynd — Slogan & README 开场文案

## 最终推荐版

## GitHub README 顶部设计

OpenCode 这类项目的 README 首屏通常不是从 `# ProjectName` 开始，而是用一段居中的 HTML：

1. 居中 logo / banner。
2. 居中项目名或 slogan。
3. 居中语言切换链接。
4. 居中 badges。
5. 再进入正文介绍。

GitHub README 支持有限 HTML，因此可以用 `<p align="center">`、`<h1 align="center">` 和 `<div align="center">` 实现。建议 Asterwynd 顶部采用这种结构。

### 推荐结构

```html
<p align="center">
  <img src="./docs/assets/asterwynd-mark.png" alt="Asterwynd" width="180" />
</p>

<h1 align="center">Asterwynd</h1>

<p align="center">
  <strong>Navigate by stars. Prove with traces.</strong>
</p>

<p align="center">
  <a href="./README.md">English</a>
  ·
  <a href="./README_CN.md">简体中文</a>
</p>

<p align="center">
  <a href="#"><img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-blue"></a>
  <a href="#"><img alt="Tests" src="https://img.shields.io/badge/tests-pytest-green"></a>
  <a href="#"><img alt="License" src="https://img.shields.io/badge/license-MIT-black"></a>
</p>
```

### 语言文件建议

如果正式改名时采用双语 README，建议：

- `README.md`：英文主 README，方便 GitHub 国际读者第一眼理解。
- `README_CN.md`：中文 README。
- `AGENTS.md` 继续规定：中文项目文档为主；README 是对外入口，可以维护英文主版和中文同步版。

如果仍希望中文作为源文档，则可以反过来：

- `README.md`：中文主 README。
- `README_EN.md`：英文翻译。
- 顶部语言链接写成 `简体中文 · English`。

考虑 GitHub 搜索和开源项目对外展示，Asterwynd 更适合用英文 `README.md` 作为默认入口，中文放 `README_CN.md`。

### Logo / Banner 方向

Asterwynd 的主视觉应分成两类：

- **TUI wordmark**：纯文本大字，启动终端工具时直接打印，类似常见 coding-agent TUI 的 splash masthead。
- **README masthead**：可以使用 SVG/PNG wordmark 做更精致的 GitHub 首屏展示。

图形 mark 只作为辅助 icon 使用，不作为主 logo。

主 logo 方向：

- 终端 / monospace / hacker 气质。
- 项目名 `Asterwynd` 作为主体，而不是抽象图标。
- 辅以星图、风线、trace/cursor 等轻量视觉元素。
- 能降级为纯文本 ASCII，在 TUI 中直接打印。

辅助 mark 方向：

- 星图：3-5 个点构成星座。
- 风线：一条弧线穿过星座。
- 航迹：线条末端留一个小点或箭头。
- 色彩：深色背景版和透明背景版各一份。

建议文件：

```text
docs/assets/asterwynd-tui-wordmarks.txt
docs/assets/asterwynd-wordmark.txt
docs/assets/asterwynd-wordmark-compact.txt
docs/assets/asterwynd-wordmark.svg
docs/assets/asterwynd-mark.png
docs/assets/asterwynd-mark.svg
docs/assets/asterwynd-banner.png
```

TUI 启动页优先使用 `asterwynd-tui-wordmarks.txt` 里的 Option B；窄终端用 compact 文本。日志、benchmark 和非交互单轮 CLI 默认不显示 banner，避免污染机器可读输出。

README 首屏使用 `asterwynd-wordmark.svg`。Web UI 通过 `/assets/asterwynd-wordmark.svg` 复用同一资产；TUI 通过 `agent/assets/asterwynd-wordmark.txt` 和 `agent/assets/asterwynd-wordmark-compact.txt` 使用纯文本源渲染。

### 当前草稿资产

已产出 wordmark 和两版 mark：

```text
docs/assets/asterwynd-wordmark.svg
docs/assets/asterwynd-wordmark.png
docs/assets/asterwynd-wordmark.txt
docs/assets/asterwynd-wordmark-compact.txt
docs/assets/asterwynd-tui-wordmarks.txt
docs/assets/asterwynd-mark.svg
docs/assets/asterwynd-mark.png
docs/assets/asterwynd-mark-simple.svg
docs/assets/asterwynd-mark-simple.png
docs/assets/asterwynd-mark-preview.png
```

建议 TUI 使用 `docs/assets/asterwynd-tui-wordmarks.txt` 中的纯文本 wordmark。README 首屏如需图片，再使用 `docs/assets/asterwynd-wordmark.svg` 或 `docs/assets/asterwynd-wordmark.png`。

`docs/assets/asterwynd-mark-simple.png` 可作为 GitHub social preview、favicon、文档小图标或后续网站导航 icon。

TUI 示例：

```text
   ___    _____ ______ ______ ___  _   ___  __ __
  / _ |  / ___//_  __// ____// _ \| | / / |/ // /
 / __ | _\ \   / /  / __/  / , _/| |/ /    // /__
/_/ |_|/___/  /_/  /____/ /_/|_| |___/_/|_//____/

Navigate by stars. Prove with traces.
```

### 英文

**Slogan**

> Navigate by stars. Prove with traces.

**README 开场**

> **Asterwynd** is a local coding agent system for turning repository tasks into traceable, test-backed software changes. It reads your codebase, finds the path from issue to fix, runs tools and validation, and leaves a trail of evidence—diffs, logs, tool traces, and benchmark results—so every change is provable, not just plausible.
>
> Stars guide direction. Wind carries motion. Traces prove the journey.

### 中文

**Slogan**

> 以星为引，变更有证。

**README 开场**

> **Asterwynd** 是一个本地 Coding Agent 系统。它理解代码仓库、找到从问题到修复的路径、调用工具执行变更和验证，并留下完整的 diff、日志、工具 trace 与 benchmark 证据——让每次代码修改都是可证明的，而不只是“看起来对的”。
>
> 星辰定向，风推动前行，trace 证明来过。

## Slogan

**英文（短）：**

> Navigate by stars. Prove with traces.

**英文（长一点，用于 README 副标题）：**

> A local agent system that navigates complex repositories and proves every change with test-backed traces.

**中文（短）：**

> 以星为引，变更有证。

**中文（长）：**

> 一个在复杂代码仓库中辨认方向、执行变更、并用测试和 trace 证明每次修改的本地 Agent 系统。

---

## README 第一段

### 英文

**Version A — 直接落地版（推荐用这个，先给读者一个锚点再展开隐喻）**

> **Asterwynd** is a local coding agent system for turning repository tasks into traceable, test-backed software changes. It reads your codebase, navigates to the right fix, runs tools, and leaves a trail of evidence—diffs, logs, tool traces, benchmark results—so every change is provable, not just plausible.
>
> Think of it as a navigator for complex code: stars for orientation, wind for movement, and a logbook that records the journey.

**Version B — 诗意先行版（隐喻开篇，再落地）**

> Code repositories are dark skies. Asterwynd is how you navigate them.
>
> It's a local agent that reads code, finds the path from issue to fix, runs tools and tests, and records every step. The result isn't a guess—it's a change backed by traces, diffs, and benchmarks you can inspect and replay.
>
> Stars guide. Wind moves. Traces prove.

**Version C — 极简版（如果偏好短 README）**

> Asterwynd navigates complex codebases and produces verifiable, test-backed changes. It's a local agent system—runtime, tools, context, traces—for turning software tasks into proven diffs.

---

### 中文

**Version A — 直接落地版**

> **Asterwynd** 是一个本地 Coding Agent 系统。它理解仓库结构、定位改动路径、调用工具执行变更，并留下完整的 trace、diff 和 benchmark 证据——让每次代码修改都是可验证的，而不只是"看起来对的"。
>
> 星辰是参照，风是动力，日志记录每一次航行。

**Version B — 诗意先行版**

> 代码仓库是暗夜，Asterwynd 是你辨认方向的星图。
>
> 它是一个本地 Agent：阅读代码，找到从问题到修复的路径，调用工具和测试，记录每一步。最终产物不是一个猜测，而是一个被 trace、diff 和 benchmark 背书的可验证变更。
>
> 星辰定向，风推动前行，trace 证明来过。

**Version C — 极简版**

> Asterwynd 在复杂代码仓库中辨认方向、执行变更、用测试和 trace 证明每次修改。它是一个本地 Agent 系统——运行时、工具、上下文、trace——把软件任务变成可验证的 diff。

---

## 面试 3 分钟开场白（如果选 Asterwynd）

> "Aster 是星辰，wynd 是古英语的风。这个名字说的是：在复杂代码空间里，你需要固定的参照点来定向，也需要动力来穿越。我们的固定参照点是 test 和 benchmark，动力是 agent runtime 和工具系统，而 trace 是我们留下的星图。
>
> 实际上它是一个本地 Coding Agent 系统——不是聊天机器人，不是 single-patch 工具。它读仓库、找路径、调工具、跑测试、产出可验证的 diff。我们在这个项目里建了完整的 agent loop、工具注册、上下文管理、benchmark 评测闭环。一句话：把模糊的软件任务变成可证明的代码变更。"

---

## 对比 Orivane 的叙事差异

两个名字都能讲好故事，但风格不同：

| | Asterwynd | Orivane |
| --- | --- | --- |
| 意象 | 星辰+风，画面感，偏诗意 | 方向+风向标，偏仪器/工具 |
| 面试叙事 | "在暗夜代码天空中辨认星座的导航者" | "软件变更的风向标：找到起点，判断方向，验证修复" |
| 品牌调性 | 更像独立开源项目名（如 Kubernetes, Celery） | 更像精密仪器名（如 Sextant, Compass） |
| 一句话差异 | "Navigate by stars." | "Navigate change. Prove the fix." |
