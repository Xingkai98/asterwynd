from typer.testing import CliRunner

import cli
from agent.result import RunResult, StopReason


class FakeAgent:
    def __init__(self, content="mock response"):
        self.max_iterations = None
        self.messages = None
        self.content = content

    async def run(self, messages):
        self.messages = messages
        return RunResult(
            content=self.content,
            stop_reason=StopReason.END_TURN,
            tool_calls_made=[],
        )


def test_cli_single_prompt_uses_mock_agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(cli, "build_agent", lambda model=None, provider="openai": fake)

    result = CliRunner().invoke(cli.app, ["main", "hello", "--max-iterations", "3"])

    assert result.exit_code == 0
    assert "mock response" in result.stdout
    assert fake.max_iterations == 3
    assert fake.messages[-1].role == "user"
    assert fake.messages[-1].content == "hello"


def test_cli_single_prompt_requires_prompt():
    result = CliRunner().invoke(cli.app, ["main"])

    assert result.exit_code == 1
    assert "PROMPT is required" in result.stderr


def test_cli_missing_openai_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MYAGENT_MODEL", raising=False)

    result = CliRunner().invoke(cli.app, ["main", "hello", "--provider", "openai"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY not set" in result.stderr
