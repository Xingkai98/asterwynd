from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Question:
    question_id: str
    title: str          # Short label (max 80 chars)
    body: str           # Detailed question, markdown supported
    options: list[str]  # Empty = free text input

    def to_event_data(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "title": self.title,
            "body": self.body,
            "options": self.options,
        }


@dataclass(frozen=True)
class QuestionAnswer:
    question_id: str
    answer: str


class QuestionHandler(Protocol):
    async def ask_question(self, question: Question) -> QuestionAnswer:
        ...


class FailClosedQuestionHandler:
    async def ask_question(self, question: Question) -> QuestionAnswer:
        return QuestionAnswer(
            question_id=question.question_id,
            answer="[Error: user questions are not available in this runtime]",
        )
