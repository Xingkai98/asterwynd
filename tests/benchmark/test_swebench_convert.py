"""Unit tests for SWE-bench task converter logic."""

import json

import pytest

from benchmarks.swebench_convert import build_test_command, extract_test_file


class TestExtractTestFile:
    def test_simple(self):
        result = extract_test_file(
            '["tests/test_requests.py::test_foo[bar]"]'
        )
        assert result == "tests/test_requests.py"

    def test_multi(self):
        result = extract_test_file(
            '["testing/test_cap.py::test_a[x]", "testing/test_cap.py::test_b[y]"]'
        )
        assert result == "testing/test_cap.py"

    def test_empty(self):
        assert extract_test_file("[]") == ""
        assert extract_test_file("invalid json") == ""


class TestBuildTestCommand:
    def test_normal_node_ids(self):
        fail = json.dumps(
            ["tests/test_blueprints.py::test_empty_name_not_allowed"]
        )
        cmd = build_test_command("pallets/flask", fail)
        assert "tests/test_blueprints.py::test_empty_name_not_allowed" in cmd
        assert "-k" not in cmd

    def test_control_characters_uses_k_flag(self):
        """Tests with \\r\\n in node ID should use -k to avoid shell issues."""
        # Simulate what HF dataset stores: after json.loads, the string contains
        # literal backslash-r-backslash-n (4 chars), which shell may mangle
        fail = json.dumps(
            [
                "testing/test_capture.py::TestCaptureFixture::test_cafd_preserves_newlines[\\r\\n]",
                "testing/test_capture.py::TestCaptureFixture::test_cafd_preserves_newlines[\\r]",
            ]
        )
        cmd = build_test_command("pytest-dev/pytest", fail)
        assert " -k " in cmd
        assert "test_cafd_preserves_newlines" in cmd

    def test_fallback_on_invalid_json(self):
        cmd = build_test_command("psf/requests", "{not valid}")
        assert "python -m pytest" in cmd
        assert "--tb=short" in cmd
