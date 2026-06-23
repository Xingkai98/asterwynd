from agent.tool_result_display import (
    ToolResultDisplayConfig,
    summarize_tool_result,
)


def test_webfetch_is_collapsed_by_default_even_when_short():
    summary = summarize_tool_result(
        "WebFetch",
        "short page",
        ToolResultDisplayConfig(
            max_result_chars=4000,
            max_result_lines=80,
            preview_chars=1200,
        ),
    )

    assert summary.collapsed is True
    assert summary.preview == "short page"
    assert summary.char_count == len("short page")
    assert summary.line_count == 1


def test_non_webfetch_collapses_when_threshold_exceeded():
    result = "line\n" * 81

    summary = summarize_tool_result(
        "Bash",
        result,
        ToolResultDisplayConfig(
            max_result_chars=4000,
            max_result_lines=80,
            preview_chars=20,
        ),
    )

    assert summary.collapsed is True
    assert summary.preview == result[:20]
    assert summary.char_count == len(result)
    assert summary.line_count == 81


def test_short_non_webfetch_result_is_not_collapsed():
    summary = summarize_tool_result(
        "Read",
        "hello",
        ToolResultDisplayConfig(
            max_result_chars=4000,
            max_result_lines=80,
            preview_chars=1200,
        ),
    )

    assert summary.collapsed is False
    assert summary.preview == "hello"
