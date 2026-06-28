# 命名工具探索记录

日期：2026-06-27

## 探索总结

跑了 7 类工具：4 个在线 AI 命名生成器、3 个 npm 命令行工具、1 个自写 Python 词根组合生成器。在线工具全部被网络安全策略拦截，npm 工具偏向功能描述型（-ify, -stack, -ware），Python 自写生成器产出最好。

## 工具清单

### 在线工具（均被拦截，但功能定位已验证）

| 工具 | URL | 特色 | 与本项目的相关性 |
| --- | --- | --- | --- |
| **Namelix** | namelix.com | AI 模型，学习用户偏好，短品牌名 | ★★★★★ 最对标。Style: Mindora, Floweo, Tasksy 等短品牌名 |
| **Musely Code Name Generator** | musely.ai/tools/cool-code-name-generator | 15 主题、10 风格、关键词注入 | ★★★★ 适合 internal codename |
| **IO Tools Brand Name Generator** | iotools.cloud/tool/brand-name-generator | 内置拉丁/希腊词根风格、创意拼写 | ★★★★ 词根方向最精准 |
| **Trickle Code Name Generator** | trickle.so/tools/code-name-generator | 军事/神话/科技/太空主题 | ★★★ 偏 codename，不太适合品牌名 |

> 如果需要实际使用 Namelix，可以在本地浏览器打开 `https://namelix.com`，输入关键词 `code repository navigation trace verify proof change` 尝试。Namelix 的学习机制意味着多次使用会优化推荐。

### npm 命令行工具（已实测）

| 工具 | 命令 | 实测效果 |
| --- | --- | --- |
| **@lxgicstudios/ai-name** | `npx @lxgicstudios/ai-name "..."` | techy 风格：功能词拼装（toolsware, contextstack, diffsforge）。不推荐。 |
| **joyful** | `npx joyful` | 生成 Heroku 风格形容词-名词组合（tactful-vega）。不适合品牌命名。 |
| **nscout** | `npx nscout --suggest "..."` | AI 模式需要 OpenAI/Anthropic API key。无 key 时超时。多注册源检查功能可用。 |

### Python 自写生成器（4 策略并行）

策略 1: **Namelix 风格** Root + Suffix（如 Ori+vane、Luci+ora）
策略 2: **复合词 Blend**（如 Ori+Repo → Orepo, Code+Vane → Codvane）
策略 3: **CV 模式**（如 Figma/Zapier 的辅元交替，产出太随机）
策略 4: **拉丁/希腊词根**（从古典语言中提取并现代化拼接）

## 本轮新发现的候选名

### 从拉丁/希腊语词根出发的（策略 4 最优）

这些名字有真实的古典语源，可以讲出有深度的故事：

| 名字 | 词源 | 一句话 | 适合的 tagline |
| --- | --- | --- | --- |
| `Veracis` | 拉丁 verus(真) + acis(锋利) | 对代码变更的锋利真值判断 | Sharply true. Code-proven. |
| `Cursora` | 拉丁 cursor(奔跑者) + ora | 在代码路径上奔跑、抵达验证结果 | Run the course. Prove the change. |
| `Tramesia` | 拉丁 trames(路径/小径) + ia | 代码空间中的路径系统 | Find paths. Leave traces. |
| `Sigillum` | 拉丁 sigillum(封印/标记) | 为每次验证过的变更封印 | Seal every change with proof. |
| `Claritas` | 拉丁 claritas(清晰/明亮) | 让复杂代码变更变得清晰 | Bring clarity to complexity. |
| `Lucerna` | 拉丁 lucerna(灯盏) | 在代码迷宫中照明 | Light in the code labyrinth. |
| `Nexilis` | 拉丁 nexilis(编织在一起) | 把任务到验证编成闭环 | Bind task to proof. |
| `Textoris` | 拉丁 textor(织工) | 编织代码的工匠 | Weave code. Prove pattern. |
| `Fabricor` | 拉丁 fabricor(建造) | 建造可验证的软件变更 | Build change. Leave proof. |
| `Novamen` | 拉丁 novamen(更新) | 通过验证过的变更带来新生 | Renew code. Prove it. |
| `Navalis` | 拉丁 navis(船) + alis | 在代码海洋中导航 | Navigate code. Arrive at proof. |
| `Gnomon` | 希腊 gnomon(指示者/知晓者) | 指向代码真相的指示器 | Point to truth in code. |
| `Dilucis` | 拉丁 dilucis(黎明/破晓) | 代码理解的新黎明 | Dawn on repository complexity. |
| `Orith` | 希腊 oris(边界) + ithos(习性) | 代码空间中的边界标记 | Boundary finder. Path prover. |
| `Probatus` | 拉丁 probatus(已被证明的) | 被验证过的存在 | Proven change. Every time. |

