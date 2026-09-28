"""P2: workflow 资产索引注入源（change ``workflow-asset-persistence``，Q4/Q9）。

只把「资产名 + 单行截断的 description」注入系统提示，并显式标注为**数据而非指令**
——这是本 change 最实质的提示注入面，因此注入的是受限最小面：不含 ``when_to_use``、
不含节点 ``task``、不含 spec 正文（完整内容走显式工具）。

两条硬性约束（照 grill Q9，不要照抄 ``MemoryIndexSource``）：

- ``cacheable = False``：``ContextBuilder`` 对 ``cacheable=True`` 的源**永不裁剪**
  （``builder.py`` 的 ``_find_trimmable_index`` 跳过 critical + cacheable）。资产会被
  ``SaveWorkflowAsset`` 在会话内改写，标成 cacheable 会让内容陈旧且**永久占据**
  系统提示、无法被预算裁掉。``MemoryIndexSource`` 是 ``cacheable=True``，与本 change
  **相反**。
- **只注入 root 会话**：子 agent loop 也走同一默认 builder，若不限制，这段文本会进入
  **每个子 agent** 的系统提示，token 与暴露面随并发度线性放大。构造期事实由
  ``AgentLoop(include_workflow_asset_index=...)`` 传入，不在渲染期推断环境。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from agent.context.protocol import BuildContext

if TYPE_CHECKING:
    from agent.subagent.manager import SubAgentManager


class WorkflowAssetIndexSource:
    """P2: bounded workflow-asset index (names + truncated descriptions)."""

    name = "WorkflowAssetIndex"
    priority = 2
    budget = 2000  # advisory；真闸是注入层总预算
    critical = False
    cacheable = False  # 可被预算裁剪（与 MemoryIndexSource 相反，见模块 docstring）

    def __init__(self, manager: "SubAgentManager | None" = None) -> None:
        self._manager = manager

    async def render(self, context: BuildContext) -> str:
        if self._manager is None:
            return ""
        # 延迟 import：``agent.context`` 不依赖资产层，反之亦然。
        from agent.subagent.workflow_assets import asset_store_for_manager, render_asset_index

        try:
            store = asset_store_for_manager(self._manager)
            listing = store.list_assets(limit=1000, offset=0)
        except Exception:  # noqa: BLE001 - 注入是尽力而为，坏库不该炸整轮上下文
            return ""
        if not listing["assets"]:
            return ""
        from agent.subagent.workflow_assets import WorkflowAsset

        assets = [
            WorkflowAsset(
                name=entry["name"],
                description=entry.get("description", ""),
                source=entry.get("source", "dsl"),
                spec_hash=entry.get("spec_hash", ""),
                node_count=entry.get("node_count", 0),
            )
            for entry in listing["assets"]
        ]
        return render_asset_index(assets)
