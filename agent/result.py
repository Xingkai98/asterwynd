# agent/result.py
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class StopReason(Enum):
    END_TURN = "end_turn"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"

@dataclass
class ToolCallMade:
    name: str
    arguments: dict
    result: Optional[str] = None

@dataclass
class RunResult:
    content: str
    stop_reason: StopReason
    tool_calls_made: list[ToolCallMade]
    total_tokens: int = 0
    error: Optional[str] = None
