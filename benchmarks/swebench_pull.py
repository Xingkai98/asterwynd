"""Pull SWE-bench Verified data and identify simple Easy tasks for benchmarking."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

# Lightweight repos that are easy to set up locally (pure Python, few deps)
LIGHTWEIGHT_REPOS = {"psf/requests", "pallets/flask", "pytest-dev/pytest"}

# Repos that are moderate difficulty to set up
MODERATE_REPOS = {"sympy/sympy", "mwaskom/seaborn", "pylint-dev/pylint"}

# Heavy repos (need system deps, databases, etc.)
HEAVY_REPOS = {
    "django/django",
    "scikit-learn/scikit-learn",
    "sphinx-doc/sphinx",
    "matplotlib/matplotlib",
    "pydata/xarray",
    "astropy/astropy",
}


def load_verified(split: str = "test"):
    from datasets import load_dataset

    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split=split)
    return ds


def patch_line_count(patch: str) -> int:
    """Count changed lines in a unified diff (excluding header lines)."""
    if not patch:
        return 0
    return sum(
        1
        for line in patch.split("\n")
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    )


def files_changed(patch: str) -> set[str]:
    """Extract set of non-test filenames changed in the patch."""
    files = set()
    for line in patch.split("\n"):
        if line.startswith("--- a/") or line.startswith("+++ b/"):
            path = line[6:] if line.startswith("--- a/") else line[6:]
            if path and path != "/dev/null":
                files.add(path)
    return {f for f in files if "test" not in f and not f.startswith("tests/")}


def analyze():
    ds = load_verified()
    print(f"Loaded {len(ds)} instances from SWE-bench Verified")

    results = []
    for ex in ds:
        instance_id = ex["instance_id"]
        repo = ex["repo"]
        patch = ex.get("patch", "")
        test_patch = ex.get("test_patch", "")
        difficulty = ex.get("difficulty", "Unknown")

        changed = patch_line_count(patch)
        files = files_changed(patch)
        test_changed = patch_line_count(test_patch)

        weight = "light" if repo in LIGHTWEIGHT_REPOS else (
            "moderate" if repo in MODERATE_REPOS else "heavy"
        )

        results.append(
            {
                "instance_id": instance_id,
                "repo": repo,
                "difficulty": difficulty,
                "repo_weight": weight,
                "patch_lines": changed,
                "files_changed": sorted(files),
                "file_count": len(files),
                "test_patch_lines": test_changed,
            }
        )

    # Sort by: weight (light first), difficulty (Easy first), patch_lines (small first)
    weight_order = {"light": 0, "moderate": 1, "heavy": 2}
    diff_order = {"<15 min fix": 0, "15 min - 1 hour": 1, "1-4 hours": 2, ">4 hours": 3, "Unknown": 4}
    results.sort(
        key=lambda r: (
            weight_order.get(r["repo_weight"], 9),
            diff_order.get(r["difficulty"], 9),
            r["patch_lines"],
        )
    )

    print(f"\n=== SWE-bench Verified: {len(results)} instances ===\n")

    # Summary by repo + difficulty
    print("## By Repo + Difficulty")
    by_repo = defaultdict(lambda: defaultdict(int))
    for r in results:
        by_repo[r["repo"]][r["difficulty"]] += 1
    for repo in sorted(by_repo):
        inner = by_repo[repo]
        parts = ", ".join(f"{d}: {c}" for d, c in sorted(inner.items()))
        weight = "LIGHT" if repo in LIGHTWEIGHT_REPOS else (
            "MOD" if repo in MODERATE_REPOS else "HEAVY"
        )
        print(f"  [{weight}] {repo}: {parts}")

    # Show top light candidates
    print("\n## Top Candidates: Lightweight + <15 min fix + ≤30 patch lines\n")
    candidates = [
        r
        for r in results
        if r["repo_weight"] == "light"
        and r["difficulty"] == "<15 min fix"
        and r["patch_lines"] <= 30
    ]
    for c in candidates[:15]:
        print(
            f"  {c['instance_id']:55s} | {c['repo']:25s} | "
            f"patch={c['patch_lines']:3d} lines | files={c['file_count']} | "
            f"test_patch={c['test_patch_lines']:3d} lines"
        )

    # Show moderate Easy tasks
    print("\n## Moderate Repo Easy Tasks (≤15 patch lines)\n")
    mod_candidates = [
        r
        for r in results
        if r["repo_weight"] == "moderate"
        and r["difficulty"] == "Easy"
        and r["patch_lines"] <= 15
    ]
    for c in mod_candidates[:15]:
        print(
            f"  {c['instance_id']:55s} | {c['repo']:25s} | "
            f"patch={c['patch_lines']:3d} lines | files={c['file_count']} | "
            f"test_patch={c['test_patch_lines']:3d} lines"
        )

    # Save full analysis
    out_path = Path(__file__).parent / "swebench_candidates.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {out_path}")

    # Print sample problem statements
    print("\n## Sample Problem Statements (first 3 candidates)\n")
    ds_dict = {ex["instance_id"]: ex for ex in ds}
    for c in candidates[:3]:
        ex = ds_dict[c["instance_id"]]
        print(f"--- {c['instance_id']} ---")
        print(ex["problem_statement"][:500])
        print("...\n")

    # Print full details for top 5 light candidates
    print("\n## Top 5 Light Candidates — Full Details\n")
    for c in candidates[:5]:
        ex = ds_dict[c["instance_id"]]
        print(f"=== {c['instance_id']} ===")
        print(f"Repo: {c['repo']}  Difficulty: {c['difficulty']}")
        print(f"Patch: {c['patch_lines']} lines, Files: {c['files_changed']}")
        print(f"Test patch: {c['test_patch_lines']} lines")
        print(f"FAIL_TO_PASS: {ex['FAIL_TO_PASS']}")
        print(f"PASS_TO_PASS: {ex.get('PASS_TO_PASS', 'N/A')}")
        print(f"Base commit: {ex['base_commit']}")
        print(f"\nProblem:\n{ex['problem_statement'][:600]}")
        print("\n---\n")

    return candidates, ds_dict


if __name__ == "__main__":
    analyze()
