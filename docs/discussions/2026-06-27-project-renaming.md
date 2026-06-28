# 项目重命名讨论稿

日期：2026-06-27

## 背景

`MyAgent` 作为项目名过于通用，在 GitHub、搜索引擎和面试叙事里都缺少辨识度。这个项目现在的定位已经不是泛化 agent demo，而是面向 Agent 相关开发岗位的本地 Coding Agent 系统：运行时、工具调用、代码理解、代码修改、验证、可观测性和 benchmark 闭环是主线。

新名字应服务于三个目标：

- **可搜索**：GitHub 上同名或近似项目尽量少。
- **可解释**：能联想到代码修复、diff、repo、trace、验证或 benchmark。
- **可长期使用**：不要像临时代号，也不要太窄到只能表示某一个工具。

## 命名方向

### 方向 A：Patch / Diff

强调 Coding Agent 的最终可验证产物是 patch 或 diff。

优点：和 SWE-bench、Claw-SWE-Bench、代码修复任务天然贴合。

风险：名字容易像单一 patch 工具，弱化 Agent runtime、trace、subagent、Web UI 等系统性。

### 方向 B：Repo / Code

强调项目处理 repository-level coding tasks。

优点：更像完整 coding agent，而不只是 patch apply 工具。

风险：`code-*`、`repo-*` 命名非常拥挤，可搜索性通常较差。

### 方向 C：Trace / Proof / Bench

强调可观测、可验证、可评测。

优点：贴合项目差异化：不是只让模型改代码，而是能记录、复现、解释和比较。

风险：过于抽象，第一次看到名字不一定知道是 coding agent。

### 方向 D：组合词

用一个相对少见但好读的意象词搭配 Patch / Diff / Repo，例如 Rivet、Mender、Kiln、Mason。

优点：更容易做到独特和可搜索。

风险：需要一句 tagline 帮用户理解。

## GitHub 初筛结果

检索方式：

- 使用 GitHub Search API 的 `in:name` 查询。
- 同时查了常见大小写合写形式和小写连字符形式。
- API 后续触发 rate limit，因此下表只记录已经完成查询的候选。
- `0` 表示本轮 GitHub 仓库名搜索没有命中，不等于商标、包名或域名可用。

| 候选名 | 合写命中 | 连字符命中 | 备注 |
| --- | ---: | ---: | --- |
| `PatchRivet` | 0 | 0 (`patch-rivet`) | 强候选；独特，和 patch 固定/铆接到 repo 的意象贴合。 |
| `Diffwright` | 0 | 2 (`diff-wright`) | 强候选；wright 有“工匠”含义，强调构造 diff。 |
| `PatchMender` | 0 | 0 (`patch-mender`) | 强候选；直观表达修复代码，但略偏普通。 |
| `TraceMender` | 0 | 0 (`trace-mender`) | 强候选；能表达“根据 trace 修复”，但 coding agent 识别度略弱。 |
| `RepoMender` | 0 | 1 (`repo-mender`) | 可选；repository-level repair 含义明确。 |
| `PatchKiln` | 0 | 0 (`patch-kiln`) | 可选；独特，但 kiln 意象需要解释。 |
| `DiffKiln` | 0 | 0 (`diff-kiln`) | 可选；独特，偏内部代号感。 |
| `PatchMason` | 0 | 2 (`patch-mason`) | 可选；Mason 有构建含义，但近似命中稍多。 |
| `PatchTrace` | 2 | 未查 | 可选；语义好，但已有命中。 |
| `DiffProof` | 0 | 14 (`diff-proof`) | 不推荐；连字符/近似命中多。 |
| `PatchProof` | 11 | 未查 | 不推荐；已有命中较多。 |
| `ProofPatch` | 2 | 未查 | 不推荐；语序不自然。 |
| `CodeMender` | 14 | 未查 | 不推荐；Google DeepMind 已有 CodeMender，冲突明显。 |
| `CodeRivet` | 2 | 未查 | 不推荐；已有 `coderivet/coderivet`。 |
| `Fixloop` | 14 | 未查 | 不推荐；已有命中较多。 |
| `Patchloop` | 6 | 未查 | 不推荐；已有命中。 |
| `PatchLoom` | 4 | 3 (`patch-loom`) | 不推荐；已有 `patchloom/patchloom`。 |
| `CodeYard` | 57 | 57 (`code-yard`) | 不推荐；过于拥挤。 |

