from typer.testing import CliRunner

import cli
from agent.memory.manager import MemoryManager
from agent.openai_llm import OpenAILLM
from agent.result import RunResult, StopReason, ToolCallMade
from agent.skills import Skill, SkillRuntime


class FakeAgent:
    def __init__(self, content="mock response", tool_calls_made=None, skill_runtime=None):
        self.llm = type("FakeLLM", (), {"model": "fake-model"})()
        self.max_iterations = None
        self.messages = None
        self.content = content
        self.tool_calls_made = tool_calls_made or []
        self.session_ids = []
        self.run_ids = []
        self.plan_document = None
        self.current_mode = "build"
        self.mode_changes = []
        self.memory = MemoryManager()
        self.skill_runtime = skill_runtime

    async def run(self, messages, session_id=None, run_id=None):
        self.messages = messages
        self.session_ids.append(session_id)
        self.run_ids.append(run_id)
        return RunResult(
            content=self.content,
            stop_reason=StopReason.END_TURN,
            tool_calls_made=self.tool_calls_made,
        )

    async def set_mode(
        self,
        mode,
        *,
        source,
        reason=None,
        on_event=None,
        trace_recorder=None,
        session_id=None,
        run_id=None,
    ):
        if mode == "bypass":
            raise ValueError("bypass mode is reserved for internal use")
        old_mode = self.current_mode
        self.current_mode = mode
        transition = {
            "old_mode": old_mode,
            "new_mode": mode,
            "source": source,
        }
        if reason is not None:
            transition["reason"] = reason
        if session_id is not None:
            transition["session_id"] = session_id
        if run_id is not None:
            transition["run_id"] = run_id
        self.mode_changes.append(transition)
        if on_event:
            await on_event("mode_changed", transition)
        return transition


class StreamingFakeAgent(FakeAgent):
    async def run(self, messages, on_event=None, session_id=None, run_id=None):
        self.messages = messages
        self.session_ids.append(session_id)
        self.run_ids.append(run_id)
        if on_event:
            await on_event("assistant_delta", {"delta": "Hel", "content": "Hel"})
            await on_event("assistant_delta", {"delta": "lo", "content": "Hello"})
            await on_event("assistant_stream_complete", {"content": "Hello", "stop_reason": "end_turn"})
            await on_event("llm_response", {"content": "Hello", "streamed": True})
        return RunResult(
            content="Hello",
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


def test_build_llm_enables_streaming_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("ASTERWYND_STREAMING", raising=False)

    llm = cli.build_llm("openai")

    assert isinstance(llm, OpenAILLM)
    assert llm.stream is True


def test_build_llm_allows_disabling_streaming(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ASTERWYND_STREAMING", "disabled")

    llm = cli.build_llm("openai")

    assert llm.stream is False


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


def test_cli_single_prompt_streams_delta_without_reprinting_final_content(monkeypatch):
    fake = StreamingFakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(cli.app, ["main", "hello"])

    assert result.exit_code == 0
    assert "Hello" in result.stdout
    assert result.stdout.count("Hello") == 1
    assert "【Agent】" not in result.stdout


def test_cli_single_prompt_summarizes_long_tool_results(monkeypatch):
    fake = FakeAgent(
        tool_calls_made=[
            ToolCallMade(
                name="Bash",
                arguments={"cmd": "generate"},
                result="x" * 5000,
            )
        ]
    )
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(cli.app, ["main", "hello"])

    assert result.exit_code == 0
    assert "【工具调用】1 次" in result.stdout
    assert "Bash" in result.stdout
    assert "摘要" in result.stdout
    assert "5000 字符" in result.stdout
    assert "完整结果" in result.stdout


def test_cli_single_prompt_prints_plan_document(monkeypatch):
    fake = FakeAgent(content="计划已生成。")
    fake.plan_document = {
        "title": "Add plan mode",
        "markdown": "# Add plan mode\n\n- Read docs",
    }
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(cli.app, ["main", "hello", "--mode", "plan"])

    assert result.exit_code == 0
    assert "【Plan Document】" in result.stdout
    assert "# Add plan mode" in result.stdout
    assert "计划已生成。" in result.stdout


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


def test_cli_interactive_prints_asterwynd_banner(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="exit\n",
    )

    assert result.exit_code == 0
    assert "Navigate by stars. Prove with traces." in result.stdout
    assert "以星为引，变更有证。" in result.stdout
    assert "Asterwynd 交互模式" in result.stdout


def test_cli_interactive_can_suppress_banner(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive", "--no-banner"],
        input="exit\n",
    )

    assert result.exit_code == 0
    assert "Navigate by stars. Prove with traces." not in result.stdout
    assert "以星为引，变更有证。" not in result.stdout
    assert "Asterwynd 交互模式" in result.stdout


def test_cli_single_prompt_does_not_print_asterwynd_banner(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(cli.app, ["main", "hello"])

    assert result.exit_code == 0
    assert "Navigate by stars. Prove with traces." not in result.stdout
    assert "以星为引，变更有证。" not in result.stdout


def test_cli_interactive_mode_command_changes_session_mode(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_session_id", lambda: "session-interactive")
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-1")

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="/mode read_only\nhello\nexit\n",
    )

    assert result.exit_code == 0
    assert "Mode changed: build -> read_only" in result.stdout
    assert fake.mode_changes == [
        {
            "old_mode": "build",
            "new_mode": "read_only",
            "source": "cli",
            "session_id": "session-interactive",
        }
    ]
    assert [message.content for message in fake.messages if message.role == "user"] == [
        "hello"
    ]


def test_cli_interactive_mode_command_rejects_bypass(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="/mode bypass\nexit\n",
    )

    assert result.exit_code == 0
    assert "bypass" in result.stdout
    assert fake.current_mode == "build"
    assert fake.mode_changes == []


def test_cli_interactive_help_command_does_not_run_agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-1")

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="/help\nexit\n",
    )

    assert result.exit_code == 0
    assert "/help" in result.stdout
    assert "/clear" in result.stdout
    assert "Run ID: run-1" not in result.stdout
    assert fake.run_ids == []


def test_cli_interactive_slash_exit_exits_without_running_agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-1")

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="/exit\n",
    )

    assert result.exit_code == 0
    assert "再见！" in result.stdout
    assert "Run ID: run-1" not in result.stdout
    assert fake.run_ids == []


def test_cli_interactive_status_command_prints_local_state(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_session_id", lambda: "session-interactive")
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-1")

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive", "--provider", "openai"],
        input="/status\nexit\n",
    )

    assert result.exit_code == 0
    assert "Session ID: session-interactive" in result.stdout
    assert "Mode: build" in result.stdout
    assert "Provider: openai" in result.stdout
    assert "Model: fake-model" in result.stdout
    assert "Run ID: run-1" not in result.stdout


def test_cli_interactive_unknown_slash_command_is_not_sent_to_agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-1")

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="/unknown\nexit\n",
    )

    assert result.exit_code == 0
    assert "Unknown command: /unknown" in result.stdout
    assert "Run ID: run-1" not in result.stdout
    assert fake.messages is None


