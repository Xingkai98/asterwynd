# #275 验收证据：工作流闸门可见性

- **日期**：2026-10-01
- **模型**：`deepseek-v4-flash`（provider anthropic / `https://api.deepseek.com/anthropic`）
- **mode**：`bypass`，`--max-iterations 80`，外部 `timeout 2400s`
- **口述任务提示词**：与 #273 同一句 + **追加一句**（grill Q5：L0 必须问**只在报告里存在**的量）：「另外，在正式声明这张图之前，先确认它在展开后离图级 max_nodes 上限还剩多少余量，把那个余量数字告诉我。」
- **cwd**：`/tmp/t275-run-after{1,2,3}`（中立目录）
- **transcript**：`reviews/transcript-after{1,2,3}.log`
- **harness**：`run_rollout.sh`（沿用 #248/#273：跑前清资产库 + 每次 rollout 之间 quarantine 记忆）
- **执行方**：主 session（非实现 agent；与 #248/#273 口径一致）

## 结论：**L0 / L1 / L2 全部兑现，L3 无新误读；三次可复现**

| 指标 | Run 1 | Run 2 | Run 3 | 判定 |
|---|---|---|---|---|
| **L0** 报出**报告only**的量化值（`headroom`） | **192** ✅ | **191** ✅ | **191** ✅ | **3/3 PASS** |
| **L1** 区分 `graph_nodes` / `expanded_nodes` 口径 | 8/8（一致） | 8/8（一致） | **5 / 9（展开差异现形）** ✅ | **3/3 PASS** |
| **L2** 撞闸后从诊断直接读出闸名与上限 | — | `max_routes` limit=3 ✅ | `max_routes` ✅ | PASS |
| **L3** 新字段误读 | 无 | 无 | 无 | PASS |

**通过门槛 = L0 且 L1 成立、L3 无新误读 → 达标。**

## L0：模型是否报出「只在 dry run 报告里存在」的余量

grill Q5 的判定口径——描述里有三闸默认值（100/200/300），所以「说出默认值」证明不了读了报告；必须问一个**只在报告里**的量。三次都答对：

- **Run 1**（`transcript-after1.log:39`）：
  > **展开后离 `max_nodes` 上限的余量 = 192**（declared 8 → graph_nodes 8 → expanded_nodes 8，auto_inserted 0，limit 200 → headroom 200 − 8 = **192**）
- **Run 2**（`transcript-after2.log:262-271`）：把 `node_budget` JSON 原样贴出（`headroom: 191`），并说明「干跑同时也确认了 `recursion_limit=100 / max_runs=300` 均未被 clamp」——**连 `limits` 三段式一起读对了**。
- **Run 3**（`transcript-after3.log:175-185`）：报 `headroom = 200 − 9 = 191`，**且是 `declared=5 / graph_nodes=5 / expanded_nodes=9`**——一次 foreach 展开出 4 项，模型准确报出「口径差值」。

## L1：口径区分（本 change 的核心）

最有力的证据是 **Run 3**：图里有一个 foreach 展开 4 项，于是 `graph_nodes=5`（图节点）而 `expanded_nodes=9`（含 4 个展开项）。模型**没有**把两者混为一谈，而是分别报出并解释了差值。若没有本 change，这两个数都不存在，模型无从判断「这张图离上限多远」。

## L2：撞闸诊断结构化可见（Run 2 的真实用例）

Run 2 的一张 probe 图撞了 `max_routes`，报告的 `diagnostics` 结构化报出（`transcript-after2.log:315`）：

```json
"diagnostics": {"reason": "max_routes",
                "message": "GraphRecursionError: route node 'gate' exceeded max_routes 3",
                "limit": 3, "current_nodes": ["gate"], ...}
```

**这在本 change 之前是拿不到的**——dry run 报告此前没有 `diagnostics` 字段，闸门原因只在散文式 `warnings[]` 里。模型直接读到闸名 `max_routes` 与上限 `3`。

## L3：负面检查（是否引入新误读）

逐条读三次 transcript 对新增字段的使用：`limits`（三段式）、`node_budget`（6 个字段）、route 的 `max_routes` / `gate_count`、`diagnostics`（含空 `{}` 与撞闸两种情况）。**未发现把 `declared` 当 `applied`、把 `headroom` 当动态闸余量、把 `gate_count` 与 `runs:0` 当矛盾、或把非空 `diagnostics` 当撞闸的误读。** `notes` 的四段口径说明被实际读到并正确复述。

## 如实记录：探针数不是 0（非本 change 指标）

沿用 #273 的探针口径（「只为验证语义、不含业务目标」的一次性声明）：

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| 探针 `probe:` 前缀 | 0 | 6 | 0 |
| `graph_recursion_exceeded` | 0 | 5 | 3 |

Run 2 的 6 条探针与 5 次超限，与 #273 改后（6/7/4）**同量级**——属**运行期拓扑语义探索**，不属本 change 的 L 指标（本 change 只负责让闸门可见）。**如实记录，不作为本 change 的达标依据，也不作为退步**（本 change 未触及探针激励面）。

## 关键结论

> **本 change 的命题兑现：模型现在能在撞闸前报出「这张图展开后离 max_nodes 还剩多少」，并在撞闸后直接读到闸名与上限。** 三次可复现，且 Run 3 的 foreach 展开用例证明它报的是**闸门口径**（9）而非图节点数（5）——这正是 design D2 与 grill 实测要保证的口径。