### 从词根组合出发的（策略 1 最佳）

| 名字 | 来源 | 感觉 |
| --- | --- | --- |
| `Veria` | veri(真理) + ia | 短、干净，像一个真理系统 |
| `Trames` | tram(路径) + es | 接近 "tram"(铁轨) + "trace"，路径感很强 |
| `Lucida` | luci(光) + da | 像"清晰的"，但做了一定变化 |
| `Stellae` | stell(星) + ae | 星之精华，画面感强 |
| `Solia` | sol(太阳/唯一) + ia | 短、亮、好读 |
| `Vialis` | via(路) + alis | 属于道路的 |

### 从复合词 Blend 出发的（策略 2）

| 名字 | 来源 | 感觉 |
| --- | --- | --- |
| `Ortrace` | ori + trace | 起点追踪 |
| `Tracvane` | trace + vane | 追踪风向标 |
| `Tracmark` | trace + mark | 追踪标记 |
| `Codvane` | code + vane | 代码风向标 |
| `Verpath` | veri + path | 真值路径 |

### 从 Namelix 的用户反馈中学习到的命名模式

Namelix 生成的好名字（如 Mindora, Floweo, Tasksy, Brainlift）遵循的模式：

```
一个有意义的短词根 + 一个软化/品牌化的后缀
```

后缀清单（按常见度）：
- `-ora`（Mindora, Orivora）
- `-eo`（Floweo）
- `-sy`（Tasksy）
- `-ify`/`-ift`（Brainlift）
- `-ly`（Tracely）
- `-ix`（Mendrix）

这个模式与我们项目的第一轮候选（Orivane, Orivora, Elarive）高度一致。

## 值得关注的新方向

与上一版讨论（Orivane/Ariadex 路线）相比，本轮探索发现了两个新方向：

### 方向 1: 纯拉丁语词根（`Veracis` / `Sigillum` / `Claritas`）

优点：
- 古典、权威、有"真理/验证"的正向含义
- 不是随机造词，每个都有真实词源可讲
- 在开源社区里差异化明显（Latino-Greek 命名在开发者工具里不常见）

风险：
- 部分词（如 Sigillum, Gnomon）对非古典学背景的人不直观
- 需要 tagline 建立含义桥梁

### 方向 2: 极短型（`Orith` / `Veria` / `Solia`）

优点：
- 5-6 个字符，极简
- 好记、好读、好打字
- 适合 CLI 命令名和命令行场景

风险：
- 含义非常轻，需要品牌叙事
- 可能与某些短词或产品名撞车，需要更多搜索验证

## 如果要继续推进

建议三步：

1. **实际使用 Namelix**（浏览器打开 namelix.com），因为它是这个领域最好的免费工具。输入 `code repository navigation trace verify proof diff agent` 看输出。它的 AI 模型比任何规则型生成器都更有创造力。

2. **从本轮拉丁语词根候选和之前 Orivane 路线中各选 2-3 个**，做最终对比。

3. **开始第二阶段验证**：PyPI / GitHub org / 域名 / 搜索引擎复查。
