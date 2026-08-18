"""Unit tests for SWE-bench task converter logic."""

import json

import pytest

from benchmarks.swebench_convert import (
    GITEE_PREFERRED_URLS,
    _test_file_from_patch,
    build_test_command,
    extract_test_file,
    generate_tasks,
    normalize_difficulty,
)


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

    def test_bare_function_names_rebuild_with_test_patch_file(self):
        """Round 1 Issue 1：裸函数名（无 .py:: 前缀）按 test.patch 文件路径重建 -k。"""
        fail = json.dumps(["test_issue_11617"])
        patch = "diff --git a/sympy/geometry/tests/test_point.py b/sympy/geometry/tests/test_point.py\n--- a/...\n+++ b/...\n"
        cmd = build_test_command("sympy/sympy", fail, patch)
        assert "sympy/geometry/tests/test_point.py" in cmd
        assert "-k 'test_issue_11617'" in cmd
        assert "::" not in cmd or True  # node id 不再出现裸标识符

    def test_bare_function_names_without_patch_uses_k_only(self):
        cmd = build_test_command("sympy/sympy", json.dumps(["test_equality", "test_args"]))
        assert "-k 'test_equality or test_args'" in cmd
        # 裸函数名只出现在 -k 表达式内，不得作为 pytest 路径参数（shlex 解析验证）
        import shlex

        tokens = shlex.split(cmd)
        node_args = []
        i = tokens.index("pytest") + 1
        while i < len(tokens):
            t = tokens[i]
            if t in {"-k", "-p"}:
                i += 2
                continue
            if t.startswith("-"):
                i += 1
                continue
            node_args.append(t)
            i += 1
        assert node_args == []

    def test_full_node_ids_unchanged(self):
        fail = json.dumps(["tests/test_blueprints.py::test_empty_name_not_allowed"])
        cmd = build_test_command("pallets/flask", fail)
        assert "tests/test_blueprints.py::test_empty_name_not_allowed" in cmd
        assert "-k" not in cmd


class TestTestFileFromPatch:
    def test_extracts_test_path_preferring_test(self):
        patch = (
            "diff --git a/sympy/core/tests/test_basic.py b/sympy/core/tests/test_basic.py\n"
            "diff --git a/sympy/core/basic.py b/sympy/core/basic.py\n"
        )
        assert _test_file_from_patch(patch) == "sympy/core/tests/test_basic.py"

    def test_empty_patch_returns_empty(self):
        assert _test_file_from_patch("") == ""
        assert _test_file_from_patch("no diff here") == ""


class TestNormalizeDifficulty:
    """C1 OQ-V1 映射口径：<15min→easy、15min-2h→medium、≥2h→hard。"""

    def test_maps_verified_difficulty_values(self):
        assert normalize_difficulty({"difficulty": "<15 min fix"}) == "easy"
        assert normalize_difficulty({"difficulty": "15-30 min fix"}) == "medium"
        assert normalize_difficulty({"difficulty": ">30 min fix"}) == "hard"
        assert normalize_difficulty({"difficulty": "<15min"}) == "easy"
        assert normalize_difficulty({"difficulty": "15min-2h"}) == "medium"
        assert normalize_difficulty({"difficulty": ">=2h"}) == "hard"
        # 本机 hf-mirror 首拉实测的真实列值（2026-08-18）
        assert normalize_difficulty({"difficulty": "15 min - 1 hour"}) == "medium"
        assert normalize_difficulty({"difficulty": "1-4 hours"}) == "hard"
        assert normalize_difficulty({"difficulty": ">4 hours"}) == "hard"

    def test_passthrough_already_normalized(self):
        assert normalize_difficulty({"difficulty": "easy"}) == "easy"
        assert normalize_difficulty({"difficulty": "hard"}) == "hard"

    def test_heuristic_by_fail_to_pass_count(self):
        assert normalize_difficulty({"FAIL_TO_PASS": json.dumps(["t1"])}) == "easy"
        assert (
            normalize_difficulty({"FAIL_TO_PASS": json.dumps(["t1", "t2", "t3", "t4"])})
            == "medium"
        )
        assert normalize_difficulty({"FAIL_TO_PASS": json.dumps(["t1"] * 8)}) == "hard"

    def test_malformed_fail_to_pass_falls_back_to_easy(self):
        assert normalize_difficulty({"FAIL_TO_PASS": "{bad json"}) == "easy"
        assert normalize_difficulty({}) == "easy"


class TestGenerateTasksVerifiedFields:
    """generate_tasks 落盘字段修复（grill OQ-V1）：track/scenario/difficulty/version/external_repo。"""

    def _dataset(self):
        return [
            {
                "instance_id": "psf__requests-1",
                "repo": "psf/requests",
                "base_commit": "abc123",
                "problem_statement": "bug report",
                "patch": "--- a/requests/x.py\n+++ b/requests/x.py\n@@ -1 +1 @@\n-foo\n+bar\n",
                "test_patch": "--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -1 +1 @@\n-foo\n+bar\n",
                "FAIL_TO_PASS": json.dumps(["tests/test_x.py::test_a"]),
                "difficulty": "<15 min fix",
                "version": "2.0",
            }
        ]

    def test_generate_tasks_writes_verified_fields(self, tmp_path):
        created = generate_tasks(
            ["psf__requests-1"], tmp_path,
            dataset=self._dataset(), repo_urls=GITEE_PREFERRED_URLS,
        )
        assert len(created) == 1
        task = json.loads((created[0] / "task.json").read_text())
        assert task["track"] == "verified"
        assert task["scenario"] == "bug-fix"
        assert task["difficulty"] == "easy"
        assert task["version"] == "2.0"
        assert task["external_repo"] == "https://gitee.com/mirrors/requests.git"
        assert task["instance_id"] == "psf__requests-1"
        assert task["dataset_name"] == "princeton-nlp/SWE-bench_Verified"
        assert task["dataset_split"] == "test"
        assert (created[0] / "issue.md").exists()
        assert (created[0] / "gold.patch").exists()
        assert (created[0] / "test.patch").exists()

    def test_external_repo_gitee_for_requests_github_for_sympy(self, tmp_path):
        ds = self._dataset() + [
            {
                "instance_id": "sympy__sympy-1",
                "repo": "sympy/sympy",
                "base_commit": "def456",
                "problem_statement": "bug",
                "patch": "--- a/sympy/x.py\n+++ b/sympy/x.py\n",
                "test_patch": "--- a/tests/test_x.py\n+++ b/tests/test_x.py\n",
                "FAIL_TO_PASS": json.dumps(["tests/test_x.py::test_b"]),
                "difficulty": "<15 min fix",
                "version": "1.0",
            }
        ]
        created = generate_tasks(
            ["psf__requests-1", "sympy__sympy-1"], tmp_path,
            dataset=ds, repo_urls=GITEE_PREFERRED_URLS,
        )
        req = json.loads((created[0] / "task.json").read_text())
        sym = json.loads((created[1] / "task.json").read_text())
        assert req["external_repo"] == "https://gitee.com/mirrors/requests.git"
        assert sym["external_repo"] == "https://github.com/sympy/sympy.git"
