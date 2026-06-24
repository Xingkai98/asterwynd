from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Parser, Query, QueryCursor

from agent.code_intelligence.config import CodeIntelligenceConfig
from agent.code_intelligence.models import FileSummary, ImportSummary, Symbol


@dataclass(frozen=True)
class TreeSitterLanguage:
    language: str
    source: str
    load_language: Callable[[], Language]
    query: str
    import_query: str = ""


def _load_javascript_language() -> Language:
    import tree_sitter_javascript

    return Language(tree_sitter_javascript.language())


def _load_typescript_language() -> Language:
    import tree_sitter_typescript

    return Language(tree_sitter_typescript.language_typescript())


def _load_go_language() -> Language:
    import tree_sitter_go

    return Language(tree_sitter_go.language())


def _load_rust_language() -> Language:
    import tree_sitter_rust

    return Language(tree_sitter_rust.language())


JAVASCRIPT_QUERY = """
(function_declaration name: (identifier) @function.name)
(class_declaration name: (identifier) @class.name)
(method_definition name: (property_identifier) @method.name)
(variable_declarator
  name: (identifier) @function.name
  value: [(arrow_function) (function_expression)])
(export_specifier name: (identifier) @export.name)
"""

TYPESCRIPT_QUERY = """
(function_declaration name: (identifier) @function.name)
(class_declaration name: (type_identifier) @class.name)
(method_definition name: (property_identifier) @method.name)
(method_signature name: (property_identifier) @method.name)
(variable_declarator
  name: (identifier) @function.name
  value: [(arrow_function) (function_expression)])
(interface_declaration name: (type_identifier) @interface.name)
(type_alias_declaration name: (type_identifier) @type.name)
(export_specifier name: (identifier) @export.name)
"""

JAVASCRIPT_IMPORT_QUERY = """
(import_statement source: (string) @import.name)
"""

GO_QUERY = """
(function_declaration name: (identifier) @function.name)
(method_declaration name: (field_identifier) @method.name)
(type_spec
  name: (type_identifier) @struct.name
  type: (struct_type))
(type_spec
  name: (type_identifier) @interface.name
  type: (interface_type))
"""

RUST_QUERY = """
(function_item name: (identifier) @function.name)
(function_signature_item name: (identifier) @method.name)
(struct_item name: (type_identifier) @struct.name)
(enum_item name: (type_identifier) @enum.name)
(trait_item name: (type_identifier) @trait.name)
"""


DEFAULT_TREE_SITTER_REGISTRY: dict[str, TreeSitterLanguage] = {
    "javascript": TreeSitterLanguage(
        language="javascript",
        source="tree-sitter-javascript",
        load_language=_load_javascript_language,
        query=JAVASCRIPT_QUERY,
        import_query=JAVASCRIPT_IMPORT_QUERY,
    ),
    "typescript": TreeSitterLanguage(
        language="typescript",
        source="tree-sitter-typescript",
        load_language=_load_typescript_language,
        query=TYPESCRIPT_QUERY,
        import_query=JAVASCRIPT_IMPORT_QUERY,
    ),
    "go": TreeSitterLanguage(
        language="go",
        source="tree-sitter-go",
        load_language=_load_go_language,
        query=GO_QUERY,
    ),
    "rust": TreeSitterLanguage(
        language="rust",
        source="tree-sitter-rust",
        load_language=_load_rust_language,
        query=RUST_QUERY,
    ),
}


class TreeSitterExtractor:
    def __init__(
        self,
        *,
        config: CodeIntelligenceConfig | None = None,
        registry: Mapping[str, TreeSitterLanguage] | None = None,
    ):
        self.config = config or CodeIntelligenceConfig()
        self.registry = registry or DEFAULT_TREE_SITTER_REGISTRY

    def supports(self, path: Path, language: str) -> bool:
        return language in self.registry

    def extract(self, path: Path, rel_path: str, language: str) -> FileSummary:
        text = path.read_text(encoding="utf-8", errors="replace")
        file_bytes = path.stat().st_size
        lines = text.count("\n") + (0 if text == "" else 1)
        if file_bytes > self.config.tree_sitter_max_file_bytes:
            return _empty_summary(
                rel_path,
                language,
                lines,
                file_bytes,
                "tree-sitter skipped: file too large",
            )

        registration = self.registry[language]
        try:
            parser_language = registration.load_language()
        except ImportError:
            return _empty_summary(
                rel_path,
                language,
                lines,
                file_bytes,
                "tree-sitter grammar unavailable",
            )

        try:
            tree = Parser(parser_language).parse(text.encode("utf-8"))
            symbols = _extract_symbols(tree.root_node, text, parser_language, registration)
            imports = _extract_imports(tree.root_node, text, parser_language, registration)
        except Exception as exc:
            return _empty_summary(
                rel_path,
                language,
                lines,
                file_bytes,
                f"tree-sitter parse failed: {exc}",
            )

        return FileSummary(
            path=rel_path,
            language=language,
            category="source",
            lines=lines,
            bytes=file_bytes,
            symbols=symbols,
            imports=imports,
        )


