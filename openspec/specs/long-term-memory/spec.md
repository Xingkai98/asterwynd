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

长期记忆系统 SHALL 用 scope（项目/repo，以及本 change 新增的 agent 人设 × 会话面）标记记忆，SHALL 在**项目间**强制 scope 隔离，并 SHALL 在同一项目内按 **agent 人设 × 会话面**强制 scope 隔离：不同人设之间、同一人设的单聊与各群之间、群与群之间 SHALL 互不可见。

#### Scenario: 跨项目查询被阻止

- **GIVEN** 一条记忆标记为项目 A scope
- **WHEN** 项目 B 的查询尝试访问它
- **THEN** 访问 SHALL 被阻止
- **AND** 不发生跨项目数据泄露

#### Scenario: 跨人设查询被阻止

- **GIVEN** 同一项目下人设 A 保存了一条记忆
- **WHEN** 人设 B 查询记忆
- **THEN** 访问 SHALL 被阻止
- **AND** 人设 A 的记忆 SHALL NOT 出现在人设 B 的检索结果中

#### Scenario: 同一人设的单聊与群聊互不可见

- **GIVEN** 人设 P 在其单聊中保存了一条记忆
- **WHEN** 人设 P 在某个群的会话中查询记忆
- **THEN** 该记忆 SHALL NOT 被检索到

#### Scenario: 同一人设的两个群互不可见

- **GIVEN** 人设 P 在群 A 的会话中保存了一条记忆
- **WHEN** 人设 P 在群 B 的会话中查询记忆
- **THEN** 该记忆 SHALL NOT 被检索到

### Requirement: 可逆写入

长期记忆系统 SHALL 在任何破坏性写（save 覆盖 / supplement / update）前用 git commit-before-write 快照旧状态，使误判的去重判断能回退到旧 body，且每次写记录一条 change log 条目。

#### Scenario: 更新前快照旧状态

- **GIVEN** 一条既有内容的记忆
- **WHEN** 写时去重判断把 incoming 归类为"更新"
- **THEN** 旧 body 在覆盖前 SHALL 被提交到 git 历史
- **AND** change log 记录一条更新条目

#### Scenario: 补充前快照旧状态

- **GIVEN** 一条既有内容的记忆
- **WHEN** 写时去重判断把 incoming 归类为"补充"
- **THEN** 旧 body 在合并前 SHALL 被提交到 git 历史
- **AND** change log 记录一条补充条目

#### Scenario: 误判可回退到旧 body

- **GIVEN** 一条被破坏性写覆盖的记忆
- **WHEN** 用户判定该写是误判
- **THEN** 旧 body SHALL 可从 git 历史恢复
- **AND** 回退记录进 change log

#### Scenario: 回退保持索引一致

- **GIVEN** 一条记忆的 body 与 description 被回退到旧版本
- **WHEN** 回退完成
- **THEN** `MEMORY.md` 中该条索引行 SHALL 重建以匹配回退后的 description
- **AND** 回退的 change log 条目保留（审计历史不回退）

#### Scenario: 回退以两步提交落盘

- **GIVEN** 一条有 git 历史版本的记忆
- **WHEN** 回退工具把记忆恢复到某个旧 commit
- **THEN** 当前状态 SHALL 先被提交（作为撤销凭据）
- **AND** 回退后的 body、重建的索引行、change log 条目 SHALL 再次提交，
  使回退历史在 `git log -- <name>.md` 中立即可见

### Requirement: 冲突解除

长期记忆系统 SHALL 提供冲突解除 API，清除两条矛盾记忆互标的 `conflict_with` 标记，在 change log 记录 resolve 事件，并可选归档败者。败者 SHALL 由显式 `loser` 参数标识。

#### Scenario: 解除冲突清除互标

- **GIVEN** 两条经互标 `conflict_with` 标记为矛盾的记忆
- **WHEN** 用双方 name 调用冲突解除 API
- **THEN** 双方 `conflict_with` 标记 SHALL 被清除
- **AND** change log 记录一条 resolve 事件