## 第二轮：代号型名字

用户反馈：`PatchRivet` 太工程零件化，缺少类似 `pi`、`openclaw`、`hermes` 的想象力。

这个反馈成立。更合适的方向应该是：

- 短、像代号，而不是功能描述。
- 有一层故事或隐喻，面试时能展开。
- 仍然能和 coding-agent 主线连接：代码仓库是迷宫，patch 是线索，验证是回到出口。

### 神话/文学原名的检索结果

| 候选名 | GitHub `in:name` 命中 | 判断 |
| --- | ---: | --- |
| `Ariadne` | 1105 | 不推荐；名字很好，但太拥挤。 |
| `Daedalus` | 1739 | 不推荐；构造者意象好，但重名严重。 |
| `Kintsugi` | 594 | 不推荐；修复隐喻好，但重名严重。 |
| `Palimpsest` | 242 | 不推荐；文本层叠意象好，但太长且已有较多命中。 |
| `Mimir` | 1758 | 不推荐；智慧/记忆意象好，但 Grafana Mimir 等项目已占据心智。 |
| `Sibyl` | 617 | 不推荐原名；oracle 意象好，但重名多。 |
| `Pythia` | 1277 | 不推荐；已有 EleutherAI Pythia 等强占位。 |

结论：直接用神话/文学原名不可行，应该做变体或组合。

### 更有想象力的候选

| 候选名 | GitHub `in:name` 命中 | 说明 |
| --- | ---: | --- |
| `PatchSibyl` | 0 | 强候选；Sibyl 是 oracle，表达“预见/判断 patch 是否成立”。 |
| `DiffSibyl` | 0 | 强候选；更偏 diff 产物和验证判断。 |
| `RepoSibyl` | 0 | 强候选；更偏 repository-level coding agent。 |
| `Ariadex` | 4 | 可选；Ariadne + index/dex，表示在代码迷宫里找线索。 |
| `Daedex` | 2 | 可选；Daedalus + index/dex，有构造迷宫和解构迷宫的感觉。 |
| `CodeSibyl` | 1 | 可选；语义直观，但比 `PatchSibyl` 更普通。 |
| `Alethex` | 4 | 可选；Aletheia（真理）+ x，偏验证，但不够 coding。 |
| `Praxion` | 20 | 可选；praxis/action 意象，偏 agent 执行，但已有一些命中。 |
| `Mendrix` | 25 | 不优先；听感不错，但已有 repair benchmark 相关命中。 |
| `Veridex` | 119 | 不推荐；验证语义好，但重名多。 |

## 当前推荐（按“有想象力”重新排序）

### 1. `PatchSibyl`

推荐度最高。

含义：

> 一个能读懂仓库、生成 patch，并通过测试和 trace 判断 patch 是否可信的 coding-agent oracle。

适合的 tagline：

> A coding-agent oracle for turning repo tasks into verified patches.

优点：

- GitHub 本轮 0 命中。
- `Sibyl` 有 oracle / prophecy 的味道，比 `Rivet` 更有记忆点。
- `Patch` 把它拉回 coding agent，不会变成泛 AI 名字。
- 面试时可讲：这个项目不是只生成答案，而是围绕 patch 的可验证性做 runtime、tool、trace 和 benchmark。

风险：

- `Sibyl` 不是人人认识，需要一句 tagline。

### 2. `Ariadex`

含义：

> Ariadne 的线索 + index：在代码仓库迷宫里找到路径。

适合的 tagline：

> A coding agent that follows repository threads to verified fixes.

优点：

- 很像项目代号，有故事感。
- 和 code intelligence / repo map / trace 很贴。
- GitHub 本轮只有 4 个 name 命中，压力不算大。

风险：

- 词义更隐晦，不看 tagline 不知道是 coding agent。
- `Ariadne` 本身重名非常多，搜索时可能被混淆。

### 3. `DiffSibyl`

含义：

> 判断 diff 是否能成立的 oracle。

适合的 tagline：