def _extract_symbols(
    root_node,
    text: str,
    language: Language,
    registration: TreeSitterLanguage,
) -> list[Symbol]:
    query = Query(language, registration.query)
    captures = QueryCursor(query).captures(root_node)
    symbols: list[Symbol] = []
    seen: set[tuple[str, str, int]] = set()
    for capture_name, nodes in captures.items():
        kind = capture_name.split(".", 1)[0]
        for node in nodes:
            symbol_kind = kind
            name = _node_text(node, text)
            if not name:
                continue
            if registration.language in {"javascript", "typescript"} and kind == "method":
                if owner := _javascript_method_owner(node, text):
                    name = f"{owner}.{name}"
            elif registration.language == "go" and kind == "method":
                if owner := _go_method_owner(node, text):
                    name = f"{owner}.{name}"
            elif registration.language == "rust":
                if kind == "function" and (owner := _rust_impl_owner(node, text)):
                    symbol_kind = "method"
                    name = f"{owner}.{name}"
                elif kind == "method" and (owner := _rust_trait_owner(node, text)):
                    name = f"{owner}.{name}"

            line = node.start_point[0] + 1
            key = (symbol_kind, name, line)
            if key in seen:
                continue
            seen.add(key)
            symbols.append(
                Symbol(
                    name=name,
                    kind=symbol_kind,
                    line=line,
                    source=registration.source,
                )
            )
    return sorted(symbols, key=lambda symbol: (symbol.line, symbol.name))


def _extract_imports(
    root_node,
    text: str,
    language: Language,
    registration: TreeSitterLanguage,
) -> list[ImportSummary]:
    if not registration.import_query:
        return []
    query = Query(language, registration.import_query)
    captures = QueryCursor(query).captures(root_node)
    imports: list[ImportSummary] = []
    for node in captures.get("import.name", []):
        imports.append(
            ImportSummary(
                name=_node_text(node, text).strip("'\""),
                line=node.start_point[0] + 1,
            )
        )
    return imports


def _empty_summary(
    rel_path: str,
    language: str,
    lines: int,
    file_bytes: int,
    parse_error: str,
) -> FileSummary:
    return FileSummary(
        path=rel_path,
        language=language,
        category="source",
        lines=lines,
        bytes=file_bytes,
        parse_error=parse_error,
    )


def _node_text(node, text: str) -> str:
    return text.encode("utf-8")[node.start_byte : node.end_byte].decode(
        "utf-8",
        errors="replace",
    )


def _ancestor(node, node_type: str):
    current = node.parent
    while current is not None:
        if current.type == node_type:
            return current
        current = current.parent
    return None


def _child_text(node, field_name: str, text: str) -> str | None:
    child = node.child_by_field_name(field_name)
    return _node_text(child, text) if child is not None else None


def _javascript_method_owner(node, text: str) -> str | None:
    if class_node := _ancestor(node, "class_declaration"):
        return _child_text(class_node, "name", text)
    if interface_node := _ancestor(node, "interface_declaration"):
        return _child_text(interface_node, "name", text)
    return None


def _go_method_owner(node, text: str) -> str | None:
    method_node = _ancestor(node, "method_declaration")
    if method_node is None:
        return None
    receiver = method_node.child_by_field_name("receiver")
    if receiver is None:
        receiver = method_node.named_children[0] if method_node.named_children else None
    if receiver is None:
        return None
    for child in receiver.named_children:
        if child.type == "parameter_declaration":
            type_node = child.child_by_field_name("type")
            if type_node is not None:
                return _node_text(type_node, text).lstrip("*")
        if child.type == "type_identifier":
            return _node_text(child, text).lstrip("*")
    return None


def _rust_impl_owner(node, text: str) -> str | None:
    if impl_node := _ancestor(node, "impl_item"):
        return _child_text(impl_node, "type", text)
    return None


def _rust_trait_owner(node, text: str) -> str | None:
    if trait_node := _ancestor(node, "trait_item"):
        return _child_text(trait_node, "name", text)
    return None
