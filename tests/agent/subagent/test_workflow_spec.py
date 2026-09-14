"""Workflow DSL 数据结构与 schema 校验（change ``workflow-dsl-scheduler``，D2/D5/D6）。

对应 tasks 1.1 / 1.2：

- 节点/边模型（subagent/aggregate/route/foreach + channel/required/reducer），
- 非法环（不含 route 的环）、未知节点、重复 id、超 max_nodes、
  多入边写同槽无 reducer、best_effort 缺 deadline_s → reject。
"""
import pytest

from agent.subagent.workflow import (
    REDUCERS,
    WorkflowSpec,
    WorkflowValidationError,
    parse_workflow_spec,
)


def _spec(**overrides) -> dict:
    base = {
        "schema_version": "workflow.v1",
        "goal": "research",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {
                "id": "join",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
            },
        ],
        "edges": [
            {"from": "a", "to": "join", "channel": "summary", "reducer": "concat"},
            {"from": "b", "to": "join", "channel": "summary", "reducer": "concat"},
        ],
    }
    base.update(overrides)
    return base


# --- 1.1 节点/边模型 ---


def test_parses_fan_out_fan_in_spec():
    spec = parse_workflow_spec(_spec())
    assert isinstance(spec, WorkflowSpec)
    assert spec.goal == "research"
    assert [node.id for node in spec.nodes] == ["a", "b", "join"]
    assert spec.node("join").kind == "aggregate"
    assert spec.node("join").join == "all_required"
    edge = spec.edge_between("a", "join")
    assert edge is not None
    assert edge.channel == "summary"
    assert edge.reducer == "concat"
    assert edge.required is True  # 默认 required


def test_entry_and_terminal_derived_when_omitted():
    spec = parse_workflow_spec(_spec())
    assert spec.entry == ("a", "b")
    assert spec.terminal == ("join",)


def test_spec_round_trips_through_dict():
    spec = parse_workflow_spec(_spec())
    again = parse_workflow_spec(spec.to_dict())
    assert again.to_dict() == spec.to_dict()
    assert again.spec_hash == spec.spec_hash


def test_spec_hash_is_stable_and_content_addressed():
    one = parse_workflow_spec(_spec())
    two = parse_workflow_spec(_spec())
    other = parse_workflow_spec(_spec(goal="other"))
    assert one.spec_hash == two.spec_hash
    assert one.spec_hash != other.spec_hash


def test_reducer_enum_is_restricted():
    assert REDUCERS == ("concat", "merge_dict", "first_non_empty", "last")
    with pytest.raises(WorkflowValidationError, match="reducer"):
        parse_workflow_spec(
            _spec(
                edges=[
                    {"from": "a", "to": "join", "reducer": "__import__('os')"},
                    {"from": "b", "to": "join", "reducer": "concat"},
                ]
            )
        )


# --- 1.2 schema 校验 ---


def test_rejects_duplicate_node_id():
    bad = _spec(
        nodes=[
            {"id": "a", "kind": "subagent", "task": "t"},
            {"id": "a", "kind": "subagent", "task": "t2"},
        ],
        edges=[],
    )
    with pytest.raises(WorkflowValidationError, match="duplicate node id"):
        parse_workflow_spec(bad)


def test_rejects_unknown_node_in_edge():
    bad = _spec(edges=[{"from": "a", "to": "ghost", "reducer": "concat"}])
    with pytest.raises(WorkflowValidationError, match="unknown node"):
        parse_workflow_spec(bad)


def test_rejects_unknown_node_kind():
    bad = _spec(
        nodes=[{"id": "a", "kind": "telepathy", "task": "t"}],
        edges=[],
    )
    with pytest.raises(WorkflowValidationError, match="kind"):
        parse_workflow_spec(bad)


def test_rejects_unknown_spec_field():
    bad = _spec()
    bad["loop"] = True
    with pytest.raises(WorkflowValidationError, match="unknown spec field"):
        parse_workflow_spec(bad)


def test_rejects_cycle_without_route_node():
    """环上必须有 route 节点提供条件出口 + max_routes 上限，否则是死循环。"""
    bad = _spec(
        nodes=[
            {"id": "a", "kind": "subagent", "task": "t"},
            {"id": "b", "kind": "subagent", "task": "t"},
        ],
        edges=[
            {"from": "a", "to": "b"},
            {"from": "b", "to": "a"},
        ],
    )
    with pytest.raises(WorkflowValidationError, match="cycle"):
        parse_workflow_spec(bad)


def test_accepts_cycle_through_route_node():
    spec = parse_workflow_spec(
        _spec(
            nodes=[
                {"id": "producer", "kind": "subagent", "task": "draft"},
                {"id": "reviewer", "kind": "subagent", "task": "review"},
                {
                    "id": "gate",
                    "kind": "route",
                    "task": "route on the review verdict",
                    "cases": [{"when": "APPROVED", "to": "join"}],
                    "default": "producer",
                    "max_routes": 3,
                },
                {
                    "id": "join",
                    "kind": "aggregate",
                    "join": "all_required",
                    "strategy": "collect",
                },
            ],
            entry=["producer"],
            edges=[
                {"from": "producer", "to": "reviewer"},
                {"from": "reviewer", "to": "gate"},
                {"from": "gate", "to": "join"},
                {"from": "gate", "to": "producer"},
                {"from": "producer", "to": "join", "reducer": "concat"},
                {"from": "reviewer", "to": "join", "reducer": "concat"},
            ],
        )
    )
    assert spec.entry == ("producer",)
    assert spec.node("gate").max_routes == 3
    assert spec.node("gate").cases[0].when == "APPROVED"
    assert spec.node("gate").cases[0].to == "join"