#### Scenario: 解除冲突可归档败者

- **GIVEN** 两条矛盾记忆
- **WHEN** 以 archive 启用且 `loser` 参数指向败者调用冲突解除 API
- **THEN** 败者 SHALL 被移动到 archive 目录
- **AND** 胜者保留内容且标记被清除

### Requirement: Git 后端访问

长期记忆系统 SHALL 暴露 git 支持的 history / diff / revert 操作作为可选工具，供 agent 检查与恢复记忆版本。

#### Scenario: agent 检查记忆历史

- **GIVEN** 一条有 git 历史版本的记忆
- **WHEN** agent 对这条记忆调用 git 后端 history 工具
- **THEN** 返回该条的 commit log

#### Scenario: agent 回退到旧版本

- **GIVEN** 一条有 git 历史版本的记忆
- **WHEN** agent 用目标 commit 调用 git 后端 revert 工具
- **THEN** 该条 body SHALL 恢复到目标 commit 版本
- **AND** change log 记录一条 revert 条目

### Requirement: 人设记忆的 review 触发与游标

人设记忆 SHALL 在对应会话的一个回合结束且该回合**实际产生了发言**时触发一次 review；`silent` / `timeout` / `failed` 出口 SHALL NOT 触发；静默成员 SHALL 在其 **review 游标**落后房间日志达到阈值（缺省 30 条）时被补齐一次 review；review SHALL 读取该 scope 自上次 review 游标之后的新增内容，SHALL 经既有 save 路径写回，SHALL 将 `remove` 映射到既有 `archive`（软删），并 SHALL 推进该 scope 的 review 游标；review 失败 SHALL NOT 中断轮次。

#### Scenario: 实际发言的回合结束后触发 review

- **GIVEN** 一个人设在某群的会话刚结束一个**实际产生发言**的回合
- **WHEN** 该回合结束
- **THEN** 系统 SHALL 为该 (人设, 群) scope 排一次记忆 review

#### Scenario: 静默回合不触发 review

- **GIVEN** 一个人设在某群的会话的一个回合以静默（`silent`）结束
- **WHEN** 该回合结束
- **THEN** 系统 SHALL NOT 为该 scope 排 review
- **AND** 该成员的记忆停滞 SHALL 由落后补齐兜底

#### Scenario: 单聊回合也触发 review

- **GIVEN** 一个人设在单聊中结束一个实际产生发言的回合
- **WHEN** 该回合结束
- **THEN** 系统 SHALL 为该人设的单聊 scope 排一次记忆 review

#### Scenario: 静默成员因 review 游标落后被补齐

- **GIVEN** 某成员在某房间的 review 游标落后房间日志达到阈值
- **WHEN** 房间发生新的发言回合
- **THEN** 系统 SHALL 为该成员的 (人设, 群) scope 排一次 review
- **AND** 该判定 SHALL 以 review 游标（而非注入用的 `seen` 游标）为基准

#### Scenario: remove 映射到既有 archive

- **GIVEN** 一次 review 决定移除一条记忆
- **WHEN** 写回该变更
- **THEN** 系统 SHALL 用既有 `archive` 软删该记忆（可 `restore`，且在 move 前有 git 前像）
- **AND** SHALL NOT 引入新的记忆删除原语

#### Scenario: 压缩或恢复后 review 仍推进

- **GIVEN** 单聊 scope 发生过上下文压缩或 session resume（消息表被缩短/重建）
- **WHEN** 该 scope 再次触发 review
- **THEN** review SHALL 仍能读到未 review 的新增内容并推进进度
- **AND** SHALL NOT 重读已被压缩换出的内容
- **AND** SHALL NOT 因消息表变短而永久停止推进

#### Scenario: review 失败不中断轮次

- **GIVEN** 一次记忆 review 在执行中失败
- **WHEN** 该失败发生
- **THEN** 系统 SHALL 记录该失败
- **AND** 当前群聊轮次 SHALL NOT 被中断
