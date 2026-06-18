"""Convert SWE-bench Verified instances to MyAgent benchmark task format.

Usage:
    python benchmarks/swebench_convert.py              # interactive: pick from top candidates
    python benchmarks/swebench_convert.py --all-requests  # generate all 6 requests tasks
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Map SWE-bench repo names to GitHub URLs
REPO_URLS = {
    "psf/requests": "https://github.com/psf/requests.git",
    "pallets/flask": "https://github.com/pallets/flask.git",
    "pytest-dev/pytest": "https://github.com/pytest-dev/pytest.git",
    "sympy/sympy": "https://github.com/sympy/sympy.git",
    "mwaskom/seaborn": "https://github.com/mwaskom/seaborn.git",
    "pylint-dev/pylint": "https://github.com/pylint-dev/pylint.git",
    "django/django": "https://github.com/django/django.git",
    "scikit-learn/scikit-learn": "https://github.com/scikit-learn/scikit-learn.git",
    "matplotlib/matplotlib": "https://github.com/matplotlib/matplotlib.git",
    "sphinx-doc/sphinx": "https://github.com/sphinx-doc/sphinx.git",
    "astropy/astropy": "https://github.com/astropy/astropy.git",
    "pydata/xarray": "https://github.com/pydata/xarray.git",
}

# Test commands per repo (runs the specific test file, not the whole suite)
REPO_TEST_COMMAND_TEMPLATES = {
    "psf/requests": "python -m pytest {test_file} -x --tb=short -p no:warnings",
    "pallets/flask": "python -m pytest {test_file} -x --tb=short -p no:warnings",
    "pytest-dev/pytest": "python -m pytest {test_file} -x --tb=short -p no:warnings",
    "sympy/sympy": "python -m pytest {test_file} -x --tb=short -p no:warnings",
    "pylint-dev/pylint": "python -m pytest {test_file} -x --tb=short -p no:warnings",
}


def load_verified():
    from datasets import load_dataset

    return load_dataset("princeton-nlp/SWE-bench_Verified", split="test")


def extract_test_file(fail_to_pass: str) -> str:
    """Extract the test file path from FAIL_TO_PASS JSON list.

    e.g. '["tests/test_requests.py::test_invalid_url[...]"]' -> 'tests/test_requests.py'
    """
    try:
        tests = json.loads(fail_to_pass)
        if tests:
            return tests[0].split("::")[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        pass
    return ""


def build_test_command(repo: str, fail_to_pass: str) -> str:
    """Build a test command for the task."""
    test_file = extract_test_file(fail_to_pass)
    template = REPO_TEST_COMMAND_TEMPLATES.get(repo, "python -m pytest {test_file} -x --tb=short -p no:warnings")
    return template.format(test_file=test_file)


def generate_tasks(instance_ids: list[str], output_base: str | Path) -> list[Path]:
    """Generate MyAgent task directories for the given SWE-bench instance IDs."""
    ds = load_verified()
    ds_dict = {ex["instance_id"]: ex for ex in ds}

    output_base = Path(output_base)
    output_base.mkdir(parents=True, exist_ok=True)

    created = []
    for iid in instance_ids:
        ex = ds_dict.get(iid)
        if ex is None:
            print(f"WARNING: {iid} not found in Verified dataset, skipping")
            continue

        repo = ex["repo"]
        repo_url = REPO_URLS.get(repo)
        short_id = iid.replace("__", "/")
        if not repo_url:
            print(f"WARNING: no URL mapping for {repo}, skipping {iid}")
            continue

        test_command = build_test_command(repo, ex["FAIL_TO_PASS"])

        task_dir = output_base / f"swebench-{iid}"
        task_dir.mkdir(parents=True, exist_ok=True)

        # Write task.json (keep it concise, no long hints)
        task_json = {
            "id": f"swebench-{iid}",
            "repo": repo,
            "base_commit": ex["base_commit"],
            "problem_statement_file": "issue.md",
            "test_command": test_command,
            "timeout_seconds": 300,
            "gold_patch_file": "gold.patch",
            "test_patch_file": "test.patch",
            "category": "bug_fix",
            "difficulty": ex.get("difficulty", ""),
            "external_repo": repo_url,
        }
        (task_dir / "task.json").write_text(
            json.dumps(task_json, indent=2, ensure_ascii=False) + "\n"
        )

        # Write hints.md (separate file, not embedded in JSON)
        if ex.get("hints_text"):
            (task_dir / "hints.md").write_text(ex["hints_text"], errors="replace")

        # Write issue.md
        (task_dir / "issue.md").write_text(
            ex["problem_statement"], errors="replace"
        )

        # Write test.patch
        test_patch = ex.get("test_patch", "")
        (task_dir / "test.patch").write_text(test_patch, errors="replace")

        # Write gold.patch (reference only, not shown to agent)
        gold_patch = ex.get("patch", "")
        (task_dir / "gold.patch").write_text(gold_patch, errors="replace")

        print(f"  Created: {task_dir.name}")
        print(f"    Repo: {repo}  Commit: {ex['base_commit'][:8]}")
        print(f"    Test: {test_command}")
        print(f"    FAIL_TO_PASS: {ex['FAIL_TO_PASS']}")
        created.append(task_dir)

    return created


def list_candidates():
    """List top lightweight Easy candidates for the user to pick."""
    from collections import defaultdict

    ds = load_verified()

    # Filter for lightweight repos, <15 min fix, small patches
    light_repos = {"psf/requests", "pallets/flask", "pytest-dev/pytest"}
    candidates = []
    for ex in ds:
        repo = ex["repo"]
        difficulty = ex.get("difficulty", "")
        if repo not in light_repos or difficulty != "<15 min fix":
            continue
        patch = ex.get("patch", "")
        if not patch:
            continue
        changed = sum(
            1
            for line in patch.split("\n")
            if (line.startswith("+") and not line.startswith("+++"))
            or (line.startswith("-") and not line.startswith("---"))
        )
        if changed > 30:
            continue
        candidates.append((ex["instance_id"], repo, difficulty, changed))

    candidates.sort(key=lambda x: x[3])

    print("## Lightweight + <15 min fix candidates (sorted by patch size):\n")
    by_repo = defaultdict(list)
    for c in candidates:
        by_repo[c[1]].append(c)

    for repo in sorted(by_repo):
        print(f"  [{repo}]")
        for c in by_repo[repo]:
            print(f"    {c[0]:55s}  patch={c[3]:3d} lines")
        print()

    print("Use --instances to select specific IDs.")


def main():
    parser = argparse.ArgumentParser(description="Convert SWE-bench instances to MyAgent tasks")
    parser.add_argument("--all-requests", action="store_true",
                        help="Generate all 6 psf/requests <15 min fix tasks")
    parser.add_argument("--batch", action="store_true",
                        help="Generate curated batch: 5 requests + 3 pytest + 1 flask")
    parser.add_argument("--instances", nargs="*", default=[],
                        help="Specific SWE-bench instance IDs to convert")
    parser.add_argument("--list", action="store_true",
                        help="List top candidates and exit")
    parser.add_argument("--output", default="benchmarks/tasks",
                        help="Output directory for generated tasks")
    args = parser.parse_args()

    if args.list:
        list_candidates()
        return

    instance_ids = list(args.instances)

    if args.batch:
        instance_ids = [
            # 5 requests (excluding 5414 which was already the smoke test)
            "psf__requests-1142",
            "psf__requests-1921",
            "psf__requests-2317",
            "psf__requests-1724",
            "psf__requests-1766",
            # 3 pytest
            "pytest-dev__pytest-7521",
            "pytest-dev__pytest-7982",
            "pytest-dev__pytest-5262",
            # 1 flask
            "pallets__flask-5014",
        ]
    elif args.all_requests:
        instance_ids = [
            "psf__requests-5414",
            "psf__requests-1921",
            "psf__requests-1142",
            "psf__requests-1766",
            "psf__requests-2317",
            "psf__requests-1724",
        ]

    if not instance_ids:
        print("No instance IDs provided. Use --list to see candidates, "
              "--all-requests to generate requests tasks, or --instances to pick.")
        sys.exit(1)

    print(f"Generating {len(instance_ids)} tasks...\n")
    created = generate_tasks(instance_ids, args.output)
    print(f"\nDone. {len(created)} tasks created in {args.output}")


if __name__ == "__main__":
    main()