> An oracle-like coding agent for crafting and validating repository diffs.

优点：

- GitHub 本轮 0 命中。
- 比 `PatchSibyl` 更偏 benchmark / diff 结果。

风险：

- `Diff` 比 `Patch` 更技术化，名字读起来稍冷。

### 4. `RepoSibyl`

含义：

> 一个理解 repository 并给出可验证修改建议的 oracle。

适合的 tagline：

> A repository-level coding agent with traceable, test-backed fixes.

优点：

- GitHub 本轮 0 命中。
- 比 `PatchSibyl` 更强调 repo-level。

风险：

- `Repo` 稍普通，想象力弱于 `PatchSibyl`。

## 第三轮：完全不绑定 coding-agent 的代号型名字

用户进一步反馈：名字不一定要和 coding agent 相关，可以更大胆。

这一轮不再强行塞 `Patch`、`Diff`、`Repo`、`Code` 这些工程词，而是追求更像独立项目名的感觉：短、有画面、能讲故事、搜索压力小。

### 初筛结果

| 候选名 | GitHub `in:name` 命中 | 判断 |
| --- | ---: | --- |
| `Orivane` | 0 | 强候选；像风、方向、航路，也像一个虚构世界里的工具名。 |
| `Asterwynd` | 0 | 强候选；星辰 + 风，画面感强，适合“穿过复杂代码空间”的叙事。 |
| `Orendae` | 0 | 强候选；接近 Orenda（内在力量/精神力），但做了变体，搜索压力小。 |
| `Talyra` | 1 | 强候选；短、柔和、像产品名，几乎无搜索压力。 |
| `Noemora` | 7 | 可选；Noema/思维 + aura，偏智能体心智。 |
| `Aurelith` | 8 | 可选；aura/gold + lith/stone，稳定、古物感。 |
| `Neralis` | 8 | 可选；像一个系统或星名，搜索压力低。 |
| `Osmira` | 9 | 可选；轻盈但不够有技术辨识度。 |
| `Caldrin` | 8 | 可选；像 fantasy 名字，但技术感较弱。 |
| `Veyra` | 333 | 不推荐；听感好但命中多。 |
| `Vespera` | 262 | 不推荐；好听但过于常见。 |
| `Luminara` | 333 | 不推荐；太常见。 |
| `Veloria` | 244 | 不推荐；太常见。 |
| `Mythra` | 263 | 不推荐；重名多且容易联想到既有角色/项目。 |

### 当前更大胆的推荐

#### 1. `Orivane`

推荐度最高。

感觉：

> 像一个能在复杂系统里辨认方向的 instrument，而不是普通工具名。

可讲故事：

- `Ori` 有 origin / orientation 的联想。
- `vane` 是风向标，暗示“在不确定的代码空间里判断方向”。
- 不直接说 coding agent，但可以承载 agent runtime、trace、benchmark 这些系统能力。

tagline：

> An instrument for navigating, changing, and proving complex software systems.

优点：

- GitHub 本轮 0 命中。
- 好读，拼写不算怪。
- 比 `PatchSibyl` 更像独立产品名。

风险：

- 语义不直给，需要 tagline 建立含义。

#### 2. `Asterwynd`

感觉：

> 星图和风，像一个穿过复杂空间的导航者。

tagline：

> A software navigator for tracing paths through change.

优点：

- GitHub 本轮 0 命中。
- 很有画面，适合做 logo / 项目叙事。

风险：

- `wynd` 拼法偏 fantasy，可能有人拼错。

#### 3. `Orendae`

感觉：

> 有内在力量的系统，不像工具，更像 runtime 的名字。

tagline：

> A local agent runtime with memory, tools, and proof.

优点：

- GitHub 本轮 0 命中。
- 比 `Orenda` 更独特。

风险：

- 读音不一定统一：o-ren-day / o-ren-dae。

#### 4. `Talyra`

感觉：

> 短、干净、像一个 AI 产品名。

tagline：

> A local agent system for software work.

优点：

- GitHub 本轮只有 1 命中。
- 好读、好记、没有明显技术包袱。

风险：

- 含义太轻，需要靠品牌叙事补。

## 第四轮：沿着 `Orivane` 和中国元素继续发散

