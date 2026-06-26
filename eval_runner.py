"""Evaluate SWE-bench patches using persistent Docker containers.

Starts 1 container per repo, then runs all eval via docker exec.
Avoids VFS overhead of creating new containers per instance.
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from collections import defaultdict
import os

os.environ["HF_HUB_OFFLINE"] = "1"
from datasets import load_dataset

INSTANCE_FILE = Path("/home/shared/agent-study/my-agent/claw-swe-bench/config/verified_mini_50.txt")

AGENTS = {
    "myagent": "/home/shared/agent-study/my-agent/claw-swe-bench/artifacts/myagent-50",
    "aider": "/home/shared/agent-study/my-agent/claw-swe-bench/artifacts/aider-host-50",
}

CONTAINERS = {
    "django/django": {"name": "eval-django", "image": "sweb.eval.x86_64.django__django-9296:latest"},
    "sphinx-doc/sphinx": {"name": "eval-sphinx", "image": "sweb.eval.x86_64.sphinx-doc__sphinx-7590:latest"},
}

OUTPUT_DIR = Path("/tmp/eval-output")


def docker(cmd, timeout=300):
    """Run a docker command through sg."""
    r = subprocess.run(
        ["sg", "docker", "-c", cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return r


def docker_exec(container, cmd, timeout=120):
    """Run a command inside a running container."""
    # Escape single quotes
    safe_cmd = cmd.replace("'", "'\\''")
    return docker(f"docker exec {container} bash -c '{safe_cmd}'", timeout=timeout)


def write_patch_and_copy(filename, content, container):
    """Write patch to temp file and copy into container."""
    path = f"/tmp/{filename}"
    with open(path, "w") as f:
        f.write(content)
    docker(f"docker cp {path} {container}:/tmp/{filename}", timeout=30)


def main():
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
    print("Starting containers (this may take 2-3 min each due to VFS)...")
    for repo, info in CONTAINERS.items():
        docker(f"docker rm -f {info['name']}", timeout=30)
        r = docker(f"docker run -d --name {info['name']} {info['image']} sleep 86400", timeout=300)
        if r.returncode != 0:
            print(f"  FAILED to start {info['name']}: {r.stderr[:200]}")
            sys.exit(1)
        print(f"  {info['name']} started")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Evaluate each agent
    for agent_name, artifact_dir in AGENTS.items():
        print(f"\n{'='*60}")
        print(f"Evaluating {agent_name}")
        print(f"{'='*60}")

        results = {}
        resolved = 0
        unresolved = 0
        errors = 0

        # Load patches
        predictions_file = Path(artifact_dir) / "predictions.jsonl"
        patches = {}
        if predictions_file.exists():
            for line in predictions_file.read_text().strip().split("\n"):
                if line:
                    p = json.loads(line)
                    patches[p["instance_id"]] = p.get("model_patch", "")
        else:
            for iid in instance_ids:
                patch_file = Path(artifact_dir) / iid / "git.patch"
                if patch_file.exists():
                    patches[iid] = patch_file.read_text()

        for idx, iid in enumerate(instance_ids, 1):
            ex = instances[iid]
            repo = ex["repo"]
            container = CONTAINERS[repo]["name"]
            base_commit = ex["base_commit"]
            test_patch = ex["test_patch"]
            patch = patches.get(iid, "")

            ftp = json.loads(ex["FAIL_TO_PASS"]) if isinstance(ex["FAIL_TO_PASS"], str) else ex["FAIL_TO_PASS"]
            ptp = json.loads(ex["PASS_TO_PASS"]) if isinstance(ex["PASS_TO_PASS"], str) else ex["PASS_TO_PASS"]

            if not patch.strip():
                results[iid] = "empty"
                errors += 1
                print(f"  [{idx:2d}/50] {iid} - EMPTY PATCH")
                continue

            # Copy patches into container
            write_patch_and_copy(f"test_{iid}.diff", test_patch, container)
            write_patch_and_copy(f"model_{iid}.diff", patch, container)

            # Build eval commands
            # Reset repo, apply patches, then run tests
            cmds = [
                f"cd /testbed",
                f"git reset --hard {base_commit}",
                "git clean -fd",
                f"git apply /tmp/test_{iid}.diff",
                f"git apply /tmp/model_{iid}.diff",
                "source /opt/miniconda3/bin/activate",
                "conda activate testbed",
            ]

            # Determine test runner
            if "django" in repo:
                test_prefix = 'python tests/runtests.py --verbosity=0 '
            else:
                test_prefix = 'python -m pytest -x -q '

            # Add all test commands
            for test in ftp + ptp:
                cmds.append(f"{test_prefix}{test} 2>&1 || exit 1")

            # Run as a single script
            eval_script = "#!/bin/bash\nset -e\n" + "\n".join(cmds)
            script_name = f"eval_{agent_name}_{iid}.sh"
            with open(f"/tmp/{script_name}", "w") as f:
                f.write(eval_script)
            docker(f"docker cp /tmp/{script_name} {container}:/tmp/{script_name}", timeout=30)

            t0 = time.time()
            r = docker_exec(container, f"bash /tmp/{script_name}", timeout=300)
            duration = time.time() - t0

            if r.returncode == 0:
                results[iid] = "resolved"
                resolved += 1
                status = "RESOLVED"
            elif r.returncode == 124 or "timed out" in r.stderr.lower():
                results[iid] = "timeout"
                errors += 1
                status = "TIMEOUT"
            else:
                results[iid] = "unresolved"
                unresolved += 1
                status = "UNRESOLVED"

            print(f"  [{idx:2d}/50] {iid} - {status} ({duration:.0f}s)")

        # Summary
        total = resolved + unresolved + errors
        rate = resolved / (resolved + unresolved) * 100 if (resolved + unresolved) > 0 else 0
        print(f"\n  {agent_name}: {resolved} resolved / {unresolved} unresolved / {errors} errors")
        print(f"  Resolve rate: {rate:.1f}%")

        # Save results
        result_path = OUTPUT_DIR / f"{agent_name}_results.json"
        with open(result_path, "w") as f:
            json.dump({
                "agent": agent_name,
                "resolved": resolved,
                "unresolved": unresolved,
                "errors": errors,
                "resolve_rate": round(rate, 1),
                "per_instance": results,
            }, f, indent=2)

    # Cleanup
    print("\nCleaning up containers...")
    for info in CONTAINERS.values():
        docker(f"docker rm -f {info['name']}", timeout=30)

    # Final comparison
    print("\n" + "="*60)
    print("FINAL COMPARISON")
    print("="*60)
    for agent_name in AGENTS:
        result_path = OUTPUT_DIR / f"{agent_name}_results.json"
        if result_path.exists():
            data = json.loads(result_path.read_text())
            print(f"  {agent_name}: {data['resolved']}/{data['resolved']+data['unresolved']} "
                  f"resolved ({data['resolve_rate']}%), {data['errors']} errors")


if __name__ == "__main__":
    main()
