# 长期记忆 规格

## Purpose

定义 长期记忆 能力域的规格。当前为基线状态；深化需求通过 OpenSpec change 的 spec delta 演进。

## Requirements

### Requirement: 长期记忆 能力域基线

长期记忆 能力域 SHALL 提供基础能力，深化需求通过 OpenSpec change 的 ADDED Requirements 合入演进。

#### Scenario: 能力域可扩展

- **GIVEN** 一个针对 长期记忆 能力域的 OpenSpec change
- **WHEN** 该 change 的 spec delta 被接受
- **THEN** 能力域的 requirement 随 ADDED Requirements 演进

### Requirement: 写入去重与冲突检测

长期记忆系统 SHALL 通过 embedding 召回 top-5 相似记忆对 incoming 记忆去重，SHALL 用 LLM 判断将其归类为"补充/更新/矛盾"三分支，SHALL 标记矛盾并维护 change log。

#### Scenario: 矛盾记忆被标记

- **GIVEN** 一条 incoming 记忆与召回的相似记忆矛盾
- **WHEN** LLM 判断关系为"矛盾"
- **THEN** 矛盾 SHALL 被标记
- **AND** change log 记录一条矛盾条目

#### Scenario: 补充分支合并追加

- **GIVEN** 一条 incoming 记忆对既有记忆只是补充细节
- **WHEN** LLM 判断关系为"补充"
- **THEN** incoming 内容 SHALL 合并追加到既有记忆 body
- **AND** 不新建独立记忆文件

#### Scenario: 更新分支替换既有记忆

- **GIVEN** 一条 incoming 记忆取代既有记忆的内容
- **WHEN** LLM 判断关系为"更新"
- **THEN** 既有记忆的 description 与 body SHALL 被整体替换
- **AND** change log 记录一条更新条目

### Requirement: importance × recency 时效性衰减

长期记忆系统 SHALL 用 importance × recency 对记忆评分，SHALL 对超 30 天未检索且衰减评分低于可配置阈值的记忆自动归档，SHALL 提供归档/恢复 API。

#### Scenario: 过期记忆自动归档

- **GIVEN** 一条记忆超过 30 天未被检索
- **AND** 其衰减评分低于可配置阈值（高 importance 记忆评分较高，可豁免归档）
- **WHEN** 衰减评分触发归档
- **THEN** 该记忆 SHALL 被自动归档
- **AND** 可通过恢复 API 还原

#### Scenario: 高重要度记忆豁免归档

- **GIVEN** 一条记忆超过 30 天未被检索
- **AND** 其 importance × recency 评分高于可配置阈值
- **WHEN** 衰减评分检查执行
- **THEN** 该记忆 SHALL 不被归档
- **AND** 仍处于 active 区可检索

### Requirement: 按需语义检索与全局摘要

长期记忆系统 SHALL 仅向上下文注入 ~50 token 的全局摘要，SHALL 暴露 `SearchMemory` 工具做按需语义检索。

#### Scenario: 按需语义检索

- **GIVEN** 上下文只注入了 ~50 token 全局摘要
- **WHEN** 模型用 query 调用 `SearchMemory`
- **THEN** 返回 top-k 语义相似的记忆

### Requirement: Scope 隔离

长期记忆系统 SHALL 用 project/repo scope 标记记忆，SHALL 在项目间强制 scope 隔离。

#### Scenario: 跨项目查询被阻止

- **GIVEN** 一条记忆标记为项目 A scope
- **WHEN** 项目 B 的查询尝试访问它
- **THEN** 访问 SHALL 被阻止
- **AND** 不发生跨项目数据泄露