用户反馈：`Orivane` 感觉不错；希望继续找类似名字，也可以融入中国元素。优先级是朗朗上口、含义正向、读出来有感觉。

### `Orivane` 相近路线

| 候选名 | GitHub `in:name` 命中 | 说明 |
| --- | ---: | --- |
| `Orivane` | 0 | 当前强候选；orientation / origin + vane，方向感明确。 |
| `Verivane` | 0 | veri 有 truth / verify 联想，偏“真值风向标”。 |
| `Navivane` | 0 | navi + vane，导航感最直观，但略像导航软件。 |
| `Aevane` | 0 | 更抽象、更像代号；含义轻。 |
| `Astravane` | 0 | astra + vane，星辰导航感强，画面好但稍长。 |
| `Aurivane` | 1 | auri 有 gold / aura 联想，正向但已有少量命中。 |
| `Lumivane` | 1 | lumi 有 light 联想，读起来顺，但已有少量命中。 |
| `Solvane` | 10 | solve + vane 很贴工程，但命中较多且功能感更强。 |

### 融入中国元素的路线

采用轻量拼音元素，不做纯中文名：

- `dao`：道、路径、方法。
- `ming`：明、清楚、照亮。
- `yun`：云、流动、云端。
- `xing`：星、导航、远方。
- `xuan`：玄、深奥、机制、天体仪象。

| 候选名 | GitHub `in:name` 命中 | 说明 |
| --- | ---: | --- |
| `DaoVane` | 0 | 道 + 风向标；含义好，但大小写中间感略强。 |
| `Yunvane` | 0 | 云 + vane；轻盈，有云端/流动感。 |
| `Xingvane` | 0 | 星 + vane；星象导航感强，正向。 |
| `Xingora` | 0 | 星 + aura/oracle 的感觉；更像产品名。 |
| `Xuanora` | 0 | 玄 + aura/oracle；有东方玄学/深层机制感，比较有脑洞。 |
| `Xuanvane` | 0 | 玄 + vane；像“判断深层系统方向”的仪器。 |
| `Yunway` | 0 | 云 + way；非常直观，但稍普通。 |
| `Xingway` | 1 | 星路；直观正向，但英文组合略直白。 |
| `Oridao` | 0 | orientation/origin + 道；含义不错，但读音像日语/拼音混合。 |
| `Navidao` | 0 | navi + 道；导航之道，直观但稍像工具名。 |
| `Mingdao` | 109 | 不推荐；中文含义很好，但重名多。 |
| `Lingora` | 67 | 不推荐；已有命中较多。 |
| `Lingvane` | 59 | 不推荐；且容易联想到 Lingvanex。 |

### 这一轮推荐

1. `Orivane`：仍然最平衡。好读、0 命中、正向、有方向感。
2. `Xingvane`：中文元素更明显，星 + 风向标，寓意“以星定向”。
3. `Xuanora`：更有想象力，东方感更强，但需要解释。
4. `Verivane`：更贴验证和 truth，技术意味更强。
5. `DaoVane`：含义好，但视觉上稍像两个词拼接。

如果要兼顾国际可读性和一点中国元素，当前最值得继续推敲的是 `Xingvane` 和 `Xuanora`。如果要最稳，还是 `Orivane`。

## `Orivane` 与 `Ariadex` 复查

### `Orivane`

GitHub 复查结果：

- 仓库名搜索：`Orivane` / `orivane` 均为 0 命中。
- 用户名：`github.com/orivane` 已被一个 User 占用。
- 该用户公开仓库数为 0，followers 为 0，bio/name/company 均为空。
- 账号创建于 2026-02-16，公开资料看起来像空账号或占位账号。

判断：

- 不能注册 `orivane` 这个 GitHub user/org。
- 可以使用 `Xingkai98/orivane` 作为仓库名；从仓库名搜索角度看很干净。

### `Ariadex`

GitHub 复查结果：

- 仓库名搜索：4 个命中。
- 组织名：`github.com/ariadex` 已被一个 Organization 占用，public repos 为 0。

命中的仓库：