def test_cli_interactive_clear_removes_previous_user_history(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    run_ids = iter(["run-1", "run-2"])
    monkeypatch.setattr(cli, "new_run_id", lambda: next(run_ids))

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="first\n/clear\nsecond\nexit\n",
    )

    assert result.exit_code == 0
    assert "Cleared conversation history." in result.stdout
    assert "Run ID: run-1" in result.stdout
    assert "Run ID: run-2" in result.stdout
    assert [message.content for message in fake.messages if message.role == "user"] == [
        "second"
    ]


def test_cli_interactive_compact_reports_noop_without_running_agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-1")

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="/compact\nexit\n",
    )

    assert result.exit_code == 0
    assert "Nothing to compact" in result.stdout
    assert "Run ID: run-1" not in result.stdout
    assert fake.run_ids == []


def test_cli_interactive_skill_command_queues_activation_and_runs_agent(monkeypatch):
    runtime = SkillRuntime(skills=[
        Skill(
            name="code-review",
            description="审查代码变更",
            prompt="Review instructions",
            tools=[],
            argument_hint="<request>",
            user_invocable=True,
        )
    ])
    fake = FakeAgent(skill_runtime=runtime)
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda model=None, provider="openai", mode="build", config=None: fake,
    )
    monkeypatch.setattr(cli, "new_run_id", lambda: "run-skill")

    result = CliRunner().invoke(
        cli.app,
        ["main", "--interactive"],
        input="/code-review 帮我审一下这个 change\nexit\n",
    )

    assert result.exit_code == 0
    assert "Activated skill: code-review" in result.stdout
    assert "Run ID: run-skill" in result.stdout
    runtime.begin_run("帮我审一下这个 change")
    assert runtime.activations == [
        {"skill_name": "code-review", "source": "slash_command"}
    ]
    assert fake.messages is not None
    user_messages = [message.content for message in fake.messages if message.role == "user"]
    assert user_messages == ["帮我审一下这个 change"]


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
    config_path = tmp_path / "asterwynd.yaml"
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
    config_path = tmp_path / "asterwynd.yaml"
    config_path.write_text("agent:\n  default_mode: plan\n", encoding="utf-8")
    monkeypatch.setenv("ASTERWYND_MODE", "read_only")

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
    config_path = tmp_path / "asterwynd.yaml"
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
    monkeypatch.delenv("ASTERWYND_MODEL", raising=False)

    result = CliRunner().invoke(cli.app, ["main", "hello", "--provider", "openai"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY not set" in result.stderr