def test_rejects_too_many_nodes():
    nodes = [{"id": f"n{i}", "kind": "subagent", "task": "t"} for i in range(5)]
    bad = _spec(nodes=nodes, edges=[], max_nodes=3)
    with pytest.raises(WorkflowValidationError, match="max_nodes"):
        parse_workflow_spec(bad, default_max_nodes=3)


def test_rejects_multi_writer_slot_without_reducer():
    """D5：并行分支写同一结果槽必须声明 reducer。"""
    bad = _spec(
        edges=[
            {"from": "a", "to": "join"},
            {"from": "b", "to": "join"},
        ]
    )
    with pytest.raises(WorkflowValidationError, match="reducer"):
        parse_workflow_spec(bad)


def test_rejects_conflicting_reducers_on_same_slot():
    bad = _spec(
        edges=[
            {"from": "a", "to": "join", "reducer": "concat"},
            {"from": "b", "to": "join", "reducer": "last"},
        ]
    )
    with pytest.raises(WorkflowValidationError, match="reducer"):
        parse_workflow_spec(bad)


def test_same_source_edges_do_not_require_reducer():
    """同一 route 节点的两条出边写同一槽不算「多入边」，无需 reducer。"""
    spec = parse_workflow_spec(
        _spec(
            nodes=[
                {"id": "a", "kind": "subagent", "task": "t"},
                {
                    "id": "gate",
                    "kind": "route",
                    "cases": [{"when": "YES", "to": "x"}],
                    "default": "y",
                    "max_routes": 1,
                },
                {"id": "x", "kind": "subagent", "task": "x"},
                {"id": "y", "kind": "subagent", "task": "y"},
            ],
            edges=[
                {"from": "a", "to": "gate"},
                {"from": "gate", "to": "x"},
                {"from": "gate", "to": "y"},
            ],
        )
    )
    assert spec.node("gate").kind == "route"


def test_rejects_best_effort_without_deadline():
    bad = _spec(
        nodes=[
            {"id": "a", "kind": "subagent", "task": "t"},
            {"id": "b", "kind": "subagent", "task": "t"},
            {"id": "join", "kind": "aggregate", "join": "best_effort"},
        ],
        edges=[
            {"from": "a", "to": "join", "reducer": "concat"},
            {"from": "b", "to": "join", "reducer": "concat"},
        ],
    )
    with pytest.raises(WorkflowValidationError, match="deadline_s"):
        parse_workflow_spec(bad)


def test_best_effort_with_deadline_is_accepted():
    spec = parse_workflow_spec(
        _spec(
            nodes=[
                {"id": "a", "kind": "subagent", "task": "t"},
                {"id": "b", "kind": "subagent", "task": "t"},
                {
                    "id": "join",
                    "kind": "aggregate",
                    "join": "best_effort",
                    "deadline_s": 2.5,
                },
            ],
            edges=[
                {"from": "a", "to": "join", "reducer": "concat"},
                {"from": "b", "to": "join", "reducer": "concat"},
            ],
        )
    )
    assert spec.node("join").deadline_s == 2.5


def test_rejects_foreach_without_collection():
    bad = _spec(
        nodes=[{"id": "fan", "kind": "foreach", "task": "do {item}"}],
        edges=[],
    )
    with pytest.raises(WorkflowValidationError, match="foreach"):
        parse_workflow_spec(bad)


def test_rejects_foreach_with_both_items_and_source():
    bad = _spec(
        nodes=[
            {"id": "a", "kind": "subagent", "task": "t"},
            {
                "id": "fan",
                "kind": "foreach",
                "task": "do {item}",
                "items": ["x"],
                "source": "a",
                "source_field": "results",
            },
        ],
        edges=[{"from": "a", "to": "fan"}],
    )
    with pytest.raises(WorkflowValidationError, match="foreach"):
        parse_workflow_spec(bad)


def test_rejects_route_with_unknown_target():
    bad = _spec(
        nodes=[
            {"id": "a", "kind": "subagent", "task": "t"},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "YES", "to": "ghost"}],
                "default": "a",
                "max_routes": 1,
            },
        ],
        edges=[{"from": "a", "to": "gate"}],
    )
    with pytest.raises(WorkflowValidationError, match="route"):
        parse_workflow_spec(bad)


def test_rejects_subagent_node_without_task():
    bad = _spec(nodes=[{"id": "a", "kind": "subagent"}], edges=[])
    with pytest.raises(WorkflowValidationError, match="task"):
        parse_workflow_spec(bad)


def test_spec_level_limits_override_defaults():
    spec = parse_workflow_spec(_spec(recursion_limit=7, max_runs=11))
    assert spec.recursion_limit == 7
    assert spec.max_runs == 11
    assert spec.max_nodes == 200  # 默认沿用三闸默认值
