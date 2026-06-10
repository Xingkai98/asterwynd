# agent/memory/manager.py
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.llm import LLM
    from agent.message import Message

logger = logging.getLogger("myagent.memory")

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:
    def _count_tokens(text: str) -> int:
        return len(text) // 4

class MemoryManager:
    def __init__(
        self,
        max_tokens: int = 100_000,
        recent_window: int = 10,
        llm: Optional["LLM"] = None,
    ):
        self.messages: list["Message"] = []
        self.max_tokens = max_tokens
        self.recent_window = recent_window
        self.llm = llm

    def add(self, message: "Message") -> None:
        self.messages.append(message)

    def count_tokens(self, messages: list["Message"]) -> int:
        return sum(_count_tokens(m.content) for m in messages)

    def compact_if_needed(self, messages: Optional[list["Message"]] = None) -> None:
        msgs = messages if messages is not None else self.messages
        total = self.count_tokens(msgs)
        if total > self.max_tokens:
            logger.info(f"[Memory] {total} tokens > {self.max_tokens} budget, compacting")
            self.compact(msgs)

    def compact(self, messages: Optional[list["Message"]] = None) -> None:
        msgs = messages if messages is not None else self.messages
        system = [m for m in msgs if m.role == "system"]
        non_system = [m for m in msgs if m.role != "system"]
        recent = self._recent_with_tool_chains(non_system)
        middle = non_system[: max(0, len(non_system) - len(recent))]

        if not middle:
            msgs[:] = system + recent
            logger.info(f"[Memory] Compacted to {len(msgs)} messages")
            return

        if self.llm is None:
            msgs[:] = system + recent
            logger.info(f"[Memory] Compacted to {len(msgs)} messages (no LLM)")
            return

        msgs[:] = system + recent
        logger.info(f"[Memory] Compacted to {len(msgs)} messages")

    def _recent_with_tool_chains(self, messages: list["Message"]) -> list["Message"]:
        if self.recent_window <= 0:
            return []

        start = max(0, len(messages) - self.recent_window)
        while start > 0:
            expanded = False
            for index in range(start, len(messages)):
                message = messages[index]
                if message.role != "tool" or not message.tool_call_id:
                    continue
                assistant_index = self._find_tool_call_assistant(messages, message.tool_call_id, before=index)
                if assistant_index is not None and assistant_index < start:
                    start = assistant_index
                    expanded = True
                    break
            if not expanded:
                break
        return messages[start:]

    def _find_tool_call_assistant(
        self,
        messages: list["Message"],
        tool_call_id: str,
        before: int,
    ) -> Optional[int]:
        for index in range(before - 1, -1, -1):
            message = messages[index]
            if message.role != "assistant":
                continue
            if any(getattr(tool_call, "id", None) == tool_call_id for tool_call in message.tool_calls):
                return index
        return None

    def get_messages(self) -> list["Message"]:
        return self.messages

    def clear(self) -> None:
        self.messages = [m for m in self.messages if m.role == "system"]
