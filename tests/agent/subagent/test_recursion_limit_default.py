"""图级 ``recursion_limit`` 默认值 25 → 100 的行为回归（change ``workflow-recursion-limit-default``）。

对应 tasks 2.3（核心回归 + 对照组）与 2.4（spec 三条 Scenario 的落地）。

**判据是 ``diagnostics.reason``，不是「跑完 / 没跑完」**。默认值改动若只断言
「某张循环图能跑完」，改前改后**都可能通过**，等于没有覆盖本 change 的核心行为。
故用同一张图、同一个显式 ``max_rounds``，断言新旧默认下 ``reason`` 不同：

- 旧默认（显式 ``recursion_limit=25``，对照组）→ ``reason == "recursion_limit"``；
- 新默认（默认 100，主组）→ ``reason == "max_routes"``。

对照组是防恒真的关键：它证明「这张图确实能触发旧默认」。否则未来任何让
superstep 记账失效的重构，都会让主断言静默恒真。

**N 的标定（实测，非照抄设计估算）**。探针实测 peer-review 拓扑（``compile_pattern
("peer-review")``，producer → reviewer → gate 三节点，gate 常回 ``producer`` 回边）：

    superstep 数 = 3 * max_rounds + 2

（每轮 producer / reviewer / gate 各派发一批 = 3 superstep，另加 entry 与终态两批；
``superstep/轮`` 收敛到 3.00，与 issues #262 的实测表逐字吻合。）据此：

- 下界：对照组触发需 ``3N + 2 > 25`` ⇒ ``N >= 8``（实测 ``N=8`` 起 ``limit=25``
  下 ``reason == "recursion_limit"``，``N=7`` 仍是 ``max_routes``）；
- 上界：主组不触需 ``3N + 2 < 100`` ⇒ ``N <= 32``；
- **编译期约束**：``compile_pattern`` 拒绝 ``max_rounds > DEFAULT_RECURSION_LIMIT``
  （``patterns.py`` 的 rounds 荒谬界），改前该界为 25，故 ``N <= 25`` 才能同时在
  改前改后编译通过。

取 **``N = 12``**（实测 38 superstep）：严格落在 (25, 100) 内，两侧都有余量，
且 12 <= 25 满足编译期界。
"""
from dataclasses import replace

import pytest

from agent.config import AsterwyndConfig, SubagentsConfig, WorkflowLimitsConfig, load_config
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import compile_pattern
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import DEFAULT_RECURSION_LIMIT
from agent.tools.builtin.subagents import parse_spec_for_manager
from agent.workspace_policy import WorkspacePolicy

#: 实测标定出的回归轮数（见模块 docstring）：38 superstep，严格落在 (25, 100) 内。
CALIBRATED_ROUNDS = 12
#: 标定轮数对应的实测 superstep 数（``3 * N + 2``），断言用。
CALIBRATED_SUPERSTEPS = 3 * CALIBRATED_ROUNDS + 2


class AlwaysCritiqueLLM:
    """peer-review 永不批准：route 的 ``max_routes`` 成为唯一自然终点。"""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        return LLMResponse(
            content="CRITIQUE needs work", stop_reason="end_turn", usage=Usage(5, 5)
        )


