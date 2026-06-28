from agent.config import SearchProviderConfig, WebSearchConfig
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tools.factory import build_coding_tool_registry, build_default_tool_registry


def _schema_names(registry):
    return {schema["function"]["name"] for schema in registry.get_all_schemas()}


def test_build_default_tool_registry_uses_build_mode_by_default():
    names = _schema_names(build_default_tool_registry())

    assert "Bash" in names
    assert "Write" in names
    assert "Edit" in names


def test_build_default_tool_registry_filters_read_only_mode():
    registry = build_default_tool_registry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    )

    names = _schema_names(registry)

    assert "Read" in names
    assert "Grep" in names
    assert "WebSearch" in names
    assert "WebFetch" in names
    assert "Bash" not in names
    assert "Write" not in names
    assert "Edit" not in names


def test_build_default_tool_registry_passes_web_search_config(monkeypatch):
    monkeypatch.setenv("ASTERWYND_TAVILY_API_KEY", "secret")
    monkeypatch.setenv("ASTERWYND_BRAVE_SEARCH_API_KEY", "secret")

    registry = build_default_tool_registry(
        web_search_config=WebSearchConfig(
            providers=(
                SearchProviderConfig(name="tavily"),
                SearchProviderConfig(name="brave"),
                SearchProviderConfig(name="duckduckgo-html"),
            )
        )
    )

    web_search = registry.get_tool("WebSearch")

    assert [provider.name for provider in web_search._registry.providers] == [
        "tavily",
        "brave",
        "duckduckgo-html",
    ]


def test_build_coding_tool_registry_filters_plan_mode():
    registry = build_coding_tool_registry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
    )

    names = _schema_names(registry)

    assert "Read" in names
    assert "InspectGitDiff" in names
    assert "ListFiles" in names
    assert "Find" in names
    assert "Bash" not in names
    assert "Write" not in names
    assert "Edit" not in names
