from pathlib import Path

import pytest

from agent.config import ConfigError, ConfigOverrides, load_config
from agent.run_config import AgentMode


def test_load_config_uses_defaults_when_yaml_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("MYAGENT_MODE", raising=False)
    monkeypatch.delenv("MYAGENT_BENCHMARK_PARALLEL", raising=False)

    config = load_config(start_dir=tmp_path)

    assert config.agent.default_mode is AgentMode.BUILD
    assert config.tools.ignore_patterns == ()
    assert config.tools.command_denylist == ()
    assert config.tools.code_intelligence.tree_sitter_max_file_bytes == 262144
    assert config.tools.web_search.providers == ()
    assert config.tools.display.max_result_chars == 4000
    assert config.tools.display.max_result_lines == 80
    assert config.tools.display.preview_chars == 1200
    assert config.benchmark.parallel == 1
    assert config.benchmark.timeout_seconds == 600


def test_load_config_reads_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("MYAGENT_MODE", raising=False)
    (tmp_path / "myagent.yaml").write_text(
        """
agent:
  default_mode: plan
modes:
  build:
    deny_tools:
      - Bash
tools:
  ignore_patterns:
    - .cache
  command_denylist:
    - dangerous-cmd
  code_intelligence:
    tree_sitter_max_file_bytes: 1234
  web_search:
    providers:
      - tavily
      - name: brave
        enabled: false
      - duckduckgo-html
  display:
    max_result_chars: 2000
    max_result_lines: 40
    preview_chars: 600
benchmark:
  parallel: 3
  timeout_seconds: 42
""",
        encoding="utf-8",
    )

    config = load_config(start_dir=tmp_path)

    assert config.agent.default_mode is AgentMode.PLAN
    assert config.mode_config(AgentMode.BUILD).deny_tools == ("Bash",)
    assert config.tools.ignore_patterns == (".cache",)
    assert config.tools.command_denylist == ("dangerous-cmd",)
    assert config.tools.code_intelligence.tree_sitter_max_file_bytes == 1234
    assert config.tools.web_search.providers[0].name == "tavily"
    assert config.tools.web_search.providers[0].enabled is True
    assert config.tools.web_search.providers[1].name == "brave"
    assert config.tools.web_search.providers[1].enabled is False
    assert config.tools.web_search.providers[2].name == "duckduckgo-html"
    assert config.tools.web_search.providers[2].enabled is True
    assert config.tools.display.max_result_chars == 2000
    assert config.tools.display.max_result_lines == 40
    assert config.tools.display.preview_chars == 600
    assert config.benchmark.parallel == 3
    assert config.benchmark.timeout_seconds == 42


def test_environment_overrides_yaml_for_supported_fields(tmp_path, monkeypatch):
    (tmp_path / "myagent.yaml").write_text(
        """
agent:
  default_mode: plan
benchmark:
  parallel: 2
  timeout_seconds: 30
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYAGENT_MODE", "read_only")
    monkeypatch.setenv("MYAGENT_BENCHMARK_PARALLEL", "4")
    monkeypatch.setenv("MYAGENT_BENCHMARK_TIMEOUT", "90")

    config = load_config(start_dir=tmp_path)

    assert config.agent.default_mode is AgentMode.READ_ONLY
    assert config.benchmark.parallel == 4
    assert config.benchmark.timeout_seconds == 90


def test_cli_overrides_environment_and_yaml(tmp_path, monkeypatch):
    (tmp_path / "myagent.yaml").write_text(
        """
agent:
  default_mode: plan
benchmark:
  parallel: 2
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYAGENT_MODE", "read_only")
    monkeypatch.setenv("MYAGENT_BENCHMARK_PARALLEL", "4")

    config = load_config(
        start_dir=tmp_path,
        cli_overrides=ConfigOverrides(
            default_mode="build",
            benchmark_parallel=5,
        ),
    )

    assert config.agent.default_mode is AgentMode.BUILD
    assert config.benchmark.parallel == 5


def test_explicit_config_path_must_exist(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(config_path=tmp_path / "missing.yaml")


def test_invalid_yaml_fails_fast(tmp_path):
    (tmp_path / "myagent.yaml").write_text("agent: [", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(start_dir=tmp_path)


def test_discovers_yaml_from_child_until_git_root(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "myagent.yaml").write_text(
        "agent:\n  default_mode: plan\n",
        encoding="utf-8",
    )
    child = tmp_path / "src" / "pkg"
    child.mkdir(parents=True)

    config = load_config(start_dir=child)

    assert config.path == tmp_path / "myagent.yaml"
    assert config.agent.default_mode is AgentMode.PLAN


def test_discovery_stops_at_git_root(tmp_path):
    parent = tmp_path / "parent"
    repo = parent / "repo"
    child = repo / "src"
    child.mkdir(parents=True)
    (parent / "myagent.yaml").write_text(
        "agent:\n  default_mode: plan\n",
        encoding="utf-8",
    )
    (repo / ".git").mkdir()

    config = load_config(start_dir=child)

    assert config.path is None
    assert config.agent.default_mode is AgentMode.BUILD


def test_tool_strategy_environment_variables_are_not_config_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAGENT_IGNORE_PATTERNS", "env_cache")
    monkeypatch.setenv("MYAGENT_COMMAND_DENYLIST", "env-danger")

    config = load_config(start_dir=tmp_path)

    assert config.tools.ignore_patterns == ()
    assert config.tools.command_denylist == ()


def test_invalid_tool_display_config_fails_fast(tmp_path, monkeypatch):
    monkeypatch.delenv("MYAGENT_MODE", raising=False)
    (tmp_path / "myagent.yaml").write_text(
        """
tools:
  display:
    max_result_chars: 0
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="tools.display.max_result_chars"):
        load_config(start_dir=tmp_path)


def test_invalid_code_intelligence_config_fails_fast(tmp_path):
    (tmp_path / "myagent.yaml").write_text(
        """
tools:
  code_intelligence:
    tree_sitter_max_file_bytes: 0
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="tools.code_intelligence.tree_sitter_max_file_bytes",
    ):
        load_config(start_dir=tmp_path)


def test_invalid_web_search_provider_config_fails_fast(tmp_path):
    (tmp_path / "myagent.yaml").write_text(
        """
tools:
  web_search:
    providers:
      - name: brave
        enabled: "yes"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"tools\.web_search\.providers\[0\]\.enabled"):
        load_config(start_dir=tmp_path)


def test_unknown_web_search_provider_fails_fast(tmp_path):
    (tmp_path / "myagent.yaml").write_text(
        """
tools:
  web_search:
    providers:
      - name: brve
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unsupported search provider"):
        load_config(start_dir=tmp_path)
