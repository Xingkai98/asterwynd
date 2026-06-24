from __future__ import annotations

from agent.code_intelligence.config import CodeIntelligenceConfig
from agent.code_intelligence.repo_map import build_repo_map, format_repo_map, search_symbols
from agent.tools.base import Tool, tool_parameters
from agent.workspace_policy import WorkspacePolicy


@tool_parameters(
    name="RepoMap",
    description="生成工作区的只读仓库结构摘要，用于快速理解源码、测试、配置和可提取符号。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "扫描起始路径。默认为工作区根目录。",
                "default": ".",
            },
            "max_files": {
                "type": "number",
                "description": "最大返回文件数，默认 200，上限 500。",
                "default": 200,
            },
        },
        "required": [],
    },
)
class RepoMapTool(Tool):
    read_only = True

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        ignore_patterns: tuple[str, ...] = (),
        code_intelligence_config: CodeIntelligenceConfig | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.ignore_patterns = ignore_patterns
        self.code_intelligence_config = code_intelligence_config or CodeIntelligenceConfig()

    async def execute(self, path: str = ".", max_files: int = 200, **kwargs) -> str:
        try:
            repo_map = build_repo_map(
                policy=self.policy,
                path=path,
                ignore_patterns=self.ignore_patterns,
                max_files=min(int(max_files), 500),
                code_intelligence_config=self.code_intelligence_config,
            )
        except (FileNotFoundError, PermissionError) as exc:
            return f"Error: {exc}"
        return format_repo_map(repo_map)


@tool_parameters(
    name="SymbolSearch",
    description="在工作区只读搜索可提取代码符号，返回已支持语言的 class、function、method 等结构化符号。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "符号名称查询。空字符串返回前几个可提取符号。",
                "default": "",
            },
            "path": {
                "type": "string",
                "description": "扫描起始路径。默认为工作区根目录。",
                "default": ".",
            },
            "max_results": {
                "type": "number",
                "description": "最大返回符号数，默认 50，上限 200。",
                "default": 50,
            },
        },
        "required": [],
    },
)
class SymbolSearchTool(Tool):
    read_only = True

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        ignore_patterns: tuple[str, ...] = (),
        code_intelligence_config: CodeIntelligenceConfig | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.ignore_patterns = ignore_patterns
        self.code_intelligence_config = code_intelligence_config or CodeIntelligenceConfig()

    async def execute(
        self,
        query: str = "",
        path: str = ".",
        max_results: int = 50,
        **kwargs,
    ) -> str:
        try:
            repo_map = build_repo_map(
                policy=self.policy,
                path=path,
                ignore_patterns=self.ignore_patterns,
                max_files=500,
                code_intelligence_config=self.code_intelligence_config,
            )
        except (FileNotFoundError, PermissionError) as exc:
            return f"Error: {exc}"

        results = search_symbols(
            repo_map,
            query=query,
            max_results=min(int(max_results), 200),
        )
        if not results:
            return f"(no symbols matching {query!r})"
        return "\n".join(
            f"{file_summary.path}:{symbol.line} {symbol.kind} {symbol.name}"
            + (
                ""
                if symbol.source == "python-ast"
                else f" [{file_summary.language}/{symbol.source}]"
            )
            for file_summary, symbol in results
        )