| 仓库 | 描述 | 判断 |
| --- | --- | --- |
| `DancingLightStudios/ariadex` | C# CLI，描述为 indexing / navigating / enriching codebase searches | 与本项目方向有实际重叠，会造成混淆。 |
| `pauloabelha/ariadex` | Chrome extension，用于探索 X 对话图和生成引用摘要 | 有少量相关的 graph / summary 意象，但领域不同。 |
| `batuhancbl/ariadexevm` | `dex conf` | 基本无影响。 |
| `Batuhankayhan/ariadexevm` | 无描述 | 基本无影响。 |

判断：

- `Ariadex` 的故事更贴“代码迷宫里的线索索引”，但它已经有一个 codebase search / navigation CLI 同名仓库。
- 如果优先可搜索和避免混淆，`Ariadex` 应降级。

### 当前结论

`Orivane` 目前比 `Ariadex` 更适合作为首选：

- 仓库名搜索 0 命中。
- 读音更顺。
- 含义正向：origin / orientation + vane，可以解释为“软件变更的风向标”。
- 不绑定 coding agent，后续项目扩展到 agent runtime、工具系统、benchmark、code intelligence 也能承载。

## 第五轮：围绕 `Orivane` 再头脑风暴

目标：保留 `Orivane` 的优点——朗朗上口、正向、像未来产品名、没有强功能词，同时看看有没有同一审美层级的替代项。

### 新候选初筛

| 候选名 | GitHub `in:name` 命中 | 说明 |
| --- | ---: | --- |
| `Orevane` | 0 | `Orivane` 的近亲，更像 ore / origin + vane；读音不如 Orivane 清晰。 |
| `Orivora` | 0 | 好读、像一个有生命感的系统名；含义更抽象。 |
| `Veyline` | 0 | vey + line，像路径线/基准线；短，顺，但含义轻。 |
| `Elarive` | 0 | 像 arrive / alive 的变体，有到达和行动感；读音顺。 |
| `Orynthe` | 0 | 更 fantasy / mythic，像一个神话地名或系统名；读音可能不统一。 |
| `Veymark` | 0 | 标记方向；比 Veyline 更工程，但也更直白。 |
| `Beaconry` | 2 | beacon 的集合/体系，含义很好，但有少量命中。 |
| `Navalis` | 5 | navigation / naval 联想，稳但不够独特。 |
| `Orialis` | 3 | 接近 orientation / aurora，读音不错但已有少量命中。 |
| `Orynva` | 2 | 短、独特，但拼写感较强。 |
| `Velinor` | 6 | 好听，但更像 fantasy 地名。 |
| `Caelora` | 6 | 天空感强，但偏通用 AI 产品名。 |

### 与 `Orivane` 对比

| 名字 | 直观含义 | 读音 | 独特性 | 叙事承载 |
| --- | --- | --- | --- | --- |
| `Orivane` | origin / orientation + vane | 强 | 强 | 强 |
| `Orivora` | 抽象生命体 / 系统名 | 强 | 强 | 中 |
| `Elarive` | arrive / alive / drive | 强 | 强 | 中 |
| `Veyline` | 路径线 / 方向线 | 强 | 强 | 中 |
| `Veymark` | 路标 / 标记方向 | 强 | 强 | 中 |
| `Orynthe` | 神话地名感 | 中 | 强 | 中 |

### 第五轮结论

`Orivane` 仍然最稳。它不像 `Veyline` / `Veymark` 那么工具化，也不像 `Orivora` / `Orynthe` 那么抽象。

如果想要比 `Orivane` 更像“品牌名”，可以考虑：

- `Orivora`：更有生命感，但含义弱。
- `Elarive`：更顺口，有“到达/行动”的积极含义。
- `Veyline`：更简短，但容易像普通工具。

当前总排序：

1. `Orivane`
2. `Elarive`
3. `Orivora`
4. `Veyline`
5. `Asterwynd`
6. `PatchSibyl`

## 第一轮保守候选

### 1. `PatchRivet`

第一轮的保守首选，但因为想象力不足，现在降级为备选。

含义：

> 把一个可验证的 patch 牢固地铆进代码仓库。

适合的 tagline：

> A benchmarkable coding agent that turns repo tasks into verified patches.

优点：

