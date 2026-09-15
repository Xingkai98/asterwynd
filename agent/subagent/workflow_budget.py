"""workflow 级四维度总预算账本（change ``workflow-budget-attribution``，D1/D2）。

设计口径来自 ``design.md`` D1/D2 与 ``reviews/grill-design.md`` 决策 2/7 及用户确认
Q4/Q5/Q6/Q11/Q14：

- **四维度**：tokens / cost_usd / runs / wall_time_s，任一维度 ``0`` = 该维度不限。
- **token/cost 记账点选 loop 层**（Q6 方案 B）：只有 ``agent/loop.py`` 的
  ``cost_ledger.record`` 同位置能同时拿到 ``response.usage`` 的 cache 四档——从
  ``SubagentRunRecord.usage`` 反算会系统性偏低（决策 3）。因此本模块只管**累加 +
  判定**，不管钩子挂载。
- **runs 维度复用调度器 ``self._runs``**（Q4）：另起计数器会在 foreach 预扣路径漂移。
  调度器在派发前调 :meth:`WorkflowBudget.reserve_runs`，超限抛
  :class:`WorkflowBudgetExceeded`。
- **超限是 stop_new（drain）语义，不是杀器**：token/cost/wall_time 超限不取消在跑
  run，只停止派发新节点。超限必须映射为 envelope，``WorkflowBudgetExceeded``
  **不得逃出** ``WorkflowScheduler.run()``——调度器在 ``_dispatch`` 捕获后置粘性
  ``budget_exceeded`` 状态，``run()`` 另有一层兜底 catch。

本模块只依赖 ``WorkflowBudgetConfig`` 与 ``cost_tracker``，不 import 调度器/manager
（避免循环依赖）；``WorkflowBudgetExceeded`` 只描述「哪一维、用到多少、上限多少」。
"""
from __future__ import annotations

import time

from agent.cost_tracker import compute_cost_cached

#: 四维度的固定顺序（诊断/测试依赖它的确定性）。
DIMENSIONS = ("tokens", "cost_usd", "runs", "wall_time_s")


class WorkflowBudgetExceeded(RuntimeError):
    """某一维度预算超限（区别于 ``GraphRecursionError`` 的结构闸）。

    **不得逃出 ``WorkflowScheduler.run()``**：调度器必须把它映射成
    ``stop_new`` + drain + ``status="budget_exceeded"`` 的 envelope（D1/D2）。
    """

    def __init__(self, dimension: str, used: float, limit: float) -> None:
        super().__init__(
            f"workflow budget exceeded ({dimension}): {used} > {limit}"
        )
        self.dimension = dimension
        self.used = used
        self.limit = limit

    def to_dict(self) -> dict:
        return {
            "reason": "budget_exceeded",
            "dimension": self.dimension,
            "used": self.used,
            "limit": self.limit,
            "message": str(self),
        }


class WorkflowBudget:
    """一个 workflow run 一份的四维度预算账本（``run()`` 创建、``_teardown()`` 结算）。

    与单 run 的 :class:`agent.subagent.budget.BudgetTracker` 是**两个层级**：
    ``BudgetTracker`` 管一个 run 的 ``max_tokens``/``max_time_s``（超限杀 run），
    本类管整张图的**总** token / cost / run 数 / 挂钟时间（超限只 stop_new）。
    """

    def __init__(self, config: object | None = None, *, started_at: float | None = None) -> None:
        self.max_tokens = int(getattr(config, "max_total_tokens", 200000))
        self.max_cost_usd = float(getattr(config, "max_total_cost_usd", 5.0))
        self.max_runs = int(getattr(config, "max_total_runs", 300))
        self.max_wall_time_s = float(getattr(config, "max_wall_time_s", 1800.0))
        self.started_at = time.time() if started_at is None else started_at
        #: 记账累加器（Q6 方案 B：由 loop 层的每次 LLM 调用驱动）。
        self.tokens = 0
        self.cost_usd = 0.0

    # -- 记账 ---------------------------------------------------------------

    def record_llm_call(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """累加一次 LLM 调用的 token / cost（cache 四档全算，Q12）。

        ``tokens`` 口径 = input + output（Q16：不含 cache）；``cost_usd`` 走
        :func:`compute_cost_cached`——未知模型按价表均值估算（``known=False``），
        绝不静默记 0。
        """
        self.tokens += int(input_tokens) + int(output_tokens)
        estimate = compute_cost_cached(
            model or "unknown",
            int(input_tokens),
            int(cache_read_tokens),
            int(cache_write_tokens),
            int(output_tokens),
        )
        self.cost_usd += estimate.cost

    # -- 判定 ---------------------------------------------------------------

    def exceeded_dimension(
        self, *, runs: int, now: float | None = None
    ) -> str | None:
        """返回**首个**超限维度名；全部在限内返回 ``None``。

        ``0`` 表示该维度不限（Q11）。``runs`` 由调度器传入（复用 ``self._runs``，
        Q4），本类不自己计数。
        """
        if self.max_tokens and self.tokens > self.max_tokens:
            return "tokens"
        if self.max_cost_usd and self.cost_usd > self.max_cost_usd:
            return "cost_usd"
        if self.max_runs and runs > self.max_runs:
            return "runs"
        if self.max_wall_time_s and self.wall_time_s(now=now) > self.max_wall_time_s:
            return "wall_time_s"
        return None

    def reserve_runs(self, runs_used: int) -> None:
        """派发前预扣 runs 维度（Q4：复用调度器的唯一计数器）。

        ``runs_used`` 是**预扣后**的累计值。超限抛 :class:`WorkflowBudgetExceeded`，
        由调度器捕获并转成 stop_new——异常不得继续上抛到 ``run()`` 之外。
        """
        if self.max_runs and runs_used > self.max_runs:
            raise WorkflowBudgetExceeded("runs", runs_used, self.max_runs)

    def wall_time_s(self, *, now: float | None = None) -> float:
        return max((time.time() if now is None else now) - self.started_at, 0.0)

    def dimensions(self, *, runs: int, now: float | None = None) -> dict:
        """四维度 ``{limit, used}`` 快照（D7 的 ``budget.dimensions``）。"""
        return {
            "tokens": {"limit": self.max_tokens, "used": self.tokens},
            "cost_usd": {
                "limit": self.max_cost_usd,
                "used": round(self.cost_usd, 9),
            },
            "runs": {"limit": self.max_runs, "used": runs},
            "wall_time_s": {
                "limit": self.max_wall_time_s,
                "used": round(self.wall_time_s(now=now), 6),
            },
        }
