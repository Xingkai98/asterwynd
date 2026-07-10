from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from agent.llm import LLMResponse, LLMStreamEvent
from agent.message import Message


@dataclass(frozen=True)
class LLMCall:
    method: str
    messages: list[Message]
    tools: list[dict] | None
    model: str


@dataclass(frozen=True)
class StreamScript:
    events: list[LLMStreamEvent]


ScriptStep = LLMResponse | StreamScript | Exception


class ScriptedLLM:
    """Deterministic LLM test harness that consumes scripted responses in order."""

    def __init__(
        self,
        responses: Iterable[ScriptStep] | None = None,
        *,
        default_response: LLMResponse | None = None,
        model: str = "scripted-test-model",
        stream: bool = False,
    ) -> None:
        self.responses = list(responses or [])
        self.default_response = default_response or LLMResponse(
            content="default response",
            stop_reason="end_turn",
        )
        self.model = model
        self.stream = stream
        self.calls: list[LLMCall] = []
        self.closed = False
        self._next_index = 0

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def last_messages(self) -> list[Message] | None:
        if not self.calls:
            return None
        return self.calls[-1].messages

    @property
    def messages_seen(self) -> list[list[Message]]:
        return [call.messages for call in self.calls]

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        model: str = "gpt-4",
    ) -> LLMResponse:
        self._record_call("chat", messages, tools, model)
        step = self._consume_step()
        if isinstance(step, Exception):
            raise step
        if isinstance(step, StreamScript):
            return self._response_from_stream_script(step)
        return step

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        model: str = "gpt-4",
    ):
        self._record_call("stream_chat", messages, tools, model)
        step = self._consume_step()
        if isinstance(step, Exception):
            raise step
        if isinstance(step, StreamScript):
            for event in step.events:
                yield event
            return

        content = step.content or ""
        if content:
            yield LLMStreamEvent(
                type="assistant_delta",
                delta=content,
                content=content,
            )
        yield LLMStreamEvent(
            type="complete",
            content=content,
            stop_reason=step.stop_reason,
            response=step,
        )

    async def close(self) -> None:
        self.closed = True

    def _record_call(
        self,
        method: str,
        messages: list[Message],
        tools: list[dict] | None,
        model: str,
    ) -> None:
        self.calls.append(
            LLMCall(
                method=method,
                messages=list(messages),
                tools=list(tools) if tools is not None else None,
                model=model,
            )
        )

    def _consume_step(self) -> ScriptStep:
        if self._next_index >= len(self.responses):
            return self.default_response
        step = self.responses[self._next_index]
        self._next_index += 1
        return step

    def _response_from_stream_script(self, script: StreamScript) -> LLMResponse:
        for event in reversed(script.events):
            if event.type == "complete":
                if event.response is not None:
                    return event.response
                return LLMResponse(
                    content=event.content,
                    stop_reason=event.stop_reason,
                )
        content = "".join(event.delta for event in script.events)
        return LLMResponse(content=content, stop_reason="end_turn")


def stream_script(
    *deltas: str,
    content: str | None = None,
    stop_reason: str = "end_turn",
    response: LLMResponse | None = None,
    extra_events: Iterable[LLMStreamEvent] | None = None,
) -> StreamScript:
    events: list[LLMStreamEvent] = []
    current = ""
    for delta in deltas:
        current = f"{current}{delta}"
        events.append(
            LLMStreamEvent(
                type="assistant_delta",
                delta=delta,
                content=current,
            )
        )
    if extra_events:
        events.extend(extra_events)
    final_content = content if content is not None else current
    final_response = response or LLMResponse(
        content=final_content,
        stop_reason=stop_reason,
    )
    events.append(
        LLMStreamEvent(
            type="complete",
            content=final_content,
            stop_reason=final_response.stop_reason,
            response=final_response,
        )
    )
    return StreamScript(events)


def tool_response(
    *,
    tool_calls: list[Any],
    content: str | None = None,
    stop_reason: str = "tool_calls",
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
    )
