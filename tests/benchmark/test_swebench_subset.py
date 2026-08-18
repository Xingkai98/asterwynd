import json
import os
from subprocess import CompletedProcess

import pytest

from benchmarks.swebench_subset import (
    SUBSET_TARGETS,
    build_subset,
    collect_existing_instance_ids,
    gold_check,
    main,
    parse_targets,
    update_manifest_verified,
    validate_fixture,
    validate_fixtures_dir,
)


def _inst(instance_id, repo, test_patch="--- a/x\n+++ b/x\n"):
    return {"instance_id": instance_id, "repo": repo, "test_patch": test_patch}


def test_build_subset_filters_known_bad_and_heavy_and_empty_test_patch():
    instances = [
        _inst("psf__requests-1", "psf/requests"),          # take
        _inst("psf__requests-2", "psf/requests"),          # take
        _inst("psf__requests-BAD", "psf/requests"),        # known_bad
        _inst("django__x-1", "django/django"),             # heavy
        _inst("pallets__flask-1", "pallets/flask", test_patch=""),  # no test_patch
    ]
    plan = build_subset(
        instances,
        targets={"psf/requests": 2},
        known_bad={"psf__requests-BAD"},
    )
    assert [e["instance_id"] for e in plan.selected] == [
        "psf__requests-1",
        "psf__requests-2",
    ]
    assert plan.skipped_known_bad == 1
    assert plan.skipped_heavy == 1
    assert plan.skipped_no_test_patch == 1


def test_build_subset_respects_per_repo_targets():
    instances = [
        _inst(f"psf__requests-{i}", "psf/requests") for i in range(6)
    ] + [_inst(f"sympy__sympy-{i}", "sympy/sympy") for i in range(3)]
    plan = build_subset(instances, targets={"psf/requests": 4, "sympy/sympy": 2})
    by_repo = {}
    for ex in plan.selected:
        by_repo.setdefault(ex["repo"], []).append(ex["instance_id"])
    assert len(by_repo["psf/requests"]) == 4
    assert len(by_repo["sympy/sympy"]) == 2
    assert "selected=6" in plan.summary()


def test_build_subset_pool_remaining_counts_extras():
    instances = [_inst(f"psf__requests-{i}", "psf/requests") for i in range(5)]
    plan = build_subset(instances, targets={"psf/requests": 2})
    assert plan.pool_remaining == 3


def test_build_subset_skips_missing_instance_id():
    instances = [
        _inst("psf__requests-1", "psf/requests"),
        {"repo": "psf/requests", "test_patch": "--- a/x\n+++ b/x\n"},  # no instance_id
    ]
    plan = build_subset(instances, targets={"psf/requests": 2})
    assert [e["instance_id"] for e in plan.selected] == ["psf__requests-1"]
    assert plan.skipped_missing_instance_id == 1


def test_validate_fixture_accepts_valid_verified_task():
    task = {
        "id": "swebench-psf__requests-1142",
        "task_family": "swebench",
        "execution_environment": "docker",
        "instance_id": "psf__requests-1142",
        "dataset_name": "princeton-nlp/SWE-bench_Verified",
        "dataset_split": "test",
        "track": "verified",
        "scenario": "bug-fix",
        "difficulty": "easy",
    }
    assert validate_fixture(task) == []


def test_validate_fixture_reports_missing_and_wrong_fields():
    task = {
        "id": "swebench-bad",
        "task_family": "swebench",
        "execution_environment": "vm",
        "instance_id": "",
        "dataset_name": "",
        "dataset_split": "",
        "track": "A",
        "scenario": "debug",
        "difficulty": "<15 min fix",
    }
    errors = validate_fixture(task)
    assert "missing instance_id" in errors
    assert "missing dataset_name" in errors
    assert "missing dataset_split" in errors
    assert "track must be 'verified'" in errors
    assert "scenario must be 'bug-fix' for verified fixtures" in errors
    assert any("difficulty not normalized" in e for e in errors)
    assert "execution_environment must be 'local' or 'docker'" in errors


def test_existing_swebench_fixtures_pass_metadata_validation():
    """现有 10 条 swebench fixture 应全部通过元数据校验（迁移后）。"""
    problems = validate_fixtures_dir("benchmarks/tasks")
    assert problems == [], f"fixtures invalid: {problems}"


