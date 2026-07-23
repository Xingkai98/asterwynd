from __future__ import annotations

import uuid

from agent.question import FailClosedQuestionHandler, Question, QuestionHandler
from agent.tools.base import Tool, tool_parameters


@tool_parameters(
    name="AskUserQuestion",
    description=(
        "Ask the user a question to gather requirements, clarify ambiguity, "
        "or request input. The agent pauses until the user responds."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short question label (max 80 chars)",
            },
            "body": {
                "type": "string",
                "description": "Detailed question body (markdown supported)",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Predefined answer choices. Empty array = free-text input.",
            },
        },
        "required": ["title", "body"],
    },
)
class AskUserQuestionTool(Tool):
    read_only = True
    parallelizable = False  # MUST be serial — blocks until user responds

    def __init__(self, question_handler: QuestionHandler | None = None) -> None:
        from agent.question import FailClosedQuestionHandler
        self._handler: QuestionHandler = question_handler or FailClosedQuestionHandler()

    async def execute(self, title: str = "", body: str = "", options: list[str] | None = None, **kwargs) -> str:
        options = options or []
        question = Question(
            question_id=str(uuid.uuid4()),
            title=title[:80] if title else "",
            body=body or "",
            options=options,
        )
        answer = await self._handler.ask_question(question)
        return answer.answer
