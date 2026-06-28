from __future__ import annotations

from dataclasses import dataclass

from agent.message import Message, system_message
from benchmarks.task_schema import TaskSpec


CODING_SYSTEM_PROMPT = """You are Asterwynd running as a local coding agent.

Work only inside the provided repository workspace. Inspect files before making
changes when context is needed. Prefer the Edit tool for precise code changes.
Use Write only for new files; do not use Write to modify existing files.
Use InspectGitDiff after meaningful edits. Keep changes scoped to the task.
Do not modify .git, .env files, secrets, caches, or benchmark run artifacts.
When finished, summarize the changed files and whether validation was run.
"""


@dataclass(frozen=True)
class CodingPromptBuilder:
    system_prompt: str = CODING_SYSTEM_PROMPT

    def build_messages(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: str,
    ) -> list[Message]:
        user_prompt = f"""Repository workspace:
{workspace}

Task:
{problem_statement.strip()}

Validation command (run this after making changes):
{task.test_command}

Requirements:
- Modify only files inside the workspace.
- Keep the change scoped to the task.
- Use tools for repository inspection and edits.
- Use Edit for existing files and Write only for new files.
- Do not rely on hidden reference or evaluator-only files.
- Do not create or modify tests unless the task explicitly asks for tests.
- Before the final answer, inspect the diff if you made changes.
"""
        return [
            system_message(self.system_prompt),
            Message(role="user", content=user_prompt),
        ]
