import json

from benchmarks.swebench_subset import (
    SUBSET_TARGETS,
    build_subset,
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
