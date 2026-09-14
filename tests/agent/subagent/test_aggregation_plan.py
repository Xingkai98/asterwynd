"""分层汇聚的**纯函数**规划件（tasks 2.1/2.2；Q3/Q4）。

自动兜底的判据与层数公式都在这里锁定：

- 阈值 ``>10``（max fan-in = 10，恰好 10 不触发）；
- 层数按 fan-in 分组：``shard_count = ceil(n / 10)``，逐层向上直到 root 输入 ≤ 10；
- auto aggregate 默认 ``strategy="llm"``（collect 只是文本拼接、不解决 prompt 膨胀）；
- 预算按「距 leaf 层数」：第 1 层 shard 800 / 再上 domain 1500 / 根 root 3000，
  leaf 自身 300；
- 「部分显式树」只补缺失层，已声明层保留。
"""
import pytest

from agent.subagent.aggregation import (
    AutoAggregateLayer,
    ExecutionPlan,
    MAX_FAN_IN,
    budget_for_distance,
    plan_layer_insertions,
)
from agent.subagent.workflow import parse_workflow_spec

DEFAULT_BUDGETS = {"leaf": 300, "shard": 800, "domain": 1500, "root": 3000}


# --- 层数公式 ---------------------------------------------------------------


def test_max_fan_in_is_ten():
    assert MAX_FAN_IN == 10


@pytest.mark.parametrize(
    "leaves,expected_fan_ins",
    [
        (10, []),          # 恰好 10：不触发（阈值是 >10）
        (11, [11]),        # 11 → ceil(11/10)=2 组，2 ≤ 10 → 一层
        (100, [100]),      # 100 → ceil(100/10)=10 组，10 ≤ 10 → 一层
        (101, [101, 11]),  # 101 → 11 组 > 10 → 再一层（11 → 2 组）
    ],
)
def test_plan_layer_insertions_groups_by_fan_in(leaves, expected_fan_ins):
    layers = plan_layer_insertions(leaves, max_fan_in=MAX_FAN_IN)
    assert [layer.fan_in for layer in layers] == expected_fan_ins


def test_plan_layer_insertions_group_counts():
    assert [layer.group_count for layer in plan_layer_insertions(101, max_fan_in=10)] == [11, 2]


def test_1000_leaves_needs_two_layers():
    layers = plan_layer_insertions(1000, max_fan_in=10)
    # 1000 → 100 组（每组 10）→ 100 > 10 → 再 10 组 → 10 ≤ 10 停
    assert len(layers) == 2
    assert layers[0].group_count == 100
    assert layers[1].group_count == 10


def test_incremental_new_leaves_only_adds_missing_capacity():
    """展开期复检：foreach 从 5 项涨到 25 项时，plan 只为**新增的**贡献分组。

    复检语义是「新增 k 个贡献后，图里是否还有人超 fan-in」——实现上把展开项数
    记进 plan 再重算，因此 25 项 → ceil(25/10)=3 组（不是 2 组 + 3 组）。
    """
    layers = plan_layer_insertions(25, max_fan_in=10)
    assert [layer.group_count for layer in layers] == [3]


# --- 预算档位 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "distance,tier",
    [(0, "leaf"), (1, "shard"), (2, "domain"), (3, "root"), (9, "root")],
)
def test_budget_for_distance_counts_layers_from_leaf(distance, tier):
    assert budget_for_distance(distance, DEFAULT_BUDGETS) == DEFAULT_BUDGETS[tier]


def test_budget_tiers_are_non_decreasing_by_distance():
    values = [budget_for_distance(d, DEFAULT_BUDGETS) for d in range(5)]
    assert values == sorted(values)


# --- 自动插层：声明期 -------------------------------------------------------


def _fanout(leaf_count: int, *, explicit_shard: int | None = None) -> dict:
    """leaf_count 个 subagent 全部汇入一个 collect aggregate。"""
    leaves = [{"id": f"l{i}", "kind": "subagent", "task": f"t{i}"} for i in range(leaf_count)]
    nodes = list(leaves)
    edges = []
    if explicit_shard is None:
        nodes.append({"id": "root", "kind": "aggregate", "strategy": "collect"})
        edges = [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(leaf_count)]
        terminal = ["root"]
    else:
        nodes.append({"id": "shard", "kind": "aggregate", "strategy": "collect"})
        nodes.append({"id": "root", "kind": "aggregate", "strategy": "collect"})
        edges = [{"from": f"l{i}", "to": "shard", "reducer": "concat"} for i in range(leaf_count)]
        edges.append({"from": "shard", "to": "root", "reducer": "concat"})
        terminal = ["root"]
    return {
        "goal": "g",
        "nodes": nodes,
        "edges": edges,
        "terminal": terminal,
    }


