# Domain docs

本文档说明 Matt Pocock engineering skills 在探索本仓库时如何读取领域语言和架构决策。

## 布局

本仓库是 single-context repo：

- 根目录 `CONTEXT.md` 是唯一项目词汇表。
- 当前没有 `CONTEXT-MAP.md`。
- 当前没有 `docs/adr/`；如后续形成重要架构决策，`grill-with-docs` 或人工维护者可按需创建。

## 探索前读取

在执行 `triage`、`to-prd`、`to-issues`、`diagnose`、`tdd`、`review`、`improve-codebase-architecture` 等 skills 前：

1. 读取根目录 `CONTEXT.md`，使用其中定义的项目语言。
2. 如果 `docs/adr/` 存在，并且其中 ADR 与当前任务相关，则读取对应 ADR。
3. 如果相关文档不存在，静默继续；不要因为缺少 ADR 主动要求创建。

## 语言使用

输出 issue 标题、PRD、诊断假设、测试名或重构建议时，使用 `CONTEXT.md` 中定义的术语。不要漂移到词汇表明确避免的同义词。

如果需要的概念尚未进入词汇表，先判断是否真的是项目语言缺口；若是，后续通过 `grill-with-docs` 讨论并更新 `CONTEXT.md`。

## ADR 冲突

如果输出建议与已有 ADR 冲突，必须明确指出冲突，而不是静默覆盖：

```text
Contradicts ADR-0007 (...) -- but worth reopening because ...
```
