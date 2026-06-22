from agent.code_intelligence.python_symbols import extract_python_summary


def test_extract_python_summary_returns_imports_classes_functions_and_methods(tmp_path):
    source = tmp_path / "service.py"
    source.write_text(
        "\n".join(
            [
                "import os",
                "import pathlib as pl",
                "from agent.tools import Tool",
                "",
                "def helper():",
                "    pass",
                "",
                "class Service:",
                "    def run(self):",
                "        pass",
                "",
                "    async def stop(self):",
                "        pass",
            ]
        )
    )

    summary = extract_python_summary(source, "service.py")

    assert [item.name for item in summary.imports] == [
        "os",
        "pathlib as pl",
        "agent.tools.Tool",
    ]
    assert [(item.kind, item.name, item.line) for item in summary.symbols] == [
        ("function", "helper", 5),
        ("class", "Service", 8),
        ("method", "Service.run", 9),
        ("method", "Service.stop", 12),
    ]


def test_extract_python_summary_reports_syntax_error_without_raising(tmp_path):
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n")

    summary = extract_python_summary(source, "broken.py")

    assert summary.parse_error is not None
    assert summary.symbols == []
