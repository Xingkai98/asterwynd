from agent.code_intelligence.config import CodeIntelligenceConfig
from agent.code_intelligence.repo_map import build_repo_map
from agent.code_intelligence.tree_sitter_symbols import (
    TreeSitterExtractor,
    TreeSitterLanguage,
)
from agent.workspace_policy import WorkspacePolicy


def test_tree_sitter_extracts_typescript_symbols_and_imports(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text(
        "\n".join(
            [
                'import { Tool } from "agent";',
                "export class Service {",
                "  start(): void {}",
                "}",
                "export const make = () => 1;",
                "interface Port { run(): void }",
            ]
        ),
        encoding="utf-8",
    )

    repo_map = build_repo_map(policy=WorkspacePolicy(tmp_path))
    summary = repo_map.files[0]

    assert summary.language == "typescript"
    assert [item.name for item in summary.imports] == ["agent"]
    assert [(symbol.kind, symbol.name, symbol.line, symbol.source) for symbol in summary.symbols] == [
        ("class", "Service", 2, "tree-sitter-typescript"),
        ("method", "Service.start", 3, "tree-sitter-typescript"),
        ("function", "make", 5, "tree-sitter-typescript"),
        ("interface", "Port", 6, "tree-sitter-typescript"),
        ("method", "Port.run", 6, "tree-sitter-typescript"),
    ]


def test_tree_sitter_extracts_javascript_go_and_rust_symbols(tmp_path):
    (tmp_path / "app.js").write_text(
        "export function run() {}\nclass Service { start() {} }\n",
        encoding="utf-8",
    )
    (tmp_path / "main.go").write_text(
        "package main\n"
        "type Service struct{}\n"
        "type Runner interface { Run() }\n"
        "func main() {}\n"
        "func (s Service) Start() {}\n",
        encoding="utf-8",
    )
    (tmp_path / "lib.rs").write_text(
        "struct Service;\n"
        "enum State { Ready }\n"
        "trait Runner { fn run(&self); }\n"
        "fn helper() {}\n"
        "impl Service { fn start(&self) {} }\n",
        encoding="utf-8",
    )

    repo_map = build_repo_map(policy=WorkspacePolicy(tmp_path))
    symbols_by_path = {
        entry.path: [(symbol.kind, symbol.name) for symbol in entry.symbols]
        for entry in repo_map.files
    }

    assert symbols_by_path["app.js"] == [
        ("function", "run"),
        ("class", "Service"),
        ("method", "Service.start"),
    ]
    assert symbols_by_path["main.go"] == [
        ("struct", "Service"),
        ("interface", "Runner"),
        ("function", "main"),
        ("method", "Service.Start"),
    ]
    assert symbols_by_path["lib.rs"] == [
        ("struct", "Service"),
        ("enum", "State"),
        ("trait", "Runner"),
        ("method", "Runner.run"),
        ("function", "helper"),
        ("method", "Service.start"),
    ]


def test_tree_sitter_keeps_file_entry_when_file_exceeds_configured_limit(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text("export function run() {}\n", encoding="utf-8")

    repo_map = build_repo_map(
        policy=WorkspacePolicy(tmp_path),
        code_intelligence_config=CodeIntelligenceConfig(tree_sitter_max_file_bytes=4),
    )

    summary = repo_map.files[0]
    assert summary.path == "app.ts"
    assert summary.symbols == []
    assert summary.parse_error == "tree-sitter skipped: file too large"


def test_unregistered_source_language_keeps_file_entry_without_fake_symbols(tmp_path):
    source = tmp_path / "Service.java"
    source.write_text("class Service { void run() {} }\n", encoding="utf-8")

    repo_map = build_repo_map(policy=WorkspacePolicy(tmp_path))

    summary = repo_map.files[0]
    assert summary.path == "Service.java"
    assert summary.language == "java"
    assert summary.category == "source"
    assert summary.symbols == []
    assert summary.parse_error is None


def test_tree_sitter_keeps_file_entry_when_grammar_is_unavailable(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text("export function run() {}\n", encoding="utf-8")
    extractor = TreeSitterExtractor(
        registry={
            "typescript": TreeSitterLanguage(
                language="typescript",
                source="tree-sitter-typescript",
                load_language=lambda: (_ for _ in ()).throw(ImportError("missing")),
                query="",
                import_query="",
            )
        }
    )

    repo_map = build_repo_map(
        policy=WorkspacePolicy(tmp_path),
        extractors=(extractor,),
    )

    summary = repo_map.files[0]
    assert summary.symbols == []
    assert summary.parse_error == "tree-sitter grammar unavailable"