def test_build_subset_excludes_existing_instance_ids():
    """OQ-V3：选择池排除既有 fixture 的 instance_id，避免覆盖写与不足 40 新。"""
    instances = [
        _inst("psf__requests-1", "psf/requests"),
        _inst("psf__requests-2", "psf/requests"),
    ]
    plan = build_subset(
        instances,
        targets={"psf/requests": 2},
        exclude_ids={"psf__requests-1"},
    )
    assert [e["instance_id"] for e in plan.selected] == ["psf__requests-2"]
    assert plan.skipped_existing == 1


def test_parse_targets_comma_separated_short_names():
    """OQ-V5②：逗号分隔短名，短名映射完整 repo 键。"""
    assert parse_targets("requests+4,flask+6") == {
        "psf/requests": 4,
        "pallets/flask": 6,
    }
    assert parse_targets(None) == dict(SUBSET_TARGETS)


def test_parse_targets_rejects_bad_input():
    with pytest.raises(ValueError, match="未知短名"):
        parse_targets("django+1")
    with pytest.raises(ValueError, match="target 需形如"):
        parse_targets("requests")


def test_collect_existing_instance_ids(tmp_path):
    (tmp_path / "swebench-psf__requests-1").mkdir()
    (tmp_path / "swebench-psf__requests-1" / "task.json").write_text(
        json.dumps({"instance_id": "psf__requests-1"})
    )
    (tmp_path / "swebench-psf__requests-2").mkdir()
    (tmp_path / "swebench-psf__requests-2" / "task.json").write_text(
        json.dumps({"instance_id": "psf__requests-2"})
    )
    assert collect_existing_instance_ids(tmp_path) == {
        "psf__requests-1",
        "psf__requests-2",
    }


def test_update_manifest_verified_summary(tmp_path):
    """OQ-V6①：verified 摘要计数（count/by_repo/by_difficulty），不破坏既有键。"""
    (tmp_path / "manifest.json").write_text(json.dumps({"version": 1, "coverage": {}}))
    fixtures = [
        ("psf__requests-1", "psf/requests", "easy"),
        ("psf__requests-2", "psf/requests", "easy"),
        ("pallets__flask-1", "pallets/flask", "medium"),
    ]
    for iid, repo, diff in fixtures:
        d = tmp_path / f"swebench-{iid}"
        d.mkdir()
        (d / "task.json").write_text(
            json.dumps(
                {"instance_id": iid, "repo": repo, "difficulty": diff, "track": "verified"}
            )
        )
    summary = update_manifest_verified(tmp_path)
    assert summary["count"] == 3
    assert summary["by_repo"] == {"psf/requests": 2, "pallets/flask": 1}
    assert summary["by_difficulty"] == {"easy": 2, "medium": 1}
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["coverage"] == {}


def test_build_subset_cli_end_to_end(tmp_path, monkeypatch):
    """build-subset 端到端（mock 数据集）：选配比→落盘→validate 全过→manifest 登记。"""
    from benchmarks import swebench_convert

    (tmp_path / "manifest.json").write_text(json.dumps({"version": 1}))
    ds = [
        {
            "instance_id": f"psf__requests-{i}",
            "repo": "psf/requests",
            "base_commit": "abc123",
            "problem_statement": "bug",
            "patch": "--- a/requests/x.py\n+++ b/requests/x.py\n@@ -1 +1 @@\n-foo\n+bar\n",
            "test_patch": "--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -1 +1 @@\n-foo\n+bar\n",
            "FAIL_TO_PASS": json.dumps(["tests/test_x.py::test_a"]),
            "difficulty": "<15 min fix",
            "version": "2.0",
        }
        for i in range(4)
    ]
    monkeypatch.setattr(swebench_convert, "load_verified", lambda: ds)
    rc = main(
        [
            "build-subset",
            "--output",
            str(tmp_path),
            "--skip-gold-check",
            "--targets",
            "requests+4",
        ]
    )
    assert rc == 0
    assert validate_fixtures_dir(tmp_path) == []
    for i in range(4):
        task = json.loads(
            (tmp_path / f"swebench-psf__requests-{i}" / "task.json").read_text()
        )
        assert task["track"] == "verified"
        assert task["scenario"] == "bug-fix"
        assert task["difficulty"] == "easy"
        assert task["external_repo"] == "https://gitee.com/mirrors/requests.git"
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["verified"]["count"] == 4
    assert data["verified"]["by_repo"] == {"psf/requests": 4}


