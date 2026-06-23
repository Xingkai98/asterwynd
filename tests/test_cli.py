from typer.testing import CliRunner

import cli
from agent.result import RunResult, StopReason


class FakeAgent:
    def __init__(self, content="mock response"):
        self.llm = type("FakeLLM", (), {"model": "fake-model"})()
        self.max_iterations = None
        self.messages = None
        self.content = content
        self.session_ids = []
        self.run_ids = []

    async def run(self, messages, session_id=None, run_id=None):
        self.messages = messages
        self.session_ids.append(session_id)
        self.run_ids.append(run_id)
        return RunResult(
            content=self.content,
            stop_reason=StopReason.END_TURN,
            tool_calls_made=[],
        )


def test_cli_single_prompt_uses_mock_agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(cli.app, ["main", "hello", "--max-iterations", "3"])

    assert result.exit_code == 0
    assert "mock response" in result.stdout
    assert fake.max_iterations == 3
    assert fake.messages[-1].role == "user"
    assert fake.messages[-1].content == "hello"


def test_cli_single_prompt_prints_session_and_run_ids(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_session_id", lambda: "session-test")
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-test")

    result = CliRunner().invoke(cli.app, ["main", "hello"])

    assert result.exit_code == 0
    assert "Session ID: session-test" in result.stdout
    assert "Run ID: run-test" in result.stdout
    assert fake.session_ids == ["session-test"]
    assert fake.run_ids == ["run-test"]


def test_cli_interactive_reuses_session_id_and_prints_run_ids(monkeypatch):
    fake = FakeAgent()
    run_ids = iter(["run-1", "run-2"])
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_session_id", lambda: "session-interactive")
    monkeypatch.setattr(cli, "new_run_id", lambda: next(run_ids))

    result = CliRunner().invoke(
        cli.app,
        ["main", "hello", "--interactive"],
        input="again\nexit\n",
    )

    assert result.exit_code == 0
    assert result.stdout.count("Session ID: session-interactive") == 1
    assert "Run ID: run-1" in result.stdout
    assert "Run ID: run-2" in result.stdout
    assert fake.session_ids == ["session-interactive", "session-interactive"]
    assert fake.run_ids == ["run-1", "run-2"]


def test_cli_single_prompt_passes_normalized_mode(monkeypatch):
    fake = FakeAgent()
    captured = {}

    def build_agent(model=None, provider="openai", mode="build", config=None):
        captured["mode"] = mode
        return fake

    monkeypatch.setattr(cli, "build_agent", build_agent)

    result = CliRunner().invoke(cli.app, ["main", "hello", "--mode", "read-only"])

    assert result.exit_code == 0
    assert captured["mode"] == "read_only"


def test_cli_single_prompt_uses_yaml_default_mode(tmp_path, monkeypatch):
    fake = FakeAgent()
    captured = {}
    config_path = tmp_path / "myagent.yaml"
    config_path.write_text("agent:\n  default_mode: plan\n", encoding="utf-8")

    def build_agent(model=None, provider="openai", mode="build", config=None):
        captured["mode"] = mode
        captured["config"] = config
        return fake

    monkeypatch.setattr(cli, "build_agent", build_agent)

    result = CliRunner().invoke(
        cli.app,
        ["main", "hello", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert captured["mode"] == "plan"
    assert captured["config"].path == config_path


def test_cli_mode_overrides_env_and_yaml(tmp_path, monkeypatch):
    fake = FakeAgent()
    captured = {}
    config_path = tmp_path / "myagent.yaml"
    config_path.write_text("agent:\n  default_mode: plan\n", encoding="utf-8")
    monkeypatch.setenv("MYAGENT_MODE", "read_only")

    def build_agent(model=None, provider="openai", mode="build", config=None):
        captured["mode"] = mode
        return fake

    monkeypatch.setattr(cli, "build_agent", build_agent)

    result = CliRunner().invoke(
        cli.app,
        ["main", "hello", "--config", str(config_path), "--mode", "build"],
    )

    assert result.exit_code == 0
    assert captured["mode"] == "build"


def test_cli_rejects_bypass_mode():
    result = CliRunner().invoke(cli.app, ["main", "hello", "--mode", "bypass"])

    assert result.exit_code == 1
    assert "bypass" in result.stderr


def test_cli_reports_invalid_config(tmp_path):
    config_path = tmp_path / "myagent.yaml"
    config_path.write_text("agent: [", encoding="utf-8")

    result = CliRunner().invoke(
        cli.app,
        ["main", "hello", "--config", str(config_path)],
    )

    assert result.exit_code == 1
    assert "Invalid YAML" in result.stderr


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