- GitHub 合写和连字符形式本轮均 0 命中。
- 比 `MyAgent` 搜索友好很多。
- `Patch` 直连 coding-agent 任务结果，`Rivet` 有稳定、固定、工程感。

风险：

- 需要 tagline 解释它是完整 agent 系统，不只是 patch 工具。

### 2. `Diffwright`

推荐度第二。

含义：

> 一个“写出正确 diff 的工匠”。

适合的 tagline：

> A traceable coding agent for crafting and validating repository diffs.

优点：

- 合写形式本轮 0 命中。
- 名字有工程感，不落入泛 agent 命名。
- 比 `PatchRivet` 更强调 diff 产物。

风险：

- `wright` 对非英语母语用户不一定直观。
- `diff-wright` 有少量近似命中。

### 3. `PatchMender`

推荐度第三。

含义：

> 修补代码的 agent。

适合的 tagline：

> A local coding agent for repairing repos and proving patches with tests.

优点：

- 合写和连字符形式本轮均 0 命中。
- 含义直接，容易讲。

风险：

- 比 `PatchRivet` 更普通，可记忆性稍弱。

## 暂不推荐的方向

- `Code*`：GitHub 上过于拥挤，且容易和通用代码工具撞名。
- `Agent*`：泛化且和大量 agent demo 撞名，不能解决 `MyAgent` 的问题。
- `Proof*`：强调验证不错，但不够像 coding agent。
- `Loop*`：容易变成通用 agent loop / workflow 工具名。

## 后续决策问题

1. 项目名是否应该突出 **patch 产物**，还是突出 **repo-level coding agent**？
2. 面试时更想讲“可验证 patch 生成器”，还是“可观测 coding agent runtime”？
3. 是否需要同时考虑 PyPI 包名、GitHub repo 名、CLI 命令名和未来域名？
4. 如果选 `PatchRivet`，Python 包名是否使用 `patchrivet`，CLI 命令是否使用 `patchrivet`？

## 建议下一步

如果接受 `PatchRivet` 作为首选名，可以进入第二阶段：

1. 补查 PyPI、npm、域名和搜索引擎重名。
2. 定义 rename 边界：仓库名、README 标题、包名、CLI 命令、环境变量、配置文件、文档引用。
3. 先做文档和品牌文本 rename，再单独评估是否改 Python package/import path。
4. 如果要改 import path，应拆成独立 OpenSpec change，明确兼容策略和迁移测试。

## 第六轮：工具探索与新候选（2026-06-27）

### 工具探索

跑了 7 类工具：4 个在线 AI 命名生成器（Namelix、Musely、IO Tools、Trickle）、3 个 npm 命令行工具（@lxgicstudios/ai-name、joyful、nscout）、1 个自写 Python 词根组合生成器。

- 在线工具均被网络安全策略拦截，但其功能模式已验证（Namelix 的"短词根+软化后缀"模式与本项目 `Orivane`/`Elarive` 路线高度一致）。
- npm 工具偏功能描述型（-ify, -stack, -ware），不推荐。
- Python 自写生成器从拉丁/希腊语词根出发产生了最有价值的候选。

详见 [命名工具探索记录](./2026-06-27-naming-tool-exploration.md)。

### `Asterwynd` 正式列为候选

GitHub 复查：

- 仓库名搜索：`Asterwynd` / `asterwynd` 均为 0 命中。
- 用户/组织名：`Asterwynd` / `asterwynd` 均未被占用。
- `Asterwind`（常规拼法）的用户已被空账号占用（类似 `Orivane` 的情况），但 `Asterwynd` 完全干净。

寓意：

> Aster（星辰，希腊语 ἀστήρ）+ Wynd（风，wind 的古英语/诗歌拼法）。以星辰定向，乘风穿越复杂代码空间。

`wynd` 是古英语中真实存在的拼法（如 Sir Walter Scott 作品中），不是生造 kool spelling。面试时可以解释：`wind` 太普通，`wynd` 给了名字一种古老导航仪器的质感。

适合的 tagline：

> A software navigator through complex change.
> 在复杂变更中辨认星图。

### 从拉丁/希腊词根出发的新候选

本轮 Python 生成器发现了若干有真实古典语源的名字，可作为 `Orivane`/`Asterwynd` 路线之外的补充：

