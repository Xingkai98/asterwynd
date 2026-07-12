# tests/agent/context/test_builder.py
"""Unit tests for ContextBuilder: registration, sorting, rendering, and truncation."""
import pytest
from agent.context.protocol import BuildContext, ContextSource
from agent.context.builder import ContextBuilder
from agent.run_config import AgentMode


class FakeSource:
    """Test ContextSource with configurable behavior."""
    def __init__(self, name: str, priority: int, content: str = "",
                 budget: int = 1000, critical: bool = False):
        self.name = name
        self.priority = priority
        self._content = content
        self.budget = budget
        self.critical = critical
        self.render_called = False

    async def render(self, context: BuildContext) -> str:
        self.render_called = True
        return self._content


def make_context(cwd: str = "/tmp/test", mode: AgentMode = AgentMode.BUILD,
                 context_window: int = 100_000, total_budget: int = 20_000) -> BuildContext:
    return BuildContext(cwd=cwd, mode=mode, context_window=context_window,
                        total_budget=total_budget)


class TestContextBuilderRegistration:
    """2.1: registration and sorting."""

    async def test_registers_and_sorts_by_priority(self):
        builder = ContextBuilder(total_budget=20_000)
        s3 = FakeSource(name="P3", priority=3, content="THREE")
        s0 = FakeSource(name="P0", priority=0, content="ZERO", critical=True)
        s5 = FakeSource(name="P5", priority=5, content="FIVE")
        builder.register(s3)
        builder.register(s0)
        builder.register(s5)
        ctx = make_context()

        result = await builder.build(ctx)
        # P0, P3, P5 order; P5 is lowest priority
        assert result.index("ZERO") < result.index("THREE") < result.index("FIVE")

    async def test_same_priority_registration_order_wins(self):
        builder = ContextBuilder(total_budget=20_000)
        s_a = FakeSource(name="A", priority=2, content="first")
        s_b = FakeSource(name="B", priority=2, content="second")
        builder.register(s_a)
        builder.register(s_b)
        ctx = make_context()

        result = await builder.build(ctx)
        assert result.index("first") < result.index("second")


class TestContextBuilderRendering:
    """2.1: rendering and separator."""

    async def test_build_renders_all_sources(self):
        builder = ContextBuilder(total_budget=20_000)
        builder.register(FakeSource(name="P0", priority=0, content="sys", critical=True))
        builder.register(FakeSource(name="P4", priority=4, content="skill"))
        ctx = make_context()

        result = await builder.build(ctx)
        assert "sys" in result
        assert "skill" in result

    async def test_empty_source_render_excluded(self):
        builder = ContextBuilder(total_budget=20_000)
        builder.register(FakeSource(name="P0", priority=0, content="sys", critical=True))
        builder.register(FakeSource(name="P4", priority=4, content=""))
        ctx = make_context()

        result = await builder.build(ctx)
        # Empty sources are not included
        assert result == "sys"

    async def test_layer_separator_between_sources(self):
        builder = ContextBuilder(total_budget=20_000)
        builder.register(FakeSource(name="P0", priority=0, content="sys", critical=True))
        builder.register(FakeSource(name="P4", priority=4, content="skill"))
        ctx = make_context()

        result = await builder.build(ctx)
        assert "---" in result

    async def test_no_trailing_separator_on_single_source(self):
        builder = ContextBuilder(total_budget=20_000)
        builder.register(FakeSource(name="P0", priority=0, content="sys", critical=True))
        ctx = make_context()

        result = await builder.build(ctx)
        assert result == "sys"