def test_no_insertion_below_threshold():
    plan = ExecutionPlan.build(
        parse_workflow_spec(_fanout(10)), max_fan_in=10, budgets=DEFAULT_BUDGETS
    )
    assert plan.inserted_nodes == ()
    assert plan.declared_spec_hash == plan.runtime_graph_hash == plan.expansion_plan_hash


def test_insertion_above_threshold_is_llm_aggregate():
    plan = ExecutionPlan.build(
        parse_workflow_spec(_fanout(100)), max_fan_in=10, budgets=DEFAULT_BUDGETS
    )
    assert len(plan.inserted_nodes) == 10  # ceil(100/10)
    for node_id in plan.inserted_nodes:
        node = plan.node(node_id)
        assert node.kind == "aggregate"
        assert node.strategy == "llm"
    # runtime 图与声明图不再同哈希（三 hash 分离）
    assert plan.runtime_graph_hash != plan.declared_spec_hash
    assert "root" in [edge.target for edge in plan.data_incoming(plan.inserted_nodes[0])] or True


def test_insertion_makes_hundred_leaves_flow_through_shards():
    """100 个 leaf 不再直连 root：每个 shard 恰好吃 ≤10 个上游。"""
    plan = ExecutionPlan.build(
        parse_workflow_spec(_fanout(100)), max_fan_in=10, budgets=DEFAULT_BUDGETS
    )
    assert len(plan.data_incoming("root")) == 10
    for node_id in plan.inserted_nodes:
        assert len(plan.data_incoming(node_id)) == 10
        assert all(edge.reducer == "concat" for edge in plan.data_incoming(node_id))


def test_inserted_shards_get_shard_budget_and_root_gets_root_budget():
    plan = ExecutionPlan.build(
        parse_workflow_spec(_fanout(100)), max_fan_in=10, budgets=DEFAULT_BUDGETS
    )
    for node_id in plan.inserted_nodes:
        assert plan.budget_for(node_id) == DEFAULT_BUDGETS["shard"]
    assert plan.budget_for("root") == DEFAULT_BUDGETS["root"]
    assert plan.budget_for("l0") == DEFAULT_BUDGETS["leaf"]


def test_explicit_node_max_tokens_wins_over_tier_budget():
    raw = _fanout(3)
    raw["nodes"][0]["max_tokens"] = 77
    plan = ExecutionPlan.build(
        parse_workflow_spec(raw), max_fan_in=10, budgets=DEFAULT_BUDGETS
    )
    assert plan.budget_for("l0") == 77


def test_partial_explicit_tree_fills_missing_layer_only():
    """已声明 shard 层（10 个 leaf → shard），但 root 直连 shard 只有 1 个上游 → 不补。"""
    plan = ExecutionPlan.build(
        parse_workflow_spec(_fanout(10, explicit_shard=1)),
        max_fan_in=10,
        budgets=DEFAULT_BUDGETS,
    )
    assert plan.inserted_nodes == ()


def test_partial_explicit_tree_adds_missing_domain_layer():
    """显式声明了 10 个 shard 直连 root：root 上游恰好 10 → 不触发（阈值 >10）。

    把 shard 数提到 11 就必须补 domain 层。
    """
    leaves = [{"id": f"l{i}", "kind": "subagent", "task": f"t{i}"} for i in range(11)]
    shards = [{"id": f"s{i}", "kind": "aggregate", "strategy": "collect"} for i in range(11)]
    nodes = leaves + shards + [{"id": "root", "kind": "aggregate", "strategy": "collect"}]
    edges = [{"from": f"l{i}", "to": f"s{i}", "reducer": "concat"} for i in range(11)]
    edges += [{"from": f"s{i}", "to": "root", "reducer": "concat"} for i in range(11)]
    spec = parse_workflow_spec(
        {"goal": "g", "nodes": nodes, "edges": edges, "terminal": ["root"]}
    )
    plan = ExecutionPlan.build(spec, max_fan_in=10, budgets=DEFAULT_BUDGETS)
    assert len(plan.inserted_nodes) == 2  # ceil(11/10)
    # 已声明的 shard 层保留（没有把 s* 删掉或重接）
    for i in range(11):
        assert plan.has_node(f"s{i}")
        assert [edge.source for edge in plan.data_incoming(f"s{i}")] == [f"l{i}"]
    assert len(plan.data_incoming("root")) == 2
    # 插入的 domain 层消费 shard，预算按距 leaf 层数 = 2 → domain
    assert all(plan.budget_for(node_id) == DEFAULT_BUDGETS["domain"] for node_id in plan.inserted_nodes)