| 名字 | 词源 | 感觉 | 风险 |
| --- | --- | --- | --- |
| `Veracis` | 拉丁 verus(真) + acis(锋利) | 对代码变更的锋利真值判断 | 已有 GitHub user/org 占用 |
| `Cursora` | 拉丁 cursor(奔跑者) + ora | 在代码路径上奔跑抵达验证 | 待查重 |
| `Sigillum` | 拉丁 sigillum(封印) | 为验证过的变更盖封印 | 三音节，略正式 |
| `Claritas` | 拉丁 claritas(清晰) | 让复杂变清晰 | 待查重，且接近 Clarity 等常见项目名 |
| `Lucerna` | 拉丁 lucerna(灯盏) | 代码迷宫中的灯 | 待查重 |
| `Nexilis` | 拉丁 nexilis(编织) | 任务到验证的闭环 | 含义不够直观 |

这些拉丁候选虽有深度，但在朗朗上口和品牌感上暂不如 `Orivane`/`Elarive`/`Asterwynd`。建议作为备选，不进入首选排序。

### 更新后的总排序

1. `Asterwynd` — 画面感最强，星辰 + 风，GitHub repo 与 user/org 均干净，当前最像长期项目名。
2. `Orivane` — 最平衡，origin / orientation + vane，故事稳，repo 干净但 user 已被空账号占用。
3. `Elarive` — 最顺口，arrive/alive/drive 三重联想，0 命中，但故事性弱于前两者。
4. `Orivora` — 更有生命感，-vora 吞噬隐喻有性格，但含义抽象。
5. `Veyline` — 最简洁，但偏工具感。
6. `Fluvane` — 流动 + 风向标，读音稳，基本干净。

## 第七轮：`Asterwynd` 作为当前首选

另一个模型输出了完整的 `Asterwynd` handoff，见 [Asterwynd 候选方案](./2026-06-27-asterwynd-handoff.md) 和 [Asterwynd slogan / README 文案](./2026-06-27-asterwynd-slogan-readme.md)。

### 最新 GitHub 核查

| 检查项 | 结果 |
| --- | --- |
| 仓库名搜索 `Asterwynd` | 0 命中 |
| 仓库名搜索 `asterwynd` | 0 命中 |
| 用户/组织名 `Asterwynd` | 未被占用 |
| 用户/组织名 `asterwynd` | 未被占用 |
| 仓库名搜索 `Asterwind` / `asterwind` | 0 命中 |
| 用户名 `Asterwind` / `asterwind` | 已被空账号占用，public repos 为 0 |

### 为什么 `Asterwynd` 现在领先

- **画面感更强**：星辰 + 风，比 `Orivane` 的风向标更有开源项目代号气质。
- **叙事更完整**：星辰对应测试、benchmark、trace 这些固定参照；风对应 agent runtime、工具调用和代码变更的动力；航迹对应日志、diff、tool trace 和 benchmark evidence。
- **搜索更干净**：GitHub 仓库名和 user/org 都未被占用，优于 `Orivane` 的 user 已占。
- **视觉延展性更好**：星图、风线、航迹、夜空都能作为 logo 和 README 视觉语言。

### 需要接受的代价

- `wynd` 拼法不是现代英语常规拼法，可能有人拼成 `Asterwind`。
- 读音应写清楚：`AS-ter-wynd`，更准确地说是 3 个音节，不是 2 个音节。
- 需要 tagline 建立认知，不能像 `OpenCode` 那样一眼看出功能。

### 当前推荐文案

英文短 slogan：

> Navigate by stars. Prove with traces.

中文短 slogan：

> 以星为引，变更有证。

英文一句话：

> Asterwynd is a local agent system that navigates complex repositories and proves every change with test-backed traces.

中文一句话：

> Asterwynd 是一个在复杂代码仓库中辨认方向、执行变更，并用测试和 trace 证明每次修改的本地 Agent 系统。

### 当前判断

如果目标是“朗朗上口、正向、有画面、有长期项目名气质”，`Asterwynd` 当前优先级高于 `Orivane`。

如果目标是“含义更直观、少解释、偏精密仪器感”，`Orivane` 仍是强备选。
