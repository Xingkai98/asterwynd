"""工具描述契约：模型可见出口的诚实口径必须写在 description 上（Q2/Q7 拍板）。

变化 ``workflow-builtin-templates``：``completed``/``failed`` 是 **run 口径**（不是
subagent 口径），且模板 ``max_rounds`` 是**期望轮数**（受图级 ``recursion_limit`` 约束）。
这两条必须落在**每个**返回含 ``completed``/``failed`` 的工具描述上，否则模型按旧口径
读会误判。本模块用 description 文本断言把该义务钉住（防实现漂移）。

四个出口（R3 实测）：``RunWorkflow`` / ``StartWorkflow`` / ``GetWorkflow`` /
``RunWorkflowAsset``（后者返回权威 ``_envelope()``，非 bounded，但字段同名同源）。
"""
import pytest

from agent.tools.builtin.subagents import (
    GetWorkflowTool,
    RunWorkflowAssetTool,
    RunWorkflowTool,
    StartWorkflowTool,
)

_RUN_SEMANTICS = "RUNS, not subagents"

#: 四个返回含 completed/failed 的模型可见出口。
_RUN_COUNT_EXITS = [RunWorkflowTool, StartWorkflowTool, GetWorkflowTool, RunWorkflowAssetTool]


@pytest.mark.parametrize("tool", _RUN_COUNT_EXITS, ids=lambda t: t.__name__)
def test_run_count_semantics_documented(tool):
    # tool_parameters 装饰器把 description 存进 ``cls.description``（见 agent/tools/base.py）。
    assert _RUN_SEMANTICS in tool.description


#: 模板 ``max_rounds`` 量纲警告只需出现在「能收到 template/params」的出口上。
_MAX_ROUNDS_EXITS = [RunWorkflowTool, RunWorkflowAssetTool, StartWorkflowTool]


@pytest.mark.parametrize("tool", _MAX_ROUNDS_EXITS, ids=lambda t: t.__name__)
def test_max_rounds_dimension_documented(tool):
    desc = tool.description
    assert "max_rounds" in desc
    assert "recursion_limit" in desc
    # 诚实必须落在错误里：截断诊断字段须点名
    assert "declared_max_rounds" in desc
    assert "rounds_actually_run" in desc
