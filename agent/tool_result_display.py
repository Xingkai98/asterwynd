from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MAX_RESULT_CHARS = 4000
DEFAULT_MAX_RESULT_LINES = 80
DEFAULT_PREVIEW_CHARS = 1200
DEFAULT_COLLAPSED_TOOLS = ("WebFetch",)


@dataclass(frozen=True)
class ToolResultDisplayConfig:
    max_result_chars: int = DEFAULT_MAX_RESULT_CHARS
    max_result_lines: int = DEFAULT_MAX_RESULT_LINES
    preview_chars: int = DEFAULT_PREVIEW_CHARS


@dataclass(frozen=True)
class ToolResultDisplaySummary:
    collapsed: bool
    preview: str
    char_count: int
    line_count: int

    def to_dict(self) -> dict:
        return {
            "collapsed": self.collapsed,
            "preview": self.preview,
            "char_count": self.char_count,
            "line_count": self.line_count,
        }


def summarize_tool_result(
    tool_name: str,
    result: str,
    config: ToolResultDisplayConfig | None = None,
) -> ToolResultDisplaySummary:
    config = config or ToolResultDisplayConfig()
    char_count = len(result)
    line_count = _line_count(result)
    collapsed = (
        tool_name in DEFAULT_COLLAPSED_TOOLS
        or char_count > config.max_result_chars
        or line_count > config.max_result_lines
    )
    preview = result[:config.preview_chars] if collapsed else result
    return ToolResultDisplaySummary(
        collapsed=collapsed,
        preview=preview,
        char_count=char_count,
        line_count=line_count,
    )


def _line_count(text: str) -> int:
    if text == "":
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)