def test_build_subset_cli_resume_skips_existing(tmp_path, monkeypatch):
    """--resume：续跑跳过输出目录已存在的 instance_id。"""
    from benchmarks import swebench_convert

    (tmp_path / "manifest.json").write_text(json.dumps({"version": 1}))
    existing = tmp_path / "swebench-psf__requests-0"
    existing.mkdir()
    (existing / "task.json").write_text(
        json.dumps(
            {
                "id": "swebench-psf__requests-0",
                "instance_id": "psf__requests-0",
                "dataset_name": "princeton-nlp/SWE-bench_Verified",
                "dataset_split": "test",
                "track": "verified",
                "scenario": "bug-fix",
                "difficulty": "easy",
                "task_family": "swebench",
                "execution_environment": "docker",
            }
        )
    )
    ds = [
        {
            "instance_id": f"psf__requests-{i}",
            "repo": "psf/requests",
            "base_commit": "abc123",
            "problem_statement": "bug",
            "patch": "--- a/requests/x.py\n+++ b/requests/x.py\n",
            "test_patch": "--- a/tests/test_x.py\n+++ b/tests/test_x.py\n",
            "FAIL_TO_PASS": json.dumps(["tests/test_x.py::test_a"]),
            "difficulty": "<15 min fix",
            "version": "2.0",
        }
        for i in range(4)
    ]
    monkeypatch.setattr(swebench_convert, "load_verified", lambda: ds)
    rc = main(
        [
            "build-subset",
            "--output",
            str(tmp_path),
            "--skip-gold-check",
            "--targets",
            "requests+4",
            "--resume",
        ]
    )
    assert rc == 0
    # requests-0 已存在被跳过（未覆盖），其余 3 条生成
    assert (tmp_path / "swebench-psf__requests-1" / "task.json").exists()
    assert (tmp_path / "swebench-psf__requests-3" / "task.json").exists()
    assert validate_fixtures_dir(tmp_path) == []


def test_gold_check_external_repo_clones_applies_runs(monkeypatch, tmp_path):
    """gold_check external_repo 路径：clone→checkout→apply gold/test→run test_command。"""
    d = tmp_path / "swebench-psf__requests-1"
    d.mkdir()
    (d / "issue.md").write_text("bug")
    (d / "gold.patch").write_text("--- a/x\n+++ b/x\n")
    (d / "test.patch").write_text("--- a/x\n+++ b/x\n")
    (d / "task.json").write_text(
        json.dumps(
            {
                "id": "swebench-psf__requests-1",
                "repo": "psf/requests",
                "base_commit": "abc123",
                "problem_statement_file": "issue.md",
                "test_command": "python -m pytest tests/test_x.py::test_a",
                "gold_patch_file": "gold.patch",
                "test_patch_file": "test.patch",
                "task_family": "local",
                "execution_environment": "local",
                "external_repo": "https://github.com/psf/requests.git",
            }
        )
    )
    calls: list[tuple[object, bool]] = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("shell", False)))
        return CompletedProcess([cmd] if isinstance(cmd, str) else cmd, 0)

    monkeypatch.setattr("benchmarks.swebench_subset.subprocess.run", fake_run)
    assert gold_check(d) == 0
    git_cmds = [cmd for cmd, shell in calls if isinstance(cmd, list) and cmd[0] == "git"]
    assert git_cmds[0][1] == "clone"
    assert "checkout" in git_cmds[1]
    assert [c for c in git_cmds if "apply" in c]  # gold/test apply
    shell_runs = [(cmd, shell) for cmd, shell in calls if shell]
    assert shell_runs and "test_a" in shell_runs[0][0]


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="真实 hf-mirror 网络测试：设置 RUN_INTEGRATION=1 启用",
)
def test_real_hf_mirror_load_and_generate(tmp_path):
    """@integration：HF_ENDPOINT 走 hf-mirror 拉取 Verified，选 2 条 requests 落盘 + validate。"""
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from benchmarks.swebench_convert import load_verified

    ds = load_verified()
    assert len(ds) > 0
    instances = list(ds)
    plan = build_subset(instances, targets={"psf/requests": 2})
    assert len(plan.selected) == 2
    from benchmarks.swebench_convert import GITEE_PREFERRED_URLS, generate_tasks

    generate_tasks(
        [ex["instance_id"] for ex in plan.selected],
        tmp_path,
        dataset=ds,
        repo_urls=GITEE_PREFERRED_URLS,
    )
    assert validate_fixtures_dir(tmp_path) == []
