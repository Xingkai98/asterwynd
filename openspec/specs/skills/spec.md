# skills 规格

## Purpose

定义 Markdown skill 的加载、解析、匹配和系统提示注入。当前实现位于 `agent/skills/loader.py`。

## Requirements

### Requirement: 从 Markdown frontmatter 加载 skill

SkillLoader SHALL 从指定目录读取 `*.md` 文件，并解析 frontmatter 与正文。

#### Scenario: skill 文件格式有效

- **GIVEN** Markdown 文件包含 frontmatter 和正文
- **WHEN** SkillLoader 加载目录
- **THEN** 系统 SHALL 创建 Skill 对象
- **AND** 填充 name、description、tools、always 和 prompt

### Requirement: 无效 skill 文件不阻断加载

SkillLoader SHALL 跳过无法解析的 skill 文件。

#### Scenario: 某个 skill 格式错误

- **GIVEN** 目录中同时存在有效和无效 skill
- **WHEN** 调用 `load`
- **THEN** 系统 SHALL 返回有效 skill
- **AND** 忽略无效文件

### Requirement: always skill 注入系统提示

SkillLoader SHALL 将 `always: true` 的 skill 拼接到系统提示片段中。

#### Scenario: 获取系统提示

- **GIVEN** skills 列表包含 always skill
- **WHEN** 调用 `get_system_prompt`
- **THEN** 返回文本 SHALL 包含该 skill 名称和 prompt

### Requirement: 按描述匹配普通 skill

SkillLoader SHALL 基于 skill description 与用户 query 的包含关系匹配非 always skill。

#### Scenario: query 命中 description

- **GIVEN** 一个非 always skill 的 description 出现在 query 中
- **WHEN** 调用 `match_skills`
- **THEN** 该 skill SHALL 出现在匹配结果中

