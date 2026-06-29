"""Evaluate patches using persistent containers (1 per repo, avoiding VFS overhead).

For each instance:
  1. Reset repo to base_commit inside the container
  2. Apply the model's patch
  3. Run FAIL_TO_PASS and PASS_TO_PASS tests
  4. Grade: resolved, unresolved, or error
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from collections import defaultdict

from datasets import load_dataset

INSTANCE_FILE = Path("/home/shared/agent-study/my-agent/claw-swe-bench/config/verified_mini_50.txt")
ARTIFACTS = {
    "myagent": Path("/home/shared/agent-study/my-agent/claw-swe-bench/artifacts/myagent-50"),
    "aider": Path("/home/shared/agent-study/my-agent/claw-swe-bench/artifacts/aider-host-50"),
}

# One container per repo
REPO_CONTAINERS = {
    "django/django": "eval-django",
    "sphinx-doc/sphinx": "eval-sphinx",
}
REPO_IMAGES = {
    "django/django": "sweb.eval.x86_64.django__django-9296:latest",
    "sphinx-doc/sphinx": "sweb.eval.x86_64.sphinx-doc__sphinx-7590:latest",
}


def run(cmd, timeout=300):
    return subprocess.run(
        ["sg", "docker", "-c", cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def docker_exec(container, bash_cmd, timeout=300):
    """Run a command inside a running container."""
    return run(f"docker exec {container} bash -c '{bash_cmd}'", timeout=timeout)


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"

    # Load instances
    with open(INSTANCE_FILE) as f:
        instance_ids = [line.strip() for line in f if line.strip()]

    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    instances = {ex["instance_id"]: ex for ex in ds if ex["instance_id"] in set(instance_ids)}

    # Group by repo
    by_repo = defaultdict(list)
    for iid in instance_ids:
        ex = instances[iid]
        by_repo[ex["repo"]].append(iid)

    # Start containers
    print("Starting containers...")
    for repo, cname in REPO_CONTAINERS.items():
        run(f"docker rm -f {cname}", timeout=30)
        r = run(f"docker run -d --name {cname} {REPO_IMAGES[repo]} sleep 86400", timeout=300)
        if r.returncode != 0:
            print(f"  FAILED to start {cname}: {r.stderr[:200]}")
            sys.exit(1)
        print(f"  {cname} started")

    # Evaluate each agent's patches
    for agent_name, artifact_dir in ARTIFACTS.items():
        print(f"\n=== Evaluating {agent_name} ===")
        results = {}

        predictions_file = artifact_dir / "predictions.jsonl"
        if not predictions_file.exists():
            # Load patches from per-instance dirs
            patches = {}
            for iid in instance_ids:
                patch_file = artifact_dir / iid / "git.patch"
                if patch_file.exists():
                    patches[iid] = patch_file.read_text()
        else:
            patches = {}
            for line in predictions_file.read_text().strip().split("\n"):
                if line:
                    p = json.loads(line)
                    patches[p["instance_id"]] = p.get("model_patch", "")

        resolved = 0
        unresolved = 0
        errors = 0

        for idx, iid in enumerate(instance_ids, 1):
            ex = instances[iid]
            repo = ex["repo"]
            cname = REPO_CONTAINERS[repo]
            base_commit = ex["base_commit"]
            patch = patches.get(iid, "")
            fail_to_pass = json.loads(ex["FAIL_TO_PASS"]) if isinstance(ex["FAIL_TO_PASS"], str) else ex["FAIL_TO_PASS"]
            pass_to_pass = json.loads(ex["PASS_TO_PASS"]) if isinstance(ex["PASS_TO_PASS"], str) else ex["PASS_TO_PASS"]

            if not patch.strip():
                results[iid] = "empty_patch"
                errors += 1
                print(f"  [{idx}/{len(instance_ids)}] {iid} - EMPTY")
                continue

            # Reset to base commit
            r = docker_exec(cname, f"cd /testbed && git reset --hard {base_commit} && git clean -fd", timeout=60)
            if r.returncode != 0:
                results[iid] = "error"
                errors += 1
                print(f"  [{idx}/{len(instance_ids)}] {iid} - ERROR (git reset)")
                continue

            # Apply patch
            # Write patch to temp file first
            escaped = patch.replace("'", "'\\''")
            r = docker_exec(cname, f"cd /testbed && echo '{escaped}' | git apply --verbose", timeout=60)
            if r.returncode != 0:
                # Try without verbose
                r = docker_exec(cname, f"cd /testbed && echo '{escaped}' | git apply", timeout=60)
            if r.returncode != 0:
                results[iid] = "error"
                errors += 1
                print(f"  [{idx}/{len(instance_ids)}] {iid} - ERROR (patch apply failed)")
                continue

            # Run FAIL_TO_PASS tests
            ftp_passed = True
            for test in fail_to_pass:
                r = docker_exec(
                    cname,
                    f"source /opt/miniconda3/bin/activate && conda activate testbed && cd /testbed && python -m pytest {test} -x -q 2>&1",
                    timeout=120,
                )
                if r.returncode != 0:
                    ftp_passed = False
                    break

            # Run PASS_TO_PASS tests
            ptp_passed = True
            if ftp_passed:
                for test in pass_to_pass:
                    r = docker_exec(
                        cname,
                        f"source /opt/miniconda3/bin/activate && conda activate testbed && cd /testbed && python -m pytest {test} -x -q 2>&1",
                        timeout=120,
                    )
                    if r.returncode != 0:
                        ptp_passed = False
                        break

            if ftp_passed and ptp_passed:
                results[iid] = "resolved"
                resolved += 1
                status = "RESOLVED"
            else:
                results[iid] = "unresolved"
                unresolved += 1
                status = f"UNRESOLVED (ftp={'OK' if ftp_passed else 'FAIL'}, ptp={'OK' if ptp_passed else 'FAIL'})"

            print(f"  [{idx}/{len(instance_ids)}] {iid} - {status}")

        # Summary
        total = resolved + unresolved + errors
        rate = resolved / (resolved + unresolved) * 100 if (resolved + unresolved) > 0 else 0
        print(f"\n  {agent_name}: {resolved}/{total} resolved ({rate:.1f}%), {errors} errors")

        # Save results
        with open(artifact_dir / "eval_results.json", "w") as f:
            json.dump({
                "agent": agent_name,
                "resolved": resolved,
                "unresolved": unresolved,
                "errors": errors,
                "resolve_rate": round(rate, 1),
                "per_instance": results,
            }, f, indent=2)

    # Cleanup containers
    print("\n=== Cleanup ===")
    for cname in REPO_CONTAINERS.values():
        run(f"docker rm -f {cname}", timeout=30)
        print(f"  {cname} removed")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
