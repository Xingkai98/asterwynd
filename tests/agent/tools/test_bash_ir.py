"""IR contract tests for the single parse pipeline (design D1/D2, tasks 1.2/1.5-1.9).

These lock the shape of `BashAnalysis`: same semantics in different spellings
produce the same IR, and each field is asserted on its own (a whole-tree
comparison once hid a `file_redirect` extraction bug — it has two parent node
types).
"""
from __future__ import annotations

import pytest

from agent.tools.bash_ir import BashAnalysis, analyze, is_interpreter


class TestSegments:
    def test_simple_command(self) -> None:
        a = analyze("ls -la")
        assert [s.argv for s in a.segments] == [("ls", "-la")]
        assert a.segments[0].name == "ls"

    @pytest.mark.parametrize(
        "spelling",
        [
            "rm -rf /",
            "rm -fr /",
            "rm -r -f /",
            "rm -rf -- /",
        ],
    )
    def test_rm_flag_spellings_same_ir(self, spelling: str) -> None:
        a = analyze(spelling)
        assert len(a.segments) == 1
        assert a.segments[0].name == "rm"
        # flag order/spelling is preserved but the target is always "/"
        assert a.segments[0].argv[-1] == "/"

    def test_chain_splits_into_segments(self) -> None:
        a = analyze("cd /tmp && cp x y")
        assert [s.name for s in a.segments] == ["cd", "cp"]

    def test_newline_separated(self) -> None:
        a = analyze("cd /tmp\ncp evil a/.env")
        assert [s.name for s in a.segments] == ["cd", "cp"]

    def test_pipeline(self) -> None:
        a = analyze("cat f | grep x")
        assert [s.name for s in a.segments] == ["cat", "grep"]

    def test_grouping(self) -> None:
        a = analyze("(cp x .env)")
        assert [s.name for s in a.segments] == ["cp"]


class TestRedirects:
    def test_file_redirect_captured(self) -> None:
        a = analyze("echo x > /etc/passwd")
        assert [(r.op, r.target) for r in a.redirects] == [(">", "/etc/passwd")]

    def test_append_redirect(self) -> None:
        a = analyze("echo x >> .env")
        assert [(r.op, r.target) for r in a.redirects] == [(">>", ".env")]

    def test_redirect_from_redirected_statement_parent(self) -> None:
        """`file_redirect` has two parent shapes; both must be picked up."""
        a = analyze("cat < in.txt")
        assert [(r.op, r.target) for r in a.redirects] == [("<", "in.txt")]


class TestHeredoc:
    def test_heredoc_binding_to_interpreter(self) -> None:
        a = analyze("bash <<EOF\ncp x .env\nEOF\n")
        assert len(a.heredocs) == 1
        h = a.heredocs[0]
        assert h.delim == "EOF"
        assert "cp x .env" in h.body
        assert is_interpreter(h.owner) is True

    def test_heredoc_binding_to_non_interpreter(self) -> None:
        a = analyze("cat <<'EOF'\ncp x .env\nEOF\n")
        assert len(a.heredocs) == 1
        assert is_interpreter(a.heredocs[0].owner) is False

    def test_heredoc_body_is_not_a_segment(self) -> None:
        """The body is data — it must not produce top-level commands."""
        a = analyze("cat <<'EOF'\ncp x .env\nEOF\n")
        assert [s.name for s in a.segments] == ["cat"]


class TestErrorSignals:
    @pytest.mark.parametrize(
        "src",
        ["", "   ", "echo 'unclosed", "$(", "rm -rf !(keep)"],
    )
    def test_never_raises(self, src: str) -> None:
        a = analyze(src)          # must not raise
        assert isinstance(a, BashAnalysis)

    def test_missing_node_detected(self) -> None:
        a = analyze("rm -rf !(keep)")
        assert a.has_errors is True

    def test_argv_disabled_when_errors(self) -> None:
        """Malformed input must not leave garbage argv for an evaluator to trust.

        `echo x; rm -rf !(keep)` makes tree-sitter capture `['echo x', 'keep',
        'rm -rf !']` — the argv of a real command degrades to nonsense. The IR
        drops argv entirely in that case (design D1 constraint 2).
        """
        a = analyze("echo x; rm -rf !(keep)")
        assert a.has_errors is True
        garbage = {"keep", "rm -rf !"}
        for segment in a.segments:
            assert not (set(segment.argv) & garbage), (
                f"garbage argv leaked through on parse error: {segment.argv!r}"
            )

    def test_clean_input_keeps_argv(self) -> None:
        """Control group: the argv-disabling must not fire on well-formed input."""
        a = analyze("rm -rf /")
        assert a.has_errors is False
        assert [s.argv for s in a.segments] == [("rm", "-rf", "/")]

    def test_direct_construction_with_errors_clears_argv(self) -> None:
        """The invariant holds regardless of construction path (`__post_init__`)."""
        from agent.tools.bash_ir import Segment

        a = BashAnalysis(
            source="x",
            segments=[Segment(argv=("keep",), dynamic=False)],
            has_errors=True,
        )
        assert all(not s.argv for s in a.segments)

    def test_empty_is_clean(self) -> None:
        a = analyze("")
        assert a.has_errors is False
        assert a.segments == []


class TestDynamicWords:
    def test_variable_in_target(self) -> None:
        a = analyze("cp x $DST")
        assert a.segments[0].dynamic is True

    def test_plain_command_is_not_dynamic(self) -> None:
        a = analyze("cp x y")
        assert a.segments[0].dynamic is False

    def test_quoted_mention_not_dynamic_command(self) -> None:
        a = analyze('grep -rn "cp x .env" docs/')
        assert [s.name for s in a.segments] == ["grep"]


class TestBudget:
    def test_deep_arithmetic_does_not_recurse(self) -> None:
        """~2,000 chars of `$(( 1+1+… ))` must not blow Python's recursion.

        QueryCursor is used precisely so enumeration does not recurse (design D1).
        """
        src = "$(( " + " + ".join(["1"] * 1000) + " ))"
        a = analyze(src)          # must not raise RecursionError
        assert isinstance(a, BashAnalysis)

    def test_budget_hit_is_reported(self) -> None:
        src = "echo x\n" * 20000
        a = analyze(src)
        assert isinstance(a, BashAnalysis)