class TestContextBuilderTruncation:
    """2.2-2.4: budget overflow and truncation."""

    async def test_p0_never_truncated(self):
        """2.2: P0 layer never truncated."""
        builder = ContextBuilder(total_budget=50)  # Very tight budget
        p0_content = "IMPORTANT_SYSTEM_PROMPT"
        p5_content = "x" * 1000  # Way over budget
        builder.register(FakeSource(name="P0", priority=0, content=p0_content,
                                    budget=30, critical=True))
        builder.register(FakeSource(name="P5", priority=5, content=p5_content,
                                    budget=900))
        ctx = make_context()

        result = await builder.build(ctx)
        assert "IMPORTANT_SYSTEM_PROMPT" in result  # P0 survives

    async def test_truncation_starts_from_lowest_priority(self):
        """2.3: when budget overflows, truncate from P5 (lowest priority)."""
        builder = ContextBuilder(total_budget=100)
        builder.register(FakeSource(name="P2", priority=2, content="P2_DATA",
                                    budget=50))
        builder.register(FakeSource(name="P4", priority=4, content="P4_DATA",
                                    budget=80))
        builder.register(FakeSource(name="P5", priority=5, content="P5_DATA",
                                    budget=200))
        ctx = make_context()

        result = await builder.build(ctx)
        # P5 should be truncated first (lowest priority)
        assert "P2_DATA" in result
        assert "P4_DATA" in result

    async def test_truncation_from_tail_of_layer(self):
        """2.3: truncation preserves the beginning of a layer (earlier content
        may be more important), cuts from the tail."""
        builder = ContextBuilder(total_budget=60)
        # Content where the important part is at the beginning
        content = "HEAD_CRITICAL_INFO " + "body " * 100 + "TAIL_EXPENDABLE"
        builder.register(FakeSource(name="P5", priority=5, content=content,
                                    budget=200))
        ctx = make_context()

        result = await builder.build(ctx)
        # Head is preserved, tail is cut
        assert "HEAD_CRITICAL_INFO" in result
        assert "TAIL_EXPENDABLE" not in result

    async def test_budget_respected(self):
        """2.3: result fits within budget."""
        builder = ContextBuilder(total_budget=100)
        builder.register(FakeSource(name="P0", priority=0, content="short",
                                    budget=10, critical=True))
        builder.register(FakeSource(name="P4", priority=4, content="data " * 100,
                                    budget=200))
        ctx = make_context()

        result = await builder.build(ctx)
        # Rough check: result shouldn't be wildly over budget
        # 100 tokens ≈ 400 chars (chars/4 estimate); allow margin
        assert len(result) < 600


class TestSetBudget:
    """2.1: set_budget updates total budget."""

    async def test_set_budget_updates_limit(self):
        builder = ContextBuilder(total_budget=20_000)
        builder.set_budget(30)
        builder.register(FakeSource(name="P0", priority=0, content="KEEP",
                                    budget=10, critical=True))
        builder.register(FakeSource(name="P5", priority=5, content="HUGE " * 100,
                                    budget=500))
        ctx = make_context()

        result = await builder.build(ctx)
        # With 30-token budget, P5 gets heavily truncated
        assert len(result) < 200


class TestRenderErrorHandling:
    """Error handling: render failures skip the source, don't block pipeline."""

    async def test_render_error_skipped_others_rendered(self):
        class FailingSource:
            name = "Failing"
            priority = 3
            budget = 100
            critical = False

            async def render(self, context: BuildContext) -> str:
                raise RuntimeError("disk read error")

        builder = ContextBuilder(total_budget=20_000)
        builder.register(FakeSource(name="P0", priority=0, content="sys",
                                    critical=True))
        builder.register(FailingSource())
        builder.register(FakeSource(name="P4", priority=4, content="skill"))
        ctx = make_context()

        result = await builder.build(ctx)
        assert "sys" in result
        assert "skill" in result
        # Failing source is simply absent from the result


class TestBuildContextFields:
    """BuildContext carries environment-level info used by sources."""

    async def test_build_context_visible_to_sources(self):
        ctx_values = {}

        class InspectingSource:
            name = "Inspector"
            priority = 0
            budget = 100
            critical = True

            async def render(self, context: BuildContext) -> str:
                ctx_values["cwd"] = context.cwd
                ctx_values["mode"] = context.mode
                ctx_values["context_window"] = context.context_window
                return "ok"

        builder = ContextBuilder(total_budget=500)
        builder.register(InspectingSource())
        ctx = make_context(cwd="/home/user/project", mode=AgentMode.PLAN,
                          context_window=200_000)

        await builder.build(ctx)
        assert ctx_values["cwd"] == "/home/user/project"
        assert ctx_values["mode"] == AgentMode.PLAN
        assert ctx_values["context_window"] == 200_000