def _manager(tmp_path, config=None) -> SubAgentManager:
    return SubAgentManager(
        llm=AlwaysCritiqueLLM(),
        config=config or AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _peer_review(rounds: int, *, recursion_limit: int | None = None):
    spec = compile_pattern(
        "peer-review", task="write a proposal", params={"max_rounds": rounds}
    )
    if recursion_limit is None:
        return spec
    return replace(spec, recursion_limit=recursion_limit)


async def _run(tmp_path, spec, config=None) -> dict:
    manager = _manager(tmp_path, config)
    scheduler = WorkflowScheduler(manager)
    return await scheduler.run(spec)


# --- 2.3 核心回归 + 对照组 ---------------------------------------------------


@pytest.mark.asyncio
async def test_default_recursion_limit_lets_max_rounds_be_reached(tmp_path):
    """主组：默认配置（100）下跑满 12 轮，终点由 route 的 ``max_routes`` 决定。

    改前（默认 25）：38 superstep 的图会在第 25 步撞图级闸 ⇒ ``reason ==
    "recursion_limit"``，本断言失败。改后（默认 100）⇒ ``reason == "max_routes"``。
    """
    spec = _peer_review(CALIBRATED_ROUNDS)
    assert spec.recursion_limit == DEFAULT_RECURSION_LIMIT

    result = await _run(tmp_path, spec)

    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_routes"
    assert result["diagnostics"]["steps"] == CALIBRATED_SUPERSTEPS


@pytest.mark.asyncio
async def test_explicit_old_default_still_trips_the_graph_gate(tmp_path):
    """对照组：同图同 N，显式 ``recursion_limit=25`` 必须撞 ``recursion_limit``。

    这条断言证明「该图确实能触发旧默认」——没有它，主组断言在「superstep 记账
    失效」类重构下会静默恒真（防恒真机制）。
    """
    spec = _peer_review(CALIBRATED_ROUNDS, recursion_limit=25)

    result = await _run(tmp_path, spec)

    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "recursion_limit"
    assert result["diagnostics"]["recursion_limit"] == 25
    # 旧默认下确实跑不满标定轮数（证明该图跨度 > 25 superstep）。
    assert result["diagnostics"]["steps"] < CALIBRATED_SUPERSTEPS


# --- 2.4 spec 三条 Scenario 的落地 ------------------------------------------


@pytest.mark.asyncio
async def test_unconfigured_default_does_not_truncate_iterative_task(tmp_path):
    """Scenario「默认配置不掐断迭代式任务」：未显式配置时超过旧默认 25、未到 100。"""
    spec = _peer_review(12)  # 38 superstep ∈ (25, 100)
    result = await _run(tmp_path, spec)
    assert result["diagnostics"]["reason"] == "max_routes"
    assert result["diagnostics"]["reason"] != "recursion_limit"
    assert result["diagnostics"]["steps"] > 25


@pytest.mark.asyncio
async def test_explicit_smaller_recursion_limit_still_applies(tmp_path, monkeypatch):
    """Scenario「显式更小的 recursion_limit 仍精确生效」：配置 7 → 按 7 报错。

    走真实的配置生效路径 ``parse_spec_for_manager``（``DeclareWorkflow`` /
    ``RunWorkflow`` 共用），模板图未声明 ``recursion_limit``，故取配置值 7。
    """
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    (tmp_path / "asterwynd.yaml").write_text(
        "subagents:\n  workflow:\n    recursion_limit: 7\n", encoding="utf-8"
    )
    config = load_config(start_dir=tmp_path)
    assert config.subagents.workflow.recursion_limit == 7

    raw = _peer_review(12).to_dict()  # 模板图不声明该键
    assert "recursion_limit" not in raw
    manager = _manager(tmp_path, config)
    spec = parse_spec_for_manager(manager, raw)
    assert spec.recursion_limit == 7

    result = await WorkflowScheduler(manager).run(spec)

    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "recursion_limit"
    assert result["diagnostics"]["recursion_limit"] == 7


@pytest.mark.asyncio
async def test_declared_above_config_is_not_raised(tmp_path):
    """``_eff_limit`` 的 min 方向不变：spec 声明高于配置时不抬高到声明值。"""
    config = AsterwyndConfig(
        subagents=SubagentsConfig(
            workflow=WorkflowLimitsConfig(recursion_limit=7, max_nodes=200, max_runs=300)
        )
    )
    spec = parse_spec_for_manager(_manager(tmp_path, config), _raw_loop_spec())
    assert spec.recursion_limit == 7


def _raw_loop_spec() -> dict:
    return {
        "goal": "loop",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "draft"},
            {
                "id": "gate",
                "kind": "route",
                "task": "route",
                "cases": [{"when": "APPROVED", "to": "done"}],
                "default": "producer",
                "max_routes": 50,
            },
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "entry": ["producer"],
        "edges": [
            {"from": "producer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
    }
