# agent/result.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from agent.message import ContentBlock

class StopReason(Enum):
    END_TURN = "end_turn"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"

@dataclass
class ToolCallMade:
    name: str
    arguments: dict
    result: Optional[str | list["ContentBlock"]] = None

@dataclass
class RunResult:
    content: str
    stop_reason: StopReason
    tool_calls_made: list[ToolCallMade]
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None