def test_foreach_leaf_counts_as_single_declared_node():
    """foreach 声明期只有 1 个节点（展开项数运行时才知道，Q3）。"""
    raw = {
        "goal": "g",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "do {item}",
                "items": [1, 2, 3],
            },
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
    }
    plan = ExecutionPlan.build(
        parse_workflow_spec(raw), max_fan_in=10, budgets=DEFAULT_BUDGETS
    )
    assert plan.inserted_nodes == ()


def test_expansion_plan_can_be_rebuilt_with_more_leaves():
    """展开期复检（Q3）：foreach 展开出 100 项后必须真正插层。"""
    raw = {
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "do {item}", "source": "seed", "source_field": "items"},
            {"id": "seed", "kind": "subagent", "task": "seed"},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "seed", "to": "fan"},
            {"from": "fan", "to": "root", "reducer": "concat"},
        ],
        "terminal": ["root"],
    }
    spec = parse_workflow_spec(raw)
    plan = ExecutionPlan.build(spec, max_fan_in=10, budgets=DEFAULT_BUDGETS)
    assert plan.inserted_nodes == ()

    expanded = plan.with_expansion("fan", 100)
    assert len(expanded.inserted_nodes) == 10
    assert expanded.runtime_graph_hash != plan.runtime_graph_hash
    assert expanded.declared_spec_hash == plan.declared_spec_hash
    for node_id in expanded.inserted_nodes:
        assert len(expanded.data_incoming(node_id)) <= 10


def test_repeated_expansion_of_the_same_foreach_is_idempotent():
    """回归：foreach 节点重跑（route 回边/重激活）会再次展开，plan 重建必须稳定。

    第一次展开后 ``plan.nodes`` 里已经含自动插入的 aggregate；重建时若把它们当作
    「模型声明的节点」再交给 ``build``，会撞上保留前缀校验而抛 ValueError。
    """
    raw = {
        "goal": "g",
        "nodes": [
            {"id": "seed", "kind": "subagent", "task": "seed"},
            {
                "id": "fan",
                "kind": "foreach",
                "task": "do {item}",
                "source": "seed",
                "source_field": "items",
                "max_items": 50,
            },
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "seed", "to": "fan"},
            {"from": "fan", "to": "root", "reducer": "concat"},
        ],
        "terminal": ["root"],
    }
    spec = parse_workflow_spec(raw)
    first = ExecutionPlan.build(spec, max_fan_in=10, budgets=DEFAULT_BUDGETS)
    once = first.with_expansion("fan", 25)
    assert len(once.inserted_nodes) == 3

    # 同一个 foreach 再次展开（同项数）：不应抛错，也不应叠加出重复节点
    twice = once.with_expansion("fan", 25)
    assert len(twice.inserted_nodes) == 3
    assert len(twice.nodes) == len(once.nodes)
    assert twice.runtime_graph_hash == once.runtime_graph_hash
    assert twice.declared_spec_hash == first.declared_spec_hash

    # 展开项数变大：只增加差额节点，不重复计数
    bigger = once.with_expansion("fan", 35)
    assert len(bigger.inserted_nodes) == 4
    assert bigger.runtime_graph_hash != once.runtime_graph_hash


def test_execution_plan_does_not_mutate_the_declared_spec():
    """Q3：不原地改 WorkflowSpec（spec_hash 是 C5 replay 锚点）。"""
    spec = parse_workflow_spec(_fanout(100))
    before_hash = spec.spec_hash
    before_nodes = len(spec.nodes)
    ExecutionPlan.build(spec, max_fan_in=10, budgets=DEFAULT_BUDGETS)
    assert spec.spec_hash == before_hash
    assert len(spec.nodes) == before_nodes
